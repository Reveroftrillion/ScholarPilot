"""Offline workflow comparison using shared questions and original test PDFs.

Does not call external AI. Generates a new isolated database and leaves existing
data intact. Mock results do not measure explanation quality or learning impact.
"""
import argparse
import csv
import json
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymupdf
from backend.config import settings,ROOT
from backend.database import data_path,init_db,one,many
from backend.ingestion import register_pdf,index_book
from backend.agent import Agent,ChatRequest
from scripts.evaluate_retrieval import CASES,contains_group

def fixture_pdf(number):
    doc=pymupdf.open()
    for i,(label,query,groups) in enumerate(CASES):
        p=doc.new_page()
        concepts=' and '.join(group[0] for group in groups)
        text=f'Independent evaluation document {number}. Topic {i+1}: {concepts}. '
        text+=f'This original test passage discusses {concepts} and related evidence. '
        text+='Conditional probability is a useful prerequisite. This is synthetic evaluation text.'
        p.insert_textbox(pymupdf.Rect(50,50,540,750),text,fontsize=11)
    doc.set_metadata({'title':f'Original assessment document {number}','author':'ScholarPilot evaluation'})
    doc.set_toc([[1,case[0],i+1] for i,case in enumerate(CASES)])
    data=doc.tobytes();doc.close();return data

