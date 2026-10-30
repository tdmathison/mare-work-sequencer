const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-backup-browser-'));
const real=fs.realpathSync(temporary),jobs=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8797';
const server=spawn('.venv/bin/python',['tests/browser/malware-families-server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_FAMILY_BROWSER_TEST:'1',MARE_FAMILY_TEST_PORT:'8797'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('family-browser');await page.getByLabel('Password',{exact:true}).fill('family-browser-password');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/settings/import-export');await page.getByRole('heading',{name:'Backup & Restore'}).waitFor();
 const area=key=>page.locator(`#backup-export [name=areas][value=${key}]`);
 assert.equal(await page.locator('#export-action').isDisabled(),true);assert.equal(await area('actors').isDisabled(),false);
 await page.locator('#complete-backup').check();for(const key of ['cases','families','tags'])assert.ok(await area(key).isChecked());
 await area('cases').uncheck();assert.equal(await page.locator('#complete-backup').isChecked(),false);
 await area('cases').check();assert.equal(await page.locator('#complete-backup').isChecked(),false);
 await area('families').uncheck();await area('actors').uncheck();await area('cases').uncheck();
 await page.locator('#export-action').click();await page.getByRole('link',{name:'Download archive',exact:true}).waitFor();
 let pending=page.waitForEvent('download');await page.getByRole('link',{name:'Download archive',exact:true}).click();let downloaded=await pending;const selective=fs.readFileSync(await downloaded.path());
 assert.match(downloaded.suggestedFilename(),/^MWS_\d{8}-\d{6}_T\.zip$/);
 assert.ok((await page.locator('#export-result').textContent()).includes(downloaded.suggestedFilename()));
 const csrf=await page.locator('#backup-workspace').getAttribute('data-csrf');
 assert.equal((await page.request.post(base+'/__backup_tag_conflict',{form:{csrf}})).status(),200);
 await page.locator('#import-tab').click();await page.locator('#backup-inspect [name=archive]').setInputFiles({name:'tags.zip',mimeType:'application/zip',buffer:selective});
 await page.getByRole('heading',{name:'Reviewed import plan'}).waitFor();assert.ok(await page.locator('#import-action').isDisabled());
 assert.equal(await page.locator('[data-import-step="2"]').getAttribute('aria-current'),'step');assert.equal(await page.locator('[data-import-step="1"] span').textContent(),'✓');
 assert.equal(await page.locator('#import-preview .import-card').count(),1);
 assert.ok((await page.locator('#import-preview table').textContent()).includes('MAL_BROWSER'));
 await page.locator('[data-import-step="1"]').click();assert.ok((await page.locator('#archive-selected').textContent()).includes('tags.zip'));
 await page.locator('[data-import-go="2"]').first().click();await page.locator('[data-import-go="3"]').click();
 await page.locator('.backup-conflict select').selectOption('reuse');await page.getByRole('button',{name:'Generate new preview'}).click();
 await page.locator('#import-status').filter({hasText:'preview · Ready for review'}).waitFor();await page.locator('#confirm-import').check();await page.waitForFunction(()=>!document.getElementById('import-action').disabled);
 await page.locator('#import-action').click();await page.locator('#import-result > p').filter({hasText:'Reviewed merge finished.'}).waitFor();
 assert.ok((await page.locator('#import-result').textContent()).includes('Unchanged'));
 assert.equal(await page.locator('[data-import-step="4"]').getAttribute('aria-current'),'step');
 assert.equal(await page.locator('#import-result pre').count(),0);
 await page.getByRole('button',{name:'Expand all',exact:true}).click();assert.ok(await page.locator('.import-result-group').first().evaluate(n=>n.open));
 await page.getByRole('button',{name:'Collapse all',exact:true}).click();assert.ok(await page.locator('.import-result-group').first().evaluate(n=>!n.open));
 await page.getByRole('searchbox',{name:'Search import results'}).fill('not a real record');assert.equal(await page.locator('.import-result-group').count(),0);await page.getByRole('searchbox',{name:'Search import results'}).fill('');
 const reportEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Download results report'}).click();const report=await reportEvent;assert.ok(JSON.parse(fs.readFileSync(await report.path())).records.length>0);
 await page.locator('#export-tab').click();await page.locator('#complete-backup').check();await page.locator('#backup-export [name=passphrase]').fill('a browser recovery passphrase');
 await page.locator('#export-action').click();await page.locator('#import-tab').click();await page.locator('#export-tab').click();
 await page.getByRole('link',{name:'Download archive',exact:true}).waitFor();pending=page.waitForEvent('download');await page.getByRole('link',{name:'Download archive',exact:true}).click();downloaded=await pending;const complete=fs.readFileSync(await downloaded.path());
 assert.match(downloaded.suggestedFilename(),/^MWS_\d{8}-\d{6}_C_T_TA_MF\.zip$/);
 assert.ok((await page.locator('#export-result').textContent()).includes(downloaded.suggestedFilename()));
 await page.locator('#import-tab').click();await page.getByRole('button',{name:'Select another archive',exact:true}).click();await page.locator('#backup-inspect [name=passphrase]').fill('a browser recovery passphrase');
 await page.locator('#backup-inspect [name=archive]').setInputFiles({name:'complete.zip',mimeType:'application/zip',buffer:complete});
 await page.getByRole('heading',{name:'Reviewed import plan'}).waitFor();await page.locator('[data-import-go="3"]').click();await page.locator('#replacement-ack').waitFor();assert.ok(await page.locator('#import-action').isDisabled());await page.locator('#ack-replace').check();await page.locator('#confirm-import').check();assert.equal(await page.locator('#import-action').isDisabled(),false);
 await page.reload();await page.getByRole('heading',{name:'Reviewed import plan'}).waitFor();await page.locator('[data-import-go="3"]').click();await page.locator('#replacement-ack').waitFor();assert.ok(await page.locator('#import-action').isDisabled(),'Reload must require renewed acknowledgement');
 if(process.env.MARE_BACKUP_SCREENSHOT)await page.screenshot({path:process.env.MARE_BACKUP_SCREENSHOT,fullPage:true});
 for(const viewport of [{width:1366,height:768},{width:390,height:844}]){await page.setViewportSize(viewport);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.locator('[data-import-step="1"]').click();await page.locator('#backup-inspect [name=archive]').setInputFiles({name:'bad.zip' ,mimeType:'application/zip',buffer:Buffer.from('invalid archive')});
 await page.locator('#import-result [role=alert]').waitFor();assert.equal(await page.locator('[data-import-step="2"]').evaluate(n=>n.classList.contains('is-complete')),false);assert.ok(await page.locator('#import-action').isDisabled());
 await page.setViewportSize({width:1440,height:1000});
 // Presentation fixtures exercise mixed outcomes without executing another import.
 const mixed={state:'failed',filename:'mixed.zip',preview:{filename:'mixed.zip',areas:['cases','tags','actors','families'],records:[]},result:{message:'Import completed with record issues.',failed:2,started_at:'2026-10-30T10:00:00+00:00',completed_at:'2026-10-30T10:00:05+00:00',duration:5,records:[
 {category:'cases',identifier:'CASE-1',name:'New investigation',action:'added',details:'New case created'},
 {category:'cases',identifier:'CASE-2',name:'Updated investigation',action:'updated',details:'Newer revision applied'},
 {category:'cases',identifier:'CASE-3',name:'Duplicate investigation',action:'skipped',details:'Existing case retained'},
 {category:'tags',identifier:'tag-1',name:'MAL_REPEAT',action:'unchanged',details:'Verified existing identity'},
 {category:'actors',identifier:'actor-1',name:'Actor collision',action:'conflict',details:'Resolve the identity collision'},
 {category:'families',identifier:'family-1',name:'Family failure',action:'error',details:'Validation failed'},
 {category:'families',identifier:'family-2',name:'New family',action:'added',details:'New validated research profile'}]}};
 await page.evaluate(fixture=>{window.importTestView=window.MWSBackupImport.create({onChoice(){return '';},onRefresh(){}});window.importTestView.renderResults(fixture);},mixed);
 assert.ok((await page.locator('#import-result').textContent()).includes('Import completed with issues'));
 assert.equal(await page.locator('#import-result .import-card').count(),4);
 assert.equal(await page.locator('.import-result-group.action-added').count(),2);
 assert.equal(await page.locator('.import-result-group.action-updated').count(),1);
 assert.equal(await page.locator('.import-result-group.action-skipped').count(),1);
 assert.equal(await page.locator('.import-result-group.action-conflict').count(),1);
 assert.equal(await page.locator('.import-result-group.action-error').count(),1);
 const originalSummary=await page.locator('#import-result .backup-summary').textContent();
 await page.getByRole('combobox',{name:'Result category',exact:true}).selectOption('families');
 assert.equal(await page.locator('.import-result-category').count(),1);
 await page.getByRole('combobox',{name:'Result action',exact:true}).selectOption('error');
 assert.equal(await page.locator('.import-result-group').count(),1);
 await page.getByRole('searchbox',{name:'Search import results'}).fill('family-1');
 assert.ok((await page.locator('.import-result-group').textContent()).includes('Family failure'));
 assert.equal(await page.locator('#import-result .backup-summary').textContent(),originalSummary);
 await page.getByRole('combobox',{name:'Result category',exact:true}).selectOption('all');await page.getByRole('combobox',{name:'Result action',exact:true}).selectOption('all');await page.getByRole('searchbox',{name:'Search import results'}).fill('');
 await page.screenshot({path:'/tmp/mws-import-results.png',fullPage:true});
 const many={filename:'preview.zip',created:'2026-10-30',format:'mare-backup/1',archive_size:1234,areas:['cases','tags'],counts:{cases:56,tags:0},blocking:[],warnings:[],conflicts:[],records:Array.from({length:56},(_,i)=>({category:'cases',identifier:'CASE-'+i,name:'Case '+String(i).padStart(2,'0'),stage:1,created:'2026-10-30',predicted_action:'new'}))};
 await page.evaluate(p=>window.importTestView.renderPreview(p),many);
 assert.equal(await page.locator('#import-preview tbody tr').count(),25);
 await page.getByRole('button',{name:'Next',exact:true}).click();assert.equal(await page.locator('#import-preview tbody tr').count(),25);
 await page.getByRole('button',{name:'Next',exact:true}).click();assert.equal(await page.locator('#import-preview tbody tr').count(),6);
 await page.getByRole('searchbox',{name:'Search archive records'}).fill('Case 55');assert.equal(await page.locator('#import-preview tbody tr').count(),1);
 await page.getByRole('combobox',{name:'Preview category',exact:true}).selectOption('tags');assert.ok((await page.locator('#import-preview').textContent()).includes('No matching records.'));
 assert.ok((await page.locator('#import-preview .import-card').last().textContent()).includes('0 records'));
 for(const viewport of [{width:1366,height:768},{width:390,height:844}]){await page.setViewportSize(viewport);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}

 assert.deepEqual(errors,[]);console.log('Structured import browser checks passed: four stages, tables, pagination, all-category outcome groups, updates, partial failures, filtering, search, report download, selection, dependencies, complete encryption, auto preview, conflict resolution, import, acknowledgement, reload, tabs and responsive layout.');
})().catch(e=>{console.error(log.slice(-3000));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(jobs,{recursive:true,force:true});});
