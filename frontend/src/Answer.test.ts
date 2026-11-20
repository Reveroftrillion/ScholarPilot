import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {mathMarkdown,sourcePages,Answer,TranslationOriginal} from './Answer';
import type {Source} from './api';
it('normalizes LaTeX delimiters and preserves code',()=>{
 expect(mathMarkdown('기호 \\(x\\) 유도 \\[y=x+1\\]')).toBe('기호 $x$ 유도 \n$$\ny=x+1\n$$\n');
 expect(mathMarkdown('`\\(code\\)`')).toBe('`\\(code\\)`');
});

it('groups chunks by book and page while preserving inline anchors and the full translation original',()=>{
 const first={id:'a',book_id:'bishop',page:48,title:'Bishop',printed_page:'28',section:'Probability',text:'First paragraph',warning:null} satisfies Source;
 const sources=[first,{...first,id:'b',text:'Second paragraph'},{...first,id:'c',book_id:'systems',title:'Systems'}];
 expect(sourcePages(sources)).toHaveLength(2);
 expect(sourcePages(sources)[0].text).toContain('Second paragraph');
 const answer=renderToStaticMarkup(createElement(Answer,{text:'See [second paragraph](#source-b)',sources,onSource:()=>{}}));
 expect(answer).toContain('inline-source');expect(answer).not.toContain('출처 확인 불가');
 const original='Exact selected text. '.repeat(100)+'FINAL SENTENCE';
 expect(renderToStaticMarkup(createElement(TranslationOriginal,{text:original}))).toContain(original);
});
