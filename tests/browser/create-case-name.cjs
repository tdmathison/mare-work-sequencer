const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-create-name-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8821';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8821'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 const name=page.locator('#case-name');
 await page.goto(base+'/cases/new');const prefix=await name.inputValue();assert.match(prefix,/^\d{8}: $/);
 assert.deepEqual(await name.evaluate(e=>[document.activeElement===e,e.selectionStart,e.selectionEnd]),[true,prefix.length,prefix.length]);
 await page.keyboard.type('My case');assert.equal(await name.inputValue(),prefix+'My case');
 await name.evaluate(e=>e.setSelectionRange(4,4));await page.evaluate(()=>document.dispatchEvent(new Event('DOMContentLoaded')));assert.deepEqual(await name.evaluate(e=>[e.value,e.selectionStart,e.selectionEnd]),[prefix+'My case',4,4]);
 await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);assert.equal(await page.locator('h1').textContent(),prefix+'My case');
 // Validation retries return the supplied text and do not re-run initialization.
 await page.goto(base+'/cases/new');await name.fill(prefix+'Validation retry ');await page.locator('[name=external_system]').selectOption('JIRA');
 const rejected=page.waitForResponse(r=>new URL(r.url()).pathname==='/cases'&&r.request().method()==='POST');await page.getByRole('button',{name:'Create case & MIP',exact:true}).click();assert.equal((await rejected).status(),400);assert.equal(await name.inputValue(),prefix+'Validation retry ');
 await name.focus();await name.evaluate(e=>e.setSelectionRange(3,3));await page.evaluate(()=>document.dispatchEvent(new Event('DOMContentLoaded')));assert.deepEqual(await name.evaluate(e=>[e.value,e.selectionStart,e.selectionEnd]),[prefix+'Validation retry ',3,3]);
 await page.locator('[name=external_system]').selectOption('');await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);assert.equal(await page.locator('h1').textContent(),prefix+'Validation retry ');
 await page.goto(base+'/cases/new');await name.fill('Custom name without a date');await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);assert.equal(await page.locator('h1').textContent(),'Custom name without a date');
 // Submit the untouched default: its trailing space must not trigger another prefix.
 await page.goto(base+'/cases/new');const untouched=await name.inputValue();await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);assert.equal(await page.locator('h1').textContent(),untouched);
 // Model restoration before the normal DOM-ready focus handler.
 await page.addInitScript(()=>document.addEventListener('DOMContentLoaded',()=>{const e=document.getElementById('case-name');if(e){e.value='Restored custom value';document.querySelector('[name=description]').focus();}},{once:true}));
 await page.goto(base+'/cases/new');assert.equal(await name.inputValue(),'Restored custom value');assert.equal(await page.locator('[name=description]').evaluate(e=>document.activeElement===e),true);
 assert.deepEqual(errors,[]);console.log('PASS: one initial prefix, caret after trailing space, immediate typing and exact save, repeated initialization, validation/retry, custom names, untouched prefix submission, and restored content/focus.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
