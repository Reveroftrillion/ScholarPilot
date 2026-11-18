"""Explicitly approved three-scenario live QA. One persistent budget for ALL routes."""
import argparse
import json
import sys
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT,settings
from backend.providers import OpenAIProvider
from scripts.bayes_evaluation import MODEL,BudgetedProvider,prepare_isolated

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--approve-paid-api',action='store_true')
    p.add_argument('--resume',type=Path)
    p.add_argument('--port',type=int,default=8020)
    a=p.parse_args()
    if not a.approve_paid_api:raise SystemExit('Explicit paid-call approval required')
    if settings.openai_model!=MODEL:raise SystemExit('Configured model has no approved pricing here; no model was changed')
    if not settings.openai_api_key or not settings.allow_external_ai:raise SystemExit('Missing .env key or external AI permission')
    if a.resume:
        target=a.resume.resolve()
        if not target.is_relative_to((ROOT/'data/bayes-evaluation-runs').resolve()) or not (target/'.live-validation').is_file():
            raise SystemExit('Resume requires a marked live evaluation directory')
        settings.data_dir=str(target)
    else:
        _,target=prepare_isolated(include_all=True)
        (target/'.live-validation').write_text('approved: three scenarios, 24 requests, USD 1.00 local estimate\n',encoding='utf-8')
    settings.ai_mode='live'
    provider=BudgetedProvider(OpenAIProvider())
    provider.trace_path=target/'model-calls.json'
    if provider.trace_path.exists():
        provider.records=json.loads(provider.trace_path.read_text(encoding='utf-8'))
        provider.reserved=sum(r['reserved_usd'] for r in provider.records)
    lock=threading.Lock()
    class Shared:
        def respond(self,messages,tools):
            with lock:return provider.respond(messages,tools)
    import backend.agent
    import backend.main
    backend.agent.OpenAIProvider=lambda:Shared()
    backend.main.OpenAIProvider=lambda:Shared()
    def state():
        return {'mode':'live','transport':'real_openai','model':settings.openai_model,
            'requests':len(provider.records),'max_requests':24,'reserved_usd':provider.reserved,
            'budget_usd':1.,'data_dir':str(target),'successful_requests':sum(r['status']=='completed' for r in provider.records),
            'errors':[{k:r.get(k) for k in ('error_type','http_status','error_code')} for r in provider.records if r['status']=='error']}
    from fastapi.routing import APIRoute
    backend.main.app.router.routes.insert(0,APIRoute('/api/live-evaluation',state,methods=['GET']))
    import uvicorn
    print(json.dumps(state(),ensure_ascii=True),flush=True)
    uvicorn.run(backend.main.app,host='127.0.0.1',port=a.port)

if __name__=='__main__':main()
