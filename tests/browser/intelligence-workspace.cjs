/* Compare actual workspace boundaries, not just isolated page screenshots. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mws-intelligence-')),base='http://127.0.0.1:8873',screens='/tmp/mws-intelligence';fs.mkdirSync(screens,{recursive:true});
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temp,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8873'},stdio:['ignore','ignore','pipe']});let browser,logs='';server.stderr.on('data',data=>logs+=data);
(async()=>{
 for(let n=0;;n++){try{await fetch(base+'/login');break;}catch{if(n>100||server.exitCode!==null)throw Error(logs);await new Promise(resolve=>setTimeout(resolve,100));}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(15000);
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in',exact:true}).click()]);
 const routes=['/malware-families','/threat-actors','/tags'];
 async function geometry(route,state,width){
  await page.goto(base+route);await page.waitForLoadState('networkidle');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal page overflow');
  const metrics=await page.locator('[data-intelligence-workspace]').evaluate(root=>{
   const rect=selector=>{const e=root.querySelector(selector);if(!e||!e.getClientRects().length)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
   const style=selector=>{const e=root.querySelector(selector);if(!e)return null;const s=getComputedStyle(e);return {padding:s.padding,border:s.border,radius:s.borderRadius,background:s.backgroundColor};};
   return {heading:rect('.intelligence-heading'),title:rect('h1'),primary:rect('.intelligence-primary'),toolbar:rect('.intelligence-toolbar'),input:rect('[name=q]'),layout:rect('.family-layout'),directory:rect('.intelligence-directory'),detail:rect('.family-workspace'),tabs:rect('.intelligence-tabs-container'),content:rect('.family-content'),panelStyle:style('.family-workspace'),rowStyle:style('.family-choice'),titleFont:getComputedStyle(root.querySelector('h1')).font};
  });
  await page.screenshot({path:path.join(screens,`${state}-${routes.findIndex(r=>route.startsWith(r))}-${width}.png`),fullPage:false});return metrics;
 }
 function compare(values,state,width){
  const same=(get,label)=>{const target=get(values[0]);for(const value of values.slice(1)){const actual=get(value);if(typeof target==='number')assert.ok(Math.abs(actual-target)<1,`${state}/${width}: ${label}: ${actual} vs ${target}`);else assert.deepEqual(actual,target,`${state}/${width}: ${label}`);}};
  same(m=>m.title.y,'title position');same(m=>m.titleFont,'title typography');same(m=>m.primary.y,'primary action position');same(m=>m.primary.height,'primary action height');same(m=>m.toolbar.y,'toolbar position');same(m=>m.toolbar.height,'toolbar height');same(m=>m.input.height,'search size');same(m=>m.layout.y,'panel top');same(m=>m.panelStyle,'panel surface');
  if(width>900){same(m=>m.directory.x,'directory left');same(m=>m.directory.width,'directory width');same(m=>m.detail.x,'detail left');same(m=>m.detail.width,'detail width');same(m=>m.tabs?.x,'tab alignment');same(m=>m.tabs?.y,'tab position');same(m=>m.content?.x,'content alignment');same(m=>m.content?.y,'content position');}
 }
 for(const width of [1440,1024,901,768,390]){await page.setViewportSize({width,height:1000});const states=[];for(const route of routes)states.push(await geometry(route,'no-selection',width));compare(states,'no-selection',width);}
 await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/tags');const csrf=await page.locator('input[name=csrf]').first().inputValue();const post=(url,form)=>page.request.post(base+url,{form:{csrf,...form}});
 const ids={};for(const name of ['MAL_LINKED','TA_LINKED','X'.repeat(120)]){assert.equal((await post('/tags/create',{name})).status(),200);ids[name]=(await(await page.request.get(base+'/tags/search?q='+name)).json()).exact_id;}
 const profileURLs=[];for(const [route,tag] of [[routes[0],'MAL_LINKED'],[routes[1],'TA_LINKED']]){const response=await post(route+'/new',{name:'MAL_LINKED',tag,short_description:'Linked intelligence profile'});assert.equal(response.status(),200);profileURLs.push(new URL(response.url()).pathname);}
 const seed=spawnSync('.venv/bin/python',['-c',`import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute("UPDATE cases SET stage=3,name=? WHERE id=1",('Long Case title '+('research '*18),));
for tid in sys.argv[2:]:c.execute("INSERT INTO case_tags VALUES(1,?,'2026',1)",(int(tid),))
c.commit()`,path.join(temp,'workflow.sqlite3'),String(ids.MAL_LINKED),String(ids.TA_LINKED)],{encoding:'utf8'});assert.equal(seed.status,0,seed.stderr);
 const selected=[...profileURLs,'/tags/'+ids.MAL_LINKED];
 for(const width of [1440,1024,901,768,390]){
  await page.setViewportSize({width,height:1000});
  for(const state of ['selected','history','empty-results']){
   const metrics=[];
   for(let i=0;i<routes.length;i++){
    const url=state==='empty-results'?routes[i]+'?q=NO_MATCHING_INTELLIGENCE':selected[i]+(state==='history'?'?tab=history':'');metrics.push(await geometry(url,state,width));
    if(state==='history'){assert.equal(await page.locator('tbody tr').count(),1);assert.equal(await page.locator('.mip-table-stage-badge.is-completed').count(),1);assert.ok(await page.getByRole('link',{name:/Open case/}).isVisible());}
    if(width<=900&&state==='selected'){
     await page.locator('[data-workspace-back]').click();await page.locator('.intelligence-directory').waitFor();await page.locator('.intelligence-directory .family-choice[aria-current=page]').click();await page.locator('.family-profile-header').waitFor();
    }
   }
   compare(metrics,state,width);
  }
  await page.goto(base+'/tags');await page.locator('.intelligence-filters summary').click();const popup=await page.locator('.intelligence-filter-fields').boundingBox();assert.ok(popup.x>=0&&popup.x+popup.width<=width,'Filter controls stay within viewport at '+width);
 }
 // Very long stored names and metadata must wrap without changing pane geometry.
 for(const [i,route] of routes.slice(0,2).entries())assert.equal((await post(route+'/new',{name:'Long intelligence '.repeat(10),tag:(i?'TA_':'MAL_')+'LONG',short_description:'Long metadata '.repeat(70),aliases:['Long alias '.repeat(15)]})).status(),200);
 for(const width of [1440,901,390]){await page.setViewportSize({width,height:1000});for(const route of routes){const url=route==='/tags'?route+'/'+ids['X'.repeat(120)]:route+'?q=Long+intelligence';await page.goto(base+url);if(width<=900&&route!=='/tags')await page.locator('.intelligence-directory .family-choice').click();await page.locator('.family-profile-header').waitFor();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const panel=await page.locator('.family-workspace').boundingBox();for(const action of await page.locator('.family-profile-header .family-actions>*').all()){const b=await action.boundingBox();assert.ok(b.x+b.width<=panel.x+panel.width+1);}await page.screenshot({path:path.join(screens,`long-${routes.indexOf(route)}-${width}.png`)});}}
 assert.deepEqual(errors,[]);console.log('Intelligence workspace comparisons passed: no selection, selected, History, empty results, long content; matched boundaries, shared surfaces, mobile navigation and filter bounds at 390–1440px. Screenshots: '+screens);
})().catch(error=>{console.error(error);console.error(logs.slice(-1200));process.exitCode=1;}).finally(async()=>{await browser?.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temp,{recursive:true,force:true});});
