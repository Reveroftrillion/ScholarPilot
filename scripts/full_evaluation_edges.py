"""Additional real submissions, independent arithmetic, and local connection failure."""
import json
import sqlite3
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx


def main():
    client=httpx.Client(base_url='http://127.0.0.1:8022',timeout=180,trust_env=False)
    root=Path(client.get('/api/local-evaluation').json()['data_dir'])
    results=[json.loads(x) for x in (root/'full-results.jsonl').read_text(encoding='utf-8').splitlines()]
    output=root/'extra-results.jsonl'
    def save(row):
        with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    def ask(id,payload):
        start=time.monotonic();r=client.post('/api/chat',json=payload).json()
        save({'id':id,'kind':'edge','request':payload,'response':r,'elapsed':round(time.monotonic()-start,3)})
        print(id,r.get('status'),flush=True);return r
    with sqlite3.connect(root/'scholarpilot.db') as db:
        for row in results:
            quiz=row['response'].get('quiz')
            if not quiz:continue
            key=json.loads(db.execute('select payload from quizzes where id=?',(quiz['id'],)).fetchone()[0])
            payload={**row['request'],'session_id':row['response']['session_id'],'quiz_id':quiz['id'],'answer':key['answer'],'message':'정답 제출'}
            r=ask('grade-'+row['id'],payload)
            ask('duplicate-'+row['id'],{**payload,'answer':'다른 답안'})
            assert r.get('evaluation',{}).get('uncertain'), 'Unverified key must not be confident'
    bishop=next(r for r in results if 'Bishop' in r['source']['book'])['request']['book_id']
    for suffix,answer in [('correct','6.5'),('wrong','13')]:
        payload={'book_id':bishop,'page':137,'message':'숫자 예제','learning_mode':'deep','math_input':{'formula':'E_W(w) = (1/2) sum_j w_j^2','expression':'(2**2+3**2)/2','source_confirmed':True}}
        r=ask('verified-quiz-'+suffix,payload)
        if r.get('quiz'):
            ask('verified-grade-'+suffix,{**payload,'session_id':r['session_id'],'quiz_id':r['quiz']['id'],'message':'계산 답안 제출','answer':answer})
    # Genuine connection refusal to a closed loopback port, not a fake model.
    from backend.config import settings
    from backend.ollama_provider import OllamaProvider
    settings.ollama_base_url='http://127.0.0.1:11435'
    start=time.monotonic()
    try:OllamaProvider().respond([{'role':'user','content':'local connection diagnostic'}],[])
    except ValueError as exc:save({'id':'offline-connection','kind':'error','request':{'book_id':bishop,'page':137},'response':{'status':'expected_connection_error','text':str(exc)},'elapsed':time.monotonic()-start,'actual_generation':False})


if __name__=='__main__':main()
