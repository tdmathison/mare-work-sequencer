const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-case-tabs-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8822';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8822'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/cases/1?tab=review');
 const root=page.locator('[data-task-collections]'), review=page.locator('#completion-review');
 const csrf=await root.getAttribute('data-csrf'), taskURL=base+'/task-workspace/cases/1';
 const tab=async name=>{await page.locator('#tab-'+name).click();await page.waitForFunction(()=>!document.querySelector('#case-data-status').textContent.startsWith('Refreshing'));};
 const post=async (url,payload)=>{const r=await page.request.post(url,{form:{csrf,payload:JSON.stringify(payload)}});assert.ok(r.ok(),await r.text());return r.json();};
 const create=async name=>{const r=await page.request.post(base+'/cases/1/tasks',{form:{csrf,name,priority:'Normal'}});assert.ok(r.ok());};
 const contains=async text=>{await review.locator('li').filter({hasText:text}).waitFor({state:'attached'});};
 const absent=async text=>{await page.waitForFunction(text=>!document.querySelector('#completion-review').textContent.includes(text),text);};
 await contains('Existing task');
 const required=await review.locator('.badge').innerText();
 await page.evaluate(()=>window.caseDocumentIdentity=crypto.randomUUID());const identity=await page.evaluate(()=>window.caseDocumentIdentity);
 await tab('tasks');page.once('dialog',d=>d.accept());await root.getByRole('button',{name:'Delete task',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('[data-task-groups] .task-row'));
 // Both hidden and visible checklists are reconciled immediately after a save.
 await absent('Existing task');await tab('review');assert.equal(await review.locator('.badge').innerText(),required);
 assert.equal(await review.locator('li').filter({hasText:'Open task:'}).count(),0);
 // Creation keeps the same mounted document and existing editors.
 await tab('tasks');await root.getByRole('button',{name:'Add Task',exact:true}).click();
 await page.locator('#add-task-dialog [name=name]').fill('New task A');await page.locator('#add-task-dialog').getByRole('button',{name:'Create task',exact:true}).click();
 await root.locator('.task-row').filter({hasText:'New task A'}).waitFor();assert.equal(await page.evaluate(()=>window.caseDocumentIdentity),identity);
 await contains('New task A');
 await create('New task B');await tab('review');await contains('New task B');await tab('tasks');
 const rowA=root.locator('.task-row').filter({hasText:'New task A'});
 await rowA.locator('select').selectOption('Completed');await absent('New task A');await contains('New task B');
 // New rows loaded asynchronously have fully functional task editors.
 await rowA.getByRole('button',{name:'Edit task',exact:true}).click();const edit=page.locator('dialog[open].task-workspace-dialog');
 assert.equal(await edit.locator('[name=state]').inputValue(),'Completed');await edit.locator('[data-close-task-dialog]').click();
 // Partial deletion preserves other task advisories.
 page.once('dialog',d=>d.accept());await rowA.getByRole('button',{name:'Delete task',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('[data-task-groups] .task-row').length===1);await tab('review');await contains('New task B');
 // Group deletion removes all copied tasks and keeps the remaining custom task.
 const collections=(await (await page.request.get(base+'/task-workspace/collections')).json()).collections;
 const collection=collections.find(c=>c.origin==='core');
 await post(taskURL+'/collections/'+collection.id+'/apply',{revision:collection.revision,template_ids:collection.tasks.slice(0,2).map(t=>t.id),mode:'copy',request_key:crypto.randomUUID().replaceAll('-','')});
 await tab('tasks');assert.equal(await root.locator('.task-row').count(),3);
 page.once('dialog',d=>d.accept());await root.getByRole('button',{name:'Remove collection from case',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('[data-task-groups] .task-row').length===1);
 await tab('review');assert.equal(await review.locator('li').filter({hasText:'Open task:'}).count(),1);
 // In-app links and browser history activate the already-mounted Review tab.
 await tab('tasks');await create('History task');await page.evaluate(()=>window.MareCaseNavigation.navigate('?tab=review#completion-review'));await contains('History task');
 await page.goBack();await page.waitForFunction(()=>!document.querySelector('#panel-tasks').hidden);
 await create('Forward task');await page.goForward();await contains('Forward task');
 const direct=await context.newPage();await direct.goto(base+'/cases/1?tab=review');await direct.locator('#completion-review li').filter({hasText:'Forward task'}).waitFor();await direct.close();
 // Notes draft and report editor state/selection survive activation revalidation.
 await tab('notes');await page.evaluate(()=>{const area=document.querySelector('[data-note-composer] textarea');window.MareEditors.setValue(area,'Unsaved notebook draft');area.dispatchEvent(new Event('input',{bubbles:true}));window.notebookEditor=window.MareEditors.get(area);});
 await tab('review');await tab('notes');assert.equal(await page.evaluate(()=>window.notebookEditor.getValue()),'Unsaved notebook draft');
 await tab('report');await page.evaluate(()=>{const area=document.querySelector('#manual-report-form .markdown-source') || document.querySelector('#panel-report .markdown-source');window.reportArea=area;window.reportEditor=window.MareEditors.get(area);window.reportEditor.setValue('Local report draft');window.reportEditor.setSelection(2,7);window.reportSelection=window.reportEditor.selection();area.dispatchEvent(new Event('input',{bubbles:true}));});
 await create('Draft task');await tab('review');await contains('Draft task');await tab('report');assert.equal(await page.evaluate(()=>window.reportEditor.getValue()),'Local report draft');assert.ok(await page.evaluate(()=>window.reportEditor===window.MareEditors.get(window.reportArea)));assert.deepEqual(await page.evaluate(()=>window.reportEditor.selection()),await page.evaluate(()=>window.reportSelection));
 const reportState=await(await page.request.get(base+'/cases/1/report-data')).json();
 const remoteReport=await page.request.post(base+'/cases/1/report-sections',{form:{csrf,ajax:'1',...reportState.sections,[await page.evaluate(()=>window.reportArea.name)]:'Report changed by another client'}});assert.ok(remoteReport.ok());
 await tab('review');await tab('report');assert.equal(await page.evaluate(()=>window.reportEditor.getValue()),'Local report draft');await page.locator('#report-save-status').filter({hasText:'autosave is paused'}).waitFor();
 // References maintain dirty cell DOM, selection and revision on remote changes.
 await tab('references');await page.locator('#add-reference').click();const cell=page.locator('#reference-table tbody tr').last().locator('[data-column="0"]');await cell.fill('https://local.example');
 await page.evaluate(()=>window.referenceCell=document.querySelector('#reference-table tbody tr:last-child td[data-column="0"]'));
 const refs=await(await page.request.get(base+'/cases/1/references')).json();
 const savedRefs=await page.request.post(base+'/cases/1/references',{form:{csrf,revision:refs.revision,rows:JSON.stringify([['https://remote.example','Saved elsewhere']])}});assert.ok(savedRefs.ok());
 await tab('review');await tab('references');assert.equal(await cell.innerText(),'https://local.example');assert.ok(await page.evaluate(()=>window.referenceCell===document.querySelector('#reference-table tbody tr:last-child td[data-column="0"]')));
 await page.locator('#reference-status').filter({hasText:'changed in another client'}).waitFor();
 // Metadata refresh updates headings but keeps unsaved Case-details input.
 await tab('workbench');const caseName=page.locator('#case-details input[name=name]');await caseName.fill('Unsaved Case name');
 const details=await page.request.post(base+'/cases/1',{form:{csrf,name:'Server Case name',description:'Saved elsewhere',external_system:'',external_number:''}});assert.ok(details.ok());
 await tab('review');await tab('workbench');assert.equal(await caseName.inputValue(),'Unsaved Case name');assert.equal(await page.locator('#case-heading h1').innerText(),'Server Case name');
 // Deterministic stale response: capture an old checklist, then release it only
 // after a newer activation has rendered another client's saved task.
 let release, captured;const held=new Promise(resolve=>release=resolve),ready=new Promise(resolve=>captured=resolve);let first=true;
 await page.route(base+'/cases/1',async route=>{if(route.request().method()!=='GET'||!first)return route.continue();first=false;const response=await route.fetch();const body=await response.text();captured();await held;await route.fulfill({response,body}).catch(()=>{});});
 await page.locator('#tab-review').click();await ready;await create('Newest task after old response');await tab('tasks');await tab('review');await contains('Newest task after old response');release();await page.unroute(base+'/cases/1');
 await contains('Newest task after old response');assert.equal(await page.evaluate(()=>window.caseDocumentIdentity),identity);
 // Useful error state and explicit retry; drafts remain intact throughout.
 await page.route(base+'/cases/1',route=>route.fulfill({status:503,body:'Unavailable'}));await page.locator('#tab-notes').click();await page.locator('#case-data-status').filter({hasText:'out of date'}).waitFor();assert.equal(await page.evaluate(()=>window.notebookEditor.getValue()),'Unsaved notebook draft');await page.unroute(base+'/cases/1');await page.locator('#case-data-status button').click();await page.waitForFunction(()=>!document.querySelector('#case-data-status').textContent.startsWith('Refreshing')&&!document.querySelector('#case-data-status').textContent.includes('out of date'));
 assert.deepEqual(errors,[]);
 console.log('PASS: last/partial/group deletion, status and creation, immediate dependent checklists, mounted tabs, other-client changes, links/history/direct URLs, retained notebook/report/reference drafts and editor DOM, out-of-order responses, and retry feedback.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
