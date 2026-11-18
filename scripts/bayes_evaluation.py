"""Approval-gated Bishop evaluation. Default plan makes no network requests."""
import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.providers import OpenAIProvider,SYSTEM,AIRequestError
from backend.agent import Agent,ChatRequest
from backend.database import init_db,one,many,data_path
from scripts.validate_learning_record import RUBRIC,validate

MODEL='gpt-6-luna'
INPUT_RATE=.10
OUTPUT_RATE=.50
RESERVATION_INPUT_RATE=INPUT_RATE*1.25 # Also allow for documented cache-write pricing.
PRICING_URL='https://developers.openai.com/api/docs/models/gpt-6-luna'

def plain(value):
    if hasattr(value,'model_dump'):return value.model_dump(mode='json')
    if isinstance(value,NS):return vars(value)
    raise TypeError(type(value).__name__)

def safe_copy(value):
    # Never retain hidden reasoning items. Request headers/client/key are never passed here.
    text=json.dumps(value,default=plain,ensure_ascii=False)
    if settings.openai_api_key:text=text.replace(settings.openai_api_key,'[REDACTED]')
    text=re.sub(r'sk-[A-Za-z0-9_-]{12,}','[REDACTED]',text)
    def clean(v):
        if isinstance(v,list):return [clean(x) for x in v if not isinstance(x,dict) or x.get('type')!='reasoning']
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in ('api_key','authorization')}
        return v
    return clean(json.loads(text))

