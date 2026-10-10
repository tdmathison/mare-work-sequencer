/* Real-browser compact tags and drawer regression; isolated temporary database. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-tags-'));
const port=Number(process.env.MARE_TAG_TEST_PORT||8782),base=`http://127.0.0.1:${port}`;
const server=spawn(path.join(root,'.venv/bin/python'),['tests/browser/server.py'],{cwd:root,env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let log='',browser;server.stderr.on('data',data=>log+=data);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(error){if(i>60||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await page.getByRole('button',{name:'Sign in'}).click();
 const fixture=await(await page.request.get(base+'/__editor_test__')).json(),cid=fixture.cid;
 const add=async value=>{await page.goto(`${base}/cases/${cid}`);const input=page.getByRole('combobox',{name:'Add tag'});await input.fill(value);await page.getByRole('option',{name:`Create “${value}”`,exact:true}).waitFor();await input.press('Enter');await page.getByRole('button',{name:`Remove ${value} from case`,exact:true}).waitFor();};
 await add('MAL-ASYNC_RAT');await add('MAL-ASYNC');
 assert.equal(await page.locator('#case-tags .tag-chip').count(),2); // Partial match did not hijack Enter.
 const input=page.getByRole('combobox',{name:'Add tag'});await input.fill('MAL-ASYNC_RAT');await page.getByRole('option',{name:'MAL-ASYNC_RAT',exact:true}).waitFor();await input.press('Enter');await page.waitForLoadState();assert.equal(await page.locator('#case-tags .tag-chip').count(),2);
 await input.fill('MAL-');await page.getByRole('option',{name:'MAL-ASYNC',exact:true}).waitFor();await input.press('ArrowDown');assert.equal(await page.locator('[role=option][aria-selected=true]').count(),1);await input.press('Escape');assert.equal(await input.getAttribute('aria-expanded'),'false');
 await page.goto(base+'/tags');const create=page.locator('form[action="/tags/create"]');await create.locator('[name=name]').fill('TA-APT41');await create.getByRole('button',{name:'Create tag'}).click();
 await page.goto(`${base}/cases/${cid}`);await input.fill('APT');await page.getByRole('option',{name:'TA-APT41',exact:true}).waitFor();await input.press('ArrowDown');await input.press('Enter');await page.locator('#case-tags .tag-chip').filter({hasText:'TA-APT41'}).waitFor();
 for(const value of ['X'.repeat(120),'PHISHING','TECH-PERSISTENCE'])await add(value);
 assert.equal(await page.locator('#case-tags .tag-chip').count(),6);
 await page.setViewportSize({width:800,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await page.goto(base+'/');const drawer=page.locator('#tag-filter-drawer');assert.equal(await drawer.isVisible(),false);
 const content=page.locator('.tag-board-content');const collapsed=await content.boundingBox();await page.getByRole('button',{name:'Filters',exact:true}).click();await drawer.getByText('MAL-ASYNC_RAT',{exact:true}).waitFor();
 const overlay=await content.boundingBox();assert.equal(collapsed.width,overlay.width);
 await drawer.getByText('MAL-ASYNC_RAT',{exact:true}).locator('input').check();await drawer.getByText('TA-APT41',{exact:true}).locator('input').check();await drawer.locator('[name=match]').selectOption('all');await drawer.getByRole('button',{name:'Apply',exact:true}).click();assert.equal(await page.locator('.mip-card').count(),1);assert.equal(await page.locator('.card-tags .tag-chip').count(),3);assert.match(await page.locator('.card-tags').textContent(),/\+3/);
 await page.setViewportSize({width:1366,height:900});await page.getByRole('button',{name:'Filters (2)',exact:true}).click();const before=await content.boundingBox();assert(before.width<1100);await drawer.getByRole('button',{name:'Collapse filters'}).click();const after=await content.boundingBox();assert(after.width>before.width);
 await page.goto(base+'/tags');await page.getByRole('link',{name:'MAL-ASYNC',exact:true}).click();await page.getByText('Merge tag',{exact:true}).click();const merge=page.locator('form[action$="/merge"]');await merge.locator('[name=destination]').selectOption({label:'MAL-ASYNC_RAT (1 cases)'});await merge.locator('[name=confirm]').check();await merge.getByRole('button',{name:'Confirm merge'}).click();
 await page.getByRole('link',{name:'MAL-ASYNC_RAT',exact:true}).click();const rename=page.locator('form[action$="/rename"]');await rename.locator('[name=name]').fill('Renamed');await rename.getByRole('button',{name:'Rename',exact:true}).click();
 await page.goto(`${base}/cases/${cid}`);assert.equal(await page.locator('#case-tags .tag-chip').count(),5);await page.getByRole('button',{name:'Remove Renamed from case'}).click();await page.waitForFunction(()=>document.querySelectorAll('#case-tags .tag-chip').length===4);assert.equal(await page.locator('#case-tags .tag-chip').count(),4);
 // Dispatch tag actions while far below the controls, without Playwright scrolling them into view.
 await page.evaluate(()=>{const spacer=document.createElement('div');spacer.style.height='2500px';document.body.append(spacer);window.scrollTo(0,900);window.__tagPageMarker='same document';});
 await page.evaluate(()=>{const area=document.querySelector('textarea[name=executive_summary]');const editor=window.MareEditors.get(area);editor.setValue('Unsaved tag regression\n'.repeat(100),{notify:true});editor.setSelection(11);window.__tagEditor=editor;window.__tagEditorState={doc:editor.getValue(),selection:editor.selection(),scroll:editor.view.scrollDOM.scrollTop};});
 const beforeScroll=await page.evaluate(()=>({x:scrollX,y:scrollY}));
 await page.evaluate(()=>{const input=document.querySelector('.tag-autocomplete input[name=name]');input.value='NO-JUMP';input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.tag-autocomplete').requestSubmit();});
 await page.getByRole('button',{name:'Remove NO-JUMP from case',exact:true}).waitFor({state:'attached'});
 assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),beforeScroll);
 assert.equal(await page.evaluate(()=>window.__tagPageMarker),'same document');
 await page.evaluate(()=>document.querySelector('[aria-label="Remove NO-JUMP from case"]').click());
 await page.getByRole('button',{name:'Remove NO-JUMP from case',exact:true}).waitFor({state:'detached'});
 assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),beforeScroll);
 assert.equal(await page.evaluate(()=>window.__tagPageMarker),'same document');
 assert(await page.evaluate(()=>window.__tagEditor===window.MareEditors.get(document.querySelector('textarea[name=executive_summary]'))));
 assert.deepEqual(await page.evaluate(()=>({doc:window.__tagEditor.getValue(),selection:window.__tagEditor.selection(),scroll:window.__tagEditor.view.scrollDOM.scrollTop})),await page.evaluate(()=>window.__tagEditorState));
 await page.evaluate(()=>{const button=[...document.querySelectorAll('[data-remove-tag]')][0];window.__tagRemovedName=button.getAttribute('aria-label');button.click();});
 await page.waitForFunction(()=>![...document.querySelectorAll('[data-remove-tag]')].some(button=>button.getAttribute('aria-label')===window.__tagRemovedName));
 assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),beforeScroll);
 page.on('dialog',dialog=>dialog.accept());
 await page.reload();assert.equal(await page.getByRole('button',{name:'Remove NO-JUMP from case',exact:true}).count(),0);
 assert.deepEqual(errors,[]);console.log('PASS: compact autocomplete, exact/partial Enter, keyboard selection/Escape, long names/many tags, narrow overlay and desktop drawer, Match All/card overflow, merge/rename/remove; no browser errors.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temporary,{recursive:true,force:true});});
