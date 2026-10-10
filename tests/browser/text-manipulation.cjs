/* Real-browser compact tags and drawer regression; isolated temporary database. */
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
 const original=Array.from({length:500},(_,i)=>`row ${i}: ${i%3===0?'192.168.1.1':i%3===1?'8.8.8.8':'1.1.1.1'}`).join('\n');
 await set(original);const viewIdentity=await workspaceFrame.evaluate(()=>{window.originalTextView=document.querySelector('[data-text-tool]').textView;return true;});
 await command('IPv4s');const extracted=await read();assert.equal(extracted,'192.168.1.1\n8.8.8.8\n1.1.1.1');
 await command('Non-Routable IPs');assert.equal(await read(),'8.8.8.8\n1.1.1.1');await command('Sort');assert.equal(await read(),'1.1.1.1\n8.8.8.8');
 for(const expected of ['8.8.8.8\n1.1.1.1',extracted,original]){await frame.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await read(),expected);}
 assert.equal(await workspaceFrame.evaluate(()=>document.querySelector('[data-text-tool]').textView.state.selection.main.head),15);
 for(const expected of [extracted,'8.8.8.8\n1.1.1.1','1.1.1.1\n8.8.8.8']){await frame.getByRole('button',{name:'Redo',exact:true}).click();assert.equal(await read(),expected);}
 assert(await frame.getByRole('button',{name:'Redo',exact:true}).isDisabled());
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
 assert.deepEqual(errors,[]);console.log('PASS: 500-line atomic undo/redo chain, selection, keyboard history, disabled buttons, formatting/highlighting/errors, retained editor/tab state, CyberChef loading and no window scrolling.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temporary,{recursive:true,force:true});});