class BudgetedProvider:
    def __init__(self,delegate,*,max_calls=24,budget_usd=1.):
        if not 1<=max_calls<=24 or not 0<budget_usd<=1:raise ValueError('Limits: 1..24 calls, USD >0 and <=1')
        self.delegate=delegate;self.max_calls=max_calls;self.budget=budget_usd
        self.reserved=0.;self.records=[]
        self.trace_path=None

    def respond(self,messages,tools):
        if len(self.records)>=self.max_calls:raise ValueError('Evaluation API call limit reached')
        # UTF-8 bytes + framing allowance is a conservative local token proxy,
        # not the API's tokenizer. Includes instructions, schemas and all history.
        input_bound=len(json.dumps({'instructions':SYSTEM,'input':messages,'tools':tools},default=plain,ensure_ascii=False).encode('utf-8'))+8192
        if input_bound>80000:raise ValueError('Evaluation input size limit reached')
        reserve=(input_bound*RESERVATION_INPUT_RATE+2400*OUTPUT_RATE)/1e6
        if self.reserved+reserve>self.budget:raise ValueError('Evaluation cost reservation limit reached')
        self.reserved+=reserve # Never refund reservations, including failed/unknown-usage calls.
        record={'request':safe_copy({'instructions':SYSTEM,'input':messages,'tools':tools}),
            'model_requested':MODEL,'input_token_proxy_bound':input_bound,'reserved_usd':reserve,'status':'started',
            'usage':{'input_tokens':None,'output_tokens':None},'estimated_usd':None}
        self.records.append(record);start=time.monotonic()
        # Persist the attempted call before sending, so a process interruption
        # cannot reset the approved request budget on resume.
        if self.trace_path:
            self.trace_path.write_text(json.dumps(safe_copy(self.records),ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            response=self.delegate.respond(messages,tools)
            usage=getattr(response,'usage',None)
            input_tokens=getattr(usage,'input_tokens',None);output_tokens=getattr(usage,'output_tokens',None)
            record.update(status='completed',model_returned=getattr(response,'model',None),
                response=safe_copy({'output':[x for x in response.output if x.type!='reasoning'],'output_text':response.output_text}),
                usage={'input_tokens':input_tokens,'output_tokens':output_tokens},
                estimated_usd=(input_tokens*INPUT_RATE+output_tokens*OUTPUT_RATE)/1e6 if input_tokens is not None and output_tokens is not None else None)
            return response
        except Exception as exc:
            record['status']='error' # SDK error strings can contain credentials; do not persist them.
            record['error_type']=type(exc).__name__
            record['http_status']=getattr(exc,'status_code',None)
            code=getattr(exc,'code',None)
            record['error_code']=code if isinstance(code,str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',code) else None
            if isinstance(exc,AIRequestError):raise ValueError(str(exc)) from None
            raise ValueError('Evaluation model request failed; no automatic retry') from None
        finally:
            record['elapsed_seconds']=round(time.monotonic()-start,3)
            if self.trace_path:
                self.trace_path.write_text(json.dumps(safe_copy(self.records),ensure_ascii=False,indent=2),encoding='utf-8')

class OfflineResponsesClient:
    """Deterministic SDK-shaped stand-in. Does not assess model quality."""
    def __init__(self):self.responses=self;self.count=0
    def create(self,**kwargs):
        self.count+=1;messages=kwargs['input']
        req=next(json.loads(m['content']) for m in reversed(messages) if isinstance(m,dict) and m.get('role')=='user' and m.get('content','').startswith('{') and 'book_id' in m['content'])
        page=next(json.loads(m['content'].split(': ',1)[1]) for m in messages if isinstance(m,dict) and m.get('content','').startswith('Current PDF page'))
        source=max(page,key=lambda x:len(x['text']))
        done={x.name for x in messages if getattr(x,'type',None)=='function_call'}
        calls=[];text=''
        explanation='[오프라인 대역] $P(A|B)=P(B|A)P(A)/P(B)$에서 $P(B)>0$입니다. 실제 AI 품질은 미검증입니다.'
        if req.get('quiz_id'):
            if 'evaluate_answer' not in done:calls=[('evaluate_answer',{'correct':False,'confidence':1,'explanation':'조건부확률은 조건을 만족하는 경우로 표본 공간을 제한합니다.','cause':'조건부확률과 결합확률 혼동'})]
            elif 'find_prerequisites' not in done:calls=[('find_prerequisites',{'concept':'Bayes theorem','candidates':['conditional probability']})]
            elif 'explain_concept' not in done:calls=[('explain_concept',{'text':explanation,'source_ids':[source['id']]})]
            elif 'recommend_next_topic' not in done:calls=[('recommend_next_topic',{})]
            else:text=explanation+' 조건부확률을 복습하세요.'
        elif '이해' in req['message']:
            if 'find_prerequisites' not in done:calls=[('find_prerequisites',{'concept':'Bayes theorem','candidates':['conditional probability']})]
            elif 'explain_concept' not in done:calls=[('explain_concept',{'text':explanation,'source_ids':[source['id']]})]
            elif 'generate_quiz' not in done:calls=[('generate_quiz',{'concept':'Conditional probability','kind':'choice','question':'조건부확률은 무엇인가요?','choices':['조건을 고정한 확률','항상 1인 확률'],'answer':'조건을 고정한 확률','explanation':'조건으로 표본 공간을 제한합니다.','source_ids':[source['id']]})]
            else:text='[오프라인 대역] 확인 문제에 답하세요.'
        elif 'search_textbook' not in done:calls=[('search_textbook',{'query':'Bayes theorem'})]
        else:text=explanation+f" [교과서 PDF {source['page']}p](#source-{source['id']})"
        return NS(status='completed',model='offline-fixture',output=[NS(type='function_call',name=n,arguments=json.dumps(a,ensure_ascii=False),call_id=f'bayes-{self.count}') for n,a in calls],output_text=text,usage=NS(input_tokens=0,output_tokens=0))

def prepare_isolated(include_all=False,category='bayes-evaluation-runs'):
    if category not in ('bayes-evaluation-runs','local-evaluation-runs'):raise ValueError('Invalid evaluation category')
    original=Path(settings.data_dir).resolve();source=original/'scholarpilot.db'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row;con.execute('BEGIN')
        book=con.execute("SELECT * FROM books WHERE title LIKE '%Bishop%' AND status='ready'").fetchone()
        if not book:raise ValueError('Ready Bishop textbook required')
        book=dict(book)
        books=[dict(r) for r in con.execute("SELECT * FROM books WHERE status='ready'")] if include_all else [book]
        target=ROOT/'data'/category/uuid.uuid4().hex
        settings.data_dir=str(target);init_db()
        with sqlite3.connect(target/'scholarpilot.db') as dest:
            for copied_book in books:
                for table in ('books','sections','chunks'):
                    rows=con.execute(f'SELECT * FROM {table} WHERE '+('id=?' if table=='books' else 'book_id=?'),(copied_book['id'],)).fetchall()
                    if rows:dest.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in rows[0])})',[tuple(r) for r in rows])
            dest.execute('INSERT INTO chunks_fts(text,chunk_id,book_id) SELECT text,id,book_id FROM chunks')
    for copied_book in books:
        shutil.copy2(original/'pdfs'/f"{copied_book['id']}.pdf",target/'pdfs'/f"{copied_book['id']}.pdf")
    (target/'.scholarpilot-evaluation').write_text('isolated Bayes assessment; no user learning history copied\n',encoding='utf-8')
    return book,target

