"""Replay diverse real-book requests against an isolated local validation server.

Raw PDF excerpts and model replies are written ONLY under ignored data/.
No semantic pass is inferred from valid JSON, source IDs, or model self-review.
"""
import argparse
import json
import statistics
import time
from pathlib import Path
import httpx
import pymupdf


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8022');parser.add_argument('--rerun',nargs='*');args=parser.parse_args()
    client=httpx.Client(base_url=args.base,timeout=240,trust_env=False)
    state=client.get('/api/local-evaluation').raise_for_status().json()
    assert state['mode']=='live' and state['provider']=='ollama' and state['external_paid_calls']==0
    root=Path(state['data_dir']);books=client.get('/api/books').json()
    books.sort(key=lambda b:0 if 'Bishop' in b['title'] else 1)
    pages=[[28,32,46,48,54,85,95,134,137,159,194,219,231,252,275,306,350,377,382,451,480,516,550,595],
           [84,104,138,164,197,232,251,267,315,375,411,442,498,535,544,554,614,647,703,730,762,1010,1288,1514]]
    manifest=[];docs={}
    for book,selected in zip(books,pages):
        doc=pymupdf.open(root/'pdfs'/f"{book['id']}.pdf");docs[book['id']]=doc
        for n in selected:
            section=[r[1] for r in doc.get_toc() if r[2]<=n][-1]
            blocks=[b[4].strip() for b in doc[n-1].get_text('blocks',sort=True) if len(b[4].strip())>160]
            paragraph=next((b for b in blocks if len(b)>250 and sum(c.isalpha() for c in b)/len(b)>.65),blocks[0] if blocks else doc[n-1].get_text())
            manifest.append({'book_id':book['id'],'book':book['title'],'page':n,'printed':doc[n-1].get_label(),'section':section,'selection':paragraph[:1400], 'text':doc[n-1].get_text()})
    (root/'full-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    plan=[]
    def add(kind,m,message,**extra):
        plan.append({'id':f'{kind}-{sum(x["kind"]==kind for x in plan)+1:02}','kind':kind,'source':m,'payload':{'book_id':m['book_id'],'page':m['page'],'message':message,'scope':'current','task':'auto','learning_mode':'basic',**extra}})
    # Interleave both books rather than letting an early failure hide one book.
    mixed=[m for pair in zip(manifest[:24],manifest[24:]) for m in pair]
    prompts=['쉽게 설명해 줘','핵심이 뭐야?','왜 이렇게 되는 거야?','예제를 들어 설명해 줘','처음 배우는 사람도 이해하게 설명해 줘']
    for i,m in enumerate(mixed[:20]):add('explain',m,prompts[i%5],selection=m['selection'])
    for i,m in enumerate(mixed[20:35]):
        message=[f'PDF {m["page"]}페이지 설명해 줘',f'인쇄 {m["printed"]}페이지 내용 설명해 줘','현재 페이지의 핵심이 뭐야?','다음 페이지 내용을 요약해 줘','이전 페이지와 지금 페이지의 차이는?'][i%5]
        add('page',m,message)
    for i,m in enumerate(mixed[35:40]):
        for j,msg in enumerate(['이 페이지 설명해 줘','조금 더 자세히','숫자 예제도 보여줘']):add('follow',m,msg,chain=f'follow-{i}',step=j)
    for m in mixed[8:23]:add('math',m,'이 페이지의 수식을 기호와 가정, 계산 예제와 함께 자세히 설명해 줘')
    for i,m in enumerate(mixed[::5][:10]):
        add('search',m,['Bayes theorem','quantization PTQ QAT','memory bandwidth','attention','이 책에 없는 유니콘 연금술의 정리를 설명해 줘'][i%5],scope='all' if i%2 else 'current')
    # Actual captions, not body references, determine figure/table pages.
    visual=[]
    for m in mixed:
        if any(__import__('re').match(r'^(Figure|Fig\.|Table)\s*\d',b[4].strip()) for b in docs[m['book_id']][m['page']-1].get_text('blocks')):visual.append(m)
    for i,m in enumerate(visual[:10]):add('visual',m,['이 그림 설명해 줘','이 표를 해석해 줘','그래프의 x축과 y축을 설명해 줘'][i%3])
    for i,m in enumerate(mixed[::5][:10]):add('quiz',m,['이 문단으로 객관식 진단 문제를 내 줘','이 문단으로 단답형 퀴즈를 내 줘','이 문단의 수치 계산 문제를 내 줘'][i%3],selection=m['selection'],learning_mode='deep')
    for i,msg in enumerate(['PDF 99999페이지 설명해 줘','이 문장을 번역해 줘','PDF 0페이지 설명해 줘','인쇄 99999쪽 설명해 줘','현재 페이지 설명해 줘']):
        add('error',mixed[i],msg,selection='This selected text does not exist in this textbook.' if i==4 else '')
    for m in mixed[40:]:add('coverage',m,'이 문단의 핵심 개념과 앞뒤 논리 관계를 쉽게 설명해 줘',selection=m['selection'])
    for m in mixed:
        if ('Bishop' in m['book'] and m['page'] in [231,252,306,350,377,382]) or ('Bishop' not in m['book'] and m['page'] in [535,544]):
            assert '=' in m['text']
            add('formula',m,f'PDF {m["page"]}페이지에 실제로 있는 수식의 정의, 기호, 가정을 자세히 설명해 줘')
    (root/'full-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    output=root/('full-rerun.jsonl' if args.rerun else 'full-results.jsonl')
    done={json.loads(line)['id'] for line in output.read_text(encoding='utf-8').splitlines()} if output.exists() else set()
    sessions={}
    prior=Path(root/'full-results.jsonl')
    if prior.exists():
        chains={item['id']:item['payload'].get('chain') for item in plan}
        for line in prior.read_text(encoding='utf-8').splitlines():
            saved=json.loads(line);chain=chains.get(saved['id'])
            if chain and saved['response'].get('session_id'):sessions[chain]=saved['response']['session_id']
    for item in plan:
        if item['id'] in done or args.rerun and item['id'] not in args.rerun:continue
        payload=dict(item['payload']);chain=payload.pop('chain',None);payload.pop('step',None)
        if chain and chain in sessions:payload['session_id']=sessions[chain]
        before=client.get('/api/local-evaluation').json()['model_calls'];start=time.monotonic()
        response=None
        try:
            response=client.post('/api/chat',json=payload);result=response.json()
        except (httpx.HTTPError,ValueError) as exc:result={'status':'transport_error','error':type(exc).__name__}
        if chain and result.get('session_id'):sessions[chain]=result['session_id']
        checks={'transport_ok':response is not None and response.status_code==200,'semantic_accuracy':'unverified','source_exists':True,'source_content_relevance':'unverified'}
        for source in result.get('sources',[]):
            doc=docs.get(source['book_id']);checks['source_exists'] &= bool(doc and 1<=source['page']<=len(doc))
        if payload['message'].startswith('PDF ') and payload['page']<10000:checks['requested_page_used']=result.get('reading_context',{}).get('page')==int(payload['message'].split()[1].split('페이지')[0])
        row={'id':item['id'],'kind':item['kind'],'model':state['model'],'source':item['source'],'request':payload,'response':result,'elapsed':round(time.monotonic()-start,3),'model_calls':client.get('/api/local-evaluation').json()['model_calls']-before,'checks':checks}
        with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({k:row[k] for k in ['id','elapsed','model_calls']}),result.get('status'),flush=True)
    print('RESULTS',output,flush=True)


if __name__=='__main__':main()
