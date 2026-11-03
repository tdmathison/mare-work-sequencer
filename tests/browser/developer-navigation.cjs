const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-developer-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8815';
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_EDITOR_BROWSER_TEST:'1',MARE_EDITOR_TEST_PORT:'8815'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.getByLabel('Username').fill('editor-test');await page.getByLabel('Password',{exact:true}).fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in'}).click()]);
 await page.goto(base+'/developer/sdk');
 const tabs=page.getByRole('navigation',{name:'Developer sections',exact:true});
 assert.deepEqual(await tabs.getByRole('link').allTextContents(),['API','SDK']);
 const sidebar=page.locator('#application-sidebar');
 assert.equal(await sidebar.locator('a[href="/plugins"]').count(),0);
 assert.equal(await tabs.getByRole('link',{name:'SDK',exact:true}).getAttribute('aria-current'),'page');
 await tabs.getByRole('link',{name:'API',exact:true}).click();await page.waitForURL(base+'/api');await page.locator('#swagger-ui .swagger-ui').waitFor();
 assert.equal(await tabs.getByRole('link',{name:'API',exact:true}).getAttribute('aria-current'),'page');
 await page.goBack();await page.waitForURL(base+'/developer/sdk');await page.reload();assert.equal(await tabs.getByRole('link',{name:'SDK',exact:true}).getAttribute('aria-current'),'page');
 for(const width of [1440,390]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/mws-developer-retired-'+width+'.png',animations:'disabled'});}
 assert.equal((await context.request.get(base+'/plugins')).status(),404);
 assert.equal((await context.request.post(base+'/plugins/discovery',{form:{csrf:await page.locator('[name=csrf]').first().inputValue()}})).status(),404);
 assert.deepEqual(errors,[]);console.log('PASS: Developer API/SDK only, shared tabs, Swagger UI, history/refresh, desktop/mobile layout, deleted routes 404.');
})().catch(e=>{console.error(log.slice(-3500));console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill();fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