def source_checks(run):
    import pymupdf
    checks=[]
    for s in run['sources']:
        chunk=one('SELECT * FROM chunks WHERE id=? AND book_id=? AND page=?',(s['id'],s['book_id'],s['page']))
        with pymupdf.open(data_path()/'pdfs'/f"{s['book_id']}.pdf") as doc:
            match=any(s['text'] in b[4].strip() for b in doc[s['page']-1].get_text('blocks',sort=True))
        checks.append({'chunk_id':s['id'],'pdf_page':s['page'],'metadata_verified':bool(chunk),'pdf_text_verified':match})
    refs=re.findall(r'#source-([\w-]+)',run['text'])
    return {'sources':checks,'citation_count':len(refs),'unresolved_citations':[r for r in refs if r not in {s['id'] for s in run['sources']}],
            'semantic_grounding':'requires human review','formula_accuracy':'requires human review'}

def workflow(provider,mode,book,target):
    cases=json.loads((ROOT/'docs/learning-cases.json').read_text(encoding='utf-8'))
    case=next(c for c in cases if c['id']=='L01')
    records=[];session=None
    def turn(message,**extra):
        nonlocal session
        req=ChatRequest(book_id=book['id'],page=case['pdf_page'],message=message,session_id=session,**extra)
        before=len(provider.records);run=Agent(req,provider).run();session=run['session_id']
        calls=provider.records[before:]
        estimated=[c.get('estimated_usd') for c in calls]
        record={'case_id':case['id'],'mode':mode,'model':MODEL if mode=='live' else 'offline-fixture',
            'request_context':req.model_dump(),'retrieved_sources':run['sources'],'agent_tools':run['events'],'response':run['text'],
            'elapsed_seconds':run['elapsed'],'usage':run['usage'],
            'cost_estimate':{'amount':sum(estimated) if all(x is not None for x in estimated) else None,'currency':'USD','input_rate_per_million':INPUT_RATE,'output_rate_per_million':OUTPUT_RATE,'pricing_date':'2026-11-17'},
            'evaluation':{'reviewer':None,'scores':dict.fromkeys(RUBRIC),'notes':'Unscored: offline fixture or pending independent human review'},
            'status':run['status'],'source_checks':source_checks(run),'model_calls':calls}
        validate(record);records.append(safe_copy(record))
        (target/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        return run
    initial=turn("Bishop의 Bayes' theorem을 검색하고 한국어로 설명해 주세요. 수식의 모든 기호, 곱의 법칙을 이용한 유도, 분모가 양수여야 하는 조건과 생성 계산 예제를 출처와 함께 설명해 주세요.")
    diagnosis=turn('아직 이해하지 못했어요. conditional probability 등 선수 지식을 검색하고 보충한 뒤 객관식 확인 문제를 하나 내 주세요. 정답은 기다려 주세요.') if initial['status']!='error' else None
    graded=None
    if diagnosis and diagnosis['quiz'] and diagnosis['status']!='error':
        quiz=diagnosis['quiz'];stored=json.loads(one('SELECT payload FROM quizzes WHERE id=?',(quiz['id'],))['payload'])
        # Injected simulated learner answer is labelled, never real-user evidence.
        if stored['kind']=='choice':wrong=next(x for x in stored['choices'] if x!=stored['answer'])
        elif stored['kind']=='numeric':wrong=str(float(stored['answer'])+max(1,stored.get('tolerance',.001)*10))
        else:wrong='조건부확률은 언제나 1이라고 생각합니다.'
        graded=turn('평가용 모의 학습자 답안입니다. 오답이면 원인과 선수 개념을 설명하고 상태를 갱신한 후 다음 학습을 추천해 주세요.',quiz_id=quiz['id'],answer=wrong)
    history=many('SELECT state FROM sessions WHERE id=?',(session,))
    events=[e for r in records for e in r['agent_tools']]
    names={e['tool'] for e in events if e['status']=='ok'}
    required={'search_textbook','find_prerequisites','generate_quiz','evaluate_answer','update_mastery','recommend_next_topic'}
    mastery=many('SELECT * FROM mastery')
    source_verified=all(c['metadata_verified'] and c['pdf_text_verified'] for r in records for c in r['source_checks']['sources'])
    summary={'mode':mode,'model':MODEL if mode=='live' else 'offline-fixture','planned_live_model':MODEL,'isolated_directory':str(target.relative_to(ROOT)),
        'actual_external_calls':len(provider.records) if mode=='live' else 0,'provider_calls':len(provider.records),
        'reserved_cost_usd':provider.reserved,'estimated_cost_usd':sum(c['estimated_usd'] for c in provider.records) if all(c.get('estimated_usd') is not None for c in provider.records) else None,
        'required_tools_present':required<=names,'missing_tools':sorted(required-names),'quiz_paused':bool(diagnosis and diagnosis['status']=='awaiting_answer'),
        'wrong_answer_recorded':bool(graded and graded['evaluation'] and not graded['evaluation']['correct'] and not graded['evaluation']['uncertain']),
        'mastery_updated':any(m['total']>=1 for m in mastery),'restored_session_state':history,
        'review_recommended':any(e['tool']=='recommend_next_topic' and e['status']=='ok' and e['output'].get('action')=='review' for e in events),
        'source_metadata_and_pdf_verified':source_verified,
        'unresolved_citations':[c for r in records for c in r['source_checks']['unresolved_citations']],
        'initial_citation_present':bool(records and records[0]['source_checks']['citation_count']),
        'all_runs_successful':all(r['status']!='error' for r in records),'human_quality_scores':None,
        'records_path':str((target/'records.json').relative_to(ROOT))}
    (target/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['plan','offline','live'],default='plan')
    p.add_argument('--approve-paid-api',action='store_true');a=p.parse_args(argv)
    plan={'model':MODEL,'expected_provider_calls':'about 10-20; model-dependent','max_provider_calls':24,'max_output_tokens_per_call':2400,
          'budget_usd':1.,'input_token_proxy_limit_per_call':80000,'input_rate_per_million':INPUT_RATE,'output_rate_per_million':OUTPUT_RATE,
          'reservation_input_rate_per_million':RESERVATION_INPUT_RATE,'reasoning_effort':'low',
          'pricing_source':PRICING_URL,'pricing_checked':'2026-11-17','network_requests':0,'key_configured_in_dotenv':bool(settings.openai_api_key)}
    if a.mode=='plan':print(json.dumps(plan,indent=2));return
    if a.mode=='live' and not a.approve_paid_api:raise SystemExit('Paid calls require explicit --approve-paid-api after user approval')
    if a.mode=='live' and (not settings.allow_external_ai or not settings.openai_api_key or settings.ai_provider!='openai'):
        raise SystemExit('Set .env OPENAI_API_KEY, AI_PROVIDER=openai and ALLOW_EXTERNAL_AI=true after approval')
    old_dir,old_mode=settings.data_dir,settings.ai_mode
    try:
        delegate=OpenAIProvider(model=MODEL) if a.mode=='live' else OpenAIProvider(OfflineResponsesClient(),model=MODEL)
        provider=BudgetedProvider(delegate)
        book,target=prepare_isolated();provider.trace_path=target/'model-calls.json'
        settings.ai_mode='live' # Same orchestration, injected offline transport when offline.
        summary=workflow(provider,'live' if a.mode=='live' else 'offline_fixture',book,target)
        if a.mode=='offline':(ROOT/'docs/bayes-offline-readiness.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=True,indent=2))
        checks=['all_runs_successful','required_tools_present','wrong_answer_recorded','quiz_paused','mastery_updated',
                'source_metadata_and_pdf_verified','initial_citation_present','review_recommended']
        if not all(summary[k] for k in checks) or summary['unresolved_citations']:raise SystemExit(1)
    finally:settings.data_dir,settings.ai_mode=old_dir,old_mode

if __name__=='__main__':main()
