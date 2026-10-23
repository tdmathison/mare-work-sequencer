const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-alias-browser-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8803';
const server=spawn('.venv/bin/python',['tests/browser/malware-families-server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_FAMILY_BROWSER_TEST:'1',MARE_FAMILY_TEST_PORT:'8803'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1366,height:900}});page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('family-browser');await page.getByLabel('Password',{exact:true}).fill('family-browser-password');await page.getByRole('button',{name:'Sign in'}).click();await page.waitForURL(base+'/');
 await page.goto(base+'/malware-families/new');
 const input=()=>page.getByLabel('Aliases',{exact:true}),chips=()=>page.locator('.family-alias-chip');
 const mutations=[];page.on('request',r=>{if(r.method()==='POST')mutations.push(new URL(r.url()).pathname);});
 const before=await (await page.request.get(base+'/cases/1/tags')).json();
 await page.getByLabel('Malware family name').fill('Alias test');await page.getByLabel('Tag',{exact:true}).fill('MAL_BROWSER');
 async function add(value){await input().fill(value);await input().press('Enter');}
 await add(' RedLine ');await add('Multiple Word Name');await add('<img src=x onerror=alert(1)>');
 assert.equal(await chips().count(),3);assert.ok(page.url().endsWith('/new'));assert.deepEqual(mutations,[]);
 assert.equal(await chips().locator('input').first().inputValue(),'RedLine');assert.equal(await chips().locator('img').count(),0);
 await add('rEdLiNe');assert.equal(await chips().count(),3);assert.match(await page.locator('#family-alias-status').textContent(),/already/);
 await input().fill('   ');await input().press('Enter');assert.equal(await chips().count(),3);
 await input().fill('');
 await page.getByRole('button',{name:'Remove alias Multiple Word Name',exact:true}).focus();await page.keyboard.press('Enter');assert.equal(await chips().count(),2);assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'Remove alias <img src=x onerror=alert(1)>');
 await add('Multiple Word Name');
 // Force a real server validation failure, retaining the submitted chips.
 await page.getByLabel('Tag',{exact:true}).fill('BAD_TAG');await page.locator('[data-family-form]').evaluate(form=>form.noValidate=true);
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await chips().count(),3);assert.equal(await input().inputValue(),'');
 await page.getByLabel('Tag',{exact:true}).fill('MAL_BROWSER');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header').waitFor();
 assert.equal(await chips().count(),3);assert.equal(await chips().getByRole('button').count(),0);
 assert.deepEqual((await chips().allTextContents()).map(x=>x.trim()),['RedLine','<img src=x onerror=alert(1)>','Multiple Word Name']);
 const after=await (await page.request.get(base+'/cases/1/tags')).json();assert.deepEqual(after,before);
 await page.getByRole('link',{name:'Edit profile'}).click();await input().waitFor();assert.equal(await chips().count(),3);
 await page.getByRole('button',{name:'Remove alias RedLine',exact:true}).click();await add('Other alternative');
 // Changes to aliases participate in the existing navigation guard.
 await page.getByRole('link',{name:'Cancel',exact:true}).click();await page.locator('#family-unsaved').waitFor();await page.locator('[data-unsaved=cancel]').click();assert.equal(await chips().count(),3);
 for(const viewport of [{width:1366,height:900},{width:390,height:844}]){
   await page.setViewportSize(viewport);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const order=await page.locator('[name=name],#family-alias-input,[name=tag]').evaluateAll(els=>els.map(el=>el.name));assert.deepEqual(order,['name','alias_draft','tag']);
 }
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header').waitFor();await page.reload();assert.equal(await chips().count(),3);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.getByLabel('Find a malware family').fill('other ALTERNATIVE');await page.getByRole('button',{name:'Search',exact:true}).click();await page.locator('.family-choice').first().waitFor();assert.equal(await page.locator('.family-choice').count(),1);
 await page.getByRole('link',{name:/Alias test/}).click();await page.getByRole('link',{name:'Edit profile'}).click();await input().waitFor();
 while(await chips().count())await chips().first().getByRole('button').click();
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header').waitFor();assert.equal(await chips().count(),0);
 assert.deepEqual(errors,[]);console.log('PASS: alias Enter/chips, multi-word/case/whitespace/duplicates, keyboard removal, safe text, failed-save retention, edit/order/removal persistence, unsaved guard, search, unchanged case tags, desktop/narrow forms and overview.');
})().catch(e=>{console.error(e);console.error(log.slice(-1600));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
