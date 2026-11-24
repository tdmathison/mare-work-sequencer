const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-autosave-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8836';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8836'},stdio:['ignore','ignore','pipe']});
let browser,logs='';server.stderr.on('data',d=>logs+=d);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch{if(i>100||server.exitCode!==null)throw Error(logs);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/settings/general');const csrf=await page.locator('[name=csrf]').first().inputValue();
 const preference=async enabled=>{const r=await page.request.post(base+'/account/autosave',{form:{csrf,autosave_minutes:'1',autosave_enabled:enabled?'1':'0'}});assert.ok(r.ok());};
 await page.getByLabel('Autosave for my account').uncheck();await page.getByLabel('Autosave interval (minutes)').fill('1');
 await Promise.all([page.waitForURL(base+'/settings/general'),page.getByRole('button',{name:'Save autosave settings',exact:true}).click()]);
 assert.equal((await(await page.request.get(base+'/account/autosave')).json()).enabled,false);
 await page.clock.install();await page.clock.pauseAt(new Date(Date.now()+1000));
 await page.goto(base+'/cases/1?tab=report');await page.waitForFunction(()=>window.MareReport&&document.querySelector('#save-sections')&&!document.querySelector('#save-sections').disabled);
 await page.evaluate(()=>window.MareAutosave.synchronize());assert.equal(await page.evaluate(()=>MareAutosave.enabled),false);
 const posts=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.startsWith('/cases/1'))posts.push({url:new URL(r.url()).pathname,automatic:/(?:name="automatic"\r?\n\r?\n1|(?:^|&)automatic=1(?:&|$))/.test(r.postData()||'')});});
 await page.evaluate(()=>{
  const area=document.querySelector('#manual-report-form .markdown-source')||document.querySelector('#panel-report .markdown-source');
  const mapping=document.querySelector('#mitre-attack-markdown');MareEditors.get(mapping).setValue('Unsent mapping draft');mapping.dispatchEvent(new Event('input',{bubbles:true}));
  window.reportDraftArea=area;const editor=MareEditors.get(area);editor.setValue('Unsent account preference draft');area.dispatchEvent(new Event('input',{bubbles:true}));
 });
 const tab=async name=>{await page.locator('#tab-'+name).click();await page.waitForFunction(()=>!document.querySelector('#case-data-status').hasAttribute('aria-busy'));};
 await tab('references');await page.locator('#add-reference').click();await page.locator('#reference-table tbody tr').last().locator('[data-column="0"]').fill('https://autosave.example');
 await tab('indicators');await page.locator('#add-indicator-section').click();await page.locator('#indicator-section-form [name=title]').fill('Autosave test section');await page.locator('#indicator-section-form button[type=submit]').click();
 await tab('notes');await page.evaluate(()=>{const area=document.querySelector('[data-note-composer] textarea');MareEditors.get(area).setValue('Private unsaved note');area.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.clock.fastForward(120000);assert.equal(posts.length,0,'disabled autosave must prevent every automatic POST');
 // Explicit Save still works for interval-based editors, including mappings.
 for(const [name,selector] of [['references','#save-references','#reference-status'],['indicators','#save-indicators','#indicator-status'],['report','#save-sections','#report-save-status'],['report','#save-mitre-mappings','#mitre-mapping-status']]){
  await tab(name);const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/cases/1/'));await page.locator(selector).click();assert.ok((await response).ok());
 }
 assert.ok(posts.length>=4);assert.ok(posts.every(p=>!p.automatic));
 await page.evaluate(()=>{const area=window.reportDraftArea;const editor=MareEditors.get(area);editor.setValue('Draft and caret stay here');area.dispatchEvent(new Event('input',{bubbles:true}));editor.setSelection(3,8);window.savedSelection=editor.selection();window.savedEditor=editor;const mapping=document.querySelector('#mitre-attack-markdown');MareEditors.get(mapping).setValue('Resumed mapping draft');mapping.dispatchEvent(new Event('input',{bubbles:true}));});
 await preference(true);await page.evaluate(()=>MareAutosave.synchronize());
 assert.deepEqual(await page.evaluate(()=>MareEditors.get(window.reportDraftArea).selection()),await page.evaluate(()=>window.savedSelection));assert.equal(await page.evaluate(()=>MareEditors.get(window.reportDraftArea)===window.savedEditor),true);
 const count=posts.length;await page.clock.fastForward(59000);assert.equal(posts.length,count,'enabling must wait for the interval');
 const completed=Promise.all(['/report-sections','/indicators','/references','/mitre-mappings'].map(suffix=>page.waitForResponse(r=>r.url().endsWith(suffix)&&r.request().method()==='POST')));
 await page.clock.fastForward(2000);await completed;
 await page.waitForFunction(()=>document.querySelector('#save-sections-countdown').textContent.startsWith('Autosave in'));
 // Let network-driven save completions settle, without advancing the next interval.

 for(const suffix of ['/report-sections','/indicators','/references'])assert.ok(posts.slice(count).some(p=>p.url.endsWith(suffix)&&p.automatic),'resumed '+suffix);
 assert.ok(posts.slice(count).some(p=>p.url.endsWith('/mitre-mappings')),'MITRE mappings resume through their existing automatic handler');
 await tab('workbench');await page.locator('[data-impact-panel]').evaluate(e=>e.open=true);
 await page.locator('[name=impact_confirmed]').check();
 const outcome=await page.locator('#impact-type option').nth(1).getAttribute('value');await page.locator('#impact-type').selectOption(outcome);
 await page.locator('#impact-summary').fill('Queued impact draft');
 await preference(false);await page.evaluate(()=>MareAutosave.synchronize());
 const before=posts.length;await page.clock.fastForward(120000);assert.equal(posts.length,before);
 assert.equal(await page.locator('#impact-summary').inputValue(),'Queued impact draft');
 const impactSaved=page.waitForResponse(r=>r.url()===base+'/cases/1'&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Save impact',exact:true}).click();assert.ok((await impactSaved).ok());
 // A reopened document receives the persisted preference; closed Cases stay locked.
 const changed=spawnSync('.venv/bin/python',['-c','import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("UPDATE cases SET stage=3 WHERE id=1");c.commit()',path.join(temporary,'workflow.sqlite3')]);assert.equal(changed.status,0);
 await page.evaluate(()=>{const area=window.reportDraftArea;MareEditors.get(area).setValue('Still unsaved while autosave is disabled');area.dispatchEvent(new Event('input',{bubbles:true}));});
 const dialogs=[];page.on('dialog',d=>{dialogs.push(d.type());d.accept();});await page.reload();assert.ok(dialogs.includes('beforeunload'),'unsaved-change warning must survive disabling');assert.equal(await page.evaluate(()=>MareAutosave.enabled),false);assert.ok(await page.locator('#save-sections').isDisabled());assert.ok(await page.locator('#save-indicators').isDisabled());assert.ok(await page.locator('#save-references').isDisabled());
 await preference(true);await page.evaluate(async()=>{await Promise.all([MareIndicators.refresh(),MareReferences.refresh(),MareReport.refresh()]);await MareAutosave.synchronize();});
 const closedPosts=posts.length;await page.clock.fastForward(61000);assert.equal(posts.length,closedPosts,'enabled autosave must honor closed-Case permissions');
 assert.deepEqual(errors,[]);console.log('PASS: real Report/Indicators/References manual and automatic saves, Notes drafts, disabled requests, resume interval, caret/editor identity, persisted preference and closed Cases');
})().catch(e=>{console.error(logs.slice(-2500));console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
