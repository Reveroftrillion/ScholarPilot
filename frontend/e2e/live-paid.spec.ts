import {test,expect,type Page} from '@playwright/test';
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';

test.skip(process.env.APPROVE_LIVE_SCENARIOS!=='1' || !process.env.LIVE_EVALUATION_DIR,'Requires explicit paid approval and marked isolated live server');
test.setTimeout(300000);
const dir=process.env.LIVE_EVALUATION_DIR||'';
async function open(page:Page,fresh=false){
 const state=await (await page.request.get('/api/live-evaluation')).json();
 expect(state.mode).toBe('live');expect(state.transport).toBe('real_openai');expect(state.max_requests).toBe(24);
 await page.goto('/');
 await page.locator('.book-title').filter({hasText:'Deep Learning'}).click();
 if(fresh)await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await page.getByLabel('페이지 번호').fill('48');
 await expect(page.locator('.react-pdf__Page__textContent')).toContainText('Bayes');
}
async function submit(page:Page,message:string,file:string){
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST',{timeout:260000});
 await page.getByLabel('AI 질문').fill(message);
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 const response=await pending;const run=await response.json();
 writeFileSync(join(dir,file),JSON.stringify({request:response.request().postDataJSON(),run},null,2));
 expect(response.ok()).toBeTruthy();expect(run.mode).toBe('live');expect(run.status,run.text).not.toBe('error');
 return run;
}
test('A: real Bayes explanation and clickable PDF source',async({page})=>{
 await open(page,true);
 const run=await submit(page,'이 페이지의 베이즈 정리를 처음 배우는 사람도 이해할 수 있게 설명하고, 수식 유도 과정과 숫자 예제를 보여줘.','scenario-A.json');
 expect(run.sources.some((s:{page:number})=>s.page===48)).toBeTruthy();
 await expect(page.locator('.answer .katex').last()).toBeVisible();
 await expect(page.locator('.inline-source').first()).toBeVisible();
 const link=page.locator('.inline-source').first();
 await link.click();
 const pageNumber=await page.getByLabel('페이지 번호').inputValue();
 writeFileSync(join(dir,'browser-A.json'),JSON.stringify({math_rendered:true,source_click_pdf_page:pageNumber}));
 await page.screenshot({path:join(dir,'browser-A.png'),fullPage:true});
});
test('B: real prerequisite diagnosis, semantic grading and restored learning state',async({page})=>{
 await open(page);
 const previous=JSON.parse(readFileSync(join(dir,'scenario-A.json'),'utf8')).run;
 const diagnosis=await submit(page,'아직 조건부확률이 이해가 안 돼. 내가 부족한 부분을 확인해 줘. 제 말로 답하는 단답형 확인 문제를 하나 내고 답안을 기다려 주세요.','scenario-B-diagnosis.json');
 expect(diagnosis.session_id).toBe(previous.session_id);
 expect(diagnosis.status).toBe('awaiting_answer');expect(diagnosis.quiz.answer).toBeUndefined();
 await page.reload();await expect(page.locator('.quiz-card')).toBeVisible();
 const quiz=diagnosis.quiz;
 const answer='조건부확률은 조건과 상관없이 언제나 1입니다.';
 // Submit through the same UI as a learner, without inspecting the private answer key.
 if(quiz.kind==='choice')await page.locator('.quiz-card input[type="radio"]').last().check();
 else await page.locator('.quiz-card input').fill(answer);
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/chat'),{timeout:260000});
 await page.getByRole('button',{name:'답안 제출',exact:true}).click();
 const response=await pending;const graded=await response.json();
 writeFileSync(join(dir,'scenario-B-grade.json'),JSON.stringify({request:response.request().postDataJSON(),run:graded},null,2));
 expect(graded.status,graded.text).not.toBe('error');expect(graded.evaluation.correct).toBe(false);
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
 await page.reload();await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
 writeFileSync(join(dir,'browser-B.json'),JSON.stringify({quiz_restored:true,learning_state_restored:true}));
 await page.screenshot({path:join(dir,'browser-B.png'),fullPage:true});
});
test('C: real two-book PTQ and QAT search',async({page})=>{
 await open(page,true);await page.getByLabel('검색 범위').selectOption('all');
 const run=await submit(page,'PTQ와 QAT의 차이를 설명하고, 두 교과서에서 관련된 내용을 찾아 비교해 줘.','scenario-C.json');
 expect(run.events.some((e:{tool:string})=>e.tool==='search_across_books')).toBeTruthy();
 await expect(page.locator('.answer').last()).toBeVisible();
 await page.screenshot({path:join(dir,'browser-C.png'),fullPage:true});
});

test('read-only restoration after refused API request',async({page,request})=>{
 const before=await (await request.get('/api/live-evaluation')).json();
 expect(before.errors.length).toBeGreaterThan(0);
 await open(page);
 await expect(page.locator('.answer').last()).toContainText('Evaluation model request failed');
 await page.reload();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('48');
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await expect(page.locator('.quiz-card')).toHaveCount(0);
 await expect(page.locator('.answer').last()).toContainText('Evaluation model request failed');
 const after=await (await request.get('/api/live-evaluation')).json();
 expect(after.requests).toBe(before.requests);
 writeFileSync(join(dir,'browser-refused-restoration.json'),JSON.stringify({history_restored:true,pdf_visible:true,no_quiz_created:true,no_extra_api_call:true}));
});
