import {it,expect} from 'vitest';
import {mathMarkdown,Answer} from './Answer';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

it('renders delimiter-free local probability equations while preserving prose and code',()=>{
 const text='베이즈 식:\np(Y|X)=p(X|Y) \\cdot p(Y) / p(X)\n```\np(X)=0.2\n```';
 const converted=mathMarkdown(text);
 expect(converted).toContain('$p(Y|X)=');expect(converted).toContain('```\np(X)=0.2\n```');
 const html=renderToStaticMarkup(createElement(Answer,{text,sources:[],onSource:()=>{}}));
 expect(html).toContain('katex');
 expect(mathMarkdown('p(X)=0.2, where X is a random variable')).toContain('$p(X)=0.2$, where X is a random variable');
});

it('does not confuse an inline double-dollar block with an open multiline block',()=>{
 expect(mathMarkdown('$$p(X)=0.2$$\np(Y)=0.3')).toContain('\n$p(Y)=0.3$');
});

it('renders actual inline local equations while keeping Korean prose outside the math',()=>{
 const text='베이즈 정리: p(Y|X) = [p(X|Y)p(Y)] / p(X)은 조건부 확률입니다. 예시 p(X=0,Y=1) = 0.2이면 확인하세요.';
 const converted=mathMarkdown(text);
 expect(converted).toContain('$p(Y|X) = [p(X|Y)p(Y)] / p(X)$은 조건부 확률입니다.');
 const html=renderToStaticMarkup(createElement(Answer,{text,sources:[],onSource:()=>{}}));
 expect(html.match(/class="katex"/g)).toHaveLength(2);
 expect(html).toContain('은 조건부 확률입니다.');
});
