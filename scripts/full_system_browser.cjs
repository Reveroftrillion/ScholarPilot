// Real PDF text-layer selections and UI actions. Raw excerpts stay in ignored data/.
const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const base=process.env.EVALUATION_BASE||'http://127.0.0.1:8022';
 const state=await (await fetch(base+'/api/local-evaluation')).json();
 const revision=(await (await fetch(base+'/api/health')).json()).running_revision;
 const root=state.data_dir,manifest=JSON.parse(fs.readFileSync(path.join(root,'full-manifest.json'),'utf8'));
 const output=path.join(root,'full-browser.jsonl');
 const done=new Set(fs.existsSync(output)?fs.readFileSync(output,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse).filter(r=>r.response?.task==='translate'&&r.response.status!=='error'&&!r.browser_error).map(r=>r.id):[]);
 for(const id of (process.env.EVALUATION_FORCE_IDS||'').split(','))done.delete(id);
 const targets=[...manifest.slice(0,24).filter((_,i)=>i%2===0).slice(0,10),...manifest.slice(24).filter((_,i)=>i%2===0).slice(0,10)];
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  for(let i=0;i<targets.length;i++){
   if(done.has(`translate-${String(i+1).padStart(2,'0')}`))continue;
   const m=targets[i],p=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];
   p.setDefaultTimeout(15000);
   p.on('pageerror',e=>{errors.push(e.message);console.log('PAGE_ERROR',e.message);});
   const row={id:`translate-${String(i+1).padStart(2,'0')}`,kind:'translate',model:state.model,revision,book:m.book,page:m.page,printed:m.printed,section:m.section};
   const start=Date.now();
   const stage=value=>{row.stage=value;fs.writeFileSync(path.join(root,'browser-current.json'),JSON.stringify(row));console.log(row.id,value);};
   try {
    stage('open');
    await p.goto(base);
    const historyLoaded=p.waitForResponse(r=>r.url().endsWith(`/api/books/${m.book_id}/history`));
    await p.locator('.book-title').filter({hasText:m.book}).click();await historyLoaded;
    await p.waitForTimeout(200);
    stage('history-loaded');
    await p.getByRole('button',{name:'새 대화',exact:true}).click();
    const page=p.getByLabel('페이지 번호');await page.fill(String(m.page));
    const layer=p.locator(`.react-pdf__Page[data-page-number="${m.page}"] .react-pdf__Page__textContent`);await layer.locator('span').first().waitFor({timeout:60000});
    stage('pdf-loaded');
    // Wait for the PDF text layer corresponding to the requested page.
    await p.waitForTimeout(600);
    row.selection=await layer.evaluate(el=>{
     const spans=[...el.querySelectorAll('span')].filter(s=>s.firstChild?.nodeType===Node.TEXT_NODE);
     const first=spans.findIndex(s=>s.textContent.length>45&&/[A-Za-z]{4}/.test(s.textContent));
     if(first<0)throw Error('No actual prose span');
     let last=first,length=0;
     while(last<spans.length-1&&length<500){length+=spans[last].textContent.length;if(length>=300&&/[.!?]$/.test(spans[last].textContent.trim()))break;last++;}
     const range=document.createRange();range.setStart(spans[first].firstChild,0);range.setEnd(spans[last].firstChild,spans[last].textContent.length);
     const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
     spans[first].dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));return selection.toString();
    });
    stage('selected');
    const sent=p.waitForRequest(r=>r.method()==='POST'&&/\/api\/chat(?:\/jobs)?$/.test(r.url()));
    await p.getByRole('button',{name:'한국어 번역',exact:true}).click();row.request=(await sent).postDataJSON();
    stage('requested');
    await p.locator('.chat-turn').first().waitFor({timeout:90000});stage('answer-rendered');
    const history=await(await p.request.get(base+`/api/books/${m.book_id}/history`)).json();
    const own=history.filter(h=>h.request.page===row.request.page&&h.request.selection===row.request.selection&&h.request.task==='translate').at(-1);
    if(!own)throw Error('No persisted response for this exact browser request');row.response=own.response;
    row.checks={selection_payload_exact:row.request.selection===row.selection,selection_content_exact:row.request.selection===row.selection.trim(),original_preserved:row.response.translation_source===row.request.selection,translation_semantics:'unverified',js_errors:errors};
    if(row.response.sources?.length){
     const sources=p.locator('.sources').last();await sources.locator('summary').click();await sources.locator('button').first().click();
     row.checks.source_navigation=+(await page.inputValue())===row.response.sources[0].page;
    }
    await p.reload();await p.locator('.chat-turn').first().waitFor({timeout:60000});
    row.checks.page_restored=+(await page.inputValue())===m.page;
    row.checks.history_restored=(await p.locator('.chat-turn').count())>=1;
   }catch(e){row.browser_error=e.message;await p.screenshot({path:path.join(root,row.id+'-error.png'),timeout:5000}).catch(()=>{});}
   row.elapsed=(Date.now()-start)/1000;
   fs.appendFileSync(path.join(root,'full-browser.jsonl'),JSON.stringify(row)+'\n');
   console.log(row.id,row.response?.status,row.browser_error||JSON.stringify(row.checks));
   await p.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
