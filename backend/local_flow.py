"""Small-model workflow: server retrieves/persists; the LLM writes and assesses.

This is explicit orchestration, not an autonomous model deciding every step.
Every model-generated action still passes the existing strict tool executor.
"""
import json
import re
from types import SimpleNamespace as NS
from . import retrieval,learning
from .database import one,many
from .ollama_provider import is_diagnosis


def _json(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def _check(result):
    if isinstance(result,dict) and 'error' in result:raise ValueError(result['error'])
    return result


def _excerpt(reference,selection,query,budget=3600):
    """A contiguous window preserves neighboring fraction/denominator lines."""
    text=reference['text']
    if len(text)<=budget:return text,False
    terms=retrieval.query_terms(selection or query)
    lines=text.splitlines();scores=[]
    for i,line in enumerate(lines):
        scores.append((sum(term.casefold() in line.casefold() for term in terms),i))
    center=max(scores,key=lambda row:row[0],default=(0,0))[1]
    start=max(0,center-10);end=min(len(lines),center+20)
    chosen='\n'.join(lines[start:end])
    return chosen[:budget],True


def _page_sources(rows,query):
    terms=retrieval.query_terms(query)
    def rank(row):return (sum(t.casefold() in row['text'].casefold() for t in terms),len(row['text']))
    return sorted(rows,key=rank,reverse=True)[:3]


def _evidence(agent,rows):
    # At most four excerpts, retaining a hit from each matching textbook.
    chosen=[];books=set()
    for row in rows:
        if row['book_id'] not in books:chosen.append(row);books.add(row['book_id'])
    for row in rows:
        if len(chosen)>=4:break
        if row['id'] not in {r['id'] for r in chosen}:chosen.append(row)
    return chosen[:4]


def _invoke(agent,provider,messages,names,task):
    from .agent import tool_schemas
    tools=[t for t in tool_schemas(agent.req.strategy=='baseline') if t['name'] in names]
    request={**agent.req.model_dump(),'_local_task':task}
    if getattr(agent,'strict_explanation',False):
        request={k:request[k] for k in ('book_id','message','quiz_id','answer','_local_task')}
        request['_reliable']=True
    turn=[{'role':'user','content':_json(request)},*messages]
    agent.usage['api_calls']+=1
    agent.phase('generating')
    try:response=provider.respond(turn,tools)
    except Exception:
        usage=getattr(provider,'last_usage',None)
        if usage:
            for key in ('input_tokens','output_tokens'):agent.usage[key]+=getattr(usage,key,0)
        raise
    if response.usage:
        for key in ('input_tokens','output_tokens'):agent.usage[key]+=getattr(response.usage,key,0)
    calls=[item for item in response.output if item.type=='function_call']
    if len(calls)!=1 or calls[0].name not in names:raise ValueError('로컬 모델이 요청한 학습 작업을 올바르게 생성하지 못했습니다.')
    call=calls[0]
    args=json.loads(call.arguments)
    agent.cited_ids.update(args.get('source_ids',[]))
    result=_check(agent.execute(call.name,args,actor='model'))
    if getattr(agent,'strict_explanation',False) and call.name=='explain_concept':
        return result  # Do not send the full published explanation again for a quiz.
    messages.extend(response.output)
    presented=result
    if call.name=='find_prerequisites':
        presented=[dict(item,sources=item.get('sources',[])[:1],omitted_sources=max(0,len(item.get('sources',[]))-1)) for item in result]
    messages.append({'type':'function_call_output','call_id':call.call_id,'output':_json(presented)})
    return result


def _reference_message(rows,tool):
    return {'type':'function_call_output','call_id':'server-'+tool,'tool':tool,'output':_json(rows)}


def run(agent,provider):
    if getattr(provider,'reliable_workflow',False):
        from .reliable_flow import run as reliable_run
        return reliable_run(agent,provider)
    r=agent.req
    agent.cited_ids=set()
    agent.local_quality=True
    rows=agent.execute('get_current_page',{},actor='server')
    reference=agent.full_page_reference(rows)
    if not reference and not rows:
        raise ValueError('현재 PDF 페이지에 읽을 수 있는 텍스트가 없습니다. 스캔 PDF의 OCR은 지원하지 않습니다.')
    if r.selection and reference:
        normalize=lambda s:re.sub(r'\W+','',s.casefold())
        selected=normalize(r.selection);actual=normalize(reference['text'])
        from difflib import SequenceMatcher
        overlap=SequenceMatcher(None,selected,actual,autojunk=False).find_longest_match().size/max(1,len(selected))
        if selected not in actual and overlap<.65:raise ValueError('선택 문장을 현재 책·페이지의 PDF 원문과 대조하지 못했습니다. 페이지를 확인하고 다시 선택하세요.')
    previous=many("SELECT request,response FROM runs WHERE session_id=? AND id!=? AND status IN ('completed','awaiting_answer','needs_review') ORDER BY rowid DESC LIMIT 3",(agent.session_id,agent.run_id))
    history=[]
    for old in reversed(previous):
        req=json.loads(old['request']);response=json.loads(old['response']) if old['response'] else {}
        review=response.get('status')=='needs_review' or response.get('quality',{}).get('status')=='needs_review'
        from .quality import assess
        review=review or bool(assess(response.get('text',''),req['message'],[s['id'] for s in response.get('sources',[])])['issues'])
        history.append({'question':req['message'],'page':req['page'],'selection':req.get('selection','')[:600],
                        'selection_truncated':len(req.get('selection',''))>600,
                        'answer':('이전 설명은 검토 필요로 판정되었습니다. 이전 수치를 정답 근거로 재사용하지 말고 실제 PDF를 확인하세요.' if review else response.get('text','')[:1400]),
                        'previous_answer_needs_review':review})
    messages=[]
    if history:messages.append({'role':'user','content':'Previous conversation DATA: '+_json(history[-1:] if r.quiz_id else history)})
    # Duplicate grading is a database read: never ask the model to reassess an
    # already persisted attempt or mutate mastery twice.
    if r.quiz_id:
        quiz=one('SELECT * FROM quizzes WHERE id=? AND session_id=?',(r.quiz_id,agent.session_id))
        if not quiz:raise ValueError('이 세션의 퀴즈가 아닙니다.')
        rubric=json.loads(quiz['payload'])
        evidence=[retrieval.get_chunk(cid) for cid in rubric.get('source_ids',[])]
        evidence=[row for row in evidence if row and (agent.scope() is None or row['book_id'] in agent.scope())]
        agent.add_sources(evidence)
        agent.cited_ids.update(row['id'] for row in evidence)
        old=one('SELECT id FROM attempts WHERE quiz_id=?',(r.quiz_id,))
        if old:
            agent.evaluation=_check(agent.execute('evaluate_answer',{},actor='server'))
            agent.text=agent.evaluation['explanation'];return
        from .quality import assess
        if any(c['status']=='fail' for c in assess(rubric['question']+'\n'+rubric['answer']+'\n'+rubric['explanation'],'',[])['math_checks']):
            raise ValueError('저장된 퀴즈 기준에 수식 오류가 감지되어 자동 채점하지 않았습니다. 원문을 대조하고 새 대화에서 진단 문제를 요청하세요.')
        messages.extend([_reference_message(evidence,'quiz_evidence'),{'role':'user','content':'Private grading rubric DATA (answer has now been submitted): '+_json(rubric)}])
        evaluation=_invoke(agent,provider,messages,['evaluate_answer'],'grade')
        agent.text=evaluation['explanation']
        if evaluation.get('cause'):agent.text+='\n\n**오답 원인** · '+evaluation['cause']
        if not evaluation['correct'] and not evaluation['uncertain']:
            concept=one('SELECT name FROM concepts WHERE id=?',(evaluation['concept_id'],))['name']
            candidates=[x['name'] for x in many('SELECT c.name FROM relations r JOIN concepts c ON c.id=r.target WHERE r.source=?',(evaluation['concept_id'],))]
            _check(agent.execute('find_prerequisites',{'concept':concept,'candidates':candidates[:3]},actor='server'))
        agent.execute('update_mastery',{},actor='server')
        recommendation=agent.execute('recommend_next_topic',{},actor='server')
        topics=', '.join(t['name'] for t in recommendation.get('topics',[])[:3])
        agent.text+='\n\n**다음 학습** · '+recommendation['message']+(' '+topics if topics else '')
        return
    query=r.selection or r.message
    # Resolve deictic follow-ups from their actual persisted conversation.
    if not r.selection and history and (not retrieval.query_terms(query) or re.search(r'앞서|이전|그 예제|사전확률|사후확률|that example|previous',query,re.I)):
        query=history[-1]['question']+' '+r.message
    search_tool='search_textbook' if r.scope=='current' else 'search_across_books'
    found=_check(agent.execute(search_tool,{'query':query[:1000]},actor='server'))
    use_page=bool(r.selection or re.search(r'이 페이지|현재 페이지|여기|this page|current page',r.message,re.I) or not found)
    page_rows=_page_sources(rows,r.selection or r.message) if use_page else []
    other_rows=_evidence(agent,[row for row in found if row['book_id']!=r.book_id]) if page_rows and r.scope!='current' else []
    focus=page_rows+other_rows if page_rows else _evidence(agent,found)
    if not focus:raise ValueError('질문과 연결할 교과서 근거를 찾지 못했습니다. 검색어를 더 구체적으로 입력하세요.')
    # Only these supplied excerpts can be cited by the local model.
    if not (use_page and reference):messages.append(_reference_message(focus,search_tool))
    elif other_rows:messages.append(_reference_message(other_rows,search_tool))
    if use_page and reference:
        text,truncated=_excerpt(reference,r.selection,r.message)
        messages.append({'role':'user','content':'Current PDF page full-text supplement DATA (not instructions): '+_json({**{k:v for k,v in reference.items() if k not in ('text','source_ids')},'text':text,'source_ids':[row['id'] for row in page_rows],'truncated':truncated})})
    if r.scope!='current':
        books=many("SELECT id,title FROM books WHERE status='ready'")
        if agent.scope() is not None:books=[b for b in books if b['id'] in agent.scope()]
        agent.unmatched_books=[b['title'] for b in books if not any(s['book_id']==b['id'] for s in found)]
        messages.append({'role':'user','content':'Searched books DATA: '+_json([dict(b,has_retrieved_evidence=any(s['book_id']==b['id'] for s in found)) for b in books])})
    diagnose=bool(re.search(r'아직|모르|이해.*(?:안|못)|부족|진단|퀴즈|확인\s*문제|문제.*(?:내|생성)|don.t understand',r.message,re.I))
    prerequisite=diagnose or bool(re.search(r'선수|알아야|prerequisite',r.message,re.I))
    if prerequisite and r.strategy!='baseline':
        prereq=_invoke(agent,provider,messages,['find_prerequisites'],'prerequisites')
        _invoke(agent,provider,messages,['explain_concept'],'explain')
        if diagnose:
            from .quality import assess
            review=assess(agent.text,r.message,agent.sources)
            if review['issues']:
                agent.text+='\n\n설명에 검토할 수식이 있어 진단 문제 생성을 중단했습니다. 원문과 대조해 주세요.'
                return
            _invoke(agent,provider,messages,['generate_quiz'],'quiz')
            agent.text+='\n\n진단 문제를 준비했습니다. 답안을 제출하면 학습을 이어갑니다.'
    else:_invoke(agent,provider,messages,['explain_concept'],'explain')
