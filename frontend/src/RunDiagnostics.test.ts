import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {QualityNotice,TracePanel} from './RunDiagnostics';
import type {Run} from './api';

it('shows incomplete math as review required rather than a quality score',()=>{
 const html=renderToStaticMarkup(createElement(QualityNotice,{quality:{status:'needs_review',issues:['숫자 예제를 검증하지 못했습니다.'],limits:'모든 수학을 증명하지 않습니다.',math_checks:[]}}));
 expect(html).toContain('검토가 필요한');expect(html).toContain('숫자 예제');expect(html).not.toContain('100%');
 expect(renderToStaticMarkup(createElement(QualityNotice,{quality:undefined}))).toBe('');
});

it('distinguishes server orchestration, actual generated actions, and legacy records',()=>{
 const run={id:'r',status:'completed',elapsed:1,provider:'ollama',usage:{api_calls:1,input_tokens:1,output_tokens:1},events:[
  {tool:'search_textbook',status:'ok',actor:'server',input:{},output:[],elapsed_ms:2},
  {tool:'explain_concept',status:'ok',actor:'model',input:{},output:{}},
  {tool:'legacy',status:'ok',input:{},output:{}}]} as Run;
 const html=renderToStaticMarkup(createElement(TracePanel,{runs:[{request:'Explain',run}]}));
 expect(html).toContain('서버 실행');expect(html).toContain('모델 생성 행동');expect(html).toContain('실행 주체 미기록');expect(html).toContain('2ms');
});
