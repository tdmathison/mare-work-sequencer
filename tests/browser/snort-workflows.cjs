const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'mare-snort-editor-')),port=8794,base=`http://127.0.0.1:${port}`;
const fake=process.env.MARE_SNORT_BROWSER_FAKE==='1';let engineSettings={MARE_SNORT_EXECUTABLE:''};
if(fake){
 const executable=path.join(data,'fake-snort'),runner=path.join(data,'fake-runner'),profile=path.join(data,'snort.lua');
 fs.writeFileSync(executable,`#!${path.join(root,'.venv/bin/python')}
import sys
if '-V' in sys.argv:print('Snort++ Version 3.1.99 fake UI fixture')
elif '--help-options' in sys.argv:print('-T -R -r -c --lua -A -l')
else:print('content http_uri alert_json')
`,{mode:0o700});
 fs.writeFileSync(runner,`#!${path.join(root,'.venv/bin/python')}
import sys,time,json,pathlib
w=pathlib.Path(sys.argv[3])
if '-r' in sys.argv:
 time.sleep(1)
 name=sys.argv[sys.argv.index('-r')+1]
 (w/'alert_json.txt').write_text(json.dumps(dict(rule='1:1000001:1',msg='FAKE UI ONLY',pkt_num=1))+'\\n' if 'target' in name else '')
print('FAKE ENGINE: lifecycle fixture, not Snort validation')
`,{mode:0o700});
 fs.writeFileSync(profile,'-- fake profile only');engineSettings={MARE_SNORT_EXECUTABLE:executable,MARE_SNORT_PROFILE:profile,MARE_SNORT_RUNNER:runner};
}
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{cwd:root,env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:data,MARE_EDITOR_TEST_PORT:String(port),...engineSettings},stdio:['ignore','ignore','pipe']});let log='',browser;server.stderr.on('data',b=>log+=b);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message);});
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.goto(base+'/tools/snort-rule-builder');const f=page.frameLocator('iframe[title^="Snort Rule Builder"]'),tool=f.locator('[data-snort-tool]');await f.locator('[data-draft]').filter({hasText:'Standalone draft ready'}).waitFor();

 const source=()=>tool.evaluate(r=>r.snortView.state.doc.toString());
 const settle=()=>tool.evaluate(r=>new Promise((resolve,reject)=>{let tries=0;function check(){if(++tries>300)return reject(Error("Parse did not settle"));if(r.snortModel?.source===r.snortView.state.doc.toString())resolve();else requestAnimationFrame(check);}check();}));
 const setSource=async text=>{await tool.evaluate((r,text)=>r.snortView.dispatch({changes:{from:0,to:r.snortView.state.doc.length,insert:text}}),text);await settle();};
 const tab=async name=>{await f.getByRole('tab',{name,exact:true}).click();};
 const where=scope=>f.locator('[data-insertion-controls="'+scope+'"] select');
 await f.locator('[data-new]').click();await settle();await tab('Request bytes');assert.match(await where('bytes').inputValue(),/:end$/);
 const empty='alert tcp any any -> any 80 (msg:"empty"; sid:1; rev:1;)';
 await setSource(empty);await tab('Request bytes');await where('bytes').selectOption({label:'End of option block'});
 await f.locator('[data-hex]').fill('41 22 5c 00 7c');await f.locator('[data-read-bytes]').click();
 await f.locator('[data-byte-end]').fill('5');assert.match(await f.locator('[data-byte-preview]').textContent(),/5 bytes/);
 assert.equal(await f.locator('[data-bytes-position]').isDisabled(),true);
 await f.locator('[data-bytes-add]').click();assert.match(await source(),/content:"\|41 22 5c 00 7c\|";/);assert.equal(await f.locator('[data-byte-end]').inputValue(),'5');
 assert.match(await f.locator('[data-byte-status]').textContent(),/Added content/);assert.equal(await f.locator('[data-dirty]').textContent(),'Unsaved changes');
 await f.locator('[data-origin]').selectOption('payload');await where('bytes').selectOption('');assert.equal(await f.locator('[data-bytes-position]').isDisabled(),false);await where('bytes').selectOption({label:'End of option block'});await f.locator('[data-origin]').selectOption('');
 await f.locator('[data-byte-view]').click();assert.equal(await f.locator('[data-outline] button[aria-pressed=true]').count(),1);
 const withBytes=await source();await f.locator('[data-undo]').click();await settle();assert.equal(await source(),empty);assert.equal(await f.locator('[data-outline] button[data-component*=":content:"]').count(),0);
 await f.locator('[data-redo]').click();await settle();assert.equal(await source(),withBytes);
 // No preselected match: the library offers its own corrective match selector.
 await setSource(empty.replace('sid:1;','content:"first"; content:"second"; sid:1;'));
 await tab('Option library');await f.locator('[data-library-search]').fill('nocase');await f.locator('[data-library]').getByRole('button',{name:'Apply nocase',exact:true}).click();
 assert.match(await f.locator('[data-library-status]').textContent(),/Choose a content match/);
 await f.locator('[data-library-match]').selectOption({index:1});await f.locator('[data-library]').getByRole('button',{name:'Apply nocase',exact:true}).click();assert.equal((await source()).match(/nocase/g).length,1);
 await f.locator('[data-library]').getByRole('button',{name:'Apply nocase',exact:true}).click();assert.match(await f.locator('[data-library-status]').textContent(),/Already applied/);assert.equal((await source()).match(/nocase/g).length,1);
 await f.locator('[data-library-view]').click();await f.locator('[data-outline] button[data-component*=":content:"]').nth(1).click();await tab('Option library');await f.locator('[data-library]').getByRole('button',{name:'Apply nocase',exact:true}).click();assert.equal((await source()).match(/nocase/g).length,2);
 await where('library').selectOption({index:1});
 await tool.evaluate(r=>r.snortView.dispatch({changes:{from:0,insert:'# prefix comment\n'}}));await settle();assert.match(await where('library').inputValue(),/:before$/);
 const targetValue=await where('library').inputValue();await tab('Request bytes');assert.equal(await where('bytes').inputValue(),targetValue);await tab('Option library');
 await f.locator('[data-library-search]').fill('content');await f.locator('[data-library]').getByRole('button',{name:'Add content match',exact:true}).click();await f.locator('[data-library-config]').getByLabel('Content value',{exact:true}).fill('library value');await f.locator('[data-library-config]').getByRole('button',{name:'Add content match',exact:true}).click();
 assert.ok((await source()).indexOf('library value')<(await source()).indexOf('content:"first"'));
 // Sticky buffer resolution is visible and preserves both existing matches.
 const sticky='alert tcp any any -> any 80 (http_uri; content:"one"; content:"two"; sid:1;)';await setSource(sticky);
 await f.locator('[data-dialect]').selectOption('snort3');await settle();await tab('Request bytes');await where('bytes').selectOption({index:2});await f.locator('[data-byte-buffer]').selectOption('file_data');assert.match(await f.locator('[data-byte-effect]').textContent(),/http_uri is restored/);await f.locator('[data-bytes-add]').click();
 assert.deepEqual(await tool.evaluate(r=>r.snortModel.components.filter(c=>c.kind==='content').map(c=>c.bufferName)),['http_uri','file_data','http_uri']);
 // An explicit stale target is invalidated, never silently rebound by ordinal.
 await setSource(sticky);await where('bytes').selectOption({index:2});await setSource(sticky.replace('"one"','"changed"'));assert.equal(await f.locator('[data-bytes-add]').isDisabled(),true);assert.match(await f.locator('[data-byte-effect]').textContent(),/Choose an insertion location/);assert.equal(await f.locator('[data-hex]').inputValue(),'41 22 5c 00 7c');
 await setSource(sticky.replace('content:"two"','content:"two",distance 0'));await where('bytes').selectOption({index:2});assert.equal(await f.locator('[data-bytes-add]').isDisabled(),true);assert.match(await f.locator('[data-byte-effect]').textContent(),/relative/);
 // A library placeholder is explicit and selected for source correction.
 await where('bytes').selectOption({label:'End of option block'});await tab('Option library');await f.locator('[data-library-search]').fill('pcre');await f.locator('[data-library]').getByRole('button',{name:'Configure pcre',exact:true}).click();await f.locator('[data-library-config]').getByRole('button',{name:'Insert source template',exact:true}).click();assert.equal(await tool.evaluate(r=>r.snortView.state.sliceDoc(r.snortView.state.selection.main.from,r.snortView.state.selection.main.to)),'REPLACE_ME');
 // Save confines new byte matches to the selected middle signature.
 const signatures=path.join(data,'cases/1/mip/signatures');fs.mkdirSync(signatures,{recursive:true});const original=empty+'\r\n'+empty+'\r\n'+empty;fs.writeFileSync(path.join(signatures,'workflow.rules'),original);
 await tab('Construct');await f.locator('[data-case]').selectOption('1');await f.getByRole('button',{name:'Discard changes',exact:true}).click();await f.locator('[data-file-path="workflow.rules"]').click();await f.locator('[data-signature-position="2"]').click();await f.locator('[data-load-signature]').click();await tab('Request bytes');await f.locator('[data-byte-buffer]').selectOption('payload');await where('bytes').selectOption({label:'End of option block'});await f.locator('[data-bytes-add]').click();const edited=await source();await f.locator('[data-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();assert.equal(fs.readFileSync(path.join(signatures,'workflow.rules'),'utf8'),empty+'\r\n'+edited+'\r\n'+empty);
 assert.deepEqual(errors,[]);console.log('PASS: byte insertion/preview/retention, library configuration/modifiers, duplicate prevention, stable targets, sticky restoration, unsafe cursor checks, atomic undo/redo and selected-signature save.');
})().catch(e=>{console.error(e);console.error(log.slice(-1500));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(r=>server.once('exit',r));fs.rmSync(data,{recursive:true,force:true});});
