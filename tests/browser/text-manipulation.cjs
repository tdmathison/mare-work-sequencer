/* Text workspace and guided command palette regression; disposable database. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-text-'));
const port=Number(process.env.MARE_TEXT_TEST_PORT||8783),base=`http://127.0.0.1:${port}`;
const server=spawn(path.join(root,'.venv/bin/python'),['tests/browser/server.py'],{cwd:root,env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let log='',browser;server.stderr.on('data',data=>log+=data);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(error){if(i>60||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await page.getByRole('button',{name:'Sign in'}).click();
 await page.goto(base+'/tools/text-manipulation');
 const frame=page.frameLocator('#tool-panel-text-manipulation iframe');await frame.locator('.cm-content').waitFor();
 const child=await page.locator('#tool-panel-text-manipulation iframe').elementHandle();const workspaceFrame=await child.contentFrame();
 const read=()=>workspaceFrame.evaluate(()=>document.querySelector('[data-text-tool]').textView.state.doc.toString());
 const set=async text=>workspaceFrame.evaluate(text=>{const view=document.querySelector('[data-text-tool]').textView;view.dispatch({changes:{from:0,to:view.state.doc.length,insert:text},selection:{anchor:Math.min(15,text.length)}});},text);
 const command=async (label)=>{await frame.getByRole('button',{name:label,exact:true}).click();await frame.locator('[role=status]').filter({hasText:/^(Done\.|No matching|[0-9]+ invalid)/}).waitFor();};
 assert(await frame.getByRole('button',{name:'Undo',exact:true}).isDisabled());assert(await frame.getByRole('button',{name:'Redo',exact:true}).isDisabled());
 const category=(name)=>frame.locator('[data-command-category]').filter({has:frame.getByRole('button',{name,exact:true})});
 const favoriteCategory=frame.locator('[data-favorites-category]');
 const expansion=()=>frame.locator('[data-category-toggle]').evaluateAll(buttons=>buttons.map(button=>button.getAttribute('aria-expanded')));
 assert.deepEqual(await expansion(),['true','false','false','false','false','false','false','false']);
 await frame.getByText('Star commands to add them here.',{exact:true}).waitFor();
 await frame.getByRole('button',{name:'Misc',exact:true}).focus();await page.keyboard.press('Enter');assert.equal(await category('Misc').locator('[data-category-toggle]').getAttribute('aria-expanded'),'true');
 await set('b\na\nb');await workspaceFrame.evaluate(()=>window.favoriteEditorState=document.querySelector('[data-text-tool]').textView.state);
 await frame.locator('[data-original-category] [data-favorite=uniq]').click();
 assert.ok(await workspaceFrame.evaluate(()=>window.favoriteEditorState===document.querySelector('[data-text-tool]').textView.state));assert.equal(await read(),'b\na\nb');
 assert.equal(await frame.locator('[data-favorite=uniq][aria-pressed=true]').count(),2);
 await frame.locator('[data-original-category] [data-favorite=sort]').click();await frame.getByRole('button',{name:'Extract',exact:true}).click();await frame.locator('[data-original-category] [data-favorite=ipv4]').focus();await page.keyboard.press('Space');
 assert.deepEqual(await favoriteCategory.locator('[data-command-row]:not([hidden])').evaluateAll(rows=>rows.map(row=>row.dataset.commandId)),['ipv4','uniq','sort']);
 for(const width of [1366,390]){await page.setViewportSize({width,height:900});await page.waitForTimeout(250);await frame.locator('.text-commands').evaluate(e=>e.scrollTop=0);assert.ok(await workspaceFrame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`/tmp/mws-text-favorites-${width}.png`});}
 await page.setViewportSize({width:1366,height:900});
 const beforeSearch=await expansion();const favoriteSearch=frame.getByRole('searchbox',{name:'Search commands'});
 await favoriteSearch.fill('uniq');assert.deepEqual(await favoriteCategory.locator('[data-command-row]:not([hidden])').evaluateAll(rows=>rows.map(row=>row.dataset.commandId)),['ipv4','uniq']);assert.equal(await category('Misc').locator('[data-category-toggle]').getAttribute('aria-expanded'),'true');
 await frame.getByRole('button',{name:'Collapse all',exact:true}).click();assert.ok((await expansion()).every(value=>value==='false'));
 await favoriteSearch.press('Escape');assert.deepEqual(await expansion(),beforeSearch);
 await favoriteCategory.getByRole('button',{name:'Uniq',exact:true}).click();await frame.getByRole('status').filter({hasText:'Done.'}).waitFor();assert.equal(await read(),'b\na');await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),'b\na\nb');
 const beforeRemove=await expansion();await favoriteCategory.getByRole('button',{name:'Remove Uniq from favorites',exact:true}).click();assert.deepEqual(await expansion(),beforeRemove);assert.equal(await frame.locator('[data-favorite=uniq][aria-pressed=false]').count(),2);
 const preferenceKey=await workspaceFrame.evaluate(()=>{const key='mare-text-favorites:'+document.querySelector('[data-text-tool]').dataset.userPreferences;const saved=JSON.parse(localStorage.getItem(key));localStorage.setItem(key,JSON.stringify([...saved,'obsolete-command']));localStorage.setItem('mare-text-favorites:other-user',JSON.stringify(['json']));return key;});
 await workspaceFrame.goto(workspaceFrame.url());await frame.locator('.cm-content').waitFor();assert.deepEqual(await expansion(),['true','false','false','false','false','false','false','false']);assert.deepEqual(await favoriteCategory.locator('[data-command-row]:not([hidden])').evaluateAll(rows=>rows.map(row=>row.dataset.commandId)),['ipv4','sort']);
 assert.equal(await frame.locator('[data-favorite=sort][aria-pressed=true]').count(),2);assert.ok(!preferenceKey.endsWith('undefined'));
 await workspaceFrame.evaluate(key=>localStorage.setItem(key,'invalid JSON'),preferenceKey);await workspaceFrame.goto(workspaceFrame.url());await frame.locator('.cm-content').waitFor();await frame.getByText('Star commands to add them here.',{exact:true}).waitFor();
 assert.deepEqual(await workspaceFrame.evaluate(()=>JSON.parse(localStorage.getItem('mare-text-favorites:other-user'))),['json']);
 await frame.getByRole('button',{name:'Expand all',exact:true}).click();assert.ok((await expansion()).every(value=>value==='true'));
 await frame.getByRole('button',{name:'Collapse all',exact:true}).click();assert.ok((await expansion()).every(value=>value==='false'));await frame.getByRole('button',{name:'Expand all',exact:true}).click();
 const original=Array.from({length:500},(_,i)=>`row ${i}: ${i%3===0?'192.168.1.1':i%3===1?'8.8.8.8':'1.1.1.1'}`).join('\n');
 await set(original);const viewIdentity=await workspaceFrame.evaluate(()=>{window.originalTextView=document.querySelector('[data-text-tool]').textView;return true;});
 const expectedCommands=['ipv4','ipv6','all-ips','cidrs','domains','ips-domains','urls','emails','non-routable','empty-lines','carriage-returns','spaces','cr-spaces','cr-commas','cr-comma-space','cr-quotes','semicolon-cr','space-cr','comma-space-cr','split','egrep','egrep-v','egrep-o','ip-sort','defang','refang','uniq','uniq-count','sort','json','xml','python'];
 assert.deepEqual(await frame.locator('[data-original-category] [data-command]').evaluateAll(rows=>rows.map(row=>row.dataset.command)),expectedCommands);
 assert.deepEqual(await frame.locator('[data-original-category] [data-category-toggle] > span:first-child').allTextContents(),['Extract','Remove','Replace','Regex','IP Functions','Misc','Formatting']);
 assert.equal(await frame.locator('[data-original-category] .text-command-description').count(),32);
 const search=frame.getByRole('searchbox',{name:'Search commands'});
 await search.fill('literal delimiter');assert.equal(await frame.locator('[data-command]:visible').count(),1);assert.equal(await frame.getByRole('button',{name:'Split by',exact:true}).count(),1);assert.equal(await frame.locator('[data-command-category]:visible').count(),1);
 await search.fill('NO_SUCH_COMMAND');await frame.getByText('No commands match your search.',{exact:true}).waitFor();assert.equal(await frame.locator('[data-command-category]:visible').count(),0);
 await frame.getByRole('button',{name:'Clear search',exact:true}).click();assert.equal(await frame.locator('[data-command]:visible').count(),32);assert.equal(await read(),original);
 assert.equal(await workspaceFrame.evaluate(()=>document.querySelector('[data-text-tool]').textView.state.selection.main.head),15);
 await search.fill('sort');assert.equal(await frame.locator('[data-command]:visible').count(),2);await search.press('Escape');assert.equal(await frame.locator('[data-command]:visible').count(),32);
 for(const width of [1366,768,390]){
  await page.setViewportSize({width,height:900});await page.waitForTimeout(250);
  assert.ok(await workspaceFrame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.ok(await workspaceFrame.evaluate(()=>[...document.querySelectorAll('.text-command-list')].every(list=>{const rows=[...list.querySelectorAll('[data-command-row]:not([hidden])')],r=list.getBoundingClientRect();return rows.every((row,i)=>{const b=row.getBoundingClientRect();return Math.abs(b.width-r.width)<1&&(!i||b.top>=rows[i-1].getBoundingClientRect().bottom)&&row.scrollWidth<=row.clientWidth;});})));
  await frame.getByRole('button',{name:'Format Python',exact:true}).focus();await frame.getByRole('button',{name:'Format Python',exact:true}).scrollIntoViewIfNeeded();assert.ok(await workspaceFrame.evaluate(()=>{const e=document.activeElement,r=e.getBoundingClientRect(),p=e.closest('.text-commands').getBoundingClientRect();return r.top>=p.top&&r.bottom<=p.bottom;}));
  await frame.locator('.text-commands').evaluate(e=>e.scrollTop=0);await page.screenshot({path:`/tmp/mws-guided-commands-${width}.png`});
 }
 await page.setViewportSize({width:1366,height:900});
 assert.ok(await workspaceFrame.evaluate(()=>window.originalTextView===document.querySelector('[data-text-tool]').textView));
 await command('IPv4s');const extracted=await read();assert.equal(extracted,'192.168.1.1\n8.8.8.8\n1.1.1.1');
 await command('Non-Routable IPs');assert.equal(await read(),'8.8.8.8\n1.1.1.1');await command('Sort');assert.equal(await read(),'1.1.1.1\n8.8.8.8');
 for(const expected of ['8.8.8.8\n1.1.1.1',extracted,original]){await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),expected);}
 assert.equal(await workspaceFrame.evaluate(()=>document.querySelector('[data-text-tool]').textView.state.selection.main.head),15);
 for(const expected of [extracted,'8.8.8.8\n1.1.1.1','1.1.1.1\n8.8.8.8']){await frame.getByRole('button',{name:'Redo',exact:true}).click();assert.equal(await read(),expected);}
 assert(await frame.getByRole('button',{name:'Redo',exact:true}).isDisabled());
 await set(' a \n\t \n b ');await frame.locator('[data-original-category] [data-command="empty-lines"] .text-command-description').click();await frame.getByRole('status').filter({hasText:'Done.'}).waitFor();assert.equal(await read(),' a \n b ');await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),' a \n\t \n b ');
 await set('b\na\nb');await frame.getByRole('button',{name:'Uniq',exact:true}).focus();await page.keyboard.press('Enter');await frame.getByRole('status').filter({hasText:'Done.'}).waitFor();assert.equal(await read(),'b\na');await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),'b\na\nb');
 await set('b\na\nb');await command('Uniq');assert.equal(await read(),'b\na');await frame.locator('.cm-content').click();await page.keyboard.press('Meta+z');assert.equal(await read(),'b\na\nb');await page.keyboard.press('Meta+Shift+z');assert.equal(await read(),'b\na');
 await command('Uniq');await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),'b\na');await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),'b\na\nb');
 await set('{"x":1}');await command('Format JSON');assert.equal(await read(),'{\n    "x": 1\n}');assert(await frame.locator('.cm-content span').count()>0);
 await set('<r><a/></r>');await command('Format XML');assert.match(await read(),/\n/);await set('x=[1,2]');await command('Format Python');assert.equal(await read(),'x = [1, 2]\n');
 await set('{broken');await frame.getByRole('button',{name:'Format JSON',exact:true}).click();await frame.getByRole('status').filter({hasText:'Invalid JSON.'}).waitFor();assert.equal(await read(),'{broken');
 await set('a12 b34');await frame.locator('[data-pattern]').fill('\\d+');await command('egrep -o');assert.equal(await read(),'12\n34');
 await page.locator('#tool-tab-cyberchef').click();await page.locator('#tool-panel-cyberchef iframe').waitFor();const chef=page.frameLocator('#tool-panel-cyberchef iframe');await chef.locator('#input-text').waitFor({timeout:60000});
 await page.locator('#tool-tab-text-manipulation').click();assert.equal(await read(),'12\n34');assert(await workspaceFrame.evaluate(()=>window.originalTextView===document.querySelector('[data-text-tool]').textView));
 const positions=await page.evaluate(()=>({x:scrollX,y:scrollY}));const childPositions=await workspaceFrame.evaluate(()=>({x:scrollX,y:scrollY}));await command('CRs with Commas');assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),positions);assert.deepEqual(await workspaceFrame.evaluate(()=>({x:scrollX,y:scrollY})),childPositions);
 await frame.getByRole('button',{name:'Undo',exact:true}).click();await frame.getByRole('button',{name:'Redo',exact:true}).click();assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY})),positions);
 assert.deepEqual(errors,[]);console.log('PASS: category defaults/toggles/all controls, Favorites stars/order/sync/persistence/user scoping/obsolete IDs, temporary search expansion, no star execution; 32 guided command rows, name/description search and empty/reset states, responsive geometry, description/keyboard activation, preserved editor; 500-line atomic undo/redo chain, selection, keyboard history, disabled buttons, formatting/highlighting/errors, retained editor/tab state, CyberChef loading and no window scrolling.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temporary,{recursive:true,force:true});});