def verify_sources(sources):
    if not sources:return False
    for source in sources:
        if not one('SELECT id FROM chunks WHERE id=? AND book_id=? AND page=?',(source['id'],source['book_id'],source['page'])):return False
        with pymupdf.open(data_path()/'pdfs'/f"{source['book_id']}.pdf") as doc:
            if not any(source['text'] in block[4].strip() for block in doc[source['page']-1].get_text('blocks',sort=True)):
                return False
    return True

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['mock','live'],default='mock')
    parser.add_argument('--approve-paid-api',action='store_true')
    parser.add_argument('--max-total-api-calls',type=int,default=0)
    args=parser.parse_args()
    provider=None
    if args.mode=='live':
        if not args.approve_paid_api or args.max_total_api_calls<1:
            raise SystemExit('실제 API 평가는 --approve-paid-api 및 양수 --max-total-api-calls가 필요합니다.')
        if not settings.allow_external_ai or not settings.openai_api_key or settings.ai_provider!='openai':
            raise SystemExit('실제 API 키, AI_PROVIDER=openai, ALLOW_EXTERNAL_AI=true 설정이 필요합니다.')
        from backend.providers import OpenAIProvider
        class BudgetProvider:
            def __init__(self):self.client=OpenAIProvider();self.used=0
            def respond(self,messages,tools):
                if self.used>=args.max_total_api_calls:raise ValueError('평가 API 호출 상한에 도달했습니다.')
                self.used+=1
                return self.client.respond(messages,tools)
        provider=BudgetProvider()
    def execute(req):return Agent(req,provider).run() if provider else Agent(req).run()
    target=ROOT/'data'/'evaluation-runs'/uuid.uuid4().hex
    settings.data_dir=str(target);settings.ai_mode=args.mode;init_db()
    ids=[]
    for i in range(2):
        bid=register_pdf(fixture_pdf(i+1),f'assessment-{i+1}.pdf');index_book(bid);ids.append(bid)
    report=[]
    for i,(label,query,groups) in enumerate(CASES):
        for strategy in ['baseline','agent']:
            start=time.perf_counter()
            paid_calls_before=provider.used if provider else 0
            req=ChatRequest(book_id=ids[0],page=i+1,message=query,scope='all',strategy=strategy)
            run=execute(req)
            search_event=next((e for e in run['events'] if e['tool'] in ('search_textbook','search_across_books')),None)
            found=search_event['output'] if search_event and isinstance(search_event['output'],list) else []
            relevant=all(any(contains_group(s,g) for s in found) for g in groups)
            restoration=None;update=None;repeat=None;review=None;all_events=list(run['events']);calls=run['usage']['api_calls'];tokens=run['usage']['input_tokens']+run['usage']['output_tokens']
            if strategy=='agent' and run['quiz']:
                # New requests and fresh SQLite connections simulate resuming an
                # interrupted dialogue; browser/process restart is tested separately.
                follow=execute(ChatRequest(book_id=ids[0],page=i+1,message='이해가 안 돼요',scope='all',session_id=run['session_id']))
                restoration=bool(follow['quiz'] and follow['quiz']['id']==run['quiz']['id'] and one('SELECT state FROM sessions WHERE id=?',(run['session_id'],))['state']=='awaiting_answer')
                stored=json.loads(one('SELECT payload FROM quizzes WHERE id=?',(run['quiz']['id'],))['payload'])
                wrong=next((c for c in stored.get('choices',[]) if c!=stored['answer']),'not the expected answer')
                grade=execute(ChatRequest(book_id=ids[0],page=i+1,message='답안 제출',scope='all',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer=wrong))
                row=one('SELECT m.* FROM mastery m JOIN quizzes q ON q.concept_id=m.concept_id WHERE q.id=?',(run['quiz']['id'],))
                update=bool(grade['evaluation'] and row and row['total']==1 and row['status']=='복습 필요')
                review=any(e['tool']=='recommend_next_topic' and e['output'].get('action')=='review' for e in grade['events'] if isinstance(e['output'],dict))
                again=execute(ChatRequest(book_id=ids[0],page=i+1,message='답안 다시 제출',scope='all',session_id=run['session_id'],quiz_id=run['quiz']['id'],answer=wrong))
                repeat=one('SELECT count(*) AS n FROM attempts WHERE quiz_id=?',(run['quiz']['id'],))['n']==1
                all_events+=follow['events']+grade['events']+again['events']
                calls+=follow['usage']['api_calls']+grade['usage']['api_calls']+again['usage']['api_calls']
                tokens+=sum(x['usage']['input_tokens']+x['usage']['output_tokens'] for x in (follow,grade,again))
            if provider:calls=provider.used-paid_calls_before
            report.append({'case':label,'query':query,'strategy':strategy,'mode':args.mode,
                'status':run['status'],'retrieval_proxy_relevant':relevant,
                'source_metadata_correct':verify_sources(run['sources']),'source_count':len(run['sources']),
                'tool_calls':len(all_events),'tool_successes':sum(e['status']=='ok' for e in all_events),
                'tool_names':[e['tool'] for e in all_events],
                'quiz_created':bool(run['quiz']),'quiz_restored':restoration,'wrong_answer_mastery_updated':update,
                'review_recommended':review,'duplicate_attempt_prevented':repeat,
                'initial_elapsed_seconds':run['elapsed'],'workflow_elapsed_seconds':round(time.perf_counter()-start,3),'api_calls':calls,'tokens':tokens})
    data={'method':'Same 12 queries, 2 synthetic original local documents. Results measure tool/state mechanics and source matching, not AI response quality or learning impact.',
          'isolated_data_dir':str(target.relative_to(ROOT)), 'results':report}
    suffix='' if args.mode=='mock' else '-live'
    (ROOT/'docs'/f'agent-evaluation{suffix}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=[k for k in report[0] if k!='tool_names']
    with (ROOT/'docs'/f'agent-evaluation{suffix}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(report)
    for strategy in ('baseline','agent'):
        rows=[r for r in report if r['strategy']==strategy]
        print(strategy, 'queries=',len(rows),'relevant=',sum(r['retrieval_proxy_relevant'] for r in rows),
              'source_valid=',sum(r['source_metadata_correct'] for r in rows),'tools=',sum(r['tool_successes'] for r in rows),'/',sum(r['tool_calls'] for r in rows),
              'restored=',sum(r['quiz_restored'] is True for r in rows),'mastery=',sum(r['wrong_answer_mastery_updated'] is True for r in rows),
              'review=',sum(r['review_recommended'] is True for r in rows),'duplicates_prevented=',sum(r['duplicate_attempt_prevented'] is True for r in rows),
              'api_calls=',sum(r['api_calls'] for r in rows))

if __name__=='__main__':main()
