/* Real Flask/CodeMirror integration with an isolated database and real browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn, spawnSync} = require('node:child_process');
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

 const originals={attack:'### MITRE Attack\nOriginal attack',mbc:'### MITRE MBC\nOriginal behavior'};
 const ids=['mitre-attack-markdown','mitre-mbc-markdown'];
 async function load(){await page.goto(`${base}/cases/${cid}?tab=report`);await page.waitForFunction(()=>document.querySelector('#mitre-mbc-markdown') && window.MareEditors.getValue(document.querySelector('#mitre-mbc-markdown')).includes('Original'));}
 await page.goto(`${base}/cases/${cid}?tab=report`);
 await page.waitForSelector('#mitre-mbc-markdown',{state:'attached'});
 await page.waitForFunction(()=>document.querySelector('#report-save-status').textContent !== 'Loading…');
 for(const [i,id] of ids.entries())await page.locator('#'+id).evaluate((area,value)=>window.MareEditors.get(area).setValue(value,{notify:true}),Object.values(originals)[i]);
 await page.locator('#save-mitre-mappings').click();await page.locator('#mitre-mapping-status').filter({hasText:'saved to mappings'}).waitFor();
 const lock=spawnSync(python,['-c',`from app import app,run
with app.app_context():run('UPDATE cases SET stage=3 WHERE id=?',(${cid},))`],{cwd:root,env:{...process.env,MARE_DATA_DIR:temporary}});
 assert.equal(lock.status,0,lock.stderr.toString());
 await load();
 assert.equal(await page.locator('#save-mitre-mappings').isDisabled(),true);
 assert.equal(await page.locator('#build-mitre-prompt').isDisabled(),true);
 const writes=[];const record=request=>{if(request.method()==='POST'&&request.url().endsWith('/mitre-mappings'))writes.push(request.url());};page.on('request',record);
 for(const [i,id] of ids.entries()){
  const area=page.locator('#'+id),section=page.locator('#'+id+'-section'),content=section.locator('.cm-content');
  assert.equal(await area.evaluate(source=>window.MareEditors.get(source).readOnly),true);
  assert.equal(await content.getAttribute('contenteditable'),'false');
  for(const button of await section.locator('button[data-md]').all())assert.equal(await button.isDisabled(),true);
  await content.focus();await page.keyboard.type('Blocked typing');
  await content.evaluate(node=>{const data=new DataTransfer();data.setData('text/plain','Blocked paste/drop');node.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));node.dispatchEvent(new DragEvent('drop',{dataTransfer:data,bubbles:true,cancelable:true}));});
  await area.evaluate(source=>{const editor=window.MareEditors.get(source);editor.setSelection(0,5);editor.command('bold');editor.insert('Blocked insert');source.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await area.evaluate(source=>window.MareEditors.getValue(source)),Object.values(originals)[i]);
  assert.equal(await area.evaluate(source=>window.MareEditors.get(source).selection().to),5);
  await section.getByRole('button',{name:'Show Preview',exact:true}).click();await section.locator('.markdown-preview').filter({hasText:'Original'}).waitFor();
  await section.getByRole('button',{name:'Hide Preview',exact:true}).click();
  await section.locator('[data-editor-expand]').click();await section.getByRole('button',{name:'Collapse',exact:true}).click();
 }
 await page.locator('#save-mitre-mappings').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true})));
 await page.evaluate(()=>{window.originalNow=Date.now;Date.now=()=>window.originalNow()+6*60000;document.dispatchEvent(new Event('visibilitychange'));});
 await delay(1200);assert.deepEqual(writes,[]);page.off('request',record);
 const csrf=await page.locator('#report-form input[name=csrf]').first().inputValue();
 const rejected=await page.request.post(`${base}/cases/${cid}/mitre-mappings`,{form:{csrf,mitre_attack_markdown:'Replace',mitre_mbc_markdown:''}});assert.equal(rejected.status(),409);
 assert.deepEqual((await (await page.request.get(`${base}/cases/${cid}/report-data`)).json()).mitre_mappings,originals);
 await page.request.post(`${base}/cases/${cid}/reopen`,{form:{csrf}});await load();
 for(const id of ids){const area=page.locator('#'+id);assert.equal(await area.evaluate(source=>window.MareEditors.get(source).readOnly),false);await area.evaluate(source=>window.MareEditors.get(source).insert('Reopened edit '));}
 await page.locator('#save-mitre-mappings').click();await page.locator('#mitre-mapping-status').filter({hasText:'saved to mappings'}).waitFor();
 const result=(await (await page.request.get(`${base}/cases/${cid}/report-data`)).json()).mitre_mappings;assert.ok(result.attack.includes('Reopened edit ')&&result.mbc.includes('Reopened edit '));
 assert.deepEqual(errors,[]);console.log('PASS: open/closed/reopened MITRE editors, blocked typing/paste/drop/format/save/autosave, preview/expand/selection, server lock and preserved content.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temporary,{recursive:true,force:true});});
