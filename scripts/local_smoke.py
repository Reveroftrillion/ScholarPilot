"""One short real local inference, with timings and no external AI client."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx,psutil
from backend.config import ROOT,settings
from backend.ollama_provider import local_url,local_model

start=time.monotonic()
with httpx.Client(timeout=300,trust_env=False) as client:
    response=client.post(local_url()+'/api/chat',json={'model':local_model(),'stream':False,'think':False,
        'messages':[{'role':'user','content':'베이즈 정리가 무엇인지 한국어로 두 문장으로 설명해 주세요.'}],
        'options':{'num_predict':128,'num_ctx':4096,'num_thread':6}}).raise_for_status().json()
    loaded=client.get(local_url()+'/api/ps').json()
report={'model':settings.ollama_model,'response':response['message']['content'],'elapsed_seconds':round(time.monotonic()-start,3),
    'load_seconds':response.get('load_duration',0)/1e9,'prompt_tokens':response.get('prompt_eval_count'),
    'generated_tokens':response.get('eval_count'),'generation_seconds':response.get('eval_duration',0)/1e9,
    'loaded_models':loaded,'available_ram_bytes':psutil.virtual_memory().available}
(ROOT/'docs/local-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
