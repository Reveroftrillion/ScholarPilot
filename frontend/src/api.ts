export type Book = {id:string;title:string;author:string;category:string;filename:string;pages:number;last_page:number;visited:number;status:string;progress:number;error:string|null};
export type Source = {id:string;book_id:string;title:string;page:number;printed_page:string|null;section:string;text:string;warning:string|null};
export type Quiz = {id:string;concept:string;kind:string;question:string;choices:string[];verification?:{status:string;measurement:string}};
export type MathInput={formula:string;source_confirmed:boolean;expression:string;comparison:string;bindings:Record<string,string>};
export type MathReview={comparison?:string;equivalent?:boolean;bindings?:Record<string,string>;status:string;formula?:string;source_confirmed?:boolean;expression?:string;exact?:string;value?:number;reason?:string;scope:string;conditions?:string[]};
export type Run = {math_review?:MathReview;draft?:string;id:string;session_id:string;text:string;sources:Source[];quiz:Quiz|null;evaluation:{model_advice?:{correct?:boolean;confidence?:number;explanation?:string};attempt_id?:string;key_verified?:boolean;correct:boolean;uncertain:boolean;answer:string;explanation:string;cause:string;next_action:string;grading?:string;confidence?:number}|null;events:{tool:string;input:unknown;output:unknown;status:string;actor?:string;elapsed_ms?:number}[];status:string;mode:string;provider?:string;quality?:{prose_status?:string;status:string;issues:string[];limits:string;math_checks:unknown[]};usage:{api_calls:number;input_tokens:number;output_tokens:number};elapsed:number};
export async function api<T>(path:string, options:RequestInit = {}):Promise<T> {
  let response:Response;
  try {response = await fetch('/api'+path,{...options,headers:options.body instanceof FormData?options.headers:{'Content-Type':'application/json',...options.headers}});}
  catch {throw new Error('서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.');}
  if(!response.ok){ const data=await response.json().catch(()=>({detail:'서버에 연결할 수 없습니다.'})); throw new Error(typeof data.detail==='string'?data.detail:'입력값을 확인해 주세요.'); }
  return response.json();
}
export const post = <T,>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export async function localChat(body:unknown,onPhase:(phase:string)=>void):Promise<Run>{
 const job=await post<{id:string}>('/chat/jobs',body);
 for(;;){
  const status=await api<{status:string;phase:string;error?:string;result?:Run}>(`/chat/jobs/${job.id}`);
  onPhase(status.phase);
  if(status.status==='done')return status.result!;
  if(status.status==='error')throw Error(status.error||'학습 작업이 실패했습니다.');
  await new Promise(resolve=>setTimeout(resolve,500));
 }
}
export function pageWithin(value:number,total:number){return Math.max(1,Math.min(total,Math.trunc(value)||1));}
