/* Board layout and relocated case backup, using isolated test data. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mare-board-browser-'));
const python = path.join(root, '.venv/bin/python'), port = 8783, base = `http://127.0.0.1:${port}`;
const env = {...process.env, MARE_EDITOR_BROWSER_TEST:'1', MARE_DATA_DIR:temporary, MARE_EDITOR_TEST_PORT:String(port)};
const server = spawn(python, ['tests/browser/server.py'], {cwd:root, env, stdio:['ignore','ignore','pipe']});
let browser, log = ''; server.stderr.on('data', data => log += data);
(async () => {
  for (let i = 0;; i++) {
    try { await fetch(base + '/login'); break; }
    catch (e) { if (i > 60 || server.exitCode !== null) throw Error(log); await new Promise(r => setTimeout(r, 100)); }
  }
  const seed = spawnSync(python, ['-c', `from app import app,run,ensure_package,package
with app.app_context():
 uid=run("INSERT INTO users(username,password,role,forced,active) VALUES(?,'unused','User',0,0)",('long-owner-'+'x'*65,)).lastrowid
 for stage in range(4):
  cid=run("INSERT INTO cases(number,name,created,stage,owner,creator,external_system,external_number) VALUES(?,?,'now',?,?,1,'JIRA','EXT-123')",('MARE-2026-'+str(stage)+'123456789012345678901234567890','Long case title '+('malware '*20) if stage==1 else 'Short title '+str(stage),stage,uid if stage==2 else None if stage==0 else 1)).lastrowid
  ensure_package(cid)
 (package(1)/'scripts'/'decoder.py').write_text('print(42)')
`], {cwd:root, env});
  assert.equal(seed.status, 0, seed.stderr.toString());
  browser = await chromium.launch({headless:true, ...(process.env.MARE_BROWSER_EXECUTABLE ? {executablePath:process.env.MARE_BROWSER_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(base+'/login');
  await page.locator('[name=username]').fill('editor-test'); await page.locator('[name=password]').fill('temporary-editor-test-123');
  await Promise.all([page.waitForURL(base+'/'), page.getByRole('button',{name:'Sign in'}).click()]);
  const cardBefore = await page.locator('.mip-board').innerHTML();
  assert.equal(await page.getByRole('button',{name:'Backup',exact:true}).count(),0);
  await page.goto(base+'/?view=table');
  assert.deepEqual(await page.locator('.mip-sort-label').allTextContents(), ['Case number','Case title','Assigned owner','Creator','Stage','Reviewed']);
  assert.equal(await page.locator('.mip-table th').count(),6);
  assert.equal(await page.getByRole('button',{name:'Backup',exact:true}).count(),0);
  assert.equal(await page.locator('h1').textContent(),'MIP Dashboard');
  assert.equal(await page.locator('.mip-table tbody tr').count(), 5);
  assert.match(await page.locator('.mip-table').innerText(), /Unassigned/);
  assert.match(await page.locator('.mip-table').innerText(), /\(disabled\)/);
  assert.match(await page.locator('.mip-table').innerText(), /JIRA: EXT-123/);
  for (const stage of ['Not started','Malware Analysis','Packaging & Delivery','Completed']) {
    assert.ok((await page.locator('.mip-table-stage-badge').allTextContents()).includes(stage));
  }
  const title = page.locator('.mip-table-title a').filter({hasText:'Long case title'});
  assert.equal(await title.getAttribute('title'), await title.textContent());
  assert.ok(await title.evaluate(e => e.scrollWidth > e.clientWidth && getComputedStyle(e).textOverflow === 'ellipsis'));
  await title.focus(); assert.equal(await title.evaluate(e => getComputedStyle(e).outlineStyle), 'solid');
  const caseHref = await title.getAttribute('href');
  await title.focus();
  await Promise.all([page.waitForURL(base+caseHref), title.press('Enter')]);
  assert.equal(await page.locator('.admin-nav a[aria-current="page"]').getAttribute('href'), '/');
  await page.goto(base+'/cases/1');
  await page.getByRole('tab',{name:'Review & Export',exact:true}).click();
  const backup = page.locator('#panel-review form[action="/cases/1/backup"] button');
  assert.deepEqual(await page.locator('.review-export-actions button').allTextContents(), ['Download Standard MIP Archive','Download RAW MIP Archive','Backup']);
  await page.getByRole('tab',{name:'Review & Export',exact:true}).focus();
  for(let i=0;i<20 && !await backup.evaluate(e => e === document.activeElement);i++)await page.keyboard.press('Tab');
  assert.equal(await backup.evaluate(e => e === document.activeElement && getComputedStyle(e).outlineStyle === 'solid'),true);
  const urlBefore = page.url();
  const [download] = await Promise.all([page.waitForEvent('download'), backup.press('Enter')]);
  assert.equal(page.url(), urlBefore); assert.match(download.suggestedFilename(), /-backup\.zip$/);
  const zipPath = path.join(temporary, 'download.zip'); await download.saveAs(zipPath);
  const inspect = spawnSync(python, ['-c', 'import sys,zipfile,json; z=zipfile.ZipFile(sys.argv[1]); assert any(n.endswith("/scripts/decoder_py.txt") for n in z.namelist()),z.namelist(); assert json.loads(z.read(next(n for n in z.namelist() if n.endswith("/case-data.json"))))["case"]["number"] == "CM-TEST"', zipPath]);
  assert.equal(inspect.status, 0, inspect.stderr.toString());
  // The same action targets the currently open case, including before Packaging.
  await page.goto(base+'/cases/2');
  await page.getByRole('tab',{name:'Review & Export',exact:true}).click();
  assert.equal(await page.locator('#panel-review form[action="/cases/2/backup"] button').isEnabled(),true);
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:900});
    const buttons = page.locator('.review-export-actions button');
    assert.equal(await buttons.count(),3);
    for (const button of await buttons.all()) assert.ok(await button.isVisible());
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const boxes = await buttons.evaluateAll(nodes => nodes.map(e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};}));
    for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++)assert.ok(boxes[i].right<=boxes[j].x || boxes[j].right<=boxes[i].x || boxes[i].bottom<=boxes[j].y || boxes[j].bottom<=boxes[i].y);
  }
  await page.goto(base+'/?view=table');
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.locator('.mip-table-scroll').evaluate(e => e.scrollWidth > e.clientWidth));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  const touch = await browser.newContext({viewport:{width:390,height:844}, hasTouch:true, storageState:await page.context().storageState()});
  const touchPage = await touch.newPage(); await touchPage.goto(base+'/?view=table');
  assert.ok(await touchPage.locator('.mip-table button').first().evaluate(e => e.getBoundingClientRect().height >= 44));
  await touch.close();
  await page.goto(base+'/?view=cards'); assert.equal(await page.locator('.mip-board').innerHTML(), cardBefore);
  // Dashboard shortcuts and manual checkboxes share the same stage query.
  await page.goto(base+'/?view=table');
  for(const [label,stages,count] of [['Not started',['0'],1],['In progress',['1','2'],3],['Completed',['3'],1]]){
    const shortcut=page.locator('.board-metric-filter').filter({hasText:label});
    await shortcut.focus();await Promise.all([page.waitForNavigation(),shortcut.press('Enter')]);
    assert.deepEqual(new URL(page.url()).searchParams.getAll('stage'),stages);
    assert.equal(await page.locator('.mip-table tbody tr').count(),count);
    await page.getByRole('button',{name:/^Filters/}).click();
    assert.deepEqual(await page.locator('.board-stage-filters input:checked').evaluateAll(inputs=>inputs.map(input=>input.value)),stages);
    await page.keyboard.press('Escape');
  }
  await page.locator('.board-metric-filter').filter({hasText:'In progress'}).click();
  await page.getByRole('link',{name:'Card view',exact:true}).click();
  assert.equal(await page.locator('.mip-board .mip-card').count(),3);
  await page.getByRole('link',{name:'Table view',exact:true}).click();
  const sortStage=page.getByRole('button',{name:'Sort by Stage, ascending',exact:true});
  await Promise.all([page.waitForNavigation(),sortStage.click()]);
  assert.deepEqual(new URL(page.url()).searchParams.getAll('stage'),['1','2']);
  await page.getByRole('button',{name:/^Filters/}).click();
  for(const checkbox of await page.locator('.board-stage-filters input').all())await checkbox.uncheck();
  await page.getByRole('checkbox',{name:'Not started',exact:true}).check();
  await page.getByRole('checkbox',{name:'Completed',exact:true}).check();
  await page.locator('#tag-filter-drawer').getByRole('button',{name:'Apply',exact:true}).click();
  assert.deepEqual(new URL(page.url()).searchParams.getAll('stage'),['0','3']);
  assert.equal(await page.locator('.mip-table tbody tr').count(),2);
  await page.goto(base+'/?view=table&q=not-a-matching-case&stage=3');
  await page.locator('.board-metric-filter').filter({hasText:'All MIPs'}).click();
  assert.equal(new URL(page.url()).searchParams.has('stage'),false);
  assert.equal(new URL(page.url()).searchParams.has('q'),false);
  assert.equal(await page.locator('.mip-table tbody tr').count(),5);
  await page.goto(base+'/?view=table&q=Short&stage=0');
  await page.getByRole('button',{name:/^Filters/}).click();
  await page.locator('#tag-filter-drawer').getByRole('button',{name:'Clear Filters',exact:true}).click();
  assert.equal(new URL(page.url()).searchParams.get('q'),'');
  assert.equal(new URL(page.url()).searchParams.has('stage'),false);
  // Reset sort for the ascending/descending checks below.
  await page.getByRole('button',{name:'Sort by Reviewed, ascending',exact:true}).click();
  // Every data header toggles, persists on reload and orders card view identically.
  for(const label of ['Case number','Case title','Assigned owner','Creator','Stage','Reviewed']){
    await page.goto(base+'/?view=table');
    await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Sort by '+label+', ascending',exact:true}).click()]);
    assert.equal(await page.locator('th[aria-sort="ascending"] .mip-sort-label').textContent(),label);
    await page.reload();assert.equal(await page.locator('th[aria-sort="ascending"] .mip-sort-label').textContent(),label);
    const descending=page.getByRole('button',{name:'Sort by '+label+', descending',exact:true});
    await descending.focus();assert.equal(await descending.evaluate(el=>getComputedStyle(el).outlineStyle),'solid');
    await Promise.all([page.waitForNavigation(),descending.press('Enter')]);
    assert.equal(await page.locator('th[aria-sort="descending"] .mip-sort-label').textContent(),label);
    const tableOrder=await page.locator('.mip-table tbody td.mip-table-number').evaluateAll(cells=>cells.map(cell=>cell.firstChild.textContent.trim()));
    await page.getByRole('link',{name:'Card view',exact:true}).click();
    assert.deepEqual(await page.locator('.mip-board .case-card .eyebrow').allTextContents(),tableOrder);
  }
  await page.goto(base+'/?view=table&q=not-a-matching-case');
  assert.equal(await page.locator('.mip-table tbody td').getAttribute('colspan'), '6');
  assert.match(await page.locator('.mip-table tbody').innerText(), /No cases found/);
  // The stage-only drawer works for an account without tag-read permission.
  const revoke=spawnSync(python,['-c',"from app import app,run\nwith app.app_context():run(\"DELETE FROM role_permissions WHERE role_name='User' AND permission='tags:read'\");run(\"UPDATE users SET role='User' WHERE username='editor-test'\")"],{cwd:root,env});
  assert.equal(revoke.status,0,revoke.stderr.toString());
  await page.goto(base+'/?view=table');
  await page.getByRole('button',{name:/^Filters/}).click();
  assert.equal(await page.locator('[data-filter-search]').count(),0);
  await page.getByRole('checkbox',{name:'Completed',exact:true}).check();
  await page.locator('#tag-filter-drawer').getByRole('button',{name:'Apply',exact:true}).click();
  assert.equal(await page.locator('.mip-table tbody tr').count(),1);
  assert.deepEqual(errors, []);
  console.log('PASS: compact dimensions, all stages, long titles/numbers/owners, unassigned and disabled owners, keyboard focus, relocated Review & Export backup/current case/Python renaming, no board Backup buttons, narrow and touch layouts, empty board.');
})().catch(error => {console.error(error); console.error(log); process.exitCode=1;}).finally(async () => {
  if (browser) await browser.close(); server.kill('SIGTERM');
  await new Promise(r => server.once('exit',r)); fs.rmSync(temporary,{recursive:true,force:true});
});
