"""Prepare/check a pending quiz on a marked offline QA server only."""
import argparse
import json
import urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT

def request(path,payload=None):
    body=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
    req=urllib.request.Request('http://127.0.0.1:8002/api'+path,data=body,headers={'Content-Type':'application/json'},method='POST' if body else 'GET')
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','check']);args=parser.parse_args()
    qa=request('/qa-mode')
    target=Path(qa['data_dir']).resolve()
    if not qa['offline_provider_fixture'] or not target.is_relative_to((ROOT/'data'/'browser-qa-runs').resolve()) or not (target/'.scholarpilot-qa').is_file():
        raise SystemExit('격리된 오프라인 QA 서버가 아닙니다.')
    statefile=target/'restart-probe.json'
    if args.phase=='prepare':
        book=next(b for b in request('/books') if b['pages']==656)
        # Position writes use PUT, not POST.
        req=urllib.request.Request(f"http://127.0.0.1:8002/api/books/{book['id']}/position",data=b'{"page":131}',headers={'Content-Type':'application/json'},method='PUT')
        with urllib.request.urlopen(req,timeout=10) as response:json.load(response)
        run=request('/chat',{'book_id':book['id'],'page':131,'message':'진단 문제를 내 주세요','scope':'current'})
        if run['status']!='awaiting_answer' or not run['quiz']:raise RuntimeError('QA 문제 대기 상태 생성 실패')
        state={'data_dir':str(target),'book_id':book['id'],'page':131,'session_id':run['session_id'],'quiz_id':run['quiz']['id']}
        statefile.write_text(json.dumps(state),encoding='utf-8')
        print(json.dumps({'ready':True,'data_dir':str(target)}))
    else:
        state=json.loads(statefile.read_text(encoding='utf-8'))
        history=request('/books/'+state['book_id']+'/history')
        restored=any(r['response'] and r['response']['session_id']==state['session_id'] and r['response']['quiz'] and r['response']['quiz']['id']==state['quiz_id'] for r in history)
        page=next(b['last_page'] for b in request('/books') if b['id']==state['book_id'])
        result={'offline_only':True,'quiz_restored':bool(restored),'book_and_page_restored':page==state['page'],'page':page,'api_calls_to_external_services':0}
        (ROOT/'docs'/'restart-test.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        if not result['quiz_restored'] or not result['book_and_page_restored']:raise SystemExit(1)

if __name__=='__main__':main()
