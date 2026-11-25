/* Dedicated impact column: rows, stable sorting, unclipped previews and existing filters. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mws-impact-column-'));
const prefix=process.env.MWS_BASE_PATH||'',base='http://127.0.0.1:8831'+prefix;
const env={...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temporary,MARE_EDITOR_TEST_PORT:'8831',MARE_EDITOR_TEST_SCRIPT_PREFIX:prefix};
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env,stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',data=>log+=data);
(async()=>{
 for(let i=0;;i++){try{if((await fetch(base+'/login')).ok)break;}catch{}if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}
 const seed=spawnSync('.venv/bin/python',['-c',`from app import app,run,ensure_package
with app.app_context():
 run("UPDATE cases SET impact_confirmed=1,impact_type='detection',impact_summary='Identified previously unknown C2 and deployed an enterprise detection.',impact_confirmed_at='2024-01-01' WHERE id=1")
 for number,name,enabled in [('IMPACT-002','Neutral comparison',0),('IMPACT-003','Long title '+('UnbrokenTitle'*13),1)]:
  cid=run("INSERT INTO cases(number,name,created,stage,owner,creator,impact_confirmed,impact_type,impact_summary) VALUES(?,?,'2024-01-01',1,1,1,?,'both',?)",(number,name,enabled,'Long impact context. '*100)).lastrowid
  ensure_package(cid)
`],{env});assert.equal(seed.status,0,seed.stderr.toString());
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1920,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');
 await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in',exact:true}).click()]);
 const cards=await page.locator('.mip-board').innerHTML();
 await page.goto(base+'/?view=table');
 assert.deepEqual(await page.locator('.mip-sort-label').allTextContents(),['Case number','Case title','Impact','Assigned owner','Creator','Stage','Section disposition']);
 assert.equal(await page.locator('.mip-table-title [data-board-impact]').count(),0);
 assert.equal(await page.locator('.mip-table-impact [data-board-impact]').count(),3);
 assert.deepEqual(await page.locator('td.mip-table-impact button').allTextContents(),['★ Impact','No known impact','★ Impact']);
 const sizes=()=>page.locator('.mip-table tbody tr').evaluateAll(rows=>rows.map(row=>row.getBoundingClientRect().height));
 if(process.env.MWS_BOARD_IMPACT_SCREENSHOT_DIR){fs.mkdirSync(process.env.MWS_BOARD_IMPACT_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.MWS_BOARD_IMPACT_SCREENSHOT_DIR,'table.png')});}
 const before=await sizes();assert.ok(Math.max(...before)-Math.min(...before)<1,JSON.stringify(before));
 const long=page.locator('.mip-table-title a').filter({hasText:'Long title'});
 assert.ok(await long.evaluate(el=>getComputedStyle(el).whiteSpace==='nowrap'&&getComputedStyle(el).textOverflow==='ellipsis'&&el.scrollWidth>el.clientWidth));
 assert.equal(await long.getAttribute('title'),await long.textContent());
 const button=page.locator('td.mip-table-impact button').first();
 await button.hover();
 const tooltip=page.locator('#'+await button.getAttribute('aria-controls'));
 await tooltip.waitFor({state:'visible'});
 assert.match(await tooltip.textContent(),/Enterprise Impact Confirmed/);
 assert.match(await tooltip.textContent(),/Outcome: Detection and Discovery/);
 assert.match(await tooltip.textContent(),/Long impact context/);
 assert.equal(await tooltip.evaluate(el=>el.matches(':popover-open')),true);
 if(process.env.MWS_BOARD_IMPACT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.MWS_BOARD_IMPACT_SCREENSHOT_DIR,'preview.png')});
 assert.deepEqual(await sizes(),before,'opening a preview must not change row heights');
 await button.focus();assert.equal(await tooltip.isVisible(),true);
 await page.keyboard.press('PageDown');assert.equal(await tooltip.isVisible(),true);
 await page.keyboard.press('Escape');assert.equal(await tooltip.isVisible(),false);
 const neutral=page.locator('td.mip-table-impact button.is-neutral');
 await neutral.focus();
 const neutralTip=page.locator('#'+await neutral.getAttribute('aria-controls'));
 await neutralTip.waitFor({state:'visible'});
 assert.match(await neutralTip.textContent(),/No known enterprise impact/);
 assert.match(await neutralTip.textContent(),/has not been marked/);
 const tooltipBox=await neutralTip.boundingBox();assert.ok(tooltipBox.x>=0&&tooltipBox.x+tooltipBox.width<=1920);
 assert.equal(await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.closest('[role=tooltip]')!==null,{x:tooltipBox.x+10,y:tooltipBox.y+10}),true);
 await page.keyboard.press('Escape');
 const numbers=()=>page.locator('td.mip-table-number').evaluateAll(cells=>cells.map(cell=>[...cell.childNodes].find(node=>node.nodeType===Node.TEXT_NODE&&node.textContent.trim()).textContent.trim()));
 await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Sort by Impact, ascending',exact:true}).click()]);
 assert.deepEqual(await numbers(),['IMPACT-002','IMPACT-003','CM-TEST']);
 assert.equal(await page.locator('th.mip-table-impact').getAttribute('aria-sort'),'ascending');
 await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Sort by Impact, descending',exact:true}).click()]);
 assert.deepEqual(await numbers(),['IMPACT-003','CM-TEST','IMPACT-002']);
 await page.reload();assert.equal(await page.locator('th.mip-table-impact').getAttribute('aria-sort'),'descending');
 await page.goto(base+'/?view=table&impact=yes&stage=1&q=Long');
 await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Sort by Impact, ascending',exact:true}).click()]);
 const url=new URL(page.url());assert.equal(url.searchParams.get('impact'),'yes');assert.equal(url.searchParams.get('stage'),'1');assert.equal(url.searchParams.get('q'),'Long');
 assert.equal(await page.locator('td.mip-table-impact button').count(),1);
 await page.goto(base+'/?view=table&impact=no');assert.deepEqual(await numbers(),['IMPACT-002']);
 await page.goto(base+'/?view=table');
 const title=page.locator('.mip-table-title a').last();const href=await title.getAttribute('href');
 await Promise.all([page.waitForURL(url=>url.pathname===href),title.click()]);
 await page.goto(base+'/?view=table');
 await page.setViewportSize({width:1024,height:800});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await page.locator('td.mip-table-impact button').count(),3);
 const mobile=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,storageState:await context.storageState()});
 const touch=await mobile.newPage();await touch.goto(base+'/?view=table');
 assert.equal(await touch.locator('td.mip-table-impact button').count(),3);
 await touch.locator('td.mip-table-impact button').first().tap();
 const popup=touch.locator('.impact-table-tooltip:popover-open');await popup.waitFor({state:'visible'});
 const bounds=await popup.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390);
 assert.ok(await touch.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await mobile.close();
 // Restore the original account ordering and compare the unmodified card markup.
 await page.goto(base+'/?view=table');
 const csrf=await page.locator('.mip-sort-form [name=csrf]').first().inputValue();
 await page.request.post(base+'/account/board-sort',{form:{csrf,column:'number',direction:'desc'}});
 await page.goto(base+'/?view=cards');
 const current=await page.locator('.mip-board').innerHTML();
 // Layout and badges are identical; compare each card independently of sort order.
 const normalize=html=>html.split(/(?=<article )/).map(s=>s.trim()).sort().join('');
 assert.equal(normalize(current),normalize(cards));
 assert.deepEqual(errors,[]);
 console.log(`PASS: dedicated Impact cells, equal row heights, ellipsis, stable boolean sorting, filters, uncut hover/focus/touch previews, navigation and unchanged cards at ${prefix||'/'}.`);
})().catch(error=>{console.error(error);console.error(log);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');if(server.exitCode===null)await new Promise(r=>server.once('exit',r));fs.rmSync(temporary,{recursive:true,force:true});});
