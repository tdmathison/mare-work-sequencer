/* Executive Metrics: isolated server/data, native SVG and responsive scorecard. */
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'), {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'), temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-metrics-browser-'));
const python=path.join(root,'.venv/bin/python'), port=8784, base=`http://127.0.0.1:${port}`;
const env={...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:String(port)};
const server=spawn(python,['tests/browser/server.py'],{cwd:root,env,stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',data=>log+=data);
function seed(code){const result=spawnSync(python,['-c',code],{cwd:root,env});assert.equal(result.status,0,result.stderr.toString());}
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>60||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 seed(`from app import app,run
from datetime import datetime,timedelta,timezone
with app.app_context():
 now=datetime.now(timezone.utc); end=(now-timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
 run('UPDATE cases SET created=?',((end-timedelta(days=10)).isoformat(),))
 uid=run("INSERT INTO users(username,password,role,active,forced) VALUES(?,'unused','User',0,0)",('Long analyst '+'x'*100,)).lastrowid
 for stage in range(4):
  created=end-timedelta(days=14-stage)
  cid=run("INSERT INTO cases(number,name,created,stage,owner,creator) VALUES(?,?,?, ?,?,1)",('SCORE-'+str(stage),'Scorecard case',created.isoformat(),stage,uid if stage else None)).lastrowid
  if stage==3: run("INSERT INTO history(case_id,stage,outcome,created) VALUES(?,2,'Done',?)",(cid,(created+timedelta(days=2)).isoformat()))
 `);
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[], external=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(base))external.push(r.url());});
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/metrics');
 assert.equal(await page.locator('h1').textContent(),'MARE performance overview');
 assert.equal(await page.locator('#metrics-total').textContent(),'5');assert.equal(await page.locator('#metrics-completed').textContent(),'1');assert.match(await page.locator('.performance-period-activity').innerText(),/Created during period: 5/);
 assert.equal(await page.locator('.admin-nav a[aria-current="page"]').getAttribute('href'),'/dashboards');
 assert.equal(await page.locator('.performance-scorecards').innerText().then(t=>t.includes('2.0')),true);
 assert.equal(await page.locator('#reporting-weeks').inputValue(),'12');
 assert.equal(await page.locator('.performance-point').count(),12);
 const points=page.locator('.performance-point');await points.first().focus();
 assert.match(await page.locator('#performance-week-detail').textContent(),/created · .*completed/);
 assert.equal(await points.first().evaluate(e=>getComputedStyle(e.querySelector('.performance-point-target')).stroke),'rgb(217, 174, 88)');
 await points.last().hover();assert.equal(await page.locator('#performance-week-detail').textContent(),await points.last().getAttribute('data-week-detail'));
 await points.last().press('Enter');
 await page.getByText('Weekly activity table',{exact:true}).click();assert.equal(await page.locator('.performance-weekly tbody tr').count(),12);
 assert.equal(await page.locator('.performance-analysts').innerText().then(t=>t.includes('Disabled')),true);
 const columns=await page.locator('.performance-columns').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length);assert.equal(columns,2);
 await page.screenshot({path:path.join(process.env.MARE_METRICS_SCREENSHOT_DIR||temporary,'metrics-desktop.png'),fullPage:true});
 for(const period of ['4','26','52']){await page.locator('#reporting-weeks').selectOption(period);await Promise.all([page.waitForURL(base+'/metrics?weeks='+period),page.getByRole('button',{name:'Apply',exact:true}).click()]);assert.equal(await page.locator('.performance-point').count(),Number(period));}
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await page.locator('.performance-columns').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);
 assert.ok(await page.locator('.performance-chart-scroll').evaluate(e=>e.scrollWidth>e.clientWidth));
 const touch=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,storageState:await page.context().storageState()});
 const touchPage=await touch.newPage();await touchPage.goto(base+'/metrics?weeks=4');await touchPage.locator('.performance-point').first().tap();assert.match(await touchPage.locator('#performance-week-detail').textContent(),/created · .*completed/);await touch.close();
 await page.screenshot({path:path.join(process.env.MARE_METRICS_SCREENSHOT_DIR||temporary,'metrics-mobile.png'),fullPage:true});
 seed(`from app import app,db
with app.app_context():
 db().execute('UPDATE cases SET stage=3')
 for i in range(11):db().execute("INSERT INTO cases(number,name,created,stage) VALUES(?,?,'',3)",('UNDATED-'+str(i),'Restored completed case'))
 db().commit()
 `);
 await page.goto(base+'/');assert.equal(await page.locator('.case-card').count()||await page.locator('tbody tr').count(),16);
 await page.goto(base+'/metrics');assert.equal(await page.locator('#metrics-total').textContent(),'16');assert.equal(await page.locator('#metrics-completed').textContent(),'16');assert.match(await page.locator('.performance-period-activity').innerText(),/Created during period: 5/);
 seed(`from app import app,db
with app.app_context():
 db().commit();db().execute('PRAGMA foreign_keys=OFF');db().execute('DELETE FROM history');db().execute('DELETE FROM cases');db().execute('DELETE FROM users WHERE username LIKE "Long analyst%"');db().commit()
 `);
 await page.goto(base+'/metrics?weeks=4');assert.match(await page.locator('.performance-scorecards').innerText(),/Unavailable/);assert.match(await page.locator('.performance-period-activity').innerText(),/No change/);assert.equal(await page.locator('.performance-point').count(),4);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log('PASS: populated and empty scorecards, all periods, desktop/mobile layout, long/disabled analysts, chart hover/focus/keyboard/touch details, zero weeks, local-only assets, active DASHBOARDS navigation.');
})().catch(error=>{console.error(error);console.error(log);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));fs.rmSync(temporary,{recursive:true,force:true});});
