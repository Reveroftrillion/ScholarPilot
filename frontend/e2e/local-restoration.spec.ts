import {test,expect} from '@playwright/test';

// Read-only browser verification of saved, genuine Ollama results. This test
// never asks any model to generate another response. Run after A/B/grade/C/D.
test.skip(!process.env.LOCAL_EVALUATION_URL,'Requires a marked actual-local evaluation server');
test.use({baseURL:process.env.LOCAL_EVALUATION_URL});
test('actual local results, PDF source navigation, selection and learning-state restoration without inference',async({page,request})=>{
 const state=await (await request.get('/api/local-evaluation')).json();
 expect(state.provider).toBe('ollama');expect(state.mode).toBe('live');expect(state.external_paid_calls).toBe(0);
 const initialCalls=state.model_calls;
 const errors:string[]=[];const chatRequests:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/chat',route=>{chatRequests.push(route.request().url());return route.abort();});
 const books=await (await request.get('/api/books')).json();
 const bishop=books.find((b:{title:string})=>b.title.includes('Bishop'));
 expect(bishop).toBeTruthy();
 const history=await (await request.get(`/api/books/${bishop.id}/history`)).json();
 const genuine=history.filter((h:{response:{provider:string;mode:string;status:string}|null})=>h.response?.provider==='ollama'&&h.response.mode==='live'&&h.response.status!=='error');
 expect(genuine.length,'Run the genuine local learning scenarios before this read-only check').toBeGreaterThan(0);
 await page.goto('/');
 await expect(page.locator('.mode-pill')).toContainText('Ollama');
 await page.locator('.book-title').filter({hasText:bishop.title}).click();
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await expect(page.locator('.answer-label').last()).toContainText('LOCAL AI');
 await expect(page.locator('.user-message').last()).toHaveText(history.at(-1).request.message);
 await expect(page.locator('.answer').last()).toBeVisible();
 const sources=page.locator('.sources');
 if(await sources.count()){
  await sources.last().locator('summary').click();
  const first=sources.last().getByRole('button').first();
  const label=await first.innerText();const target=label.match(/PDF (\d+)p/);
  expect(target).toBeTruthy();await first.click();
  await expect(page.getByLabel('페이지 번호')).toHaveValue(target![1]);
  await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 }
 await page.getByLabel('교과서 선택').selectOption(bishop.id);
 await page.getByLabel('페이지 번호').fill('48');
 await expect(page.locator('.react-pdf__Page__textContent')).toContainText('Bayes');
 await page.locator('.react-pdf__Page__textContent').evaluate(el=>{
  const span=Array.from(el.querySelectorAll('span')).find(s=>(s.textContent?.length||0)>20)!;
  const range=document.createRange();range.selectNodeContents(span);const selection=window.getSelection()!;
  selection.removeAllRanges();selection.addRange(range);span.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
 });
 await expect(page.locator('.selection-card')).toBeVisible();
 await expect(page.getByRole('button',{name:'쉽게 설명',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'실행 로그',exact:true}).click();
 await expect(page.locator('.trace-run').first()).toContainText('로컬 모델 요청');
 await page.reload();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('48');
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await expect(page.locator('.answer-label').last()).toContainText('LOCAL AI');
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 const dashboard=await (await request.get('/api/dashboard')).json();
 if(dashboard.mastery.some((m:{status:string})=>m.status==='복습 필요'))await expect(page.locator('.status-tag.review').first()).toContainText('복습 필요');
 await page.getByRole('button',{name:'설정',exact:true}).click();
 await expect(page.getByRole('button',{name:/유료 호출 승인/})).toHaveCount(0);
 await page.getByRole('button',{name:'Ollama 연결 확인 · 무료',exact:true}).click();
 await expect(page.locator('.ai-check')).toContainText('외부 유료 호출 없음');
 await expect(page.locator('.ai-check')).toContainText('텍스트를 생성하지 않습니다');
 // Switch books and exercise the actual backend search without generation.
 await page.getByRole('button',{name:'내 서재',exact:true}).click();
 const systems=books.find((b:{title:string})=>b.title.includes('Machine Learning Systems'));
 await page.locator('.book-title').filter({hasText:systems.title}).click();
 await expect(page.getByLabel('교과서 선택')).toHaveValue(systems.id);
 await page.getByRole('button',{name:'원문 검색',exact:true}).click();
 const search=page.waitForResponse(r=>r.url().endsWith('/api/search')&&r.request().method()==='POST');
 await page.getByLabel('원문 검색어').fill('PTQ QAT');
 await page.getByRole('button',{name:'검색',exact:true}).click();
 const searchResponse=await search;const results=await searchResponse.json();
 expect(results.length).toBeGreaterThan(0);
 expect(results.every((r:{book_id:string})=>r.book_id===systems.id)).toBe(true);
 await expect(page.locator('.search-result').first()).toBeVisible();
 await page.locator('.search-result').first().click();
 await expect(page.getByLabel('페이지 번호')).toHaveValue(String(results[0].page));
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 const after=await (await request.get('/api/local-evaluation')).json();
 expect(after.model_calls).toBe(initialCalls);expect(after.external_paid_calls).toBe(0);
 expect(chatRequests).toEqual([]);expect(errors).toEqual([]);
 await page.screenshot({path:'test-results/local-restoration.png',fullPage:true});
});
