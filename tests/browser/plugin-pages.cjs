/* Real folder discovery and management, without any editor or worker fixture. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'mare-installed-plugins-')),packages=path.join(temp,'plugins'),port=8793,base=`http://127.0.0.1:${port}`;
for(const [id,name] of [['hello_plugin','Hello World'],['second_plugin','Second plugin']]){
 const directory=path.join(packages,id);fs.mkdirSync(directory,{recursive:true});
 fs.writeFileSync(path.join(directory,'plugin.json'),JSON.stringify({schema:'mws-plugin/1',id,name,description:'External package',version:'1.0.0',author:'Test',entrypoint:'main.py:run',api_version:'v1',sdk_version:'>=1,<2',plugin_api:'1',permissions:[],dependencies:[]}));
 fs.writeFileSync(path.join(directory,'main.py'),'def run(context):\n    print("Hello World")\n');
}
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:temp+'/data',MARE_EDITOR_TEST_PORT:String(port),MARE_PLUGINS_DIR:packages},stdio:['ignore','ignore','pipe']});
let browser,logs='';server.stderr.on('data',data=>logs+=data);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(error){if(i>100)throw Error(logs||error.message);await new Promise(resolve=>setTimeout(resolve,100));}}
 const executablePath=process.env.MARE_BROWSER_EXECUTABLE;
 browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
 const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await Promise.all([page.waitForURL(base+'/'),page.getByRole('button',{name:'Sign in',exact:true}).click()]);
 // Compare the shared page container at desktop, tablet and phone widths.
 const screenshots=process.env.MARE_DEVELOPER_SCREENSHOTS;
 if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
 for(const viewport of [{width:1440,height:900},{width:768,height:900},{width:390,height:844}]){
  await page.setViewportSize(viewport);const layouts=[];
  for(const [name,route,content] of [['api','/api','.api-workspace'],['sdk','/developer/sdk','.developer-heading'],['plugins','/plugins','[data-plugin-management]']]){
   await page.goto(base+route);await page.locator(content).waitFor();
   if(name==='plugins')await page.locator('[data-detail-name]').filter({hasText:'Hello World'}).waitFor();
   const layout=await page.evaluate(selector=>{
    const main=document.querySelector('main.page'),tabs=document.querySelector('.developer-navigation'),content=document.querySelector(selector),style=getComputedStyle(main),box=main.getBoundingClientRect(),tabBox=tabs.getBoundingClientRect(),contentBox=content.getBoundingClientRect();
    return {padding:[style.paddingTop,style.paddingRight,style.paddingBottom,style.paddingLeft],tabLeft:tabBox.left-box.left,tabRight:box.right-tabBox.right,contentLeft:contentBox.left-box.left,gap:contentBox.top-tabBox.bottom,overflow:document.documentElement.scrollWidth>innerWidth,contentBottom:box.bottom-contentBox.bottom};
   },content);
   assert.equal(layout.overflow,false,`${name} overflows at ${viewport.width}px`);
   assert.equal(layout.contentLeft,parseFloat(layout.padding[3]),`${name} has double content padding`);
   if(name==='plugins')assert.equal(layout.contentBottom,parseFloat(layout.padding[2]),'Plugins bottom padding');
   layouts.push(layout);
   if(screenshots)await page.screenshot({path:path.join(screenshots,`${name}-${viewport.width}.png`)});
  }
  for(const layout of layouts.slice(1)){
   assert.deepEqual(layout.padding,layouts[0].padding,`Developer page padding at ${viewport.width}px`);
   assert.equal(layout.tabLeft,layouts[0].tabLeft);assert.equal(layout.tabRight,layouts[0].tabRight);
  }
  assert.equal(layouts[2].gap,layouts[1].gap,'Plugins and SDK share the tabs/content gap');
  console.log(`Developer padding at ${viewport.width}px: ${JSON.stringify(layouts)}`);
 }
 await page.setViewportSize({width:1280,height:800});
 await page.goto(base+'/plugins');await page.locator('[data-detail-name]').filter({hasText:'Hello World'}).waitFor();
 assert.deepEqual(await page.locator('.developer-navigation a').allTextContents(),['API','SDK','Plugins']);
 assert.equal(await page.locator('[data-edit], [data-plugin-new], #plugin-create').count(),0);
 const splitter=page.getByRole('separator',{name:'Plugin inventory width'}),width=Number(await splitter.getAttribute('aria-valuenow'));await splitter.focus();await page.keyboard.press('ArrowRight');assert.equal(Number(await splitter.getAttribute('aria-valuenow')),width+20);
 const row=id=>page.locator(`[data-plugin-id="${id}"]`),menu=page.getByRole('menu',{name:'Plugin actions'});
 await row('second_plugin').click({button:'right'});await menu.waitFor();
 assert.equal(await page.locator('[data-detail-name]').textContent(),'Second plugin');
 assert.deepEqual(await menu.getByRole('menuitem').allTextContents(),['✓Enable','⊘Disable','×Delete']);
 assert.ok(await menu.getByRole('menuitem',{name:'Disable',exact:true}).isDisabled());
 await menu.getByRole('menuitem',{name:'Enable',exact:true}).click();await page.locator('[data-management-status]').filter({hasText:'Plugin enabled.'}).waitFor();
 await row('second_plugin').click({button:'right'});assert.ok(await menu.getByRole('menuitem',{name:'Enable',exact:true}).isDisabled());
 await page.keyboard.press('Escape');await menu.waitFor({state:'detached'});
 await row('second_plugin').click({button:'right'});await page.locator('[data-detail-name]').click();await menu.waitFor({state:'detached'});
 await row('hello_plugin').click();await page.locator('[data-detail-name]').filter({hasText:'Hello World'}).waitFor();assert.equal(await page.locator('[data-detail-name]').textContent(),'Hello World');
 await row('hello_plugin').click({button:'right'});await menu.getByRole('menuitem',{name:'Delete',exact:true}).click();
 await page.locator('#plugin-delete').waitFor();await page.locator('[data-delete-cancel]').click();assert.ok(fs.existsSync(path.join(packages,'hello_plugin')));
 await row('hello_plugin').click({button:'right'});await menu.getByRole('menuitem',{name:'Delete',exact:true}).click();await page.locator('#plugin-delete button[type=submit]').click();
 await row('hello_plugin').waitFor({state:'detached'});assert.equal(fs.existsSync(path.join(packages,'hello_plugin')),false);
 await page.locator('#developer-tab-sdk').click();await page.waitForURL(base+'/developer/sdk');await page.locator('#sdk-doc-content').waitFor();assert.ok((await page.locator('#sdk-doc-content').textContent()).includes('External plugin development'));
 await page.locator('#developer-tab-api').click();await page.waitForURL(base+'/api');await page.locator('#developer-tab-plugins').click();await page.waitForURL(/\/plugins/);await row('second_plugin').waitFor();
 await page.goBack();await page.waitForURL(base+'/api');await page.goForward();await page.waitForURL(/\/plugins/);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight));
 const response=await page.request.get(base+'/developer/editor');assert.equal(response.status(),404);
 assert.deepEqual(errors,[]);console.log('Plugin browser checks passed: navigation/history, external discovery, permissions-driven actions, selection, enablement, menu close, confirmed/canceled deletion and viewport.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server.exitCode===null){server.kill();await new Promise(resolve=>server.once('exit',resolve));}fs.rmSync(temp,{recursive:true,force:true});});
