/* Isolated real-browser MIP search integration; no production data touched. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-search-browser-'));
const python=path.join(root,'.venv/bin/python'),port=8782,base=`http://127.0.0.1:${port}`;
const server=spawn(python,['tests/browser/server.py'],{cwd:root,env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let log='',browser;server.stderr.on('data',data=>log+=data);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>60||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 const folder=path.join(temporary,'cases/1/mip/supporting');
 fs.writeFileSync(path.join(folder,'current.txt'),'evil[.]example[.]com\n<script>search needle</script>\nsearch needle');
 fs.mkdirSync(path.join(temporary,'archives'));
 const zip=spawnSync(python,['-c',`import json,zipfile,sys\nwith zipfile.ZipFile(sys.argv[1],'w') as z:\n z.writestr('pkg/manifest.json',json.dumps({'schema':'mare-mip/2.0','archive_type':'standard','case_number':'CM-TEST','title':'Archived case'}))\n z.writestr('pkg/supporting/old.txt','archived search needle')`,path.join(temporary,'archives/old.zip')]);assert.equal(zip.status,0,zip.stderr.toString());
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}});const errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(base))external.push(r.url());});
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 async function checkNavigation(href){
  const active=page.locator('.admin-nav a[aria-current="page"]');assert.equal(await active.count(),1);assert.equal(await active.getAttribute('href'),href);
  const style=await active.evaluate(link=>{const css=getComputedStyle(link);return {color:css.color,decoration:css.textDecorationLine,thickness:css.textDecorationThickness};});
  assert.deepEqual(style,{color:'rgb(217, 174, 88)',decoration:'underline',thickness:'2px'});
  await active.focus();assert.equal(await active.evaluate(link=>getComputedStyle(link).outlineStyle),'solid');
 }
 for(const [route,parent] of [['/','/'],['/cases/new','/'],['/cases/1','/'],['/metrics','/metrics'],['/tags','/tags'],['/tools','/tools'],['/users','/users'],['/audit','/audit'],['/account','/account'],['/api','/api'],['/import-export','/import-export']]){
  await page.goto(base+route);await checkNavigation(parent);
 }
 await page.getByRole('link',{name:'SEARCH',exact:true}).click();await checkNavigation('/search');
 await page.locator('[name=q]').fill('search needle');await page.locator('[name=q]').press('Enter');
 await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('1 matching packages')&&document.querySelector('#search-status').textContent.includes('2 matching artifacts'),null,{timeout:30000});
 assert.ok(await page.locator('#mip-search-results mark').count()>=3);assert.equal(await page.locator('#mip-search-results script').count(),0);
 assert.match(await page.locator('#mip-search-results').innerText(),/old.zip/);
 // Exercise dynamically rendered group folding and pagination with real finding
 // payloads, keeping this presentation test independent of indexing timing.
 const payload=await page.evaluate(async()=>await (await fetch('/search/results?q=search+needle')).json());
 const original=payload.groups[0];let foldingRequests=0;
 await page.route('**/search/results?**',async route=>{
  const url=new URL(route.request().url());if(url.searchParams.get('q')!=='foldtest')return route.continue();
  foldingRequests++;const pageNumber=Number(url.searchParams.get('page')||1);
  const groups=pageNumber===1?[original,{...original,case:{...original.case,number:'FOLD-002',name:'Independent group'}}]:[original];
  await route.fulfill({json:{...payload,status:{...payload.status,state:'ready'},groups,page:pageNumber,pages:2}});
 });
 await page.locator('[name=q]').fill('foldtest');await page.locator('[name=q]').press('Enter');
 const toggles=page.locator('.search-group-toggle');await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===2);
 assert.deepEqual(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-expanded'))),['true','true']);
 assert.equal(new Set(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-controls')))).size,2);
 await page.evaluate(()=>{window.foldTable=document.querySelector('.search-result-table');});
 const beforeFold=foldingRequests;
 await toggles.first().focus();await toggles.first().press('Enter');
 assert.equal(await toggles.first().getAttribute('aria-expanded'),'false');assert.match(await toggles.first().getAttribute('aria-label'),/^Expand results for /);
 assert.equal(await toggles.first().textContent(),'▸');assert.equal(await toggles.nth(1).getAttribute('aria-expanded'),'true');
 assert.equal(await page.locator('.search-table-wrap').first().isVisible(),false);
 assert.equal(await page.locator('.search-group-header').first().isVisible(),true);
 assert.equal(await toggles.first().evaluate(n=>getComputedStyle(n).outlineStyle),'solid');
 await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Open case');
 await page.keyboard.press('Tab');assert.equal(await toggles.nth(1).evaluate(n=>n===document.activeElement),true);
 for(let i=0;i<2;i++){await page.getByRole('button',{name:'Collapse All',exact:true}).click();assert.deepEqual(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-expanded'))),['false','false']);}
 for(let i=0;i<2;i++){await page.getByRole('button',{name:'Expand All',exact:true}).click();assert.deepEqual(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-expanded'))),['true','true']);}
 assert.equal(await page.evaluate(()=>window.foldTable===document.querySelector('.search-result-table')),true);
 assert.equal(foldingRequests,beforeFold);
 await page.getByRole('button',{name:'Collapse All',exact:true}).click();
 await page.locator('#search-pagination').getByRole('button',{name:'Next',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#search-pagination').textContent.includes('Page 2 of 2'));
 assert.equal(await toggles.first().getAttribute('aria-expanded'),'true');
 await toggles.first().press('Space');assert.equal(await toggles.first().getAttribute('aria-expanded'),'false');
 await page.locator('[name=q]').press('Enter');await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===2);
 assert.equal(await toggles.first().getAttribute('aria-expanded'),'true');
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:1366,height:900});
 await page.locator('[name=q]').fill('search needle');await page.locator('[name=q]').press('Enter');
 await page.waitForFunction(()=>document.querySelectorAll('.search-group-toggle').length===1&&document.querySelector('#search-status').textContent.includes('2 matching artifacts'));
 const archivedRow=page.locator('tr').filter({hasText:'old.txt'});await archivedRow.getByRole('link',{name:'Open finding'}).click();
 assert.equal(await page.locator('.search-preview').textContent(),'archived search needle');
 await checkNavigation('/search');
 await page.getByRole('link',{name:'Back to Search'}).click();
 await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('2 matching artifacts'));
 await page.locator('[name=q]').fill('evil.example.com');await page.getByRole('button',{name:'Search',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('1 matching artifacts'));
 assert.equal(await page.locator('#mip-search-results mark').textContent(),'evil[.]example[.]com');
 await page.setViewportSize({width:1024,height:768});assert.ok(await page.locator('[name=q]').isVisible());
 await page.getByRole('button',{name:'Clear',exact:true}).click();assert.equal(await page.locator('#mip-search-results').textContent(),'');assert.equal(await page.locator('[name=q]').inputValue(),'');
 assert.equal(await page.getByRole('button',{name:'Expand All',exact:true}).isDisabled(),true);assert.equal(await page.getByRole('button',{name:'Collapse All',exact:true}).isDisabled(),true);
 await page.locator('[name=q]').fill('no-match-unique-987654');await page.locator('[name=q]').press('Enter');await page.waitForFunction(()=>document.querySelector('#search-status').textContent.includes('No matching results.'));
 assert.equal(await toggles.count(),0);assert.equal(await page.getByRole('button',{name:'Expand All',exact:true}).isDisabled(),true);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log('PASS: background indexing, case grouping, archives, exact-source preview, safe highlights, defanged literal search, Enter/Clear, laptop layout; no browser errors or external requests.');
})().catch(error=>{console.error(error);console.error(log);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));fs.rmSync(temporary,{recursive:true,force:true});});
