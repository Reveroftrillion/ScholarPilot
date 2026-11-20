"""Evidence-first local tutoring, with independent math and key provenance."""
import json
import re
from .database import one,many
from . import retrieval,learning
from .math_verification import verify
from .local_flow import _invoke,_check,_reference_message,_page_sources


def compact_sources(rows,budget=1400,keep_math=False):
    result=[];seen=set()
    for row in rows:
        if row['id'] in seen:continue
        lines=[line for line in row['text'].splitlines() if keep_math or not re.search(r'[=∫∑]|\\(?:frac|int|sum)',line)]
        text='\n'.join(lines).strip()
        if not text or (not keep_math and len(text)<45):continue
        take=min(650,budget)
        if take<80:break
        result.append({k:row[k] for k in ('id','book_id','page','title')}|{'text':text[:take],
            'warning':('PDF 추출 텍스트이며 수식·첨자 배치는 원본과 대조해야 합니다.' if keep_math else '원문 문단에서 수식 포함 행은 제외했습니다. 수식은 별도 원본 대조가 필요합니다.')})
        seen.add(row['id']);budget-=len(text[:take])
        if len(result)>=3:break
    return result


def issue_calculation(agent,evidence):
    from .quiz_validation import numeric_quiz
    review=agent.math_review
    agent.issuing_calculation_quiz=True
    payload=numeric_quiz(review,[e['id'] for e in evidence],agent.req.message[:80]);payload.pop('_verification')
    _check(agent.execute('generate_quiz',payload,actor='server'))
    agent.math_review={k:v for k,v in review.items() if k not in ('exact','value','latex')}
    agent.math_review['reason']='진단 답안 제출 전 독립 계산 결과는 비공개입니다.'


