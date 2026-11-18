"""Actual local Ollama QA on isolated copies of registered books; no paid provider."""
import argparse
import json
import sys
import threading
import time
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
    delegate=OllamaProvider();ledger=target/'local-model-calls.json'
    records=json.loads(ledger.read_text(encoding='utf-8')) if ledger.exists() else []
    lock=threading.Lock()
    class Recorded:
        local=True
        def respond(self,messages,tools):
            with lock:
                start=time.monotonic();record={'model':settings.ollama_model,'status':'started','input':safe_copy(messages)};records.append(record)
                try:
                    response=delegate.respond(messages,tools)
                    record.update(status='completed',response=response.output_text,tools=[o.name for o in response.output],metrics=delegate.metrics[-1])
                    return response
                except Exception as e:
                    record.update(status='error',error=str(e) if isinstance(e,ValueError) else 'local inference failed')
                    raise
                finally:
                    record['elapsed']=round(time.monotonic()-start,3)
                    ledger.write_text(json.dumps(safe_copy(records),ensure_ascii=False,indent=2),encoding='utf-8')
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
