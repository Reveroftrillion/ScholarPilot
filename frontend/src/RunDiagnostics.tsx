import type {Run} from './api';

export function QualityNotice({quality}:{quality:Run['quality']}){
 if(!quality)return null;
 return quality.issues.length?<div className="ai-unavailable quality-notice" role="status"><strong>검토가 필요한 AI 설명입니다.</strong>{quality.issues.map((issue,i)=><span key={i}>{issue}</span>)}<small>{quality.limits}</small></div>:<small className="muted quality-notice">{quality.prose_status?'AI 개념 설명 · 의미 정확성 미검증 · 교과서 원문과 대조하세요.':'일부 자동 검사 통과 · 설명 전체의 정확성을 보증하지 않습니다.'}</small>;
}

export function TracePanel({runs}:{runs:{request:string;run:Run}[]}){
 return <div className="trace-panel"><p>서버가 수행한 검색·저장과 모델이 생성한 행동을 구분합니다. 내부 추론은 표시하지 않습니다.</p>{runs.length===0&&<div className="empty-state">질문하면 도구 실행 로그가 표시됩니다.</div>}{[...runs].reverse().map(({request,run})=><section className="trace-run" key={run.id}><h3>{request}</h3><small>{run.status} · {run.elapsed}s · {run.provider==='ollama'?'로컬 모델 요청':'API'} {run.usage.api_calls}회 · {run.usage.input_tokens+run.usage.output_tokens} tokens</small>{run.events.map((event,i)=><details key={i}><summary><span>{i+1}</span>{event.tool}<b>{event.status}</b></summary><small>{event.actor==='server'?'서버 실행':event.actor==='model'?'모델 생성 행동':event.actor==='mock'?'Mock 규칙':'이전 기록 · 실행 주체 미기록'}{event.elapsed_ms!==undefined?` · ${event.elapsed_ms}ms`:''}</small><pre>{JSON.stringify({input:event.input,output:event.output},null,2)}</pre></details>)}</section>)}</div>;
}
