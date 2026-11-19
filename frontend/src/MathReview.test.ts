import {it,expect} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MathResult,TaskStatus,QuizTrust,ManualReviewPanel} from './MathReview';

it('shows the exact scope of independent math and never invents missing results',()=>{
 const html=renderToStaticMarkup(createElement(MathResult,{review:{status:'unverified',formula:'p(Y|X)',scope:'확률 해석 미검증',reason:'원문 확인 필요'}}));
 expect(html).toContain('미검증');expect(html).toContain('원문 확인 필요');expect(html).not.toContain('0.4');
});
it('distinguishes real phases and unverified quiz keys',()=>{
 expect(renderToStaticMarkup(createElement(TaskStatus,{phase:'generating'}))).toContain('생성 중');
 expect(renderToStaticMarkup(createElement(QuizTrust,{verification:{status:'unverified',measurement:'개념 문제 미확인'}}))).toContain('자동 이해도 반영 없음');
});
it('manual self review requires explicit confirmation before submission',()=>{
 const html=renderToStaticMarkup(createElement(ManualReviewPanel,{evaluation:{attempt_id:'attempt',uncertain:true,correct:false,answer:'candidate',explanation:'pending',cause:'unknown',next_action:'review',key_verified:false}}));
 expect(html).toContain('disabled=""');expect(html).toContain('자가 채점');
});
