const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'mare-yara-editor-')),port=8796,base=`http://127.0.0.1:${port}`;
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
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.setDefaultTimeout(12000);page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message);});
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await page.getByRole('button',{name:'Sign in',exact:true}).click();

 await page.goto(base+'/tools/yara-rule-editor');let f=page.frameLocator('iframe[title^="YARA Rule Editor"]'),tool=f.locator('[data-yara-tool]');await f.locator('[data-yara-tool][data-ready=true]').waitFor();
 const source=()=>tool.evaluate(r=>r.yaraView.state.doc.toString());
 const setSource=async(text,anchor=text.length)=>{await tool.evaluate((r,{text,anchor})=>r.yaraView.dispatch({changes:{from:0,to:r.yaraView.state.doc.length,insert:text},selection:{anchor}}),{text,anchor});await tool.evaluate(r=>new Promise(resolve=>{function check(){if(r.yaraAnalysisSource===r.yaraView.state.doc.toString())resolve();else requestAnimationFrame(check);}check();}));};
 const tab=name=>f.getByRole('tab',{name,exact:true}).click();
 // Options shares the existing dropdown and changes only the wrapping compartment.
 const options=f.locator('[data-options]'), summary=options.locator('summary'), wrapItem=f.getByRole('checkbox',{name:'Word wrap'});
 assert.equal(await f.locator('input[data-wrap]').count(),1);
 await summary.focus();await summary.press('ArrowDown');
 assert.equal(await summary.getAttribute('aria-expanded'),'true');
 assert.equal(String(await wrapItem.isChecked()),'true');
 await tool.evaluate(r=>{r.originalView=r.yaraView;r.wrapDoc=r.yaraView.state.doc;r.yaraView.dispatch({selection:{anchor:1,head:4}});r.wrapSelection=r.yaraView.state.selection.toJSON();});
 await options.locator('label').click();assert.ok(await options.evaluate(e=>e.open));assert.equal(String(await wrapItem.isChecked()),'false');
 await tool.evaluate(r=>new Promise(resolve=>{function check(){if(!r.yaraView.lineWrapping)resolve();else requestAnimationFrame(check);}check();}));
 assert.ok(await tool.evaluate(r=>r.yaraView===r.originalView && r.yaraView.state.doc===r.wrapDoc && JSON.stringify(r.yaraView.state.selection.toJSON())===JSON.stringify(r.wrapSelection) && !r.yaraView.lineWrapping));
 await wrapItem.press('Escape');assert.equal(await summary.getAttribute('aria-expanded'),'false');assert.ok(await summary.evaluate(e=>e===document.activeElement));
 await summary.click();await f.locator('h1').click();assert.equal(await summary.getAttribute('aria-expanded'),'false');
 await summary.click();await wrapItem.press('Space');assert.equal(String(await wrapItem.isChecked()),'true');await wrapItem.press('Space');assert.equal(String(await wrapItem.isChecked()),'false');await wrapItem.press('Escape');
 const checkSplit=async()=>assert.ok(await f.locator('.yara-split-control').evaluate(e=>{const b=e.getBoundingClientRect(),input=e.querySelector('input').getBoundingClientRect(),text=e.querySelector('span').getBoundingClientRect();return getComputedStyle(e.parentElement).alignItems==='center'&&Math.abs((input.top+input.bottom-text.top-text.bottom)/2)<2&&b.right<=innerWidth;}));
 await checkSplit();
 const initial='import "pe"\nrule browser_rule {\n strings:\n  $sample = "MARE_TEST" ascii\n condition:\n  $sa\n}\n';
 await setSource(initial,initial.lastIndexOf('$sa')+3);await f.locator('[data-complete]').click();await f.getByRole('option').filter({hasText:'$sample'}).first().click();assert.ok((await source()).includes('  $sample\n'));
 assert.ok(await f.locator('.cm-line .ͼb, .cm-line [class]').count());
 const completed=await source();await tool.evaluate((r,from)=>r.yaraView.dispatch({selection:{anchor:from,head:from+7}}),completed.lastIndexOf('$sample'));
 await tab('Conditions');await f.locator('[data-snippet-search]').fill('Any string');await f.locator('[data-snippets]').getByRole('button',{name:'Replace selection',exact:true}).click();assert.ok((await source()).includes('any of them'));await f.locator('[data-undo]').click();assert.equal(await source(),completed);await f.locator('[data-redo]').click();
 await tab('Metadata');await f.locator('[data-meta-key]').fill('author');await f.locator('[data-meta-value]').fill('analyst "review"');await f.locator('[data-meta-insert]').click();assert.ok((await source()).includes('author = '+JSON.stringify('analyst "review"')));const metadataSource=await source();await f.locator('[data-meta-insert]').click();assert.equal(await source(),metadataSource);assert.match(await f.locator('[data-meta-status]').textContent(),/already exists/);
 await tab('Completion');await f.locator('[data-module]').selectOption('math');await f.locator('[data-preview-import]').click();assert.ok(!(await source()).includes('import "math"'));await f.locator('[data-apply-import]').click();assert.ok((await source()).startsWith('import "math"'));await f.locator('[data-preview-import]').click();assert.equal((await source()).match(/import "math"/g).length,1);
 await tab('Test');await f.locator('[data-validate]').click();await f.locator('[data-validation]').filter({hasText:'Valid for classic YARA 4.5.4'}).waitFor();
 await f.locator('[data-positive]').setInputFiles({name:'positive.bin',mimeType:'application/octet-stream',buffer:Buffer.from('MARE_TEST')});await f.locator('[data-baseline]').setInputFiles({name:'benign.bin',mimeType:'application/octet-stream',buffer:Buffer.from('benign data')});await f.locator('[data-scan]').click();await f.locator('[data-results] h3').filter({hasText:'Positive sample · positive.bin · match'}).waitFor();await f.locator('[data-results] h3').filter({hasText:'Benign baseline · benign.bin · no match'}).waitFor();assert.match(await f.locator('[data-results]').textContent(),/\$sample · offset 0, length 9/);
 let saved=await source();await f.locator('[data-case]').selectOption('1');assert.equal(await source(),saved);await f.locator('[data-save-as]').click();await f.locator('[data-filename]').fill('../bad.yara');await f.locator('[data-confirm-save]').click();await f.locator('[data-save-error]').filter({hasText:'relative .yara'}).waitFor();assert.equal(await source(),saved);await f.locator('[data-filename]').fill('nested/browser.yara');await f.locator('[data-confirm-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();assert.equal(fs.readFileSync(path.join(data,'cases/1/mip/signatures/nested/browser.yara'),'utf8'),saved);
 // Editing during a slow save keeps new text dirty and advances the disk version.
 let saveRelease,saveHeld;const saveGate=new Promise(r=>saveRelease=r),saveStarted=new Promise(r=>saveHeld=r);
 await page.route('**/cases/1/yara-file',async route=>{const response=await route.fetch();saveHeld();await saveGate;await route.fulfill({response});});
 await setSource(saved+'// snapshot\n');await f.locator('[data-save]').click();await saveStarted;await setSource(saved+'// newer edit\n');saveRelease();await f.locator('[data-status]').filter({hasText:'Snapshot saved; newer edits remain unsaved'}).waitFor();assert.equal(await f.locator('[data-dirty]').textContent(),'Unsaved changes');await page.unroute('**/cases/1/yara-file');await f.locator('[data-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();saved=await source();assert.equal(fs.readFileSync(path.join(data,'cases/1/mip/signatures/nested/browser.yara'),'utf8'),saved);
 await setSource(saved+'// unsaved\n');await f.locator('[data-file-path="nested/browser.yara"]').click();await f.getByRole('button',{name:'Cancel',exact:true}).click();assert.ok((await source()).includes('// unsaved'));await f.locator('[data-file-path="nested/browser.yara"]').click();await f.getByRole('button',{name:'Discard',exact:true}).click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();assert.equal(await source(),saved);
 // A compiler response for an edited document must never paint it valid.
 let release,held;const gate=new Promise(r=>release=r),started=new Promise(r=>held=r);let intercepted=false;
 await page.route('**/tools/yara-rule-editor/jobs/*',async route=>{const response=await route.fetch();const result=await response.json();if(!intercepted&&!['queued','running'].includes(result.status)){intercepted=true;held();await gate;}await route.fulfill({response});});
 await tab('Test');await f.locator('[data-validate]').click();await started;await setSource(saved+'// newer source\n');release();await f.locator('[data-job-status]').filter({hasText:'older-source results discarded'}).waitFor();assert.equal(await f.locator('[data-validation]').textContent(),'Changed since last validation');await page.unroute('**/tools/yara-rule-editor/jobs/*');
 // Syntax error is compiler-owned and navigates to the reported source line.
 await setSource('rule Broken {\n condition: unknown_symbol\n}\n');await f.locator('[data-validate]').click();await f.locator('[data-validation]').filter({hasText:'Errors'}).waitFor();await tab('Problems');await f.locator('[data-compiler-problems] button').first().click();assert.equal(await tool.evaluate(r=>r.yaraView.state.doc.lineAt(r.yaraView.state.selection.main.head).number),2);
 // A dirty draft is recovered after reload; browser-native unload confirmation is expected.
 const recovered=saved+'// recover me\n';await setSource(recovered);await f.locator('[data-draft]').filter({hasText:'Recoverable account draft saved'}).waitFor();
 assert.equal(JSON.parse(fs.readFileSync(path.join(data,'yara-drafts',fs.readdirSync(path.join(data,'yara-drafts'))[0]),'utf8')).source,recovered);
 page.on('dialog',dialog=>dialog.accept());await page.reload();f=page.frameLocator('iframe[title^="YARA Rule Editor"]');tool=f.locator('[data-yara-tool]');await f.locator('[data-yara-tool][data-recovered=true]').waitFor();assert.equal(await source(),recovered);
 await f.locator('[data-options] summary').click();assert.equal(String(await f.getByRole('checkbox',{name:'Word wrap'}).isChecked()),'false');assert.ok(await tool.evaluate(r=>!r.yaraView.lineWrapping));await f.getByRole('checkbox',{name:'Word wrap'}).press('Escape');
 await page.getByRole('tab',{name:/CyberChef/}).click();await f.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await page.getByRole('tab',{name:/YARA Rule Editor/}).getAttribute('aria-selected'),'true');assert.equal(await source(),recovered);
 assert.equal(await f.locator('a:not(#yara-panel-docs a)').count(),0);assert.equal(await f.getByRole('tab').last().textContent(),'Docs');await page.setViewportSize({width:390,height:844});await f.locator('.yara-browser summary').click();await checkSplit();assert.ok(await tool.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await f.locator('[data-options] summary').click();await f.locator('#yara-options-menu').evaluate(e=>new Promise(resolve=>{function check(){const b=e.getBoundingClientRect();if(b.left>=0&&b.right<=innerWidth&&b.top>=0&&b.bottom<=innerHeight)resolve();else requestAnimationFrame(check);}check();}));await f.getByRole('checkbox',{name:'Word wrap'}).press('Escape');
 assert.deepEqual(errors,[]);console.log('PASS: YARA completion/highlighting, snippets/undo, metadata/imports, real compile and positive/baseline scan, complete case save/reopen, cancel/discard, stale diagnostics, source navigation, draft recovery and responsive dock.');
})().catch(e=>{console.error(e);console.error(log.slice(-1500));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(r=>server.once('exit',r));fs.rmSync(data,{recursive:true,force:true});});
