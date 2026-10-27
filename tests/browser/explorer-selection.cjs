const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'mare-explorer-')),real=fs.realpathSync(tmp),workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8806',server=spawn('.venv/bin/python',['tests/browser/data-explorer-server.py'],{env:{...process.env,MARE_DATA_DIR:tmp,MARE_EXPLORER_TEST:'1'},stdio:['ignore','ignore','pipe']});let browser,logs='';server.stderr.on('data',d=>logs+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch{if(i>100||server.exitCode!==null)throw Error(logs);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1366,height:900}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/data-explorer');await page.waitForURL(base+'/login');await page.getByLabel('Username').fill('explorer-browser');await page.getByLabel('Password',{exact:true}).fill('explorer-browser-password');await page.getByRole('button',{name:'Sign in'}).click();await page.waitForURL(base+'/');
 await page.getByRole('link',{name:'DATA EXPLORER',exact:true}).click();await page.locator('#explorer-tally').filter({hasText:'5 objects'}).waitFor();
 assert.equal(await page.locator('.admin-nav').evaluate(n=>n.getBoundingClientRect().height),52);
 assert.equal(await page.locator('.admin-nav > :last-child').textContent(),'DATA EXPLORER');assert.equal(await page.locator('.admin-nav a[aria-current=page]').getAttribute('href'),'/data-explorer');
 const graph=fn=>page.evaluate(fn);
 const state=()=>graph(()=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy;return {zoom:cy.zoom(),pan:cy.pan(),nodes:cy.nodes().map(n=>({id:n.id(),position:n.position()})),edges:cy.edges().length};});
 const filters=()=>page.getByRole('button',{name:/^Filters, /});
 const choose=async id=>{if(await page.locator('#explorer-details').isVisible())await page.getByRole('button',{name:'Close details',exact:true}).click();await page.getByRole('button',{name:'Legend & objects',exact:true}).click();await page.locator('#explorer-objects').selectOption(id);};

 await page.locator('#explorer-status').filter({hasText:'Layout settled'}).waitFor();
 const selected=()=>graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes(':selected').map(n=>n.id()).sort());
 const ids=await graph(()=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy;return {family:cy.nodes('[kind="family"]').id(),actor:cy.nodes('[kind="actor"]').id()};});
 async function place(zoom=1){await page.evaluate(({ids,zoom})=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy;cy.elements().unselect();cy.getElementById('case:1').position({x:100,y:100});cy.getElementById('case:2').position({x:400,y:100});cy.getElementById('case:3').position({x:700,y:100});cy.getElementById(ids.family).position({x:350,y:330});cy.getElementById(ids.actor).position({x:650,y:330});cy.viewport({zoom,pan:{x:100,y:100}});}, {ids,zoom});}
 async function point(id){return page.evaluate(id=>{const canvas=document.querySelector('#explorer-canvas'),cy=canvas._cyreg.cy,p=cy.getElementById(id).renderedPosition(),r=canvas.getBoundingClientRect();return {x:r.x+p.x,y:r.y+p.y};},id);}
 async function marquee(start,end,key='Control'){
  await page.keyboard.down(key);await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:10});await page.mouse.up();await page.keyboard.up(key);await delay(40);
 }
 async function toggle(id,key='Control'){const p=await point(id);await page.keyboard.down(key);await page.mouse.click(p.x,p.y);await page.keyboard.up(key);await delay(30);}
 async function drag(id,dx,dy){const p=await point(id);await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+dx,p.y+dy,{steps:10});await page.mouse.up();await delay(40);}
 function moved(before,after,targets,dx,dy){for(const original of before.nodes){const next=after.nodes.find(n=>n.id===original.id);assert.ok(Math.abs(next.position.x-original.position.x-(targets.includes(original.id)?dx:0))<.05,original.id+' x');assert.ok(Math.abs(next.position.y-original.position.y-(targets.includes(original.id)?dy:0))<.05,original.id+' y');}}

 async function assertGlow(){const styles=await graph(()=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy;return cy.nodes(':selected').map(n=>({kind:n.data('kind'),halo:Number(n.style('underlay-opacity')),outline:parseFloat(n.style('border-width'))*cy.zoom(),padding:parseFloat(n.style('underlay-padding'))*cy.zoom(),opacity:Number(n.style('opacity'))}));});assert.ok(styles.every(s=>s.halo>=.5&&Math.abs(s.outline-3)<.05&&Math.abs(s.padding-9)<.05&&s.opacity===1),JSON.stringify(styles));}
 for(const zoom of [.5,1,1.5]){
  await place(zoom);const one=await point('case:1'),two=await point('case:2'),margin=Math.max(50,zoom*60),start={x:one.x-margin,y:one.y-margin},short={x:one.x+Math.max(35,zoom*45),y:one.y+margin};
  await page.keyboard.down('Control');await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(short.x,short.y,{steps:5});await delay(40);
  assert.ok(await page.locator('.explorer-marquee').isVisible());
  const rectangle=await page.locator('.explorer-marquee').evaluate(el=>({border:getComputedStyle(el).borderTopWidth,events:getComputedStyle(el).pointerEvents,width:el.getBoundingClientRect().width,z:getComputedStyle(el).zIndex}));assert.equal(rectangle.border,'2px');assert.equal(rectangle.events,'none');assert.ok(rectangle.width>50&&Number(rectangle.z)>0);
  assert.deepEqual(await graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes('.marquee-preview').map(n=>n.id()).sort()),['case:1']);
  await page.mouse.move(two.x+8,short.y,{steps:5});await delay(40);assert.deepEqual(await graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes('.marquee-preview').map(n=>n.id()).sort()),['case:1','case:2']);
  if(process.env.MARE_SELECTION_SCREENSHOT && zoom===1)await page.screenshot({path:process.env.MARE_SELECTION_SCREENSHOT+'-marquee.png'});
  await page.mouse.move(short.x,short.y,{steps:5});await delay(40);assert.deepEqual(await graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes('.marquee-preview').map(n=>n.id()).sort()),['case:1']);
  await page.mouse.up();await page.keyboard.up('Control');await delay(30);assert.ok(await page.locator('.explorer-marquee').isHidden());assert.deepEqual(await selected(),['case:1']);await assertGlow();
  await toggle('case:2');await assertGlow();
  // Additive previews retain the bright glow on seed nodes outside the rectangle.
  await page.keyboard.down('Control');await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(short.x,short.y,{steps:5});await delay(40);assert.deepEqual(await graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes('.marquee-preview').map(n=>n.id()).sort()),['case:1','case:2']);
  await page.evaluate(()=>document.dispatchEvent(new Event('pointercancel')));assert.ok(await page.locator('.explorer-marquee').isHidden());await page.mouse.up();await page.keyboard.up('Control');await delay(30);await assertGlow();
  await graph(()=>{document.querySelector('#explorer-canvas')._cyreg.cy.panBy({x:20,y:10});});await assertGlow();
 }
 await page.locator('#explorer-canvas').focus();await page.keyboard.press('Escape');await page.mouse.move(0,0);await delay(30);
 assert.equal(await graph(()=>parseFloat(document.querySelector('#explorer-canvas')._cyreg.cy.getElementById('case:1').style('underlay-opacity'))),.12);
 await place();const p1=await point('case:1'),p2=await point('case:2'),initial=await state();
 // The second case's center is inside but its boundary extends beyond the marquee.
 await marquee({x:p1.x-85,y:p1.y-65},{x:p2.x+5,y:p2.y+55});
 assert.deepEqual(await selected(),['case:1','case:2']);assert.deepEqual((await state()).pan,initial.pan);
 assert.equal(await page.locator('#explorer-tray-title').textContent(),'2 objects selected');if(process.env.MARE_SELECTION_SCREENSHOT)await page.screenshot({path:process.env.MARE_SELECTION_SCREENSHOT});assert.ok(await page.locator('#explorer-details-toggle').isHidden());assert.ok(await page.locator('#explorer-details').isHidden());
 let before=await state();await drag('case:1',55,30);moved(before,await state(),['case:1','case:2'],55,30);assert.deepEqual(await selected(),['case:1','case:2']);
 const unselectedPoint=await point('case:3');await page.mouse.click(unselectedPoint.x,unselectedPoint.y);assert.deepEqual(await selected(),['case:3']);assert.equal(await page.locator('#explorer-details-toggle').isHidden(),false);
 await page.locator('#explorer-canvas').focus();await page.keyboard.press('Escape');assert.deepEqual(await selected(),[]);await toggle('case:1');await toggle('case:2');
 await toggle('case:2');assert.deepEqual(await selected(),['case:1']);await toggle('case:3','Meta');assert.deepEqual(await selected(),['case:1','case:3']);await assertGlow();
 const familyPoint=await point(ids.family);await marquee({x:familyPoint.x-75,y:familyPoint.y-65},{x:familyPoint.x+75,y:familyPoint.y+65});assert.deepEqual(await selected(),['case:1','case:3',ids.family].sort());await toggle(ids.actor);await assertGlow();
 await page.locator('#explorer-canvas').focus();await page.keyboard.press('Escape');assert.deepEqual(await selected(),[]);
 await toggle('case:1');await toggle('case:2');await page.getByRole('button',{name:'Clear Selection',exact:true}).first().click();assert.deepEqual(await selected(),[]);
 // Native group deltas are model coordinates, independent of zoom and pan.
 await place(.7);await toggle('case:1');await toggle('case:2');before=await state();await drag('case:1',70,35);moved(before,await state(),['case:1','case:2'],100,50);
 await graph(()=>{document.querySelector('#explorer-canvas')._cyreg.cy.panBy({x:35,y:-15});});before=await state();await drag('case:2',-35,21);moved(before,await state(),['case:1','case:2'],-50,30);
 // Empty-canvas click clears; unmodified background drag still pans.
 const canvas=await page.locator('#explorer-canvas').boundingBox(),empty={x:canvas.x+12,y:canvas.y+canvas.height/2};await page.mouse.click(empty.x,empty.y);assert.deepEqual(await selected(),[]);
 before=await state();await page.mouse.move(empty.x,empty.y);await page.mouse.down();await page.mouse.move(empty.x+35,empty.y+20,{steps:8});await page.mouse.up();assert.notDeepEqual((await state()).pan,before.pan);
 await choose('case:1');assert.equal(await page.locator('#explorer-tray-title').textContent(),'MARE-EXPLORER-1');await page.getByRole('button',{name:'Expand Standard MIP',exact:true}).click();await page.getByRole('button',{name:'Collapse Standard MIP',exact:true}).waitFor();
 const children=await graph(()=>document.querySelector('#explorer-canvas')._cyreg.cy.nodes('[kind="category"]').map(n=>n.id()));
 await place(); // primary positions only; place children deliberately away from other nodes.
 await page.evaluate(children=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy;children.forEach((id,i)=>cy.getElementById(id).position({x:100+i*110,y:360}));},children);
 await toggle('case:1');await toggle(children[0]);before=await state();await drag('case:1',25,15);moved(before,await state(),['case:1',...children],25,15);assert.deepEqual(await selected(),['case:1',children[0]].sort());
 // Layouts preserve group membership and allow subsequent manual movement.
 for(const mode of ['tree','radial','clusters']){await page.getByLabel('Auto Arrange layout',{exact:true}).selectOption(mode);await page.locator('#explorer-status').filter({hasText:'Layout settled'}).waitFor();assert.deepEqual(await selected(),['case:1',children[0]].sort());await assertGlow();}
 // Hidden categories leave the selection, restoring the single case summary.
 await filters().click();await page.getByLabel('Show MIP contents',{exact:true}).uncheck();await page.keyboard.press('Escape');assert.deepEqual(await selected(),['case:1']);
 await toggle('case:2');assert.equal((await selected()).length,2);
 await page.getByRole('button',{name:'Legend & objects',exact:true}).click();await Promise.all([page.waitForResponse(response=>response.url().includes('/data-explorer/data?')),page.getByRole('button',{name:'Refresh data',exact:true}).click()]);await page.getByRole('button',{name:'Close legend and objects',exact:true}).click();assert.deepEqual(await selected(),['case:1','case:2']);
 await filters().click();await page.getByLabel('Cases',{exact:true}).uncheck();await page.locator('#explorer-tally').filter({hasText:'2 objects'}).waitFor();assert.deepEqual(await selected(),[]);await page.getByLabel('Cases',{exact:true}).check();await page.locator('#explorer-tally').filter({hasText:'5 objects'}).waitFor();await page.keyboard.press('Escape');
 await toggle('case:1');await toggle('case:2');await graph(()=>{document.querySelector('#explorer-canvas')._cyreg.cy.getElementById('case:2').remove();});await delay(30);assert.deepEqual(await selected(),['case:1']);
 await page.reload();await page.locator('#explorer-tally').filter({hasText:'5 objects'}).waitFor();await page.locator('#explorer-status').filter({hasText:'Layout settled'}).waitFor();
 // Canceled marquee and release outside canvas leave the next pan/click functional.
 await place();const a=await point('case:1');await page.keyboard.down('Control');await page.mouse.move(a.x-85,a.y-65);await page.mouse.down();await page.mouse.move(a.x+20,a.y+20);await page.evaluate(()=>document.dispatchEvent(new Event('pointercancel')));await page.mouse.up();await page.keyboard.up('Control');
 await toggle('case:1');await toggle('case:2');assert.equal((await selected()).length,2,JSON.stringify(await selected()));
 before=await state();const last=await point('case:1');await page.mouse.move(last.x,last.y);await page.mouse.down();await page.mouse.move(canvas.x-5,last.y+10,{steps:8});await page.mouse.up();assert.deepEqual(await selected(),['case:1','case:2']);
 await page.locator('#explorer-canvas').focus();await page.keyboard.press('Escape');assert.deepEqual(await selected(),[]);

 // Marquee normalization remains linear and responsive on a larger displayed graph.
 await place(.2);
 await graph(()=>{const cy=document.querySelector('#explorer-canvas')._cyreg.cy,source=cy.nodes('[kind="family"]')[0].data();cy.add(Array.from({length:400},(_,i)=>({data:{...source,id:'bulk:'+i},position:{x:1000+(i%20)*150,y:200+Math.floor(i/20)*100}})));});
 const selectionStarted=Date.now();await marquee({x:canvas.x+270,y:canvas.y+110},{x:canvas.x+900,y:canvas.y+550},'Meta');assert.equal((await selected()).filter(id=>id.startsWith('bulk:')).length,400);assert.ok(Date.now()-selectionStarted<3000);
 assert.deepEqual(errors,[]);console.log('PASS Explorer selection: center marquee, CTRL/Command toggle/add, group deltas after zoom/pan, stationary neighbors, category followers exactly once, layouts, hidden-node pruning, cancel/outside release, single details, Escape and normal pan.');
})().catch(error=>{console.error(error);console.error(logs.slice(-2200));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
