import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
import {resolve,sep} from 'node:path';

// Explicit opt-in: these are real, potentially slow CPU generations. This
// never runs as part of the ordinary offline/browser regression suite.
// Historical semantic-quality diagnostic. The current guarded workflow is
// covered by reliable-learning.spec.ts; never run both sets of paid-in-time
// local generations through the ordinary inference opt-in.
test.skip(!process.env.LOCAL_EVALUATION_URL||process.env.RUN_LOCAL_INFERENCE!=='1'||process.env.RUN_LEGACY_LOCAL_FLOW!=='1','Historical local-flow diagnostic; use reliable-learning.spec.ts');
test.use({baseURL:process.env.LOCAL_EVALUATION_URL});
test('real local PDF selection, prerequisite diagnosis, private quiz, semantic grading and restoration',async({page,request})=>{
 test.setTimeout(1_200_000);
 const state=await (await request.get('/api/local-evaluation')).json();
 expect(state.provider).toBe('ollama');expect(state.external_paid_calls).toBe(0);
 const destination=resolve(state.data_dir);
 expect(destination.startsWith(resolve('..','data','local-evaluation-runs')+sep)).toBe(true);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const save=(scenario:string,payload:unknown)=>writeFileSync(resolve(destination,`scenario-${scenario}.json`),JSON.stringify(payload,null,2),'utf8');
 await page.goto('/');
 await expect(page.locator('.mode-pill')).toContainText('Ollama');
 await page.locator('.book-title').filter({hasText:'Deep Learning'}).click();
 await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeDisabled();
 await page.getByLabel('페이지 번호').fill('48');
 await expect(page.locator('.react-pdf__Page__textContent')).toContainText('Bayes');
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 // Select actual PDF.js text, using the same DOM selection/pointer-up event
 // read by a physical drag; retain the exact selected characters as evidence.
 const selection=await page.locator('.react-pdf__Page__textContent').evaluate(el=>{
  const span=Array.from(el.querySelectorAll('span')).find(s=>s.textContent?.includes('From the product rule'))!;
  if(!span)throw new Error('Actual Bayes passage was not rendered');
  const range=document.createRange();range.selectNodeContents(span);const selected=window.getSelection()!;
  selected.removeAllRanges();selected.addRange(range);el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
  return selected.toString().trim();
 });
 await expect(page.locator('.selection-card')).toContainText(selection);
 await expect(page.getByRole('button',{name:'쉽게 설명',exact:true})).toBeEnabled();
 const selectionPending=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST',{timeout:900_000});
 await page.getByRole('button',{name:'쉽게 설명',exact:true}).click();
 const selectionResponse=await selectionPending;const selectedRun=await selectionResponse.json();
 save('selection',{request:selectionResponse.request().postDataJSON(),run:selectedRun});
 expect(selectedRun.provider).toBe('ollama');expect(selectedRun.status).toBe('completed');
 expect(selectionResponse.request().postDataJSON().selection).toBe(selection);
 await expect(page.locator('.answer-label').last()).toContainText('LOCAL AI');
 await expect(page.locator('.answer').last()).toBeVisible();
 const diagnosisText='아직 조건부확률이 이해가 안 돼. 선수 개념을 검색하고 설명한 다음, 내가 부족한 부분을 확인할 단답형 문제를 하나 내고 답안을 기다려 줘.';
 const diagnosisPending=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST',{timeout:900_000});
 await page.getByLabel('AI 질문').fill(diagnosisText);
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 const diagnosisResponse=await diagnosisPending;expect(diagnosisResponse.ok()).toBe(true);
 const diagnosisRequest=diagnosisResponse.request().postDataJSON();const diagnosis=await diagnosisResponse.json();
 save('B',{request:diagnosisRequest,run:diagnosis});
 expect(diagnosisRequest.page).toBe(48);expect(diagnosisRequest.selection).toBe(selection);
 expect(diagnosis.provider).toBe('ollama');expect(diagnosis.status).toBe('awaiting_answer');
 for(const tool of ['find_prerequisites','explain_concept','generate_quiz'])expect(diagnosis.events.some((e:{tool:string;status:string})=>e.tool===tool&&e.status==='ok')).toBe(true);
 expect(diagnosis.quiz.kind).toBe('short');expect(diagnosis.quiz.answer).toBeUndefined();expect(diagnosis.quiz.explanation).toBeUndefined();
 await expect(page.locator('.quiz-card')).toBeVisible();
 const callsBeforeReload=(await (await request.get('/api/local-evaluation')).json()).model_calls;
 await page.reload();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('48');
 await expect(page.locator('.quiz-question')).toHaveText(diagnosis.quiz.question);
 expect((await (await request.get('/api/local-evaluation')).json()).model_calls).toBe(callsBeforeReload);
 await page.getByLabel('진단 답안').fill('조건부확률은 조건과 상관없이 언제나 1입니다.');
 const gradingPending=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST',{timeout:900_000});
 await page.getByRole('button',{name:'답안 제출',exact:true}).click();
 const gradingResponse=await gradingPending;expect(gradingResponse.ok()).toBe(true);
 const grading=await gradingResponse.json();save('grade',{request:gradingResponse.request().postDataJSON(),run:grading});
 // Continue checking persistence/navigation even when model quality fails;
 // soft assertions still make this test FAIL in that case.
 expect.soft(grading.status).toBe('completed');expect.soft(grading.evaluation.correct).toBe(false);expect.soft(grading.evaluation.uncertain).toBe(false);
 expect(grading.evaluation.grading).toContain('AI 의미 평가');
 // The compact workflow publishes evaluate_answer's own feedback without a
 // redundant second explanation generation. The quality assertions stay strict.
 for(const tool of ['evaluate_answer','recommend_next_topic','update_mastery'])expect(grading.events.some((e:{tool:string;status:string})=>e.tool===tool&&e.status==='ok')).toBe(true);
 expect.soft(grading.events.some((e:{tool:string;status:string})=>e.tool==='find_prerequisites'&&e.status==='ok')).toBe(true);
 await expect(page.locator('.evaluation').last()).toBeVisible();
 await expect(page.locator('.quiz-card')).toHaveCount(0);
 await page.reload();
 await expect(page.locator('.evaluation').last()).toBeVisible();await expect(page.locator('.quiz-card')).toHaveCount(0);
 const sources=page.locator('.sources').last();await sources.locator('summary').click();
 const source=sources.getByRole('button').first();const match=(await source.innerText()).match(/PDF (\d+)p/);
 expect(match).toBeTruthy();await source.click();await expect(page.getByLabel('페이지 번호')).toHaveValue(match![1]);
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 if(!grading.evaluation.uncertain)await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
 expect(errors).toEqual([]);await page.screenshot({path:'test-results/local-learning.png',fullPage:true});
});
