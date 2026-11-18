"""Explicit OFFLINE browser QA server, never for regular startup.

Uses copied local data and a scripted model substitute. It tests the live
orchestrator and backend paths without claiming OpenAI quality or making calls.
"""
import json
import argparse
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.database import init_db

parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=['fixture','mock','bayes'],default='fixture')
parser.add_argument('--port',type=int,default=8001)
parser.add_argument('--resume',help='Existing directory created by this QA script')
args=parser.parse_args()
source_root=Path(settings.data_dir).resolve()
source_db=source_root/'scholarpilot.db'
qa_root=(ROOT/'data'/'browser-qa-runs').resolve()
target=Path(args.resume).resolve() if args.resume else qa_root/uuid.uuid4().hex
if not target.is_relative_to(qa_root):raise SystemExit('QA resume path must be inside data/browser-qa-runs')
if args.resume:
    if not (target/'.scholarpilot-qa').is_file() or not (target/'scholarpilot.db').is_file():
        raise SystemExit('Not a previously created ScholarPilot QA directory')
else:
    target.mkdir(parents=True,exist_ok=False)
    (target/'.scholarpilot-qa').write_text('isolated offline QA\n',encoding='utf-8')
settings.data_dir=str(target)
settings.ai_mode='live' if args.mode!='mock' else 'mock'
settings.allow_external_ai=False
settings.ai_provider='openai' # Explicit offline injection; never select the user's real local provider here.
init_db()
# Create a fresh isolated DB with only document data; do not copy, alter or
# delete the user's learning history. Read the source in a consistent snapshot.
if not args.resume:
    with sqlite3.connect(source_db.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(target/'scholarpilot.db') as copy:
        source.execute('BEGIN')
        for table in ('books','sections','chunks'):
            rows=source.execute(f'SELECT * FROM {table}').fetchall()
            if rows:copy.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in rows[0])})',rows)
        rows=source.execute('SELECT text,chunk_id,book_id FROM chunks_fts').fetchall()
        copy.executemany('INSERT INTO chunks_fts(text,chunk_id,book_id) VALUES(?,?,?)',rows)
pdfs=target/'pdfs';pdfs.mkdir(exist_ok=True)
if not args.resume:
    for file in (source_root/'pdfs').iterdir():
        if file.suffix in ('.pdf','.png'):shutil.copy2(file,pdfs/file.name)
from tests.conftest import pdf_bytes
upload_path=target/'browser-qa-upload.pdf'
if not args.resume:upload_path.write_bytes(pdf_bytes('QA additional textbook'))

class OfflineModel:
    def __init__(self):self.count=0
    def respond(self,messages,tools):
        self.count+=1
        inputs=[m for m in messages if isinstance(m,dict)]
        user=next(json.loads(m['content']) for m in reversed(inputs) if m.get('role')=='user' and m.get('content','').startswith('{') and 'book_id' in m['content'])
        if '[QA slow]' in user['message'] and self.count==1:time.sleep(1)
        if '[QA failure]' in user['message']:raise RuntimeError('offline fixture private diagnostic')
        page_data=next(json.loads(m['content'].split(': ',1)[1]) for m in inputs if m.get('content','').startswith('Current PDF page'))
        source=next((s for s in page_data if 'regression' in s['text'].lower()),page_data[0])
        logs=[m for m in inputs if m.get('type')=='function_call_output']
        completed={item.name for item in messages if getattr(item,'type',None)=='function_call'}
        calls=[];text=''
        if user.get('quiz_id'):
            if 'evaluate_answer' not in completed:calls=[('evaluate_answer',{'correct':False,'confidence':.99,'explanation':'[오프라인 모델 대역] 조건을 고정하는 개념을 복습하세요.','cause':'조건부확률 개념 혼동'})]
            elif 'find_prerequisites' not in completed:calls=[('find_prerequisites',{'concept':'Bayes theorem','candidates':['conditional probability']})]
            elif 'recommend_next_topic' not in completed:calls=[('recommend_next_topic',{})]
            else:text='[오프라인 모델 대역] 조건부확률을 복습한 후 다시 도전하세요.'
        elif ('문제' in user['message'] or '이해' in user['message']) and tools:
            if 'find_prerequisites' not in completed:calls=[('find_prerequisites',{'concept':'Bayes theorem','candidates':['conditional probability']})]
            elif 'explain_concept' not in completed:calls=[('explain_concept',{'text':'[오프라인 모델 대역] 조건부확률을 먼저 확인해 보세요.','source_ids':[source['id']]})]
            elif 'generate_quiz' not in completed:calls=[('generate_quiz',{'concept':'Conditional probability','kind':'choice','question':'[오프라인 모델 대역] 조건부확률은 어떤 확률인가요?','choices':['조건이 주어졌을 때','항상 1인 확률'],'answer':'조건이 주어졌을 때','explanation':'조건이 주어진 표본 공간에서 계산합니다.','source_ids':[source['id']]})]
        elif 'search_across_books' not in completed and user['scope']!='current':calls=[('search_across_books',{'query':'Quantization'})]
        elif 'search_textbook' not in completed:calls=[('search_textbook',{'query':'Bayes' if 'Bayes' in user['message'] else 'regression'})]
        if not calls and not text:
            text=f'## AI 설명 · 오프라인 모델 대역\n\n현재 PDF {user["page"]}페이지를 사용했습니다. 선택 원문: {user.get("selection") or "없음"}\n\n수식 \\(y=wx+b\\) 에서 $w$는 가중치입니다.\n\n[원문 PDF {source["page"]}p](#source-{source["id"]})\n\n이 응답은 브라우저 연결 검증용이며 실제 OpenAI 응답이 아닙니다.'
        output=[NS(type='function_call',name=n,arguments=json.dumps(a,ensure_ascii=False),call_id=f'fixture-{self.count}-{i}') for i,(n,a) in enumerate(calls)]
        return NS(output=output,output_text=text,usage=NS(input_tokens=0,output_tokens=0))

import backend.agent
if args.mode=='fixture':backend.agent.OpenAIProvider=OfflineModel
if args.mode=='bayes':
    from scripts.bayes_evaluation import BudgetedProvider,OfflineResponsesClient
    from backend.providers import OpenAIProvider as RealProvider
    backend.agent.OpenAIProvider=lambda:BudgetedProvider(RealProvider(OfflineResponsesClient()))
from backend.main import app
from backend.providers import readiness
from fastapi.routing import APIRoute

def qa_mode():return {'offline_provider_fixture':args.mode!='mock','provider_mode':args.mode,'external_api_calls':0,'upload_path':str(upload_path),'data_dir':str(target)}
app.router.routes.insert(0,APIRoute('/api/qa-mode',qa_mode,methods=['GET']))

if __name__=='__main__':
    import uvicorn
    print(f'Isolated browser QA: {target}',flush=True)
    for attempt in range(3):
        try:
            uvicorn.run(app,host='127.0.0.1',port=args.port)
            break
        except OSError as exc:
            if getattr(exc,'winerror',None)!=10014 or attempt==2:raise
            print('Windows socket initialization 10014; retrying QA server.',flush=True)
            time.sleep(.5)
