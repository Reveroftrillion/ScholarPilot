import {test,expect} from '@playwright/test';

test.skip(!process.env.QA_BASE_URL || process.env.QA_BAYES!=='1','Requires explicit isolated Bayes offline server');
test('Bishop Bayes page, Korean math, prerequisite quiz, wrong answer and restored progress',async({page,request})=>{
 const qa=await (await request.get('/api/qa-mode')).json();
 expect(qa.provider_mode).toBe('bayes');expect(qa.external_api_calls).toBe(0);
 await page.goto('/');
 await page.locator('.book-title').filter({hasText:'Deep Learning'}).click();
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await page.getByLabel('페이지 번호').fill('48');
 await expect(page.locator('.react-pdf__Page__textContent')).toContainText('Bayes');
 const submit=async(text:string)=>{
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/chat') && r.request().method()==='POST');
  await page.getByLabel('AI 질문').fill(text);
  await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
  const response=await pending;expect(response.ok()).toBeTruthy();return response.json();
 };
 const first=await submit("Bayes' theorem을 한국어로 설명하고 기호와 적용 조건을 알려 주세요.");
 expect(first.status).toBe('completed');
 expect(first.events.some((e:{tool:string,status:string})=>e.tool==='search_textbook' && e.status==='ok')).toBeTruthy();
 expect(first.sources.some((s:{page:number})=>s.page===48)).toBeTruthy();
 await expect(page.locator('.answer').last()).toContainText('오프라인 대역');
 await expect(page.locator('.answer .katex').last()).toBeVisible();
 await page.locator('.inline-source').last().click();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('48');
 const diagnosis=await submit('아직 이해하지 못했어요. 선수 지식을 검색하고 확인 문제를 내 주세요.');
 expect(diagnosis.status).toBe('awaiting_answer');
 expect(diagnosis.events.some((e:{tool:string})=>e.tool==='find_prerequisites')).toBeTruthy();
 expect(diagnosis.quiz.answer).toBeUndefined();
 await page.reload();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('48');
 await expect(page.locator('.quiz-card')).toBeVisible();
 await page.getByLabel('항상 1인 확률',{exact:true}).check();
 const grading=page.waitForResponse(r=>r.url().endsWith('/api/chat'));
 await page.getByRole('button',{name:'답안 제출',exact:true}).click();
 const graded=await (await grading).json();
 expect(graded.evaluation.correct).toBe(false);
 for(const name of ['evaluate_answer','update_mastery','recommend_next_topic'])
  expect(graded.events.some((e:{tool:string,status:string})=>e.tool===name && e.status==='ok')).toBeTruthy();
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
 await page.reload();
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
});
