import {describe,it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AICheck} from './ConnectionStatus';

describe('AI connection controls',()=>{
 it('never offers a paid request in local mode, even with a stale paid flag',()=>{
  const html=renderToStaticMarkup(createElement(AICheck,{local:true,allowPaid:true}));
  expect(html).toContain('Ollama 연결 확인');
  expect(html).toContain('AI 설명을 생성하지 않습니다');
  expect(html).not.toContain('유료 호출 승인');
 });
 it('hides paid calls until provider settings explicitly enable them',()=>{
  expect(renderToStaticMarkup(createElement(AICheck))).not.toContain('유료 호출 승인');
  expect(renderToStaticMarkup(createElement(AICheck,{allowPaid:true}))).toContain('유료 호출 승인');
 });
});
