import {useEffect,useState} from 'react';
import {api,post,type MathInput,type MathReview,type Run} from './api';

export function LearningMode({value,onChange}:{value:string;onChange:(value:string)=>void}){
 return <select aria-label="학습 깊이" value={value} onChange={e=>onChange(e.target.value)}><option value="basic">기본 설명 · 1회 생성</option><option value="deep">심화 · 선수 개념·진단</option></select>;
}
export function TaskStatus({phase}:{phase:string}){
 const labels:Record<string,string>={searching:'원문 검색·페이지 확인 중',generating:'로컬 AI 설명·문제 생성 중',verifying:'수학·출처·학습 기록 확인 중',error:'예상하지 못한 오류',done:'완료'};
 return <p role="status" className="task-status">{labels[phase]||'작업 준비 중'} · CPU 생성은 시간이 걸릴 수 있습니다.</p>;
}
export function QuizTrust({verification}:{verification?:{status:string;measurement:string}}){
 if(!verification)return null;
 return <p className="quiz-trust">{verification.status==='unverified'?'정답 기준 미검증 · 자동 이해도 반영 없음':'서버가 확인한 제한적 문제 기준'}<br/>{verification.measurement}</p>;
}

type Preview={warning:string;image_url:string;candidates:{left_context:string;fraction_latex:string}[]};
export function MathInputPanel({bookId,page,onChange}:{bookId:string;page:number;onChange:(value:MathInput|undefined)=>void}){
 const [preview,setPreview]=useState<Preview>(),[formula,setFormula]=useState(''),[expression,setExpression]=useState(''),[comparison,setComparison]=useState(''),[bindings,setBindings]=useState('{}'),[confirmed,setConfirmed]=useState(false),[error,setError]=useState('');
 useEffect(()=>{setPreview(undefined);setFormula('');setExpression('');setComparison('');setBindings('{}');setConfirmed(false);setError('');onChange(undefined);},[bookId,page]);
 useEffect(()=>{try{
  const values=JSON.parse(bindings);if(!values||Array.isArray(values)||typeof values!=='object'||Object.values(values).some(v=>!['string','number'].includes(typeof v)))throw Error('변숫값 JSON을 확인하세요.');
  onChange(formula||expression?{formula,expression,comparison,bindings:Object.fromEntries(Object.entries(values).map(([k,v])=>[k,String(v)])),source_confirmed:confirmed}:undefined);setError('');
 }catch{onChange(undefined);setError('변숫값은 {"joint":"0.2","condition":"0.5"} 같은 JSON으로 입력하세요.');}},[formula,expression,comparison,bindings,confirmed]);
 async function load(){try{const p=await api<Preview>(`/books/${bookId}/pages/${page}/math-preview`);setPreview(p);if(p.candidates[0])setFormula(p.candidates[0].left_context+p.candidates[0].fraction_latex);}catch(e){setError((e as Error).message);}}
 return <details className="math-input-panel"><summary>수식 원본 확인 · 독립 검산</summary><p>PDF 추출 식은 미확인 후보입니다. 첨자·분모·적분 기호를 원본과 대조하세요.</p><button type="button" onClick={load}>수식 원본 불러오기</button>{preview&&<><p>{preview.warning}</p><img src={preview.image_url+(preview.candidates.length?'?region=0':'')} alt={`PDF ${page}페이지 실제 수식 원본 영역`} style={{maxWidth:'100%'}}/></>}
 <label>원문 대조·수정 수식<textarea aria-label="확인할 수식" value={formula} onChange={e=>{setFormula(e.target.value);setConfirmed(false);}}/></label>
 <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>원본과 대조했습니다 (사용자 확인이며 자동 수학 인증이 아닙니다)</label>
 <label>계산식<input aria-label="독립 계산식" placeholder="joint / condition" value={expression} onChange={e=>setExpression(e.target.value)}/></label>
 <label>변숫값 JSON<input aria-label="계산 변숫값" value={bindings} onChange={e=>setBindings(e.target.value)}/></label>
 <label>비교할 식 (선택)<input aria-label="비교할 식" value={comparison} onChange={e=>setComparison(e.target.value)}/></label>
 <small>사칙연산·정수 거듭제곱의 계산과 유리식 항등식만 지원합니다. 확률 해석·일반 유도는 미검증입니다.</small>{error&&<p role="alert">{error}</p>}</details>;
}

export function MathResult({review}:{review?:MathReview}){
 if(!review||review.status==='not_supplied'||(!review.expression&&!review.comparison&&review.exact===undefined&&review.status!=='failed'))return null;
 return <section className="math-result" aria-label="독립 수학 검증 결과"><strong>Python 독립 확인 · {review.status}</strong>{review.formula&&<p>사용자 입력 수식: {review.formula} · {review.source_confirmed?'사용자 원문 대조 확인':'원문 대조 미확인'}</p>}{review.bindings&&<p>입력값: {Object.entries(review.bindings).map(([k,v])=>`${k}=${v}`).join(', ')}</p>}{review.comparison&&<p>{review.expression} =? {review.comparison}</p>}{review.exact!==undefined&&<p>{review.expression} = {review.exact}</p>}{review.reason&&<p>{review.reason}</p>}{review.conditions?.map(c=><p key={c}>조건: {c}</p>)}<small>{review.scope}</small></section>;
}

export function ManualReviewPanel({evaluation}:{evaluation:NonNullable<Run['evaluation']>}){
 const [confirmed,setConfirmed]=useState(false),[correct,setCorrect]=useState('false'),[key,setKey]=useState(evaluation.answer),[status,setStatus]=useState('');
 useEffect(()=>{if(evaluation.attempt_id)api<{review:unknown}>(`/attempts/${evaluation.attempt_id}/review`).then(r=>{if(r.review)setStatus('사용자 원문 확인에 따른 자가 채점이 반영돼 있습니다.');}).catch(()=>{});},[evaluation.attempt_id]);
 if(!evaluation.uncertain||!evaluation.attempt_id)return null;
 async function submit(){try{await post(`/attempts/${evaluation.attempt_id}/review`,{correct:correct==='true',confirmed_key:key,confirm_key:confirmed,note:'사용자 원문 대조 후 자가 채점'});setStatus('자가 채점을 기록했습니다. 원래 AI 판정은 보존했습니다.');}catch(e){setStatus((e as Error).message);}}
 return <details><summary>원문 대조 후 수동 확인</summary><p>AI 정답 후보를 확정하지 않습니다. 원문과 직접 비교한 자가 채점만 별도 기록합니다.</p>{evaluation.model_advice&&<p>AI 의미 검토 제안 (미확정·이해도 미반영): {evaluation.model_advice.explanation}</p>}<input aria-label="수동 확인 정답" value={key} onChange={e=>{setKey(e.target.value);setConfirmed(false);}}/><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>원문과 정답을 직접 확인했습니다</label><select aria-label="자가 채점 결과" value={correct} onChange={e=>setCorrect(e.target.value)}><option value="false">오답으로 확인</option><option value="true">정답으로 확인</option></select><button type="button" disabled={!confirmed||!key.trim()} onClick={submit}>자가 채점 반영</button>{status&&<p role="status">{status}</p>}</details>;
}
