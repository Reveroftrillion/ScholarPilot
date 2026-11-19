"""Finite real-local A/B/C checks; no retries, no paid provider, isolated data."""
import argparse,json,time
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8021');a=parser.parse_args()
    with httpx.Client(base_url=a.base,timeout=15,trust_env=False) as client:
        state=client.get('/api/local-evaluation').raise_for_status().json()
        if state.get('provider')!='ollama' or state.get('external_paid_calls')!=0:raise SystemExit('Only isolated local Ollama QA is allowed')
        root=Path(__file__).resolve().parents[1];directory=Path(state['data_dir']).resolve()
        if not directory.is_relative_to(root/'data/local-evaluation-runs') or not (directory/'.local-evaluation').is_file():raise SystemExit('Not an isolated evaluation directory')
        books=client.get('/api/books').raise_for_status().json();book=next(b for b in books if 'Bishop' in b['title'])
        results={}
        def execute(name,request):
            job=client.post('/api/chat/jobs',json=request).raise_for_status().json();phases=[];start=time.monotonic()
            while time.monotonic()-start<900:
                current=client.get('/api/chat/jobs/'+job['id']).raise_for_status().json()
                if not phases or phases[-1]!=current['phase']:phases.append(current['phase'])
                if current['status']=='error':raise RuntimeError(current['error'])
                if current['status']=='done':break
                time.sleep(.3)
            else:raise RuntimeError('QA wait timed out. No request was retried.')
            result=current['result'];results[name]=result
            (directory/f'scenario-{name}.json').write_text(json.dumps({'request':request,'run':result,'observed_phases':phases},ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'scenario':name,'status':result['status'],'elapsed':result['elapsed'],'usage':result['usage'],'phases':phases,
                              'math_status':result.get('math_review',{}).get('status'),'quiz_verified':(result.get('quiz') or {}).get('verification')},ensure_ascii=True),flush=True)
            return result
        # Evaluator checked Bishop PDF 48's product rule and the actual fraction
        # image. These numeric values are labelled practice values, not a book quote.
        math_input={'formula':'p(Y|X)=p(X|Y)p(Y)/p(X)','source_confirmed':True,'expression':'joint/condition',
                    'bindings':{'joint':'0.2','condition':'0.5'}}
        base={'book_id':book['id'],'page':48,'scope':'current','learning_mode':'basic'}
        initial=execute('A',{**base,'message':'이 페이지 베이즈 정리를 처음 배우는 사람에게 한국어로 쉽게 설명하고 숫자 예제를 확인해 줘.','math_input':math_input})
        diagnosis=execute('B',{**base,'session_id':initial['session_id'],'learning_mode':'deep',
            'message':'조건부확률이 어렵습니다. 선수 개념을 검색하고 확인한 식의 계산 진단 문제를 내 주세요.',
            'math_input':{**math_input,'bindings':{'joint':'0.12','condition':'0.4'}}})
        if diagnosis.get('quiz'):
            execute('grade',{**base,'session_id':diagnosis['session_id'],'message':'내 답안을 확인하고 복습을 추천해 줘.',
                  'quiz_id':diagnosis['quiz']['id'],'answer':'1'})
        execute('C',{**base,'scope':'all','message':'Quantization에서 PTQ와 QAT의 차이를 한국어로 설명해 줘. 두 교과서를 검색하되 실제 근거가 있는 책만 활용해 줘.'})
        after=client.get('/api/local-evaluation').raise_for_status().json()
        ledger=json.loads((directory/'local-model-calls.json').read_text(encoding='utf-8'));metrics=[c.get('metrics',{}) for c in ledger]
        report={'local_requests':after['model_calls']-state['model_calls'],'paid_requests':0,
                'input_tokens':sum(m.get('prompt_tokens',0) for m in metrics),'output_tokens':sum(m.get('generated_tokens',0) for m in metrics),
                'stages':{name:{k:r[k] for k in ('status','elapsed','usage')} for name,r in results.items()},
                'quality_note':'Actual AI prose still requires human source/meaning review. Server arithmetic does not certify conceptual understanding.'}
        (directory/'reliable-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
