import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type {Source} from './api';
export function sourcePages(sources:Source[]):Source[]{
 const groups=new Map<string,Source[]>();
 for(const source of sources){const key=`${source.book_id}:${source.page}`;groups.set(key,[...(groups.get(key)||[]),source]);}
 return Array.from(groups.values(),group=>({...group[0],text:Array.from(new Set(group.map(s=>s.text))).join('\n\n'),warning:Array.from(new Set(group.map(s=>s.warning).filter(Boolean))).join(' ')||null}));
}
export function PageSources({sources,onSource}:{sources:Source[];onSource:(s:Source)=>void}){
 const pages=sourcePages(sources);
 if(!pages.length)return null;
 return <details className="sources"><summary>참고한 원문 {pages.length}페이지</summary>{pages.map(source=><button key={`${source.book_id}:${source.page}`} onClick={()=>onSource(source)}><span>{source.title}<small>PDF {source.page}p{source.printed_page?` · 인쇄 ${source.printed_page}`:''}</small><small className="source-excerpt">{source.text.slice(0,1200)}</small>{source.warning&&<small className="warning">{source.warning}</small>}</span><span aria-hidden="true">↗</span></button>)}</details>;
}
export function TranslationOriginal({text}:{text?:string}){
 if(!text)return null;
 return <><details className="translation-original" open={text.length<=1200}><summary>번역 원문 · 전체</summary><blockquote>{text}</blockquote></details><h4 className="translation-label">한국어 번역</h4></>;
}
export function mathMarkdown(text:string){
 // Preserve fenced/inline code while accepting the model's common LaTeX delimiters.
 return text.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part,i)=>{
  if(i%2)return part;
  const normalized=part.replace(/\\\[([\s\S]*?)\\\]/g,(_,math)=>`\n$$\n${math}\n$$\n`).replace(/\\\(([\s\S]*?)\\\)/g,(_,math)=>`$${math}$`);
  let display=false;
  return normalized.split('\n').map(line=>{
   const delimiters=line.match(/\$\$/g)?.length||0;
   if(delimiters){if(delimiters%2)display=!display;return line;}
   if(display||line.includes('$')||line.includes('`'))return line;
   // Small local models sometimes omit LaTeX delimiters. Preserve the actual
   // expression; only wrap a probability equality whose tail has no prose.
   const start=line.search(/[pP]\(/);
   if(start<0||!line.slice(start).includes('='))return line;
   const tail=line.slice(start);
   if(/[가-힣]/.test(tail)||/https?:|source-/i.test(tail)||/[A-Za-z]{3,}/.test(tail.replace(/\\[A-Za-z]+/g,''))){
    // Keep surrounding prose outside math. This bounded form covers the bare
    // ASCII probability equalities observed in actual Qwen answers; it does
    // not rewrite symbols, evaluate them, or parse arbitrary prose as LaTeX.
    return line.replace(/[pP]\([^()\n$]+\)\s*=\s*(?:[pP]\([^()\n$]+\)|\d+(?:\.\d+)?|[+\-*/=()[\],.\s])+/g,match=>{
     const expression=match.trimEnd().replace(/[,.]+$/,'');
     if(!/=(?:\s|[([])*(?:[pP]\(|\d)/.test(expression))return match;
     if([...expression].filter(c=>c==='(').length!==[...expression].filter(c=>c===')').length)return match;
     if([...expression].filter(c=>c==='[').length!==[...expression].filter(c=>c===']').length)return match;
     return '$'+expression+'$'+match.slice(expression.length);
    });
   }
   return line.slice(0,start)+'$'+tail+'$';
  }).join('\n');
 }).join('');
}
export function Answer({text,sources,onSource}:{text:string;sources:Source[];onSource:(s:Source)=>void}){
 // The page list below already provides this server-generated citation appendix.
 // Keep all original chunks for inline anchors in the actual answer body.
 const visible=sources.length?text.replace(/\n\n\*\*원문 출처\*\* · [^\n]+$/,''):text;
 return <Markdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={{a:({href,children})=>{
   if(href?.startsWith('#source-')){const source=sources.find(s=>s.id===href.slice(8));return source?<button className="inline-source" onClick={()=>onSource(source)}>{children}</button>:<span title="출처 검증 불가">[출처 확인 불가]</span>;}
   return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
 }}}>{mathMarkdown(visible)}</Markdown>;
}
