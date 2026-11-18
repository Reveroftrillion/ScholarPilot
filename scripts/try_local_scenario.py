"""Run one requested scenario against the marked REAL local evaluation server."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx

p=argparse.ArgumentParser();p.add_argument('scenario',choices=['A','B','grade','C','D']);p.add_argument('--base',default='http://127.0.0.1:8021');a=p.parse_args()
with httpx.Client(base_url=a.base,timeout=900,trust_env=False) as c:
    state=c.get('/api/local-evaluation').raise_for_status().json()
    if state.get('provider')!='ollama' or state.get('external_paid_calls')!=0:raise SystemExit('Not a local-only evaluation server')
    directory=Path(state['data_dir']);books=c.get('/api/books').json();book=next(b for b in books if 'Bishop' in b['title'])
    req={'book_id':book['id'],'page':48,'message':'이 페이지의 베이즈 정리를 한국어로 쉽게 설명하고, 곱의 법칙을 이용한 수식 유도와 숫자 예제를 보여줘.','scope':'current'}
    if a.scenario in ('B','grade','D'):
        initial=json.loads((directory/'scenario-A.json').read_text(encoding='utf-8'))['run'];req['session_id']=initial['session_id']
    if a.scenario=='B':req['message']='아직 조건부확률이 이해가 안 돼. 선수 개념을 검색하고 설명한 다음, 내가 부족한 부분을 확인할 단답형 문제를 하나 내고 답안을 기다려 줘.'
    if a.scenario=='grade':
        diagnosis=json.loads((directory/'scenario-B.json').read_text(encoding='utf-8'))['run'];quiz=diagnosis['quiz']
        req.update(message='내 답안을 채점하고 오답 원인을 설명한 다음 복습을 추천해 줘.',quiz_id=quiz['id'],answer='조건부확률은 조건과 상관없이 언제나 1입니다.')
    if a.scenario=='C':req.update(message='Quantization에서 PTQ와 QAT의 차이를 한국어로 설명하고 두 교과서에서 관련 원문을 찾아 구분해 줘. 근거 없는 책의 내용은 만들지 마.',scope='all')
    if a.scenario=='D':req['message']='앞서 설명한 예제에서 사전확률과 사후확률의 차이를 한 번 더 쉽게 설명해 줘.'
    response=c.post('/api/chat',json=req);response.raise_for_status();run=response.json()
    (directory/f'scenario-{a.scenario}.json').write_text(json.dumps({'request':req,'run':run},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'scenario':a.scenario,'status':run['status'],'tools':[(e['tool'],e['status']) for e in run['events']],'usage':run['usage'],'elapsed':run['elapsed'],'quiz':run['quiz'],'evaluation':run['evaluation']},ensure_ascii=True))
    print(run['text'])
