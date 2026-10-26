const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-actor-wall-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8805';
const server=spawn('.venv/bin/python',['tests/browser/actor-dashboard-server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_ACTOR_WALL_TEST:'1'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',data=>log+=data);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1920,height:1080}});page.setDefaultTimeout(12000);await page.clock.install();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByRole('link',{name:'Threat actors dashboard'}).click();
 await page.locator('#tracked_actors').filter({hasText:'49'}).waitFor();
 assert.equal(await page.locator('#active article').count(),3);assert.equal(await page.locator('#tracked article').count(),24);
 assert.equal(await page.locator('main img').count(),0);assert.equal(await page.locator('main a').count(),0);
 const geometry=()=>page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,bottom:document.querySelector('.wall-footer').getBoundingClientRect().bottom,height:innerHeight}));
 let bounds=await geometry();assert.ok(bounds.width<=bounds.viewport,JSON.stringify(bounds));assert.ok(bounds.bottom<=bounds.height,JSON.stringify(bounds));
 if(process.env.MARE_ACTOR_WALL_SCREENSHOT)await page.screenshot({path:process.env.MARE_ACTOR_WALL_SCREENSHOT,fullPage:true});
 const offset=()=>page.locator('.strip-track').evaluate(el=>new DOMMatrix(getComputedStyle(el).transform).m41);
 await page.mouse.move(0,0);let before=await offset();await delay(600);assert.ok(await offset()<before-7,'Strip moves left at readable speed');
 assert.equal(await page.locator('[data-copy]').getAttribute('aria-hidden'),'true');
 const seam=await page.locator('.strip-track').evaluate(el=>({gap:el.children[1].getBoundingClientRect().left-el.children[0].getBoundingClientRect().right,same:el.children[1].textContent===el.children[0].textContent}));
 assert.ok(Math.abs(seam.gap-16)<.1&&seam.same);
 await page.locator('#strip-pause').click();await page.mouse.move(0,0);before=await offset();await delay(200);assert.equal(await offset(),before);
 await page.locator('#strip-pause').click();await page.locator('#strip-pause').blur();await page.locator('.strip-viewport').hover();before=await offset();await delay(200);assert.equal(await offset(),before);
 await page.mouse.move(0,0);await page.locator('.strip-viewport').focus();before=await offset();await delay(200);assert.equal(await offset(),before);await page.locator('.strip-viewport').press('ArrowRight');assert.notEqual(await offset(),before);
 await page.locator('#next').click();await page.locator('#page-position').filter({hasText:'Page 2 of 3'}).waitFor();await page.locator('#next').blur();await page.mouse.move(0,0);
 await page.clock.fastForward(25001);await page.locator('#page-position').filter({hasText:'Page 3 of 3'}).waitFor();
 await page.locator('#active-pause').click();await page.locator('#active-pause').blur();await page.mouse.move(0,0);await page.clock.fastForward(25001);await delay(100);assert.match(await page.locator('#page-position').textContent(),/Page 3 of 3/);
 await page.locator('#library-next').click();await page.locator('#library-position').filter({hasText:'Library page 2 of 3'}).waitFor();await page.locator('#library-next').click();await page.locator('#library-position').filter({hasText:'Library page 3 of 3'}).waitFor();assert.equal(await page.locator('#tracked article').count(),1);
 await page.locator('#strip-pause').click();
 const original=await(await fetch(base+'/dashboards/threat-actors/data?page=2&library_page=2')).json();
 let failed=true;
 await page.route('**/dashboards/threat-actors/data?*',route=>failed?route.fulfill({status:503,body:'Unavailable'}):route.fulfill({json:{...original,featured:{...original.featured,name:'Refreshed research actor'}}}));
 const refresh=()=>page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
 await refresh();await page.locator('#update-status').filter({hasText:'Unable to refresh'}).waitFor();assert.equal(await page.locator('#tracked_actors').textContent(),'49');
 failed=false;await refresh();await page.getByRole('heading',{name:'Refreshed research actor'}).waitFor();assert.equal(await page.locator('#strip-pause').textContent(),'Resume scrolling');assert.equal(await page.locator('#active-pause').textContent(),'Resume rotation');assert.match(await page.locator('#page-position').textContent(),/Page 3 of 3/);
 await page.unroute('**/dashboards/threat-actors/data?*');
 let received=0,release;
 await page.route('**/dashboards/threat-actors/data?*',async route=>{
   received++;
   if(received===1)await new Promise(resolve=>release=resolve);
   await route.fulfill({json:{...original,featured:{...original.featured,name:received===1?'Obsolete response':'Newest response'}}});
 });
 await refresh();for(let i=0;!release&&i<100;i++)await delay(20);assert.ok(release);
 await refresh();await delay(100);assert.equal(received,1,'Refreshes must not overlap');
 release();await page.getByRole('heading',{name:'Newest response'}).waitFor();assert.equal(await page.getByRole('heading',{name:'Obsolete response'}).count(),0);
 await page.unroute('**/dashboards/threat-actors/data?*');
 const updated=spawnSync('.venv/bin/python',['-c',`import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("UPDATE threat_actors SET name=? WHERE name=?",('Live database change',sys.argv[2])); c.commit()`,path.join(temporary,'workflow.sqlite3'),original.featured.name]);
 assert.equal(updated.status,0,updated.stderr?.toString());await refresh();await page.getByRole('heading',{name:'Live database change'}).waitFor();
 for(const size of [{width:1366,height:768},{width:390,height:844}]){await page.setViewportSize(size);bounds=await geometry();assert.ok(bounds.width<=bounds.viewport,JSON.stringify(bounds));}
 await page.emulateMedia({reducedMotion:'reduce'});await page.mouse.move(0,0);before=await offset();await delay(200);assert.equal(await offset(),before);assert.equal(await page.locator('[data-copy]').count(),0);assert.equal(await page.locator('#active-pause').isDisabled(),true);
 await page.locator('#library-previous').click();await page.locator('#library-position').filter({hasText:'Library page 2 of 3'}).waitFor();await page.locator('#library-previous').click();await page.locator('#library-position').filter({hasText:'Library page 1 of 3'}).waitFor();assert.equal(await page.locator('#tracked article').count(),24);
 const reachable=[];
 for(let i=0;i<3;i++){reachable.push(...await page.locator('#tracked h3').allTextContents());if(i<2){await page.locator('#library-next').click();await page.locator('#library-position').filter({hasText:`Library page ${i+2} of 3`}).waitFor();}}
 assert.equal(new Set(reachable).size,49,'All eligible actors must be reachable, including the short final page');
 // A stationary one-card final page still advances after a readable dwell.
 await page.emulateMedia({reducedMotion:'no-preference'});await page.locator('#strip-pause').click();await page.locator('#strip-pause').blur();await page.mouse.move(0,0);await page.clock.fastForward(25001);await page.locator('#library-position').filter({hasText:'Library page 1 of 3'}).waitFor();
 await page.locator('#strip-pause').click();
 await page.getByRole('link',{name:'Cases',exact:true}).click();await page.locator('#in_progress').filter({hasText:'8'}).waitFor();await page.getByRole('link',{name:'Malware Families',exact:true}).click();await page.locator('#tracked_families').filter({hasText:'1'}).waitFor();await page.getByRole('link',{name:'Threat Actors',exact:true}).click();await page.locator('#tracked_actors').filter({hasText:'49'}).waitFor();
 await page.setViewportSize({width:1920,height:1080});await page.emulateMedia({reducedMotion:'no-preference'});
 const empty={...original,metrics:{tracked_actors:0,actors_in_progress:0,unique_linked_cases:0,reports_collected:0},featured:null,investigations:[],tracked:[],pagination:{page:0,pages:1,page_size:3,total:0},library_pagination:{page:0,pages:1,page_size:24,total:0}};
 let display=empty;await page.route('**/dashboards/threat-actors/data?*',route=>route.fulfill({json:display}));
 await refresh();await page.getByRole('heading',{name:'Research starts with an actor.'}).waitFor();await page.getByText('No threat actor investigations currently in progress',{exact:true}).waitFor();assert.equal(await page.locator('#tracked article').count(),0);assert.ok(await page.locator('#strip-pause').isDisabled());
 const single={...original.tracked[0],name:'Single tracked profile'};display={...empty,featured:single,tracked:[single],metrics:{...empty.metrics,tracked_actors:1},library_pagination:{...empty.library_pagination,total:1}};
 await refresh();await page.getByRole('heading',{name:'Single tracked profile',exact:true}).first().waitFor();assert.equal(await page.locator('#tracked article').count(),1);assert.equal(await page.locator('[data-copy]').count(),0);assert.ok(await page.locator('#strip-pause').isDisabled());
 assert.deepEqual(errors,[]);console.log('Actor wall browser checks passed: layouts, safety, movement, seam, pauses, workload/library pages, refresh failure/recovery, reduced motion all 49 actors, short-page automatic cycling and Cases/Family navigation.');
})().catch(error=>{console.error(log.slice(-2500));console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
