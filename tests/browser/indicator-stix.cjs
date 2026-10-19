/* Real indicator editor/unified import dialog against isolated Flask state. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-indicator-stix-'));
const port=8788,base=`http://127.0.0.1:${port}`;
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let log='',browser;server.stderr.on('data',data=>log+=data);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(error){if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}});page.setDefaultTimeout(15000);
 const errors=[],external=[];page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(/^https?:/.test(request.url())&&!request.url().startsWith(base+'/'))external.push(request.url());});
 page.on('dialog',dialog=>dialog.accept());
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/cases/1?tab=indicators');
 async function checkDisclosure(){
  for(const field of await page.locator('input[list="indicator-type-options"]').all()){
   const appearance=await field.evaluate(el=>({background:getComputedStyle(el).backgroundImage,nativeOpacity:getComputedStyle(el,'::-webkit-calendar-picker-indicator').opacity,before:getComputedStyle(el,'::before').content,after:getComputedStyle(el,'::after').content}));
   assert.ok(appearance.background.startsWith('url('));assert.ok(await page.evaluate(()=>[...document.styleSheets].filter(sheet=>sheet.href?.endsWith('/static/mare.css')).some(sheet=>[...sheet.cssRules].some(rule=>rule.selectorText==='input.indicator-type-input::-webkit-calendar-picker-indicator'&&rule.style.opacity==='0'))));
   assert.ok(['none','normal'].includes(appearance.before));assert.ok(['none','normal'].includes(appearance.after));
  }
 }
 const workspace=page.locator('#indicator-workspace'),sections=page.locator('.indicator-section');
 await workspace.getByRole('button',{name:'Add row',exact:true}).click();
 const type=sections.first().getByRole('combobox');
 assert.equal(await sections.first().locator('[data-validation="blank"]').count(),1);
 assert.equal(await sections.first().locator('.indicator-validation-icon').count(),0);
 await checkDisclosure();
 await type.fill('SHA256');await type.press('Tab');
 await page.keyboard.type('a'.repeat(64));await page.keyboard.press('Tab');await page.keyboard.type('Original description');
 await page.locator('#save-indicators').click();await page.waitForFunction(()=>document.querySelector('#indicator-status').textContent.includes('CSV and STIX'));
 assert.equal(await sections.first().getByRole('combobox').inputValue(),'sha256');
 assert.equal(await sections.first().getByRole('img',{name:'Valid indicator'}).count(),1);
 assert.equal(await workspace.locator('.indicator-type-help,.indicator-export-info,.indicator-correction').count(),0);
 const validHeight=await sections.first().locator('tbody tr').first().evaluate(el=>el.getBoundingClientRect().height);
 assert.ok(await page.locator('#indicator-type-options option[value="sha256"]').count());
 await checkDisclosure();
 assert.ok(await page.locator('#indicator-type-options option[value="mobile-application-id"]').count());
 assert.ok(await page.locator('#indicator-type-options option[value="software"]').count());
 await page.locator('#add-indicator-section').click();await page.locator('#indicator-section-form [name=title]').fill('Imported infrastructure');await page.locator('#indicator-section-form [name=description]').fill('Preserved section context');await page.locator('#indicator-section-form button[type=submit]').click();
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();
 const dialog=page.locator('#indicator-import-dialog');
 assert.equal(await dialog.getByRole('tab',{name:'CSV',exact:true}).getAttribute('aria-selected'),'true');
 const target=await page.locator('#indicator-import-target').textContent();
 await dialog.getByRole('tab',{name:'STIX',exact:true}).focus();await page.keyboard.press('Enter');
 assert.equal(await dialog.getByRole('tab',{name:'STIX',exact:true}).getAttribute('aria-selected'),'true');
 await page.keyboard.press('ArrowLeft');assert.equal(await dialog.getByRole('tab',{name:'CSV',exact:true}).getAttribute('aria-selected'),'true');assert.equal(await page.locator('#indicator-import-target').textContent(),target);
 await page.locator('#indicator-csv-text').fill('Type,Value,Description\nSHA-256,'+'a'.repeat(64)+',Payload\nIP,192.0.2.1,Observed');
 const previewResponse=page.waitForResponse(response=>response.url().endsWith('/indicators/import/preview'));
 await page.locator('#preview-indicator-import').click();const previewData=await(await previewResponse).json();await page.locator('#indicator-import-status').filter({hasText:'1 need correction'}).waitFor();
 assert.equal(await page.locator('.indicator-preview-row').count(),2);
 await page.locator('.indicator-preview-row').nth(1).getByRole('combobox').fill('ip-dst');
 await page.locator('#confirm-indicator-import').click();await page.waitForFunction(()=>!document.querySelector('#indicator-import-dialog').open);
 await checkDisclosure();
 assert.equal(await sections.first().locator('tbody tr').count(),1);assert.equal(await sections.nth(1).locator('tbody tr').count(),2);
 assert.equal(await sections.nth(1).locator('.indicator-section-description').textContent(),'Preserved section context');
 const downloaded=page.waitForEvent('download');await page.locator('#download-indicator-stix').click();const file=await downloaded;
 const raw=fs.readFileSync(await file.path());const bundle=JSON.parse(raw);
 assert.equal(bundle.objects.filter(item=>item.type==='indicator').length,3);
 assert.ok(bundle.objects.some(item=>item.type==='grouping'&&item.name==='Imported infrastructure'));
 // Own export reimport is additive and skips canonical destination duplicates.
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();await dialog.getByRole('tab',{name:'STIX',exact:true}).click();
 await page.locator('#indicator-stix-file').setInputFiles({name:'export.stix',mimeType:'application/json',buffer:raw});
 await page.locator('#preview-indicator-import').click();await page.locator('#indicator-import-status').filter({hasText:'3 exact destination duplicates'}).waitFor();
 await page.locator('#confirm-indicator-import').click();await page.waitForFunction(()=>!document.querySelector('#indicator-import-dialog').open);
 assert.equal(await sections.nth(1).locator('tbody tr').count(),2);
 assert.ok((await page.locator('#indicator-status').textContent()).includes('skipped 3 duplicates'));
 // A new upload clears old previews and cannot apply prior validation state.
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();await dialog.getByRole('tab',{name:'STIX',exact:true}).click();
 const complex={...bundle.objects.find(item=>item.type==='indicator'),pattern:"[domain-name:value = 'a.example' OR domain-name:value = 'b.example']"};
 await page.locator('#indicator-stix-file').setInputFiles({name:'complex.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(complex))});
 await page.locator('#preview-indicator-import').click();await page.locator('#indicator-import-status').filter({hasText:'1 unsupported/skipped'}).waitFor();
 assert.equal(await page.locator('#confirm-indicator-import').isDisabled(),true);
 assert.ok((await page.locator('#indicator-import-preview').textContent()).includes('cannot be represented faithfully'));
 await page.locator('#indicator-stix-file').setInputFiles({name:'malformed.json',mimeType:'application/json',buffer:Buffer.from('not JSON')});
 assert.equal(await page.locator('#indicator-import-preview').textContent(),'');
 await page.locator('#preview-indicator-import').click();await page.locator('#indicator-import-status').filter({hasText:'valid UTF-8 STIX'}).waitFor();
 assert.equal(await page.locator('#confirm-indicator-import').isDisabled(),true);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.ok(await dialog.isVisible());
 await page.keyboard.press('Escape');await page.setViewportSize({width:1366,height:900});
 // Real timer-driven autosave must keep live cell bindings and newer typing.
 const beforeAuto=await (await page.request.get(base+'/cases/1/indicators')).json();
 const originalId=beforeAuto.sections[0].row_meta[0].id;
 await sections.first().locator('td[data-column="2"]').fill('Autosave snapshot');
 assert.equal(await sections.first().locator('[data-validation="pending"]').count(),1);
 assert.equal(await sections.first().locator('.indicator-validation-icon').count(),0);
 let release;const gate=new Promise(resolve=>release=resolve);
 await page.route('**/cases/1/indicators',async route=>{if(route.request().method()==='POST'&&(route.request().postData()||'').includes('name="automatic"'))await gate;await route.continue();});
 const automatic=page.waitForRequest(request=>request.url().endsWith('/indicators')&&request.method()==='POST'&&(request.postData()||'').includes('name="automatic"'));
 await page.evaluate(()=>{window.indicatorDateNow=Date.now;Date.now=()=>window.indicatorDateNow()+6*60000;});
 await automatic;
 await sections.first().locator('td[data-column="2"]').fill('Newer edit during autosave');
 const completed=page.waitForResponse(response=>response.url().endsWith('/indicators')&&response.request().method()==='POST');release();await completed;
 await page.locator('#indicator-status').filter({hasText:'newer changes pending'}).waitFor();
 assert.equal(await sections.first().locator('[data-validation="pending"]').count(),1);
 assert.equal(await sections.first().locator('.indicator-validation-icon').count(),0);
 await page.waitForFunction(()=>!document.querySelector('#download-indicator-stix').disabled);
 assert.equal(await sections.first().locator('td[data-column="2"]').textContent(),'Newer edit during autosave');
 await page.unroute('**/cases/1/indicators');await page.evaluate(()=>{Date.now=window.indicatorDateNow;});
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 const afterAuto=await(await page.request.get(base+'/cases/1/indicators')).json();
 assert.equal(afterAuto.sections[0].row_meta[0].id,originalId);assert.equal(afterAuto.sections[0].rows[0][2],'Newer edit during autosave');
 // An unfinished row saves as a draft and cannot download the prior STIX file.
 await sections.first().getByRole('combobox').fill('IP');await page.evaluate(()=>{Date.now=()=>window.indicatorDateNow()+6*60000;});await page.locator('#indicator-status').filter({hasText:'STIX unavailable'}).waitFor();
 await page.evaluate(()=>{Date.now=window.indicatorDateNow;});
 const invalid=sections.first().locator('[data-validation="invalid"] button');
 assert.equal(await invalid.count(),1);
 assert.ok((await invalid.getAttribute('aria-label')).startsWith('Invalid indicator:'));
 const tip=page.locator('#indicator-validation-error');
 await invalid.hover();await tip.waitFor({state:'visible'});
 assert.ok((await tip.textContent()).length>10);
 await invalid.focus();assert.equal(await invalid.getAttribute('aria-expanded'),'true');
 await invalid.press('Escape');assert.equal(await tip.isVisible(),false);
 await invalid.press('Enter');assert.equal(await tip.isVisible(),true);
 await invalid.press('Tab');assert.equal(await tip.isVisible(),false);
 assert.equal(await sections.first().locator('td[data-column="1"]').evaluate(el=>el===document.activeElement),true);
 const invalidHeight=await sections.first().locator('tbody tr').first().evaluate(el=>el.getBoundingClientRect().height);
 assert.equal(invalidHeight,validHeight);
 await page.setViewportSize({width:390,height:844});
 await invalid.click();await tip.waitFor({state:'visible'});
 assert.ok(await tip.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}));
 await page.keyboard.press('Escape');await page.setViewportSize({width:1366,height:900});
 const saved=await page.request.get(base+'/cases/1/indicators/stix');assert.equal(saved.status(),409);
 // New software/package selectors use the same accessible control and retain dots.
 await sections.first().getByRole('combobox').fill('application');
 await sections.first().locator('td[data-column="1"]').fill('Example App');
 await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
 const packageRow=sections.first().locator('tbody tr').last();
 await packageRow.getByRole('combobox').fill('package-name');await packageRow.getByRole('combobox').press('Tab');await page.keyboard.type('com.example.app');
 await checkDisclosure();
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 assert.equal(await packageRow.getByRole('combobox').inputValue(),'mobile-application-id');await checkDisclosure();
 const softwareSaved=await(await page.request.get(base+'/cases/1/indicators')).json();
 assert.equal(softwareSaved.sections[0].rows.at(-1)[1],'com.example.app');
 assert.equal(softwareSaved.sections[0].rows[0][0],'software');
 // Full official catalog has one entry per canonical type, not alias copies.
 const options=await page.locator('#indicator-type-options option').evaluateAll(items=>items.map(item=>({value:item.value,label:item.label})));
 assert.equal(options.length,195);assert.equal(new Set(options.map(item=>item.value)).size,195);
 assert.ok(options.find(item=>item.value==='text').label.includes('unknown'));
 assert.ok(options.find(item=>item.value==='mobile-application-id').label.includes('Android'));
 for(const kind of ['text','comment','other','mobile-application-id','chrome-extension-id','edge-extension-id'])assert.ok(options.some(item=>item.value===kind));
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();
 await page.locator('#indicator-csv-text').fill('type,value,description\nMystery-artifact,"  Unicode 🦀\nsecond line https://evil.example  ",Evidence\n');
 const contextualPreviewResponse=page.waitForResponse(response=>response.url().endsWith('/indicators/import/preview'));
 await page.locator('#preview-indicator-import').click();const contextualPreviewData=await(await contextualPreviewResponse).json();await page.locator('#indicator-import-status').filter({hasText:'1 need correction'}).waitFor();
 const unknown=page.locator('.indicator-preview-row');
 assert.equal(await unknown.getByRole('combobox').inputValue(),'Mystery-artifact');
 const originalValue=await unknown.getByRole('textbox',{name:'Value',exact:true}).inputValue();
 await unknown.getByRole('button',{name:'Use other',exact:true}).click();
 assert.equal(await unknown.getByRole('combobox').inputValue(),'other');
 assert.equal(await unknown.getByRole('textbox',{name:'Value',exact:true}).inputValue(),originalValue);
 await page.locator('#confirm-indicator-import').click();await page.waitForFunction(()=>!document.querySelector('#indicator-import-dialog').open);
 const contextualSaved=await(await page.request.get(base+'/cases/1/indicators')).json();
 assert.equal(contextualSaved.sections[1].rows.at(-1)[1],contextualPreviewData.rows[0].row[1]);
 assert.equal(contextualSaved.sections[1].row_meta.at(-1).original_type,'Mystery-artifact');
 assert.ok(contextualSaved.stix.available);await checkDisclosure();
 // A valid former mapping gap is informational, never a correction error.
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();
 await page.locator('#indicator-csv-text').fill('type,value,description\nport,443,Traffic port\n');
 await page.locator('#preview-indicator-import').click();await page.locator('#indicator-import-status').filter({hasText:'1 supported rows ready'}).waitFor();
 await page.locator('#confirm-indicator-import').click();await page.waitForFunction(()=>!document.querySelector('#indicator-import-dialog').open);
 const portRow=sections.nth(1).locator('tbody tr').last();
 assert.equal(await portRow.locator('[data-validation="valid"]').count(),1);
 assert.equal(await portRow.getByRole('img',{name:'Valid indicator'}).count(),1);
 assert.equal(await workspace.locator('.indicator-type-help,.indicator-export-info,.indicator-correction').count(),0);
 for(let i=0;i<2;i++){
  await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
  assert.equal(await workspace.locator('[data-validation="blank"] .indicator-validation-icon').count(),0);
  assert.equal(await portRow.locator('.indicator-validation-icon').count(),1);
  await sections.first().locator('tbody tr').last().getByRole('button',{name:/Delete/}).click();
 }
 await checkDisclosure();
 const complete=await(await page.request.get(base+'/cases/1/indicators/stix')).json();
 assert.ok(complete.objects.some(item=>item.type==='x-misp-attribute'&&item.x_misp_type==='port'&&item.x_misp_value==='443'&&item.x_misp_to_ids===false));
 // Manual and imported duplicate values highlight across sections; removal is local.
 for(const kind of ['port','text']){
  await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
  const row=sections.first().locator('tbody tr').last();
  await row.getByRole('combobox').fill(kind);await row.locator('td[data-column="1"]').fill('443');
 }
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 const duplicateSaved=await(await page.request.get(base+'/cases/1/indicators')).json();
 const firstDuplicateId=duplicateSaved.sections[0].row_meta.at(-2).id;
 await sections.nth(1).getByRole('button',{name:'Import',exact:true}).click();
 await page.locator('#indicator-csv-text').fill('type,value,description\nport,443,duplicate one\nport,443,duplicate two\n');
 await page.locator('#preview-indicator-import').click();await page.locator('#indicator-import-status').filter({hasText:'2 exact destination duplicates'}).waitFor();
 await page.locator('#indicator-skip-duplicates').uncheck();
 await page.locator('#confirm-indicator-import').click();await page.waitForFunction(()=>!document.querySelector('#indicator-import-dialog').open);
 const firstDuplicate=sections.first().locator('tbody tr').nth(2);
 await firstDuplicate.locator('td[data-column="1"]').focus();
 assert.equal(await workspace.locator('.indicator-duplicate-match').count(),4);
 assert.equal(await firstDuplicate.evaluate(el=>el.classList.contains('indicator-duplicate-match')),false);
 // Editing recomputes matches without rendering/replacing the focused cell.
 await firstDuplicate.locator('td[data-column="1"]').fill('444');
 assert.equal(await workspace.locator('.indicator-duplicate-match').count(),0);
 await firstDuplicate.locator('td[data-column="1"]').fill('443');
 assert.equal(await workspace.locator('.indicator-duplicate-match').count(),4);
 for(let i=0;i<2;i++)await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
 assert.equal(await workspace.locator('.indicator-duplicate-match').count(),0);
 const otherCount=await sections.nth(1).locator('tbody tr').count();
 const removeDuplicates=sections.first().getByRole('button',{name:'Remove duplicates',exact:true});
 assert.equal(await removeDuplicates.evaluate(el=>el.previousElementSibling.textContent),'Refang');
 await removeDuplicates.click();
 assert.equal(await sections.first().locator('tbody tr').count(),5); // two original, one retained, two blanks
 assert.equal(await sections.nth(1).locator('tbody tr').count(),otherCount);
 assert.equal(await sections.first().locator('[data-validation="blank"]').count(),2);
 assert.equal(await removeDuplicates.evaluate(el=>el===document.activeElement),true);
 await removeDuplicates.click();await page.locator('#indicator-status').filter({hasText:'No duplicate values'}).waitFor();
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 const deduplicated=await(await page.request.get(base+'/cases/1/indicators')).json();
 assert.equal(deduplicated.sections[0].rows.filter(row=>row[1]==='443').length,1);
 assert.equal(deduplicated.sections[0].row_meta[2].id,firstDuplicateId);
 assert.equal(deduplicated.sections[1].rows.filter(row=>row[1]==='443').length,3);
 // Saved canonical/refanged equivalents warn on every member, including the first.
 for(const value of ['hxxps://EXAMPLE[.]com/path','https://example.com/path']){
  await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
  const row=sections.first().locator('tbody tr').last();
  await row.getByRole('combobox').fill('url');await row.locator('td[data-column="1"]').fill(value);
 }
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 const allRows=sections.first().locator('tbody tr');
 const urlFirst=allRows.nth(await allRows.count()-2),urlSecond=allRows.last();
 for(const row of [urlFirst,urlSecond]){
  const warning=row.getByRole('button',{name:'Duplicate rows detected',exact:true});
  assert.equal(await warning.textContent(),'⚠');
  await warning.hover();assert.equal(await page.locator('#indicator-validation-error').textContent(),'Duplicate rows detected');
  await warning.focus();assert.equal(await warning.getAttribute('aria-expanded'),'true');
  await warning.press('Escape');await warning.press('Enter');assert.equal(await page.locator('#indicator-validation-error').isVisible(),true);
 }
 assert.equal(await sections.nth(1).locator('[data-validation="duplicate"]').count(),3);
 // Hold an autosave response, then change the second row: old warnings must not return.
 await urlFirst.locator('td[data-column="1"]').fill('https://one.example/path');
 let releaseDuplicateSave;const duplicateGate=new Promise(resolve=>releaseDuplicateSave=resolve);
 await page.route('**/cases/1/indicators',async route=>{if(route.request().method()==='POST'&&(route.request().postData()||'').includes('name="automatic"'))await duplicateGate;await route.continue();});
 const duplicateAuto=page.waitForRequest(request=>request.url().endsWith('/indicators')&&request.method()==='POST'&&(request.postData()||'').includes('name="automatic"'));
 await page.evaluate(()=>{Date.now=()=>window.indicatorDateNow()+6*60000;});await duplicateAuto;
 await urlSecond.locator('td[data-column="1"]').fill('https://two.example/path');
 releaseDuplicateSave();await page.locator('#indicator-status').filter({hasText:'newer changes pending'}).waitFor();
 assert.equal(await urlSecond.locator('[data-validation="pending"]').count(),1);
 assert.equal(await urlSecond.locator('.indicator-validation-icon').count(),0);
 await page.unroute('**/cases/1/indicators');await page.evaluate(()=>{Date.now=window.indicatorDateNow;});
 await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 assert.equal(await sections.first().locator('[data-validation="duplicate"]').count(),0);
 assert.equal(await urlFirst.getByRole('img',{name:'Valid indicator'}).count(),1);
 assert.equal(await urlSecond.getByRole('img',{name:'Valid indicator'}).count(),1);
 // An unchanged autosave retains canonical warnings in the other section.
 await page.evaluate(()=>{Date.now=()=>window.indicatorDateNow()+6*60000;});
 await page.locator('#indicator-status').filter({hasText:'Autosaved to'}).waitFor();
 await page.evaluate(()=>{Date.now=window.indicatorDateNow;});
 assert.equal(await sections.nth(1).locator('[data-validation="duplicate"]').count(),3);
 // Invalid values, missing binary data and unknown types all use the same X.
 for(const [kind,value] of [['sha256','invalid hash'],['SHA256','invalid hash'],['attachment','sample.bin'],['unknown-indicator-type','example']]){
  await sections.first().getByRole('button',{name:'Add row',exact:true}).click();
  const row=sections.first().locator('tbody tr').last();
  await row.getByRole('combobox').fill(kind);await row.locator('td[data-column="1"]').fill(value);
  assert.equal(await row.locator('[data-validation="pending"]').count(),1);
  await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'STIX unavailable'}).waitFor();
  assert.equal(await row.locator('[data-validation="invalid"] button').count(),1);
  assert.equal(await row.locator('.indicator-validation-icon').count(),1);
 }
 await page.reload();await sections.first().locator('[data-validation="invalid"]').first().waitFor();
 assert.equal(await sections.first().locator('[data-validation="invalid"]').count(),4);
 assert.equal(await portRow.getByRole('button',{name:'Duplicate rows detected',exact:true}).count(),1);
 await page.setViewportSize({width:390,height:844});
 const narrowWarning=portRow.getByRole('button',{name:'Duplicate rows detected',exact:true});
 await narrowWarning.click();
 assert.equal(await page.locator('#indicator-validation-error').textContent(),'Duplicate rows detected');
 assert.ok(await page.locator('#indicator-validation-error').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;}));
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await workspace.locator('.indicator-type-help,.indicator-export-info,.indicator-correction').count(),0);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log('PASS: canonical selector and keyboard editing, CSV/STIX tabs/target, correction preview, additive imports, STIX save/download/roundtrip, duplicates, stale previews, invalid drafts, compact validation icons, pending/stale status, error hover/focus/tap, repeated renders and narrow layouts; no external requests or browser errors.');
})().catch(error=>{console.error(error);console.error(log);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));fs.rmSync(temporary,{recursive:true,force:true});});
