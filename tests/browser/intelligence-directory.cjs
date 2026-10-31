/* Scrollbar-free directory checks use real profile/tag routes and disposable data. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mws-directory-')),base='http://127.0.0.1:8874';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temp,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8874'},stdio:['ignore','ignore','pipe']});let browser,logs='';server.stderr.on('data',data=>logs+=data);
(async()=>{
 for(let n=0;;n++){try{await fetch(base+'/login');break;}catch{if(n>100||server.exitCode!==null)throw Error(logs);await new Promise(resolve=>setTimeout(resolve,100));}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({hasTouch:true,viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(15000);
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in',exact:true}).click()]);
 await page.goto(base+'/tags');const csrf=await page.locator('input[name=csrf]').first().inputValue(),routes=['/malware-families','/threat-actors','/tags'];
 async function create(index){for(const [route,prefix] of [[routes[0],'MAL_'],[routes[1],'TA_']])assert.equal((await page.request.post(base+route+'/new',{form:{csrf,name:'Directory object '+String(index).padStart(2,'0'),tag:prefix+'DIRECTORY_'+index}})).status(),200);}
 const list=page.locator('.intelligence-directory-list');
 async function inspect(long){
  await page.waitForLoadState('networkidle');const metrics=await list.evaluate(e=>{const s=getComputedStyle(e);return {height:e.clientHeight,extent:e.scrollHeight,gutter:e.offsetWidth-e.clientWidth,overflow:s.overflowY,width:s.scrollbarWidth,webkit:getComputedStyle(e,'::-webkit-scrollbar').display};});
  assert.equal(metrics.overflow,'auto');assert.equal(metrics.width,'none');assert.equal(metrics.webkit,'none');assert.equal(metrics.gutter,0);
  assert.ok(long?metrics.extent>metrics.height:metrics.extent<=metrics.height+1,JSON.stringify(metrics));
  assert.ok(await list.evaluate(e=>{for(let p=e.parentElement;p&&!p.matches('body');p=p.parentElement){if(/auto|scroll/.test(getComputedStyle(p).overflowY))return false;}return true;}),'No competing directory scroll ancestor');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 await create(0);
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:900});for(const route of routes){await page.goto(base+route);await inspect(false);await page.screenshot({path:`/tmp/mws-directory-short-${routes.indexOf(route)}-${width}.png`});}}
 for(let i=1;i<30;i++)await create(i);
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:900});
  for(const route of routes){
   console.log('Long directory:',width,route);await page.goto(base+route);await inspect(true);
   const rows=list.locator('.family-choice');await rows.first().focus();
   for(let n=1;n<await rows.count();n++)await page.keyboard.press('Tab');
   assert.ok(await rows.last().evaluate(e=>{const r=e.getBoundingClientRect(),p=e.closest('.intelligence-directory-list').getBoundingClientRect();return document.activeElement===e&&r.top>=p.top-1&&r.bottom<=p.bottom+1;}),'Keyboard focus reveals the last object');
   await list.evaluate(e=>e.scrollTop=0);await list.hover();await page.mouse.wheel(0,400);
   await page.waitForFunction(()=>document.querySelector('.intelligence-directory-list').scrollTop>=399);
   await list.evaluate(e=>e.scrollTop=0);await list.scrollIntoViewIfNeeded();
   const r=await list.boundingBox(),y=Math.max(220,Math.min(r.y+r.height/2,650)),x=r.x+r.width/2,cdp=await context.newCDPSession(page);
   assert.ok(await page.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('.intelligence-directory-list'),{x,y}));
   await cdp.send('Input.synthesizeScrollGesture',{x,y,yDistance:-200,gestureSourceType:'touch',speed:600});await cdp.detach();
   await page.waitForFunction(()=>document.querySelector('.intelligence-directory-list').scrollTop>0);
   await list.evaluate(e=>e.scrollTop=e.scrollHeight);await page.screenshot({path:`/tmp/mws-directory-long-${routes.indexOf(route)}-${width}.png`});
   const selectedPath=new URL(await rows.last().getAttribute('href'),base).pathname;await rows.last().focus();await page.keyboard.press('Enter');await page.waitForURL(url=>url.pathname===selectedPath);await page.locator('.family-profile-header').waitFor();
   if(width<=900){await page.locator('[data-workspace-back]').click();await list.waitFor();}
   assert.ok(await list.locator('[aria-current=page]').evaluate(e=>{const r=e.getBoundingClientRect(),p=e.closest('.intelligence-directory-list').getBoundingClientRect();return r.top>=p.top-1&&r.bottom<=p.bottom+1;}),'Activated selection remains visible');
   await page.locator('.intelligence-toolbar [name=q]').fill(route==='/tags'?'DIRECTORY_0':'Directory object 00');await page.locator('.intelligence-toolbar > button').click();await page.waitForURL(url=>url.searchParams.get('q')===(route==='/tags'?'DIRECTORY_0':'Directory object 00'));await inspect(false);
  }
 }
 assert.deepEqual(errors,[]);console.log('Directory checks passed: short/long lists, hidden scrollbar/no gutter, no nested scroll areas, wheel/touch/Tab reachability, selection and search at 1440/768/390px.');
})().catch(error=>{console.error(error);console.error(logs.slice(-1400));process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temp,{recursive:true,force:true});});
