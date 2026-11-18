import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type {Source} from './api';
export function mathMarkdown(text:string){
 // Preserve fenced/inline code while accepting the model's common LaTeX delimiters.
 return text.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part,i)=>i%2?part:part.replace(/\\\[([\s\S]*?)\\\]/g,(_,math)=>`\n$$\n${math}\n$$\n`).replace(/\\\(([\s\S]*?)\\\)/g,(_,math)=>`$${math}$`)).join('');
}
export function Answer({text,sources,onSource}:{text:string;sources:Source[];onSource:(s:Source)=>void}){
 return <Markdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={{a:({href,children})=>{
   if(href?.startsWith('#source-')){const source=sources.find(s=>s.id===href.slice(8));return source?<button className="inline-source" onClick={()=>onSource(source)}>{children}</button>:<span title="출처 검증 불가">[출처 확인 불가]</span>;}
   return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
 }}}>{mathMarkdown(text)}</Markdown>;
}
