"""Actual local Ollama QA on isolated copies of registered books; no paid provider."""
import argparse
import json
import re
import sys
import threading
import time
import psutil
import httpx
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.ollama_provider import OllamaProvider
from scripts.bayes_evaluation import prepare_isolated,safe_copy

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8021);p.add_argument('--resume',type=Path);a=p.parse_args()
    settings.ai_provider='ollama';settings.ai_mode='live';settings.allow_external_ai=False
    if a.resume:
        target=a.resume.resolve()
        if not target.is_relative_to((ROOT/'data/local-evaluation-runs').resolve()) or not (target/'.local-evaluation').is_file():raise SystemExit('Invalid local QA directory')
        settings.data_dir=str(target)
    else:
        _,target=prepare_isolated(include_all=True,category='local-evaluation-runs')
        (target/'.local-evaluation').write_text('actual local model; no user history copied\n',encoding='utf-8')
    class CaptureHTTP:
        final=None
        def post(self,url,*,json):
            with httpx.Client(timeout=settings.ollama_timeout,trust_env=False,follow_redirects=False) as client:
                response=client.post(url,json=json)
            try:
                body=response.json();message=body.get('message',{})
                # Store final wire content for rejected JSON too, never thinking.
                content=message.get('content','')
                if '<think>' in content:
                    content=re.sub(r'<think>.*?</think>','',content,flags=re.S) if '</think>' in content else ''
                self.final={'content':content,'tool_calls':message.get('tool_calls',[]),'done_reason':body.get('done_reason')}
            except (ValueError,AttributeError,TypeError):self.final={'http_status':response.status_code}
            return response
    transport=CaptureHTTP()
    delegate=OllamaProvider(client=transport);ledger=target/'local-model-calls.json'
    records=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else []
    lock=threading.Lock()
    def save():
        temporary=ledger.with_suffix('.tmp')
        temporary.write_text(json.dumps(safe_copy(records),ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(ledger)
    def memory():
        names={'ollama.exe','llama-server.exe','ollama','llama-server'}
        processes=[]
        for process in psutil.process_iter(['pid','name','memory_info']):
            try:
                if (process.info['name'] or '').casefold() in names:processes.append({'pid':process.pid,'name':process.info['name'],'rss_bytes':process.info['memory_info'].rss})
            except (psutil.Error,AttributeError):pass
        return {'available_bytes':psutil.virtual_memory().available,'processes':processes}
    class Recorded:
        local=True
        compact_workflow=True
        reliable_workflow=True
        @property
        def last_usage(self):return getattr(delegate,'last_usage',None)
        def respond(self,messages,tools):
            with lock:
                start=time.monotonic();before=len(delegate.metrics)
                transport.final=None
                record={'model':settings.ollama_model,'status':'started','input':safe_copy(messages),'memory_before':memory()};records.append(record);save()
                try:
                    response=delegate.respond(messages,tools)
                    record.update(status='completed',response=response.output_text,tools=[o.name for o in response.output],metrics=delegate.metrics[-1])
                    return response
                except Exception as e:
                    record.update(status='error',error=str(e) if isinstance(e,ValueError) else 'local inference failed')
                    raise
                finally:
                    record['elapsed']=round(time.monotonic()-start,3)
                    if transport.final is not None:record['final_wire_response']=transport.final
                    if len(delegate.metrics)>before:record['metrics']=delegate.metrics[-1]
                    record['memory_after']=memory()
                    try:
                        with httpx.Client(timeout=2,trust_env=False) as client:
                            loaded=client.get(delegate.base+'/api/ps').raise_for_status().json()
                        record['loaded_models']=[{k:m.get(k) for k in ('name','size','size_vram','context_length')} for m in loaded.get('models',[])]
                    except (httpx.HTTPError,ValueError):record['loaded_models']=None
                    save()
    import backend.agent
    backend.agent.OllamaProvider=lambda:Recorded()
    from backend.main import app
    def state():return {'provider':'ollama','mode':'live','model':settings.ollama_model,'external_paid_calls':0,'data_dir':str(target),'model_calls':len(records)}
    from fastapi.routing import APIRoute
    app.router.routes.insert(0,APIRoute('/api/local-evaluation',state,methods=['GET']))
    import uvicorn
    print(json.dumps(state()),flush=True)
    uvicorn.run(app,host='127.0.0.1',port=a.port)

if __name__=='__main__':main()
