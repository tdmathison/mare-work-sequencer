const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-backup-conflicts-'));
const real=fs.realpathSync(temporary),jobs=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8820';
const server=spawn('.venv/bin/python',['tests/browser/malware-families-server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_FAMILY_BROWSER_TEST:'1',MARE_FAMILY_TEST_PORT:'8820'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('family-browser');await page.getByLabel('Password',{exact:true}).fill('family-browser-password');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/settings/import-export');await page.locator('#import-tab').click();
 // Exercise every cardinality in the actual renderer, without submitting an import.
 await page.evaluate(()=>{
   window.conflictValues={};window.conflictRefreshes=[];
   window.conflictView=window.MWSBackupImport.create({onChoice(key,value){if(value===undefined)return window.conflictValues[key]||'';window.conflictValues[key]=value;},onRefresh(){window.conflictRefreshes.push({...window.conflictValues});}});
   window.conflictPreview={filename:'cardinality.zip',created:'2026-11-03T12:00:00Z',format:'mare-backup/1',application_version:'test',archive_hash:'first',destination:'first',complete:false,areas:['tags','cases','families'],counts:{cases:0,tags:0,malware_families:0},records:[],blocking:[],warnings:[],conflicts:[{key:'tag:none',label:'Renamed identity has no safe mapping',options:[]},{key:'family:one',label:'Existing family differs',record_name:'Incoming family',record_id:'family-one',reports:[{identifier:'report-one',name:'incoming.pdf'}],options:[['keep','Keep destination family; skip incoming family and reports']]},{key:'case:many',label:'Case conflict',options:[['keep','Keep destination'],['replace','Replace destination']]}]};
   window.conflictView.renderPreview(window.conflictPreview);window.conflictView.show(3);
 });
 const block=key=>page.locator('.backup-conflict[data-conflict-key="'+key+'"]');
 assert.equal(await block('family:one').locator('select').count(),0);assert.match(await block('family:one').innerText(),/Automatically selected/);assert.match(await block('family:one').innerText(),/Incoming family/);
 assert.equal(await page.evaluate(()=>window.conflictValues['family:one']),'keep');
 assert.ok(await block('tag:none').getByRole('alert').isVisible());assert.equal(await block('tag:none').locator('select').count(),0);
 assert.equal(await block('case:many').locator('select option').count(),3);assert.equal(await block('case:many').locator('select').inputValue(),'');
 await block('case:many').locator('select').selectOption('replace');
 await page.getByRole('button',{name:'Generate new preview',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.conflictRefreshes[0]['family:one']),'keep');assert.equal(await page.evaluate(()=>window.conflictRefreshes[0]['case:many']),'replace');
 await page.evaluate(()=>{const p=structuredClone(window.conflictPreview);p.archive_hash='second';p.destination='changed';p.conflicts.find(c=>c.key==='family:one').options=[];window.conflictView.renderPreview(p);window.conflictView.show(3);});
 assert.equal(await page.evaluate(()=>window.conflictValues['family:one']),'');assert.ok(await block('family:one').getByRole('alert').isVisible());
 assert.equal(await block('case:many').locator('select').inputValue(),'replace');
 await page.reload();
 const csrf=await page.locator('#backup-workspace').getAttribute('data-csrf');
 let response=await page.request.post(base+'/malware-families/new',{form:{csrf,name:'Automatic resolution family',tag:'MAL_AUTO_RESOLUTION',short_description:'Incoming research'},maxRedirects:0});assert.equal(response.status(),302);
 const fid=response.headers().location.split('/').pop().split('?')[0];
 response=await page.request.post(base+'/malware-families/'+fid+'/reports/upload',{multipart:{csrf,version:'1',reports:{name:'incoming-research.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:fs.readFileSync(path.join(temporary,'browser-research.docx'))}},maxRedirects:0});assert.equal(response.status(),302);
 await page.reload();await page.locator('#export-tab').click();await page.locator('#backup-export [name=areas][value=families]').check();await page.locator('#export-action').click();await page.getByRole('link',{name:'Download archive',exact:true}).waitFor();
 const download=await page.request.get(new URL(await page.getByRole('link',{name:'Download archive',exact:true}).getAttribute('href'),base).href);assert.equal(download.status(),200);const archive=await download.body();
 response=await page.request.post(base+'/malware-families/'+fid+'/edit',{form:{csrf,version:'2',name:'Automatic resolution family',tag:'MAL_AUTO_RESOLUTION',short_description:'Destination-only research',aliases_present:'1'},maxRedirects:0});assert.equal(response.status(),302);
 let applies=0;page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/apply'))applies++;});
 await page.locator('#import-tab').click();await page.locator('#backup-inspect [name=archive]').setInputFiles({name:'families.zip',mimeType:'application/zip',buffer:archive});await page.getByRole('heading',{name:'Reviewed import plan'}).waitFor();await page.locator('[data-import-go="3"]').click();
 const conflict=block('family:'+fid);assert.equal(await conflict.locator('select').count(),0);assert.match(await conflict.innerText(),/Automatically selected/);assert.match(await conflict.innerText(),/Automatic resolution family/);await conflict.locator('summary').click();assert.match(await conflict.innerText(),/incoming-research.docx/);assert.equal(applies,0);assert.ok(await page.locator('#import-action').isDisabled());
 const requested=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith('/preview'));
 await page.getByRole('button',{name:'Generate new preview',exact:true}).click();const request=await requested;assert.ok(request.postData().includes('family:'+fid));assert.ok(request.postData().includes('keep'));
 await page.locator('#import-status').filter({hasText:'preview · Ready for review'}).waitFor();assert.equal(applies,0);assert.match(await page.locator('#import-options').innerText(),/1 attached report\(s\) will be skipped/);
 // Resuming the validated preview must recover the canonical choice as well.
 await page.reload();await page.locator('[data-import-step="2"][aria-current=step]').waitFor();await page.locator('[data-import-go="3"]').click();
 await page.locator('#confirm-import').check();await page.waitForFunction(()=>!document.getElementById('import-action').disabled);
 const applying=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith('/apply'));
 await page.locator('#import-action').click();const finalRequest=await applying;assert.ok(finalRequest.postData().includes('family:'+fid));assert.ok(finalRequest.postData().includes('keep'));
 await page.locator('#import-result > p').filter({hasText:'Reviewed merge finished.'}).waitFor();
 const results=await page.locator('#import-result').innerText();assert.match(results,/1 incoming family record\(s\) and 1 attached report\(s\) skipped/);
 await page.getByRole('button',{name:'Expand all',exact:true}).click();assert.match(await page.locator('#import-result').innerText(),/incoming-research.docx/);
 assert.equal(applies,1);assert.deepEqual(errors,[]);console.log('PASS: zero/one/multiple rendering, automatic choice submission in preview and import, changed preview recalculation, persisted resume, no automatic import, and explicit skipped-family/report results.');
})().catch(e=>{console.error(log.slice(-3000));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(jobs,{recursive:true,force:true});});
