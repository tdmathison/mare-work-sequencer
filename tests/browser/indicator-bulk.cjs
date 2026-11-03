const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-indicator-bulk-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8824';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8824'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/cases/1?tab=indicators');
 const workspace=page.locator('#indicator-workspace'),dialog=page.locator('#indicator-import-dialog');
 const table=async()=>await(await page.request.get(base+'/cases/1/indicators')).json();
 await workspace.getByRole('button',{name:'Add new section',exact:true}).click();await page.locator('#indicator-section-form [name=title]').fill('Bulk target');await page.locator('#indicator-section-form button[type=submit]').click();
 // Opening the existing Import dialog saves a new section through the normal path.
 const target=page.locator('.indicator-section').filter({has:page.getByRole('heading',{name:'Bulk target',exact:true})});
 await target.getByRole('button',{name:'Import',exact:true}).click();await dialog.waitFor();
 const before=await table();assert.equal(before.sections.length,2);
 const openBulk=async()=>{await dialog.getByRole('tab',{name:'Type in bulk',exact:true}).click();};
 const preview=async()=>{await dialog.getByRole('button',{name:'Preview import',exact:true}).click();await dialog.locator('.indicator-preview-row').first().waitFor();};
 await openBulk();
 const kind=dialog.locator('#indicator-bulk-type'),values=dialog.locator('#indicator-bulk-values'),description=dialog.locator('#indicator-bulk-description');
 assert.equal(await kind.getAttribute('list'),'indicator-type-options');
 await dialog.getByRole('button',{name:'Preview import',exact:true}).click();await dialog.locator('#indicator-import-status').filter({hasText:'Choose a supported indicator type'}).waitFor();
 await kind.fill('SHA-256');await dialog.getByRole('button',{name:'Preview import',exact:true}).click();await dialog.locator('#indicator-import-status').filter({hasText:'at least one nonempty value'}).waitFor();
 await values.fill(' '+ 'a'.repeat(64)+' \r\n\r\n invalid hash \n'+ 'c'.repeat(64));await description.fill('Extracted, during "static" analysis');await preview();
 const rows=dialog.locator('.indicator-preview-row');assert.equal(await rows.count(),3);assert.equal(await rows.nth(1).locator('.indicator-source-line').innerText(),'Line 3');assert.match(await rows.nth(1).innerText(),/Needs correction/);
 assert.ok((await values.inputValue()).includes('invalid hash'));assert.deepEqual(await table(),before);
 await values.fill(' '+ 'a'.repeat(64)+' \r\n\r\n'+ 'c'.repeat(64)+' \n');await preview();assert.equal(await rows.count(),2);
 let posts=0;page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/cases/1/indicators/import')posts++;});
 await dialog.locator('#confirm-indicator-import').evaluate(button=>{button.click();button.click();});await dialog.waitFor({state:'hidden'});
 let saved=await table();assert.equal(saved.sections[0].rows.length,0);assert.deepEqual(saved.sections[1].rows,[['sha256','a'.repeat(64),'Extracted, during "static" analysis'],['sha256','c'.repeat(64),'Extracted, during "static" analysis']]);assert.equal(posts,1);assert.match(await page.locator('#indicator-status').innerText(),/Added 2 rows/);
 // Destination + within-batch duplicates are visible; default skipping is explicit.
 await target.getByRole('button',{name:'Import',exact:true}).click();await openBulk();await kind.fill('sha256');await values.fill('a'.repeat(64)+'\n'+'b'.repeat(64)+'\n'+'b'.repeat(64));await preview();assert.match(await rows.first().innerText(),/duplicate in destination/);assert.match(await rows.nth(2).innerText(),/Duplicate of an earlier incoming row/);
 await dialog.getByRole('button',{name:'Import',exact:true}).click();await dialog.waitFor({state:'hidden'});saved=await table();assert.equal(saved.sections[1].rows.length,3);assert.equal(saved.sections[1].rows[2][2],'');assert.match(await page.locator('#indicator-status').innerText(),/Added 1 rows; skipped 2 duplicates/);
 // Explicitly keeping duplicates honors the existing import option.
 await target.getByRole('button',{name:'Import',exact:true}).click();await openBulk();await kind.fill('sha256');await values.fill('b'.repeat(64)+'\n'+'b'.repeat(64));await preview();await dialog.locator('#indicator-skip-duplicates').uncheck();await dialog.getByRole('button',{name:'Import',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.equal((await table()).sections[1].rows.length,5);
 // Arbitrary text retains commas, quotes and internal whitespace; cancel is inert.
 const preCancel=await table();await target.getByRole('button',{name:'Import',exact:true}).click();await openBulk();await kind.fill('text');await values.fill('  hello, "world"  with spaces  \n next value ');await preview();await dialog.getByRole('button',{name:'Cancel',exact:true}).click();assert.deepEqual(await table(),preCancel);
 await target.getByRole('button',{name:'Import',exact:true}).click();await openBulk();await kind.fill('text');await values.fill('  hello, "world"  with spaces  \n next value ');await preview();await dialog.getByRole('button',{name:'Import',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.deepEqual((await table()).sections[1].rows.slice(-2),[['text','hello, "world"  with spaces',''],['text','next value','']]);
 // Original CSV option remains functional and Save table remains available.
 await target.getByRole('button',{name:'Import',exact:true}).click();assert.equal(await dialog.getByRole('tab',{name:'CSV',exact:true}).getAttribute('aria-selected'),'true');await dialog.locator('#indicator-csv-text').fill('domain,bulk.example,CSV still works');await preview();await dialog.getByRole('button',{name:'Append accepted rows',exact:true}).click();await dialog.waitFor({state:'hidden'});await page.locator('#save-indicators').click();await page.locator('#indicator-status').filter({hasText:'CSV and STIX'}).waitFor();
 // Responsive bulk form and three-tab keyboard navigation.
 await target.getByRole('button',{name:'Import',exact:true}).click();await openBulk();await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await dialog.getByRole('tab',{name:'Type in bulk',exact:true}).press('Home');assert.equal(await dialog.getByRole('tab',{name:'CSV',exact:true}).getAttribute('aria-selected'),'true');await dialog.getByRole('tab',{name:'CSV',exact:true}).press('End');assert.equal(await dialog.getByRole('tab',{name:'Type in bulk',exact:true}).getAttribute('aria-selected'),'true');await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 const changed=spawnSync('.venv/bin/python',['-c','import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("UPDATE cases SET stage=3 WHERE id=1"); c.commit()',path.join(temporary,'workflow.sqlite3')]);assert.equal(changed.status,0);await page.reload();await target.waitFor();assert.ok(await target.getByRole('button',{name:'Import',exact:true}).isDisabled());
 assert.deepEqual(errors,[]);console.log('PASS: bulk fields/type catalog, required input, line-number validation, CRLF/blanks, section target, shared/empty descriptions, immediate save counts, repeated-click guard, duplicate skip/keep, literal text, cancel, CSV and Save table, keyboard/mobile, closed Case.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
