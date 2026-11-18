export type Book = {id:string;title:string;author:string;category:string;filename:string;pages:number;last_page:number;visited:number;status:string;progress:number;error:string|null};
export type Source = {id:string;book_id:string;title:string;page:number;printed_page:string|null;section:string;text:string;warning:string|null};
export type Quiz = {id:string;concept:string;kind:string;question:string;choices:string[]};
export type Run = {id:string;session_id:string;text:string;sources:Source[];quiz:Quiz|null;evaluation:{correct:boolean;uncertain:boolean;answer:string;explanation:string;cause:string;next_action:string;grading?:string;confidence?:number}|null;events:{tool:string;input:unknown;output:unknown;status:string}[];status:string;mode:string;provider?:string;usage:{api_calls:number;input_tokens:number;output_tokens:number};elapsed:number};
export async function api<T>(path:string, options:RequestInit = {}):Promise<T> {
  let response:Response;
  try {response = await fetch('/api'+path,{...options,headers:options.body instanceof FormData?options.headers:{'Content-Type':'application/json',...options.headers}});}
  catch {throw new Error('서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.');}
  if(!response.ok){ const data=await response.json().catch(()=>({detail:'서버에 연결할 수 없습니다.'})); throw new Error(typeof data.detail==='string'?data.detail:'입력값을 확인해 주세요.'); }
  return response.json();
}
export const post = <T,>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export function pageWithin(value:number,total:number){return Math.max(1,Math.min(total,Math.trunc(value)||1));}