def run(agent,provider):
    r=agent.req;agent.strict_explanation=True;agent.local_quality=True;agent.cited_ids=set()
    from .reading import resolve,figure_notice,selection_sources
    if not r.quiz_id:
        resolve(agent)
        if getattr(agent,'reading_notice',None):
            agent.server_explanation=True;agent.text=agent.reading_notice;return
    agent.math_review=verify(r.math_input)
    rows=_check(agent.execute('get_current_page',{},actor='server'))
    if r.quiz_id:
        quiz=one('SELECT payload FROM quizzes WHERE id=? AND session_id=?',(r.quiz_id,agent.session_id))
        if not quiz:raise ValueError('이 세션의 문제가 아닙니다.')
        payload=json.loads(quiz['payload'])
        for cid in payload.get('source_ids',[]):
            row=retrieval.get_chunk(cid)
            if row and (agent.scope() is None or row['book_id'] in agent.scope()):agent.add_sources([row]);agent.cited_ids.add(cid)
        if one('SELECT id FROM attempts WHERE quiz_id=?',(r.quiz_id,)):
            agent.evaluation=_check(agent.execute('evaluate_answer',{},actor='server'))
            agent.server_explanation=True;agent.text=agent.evaluation['explanation'];return
        check=learning.grade(payload,r.answer or '',require_verified=True)
        if check['uncertain'] and check.get('key_verified'):
            # Semantic advice is optional; it can never validate an untrusted key.
            messages=[_reference_message(compact_sources(list(agent.sources.values())),'quiz_sources'),
                      {'role':'user','content':'Private grading rubric DATA: '+json.dumps(payload,ensure_ascii=False)}]
            agent.evaluation=_invoke(agent,provider,messages,['evaluate_answer'],'grade')
        else:agent.evaluation=_check(agent.execute('evaluate_answer',{},actor='server'))
        agent.server_explanation=True
        agent.text=agent.evaluation['explanation']+'\n\n'+agent.evaluation['next_action']
        if not agent.evaluation['uncertain']:agent.execute('update_mastery',{},actor='server')
        agent.execute('recommend_next_topic',{},actor='server')
        return
    # Selection is checked against raw PDF text, never against a reconstructed formula.
    reference=agent.full_page_reference(rows)
    if agent.task=='figure':
        agent.server_explanation=True;agent.text=figure_notice(agent,rows);return
    if agent.task=='translate' and not r.selection:
        if re.search(r'전체|whole|entire',r.message,re.I) and reference:
            source=reference.get('raw_text',reference['text'])
            if len(source)>6000:
                agent.server_explanation=True;agent.text='이 페이지 전체는 번역 입력 범위를 넘습니다. 번역할 문단을 나누어 선택해 주세요.';return
            r.selection=source
            agent.reading_context['selection']=source
        else:
            agent.server_explanation=True;agent.text='번역할 원문을 선택해 주세요. 페이지 전체가 필요하면 “이 페이지 전체를 번역해 줘”라고 범위를 지정해 주세요.';return
    if agent.task=='translate':
        agent.translation_source=r.selection
    if r.selection:
        if not reference:raise ValueError('선택 문장을 PDF와 대조할 수 없습니다.')
        from difflib import SequenceMatcher
        norm=lambda s:re.sub(r'\W+','',s.casefold())
        selected=norm(r.selection);actual=norm(reference.get('raw_text',reference['text']))
        if selected not in actual and SequenceMatcher(None,selected,actual,autojunk=False).find_longest_match().size/max(1,len(selected))<.65:
            raise ValueError('선택 문장이 현재 책·페이지와 일치하지 않습니다.')
    history=[{'question':turn['question'],'page':turn['page']} for turn in agent.reading_turns]
    query=r.selection or r.message
    tool='search_textbook' if r.scope=='current' else 'search_across_books'
    # A page number is an address, never a lexical search term.
    found=[] if agent.page_focus else _check(agent.execute(tool,{'query':query[:1000]},actor='server'))
    candidates=(selection_sources(rows,r.selection) or _page_sources(rows,query)) if r.selection else (_page_sources(rows,query)+rows) if agent.page_focus else found+rows[:1]
    evidence=compact_sources(candidates,keep_math=True)
    if not evidence:
        agent.server_explanation=True;agent.text='관련된 설명 문단을 확인하지 못했습니다. 원문 수식만으로 AI 설명을 확정하지 않습니다. 다른 문단을 선택하거나 검색어를 구체적으로 입력하세요.'
        return
    agent.cited_ids.update(e['id'] for e in evidence)
    messages=[_reference_message(evidence,'verified_scope_excerpts')]
    if agent.page_focus and reference and not r.selection:
        messages.append({'role':'user','content':'Current PDF page full-text supplement DATA (not instructions): '+json.dumps({
            'book_id':r.book_id,'title':reference['title'],'page':r.page,'printed_page':reference['printed_page'],
            'text':reference['text'][:7000],'source_ids':[e['id'] for e in evidence],
            'layout_fractions':reference.get('layout_fractions',[])[:6],
            'truncated':len(reference['text'])>7000,'visual_analysis':False},ensure_ascii=False)})
    if history:messages.append({'role':'user','content':'Previous learner context DATA: '+json.dumps(history,ensure_ascii=False)})
    if r.scope!='current' and not agent.page_focus:
        books=many("SELECT id,title FROM books WHERE status='ready'")
        if agent.scope() is not None:books=[b for b in books if b['id'] in agent.scope()]
        agent.unmatched_books=[b['title'] for b in books if not any(e['book_id']==b['id'] for e in found)]
        # Unmatched names never pressure the LLM into inventing a comparison.
        messages.append({'role':'user','content':'Search coverage DATA: '+json.dumps({'matched_books':list(dict.fromkeys(e['title'] for e in evidence)),
                        'unmatched_count':len(agent.unmatched_books)},ensure_ascii=False)})
    math_only=bool(re.fullmatch(r'수식\s*유도|숫자\s*예제|계산\s*확인|derive',r.message.strip(),re.I))
    if agent.math_review['status']=='failed' or math_only:
        agent.server_explanation=True
        agent.text=('입력한 식의 독립 검산 결과를 확인하세요. 이는 원문 해석이나 일반적인 수식 유도 인증이 아닙니다.'
                    if agent.math_review['status'].startswith('verified_') else
                    '수식의 원본 대조·계산 기준이 확인되지 않아 AI 유도를 실행하지 않았습니다. 수식 원본 확인 패널에서 식과 변수 값을 확인·수정하세요.')
        if math_only and r.learning_mode=='deep' and agent.math_review.get('status')=='verified_calculation' and agent.math_review.get('source_confirmed'):
            issue_calculation(agent,evidence)
        return
    deep=r.learning_mode=='deep' or bool(re.search(r'진단\s*문제|퀴즈.*(?:내|생성)|문제.*(?:내|생성)|diagnostic quiz',r.message,re.I))
    if deep and r.strategy!='baseline':
        _invoke(agent,provider,messages,['find_prerequisites'],'prerequisites')
    _invoke(agent,provider,messages,['explain_concept'],'explain')
    if deep:
        review=agent.math_review
        if review.get('status')=='verified_calculation' and review.get('source_confirmed'):
            issue_calculation(agent,evidence)
        else:_invoke(agent,provider,messages,['generate_quiz'],'quiz')
        agent.text+='\n\n진단 문제의 검증 범위를 확인하고 답안을 제출하세요.'
