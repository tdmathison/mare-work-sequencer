/* Account-bound review UI fixture; never applies synthetic case snapshots. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-sync-review-'));
const python=path.join(root,'.venv/bin/python'),port=8785,base=`http://127.0.0.1:${port}`,operation='11111111-1111-4111-8111-111111111111';
const env={...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:String(port)};
const server=spawn(python,['tests/browser/server.py'],{cwd:root,env,stdio:['ignore','ignore','pipe']});let browser,log='';server.stderr.on('data',data=>log+=data);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>60||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 const seed=spawnSync(python,['-c',`import sys,json,time
sys.path.insert(0,'tests')
from app import app,db
from test_sync_review import mixed_plan
from sync_review import OUTCOMES
with app.app_context():
 user=db().execute('SELECT id,user_uuid FROM users LIMIT 1').fetchone()
 for suffix,status,plan,outcomes in [('111111111111','preview',mixed_plan(),[]),('222222222222','complete',mixed_plan(),[{'index':i,'action':action,'reason':'Recorded outcome','destination_number':'CM-TEST'} for i,action in enumerate(OUTCOMES)]),('333333333333','preview',{'items':[]},[])]:
  key='11111111-1111-4111-8111-'+suffix
  db().execute('INSERT INTO sync_imports(id,user_id,user_uuid,filename,checksum,created,stage,status,plan,outcomes) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,user['id'],user['user_uuid'],'fixture.zip','0'*64,time.time(),key,status,json.dumps(plan),json.dumps(outcomes)))
 db().commit()`],{cwd:root,env});assert.equal(seed.status,0,seed.stderr.toString());
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/import-export/review/'+operation);
 const toggles=page.locator('[data-sync-toggle]');
 assert.deepEqual(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-expanded'))),['true','true','true','true','false','false']);
 assert.equal(new Set(await toggles.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-controls')))).size,6);
 await page.locator('[name=decision-2]').selectOption('replace');assert.ok(await page.locator('[data-sync-replacement]').isVisible());
 assert.match(await page.locator('[data-sync-plan]').textContent(),/1 replacement/);
 await toggles.first().focus();await toggles.first().press('Enter');assert.equal(await toggles.first().getAttribute('aria-expanded'),'false');assert.equal(await toggles.first().evaluate(e=>getComputedStyle(e).outlineStyle),'solid');
 await toggles.first().press('Space');assert.equal(await page.locator('[name=decision-2]').inputValue(),'replace');
 for(let i=0;i<2;i++){await page.getByRole('button',{name:'Collapse All',exact:true}).click();await page.getByRole('button',{name:'Expand All',exact:true}).click();}
 assert.equal(await page.locator('[name=decision-2]').inputValue(),'replace');
 assert.equal(await page.locator('[data-sync-row]').first().getAttribute('data-index'),'2');
 await page.locator('[name=decision-2]').selectOption('keep');assert.match(await page.locator('[data-sync-plan]').textContent(),/0 replacements/);assert.equal(await page.locator('[data-sync-replacement]').isVisible(),false);
 await page.locator('[name=decision-5]').selectOption('link');await toggles.first().click();
 await page.getByRole('button',{name:'Apply valid cases and selected decisions'}).click();assert.equal(await toggles.first().getAttribute('aria-expanded'),'true');assert.equal(await page.locator('[name=target-5]').evaluate(e=>e===document.activeElement),true);
 await page.locator('[name=target-5]').selectOption('1');assert.match(await page.locator('[data-sync-plan]').textContent(),/0 unresolved/);assert.match(await page.locator('[data-sync-plan]').textContent(),/1 provenance-only links/);
 await page.route('**/import-export/apply/**',async route=>{const data=new URLSearchParams(route.request().postData());assert.equal(data.get('decision-2'),'keep');assert.equal(data.get('decision-5'),'link');assert.equal(data.get('target-5'),'1');await route.fulfill({body:'Submission indices preserved.'});});
 await page.getByRole('button',{name:'Collapse All',exact:true}).click();await page.getByRole('button',{name:'Apply valid cases and selected decisions'}).click();await page.waitForURL('**/import-export/apply/**');
 await page.goto(base+'/import-export/review/'+operation);await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.goto(base+'/import-export/review/11111111-1111-4111-8111-222222222222');assert.equal(await page.locator('.sync-outcomes .sync-badge').count(),9);assert.equal(await page.getByText('Failed / rolled back',{exact:true}).evaluate(e=>getComputedStyle(e).color),'rgb(214, 108, 98)');
 await page.goto(base+'/import-export/review/11111111-1111-4111-8111-333333333333');assert.equal(await page.getByRole('button',{name:'Expand All',exact:true}).isDisabled(),true);assert.equal(await page.locator('.sync-action-group').count(),0);
 assert.deepEqual(errors,[]);console.log('PASS: ordered groups, defaults, bulk/keyboard folding, retained decisions and original submission indices, effective counts, legacy-link validation/focus, narrow layout, empty state, distinct actual failure badges.');
})().catch(error=>{console.error(error);console.error(log);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));fs.rmSync(temporary,{recursive:true,force:true});});
