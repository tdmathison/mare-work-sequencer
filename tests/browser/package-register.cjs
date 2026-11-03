const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-register-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8816';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8816'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/cases/1?tab=package');
 const root=page.locator('[data-artifact-register]');await root.locator('[data-register-rows]').waitFor();
 const section=root.locator('[data-register-section-filter]');await section.selectOption('scripts');await root.locator('[data-register-section-title]').filter({hasText:'Empty'}).waitFor();
 const na=root.getByLabel('Not applicable — no content expected.',{exact:true});await na.check();await root.locator('[data-register-section-title]').filter({hasText:'Not applicable'}).waitFor();
 await root.getByRole('button',{name:'Upload files',exact:true}).first().click();const queue=page.locator('.register-upload');
 await queue.locator('[data-register-files]').setInputFiles([{name:'test.py',mimeType:'text/plain',buffer:Buffer.from('print(42)')},{name:'test.py',mimeType:'text/plain',buffer:Buffer.from('do not overwrite')}]);
 assert.equal(await queue.locator('.register-queue-row').count(),2);await queue.getByRole('button',{name:'Upload queue',exact:true}).click();await queue.locator('[data-register-upload-status]').filter({hasText:'Queue finished'}).waitFor();
 assert.match(await queue.locator('.register-queue-row').first().innerText(),/Saved as scripts\/test.py/);assert.match(await queue.locator('.register-queue-row').last().innerText(),/already exists/);
 await queue.locator('.register-queue-row').last().getByLabel('Queued filename',{exact:true}).fill('other.py');await queue.getByRole('button',{name:'Upload queue',exact:true}).click();await queue.locator('.register-queue-row').last().getByText('Saved as scripts/other.py',{exact:true}).waitFor();await queue.getByRole('button',{name:'Close',exact:true}).click();
 await root.locator('[data-register-section-title]').filter({hasText:'Populated'}).waitFor();assert.ok(await na.isHidden());assert.equal(await root.locator('[data-register-rows] tr').count(),2);
 const artifact=root.locator('[data-register-rows] tr').filter({hasText:'scripts/test.py'});await artifact.getByRole('button',{name:'Edit',exact:true}).click();const editor=page.locator('.register-editor');await editor.locator('[data-register-editor-text]').fill('print(43)');
 await context.request.get(base+'/cases/1/package-register');assert.equal(await editor.locator('[data-register-editor-text]').inputValue(),'print(43)');await editor.getByRole('button',{name:'Save',exact:true}).click();await editor.locator('[data-register-editor-status]').filter({hasText:'Saved.'}).waitFor();await editor.getByRole('button',{name:'Cancel',exact:true}).click();
 for(const width of [1440,390]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/mws-artifact-register-'+width+'.png',animations:'disabled'});}
 await root.getByLabel('Select visible artifacts',{exact:true}).check();page.once('dialog',d=>d.accept());await root.getByRole('button',{name:'Remove selected',exact:true}).click();await root.locator('[data-register-section-title]').filter({hasText:'Empty'}).waitFor();
 assert.equal(await na.isChecked(),false);
 assert.deepEqual(errors,[]);console.log('PASS: automatic Empty/NA/Populated transitions, mixed-success queue and retry, no overwrite, editor save/retained buffer, bulk removal, 390/1440px layout.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
