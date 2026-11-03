const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-package-navigation-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8817';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8817'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 const pattern='**/cases/1/package-register?*';
 let releaseInitial,noticeInitial;
 const initialGate=new Promise(resolve=>releaseInitial=resolve),initialSeen=new Promise(resolve=>noticeInitial=resolve);
 let holdInitial=true,holdScripts=false,scriptGate,noticeScript;const stalled=[];
 await page.route(pattern,async route=>{
   const section=new URL(route.request().url()).searchParams.get('section');
   const gate=holdInitial&&section===''?initialGate:holdScripts&&section==='scripts'?scriptGate:null;
   if(!gate){await route.continue();return;}
   const response=await route.fetch();
   if(holdInitial&&section==='')noticeInitial();else noticeScript();
   const done=(async()=>{await gate;await route.fulfill({response});})();stalled.push(done);await done;
 });
 const filter=page.locator('[data-register-section-filter]');
 const check=async value=>{await page.waitForFunction(value=>document.querySelector('[data-register-section-filter]')?.value===value&&document.querySelector('[data-register-rows]')?.getAttribute('aria-busy')==='false',value);assert.equal(await filter.inputValue(),value);assert.equal(await page.locator('#tab-package').getAttribute('aria-selected'),'true');assert.equal(new URL(page.url()).searchParams.get('tab'),'package');};
 const review=()=>page.getByRole('tab',{name:'Review & Export',exact:true}).click();
 const checklist=value=>page.locator('#completion-review a[data-case-target="readiness-'+value+'"]').click();
 await page.goto(base+'/cases/1?tab=review');await initialSeen;
 await page.evaluate(()=>window.packageNavigationMarker='same mounted workspace');
 await checklist('scripts');await check('scripts');assert.equal(new URL(page.url()).hash,'#readiness-scripts');
 assert.equal(await page.evaluate(()=>window.packageNavigationMarker),'same mounted workspace');
 holdInitial=false;releaseInitial();await Promise.all(stalled);await check('scripts');
 await review();await checklist('signatures');await check('signatures');
 await page.goBack();assert.equal(new URL(page.url()).searchParams.get('tab'),'review');
 await page.goBack();await check('scripts');await page.goForward();await page.goForward();await check('signatures');
 await filter.selectOption('supporting');await check('supporting');assert.equal(new URL(page.url()).hash,'#readiness-supporting');
 await page.locator('#readiness-scripts').click();await check('scripts');await page.goBack();await check('supporting');await page.goBack();await check('signatures');
 assert.equal(await page.evaluate(()=>window.packageNavigationMarker),'same mounted workspace');
 await page.goto(base+'/cases/1?tab=package#readiness-mappings');await check('mappings');await page.reload();await check('mappings');
 await page.goto(base+'/cases/1?tab=package#readiness-not-a-section');await check('');
 await page.goto(base+'/cases/1?tab=package');await check('');
 await page.goto(base+'/cases/1#readiness-samples');await check('samples');
 await page.evaluate(()=>{location.hash='readiness-supporting';});await check('supporting');
 await review();holdScripts=true;let releaseScripts;scriptGate=new Promise(resolve=>releaseScripts=resolve);const scriptSeen=new Promise(resolve=>noticeScript=resolve);
 await checklist('scripts');await scriptSeen;
 assert.equal(await filter.inputValue(),'scripts');assert.match(await page.locator('[data-register-section-title]').innerText(),/^Scripts/);
 await review();await checklist('signatures');await check('signatures');holdScripts=false;releaseScripts();await Promise.all(stalled);await check('signatures');
 // Refreshed checklist nodes must retain in-app routing.
 await page.evaluate(()=>{const panel=document.getElementById('panel-review');panel.innerHTML=panel.innerHTML;});
 await review();await checklist('scripts');await check('scripts');
 // History cancellation must preserve a queued draft and its accepted section URL.
 await page.locator('[data-register-upload]').click();await page.locator('[data-register-files]').setInputFiles({name:'unsent.py',mimeType:'text/plain',buffer:Buffer.from('print(1)')});
 page.once('dialog',dialog=>dialog.dismiss());await page.goBack();
 assert.equal(await page.locator('.register-upload').evaluate(dialog=>dialog.open),true);assert.equal(new URL(page.url()).hash,'#readiness-scripts');assert.equal(await filter.inputValue(),'scripts');
 page.once('dialog',dialog=>dialog.accept());await page.locator('[data-register-upload-close]').click();
 assert.deepEqual(errors,[]);console.log('PASS: checklist routing on first mounted navigation, different sections, late responses, direct/refresh/hash links, missing/invalid fallback, shared section controls, Back/Forward, refreshed links, and unsaved queue protection.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
