const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-case-start-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8823';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8823'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/cases/new');
 await page.locator('#create-owner-help').filter({hasText:'An active owner is required'}).waitFor();
 assert.equal(await page.locator('[name=owner_id]').inputValue(),'');
 await page.locator('#case-name').fill('Unassigned start regression');
 await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);
 const casePath=new URL(page.url()).pathname,start=page.getByRole('button',{name:'Start analysis',exact:true});
 assert.ok(await start.isDisabled());assert.equal(await start.getAttribute('aria-describedby'),'stage-owner-required');
 await page.locator('#stage-owner-required').getByRole('link',{name:'Case details',exact:true}).click();
 await page.waitForURL(/tab=workbench#case-details$/);assert.ok(await page.locator('#case-details').evaluate(el=>el.open));
 const owner=page.locator('#case-owner');const selected=await owner.locator('option').filter({hasText:'editor-test'}).getAttribute('value');
 await owner.selectOption(selected);
 const assignment=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===casePath+'/owner');
 await page.getByRole('button',{name:'Save assigned owner',exact:true}).click();assert.equal((await assignment).status(),302);
 await page.waitForFunction(()=>!document.querySelector('.stage-panel form[action$="/stage"] button').disabled);
 assert.ok(await start.isEnabled());assert.equal(await page.locator('#stage-owner-required').count(),0);
 const started=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===casePath+'/stage');
 await start.click();assert.equal((await started).status(),302);
 await page.locator('#case-heading .badge').filter({hasText:'Malware Analysis'}).waitFor();assert.ok(await page.locator('#tab-notes').isEnabled());
 // Selecting an owner during creation makes Start analysis available immediately.
 await page.goto(base+'/cases/new');await page.locator('#case-name').fill('Assigned start regression');await page.locator('[name=owner_id]').selectOption(selected);
 await Promise.all([page.waitForURL(/\/cases\/\d+$/),page.getByRole('button',{name:'Create case & MIP',exact:true}).click()]);
 assert.ok(await start.isEnabled());await start.click();await page.locator('#case-heading .badge').filter({hasText:'Malware Analysis'}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('PASS: explicit unassigned-owner guidance, accessible start gate and assignment link, saved ownership unlocks Start analysis, successful stage transition, and owner selected at creation.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
