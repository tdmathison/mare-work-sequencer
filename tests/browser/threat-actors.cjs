const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'mare-actor-browser-')),real=fs.realpathSync(temporary);
const workspace=path.join(path.dirname(real),'.mare-backup-work-'+crypto.createHash('sha256').update(real).digest('hex').slice(0,16));
const base='http://127.0.0.1:8804';
const server=spawn('.venv/bin/python',['tests/browser/threat-actors-server.py'],{env:{...process.env,MARE_DATA_DIR:temporary,MARE_ACTOR_BROWSER_TEST:'1',MARE_ACTOR_TEST_PORT:'8804'},stdio:['ignore','ignore','pipe']});
let browser,log='';server.stderr.on('data',d=>log+=d);const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await delay(100);}}
 browser=await chromium.launch({headless:true,executablePath:process.env.MARE_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:900}}),page=await context.newPage();page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/threat-actors');await page.waitForURL(base+'/login');
 await page.getByLabel('Username').fill('actor-browser');await page.getByLabel('Password',{exact:true}).fill('actor-browser-password');await page.getByRole('button',{name:'Sign in'}).click();await page.waitForURL(base+'/');
 await page.getByRole('link',{name:'THREAT ACTORS',exact:true}).click();await page.getByRole('heading',{name:'Actor knowledge starts here'}).waitFor();assert.equal(await page.locator('.admin-nav a[aria-current=page]').getAttribute('href'),'/threat-actors');
 await page.getByRole('link',{name:'MALWARE FAMILIES',exact:true}).click();await page.getByRole('link',{name:'Create malware family',exact:true}).click();
 await page.getByLabel('Malware family name').fill('Browser family');await page.getByLabel('Tag',{exact:true}).fill('MAL_BROWSER');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header h2').filter({hasText:'Browser family'}).waitFor();const familyURL=new URL(page.url()).pathname;
 await page.getByRole('link',{name:'TAGS',exact:true}).click();await page.locator('tr').filter({hasText:'TA_APT_BROWSER'}).getByRole('link',{name:'Create threat actor',exact:true}).click();
 assert.equal(await page.getByLabel('Tag',{exact:true}).inputValue(),'TA_APT_BROWSER');assert.equal(await page.getByLabel('Threat actor name').inputValue(),'');
 await page.getByLabel('Threat actor name').fill('Browser actor');const alias=()=>page.getByRole('textbox',{name:'Aliases',exact:true});
 for(const value of ['Actor Alias','Multi Word Alternative']){await alias().fill(value);await alias().press('Enter');}
 assert.equal(await page.locator('.family-alias-chip').count(),2);assert.ok(page.url().includes('/threat-actors/new'));
 const picker=()=>page.getByRole('combobox',{name:'Find a Malware Family'});
 await page.route('**/threat-actors/families/search?**',route=>route.fulfill({status:503,body:'Unavailable'}));await picker().fill('Browser');await page.getByText('Unable to load families. Retry your search.',{exact:true}).waitFor();await page.unroute('**/threat-actors/families/search?**');
 await picker().fill('NoSuchFamily');await page.getByText('No matching configured families.',{exact:true}).waitFor();
 await picker().fill('Browser');await page.getByRole('option',{name:'Browser family · MAL_BROWSER',exact:true}).waitFor();await picker().press('ArrowDown');await picker().press('Enter');assert.equal(await page.locator('.actor-family-chip').count(),1);
 await page.getByLabel('Long description').fill('<script>not executed</script>\nActor research.');await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header h2').filter({hasText:'Browser actor'}).waitFor();const actorURL=new URL(page.url()).pathname;
 assert.equal(await page.locator('.family-content script').count(),0);await page.locator('.actor-known-families a').filter({hasText:'Browser family'}).waitFor();
 await page.getByRole('link',{name:'History',exact:true}).click();await page.getByRole('link',{name:'MARE-ACTOR-1',exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'MARE-ACTOR-2',exact:true}).count(),0);
 await page.getByRole('link',{name:'OSINT & Reports',exact:true}).click();await page.getByRole('link',{name:'Add link',exact:true}).click();await page.getByLabel('Article title').fill('Actor source');await page.getByLabel('URL',{exact:true}).fill('https://example.com/actor-research');await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('link',{name:'Actor source'}).waitFor();
 const pdf=Buffer.from('%PDF-1.4\nActor research report\n%%EOF');await page.getByLabel('Research documents').setInputFiles({name:'actor-research.pdf',mimeType:'application/pdf',buffer:pdf});await page.getByRole('button',{name:'Upload reports',exact:true}).click();await page.locator('.family-report').waitFor();
 const dl=page.waitForEvent('download');await page.getByRole('link',{name:'Download report',exact:true}).click();const download=await dl;assert.equal(crypto.createHash('sha256').update(fs.readFileSync(await download.path())).digest('hex'),crypto.createHash('sha256').update(pdf).digest('hex'));
 await page.getByRole('link',{name:'Edit title/description'}).click();await page.getByLabel('Display title').fill('Saved actor report');await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('heading',{name:'Saved actor report'}).waitFor();
 await page.getByRole('link',{name:'Edit profile',exact:true}).click();await alias().waitFor();await page.getByRole('button',{name:'Remove alias Actor Alias',exact:true}).focus();await page.keyboard.press('Enter');await alias().fill('Added after reopening');await alias().press('Enter');
 await page.getByRole('button',{name:'Remove family Browser family',exact:true}).focus();await page.keyboard.press('Enter');assert.equal(await page.locator('.actor-family-chip').count(),0);
 await picker().fill('MAL_BROWSER');await page.getByRole('option',{name:'Browser family · MAL_BROWSER',exact:true}).waitFor();await picker().press('ArrowDown');await picker().press('Enter');
 await page.getByRole('link',{name:'Cancel',exact:true}).click();await page.locator('#family-unsaved').waitFor();await page.locator('[data-unsaved=cancel]').click();assert.equal(await page.locator('.family-alias-chip').count(),2);
 for(const viewport of [{width:1366,height:900},{width:390,height:844}]){await page.setViewportSize(viewport);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.ok(await picker().isVisible());}
 await page.getByRole('button',{name:'Save',exact:true}).click();await page.locator('.family-profile-header h2').filter({hasText:'Browser actor'}).waitFor();await page.reload();await page.locator('.actor-known-families a').waitFor();assert.ok((await page.locator('.family-alias-chip').allTextContents()).join(' ').includes('Added after reopening'));assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.goto(base+'/tags');await page.locator('tr').filter({hasText:'TA_APT_BROWSER'}).getByRole('link',{name:'View threat actor',exact:true}).click();await page.waitForURL(url=>url.pathname===actorURL);
 const tagData=await(await page.request.get(base+'/cases/1/tags')).json();assert.ok(tagData.tags.some(t=>t.name==='TA_APT_BROWSER'));assert.ok(tagData.tags.some(t=>t.name==='MAL_BROWSER'));
 await page.goto(base+'/dashboards');const future=page.locator('.directory-row').filter({hasText:'Threat Actors'});assert.equal(await future.getByRole('link').count(),0);assert.match(await future.innerText(),/Coming later/);
 const publicData=await(await page.request.get(base+'/dashboards/malware-families/data')).text();assert.ok(!publicData.includes('Browser actor')&&!publicData.includes('Added after reopening'));
 assert.deepEqual(errors,[]);console.log('PASS: existing TA tag → actor aliases/configured family picker → OSINT/report upload and hash-checked download → tag-only History → edit/reopen; Tags View/Create, search errors/empty states, unsaved guard, safe/private data and desktop/narrow layouts.');
})().catch(e=>{console.error(e);console.error(log.slice(-2200));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));fs.rmSync(temporary,{recursive:true,force:true});fs.rmSync(workspace,{recursive:true,force:true});});
