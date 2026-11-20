import type {Run} from './api';

export function QualityNotice({quality}:{quality:Run['quality']}){
 if(!quality)return null;
 const mathFailed=quality.math_checks.some(check=>!!check&&typeof check==='object'&&'status' in check&&check.status==='fail');
 const hasAIWarning=!!quality.prose_status||quality.issues.length>0;
 if(!hasAIWarning&&!quality.math_checks.length)return null;
 return <div className={'quality-notice '+(mathFailed?'math-warning':'')}>
  {(mathFailed||hasAIWarning)&&<small role="status">{mathFailed?'수식 오류가 발견되었습니다. 원문과 검산 결과를 확인하세요.':'AI 응답 · 정확성 미검증, 원문과 대조하세요.'}</small>}
  {(quality.issues.length>0||quality.limits||quality.math_checks.length>0)&&<details className="quality-details"><summary>검증 상세</summary>{quality.issues.map((issue,i)=><p key={i}>{issue}</p>)}{quality.limits&&<p>{quality.limits}</p>}{quality.math_checks.length>0&&<pre>{JSON.stringify(quality.math_checks,null,2)}</pre>}</details>}
 </div>;
}

export function TracePanel({runs}:{runs:{request:string;run:Run}[]}){
 return <div className="trace-panel"><p>서버가 수행한 검색·저장과 모델이 생성한 행동을 구분합니다. 내부 추론은 표시하지 않습니다.</p>{runs.length===0&&<div className="empty-state">질문하면 도구 실행 로그가 표시됩니다.</div>}{[...runs].reverse().map(({request,run})=><section className="trace-run" key={run.id}><h3>{request}</h3><small>{run.status} · {run.elapsed}s · {run.provider==='ollama'?'로컬 모델 요청':'API'} {run.usage.api_calls}회 · {run.usage.input_tokens+run.usage.output_tokens} tokens</small>{run.events.map((event,i)=><details key={i}><summary><span>{i+1}</span>{event.tool}<b>{event.status}</b></summary><small>{event.actor==='server'?'서버 실행':event.actor==='model'?'모델 생성 행동':event.actor==='mock'?'Mock 규칙':'이전 기록 · 실행 주체 미기록'}{event.elapsed_ms!==undefined?` · ${event.elapsed_ms}ms`:''}</small><pre>{JSON.stringify({input:event.input,output:event.output},null,2)}</pre></details>)}</section>)}</div>;
}
