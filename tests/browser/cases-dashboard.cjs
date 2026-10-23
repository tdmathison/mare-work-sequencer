const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mare-dashboard-'));
const port = 8794, base = `http://127.0.0.1:${port}`;
const server = spawn('.venv/bin/python', ['tests/browser/cases-dashboard-server.py'], {env:{...process.env, MARE_DATA_DIR:temporary, MARE_DASHBOARD_BROWSER_TEST:'1'}, stdio:['ignore','ignore','pipe']});
let browser, log=''; server.stderr.on('data', data => log += data);
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
(async () => {
  for (let i=0;;i++) { try {await fetch(base+'/login');break;} catch(e) {if(i>100||server.exitCode!==null)throw Error(log); await delay(100);} }
  browser = await chromium.launch({headless:true, executablePath:process.env.MARE_BROWSER_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const context = await browser.newContext({viewport:{width:1920,height:1080}});
  const page = await context.newPage(); page.setDefaultTimeout(10000); await page.clock.install();
  const errors=[]; page.on('pageerror', error=>errors.push(error.message));
  await page.goto(base+'/login'); await page.getByRole('link',{name:'Cases dashboard'}).click();
  await page.locator('#in_progress').filter({hasText:'11'}).waitFor();
  assert.equal(await page.locator('#latest img').count(),0,'Markup must remain plain text');
  assert.equal(await page.locator('#active article').count(),4);
  const geometry = () => page.evaluate(()=>({width:document.documentElement.scrollWidth, viewport:innerWidth, bottom:document.querySelector('.wall-footer').getBoundingClientRect().bottom,height:innerHeight}));
  let bounds=await geometry(); assert.ok(bounds.width<=bounds.viewport); assert.ok(bounds.bottom<=bounds.height,JSON.stringify(bounds));
  if (process.env.MARE_DASHBOARD_SCREENSHOT) await page.screenshot({path:process.env.MARE_DASHBOARD_SCREENSHOT,fullPage:true});
  await page.mouse.move(0,0);
  const offset=()=>page.locator('.strip-track').evaluate(el=>new DOMMatrix(getComputedStyle(el).transform).m41);
  let before=await offset(); await delay(600); let after=await offset(); assert.ok(after<before-7,'Strip visibly moves left');
  assert.equal(await page.locator('[data-copy]').count(),1);
  assert.equal(await page.locator('[data-copy]').getAttribute('aria-hidden'),'true');
  const seam = await page.locator('.strip-track').evaluate(el => {
    const [first, copy] = el.children;
    return {gap:copy.getBoundingClientRect().left-first.getBoundingClientRect().right, same:copy.textContent===first.textContent, width:first.getBoundingClientRect().width, viewport:el.parentElement.clientWidth};
  });
  assert.ok(Math.abs(seam.gap-16)<.1); assert.ok(seam.same && seam.width>seam.viewport);
  await page.locator('#strip-pause').click(); await page.mouse.move(0,0);
  before=await offset();await delay(200);assert.equal(await offset(),before);
  await page.locator('#strip-pause').click(); await page.mouse.move(0,0); await page.locator('#strip-pause').blur();
  await page.locator('.strip-viewport').hover();before=await offset(); await delay(200); assert.equal(await offset(),before);
  await page.mouse.move(0,0);await page.locator('.strip-viewport').focus();before=await offset();await delay(200); assert.equal(await offset(),before);
  await page.locator('#next').click();await page.locator('#page-position').filter({hasText:'Page 2 of 3'}).waitFor();
  await page.locator('#next').blur(); await page.mouse.move(0,0);
  await page.clock.fastForward(15001);
  await page.locator('#page-position').filter({hasText:'Page 3 of 3'}).waitFor();
  await page.locator('#previous').click();
  await page.locator('#page-position').filter({hasText:'Page 2 of 3'}).waitFor();
  await page.locator('#active-pause').click(); await page.locator('#active-pause').blur();
  await page.mouse.move(0,0); await page.clock.fastForward(15001); await delay(100);
  assert.ok((await page.locator('#page-position').textContent()).includes('Page 2 of 3'));

  await page.locator('#strip-pause').click(); // preserve explicit pause through reconciliation
  const initial = await (await fetch(base+'/dashboards/cases/data?page=1')).json();
  let failed=true;
  await page.route('**/dashboards/cases/data?*', route => failed ? route.fulfill({status:503,body:'Unavailable'}) : route.fulfill({json:{...initial, metrics:{...initial.metrics,in_progress:99},latest:{...initial.latest,title:'Updated without reload'}}}));
  const refresh = () => page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  await refresh();await page.locator('#update-status').filter({hasText:'Unable to refresh'}).waitFor();
  assert.equal(await page.locator('#in_progress').textContent(),'11');
  failed=false;await refresh();await page.getByRole('heading',{name:'Updated without reload'}).waitFor();
  assert.equal(await page.locator('#in_progress').textContent(),'99');
  assert.equal(await page.locator('#strip-pause').textContent(),'Resume scrolling');
  assert.ok((await page.locator('#page-position').textContent()).includes('Page 2 of 3'));
  for(const size of [{width:1366,height:768},{width:390,height:844}]) {
    await page.setViewportSize(size); bounds=await geometry();assert.ok(bounds.width<=bounds.viewport,JSON.stringify(bounds));
  }
  await page.emulateMedia({reducedMotion:'reduce'}); await page.mouse.move(0,0);
  before=await offset();await delay(200);assert.equal(await offset(),before);
  assert.equal(await page.locator('[data-copy]').count(),0);
  assert.equal(await page.locator('.strip-viewport').evaluate(el=>getComputedStyle(el).overflowX),'auto');
  // Empty and single-card snapshots do not fabricate repeated content.
  for (const recent of [[], [initial.recent[0]]]) {
    await page.unroute('**/dashboards/cases/data?*');
    await page.route('**/dashboards/cases/data?*', route => route.fulfill({json:{...initial,latest:null,active:[],recent,metrics:{in_progress:0,preparing:0,completed_month:0,not_started:0},pagination:{page:0,pages:1,total:0,page_size:4}}}));
    await refresh(); await delay(150);
    assert.equal(await page.locator('#recent article').count(),recent.length);
    assert.equal(await page.locator('[data-copy]').count(),0);
  }
  await page.unroute('**/dashboards/cases/data?*');
  let requests=0, release;
  await page.route('**/dashboards/cases/data?*', async route => {requests++; await new Promise(resolve=>release=resolve); await route.fulfill({json:initial});});
  await refresh(); await delay(100); await refresh(); await delay(100);
  assert.equal(requests,1,'Requests must not overlap');
  release(); await delay(100);
  await page.unroute('**/dashboards/cases/data?*');
  let periodic=0;
  await page.route('**/dashboards/cases/data?*', route => { periodic++; return route.fulfill({json:initial}); });
  await page.clock.fastForward(60001); await delay(100);
  assert.ok(periodic>=1,'Scheduled refresh runs without a reload');
  assert.deepEqual(errors,[]);
  console.log('Cases dashboard browser checks passed (wall, desktop, mobile, safe text, pagination, motion, pause, refresh failure/recovery).');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});});
