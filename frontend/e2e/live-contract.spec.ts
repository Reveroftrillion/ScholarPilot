import {test,expect,type Page} from '@playwright/test';
import {writeFileSync} from 'node:fs';
test.skip(!process.env.QA_BASE_URL,'Requires explicit isolated offline model QA server');
test.beforeAll(async({request})=>{
 const response=await request.get('/api/qa-mode');expect(response.ok()).toBeTruthy();
 const qa=await response.json();expect(qa.offline_provider_fixture).toBeTruthy();expect(qa.external_api_calls).toBe(0);
});

async function openBishop(page:Page){
 await page.goto('/');
 await page.locator('.book-title').filter({hasText:'Deep Learning'}).click();
 await page.getByRole('button',{name:'새 대화',exact:true}).click();
 await page.getByLabel('페이지 번호').fill('131');
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await expect(page.locator('.react-pdf__Page__textContent')).toContainText('regression');
}
async function submit(page:Page,text:string){
 const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');
 await page.getByLabel('AI 질문').fill(text);
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 const r=await response;expect(r.ok()).toBeTruthy();
 return {request:r.request().postDataJSON(),run:await r.json()};
}

test('current page, real mouse selection, model tool loop, Markdown math and source click',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await openBishop(page);
 const {request,run}=await submit(page,'여기 설명해 줘');
 expect(request.page).toBe(131);
 expect(run.events[0].tool).toBe('get_current_page');
 expect(run.sources.some((s:{page:number})=>s.page===131)).toBeTruthy();
 await expect(page.locator('.answer').last()).toContainText('오프라인 모델 대역');
 await expect(page.locator('.answer .katex').last()).toBeVisible();
 await page.locator('.inline-source').last().click();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('131');
 const bounds=await page.locator('.react-pdf__Page__textContent').evaluate(el=>{
   const span=Array.from(el.querySelectorAll('span')).find(s=>(s.textContent?.length||0)>40)!;
   const r=span.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
 });
 await page.mouse.move(bounds.x+1,bounds.y+bounds.height/2);await page.mouse.down();
 await page.mouse.move(bounds.x+bounds.width-1,bounds.y+bounds.height/2,{steps:15});await page.mouse.up();
 await expect(page.locator('.selection-card')).toBeVisible();
 const selected=await page.evaluate(()=>window.getSelection()?.toString().trim());expect(selected!.length).toBeGreaterThan(10);
 const sent=page.waitForResponse(r=>r.url().endsWith('/api/chat'));
 await page.getByRole('button',{name:'한국어 번역',exact:true}).click();
 const response=await sent;
 expect(response.request().postDataJSON().selection).toBe(selected);
 expect(response.request().postDataJSON().page).toBe(131);
 await expect(page.locator('.answer').last()).toContainText(selected!.slice(0,15));
 await page.getByRole('button',{name:'문장 저장',exact:true}).click();
 await page.getByRole('button',{name:'목차',exact:true}).click();
 await expect(page.locator('.toc mark').filter({hasText:selected!.slice(0,15)}).first()).toBeVisible();
 await page.getByRole('button',{name:'확대',exact:true}).click();
 await page.getByRole('button',{name:'축소',exact:true}).click();
 await page.getByRole('button',{name:'실행 로그',exact:true}).click();
 await expect(page.locator('.trace-run').first()).toContainText('get_current_page');
 await page.screenshot({path:'test-results/repaired-reader.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('followup diagnosis, wrong-answer feedback, pending quiz restoration and saved progress',async({page})=>{
 await openBishop(page);
 await submit(page,"Bayes' theorem을 설명해 줘");
 const result=await submit(page,'아직 이해가 안 돼. 진단 문제를 내줘');
 expect(result.run.status).toBe('awaiting_answer');
 expect(result.run.events.some((e:{tool:string})=>e.tool==='find_prerequisites')).toBeTruthy();
 await expect(page.locator('.quiz-card')).toBeVisible();
 const quizId=result.run.quiz.id;
 await page.reload();
 await expect(page.getByLabel('페이지 번호')).toHaveValue('131');
 await expect(page.locator('.quiz-card')).toBeVisible();
 await page.getByLabel('항상 1인 확률',{exact:true}).check();
 const submitted=page.waitForResponse(r=>r.url().endsWith('/api/chat'));
 await page.getByRole('button',{name:'답안 제출',exact:true}).click();
 const response=await submitted;const run=await response.json();
 expect(response.request().postDataJSON().quiz_id).toBe(quizId);
 expect(run.evaluation.correct).toBeFalsy();
 expect(run.events.some((e:{tool:string})=>e.tool==='update_mastery')).toBeTruthy();
 await expect(page.locator('.evaluation').last()).toContainText('다시 살펴볼까요');
 await page.getByRole('button',{name:'학습 대시보드',exact:true}).click();
 await expect(page.locator('.status-tag.review')).toContainText('복습 필요');
 await page.screenshot({path:'test-results/repaired-dashboard.png',fullPage:true});
});

test('all and selected books retrieval, cross-book source, upload edit reindex delete and settings',async({page})=>{
 await openBishop(page);
 await page.getByLabel('검색 범위').selectOption('all');
 const result=await submit(page,'Quantization을 두 책에서 비교해 줘');
 expect(new Set(result.run.sources.map((s:{book_id:string})=>s.book_id)).size).toBe(2);
 await page.getByRole('button',{name:'원문 검색',exact:true}).click();
 await page.getByLabel('원문 검색어').fill('Quantization');
 await page.getByRole('button',{name:'검색',exact:true}).click();
 await expect(page.locator('.search-result')).not.toHaveCount(0);
 await page.getByLabel('검색 범위').selectOption('selected');
 const selected=page.waitForResponse(r=>r.url().endsWith('/api/search'));
 await page.getByRole('button',{name:'검색',exact:true}).click();
 const search=await selected;expect(search.request().postDataJSON().book_ids).toHaveLength(1);
 await page.getByLabel('교과서 선택').selectOption({label:'Machine Learning Systems'});
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await page.getByRole('button',{name:'서재로',exact:true}).click();
 const qa=await (await page.request.get('/api/qa-mode')).json();
 expect(qa.offline_provider_fixture).toBeTruthy();
 await page.getByLabel('PDF 업로드').setInputFiles(qa.upload_path);
 const card=page.locator('.book-card').filter({hasText:'QA additional textbook'});
 await expect(card).toBeVisible();await expect(card).not.toContainText('분석 중');
 await card.getByRole('button',{name:'정보 수정',exact:true}).click();
 await page.getByLabel('분야',{exact:true}).fill('테스트 분야');
 await page.getByRole('button',{name:'저장',exact:true}).click();
 await expect(card).toContainText('테스트 분야');
 const reindex=page.waitForResponse(r=>r.url().endsWith('/reindex'));
 await card.getByRole('button',{name:/재인덱싱/}).click();expect((await reindex).ok()).toBeTruthy();
 await expect(card.getByRole('button',{name:/삭제/})).toBeEnabled();
 page.once('dialog',d=>d.accept());await card.getByRole('button',{name:/삭제/}).click();await expect(card).toHaveCount(0);
 await page.getByRole('button',{name:'설정',exact:true}).click();
 await page.getByRole('button',{name:'설정 상태 확인 · 무료',exact:true}).click();
 await expect(page.locator('.ai-check')).toContainText('실제 호출 0회');
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('link',{name:'ScholarPilot',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:'test-results/repaired-mobile.png',fullPage:true});
});

test('multiline and formula selection, page navigation, no results and long-chat stability',async({page})=>{
 await openBishop(page);
 const bookId=await page.getByLabel('교과서 선택').inputValue();
 const context=await (await page.request.get(`/api/books/${bookId}/pages/131`)).json();
 expect(context.page).toBe(131);
 expect(context.chunks.some((c:{printed_page:string})=>c.printed_page==='112')).toBeTruthy();
 const spans=page.locator('.react-pdf__Page__textContent span');
 const positions=await spans.evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {text:node.textContent||'',x:r.x,y:r.y,width:r.width,height:r.height};}).filter(v=>v.text.length>15&&v.width>30&&v.y>180&&v.y<620));
 expect(positions.length).toBeGreaterThan(2);
 const start=positions[0];const end=positions.find(v=>v.y>start.y+4&&v.y<start.y+100)!;expect(end).toBeTruthy();
 await page.mouse.move(start.x+2,start.y+start.height/2);await page.mouse.down();
 await page.mouse.move(end.x+end.width-2,end.y+end.height/2,{steps:20});await page.mouse.up();
 const selection=await page.evaluate(()=>window.getSelection()?.toString().trim());
 expect(selection!.length).toBeGreaterThan(30);await expect(page.locator('.selection-card')).toBeVisible();
 let request=page.waitForResponse(r=>r.url().endsWith('/api/chat'));
 await page.getByRole('button',{name:'자세히 설명',exact:true}).click();
 let r=await request;expect(r.request().postDataJSON().selection).toBe(selection);
 expect(r.request().postDataJSON().page).toBe(131);
 await expect(page.locator('.answer').last()).toContainText('오프라인 모델 대역');
 // Select an equation directly from the real PDF.js text layer. Browser text
 // extraction may differ from the visual PDF, so the UI must warn.
 const equation=spans.filter({hasText:'='}).first();
 await expect(equation).toHaveCount(1);
 await equation.scrollIntoViewIfNeeded();
 await equation.evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);const sel=window.getSelection()!;sel.removeAllRanges();sel.addRange(range);el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));});
 await expect(page.locator('.selection-card')).toContainText('원본과 대조');
 const formulaText=await page.evaluate(()=>window.getSelection()?.toString().trim());
 request=page.waitForResponse(resp=>resp.url().endsWith('/api/chat'));
 await page.getByRole('button',{name:'수식 유도',exact:true}).click();
 r=await request;expect(r.request().postDataJSON().selection).toBe(formulaText);
 const formulaRun=await r.json();expect(formulaRun.text).toContain('원본과 대조');
 const t0=Date.now();
 await page.getByLabel('페이지 번호').fill('132');
 await expect(page.locator('.react-pdf__Page')).toHaveAttribute('data-page-number','132');
 await expect(page.locator('.selection-card')).toHaveCount(0);
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 const pageMs=Date.now()-t0;
 const moved=await submit(page,'현재 페이지 설명해 줘');
 expect(moved.request.page).toBe(132);expect(moved.request.selection).toBe('');
 expect(moved.run.sources.some((s:{page:number})=>s.page===132)).toBeTruthy();
 await page.getByRole('button',{name:'원문 검색',exact:true}).click();
 await page.getByLabel('원문 검색어').fill('zzzznonexistent0987654321');
 await page.getByRole('button',{name:'검색',exact:true}).click();
 await expect(page.getByText('검색 결과가 없습니다.',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'대화',exact:true}).click();
 await page.getByLabel('AI 질문').fill('[QA slow] 현재 페이지 설명');
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
 await expect(page.locator('.thinking')).toBeVisible();
 await expect(page.locator('.thinking')).toHaveCount(0,{timeout:15000});
 for(let i=0;i<5;i++)await submit(page,`추가 질문 ${i} regression`);
 await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
 await submit(page,'[QA failure] 오류 처리');
 await expect(page.locator('.error-answer').last()).toContainText('AI 요청에 실패했습니다');
 await expect(page.locator('.error-answer').last()).not.toContainText('private diagnostic');
 writeFileSync('../docs/browser-performance.json',JSON.stringify({mode:'offline fixture',pdf_page:132,page_transition_ms:pageMs,long_chat_followups:5,source:'single local Edge run; not a benchmark distribution'},null,2));
});
