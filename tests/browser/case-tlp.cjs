/* Exercise official markings, native selection, create geometry and live Board refresh. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mws-case-tlp-')),real=fs.realpathSync(temp),jobs=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const prefix=process.env.MWS_BASE_PATH||'',base='http://127.0.0.1:8837'+prefix;
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temp,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8837',MARE_EDITOR_TEST_SCRIPT_PREFIX:prefix},stdio:['ignore','ignore','pipe']});let browser,log='';server.stderr.on('data',d=>log+=d);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch{if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.setDefaultTimeout(15000);
 const errors=[];context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/settings/general');await page.locator('#default-case-tlp').selectOption('TLP:GREEN');await page.getByRole('button',{name:'Save Default Case TLP',exact:true}).click();await page.waitForURL(base+'/settings/general');
 await page.goto(base+'/cases/new');const name=page.locator('#case-name'),select=page.locator('#case-tlp');
 const original=await name.inputValue();assert.match(original,/^\d{8}: $/);assert.equal(await select.inputValue(),'TLP:GREEN');
 assert.deepEqual(await name.evaluate(e=>({focused:document.activeElement===e,start:e.selectionStart,end:e.selectionEnd})),{focused:true,start:original.length,end:original.length});
 const labels=['TLP:RED','TLP:AMBER+STRICT','TLP:AMBER','TLP:GREEN','TLP:CLEAR'],colors=['#FF2B2B','#FFC000','#FFC000','#33FF00','#FFFFFF'];
 assert.deepEqual(await select.locator('option').allTextContents(),labels);
 for(let i=0;i<labels.length;i++){await select.selectOption(labels[i]);assert.equal(await select.locator('option:checked').getAttribute('data-color'),colors[i]);assert.equal(await select.locator('..').locator('[data-tlp-selected]').evaluate(e=>getComputedStyle(e).getPropertyValue('--tlp-color')),colors[i]);}
 await select.selectOption('TLP:AMBER+STRICT');
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});const a=await name.boundingBox(),b=await select.boundingBox();
  if(width>600){assert.ok(Math.abs(a.y-b.y)<2,JSON.stringify({a,b}));assert.ok(b.x>a.x+a.width);assert.ok(b.width>170);}
  else{assert.ok(b.y>a.y+a.height);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 }
 // Validation re-render preserves the analyst's selection and never inserts another date.
 await name.fill('');await page.locator('form[action$="/cases"]').evaluate(e=>e.noValidate=true);await page.getByRole('button',{name:'Create case & MIP',exact:true}).click();await page.waitForURL(base+'/cases');assert.equal(await name.inputValue(),'');assert.equal(await select.inputValue(),'TLP:AMBER+STRICT');
 await name.fill(original+'TLP browser Case');await page.locator('[name=owner_id]').selectOption('1');await page.getByRole('button',{name:'Create case & MIP',exact:true}).click();await page.waitForURL(/\/cases\/\d+$/);const casePath=new URL(page.url()).pathname,cid=casePath.split('/').at(-1);
 await page.setViewportSize({width:1440,height:1000});
 const board=await context.newPage();await board.goto(base+'/?view=table');const marker=board.locator(`[data-tlp-case="${cid}"]`);await marker.waitFor();assert.equal(await marker.getAttribute('aria-label'),'TLP:AMBER+STRICT');assert.equal(await marker.locator('[data-tlp-symbol]').textContent(),'+');
 const rowHeight=await marker.locator('xpath=ancestor::tr').evaluate(e=>e.getBoundingClientRect().height);
 await marker.focus();assert.equal(await marker.locator('.tlp-tooltip').isVisible(),true);
 await page.bringToFront();await page.locator('#edit-case-tlp').selectOption('TLP:CLEAR');await page.getByRole('button',{name:'Save details',exact:true}).click();await page.waitForURL(base+'/cases/'+cid);
 await board.bringToFront();await board.evaluate(()=>window.dispatchEvent(new Event('focus')));await marker.filter({has:board.locator('[data-tlp-symbol]')}).waitFor();await board.waitForFunction(cid=>document.querySelector(`[data-tlp-case="${cid}"]`).getAttribute('aria-label')==='TLP:CLEAR',cid);
 assert.equal(await marker.locator('[data-tlp-symbol]').textContent(),'');assert.equal(await marker.locator('xpath=ancestor::tr').evaluate(e=>e.getBoundingClientRect().height),rowHeight);
 const publicData=await(await page.request.get(base+'/dashboards/cases/data')).json();assert.equal(publicData.metrics.not_started,1);
 await board.goto(base+'/?view=cards');assert.equal(await board.locator(`[data-tlp-case="${cid}"]`).getAttribute('aria-label'),'TLP:CLEAR');
 // Server-side filtering removes a previously public Case on the next data read.
 await page.bringToFront();await page.locator('#edit-case-tlp').selectOption('TLP:RED');await page.getByRole('button',{name:'Save details',exact:true}).click();await page.waitForURL(base+'/cases/'+cid);
 assert.equal((await(await page.request.get(base+'/dashboards/cases/data')).json()).metrics.not_started,0);
 assert.deepEqual(errors,[]);console.log('PASS: TLP values/swatches, default, create row/caret/validation, mobile stacking, Workbench edits, accessible strict marker, stable row height, live Board refresh and public exclusion at '+(prefix||'/'));
})().catch(e=>{console.error(log.slice(-2500));console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();fs.rmSync(temp,{recursive:true,force:true});fs.rmSync(jobs,{recursive:true,force:true});});
