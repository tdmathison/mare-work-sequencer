/* Private overview over real, disposable application content. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mws-content-')),base='http://127.0.0.1:8876';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temp,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8876'},stdio:['ignore','ignore','pipe']});let browser,log='';server.stderr.on('data',value=>log+=value);
(async()=>{
 for(let n=0;;n++){try{await fetch(base+'/login');break;}catch{if(n>100||server.exitCode!==null)throw Error(log);await new Promise(resolve=>setTimeout(resolve,100));}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(15000);
 await page.goto(base+'/content-metrics');assert.equal(new URL(page.url()).pathname,'/login');
 await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/content-metrics'),page.getByRole('button',{name:'Sign in',exact:true}).click()]);
 const root=page.locator('[data-content-metrics]');await root.locator('[data-metrics-status]').filter({hasText:'No recorded dated additions'}).waitFor();assert.equal(await root.locator('[data-summary-kind]').count(),10);
 await page.screenshot({path:'/tmp/mws-content-empty.png'});
 await page.goto(base+'/tags');const csrf=await page.locator('input[name=csrf]').first().inputValue();
 const post=(url,form)=>page.request.post(base+url,{form:{csrf,...form}});
 assert.equal((await post('/malware-families/new',{name:'Metrics research family',tag:'MAL_CONTENT'})).status(),200);
 assert.equal((await post('/threat-actors/new',{name:'Metrics research actor',tag:'TA_CONTENT'})).status(),200);
 assert.equal((await post('/cases/1/indicators',{rows:JSON.stringify([['domain','same.example','A'],['domain','same.example','B']]),revision:'0'})).status(),200);
 for(const [category,name,buffer]of [['samples','test.bin',Buffer.from('inert bytes')],['scripts','example.py',Buffer.from('print(42)')],['reports','research.pdf',Buffer.from('%PDF-1.4\n%%EOF\n')],['signatures','demo.rules',Buffer.from('alert tcp any any -> any any (sid:1;)')]]){const response=await page.request.post(base+'/cases/1/upload',{multipart:{csrf,category,ajax:'1',file:{name,mimeType:'application/octet-stream',buffer}}});assert.equal(response.status(),200,await response.text());}
 assert.equal((await post('/cases/1/references',{rows:JSON.stringify([['https://example.org','Research']]),revision:'0'})).status(),200);
 await page.goto(base+'/content-metrics');await root.locator('[data-metrics-status]').filter({hasText:'Content metrics updated.'}).waitFor();
 assert.equal(await page.title(),'Content Metrics — MARE');assert.equal(await root.locator('[data-summary-kind=indicators] strong').textContent(),'2');assert.equal(await root.locator('[data-summary-kind=samples] strong').textContent(),'1');
 assert.ok(await page.locator('[data-group=Dashboards]').getAttribute('aria-expanded')==='true');
 const links=await page.locator('.sidebar-group a').allTextContents();assert.ok(links.findIndex(label=>label.includes('Case Metrics — Private'))<links.findIndex(label=>label.includes('Content Metrics — Private')));
 const chart=root.locator('[data-plot=indicators]'),point=chart.locator('.metric-point').last();await point.focus();assert.match(await chart.locator('.content-chart-detail').textContent(),/Indicators: 2 additions/);assert.ok(await point.locator('title').count());
 await chart.getByRole('checkbox',{name:'Indicators',exact:true}).uncheck();assert.equal(await chart.locator('.metric-point').count(),0);await chart.getByRole('checkbox',{name:'Indicators',exact:true}).check();
 await page.screenshot({path:'/tmp/mws-content-default-overview.png',fullPage:true});
 const originalInventory=await root.locator('[data-inventory]').textContent();
 await root.getByLabel('Measure',{exact:true}).selectOption('cumulative');await root.getByLabel('Granularity',{exact:true}).selectOption('weekly');await root.getByRole('button',{name:'Apply',exact:true}).click();await root.locator('[data-chart-context]').filter({hasText:'Weekly · Cumulative'}).waitFor();
 assert.equal(await root.locator('[data-inventory]').textContent(),originalInventory);assert.equal(await root.locator('[data-summary-kind=indicators] strong').textContent(),'2');
 // Newer filters must win when an older response is deliberately delayed.
 await page.route('**/content-metrics/data?**',async route=>{if(new URL(route.request().url()).searchParams.get('granularity')==='monthly'){try{const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,400));await route.fulfill({response});}catch{}}else await route.continue();});
 await root.getByLabel('Granularity',{exact:true}).selectOption('monthly');await root.getByRole('button',{name:'Apply',exact:true}).click();await root.getByLabel('Granularity',{exact:true}).selectOption('weekly');await root.getByRole('button',{name:'Apply',exact:true}).click();await root.locator('[data-metrics-status]').filter({hasText:'Content metrics updated.'}).waitFor();await page.waitForTimeout(500);assert.match(await root.locator('[data-chart-context]').textContent(),/^Weekly/);await page.unroute('**/content-metrics/data?**');
 // Failure clears old results, then manual Refresh recovers without fabricated data.
 await page.route('**/content-metrics/data?**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Test outage'})}));await root.getByRole('button',{name:'Refresh',exact:true}).click();await root.locator('[data-metrics-status]').filter({hasText:'Test outage'}).waitFor();assert.equal(await root.locator('[data-inventory] article').count(),0);await page.unroute('**/content-metrics/data?**');await root.getByRole('button',{name:'Refresh',exact:true}).click();await root.locator('[data-metrics-status]').filter({hasText:'Content metrics updated.'}).waitFor();
 for(const width of [1440,1024,768,390]){await page.setViewportSize({width,height:1100});await page.waitForTimeout(250);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`/tmp/mws-content-overview-${width}.png`,fullPage:true});await root.locator('[data-plot=indicators]').screenshot({path:`/tmp/mws-content-indicators-${width}.png`});}
 await page.goto(base+'/metrics');assert.equal(await page.locator('h1').textContent(),'Case Metrics');assert.equal(await page.title(),'Case Metrics — MARE');
 assert.deepEqual(errors,[]);console.log('Content Metrics passed: private access, actual inventory/entry counts, independent scales, legends/keyboard tooltips, weekly/cumulative controls, period summaries, refresh/error recovery and 390–1440px layouts; existing /metrics preserved.');
})().catch(error=>{console.error(error);console.error(log.slice(-2000));process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temp,{recursive:true,force:true});});
