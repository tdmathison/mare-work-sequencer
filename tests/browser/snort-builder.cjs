const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'mare-snort-editor-')),port=8794,base=`http://127.0.0.1:${port}`;
const fake=process.env.MARE_SNORT_BROWSER_FAKE==='1';let engineSettings={MARE_SNORT_EXECUTABLE:''};
if(fake){
 const executable=path.join(data,'fake-snort'),runner=path.join(data,'fake-runner'),profile=path.join(data,'snort.lua');
 fs.writeFileSync(executable,`#!${path.join(root,'.venv/bin/python')}
import sys
if '-V' in sys.argv:print('Snort++ Version 3.1.99 fake UI fixture')
elif '--help-options' in sys.argv:print('-T -R -r -c --lua -A -l')
else:print('content http_uri alert_json')
`,{mode:0o700});
 fs.writeFileSync(runner,`#!${path.join(root,'.venv/bin/python')}
import sys,time,json,pathlib
w=pathlib.Path(sys.argv[3])
if '-r' in sys.argv:
 time.sleep(1)
 name=sys.argv[sys.argv.index('-r')+1]
 (w/'alert_json.txt').write_text(json.dumps(dict(rule='1:1000001:1',msg='FAKE UI ONLY',pkt_num=1))+'\\n' if 'target' in name else '')
print('FAKE ENGINE: lifecycle fixture, not Snort validation')
`,{mode:0o700});
 fs.writeFileSync(profile,'-- fake profile only');engineSettings={MARE_SNORT_EXECUTABLE:executable,MARE_SNORT_PROFILE:profile,MARE_SNORT_RUNNER:runner};
}
const server=spawn('.venv/bin/python',['tests/browser/server.py'],{cwd:root,env:{...process.env,MARE_EDITOR_BROWSER_TEST:'1',MARE_DATA_DIR:data,MARE_EDITOR_TEST_PORT:String(port),...engineSettings},stdio:['ignore','ignore','pipe']});let log='',browser;server.stderr.on('data',b=>log+=b);
(async()=>{
 for(let i=0;;i++){try{await fetch(base+'/login');break;}catch(e){if(i>100||server.exitCode!==null)throw Error(log);await new Promise(r=>setTimeout(r,100));}}
 browser=await chromium.launch({headless:true,...(process.env.MARE_BROWSER_EXECUTABLE?{executablePath:process.env.MARE_BROWSER_EXECUTABLE}:{})});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/login');await page.locator('[name=username]').fill('editor-test');await page.locator('[name=password]').fill('temporary-editor-test-123');await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.goto(base+'/tools/snort-rule-builder');const f=page.frameLocator('iframe[title^="Snort Rule Builder"]'),tool=f.locator('[data-snort-tool]');await f.locator('[data-draft]').filter({hasText:'Standalone draft ready'}).waitFor();
 const source=()=>tool.evaluate(r=>r.snortView.state.doc.toString());
 const defaultSource=await source();await f.locator('[data-outline] button').filter({hasText:'Header'}).first().click();
 await f.locator('[data-inspector] select').first().waitFor();
 // Keep the viewport fixed: layout must follow the inspector, with case browser open.
 const inspector=f.locator('[data-inspector]');
 assert.equal(await f.locator('.snort-browser details').evaluate(n=>n.open),true);
 await inspector.getByLabel('Source port presets',{exact:true}).evaluate(n=>{const o=new Option('$A_VERY_LONG_CONFIGURATION_VARIABLE_THAT_MUST_NOT_WIDEN_THE_PRESETS_COLUMN','layout-test');n.add(o);n.value=o.value;});
 for(const width of [720,600,480,300,720]){
   await inspector.evaluate((n,w)=>n.style.width=w+'px',width);
   await inspector.getByLabel('Direction',{exact:true}).evaluate(n=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const layout=await inspector.evaluate(n=>{
     const box=name=>n.querySelector('[aria-label="'+name+'"]:is(input,select)').getBoundingClientRect();
     const names=['Source address','Source port','Destination address','Destination port'];
     return {pairs:names.map(name=>({a:box(name).toJSON(),b:box(name+' presets').toJSON(),wrapper:n.querySelector('select[aria-label="'+name+' presets"]').parentElement.getBoundingClientRect().toJSON()})),
       direction:box('Direction').toJSON(),order:[...n.querySelectorAll('input,select')].filter(e=>e.getClientRects().length).map(e=>e.getAttribute('aria-label')),
       overflow:n.scrollWidth>n.clientWidth};
   });
   assert.equal(layout.overflow,false);
   for(const {a,b,wrapper} of layout.pairs){
     assert.ok(Math.abs(wrapper.x-b.x)<1);assert.ok(b.right<=wrapper.right+1);
     if(width<380){assert.ok(b.y>a.y);assert.equal(b.x,a.x);}
     else{assert.equal(a.y,b.y);assert.ok(b.x>=a.right+7);assert.ok(Math.abs(b.x-layout.pairs[0].b.x)<1);}
     assert.ok(Math.abs(a.width-layout.pairs[0].a.width)<1);
   }
   const sourcePort=layout.pairs[1],dest=layout.pairs[2],port=layout.pairs[3];
   if(width>=600){assert.equal(layout.direction.y,sourcePort.a.y);assert.ok(layout.direction.x-sourcePort.b.right>=15.5);assert.ok(sourcePort.b.width<dest.b.width);assert.ok(Math.abs(layout.direction.right-dest.b.right)<1);assert.ok(layout.direction.width<100);assert.ok(layout.order.indexOf('Direction')===layout.order.indexOf('Source port presets')+1);}
   else{assert.ok(layout.direction.y>port.b.y);assert.equal(layout.order.at(-1),'Direction');}
 }
 await inspector.getByLabel('Source port presets',{exact:true}).evaluate(n=>{n.querySelector('option[value="layout-test"]').remove();n.value='';});
 await inspector.evaluate(n=>n.style.removeProperty('width'));
 assert.deepEqual(await f.locator('[data-inspector]').getByLabel('Action',{exact:true}).locator('option').allTextContents(),['alert','block','drop','log','pass','react','reject','rewrite']);
 await f.locator('[data-inspector]').getByLabel('Action',{exact:true}).selectOption('drop');
 await f.locator('[data-inspector]').getByLabel('Protocol/service',{exact:true}).selectOption('ssl');await f.locator('[data-inspector]').getByLabel('Direction',{exact:true}).selectOption('<>');
 await f.locator('[data-inspector]').getByLabel('Source address presets',{exact:true}).selectOption('$HOME_NET');assert.equal(await f.locator('[data-inspector]').getByLabel('Source address',{exact:true}).inputValue(),'$HOME_NET');
 await f.locator('[data-inspector]').getByLabel('Destination address presets',{exact:true}).selectOption('$EXTERNAL_NET');await f.locator('[data-inspector]').getByLabel('Destination address',{exact:true}).fill('192.0.2.0/24');
 await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();assert.match(await source(),/^drop ssl \$HOME_NET any <> 192\.0\.2\.0\/24 80/);
 await f.locator('[data-inspector]').getByLabel('Protocol/service',{exact:true}).selectOption('__custom__');await f.locator('[data-inspector]').getByLabel('Custom Protocol/service',{exact:true}).fill('custom_service');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();assert.match(await source(),/^drop custom_service/);
 const controlsRule='alert tcp any any -> any 80 (flow:established; http_uri; content:"/path",nocase; msg:"controls"; sid:1; rev:1;)';
 await tool.evaluate((r,text)=>{const v=r.snortView;v.dispatch({changes:{from:0,to:v.state.doc.length,insert:text}});},controlsRule);
 await f.locator('[data-outline] button').filter({hasText:'Flow'}).waitFor();await f.locator('[data-outline] button').filter({hasText:'Flow'}).click();
 await f.locator('[data-inspector]').getByLabel('Add flow option',{exact:true}).selectOption('to_server');assert.equal(await f.locator('[data-inspector]').getByLabel('flow',{exact:true}).inputValue(),'established,to_server');
 assert.equal(await f.locator('[data-inspector]').getByLabel('Add flow option',{exact:true}).locator('option[value=to_client]').evaluate(o=>o.disabled),true);
 await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();assert.match(await source(),/flow:established,to_server;/);
 await f.getByRole('button',{name:'Remove flow option established',exact:true}).click();await f.locator('[data-inspector]').getByLabel('Add flow option',{exact:true}).selectOption('stateless');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();assert.match(await source(),/flow:to_server,stateless;/);
 await f.locator('[data-inspector]').getByLabel('flow',{exact:true}).fill('to_server,from_client');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();await f.locator('[data-inspector-error]').filter({hasText:'only one direction'}).waitFor();assert.match(await source(),/flow:to_server,stateless;/);
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();
 for(const label of ['Negated content','nocase','fast_pattern'])assert.ok(await f.locator('[data-inspector]').getByLabel(label,{exact:true}).evaluate(n=>{const l=n.closest('label'),s=l.querySelector('span'),a=n.getBoundingClientRect(),b=s.getBoundingClientRect();return getComputedStyle(l).display==='flex'&&Math.abs(a.y+a.height/2-b.y-b.height/2)<2;}));
 assert.equal(await f.locator('a:not(#snort-panel-docs a)').count(),0);await f.getByRole('tab',{name:'Docs',exact:true}).click();await f.locator('[data-docs-search]').fill('flow');assert.ok(await f.locator('[data-docs-list] a').count());assert.equal(await f.locator('[data-rule-editor]').isVisible(),true);
 await f.getByRole('tab',{name:'Option library',exact:true}).click();assert.equal(await f.locator('[data-library] a').count(),0);await f.getByRole('tab',{name:'Construct',exact:true}).click();
 await tool.evaluate((r,text)=>{const v=r.snortView;v.dispatch({changes:{from:0,to:v.state.doc.length,insert:text}});},defaultSource);

 const signatures=path.join(data,'cases/1/mip/signatures');fs.mkdirSync(signatures,{recursive:true});
 const first='alert tcp any any -> any 80 (msg:"first"; content:"GET"; http_method; depth:3; sid:100; rev:1;)';
 const second='alert tcp any any -> any 80 (\r\n/* comment (alert http ()); quoted \" is comment text */\r\nhttp_uri; content:"/before",depth 12; msg:"second"; sid:100; rev:2;\r\n)';
 const third='alert http (content:"third";)';
 const original='\ufeff# shared\r\n# '+first+'\n'+first+'\r\ninclude local.rules\n# adjacent\r\n'+second+' '+third+'\n# final\r\n';
 fs.writeFileSync(path.join(signatures,'multiple.rules'),original);
 fs.writeFileSync(path.join(signatures,'inspect.rules'),'ips = {\n'+first+'\n}');
 await f.locator('[data-case]').selectOption('1');await f.locator('[data-file-path="multiple.rules"]').waitFor();
 assert.deepEqual(fs.readdirSync(signatures).sort(),['inspect.rules','multiple.rules']);
 const initial=await source();await f.locator('[data-file-path="multiple.rules"]').click();await f.locator('[data-signature-dialog]').waitFor();
 assert.equal(await f.locator('[data-signature-position]').count(),3);assert.match(await f.locator('[data-signature-summary]').textContent(),/1 disabled.*1 preserved directives/);
 await f.locator('[data-signature-position="2"]').click();assert.equal(await f.locator('[data-signature-preview]').textContent(),second);
 await f.locator('[data-cancel-signature]').click();assert.equal(await source(),initial);
 await f.locator('[data-file-path="multiple.rules"]').click();await f.locator('[data-signature-search]').fill('second');assert.equal(await f.locator('[data-signature-position]').count(),1);await f.locator('[data-signature-position="2"]').click();await f.locator('[data-load-signature]').click();
 await f.locator('[data-file]').filter({hasText:'Signature 2 of 3'}).waitFor();assert.equal(await source(),second.replaceAll('\r\n','\n'));
 await f.locator('[data-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();assert.equal(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8'),original);
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();await f.locator('[data-inspector]').getByLabel('Content',{exact:true}).fill('/much-longer');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();
 await f.locator('[data-save]').click();await f.locator('[data-status]').filter({hasText:'Saved signature 2 of 3'}).waitFor();
 let edited=second.replace('content:"/before"','content:"/much-longer"');assert.equal(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8'),original.replace(second,edited));
 await f.locator('[data-outline] button').filter({hasText:'Rule identity'}).click();await f.locator('[data-inspector]').getByLabel('msg',{exact:true}).fill('edited message');await f.locator('[data-inspector]').getByLabel('sid',{exact:true}).fill('777');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();await f.locator('[data-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();
 edited=edited.replace('msg:"second"','msg:"edited message"').replace('sid:100','sid:777');assert.equal(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8'),original.replace(second,edited));
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();await f.locator('[data-inspector]').getByLabel('Content',{exact:true}).fill('/x');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();
 await f.locator('[data-change-signature]').click();await f.getByRole('button',{name:'Cancel',exact:true}).click();assert.match(await source(),/content:"\/x"/);
 await f.locator('[data-change-signature]').click();await f.getByRole('button',{name:'Save current rule',exact:true}).click();await f.locator('[data-signature-position="3"]').click();await f.locator('[data-load-signature]').click();await f.locator('[data-file]').filter({hasText:'Signature 3 of 3'}).waitFor();assert.equal(await source(),third);
 edited=edited.replace('/much-longer','/x');assert.equal(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8'),original.replace(second,edited));
 // Reopen the same complete file and select the edited rule by source order.
 await f.locator('[data-file-path="multiple.rules"]').click();await f.locator('[data-signature-search]').fill('777');await f.locator('[data-signature-position="2"]').click();await f.locator('[data-load-signature]').click();assert.equal(await source(),edited.replaceAll('\r\n','\n'));
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();await f.locator('[data-inspector]').getByLabel('Content',{exact:true}).fill('/local');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();fs.appendFileSync(path.join(signatures,'multiple.rules'),'# another session\n');
 await f.locator('[data-save]').click();await f.getByRole('button',{name:'Cancel',exact:true}).click();assert.match(await source(),/content:"\/local"/);assert.ok(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8').endsWith('# another session\n'));
 await f.locator('[data-save-as]').click();await f.locator('[data-filename]').fill('../bad.rules');await f.locator('[data-confirm-save]').click();await f.locator('[data-save-error]').filter({hasText:'relative .rules'}).waitFor();await f.locator('[data-dismiss-save]').click();assert.match(await source(),/content:"\/local"/);
 await f.locator('[data-save-as]').click();await f.locator('[data-filename]').fill('copy.rules');await f.locator('[data-confirm-save]').click();await f.locator('[data-file]').filter({hasText:'copy.rules'}).waitFor();assert.equal(fs.readFileSync(path.join(signatures,'copy.rules'),'utf8'),edited.replace('/x','/local'));assert.ok(fs.readFileSync(path.join(signatures,'multiple.rules'),'utf8').includes('/x'));
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();await f.locator('[data-inspector]').getByLabel('Content',{exact:true}).fill('/discarded');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();
 await f.locator('[data-file-path="multiple.rules"]').click();await f.getByRole('button',{name:'Discard changes',exact:true}).click();await f.locator('[data-signature-position="3"]').click();await f.locator('[data-load-signature]').click();assert.equal(await source(),third);assert.ok(!fs.readFileSync(path.join(signatures,'copy.rules'),'utf8').includes('/discarded'));
 await f.locator('[data-file-path="inspect.rules"]').click();await f.getByRole('button',{name:'Inspect whole file',exact:true}).click();assert.equal(await f.locator('[data-save]').isDisabled(),true);assert.match(await source(),/ips =/);assert.match(await f.locator('[data-parse]').textContent(),/Whole-file inspection/);
 await f.locator('[data-file-path="multiple.rules"]').click();await f.locator('[data-signature-position="2"]').click();await page.setViewportSize({width:390,height:844});
 assert.ok(await tool.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.ok(await f.locator('[data-signature-dialog]').evaluate(n=>n.scrollWidth<=n.clientWidth));await f.locator('[data-cancel-signature]').click();
 await page.setViewportSize({width:1440,height:1000});const spacing=await f.locator('.snort-toolbar').evaluate(n=>getComputedStyle(n).columnGap);assert.equal(spacing,'8px');
 const partial=first+'\n'+second+'\nalert tcp any any -> any 80 (msg:"unterminated';
 fs.writeFileSync(path.join(signatures,'partial.rules'),partial);await f.locator('[data-refresh]').click();await f.locator('[data-file-path="partial.rules"]').click();
 await f.getByRole('button',{name:'Select safe signatures',exact:true}).click();await f.locator('[data-signature-position="2"]').click();await f.locator('[data-load-signature]').click();
 await f.locator('[data-outline] button').filter({hasText:'URI match'}).click();await f.locator('[data-inspector]').getByLabel('Content',{exact:true}).fill('/partial-edited');await f.getByRole('button',{name:'Apply inspector changes',exact:true}).click();await f.locator('[data-save]').click();await f.locator('[data-dirty]').filter({hasText:'Saved / unchanged'}).waitFor();
 assert.equal(fs.readFileSync(path.join(signatures,'partial.rules'),'utf8'),partial.replace('/before','/partial-edited'));
 assert.deepEqual(errors,[]);console.log('PASS: responsive Header field/preset rows and Direction placement, multi-rule selector, second signature inspector edit/save/reopen, SID/message changes, exact surrounding bytes/BOM/comments/directives, repeated saves, save/cancel, conflicts, Save As, raw inspection and responsive spacing.');
})().catch(e=>{console.error(e);console.error(log.slice(-1500));process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();await new Promise(r=>server.once('exit',r));fs.rmSync(data,{recursive:true,force:true});});
