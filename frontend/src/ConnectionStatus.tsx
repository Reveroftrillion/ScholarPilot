import {useEffect,useState} from 'react';
import {api,post} from './api';
export type Readiness={ready:boolean;reasons:string[];network_checked:boolean;message:string;connected?:boolean;api_calls?:number};
export function ConnectionStatus(){
 const [health,setHealth]=useState<{restart_required:boolean;running_revision:string;frontend:{rebuild_required:boolean}}|null>(null);
 const [online,setOnline]=useState(true);
 useEffect(()=>{let alive=true;const check=()=>api<typeof health>('/health').then(h=>{if(alive){setHealth(h);setOnline(true);}}).catch(()=>{if(alive)setOnline(false);});check();const id=setInterval(check,10000);return()=>{alive=false;clearInterval(id);};},[]);
 return <span className="connection-status" role="status">{!online?'백엔드 연결 끊김':health?.restart_required?'서버 재시작 필요':health?.frontend.rebuild_required?'화면 재빌드 필요':health?'화면·서버 연결 정상':'서버 확인 중'}{health&&<small> · {health.running_revision.slice(0,7)}</small>}</span>;
}
export function AICheck({local=false,allowPaid=false,onChecked}:{local?:boolean;allowPaid?:boolean;onChecked?:(status:Readiness)=>void}){
 const [result,setResult]=useState<Readiness|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function check(paid:boolean){if(paid&&(local||!allowPaid))return;if(paid&&!confirm('설정된 OpenAI 모델을 1회 호출합니다. API 비용이 발생할 수 있습니다. 연결 테스트를 실행할까요?'))return;setBusy(true);setError('');try{const status=await post<Readiness>('/ai/check',{approve_paid_call:paid});setResult(status);onChecked?.(status);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="ai-check"><button className="primary" disabled={busy} onClick={()=>check(false)}>{local?'Ollama 연결 확인 · 무료':'설정 상태 확인 · 무료'}</button>{!local&&allowPaid&&<button disabled={busy} onClick={()=>check(true)}>실제 API 연결 테스트 · 유료 호출 승인</button>}{local&&<small>모델 설치와 연결만 확인하며 AI 설명을 생성하지 않습니다.</small>}{error&&<p role="alert">{error}</p>}{result&&<div role="status"><p>{result.message}</p>{result.reasons.map(r=><p key={r}>{r}</p>)}<small>{local?'외부 유료 호출 없음':`실제 호출 ${result.api_calls||0}회`} {result.connected?'· 연결 성공':''}</small></div>}</div>;
}
