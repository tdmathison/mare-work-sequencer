/* Real Flask/CodeMirror integration with an isolated database and real browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mare-editor-browser-'));
const port = Number(process.env.MARE_EDITOR_TEST_PORT || 8779);
const base = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON_BIN || (fs.existsSync(path.join(root,'.venv/bin/python')) ? path.join(root,'.venv/bin/python') : 'python3');
const server = spawn(python, ['tests/browser/server.py'], {cwd:root, env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)},stdio:['ignore','ignore','pipe']});
let serverLog='';server.stderr.on('data',data=>{serverLog += data.toString();});
let browser;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let attempts=0;;attempts++) {
  try { await fetch(base+'/login');break; } catch(error) { if(attempts>=60 || server.exitCode !== null) throw new Error('Test server failed: '+serverLog);await delay(100); }
 }
 const executable = process.env.MARE_BROWSER_EXECUTABLE;
 browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const external=[];page.on('request',request=>{if(!request.url().startsWith(base) && /^https?:/.test(request.url()))external.push(request.url());});
 await page.goto(base+'/login');
 await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 const fixture=await (await page.request.get(base+'/__editor_test__')).json();
 const cid=fixture.cid;
 await page.goto(`${base}/account`);
 await page.locator('input[name=template]').setInputFiles(fixture.template);
 await Promise.all([page.waitForURL(base+'/account'),page.getByRole('button',{name:'Upload & select template',exact:true}).click()]);
 await page.goto(`${base}/cases/${cid}?tab=report`);
 const source='textarea[name=executive_summary]';
 const section=page.locator('.manual-section').filter({has:page.locator(source)});
 const content=section.locator('.cm-content');
 async function state(){return page.locator(source).evaluate(area=>{
  const editor=window.MareEditors.get(area);return {doc:editor.getValue(),selection:editor.selection(),scroll:editor.view.scrollDOM.scrollTop};
 });}
 async function setDocument(text,position=0){await page.locator(source).evaluate((area,{text,position})=>{const editor=window.MareEditors.get(area);editor.setValue(text,{notify:true});editor.setSelection(position);editor.focus();},{text,position});}
 async function checkGeometry(){
  const result=await page.locator(source).evaluate(area=>{
   const editor=window.MareEditors.get(area),view=editor.view,position=view.state.selection.main.head;
   const cursor=view.dom.querySelector('.cm-cursor-primary');
   const coords=view.coordsAtPos(position);
   const cursorRect=cursor?.getBoundingClientRect();
   const scrollRect=view.scrollDOM.getBoundingClientRect();
   const caretVisible=coords && coords.top>=scrollRect.top && coords.bottom<=scrollRect.bottom;
   const rows=[...view.dom.querySelectorAll('.cm-lineNumbers .cm-gutterElement')].filter(el=>/^\d+$/.test(el.textContent.trim()) && el.getBoundingClientRect().height>0 && Number(el.textContent.trim())<=view.state.doc.lines);
   const differences=rows.map(row=>{
    const number=Number(row.textContent.trim()),line=view.state.doc.line(number),block=view.lineBlockAt(line.from);
    return Math.abs(row.getBoundingClientRect().top-(view.documentTop+block.top));
   });
   return {scrollContainer:view.scrollDOM.contains(view.dom.querySelector('.cm-gutters')),maxGutterDifference:Math.max(0,...differences),cursorDifference:caretVisible&&cursorRect?Math.abs(coords.top-cursorRect.top):null,legacy:document.querySelectorAll('.markdown-highlight,.line-numbers').length};
  });
  assert.equal(result.scrollContainer,true,'gutter and text must share the scroller');
  assert.ok(result.maxGutterDifference<3,JSON.stringify(result));
  assert.equal(result.legacy,0);
  if(result.cursorDifference!==null)assert.ok(result.cursorDifference<3,JSON.stringify(result));
 }
 async function checkToolbar(workspace=section) {
  const view=workspace.locator('.markdown-menu').nth(2);
  assert.equal(await view.locator('button').count(),0,'View must contain only preferences');
  assert.equal(await view.locator('input[type=checkbox]').count(),4);
  const expandButton=workspace.locator('[data-editor-expand]');
  const expanded=await expandButton.getAttribute('aria-expanded')==='true';
  assert.equal((await expandButton.textContent()).trim().slice(1).trim(),expanded?'Collapse':'Expand');
  const previewButton=workspace.locator('[data-editor-preview]');
  if(await previewButton.count()) {
   const visible=await workspace.locator('.markdown-preview').evaluate(pane=>!pane.hidden);
   assert.equal((await previewButton.textContent()).trim().slice(1).trim(),visible?'Hide Preview':'Show Preview');
  }
  const geometry=await workspace.evaluate(node=>{
   const toolbar=node.querySelector('.markdown-toolbar').getBoundingClientRect();
   const active=node.querySelector('.markdown-editor:not([hidden]),.markdown-preview:not([hidden])').getBoundingClientRect();
   return {toolbar:{top:toolbar.top,bottom:toolbar.bottom},active:{top:active.top,height:active.height},expanded:node.classList.contains('editor-expanded')};
  });
  assert.ok(geometry.toolbar.bottom<=geometry.active.top+1,JSON.stringify(geometry));
  if(geometry.expanded)assert.ok(geometry.toolbar.top>=0 && geometry.toolbar.bottom<page.viewportSize().height,JSON.stringify(geometry));
  assert.ok(geometry.active.height>0,JSON.stringify(geometry));
  const groups=await workspace.evaluate(node=>{
   const toolbar=node.querySelector('.markdown-toolbar').getBoundingClientRect(),menus=node.querySelector('.markdown-toolbar-menus').getBoundingClientRect(),actions=node.querySelector('.markdown-toolbar-actions').getBoundingClientRect();
   return {toolbar:{left:toolbar.left,right:toolbar.right},menus:{left:menus.left,right:menus.right,bottom:menus.bottom},actions:{left:actions.left,right:actions.right,top:actions.top}};
  });
  assert.ok(groups.actions.right<=groups.toolbar.right+1 && groups.actions.left>=groups.toolbar.left-1);
  assert.ok(groups.actions.left>=groups.menus.right-1 || groups.actions.top>=groups.menus.bottom-1,'action group must not overlap menus');

 }
 async function checkMenus(workspace=section) {
  for(const menu of await workspace.locator('.markdown-menu').all()) {
   await menu.locator('summary').click();await delay(50);
   const box=await menu.locator('.markdown-menu-items').boundingBox();
   assert.ok(box.y>=7 && box.y+box.height<=page.viewportSize().height-7,JSON.stringify(box));
   assert.ok(box.x>=7 && box.x+box.width<=page.viewportSize().width-7,JSON.stringify(box));
   const last=menu.locator('.markdown-menu-items button,.markdown-menu-items input').last();
   await last.scrollIntoViewIfNeeded();
   assert.equal(await last.evaluate(node=>{
    const r=node.getBoundingClientRect();return node.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2));
   }),true,'last menu item must be visible and unobscured');
   await menu.locator('summary').click();
  }
 }
 await content.waitFor();
 await page.waitForFunction(expected=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]'))===expected,fixture.initial);
 assert.equal((await state()).doc,fixture.initial);
 await checkToolbar();await checkMenus();
 const initialEditorState=await state();
 await section.locator('[data-editor-preview]').click();await section.locator('.markdown-preview strong').waitFor();await checkToolbar();
 await section.locator('[data-editor-expand]').click();await checkToolbar();
 await section.locator('[data-editor-preview]').click();await section.locator('.markdown-preview strong').waitFor();await checkToolbar();
 await section.locator('[data-editor-expand]').click();await checkToolbar();
 assert.deepEqual(await state(),initialEditorState);
 // Legacy controls and keyboard actions must update the new buttons too.
 await section.locator('.editor-preview-tab').evaluate(node=>node.click());await delay(50);await checkToolbar();
 await section.locator('.editor-raw-tab').evaluate(node=>node.click());await delay(50);await checkToolbar();
 await section.locator('[data-editor-expand]').click();await page.keyboard.press('Escape');await delay(50);await checkToolbar();
 // A normal toolbar near the viewport bottom must flip its long menu upward.
 await section.locator('.markdown-toolbar').evaluate(node=>{const r=node.getBoundingClientRect();window.scrollBy(0,r.bottom-window.innerHeight+48);});
 await section.locator('.markdown-menu').first().locator('summary').click();await delay(50);
 assert.equal(await section.locator('.markdown-menu').first().evaluate(menu=>menu.querySelector('.markdown-menu-items').getBoundingClientRect().bottom<=menu.querySelector('summary').getBoundingClientRect().top+1),true);
 await section.locator('.markdown-menu').first().locator('summary').click();

 await section.locator('[data-editor-expand]').click();
 await checkToolbar();await checkMenus();
 await page.setViewportSize({width:1024,height:600});await delay(50);await checkToolbar();await checkMenus();
 await page.setViewportSize({width:360,height:640});await delay(50);await checkToolbar();await checkMenus();
 await page.setViewportSize({width:1366,height:900});
 // Regression corpus includes the exact inline/fenced wrap boundaries from the old overlay.
 const long=Array.from({length:700},(_,i)=>`${i} aaa \`bbb\` ${'long wrapped paragraph '.repeat(i%7+1)}`).join('\n')+'\n\n```python\n'+('a'.repeat(35)+'\n').repeat(20)+'```';
 await setDocument(long,0);
 await page.keyboard.type('BEGIN '+ 'continuous typing '.repeat(15));assert.ok((await state()).doc.startsWith('BEGIN '));
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(Math.floor(e.getValue().length/2));e.focus();});
 await page.keyboard.type('MIDDLE ');assert.ok((await state()).doc.includes('MIDDLE '));
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(e.getValue().length);e.focus();});
 await page.keyboard.type(' END');assert.ok((await state()).doc.endsWith(' END'));
 await delay(100);await checkGeometry();
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.view.scrollDOM.scrollTop=3000;});
 await delay(100);await checkGeometry();await checkToolbar();
 const toolbarBefore=await section.locator('.markdown-toolbar').boundingBox();
 await page.locator(source).evaluate(area=>window.MareEditors.get(area).view.scrollDOM.scrollTop+=1500);
 await delay(50);const toolbarAfter=await section.locator('.markdown-toolbar').boundingBox();assert.equal(toolbarAfter.y,toolbarBefore.y);
 const beforeWrap=await state();
 await section.locator('.markdown-menu').nth(2).locator('summary').click();await section.locator('.word-wrap').uncheck();assert.equal((await state()).doc,beforeWrap.doc);assert.deepEqual((await state()).selection,beforeWrap.selection);
 await section.locator('.word-wrap').check();await section.locator('.markdown-menu').nth(2).locator('summary').click();
 await page.setViewportSize({width:1920,height:1080});await delay(100);await checkGeometry();
 await page.setViewportSize({width:1366,height:768});await delay(100);await checkGeometry();
 // Let CodeMirror complete resize measurement before setting a test viewport.
 // Keep the original EditorView and its logical scroll anchor across expansion.
 await section.locator('[data-editor-expand]').click();await delay(100);
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);window.originalEditor=e.view;e.view.scrollDOM.scrollTop=2500;});
 await delay(100);const beforeExpand=await state();
 const beforeAnchor=await page.locator(source).evaluate(area=>{const v=window.MareEditors.get(area).view,p=v.scrollSnapshot().value.range.head;return {p,top:v.coordsAtPos(p)?.top-v.scrollDOM.getBoundingClientRect().top};});
 await section.locator('[data-editor-expand]').click();await delay(100);
 await section.locator('[data-editor-expand]').click();await delay(100);
 assert.equal(await page.locator(source).evaluate(area=>window.MareEditors.get(area).view===window.originalEditor),true);
 assert.equal((await state()).doc,beforeExpand.doc);assert.deepEqual((await state()).selection,beforeExpand.selection);
 const afterAnchor=await page.locator(source).evaluate((area,anchor)=>{const v=window.MareEditors.get(area).view;return {top:v.coordsAtPos(anchor.p)?.top-v.scrollDOM.getBoundingClientRect().top,p:v.scrollSnapshot().value.range.head};},beforeAnchor);
 // Virtualized off-screen heights may change scrollTop after width changes;
 // the visible document position and its screen offset must remain stable.
 assert.equal(afterAnchor.p,beforeAnchor.p,'expansion changed the visible document anchor');
 assert.ok(Math.abs(afterAnchor.top-beforeAnchor.top)<3,JSON.stringify({beforeAnchor,afterAnchor}));
 await section.locator('[data-editor-expand]').click();

 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.view.scrollDOM.scrollTop=6000;});
 await delay(100);
 const expandedSnapshot=await page.locator(source).evaluate(area=>{
  const e=window.MareEditors.get(area),snapshot=e.view.scrollSnapshot().value;
  return {position:snapshot.range.head,margin:snapshot.yMargin};
 });
 await section.locator('[data-editor-expand]').click();await delay(100);
 const restoredOffset=await page.locator(source).evaluate((area,snapshot)=>{
  const view=window.MareEditors.get(area).view;return view.lineBlockAt(snapshot.position).top-view.scrollDOM.scrollTop;
 },expandedSnapshot);
 // CodeMirror's anchor includes its content padding; allow one line for
 // rounding a wrapped-line anchor when widths change.
 assert.ok(Math.abs(restoredOffset-expandedSnapshot.margin)<24,`expanded viewport reset: ${restoredOffset} vs ${expandedSnapshot.margin}`);
 await section.locator('[data-editor-expand]').click();
 // Command transactions preserve logical-line boundaries and all selections.
 await page.locator(source).evaluate(area=>{
  const e=window.MareEditors.get(area),same=(actual,expected)=>{if(actual!==expected)throw Error(JSON.stringify({actual,expected}));};
  for(let level=1;level<=6;level++) {
   e.setValue('### Malware Configuration\nUnrelated');e.setSelection(5,12);e.command('h'+level);
   same(e.getValue(),'#'.repeat(level)+' Malware Configuration\nUnrelated');
   e.command('h'+level);same(e.getValue(),'#'.repeat(level)+' Malware Configuration\nUnrelated');
   e.command('paragraph');same(e.getValue(),'Malware Configuration\nUnrelated');
  }
  e.setValue('one\ntwo\nthree');e.setSelection(0,8);e.command('h2');same(e.getValue(),'## one\n## two\nthree');
  for(const [command,marker] of [['bold','**'],['italic','*'],['strike','~~'],['inline-code','`']]) {
   e.setValue('text');e.setSelection(0,4);e.command(command);same(e.getValue(),marker+'text'+marker);
   e.command(command);same(e.getValue(),'text');
   e.setValue('');e.setSelection(0);e.command(command);same(e.getValue(),marker+marker);same(e.selection().head,marker.length);
  }
  for(const [command,expected] of [['bullet','- one\n- two'],['numbered','1. one\n2. two'],['quote','> one\n> two']]) {
   e.setValue('one\ntwo');e.setSelection(0,7);e.command(command);same(e.getValue(),expected);e.command(command);same(e.getValue(),'one\ntwo');
  }
  e.setValue('one');e.setSelection(1);e.command('code');same(e.getValue(),'```\none\n```');
  e.setValue('line');e.setSelection(0,4);e.command('indent');if(!/^\s+line$/.test(e.getValue()))throw Error('indent failed');e.command('outdent');same(e.getValue(),'line');
  e.setValue('first second');
  const Selection=e.view.state.selection.constructor;
  e.view.dispatch({selection:Selection.create([Selection.range(0,5),Selection.range(6,12)])});
  same(e.view.state.selection.ranges.length,2);e.command('bold');same(e.getValue(),'**first** **second**');e.command('bold');same(e.getValue(),'first second');
  const previous=e.view.state.selection;
  for(const setting of ['wrap','numbers','active','folding']) { e.setPreference(setting,false);e.setPreference(setting,true); }
  same(e.getValue(),'first second');if(!e.view.state.selection.eq(previous))throw Error('preferences lost selections');
  const table=window.MareEditors.pastedTable;
  same(table('', 'A\tB\r\nx|y\t\r\nq\tr\textra\r\n'),'| A | B |  |\n| --- | --- | --- |\n| x\\|y |  |  |\n| q | r | extra |');
  same(table('<table><tr><th rowspan="2">A</th><th colspan="2">B</th></tr><tr><td>x</td><td>y<script>bad</script></td></tr></table>'),'| A | B |  |\n| --- | --- | --- |\n|  | x | y |');
  same(table('<p>No table</p>','A\tB\n1\t2'),'| A | B |\n| --- | --- |\n| 1 | 2 |');
  same(table('', 'A\tB\n\t\n'),'| A | B |\n| --- | --- |\n|  |  |');
 });
 // Undo remains available after preference reconfiguration, and typing uses both cursors.
 await page.keyboard.press(process.platform==='darwin'?'Meta+z':'Control+z');assert.equal((await state()).doc,'**first** **second**');
 await page.keyboard.press(process.platform==='darwin'?'Meta+Shift+z':'Control+Shift+z');assert.equal((await state()).doc,'first second');
 await page.keyboard.type('X');assert.equal((await state()).doc,'X X');
 await setDocument('# Heading\nbody\n## Child\nchild body\n\n```python\na=1\n```\n\n# Next\nend');
 await delay(150);await section.locator('.cm-foldGutter .cm-gutterElement').filter({hasText:'⌄'}).first().click();
 assert.ok(await section.locator('.cm-foldPlaceholder').count());
 await section.locator('.cm-foldPlaceholder').first().click();
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(e.getValue().indexOf('```python'));e.focus();});
 await page.keyboard.press(process.platform==='darwin'?'Meta+Alt+[':'Control+Shift+[');
 assert.ok(await section.locator('.cm-foldPlaceholder').count(),'fenced code must fold');
 await page.keyboard.press(process.platform==='darwin'?'Meta+Alt+]':'Control+Shift+]');
 assert.equal(await section.locator('.cm-foldPlaceholder').count(),0);

 // Native dialog: dimensions, safe insertion inside prose, first-cell caret, undo.
 await setDocument('BeforeAfter',6);
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=table]').click();
 await section.locator('[data-table-size=columns]').fill('3');await section.locator('[data-table-size=rows]').fill('2');await section.locator('[data-table-create]').click();
 assert.equal((await state()).doc,'Before\n\n| Column1 | Column2 | Column3 |\n| --- | --- | --- |\n|  |  |  |\n|  |  |  |\n\nAfter');
 assert.equal((await state()).selection.head,10);
 await page.keyboard.press(process.platform==='darwin'?'Meta+z':'Control+z');assert.equal((await state()).doc,'BeforeAfter');
 await page.keyboard.press(process.platform==='darwin'?'Meta+Shift+z':'Control+Shift+z');assert.ok((await state()).doc.includes('| Column1 |'));
 await setDocument('selected text');await page.locator(source).evaluate(area=>window.MareEditors.get(area).setSelection(0,8));
 await section.locator('.markdown-menu').first().locator('summary').click();await section.locator('[data-md=bold]').click();assert.equal((await state()).doc,'**selected** text');
 await content.click();await page.keyboard.press(process.platform==='darwin'?'Meta+z':'Control+z');assert.equal((await state()).doc,'selected text');
 await page.keyboard.press(process.platform==='darwin'?'Meta+Shift+z':'Control+Shift+z');assert.equal((await state()).doc,'**selected** text');
 await section.locator('.markdown-menu').first().locator('summary').click();await section.locator('[data-md=h2]').click();assert.ok((await state()).doc.startsWith('## '));
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=url]').click();assert.ok((await state()).doc.includes('https://example.com'),JSON.stringify({state:await state(),errors}));
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=table]').click();await section.locator('[data-table-size=columns]').fill('3');await section.locator('[data-table-size=rows]').fill('2');await section.locator('[data-table-create]').click();assert.ok((await state()).doc.includes('| Column1 | Column2 | Column3 |'));await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(e.getValue().length);});
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=html-table]').click();
 await section.locator('.markdown-table-input').fill('<table><tr><th>A</th><th>B</th></tr><tr><td>x</td><td>y</td></tr></table>');
 await section.locator('[data-html-table-convert]').click();assert.ok((await state()).doc.includes('| A | B |'));
 assert.equal(await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);const line=e.view.state.doc.lineAt(e.selection().head);return line.text;}),'','Paste Table caret must land on a blank line after the table');

 // Clipboard HTML wins over misleading TSV, and only extracted text is inserted.
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(e.getValue().length);});
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=html-table]').click();
 await section.locator('.markdown-table-input').evaluate(input=>{
  const data=new DataTransfer();data.setData('text/html','<table><tr><th>Clipboard HTML</th><th>B</th></tr><tr><td>safe<script>bad()</script></td><td></td></tr></table>');data.setData('text/plain','Wrong\tTSV\n1\t2');
  input.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));
 });
 await section.locator('[data-html-table-convert]').click();
 assert.ok((await state()).doc.includes('| Clipboard HTML | B |'));assert.ok(!(await state()).doc.includes('bad()'));
 // Escape closes the modal while retaining the expanded editor and its source.
 await section.locator('.markdown-menu').nth(1).locator('summary').click();await section.locator('[data-md=table]').click();
 await section.locator('[data-table-size=columns]').fill('0');await section.locator('[data-table-create]').click();assert.equal(await section.locator('.markdown-insert-table-dialog').evaluate(node=>node.open),true);
 await page.keyboard.press('Escape');assert.equal(await section.evaluate(node=>node.classList.contains('editor-expanded')),true);
 // Local image uploads use the same existing storage/caption conventions.
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN9sAAAAASUVORK5CYII=','base64');
 await section.locator('.markdown-image-input').setInputFiles({name:'figure.png',mimeType:'image/png',buffer:png});
 await page.waitForFunction(()=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]')).includes('::: figure'));
 assert.ok((await state()).doc.includes('*Figure 1:*'));

 async function clipboardOrDrop(kind,rich=false) {
  await content.evaluate((el,{base64,kind,rich})=>{
   const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));const transfer=new DataTransfer();
   transfer.items.add(new File([bytes],'browser-image.png',{type:'image/png'}));
   if(rich)transfer.setData('text/plain',' ordinary text paste ');
   if(kind==='drop') {const rect=el.getBoundingClientRect();el.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer,clientX:rect.left+20,clientY:rect.top+10}));}
   else el.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:transfer}));
  },{base64:png.toString('base64'),kind,rich});
 }
 await clipboardOrDrop('drop');await page.waitForFunction(()=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]')).includes('*Figure 2:*'));
 await clipboardOrDrop('paste');await page.waitForFunction(()=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]')).includes('*Figure 3:*'));
 await clipboardOrDrop('paste',true);await page.waitForFunction(()=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]')).includes('ordinary text paste'));
 assert.ok(!(await state()).doc.includes('*Figure 4:*'),'rich clipboard should paste text instead of uploading its image');
 const beforePreview=await state();await section.locator('[data-editor-preview]').click();await section.locator('.markdown-preview img').first().waitFor();await checkToolbar();await checkMenus();
 assert.equal((await state()).doc,beforePreview.doc);await section.locator('[data-editor-preview]').click();
 // Ctrl/Cmd-F is CodeMirror's local search panel, not a browser search overlay.
 await content.click();await page.keyboard.press(process.platform==='darwin'?'Meta+f':'Control+f');await section.locator('.cm-search').waitFor();
 await section.locator('.cm-search [name=search]').fill('Column1');await section.locator('.cm-search [name=search]').press('ArrowRight');
 await section.locator('.cm-search input[name=replace]').fill('Header1');await section.locator('.cm-search input[name=replace]').press('ArrowRight');
 await section.locator('.cm-search [name=replaceAll]').click();assert.ok((await state()).doc.includes('| Header1 |'));
 await page.keyboard.press('Escape');assert.ok(await section.evaluate(el=>el.classList.contains('editor-expanded')),'search Escape must not collapse editor');
 if(process.env.MARE_EDITOR_SCREENSHOT)await page.screenshot({path:process.env.MARE_EDITOR_SCREENSHOT});
 await section.locator('[data-editor-expand]').click();
 // Independent non-expanded section previews may finish out of order.
 const second=page.locator('.manual-section').filter({has:page.locator('textarea[name=key_findings]')});
 await page.locator('textarea[name=key_findings]').evaluate(area=>window.MareEditors.get(area).setValue('Other section preview',{notify:true}));
 let previewRelease;const previewBlocked=new Promise(resolve=>{previewRelease=resolve;});
 let previewCount=0;
 await page.route(`**/cases/${cid}/markdown-preview`,async route=>{if(++previewCount===1)await previewBlocked;await route.continue();});
 await section.locator('[data-editor-preview]').click();
 await second.locator('[data-editor-preview]').click();
 await second.locator('.markdown-preview').filter({hasText:'Other section preview'}).waitFor();previewRelease();await section.locator('.markdown-preview img').first().waitFor();
 await page.unroute(`**/cases/${cid}/markdown-preview`);
 for(const workspace of [section,second]) {await workspace.locator('[data-editor-preview]').click();}
 await page.locator('textarea[name=key_findings]').evaluate(area=>window.MareEditors.get(area).setValue('',{notify:true}));
 // Save with a delayed response while more text is typed; no editor reset is allowed.
 let release;const blocked=new Promise(resolve=>{release=resolve;});
 await page.route(`**/cases/${cid}/report-sections`,async route=>{await blocked;await route.continue();});
 const manualRequest=page.waitForRequest(request=>request.url().endsWith('/report-sections'));
 const manualResponse=page.waitForResponse(response=>response.url().endsWith('/report-sections'));
 await page.locator('#save-sections').click();await manualRequest;
 await page.locator(source).evaluate(area=>{const e=window.MareEditors.get(area);e.setSelection(e.getValue().length);e.insert('\nNewer typing during save');});
 await delay(100);const duringSave=await state();release();const savedResponse=await manualResponse;await delay(150);assert.match(await page.locator('#report-save-status').textContent(),/newer changes pending/,JSON.stringify({http:savedResponse.status(),errors,doc:(await state()).doc}));
 assert.deepEqual(await state(),duringSave);
 await page.unroute(`**/cases/${cid}/report-sections`);
 let releaseAutosave;const autosaveBlocked=new Promise(resolve=>{releaseAutosave=resolve;});
 await page.route(`**/cases/${cid}/report-sections`,async route=>{await autosaveBlocked;await route.continue();});
 const automaticRequest=page.waitForRequest(request=>request.url().endsWith('/report-sections') && (request.postData()||'').includes('name="automatic"'));
 await page.evaluate(()=>{window.originalDateNow=Date.now;Date.now=()=>window.originalDateNow()+6*60000;});
 await automaticRequest;
 await page.locator(source).evaluate(area=>window.MareEditors.get(area).insert(' and autosave typing'));
 await delay(100);const duringAutosave=await state();
 const automaticResponse=page.waitForResponse(response=>response.url().endsWith('/report-sections') && response.request().method()==='POST');
 releaseAutosave();await automaticResponse;
 await page.locator('#report-save-status').filter({hasText:'newer changes pending'}).waitFor();
 assert.deepEqual(await state(),duringAutosave);
 await page.unroute(`**/cases/${cid}/report-sections`);
 await page.evaluate(()=>{Date.now=window.originalDateNow;});

 await Promise.all([page.waitForResponse(response=>response.url().endsWith('/report-sections') && response.request().method()==='POST'),page.locator('#save-sections').click()]);await page.locator('#report-save-status').filter({hasText:'Report sections saved'}).waitFor();
 const saved=(await state()).doc;
 await page.reload();await page.waitForFunction(saved=>window.MareEditors.getValue(document.querySelector('textarea[name=executive_summary]'))===saved,saved);
 assert.equal((await state()).doc,saved);
 await page.locator('#generate-report-pdf').uncheck();await page.locator('#generate-manual-report').click();
 await page.locator('#report-job-status').filter({hasText:'completed'}).waitFor({timeout:30000});
 const generated=await (await page.request.get(base+'/__editor_test__')).json();assert.ok(generated.paragraphs.some(text=>text.includes('Newer typing during save')));assert.equal(generated.inline_shapes,3);
 // Task dialog, dynamically initialized MITRE editors, Markdown-file editing.
 await page.locator('#tab-tasks').click();await page.locator('[data-open-task="add-task-dialog"]').click();
 const task=page.locator('#add-task-dialog');await checkToolbar(task);await checkMenus(task);await task.locator('[name=name]').fill('CM task');await task.locator('.cm-content').fill('Task **Markdown**');
 assert.equal(await task.locator('textarea[name=description]').evaluate(area=>new FormData(area.form).get('description')),'Task **Markdown**');
 await task.locator('[data-editor-preview]').click();await task.locator('.markdown-preview strong').waitFor();await checkToolbar(task);await checkMenus(task);await task.locator('[data-editor-preview]').click();
 await task.getByRole('button',{name:'Create task'}).click();await page.waitForURL(`**/cases/${cid}?tab=tasks`);assert.ok(await page.locator('.task-body').filter({hasText:'Task **Markdown**'}).count());
 await page.locator('#tab-report').click();
 await page.locator('#mitre-attack-markdown').evaluate(area=>window.MareEditors.get(area).insert('### MITRE Attack\n\nSaved mapping'));
 await page.locator('#save-mitre-mappings').click();await page.locator('#mitre-mapping-status').filter({hasText:'saved to mappings'}).waitFor();
 await page.goto(`${base}/cases/${cid}/file?path=mappings/mitre-attack.md`);
 await page.locator('.cm-content').waitFor();assert.equal(await page.locator('textarea[name=content]').evaluate(area=>window.MareEditors.getValue(area)), '### MITRE Attack\n\nSaved mapping');
 await page.locator('.mare-editor-workspace [data-editor-expand]').click();
 assert.equal(await page.locator('.mare-editor-workspace').evaluate(node=>node.classList.contains('mare-editor-expanded')),true);await checkToolbar(page.locator('.mare-editor-workspace'));await checkMenus(page.locator('.mare-editor-workspace'));
 await page.keyboard.press('Escape');assert.equal(await page.locator('.mare-editor-workspace').evaluate(node=>node.classList.contains('mare-editor-expanded')),false);
 await page.locator('textarea[name=content]').evaluate(area=>window.MareEditors.get(area).insert('\nEdited file'));
 await page.getByRole('button',{name:'Save file'}).click();await page.waitForURL(`**/cases/${cid}`);
 await page.locator('#tab-tasks').click();await page.locator('[data-open-task="add-task-dialog"]').click();
 assert.equal(await page.locator('#add-task-dialog textarea[name=description]').evaluate(area=>window.MareEditors.getValue(area)),'');
 await page.locator('#add-task-dialog .cm-content').fill('Discard this draft');
 await page.locator('#add-task-dialog .markdown-menu').nth(2).locator('summary').click();await page.locator('#add-task-dialog .word-wrap').uncheck();
 await page.locator('#add-task-dialog [data-close-task-dialog]').click();
 await page.locator('[data-open-task="add-task-dialog"]').click();
 assert.equal(await page.locator('#add-task-dialog textarea[name=description]').evaluate(area=>window.MareEditors.getValue(area)),'');
 await page.locator('#add-task-dialog [data-close-task-dialog]').click();

 await page.evaluate(()=>{
  const source=document.createElement('textarea');source.dataset.markdownEditor='';source.maxLength=5;source.value='abc';document.body.append(source);
  const editor=window.MareEditors.create(source);editor.setSelection(3);editor.insert('too long');
  if(editor.getValue()!=='abc')throw new Error('maxlength not enforced');
  editor.setReadOnly(true);editor.insert('x');if(editor.getValue()!=='abc')throw new Error('read-only edit allowed');
  editor.setReadOnly(false);editor.insert('x');if(editor.getValue()!=='abcx')throw new Error('unlock failed');
  editor.destroy();if(source.hidden || source.value!=='abcx' || source.parentElement!==document.body)throw new Error('cleanup failed');source.remove();
 });
 assert.equal(await page.locator('#add-task-dialog textarea[name=description]').evaluate(area=>window.MareEditors.get(area).view.lineWrapping),true);
 assert.equal(errors.length,0,errors.join('\n'));assert.deepEqual(external,[]);
 console.log('PASS: saved Markdown, 700 lines, cursor/gutter geometry, wrapping, scroll, resize, expand, all headings/inline toggles/lists, multicursor typing, folding, View preferences/history, HTML/TSV/span tables, modal validation, top toolbar/viewport dropdowns, search, image picker/drop/paste, preview, concurrent manual/autosave, reload, Word report, tasks, mappings, Markdown files; no browser errors or external requests.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temporary,{recursive:true,force:true});});
