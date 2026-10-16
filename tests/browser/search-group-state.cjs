/* Deterministic polling races against the real Search UI, with isolated data. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-search-folding-'));
const port=8787,base=`http://127.0.0.1:${port}`;
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',data=>log+=data);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const poll=deferred(),pollStarted=deferred(),stale=deferred(),staleStarted=deferred();
const group=id=>({case:{id,number:`CASE-${id}`,name:`Case ${id}`,stage:1},title:'Current workspace',artifact_total:0,findings:[]});
const archive=title=>({case:null,archive_case:{number:'ARCHIVE',name:title},title,artifact_total:0,findings:[]});
const payload=(groups,state='ready',page=1)=>({groups,packages:groups.length,artifacts:0,page,pages:2,status:{state}});
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(error){if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage();page.setDefaultTimeout(10000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 // Let one intentionally late response complete despite abort, exercising the
 // generation guard rather than relying on the browser cancelling the request.
 await page.addInitScript(()=>{
  const fetch=window.fetch.bind(window);
  window.fetch=(url,options)=>{
   if(new URL(url,location.href).searchParams.get('q')!=='stale')return fetch(url,options);
   return fetch(url,{...options,signal:undefined}).then(response=>{
    const json=response.json.bind(response);
    response.json=async()=>{const data=await json();window.staleConsumed=true;return data;};
    return response;
   });
  };
 });
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 let requests=0,first=0;
 await page.route('**/search/results?**',async route=>{
  requests++;const params=new URL(route.request().url()).searchParams,q=params.get('q'),pageNumber=Number(params.get('page')||1);
  if(q==='first'){
   if(++first===1)return route.fulfill({json:payload([group(1),group(2)],'indexing')});
   pollStarted.resolve();await poll.promise;
   return route.fulfill({json:payload([group(2),archive('retained/a.zip'),group(1),archive('retained/b.zip')])});
  }
  if(q==='stale'){staleStarted.resolve();await stale.promise;return route.fulfill({json:payload([group(99)])}).catch(()=>{});}
  return route.fulfill({json:payload(pageNumber===1?[group(1),group(2)]:[group(1)],'ready',pageNumber)});
 });
 if(process.env.MARE_SEARCH_SCRIPT)await page.route('**/static/mip-search.js',route=>route.fulfill({path:process.env.MARE_SEARCH_SCRIPT,contentType:'application/javascript'}));
 await page.goto(base+'/search');
 const toggle=id=>page.locator('.search-group-toggle').filter({has:page.locator('span')}).and(page.locator(`[data-case-label="CASE-${id}"]`));
 const states=()=>page.locator('.search-group-toggle').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-expanded')));
 async function submit(q){await page.locator('[name=q]').fill(q);await page.locator('[name=q]').press('Enter');}
 async function check(id,expanded){const button=toggle(id);assert.equal(await button.getAttribute('aria-expanded'),String(expanded));assert.equal(await button.textContent(),expanded?'▾':'▸');const content=page.locator('[id='+JSON.stringify(await button.getAttribute('aria-controls'))+']');assert.equal(await content.isVisible(),expanded);}
 await submit('first');await toggle(2).waitFor();assert.deepEqual(await states(),['true','true']);
 // First interaction, before a bulk action or the pending indexing refresh.
 await toggle(1).click();await check(1,false);await check(2,true);
 await pollStarted.promise;poll.resolve();await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===4);
 await check(1,false);await check(2,true);assert.deepEqual(await states(),['true','true','false','true']);
 await toggle(2).focus();await toggle(2).press('Enter');await check(2,false);await check(1,false);
 await toggle(2).press('Space');await check(2,true);await check(1,false);
 const before=requests;
 for(let i=0;i<2;i++){await page.getByRole('button',{name:'Collapse All',exact:true}).click();assert.deepEqual(await states(),['false','false','false','false']);}
 for(let i=0;i<2;i++){await page.getByRole('button',{name:'Expand All',exact:true}).click();assert.deepEqual(await states(),['true','true','true','true']);}
 await toggle(1).click();await check(1,false);assert.equal(requests,before);
 await submit('new');await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===2);await check(1,true);
 await toggle(1).click();await check(1,false);
 await page.locator('#search-pagination').getByRole('button',{name:'Next',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#search-pagination').textContent.includes('Page 2'));
 await check(1,false);
 await page.locator('#search-pagination').getByRole('button',{name:'Previous',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===2);await check(1,false);
 // A slow older query must not restore its groups after the next submission.
 await submit('stale');await staleStarted.promise;await submit('latest');await page.waitForFunction(()=>document.querySelector('#search-status').textContent.startsWith('2 matching packages'));
 await toggle(1).click();await check(1,false);stale.resolve();
 await page.waitForFunction(()=>window.staleConsumed===true);
 await check(1,false);assert.equal(await toggle(99).count(),0);
 // Filter submissions are genuinely new searches, even with the same term.
 await page.locator('[name=stage]').selectOption('1');await page.getByRole('button',{name:'Search',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('[data-case-label="CASE-1"]').getAttribute('aria-expanded')==='true');
 await check(1,true);assert.deepEqual(errors,[]);
 console.log('PASS: first-click folding survives indexing refresh; stable identities, independent/bulk/keyboard controls, new-query/filter reset, pagination and stale-response protection.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{poll.resolve();stale.resolve();await browser?.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));fs.rmSync(temporary,{recursive:true,force:true});});
