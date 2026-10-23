(() => {
  'use strict';
  const host=document.getElementById('backup-workspace');if(!host)return;
  const $=id=>document.getElementById(id),root=host.dataset.jobs.replace('/JOB',''),csrf=host.dataset.csrf;
  const selected=[...document.querySelectorAll('#backup-export [name=areas]:enabled')];
  const complete=$('complete-backup');let stopped=false,timer,preview=null,choices={},importId=null,exportId=null,busy=false;
  const storageKey='mare-backup-workspace:'+host.dataset.owner;
  function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
  function remember(){try{sessionStorage.setItem(storageKey,JSON.stringify({importId,exportId,tab:document.querySelector('[data-tab][aria-selected="true"]')?.dataset.tab}));}catch(e){}}
  function selection(){
    const chosen=selected.filter(c=>c.checked),deps=[...new Set(chosen.flatMap(c=>c.dataset.dependencies.split(',').filter(Boolean)))].filter(d=>!chosen.some(c=>c.value===d));
    $('selection-summary').textContent=complete.checked?'Complete recovery: all implemented areas plus accounts, credentials, settings, audit, keys and stored files.':chosen.length?'Selective transfer: '+chosen.map(c=>c.getAttribute('aria-label')).join(', ')+(deps.length?'. Automatically includes required '+deps.join(', ')+' identities and relationship mappings.':'. Selecting all rows still excludes system-level data.'):'Choose at least one data area.';
    $('export-action').disabled=!chosen.length||busy;$('backup-export').elements.passphrase.required=complete.checked;
  }
  complete.onchange=()=>{if(complete.checked)selected.forEach(c=>c.checked=true);selection();};
  selected.forEach(c=>c.onchange=()=>{if(!c.checked)complete.checked=false;selection();});selection();
  for(const tab of document.querySelectorAll('[data-tab]'))tab.onclick=()=>{
    for(const item of document.querySelectorAll('[data-tab]')){const current=item===tab;item.setAttribute('aria-selected',String(current));item.tabIndex=current?0:-1;$(item.dataset.tab+'-panel').hidden=!current;}remember();
  };
  document.querySelector('.backup-tabs').onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const tabs=[...document.querySelectorAll('[data-tab]')];const next=event.key==='Home'?tabs[0]:event.key==='End'?tabs[1]:tabs.find(t=>t.getAttribute('aria-selected')!=='true');next.click();next.focus();}};
  async function request(url,data){
    const options=data?{method:'POST',body:data}:{};const r=await fetch(url,{...options,cache:'no-store'});
    if(r.redirected&&new URL(r.url).pathname.endsWith('/login'))throw Error('Your session ended. For complete replacement, sign in using a restored administrator account.');
    const value=await r.json();if(!r.ok)throw Error(value.error||'Request failed. Refresh and retry.');return value;
  }
  function form(data={}){const f=new FormData();f.set('csrf',csrf);for(const [k,v] of Object.entries(data))f.set(k,v);return f;}
  function error(message){$('import-error').hidden=false;$('import-error').textContent=message;}
  function allowImport(){const blocking=!preview||preview.blocking.length||preview.conflicts.length||busy||preview.complete&&!$('ack-replace').checked;$('import-action').disabled=!!blocking;}
  $('ack-replace').onchange=allowImport;
  function details(label,items){const d=node('details'),s=node('summary',label),list=node('ul');for(const item of items){list.append(node('li',typeof item==='string'?item:JSON.stringify(item)));}d.append(s,list);return d;}
  function renderPreview(p){
    preview=p;$('import-preview').hidden=false;$('import-preview').replaceChildren();$('backup-import').hidden=false;$('replacement-ack').hidden=!p.complete;$('ack-replace').checked=false;
    const dl=node('dl');dl.className='backup-summary';
    for(const [label,value] of [['Archive',p.filename],['Created',p.created],['Format / application',p.format+' / '+p.application_version],['Scope / mode',(p.complete?'Complete application backup':'Selective / legacy transfer')+' / '+p.mode],['Included areas',p.areas.join(', ')],['Dependencies',p.dependencies.join(', ')||'None'],['Records',Object.entries(p.counts).filter(([k])=>['cases','malware_families','tags','family_reports','users'].includes(k)).map(([k,n])=>k+': '+n).join(' · ')],['Stored files',p.file_count]]){const row=node('div');row.append(node('dt',label),node('dd',String(value)));dl.append(row);}
    $('import-preview').append(node('h3','Reviewed import plan'),dl);
    if(p.complete)$('import-preview').append(node('p','Replace every application record and durable file with this snapshot. User identities and relationships are restored together.'),details('All restored record counts',[p.counts]));
    if(p.complete&&p.handoff)$('import-preview').append(node('p','Replacement ends all current sessions. Completion results will be available to restored administrator '+p.handoff.username+'.'));
    for(const message of [...p.blocking,...p.warnings])$('import-preview').append(node('p',message));
    for(const conflict of p.conflicts){const block=node('div');block.className='backup-conflict';block.append(node('p',conflict.label));if(conflict.options.length){const select=node('select');select.setAttribute('aria-label',conflict.label);select.append(new Option('Choose a resolution',''));for(const [value,label] of conflict.options)select.append(new Option(label,value));select.value=choices[conflict.key]||'';select.onchange=()=>{choices[conflict.key]=select.value;preview=null;allowImport();};block.append(select);}else block.append(node('p','Resolve this identity conflict in the application, then refresh the preview.'));$('import-preview').append(block);}
    if(p.conflicts.length){const refresh=node('button','Generate new preview');refresh.type='button';refresh.onclick=refreshPreview;$('import-preview').append(refresh);}
    $('import-preview').append(details('Shared additions and skips',[p.shared_actions]),details('User/tag mapping outcomes',p.mapping),details('Planned case additions, updates, skips and replacements',p.cases));allowImport();
  }
  async function refreshPreview(){if(!importId||busy)return;preview=null;allowImport();busy=true;try{await request(root+'/'+importId+'/preview',form({choices:JSON.stringify(choices),passphrase:$('backup-inspect').elements.passphrase.value}));poll();}catch(e){busy=false;error(e.message);}}
  async function poll(){
    clearTimeout(timer);if(stopped)return;
    try{
      let active=false;
      for(const [kind,id] of [['export',exportId],['import',importId]]){
        if(!id)continue;const data=await request(root+'/'+id);if(kind==='import'&&id!==importId)continue;const status=$(kind+'-status');status.hidden=false;status.textContent=data.state+' · '+data.phase;
        if(data.state==='queued'||data.state==='running'){active=true;continue;}
        if(data.state==='failed'){error(data.error||'Some items failed. Review the result.');}
        if(kind==='export'&&data.state==='completed'){
          const box=$('export-result');box.hidden=false;box.replaceChildren(node('p',(data.complete?'Complete':'Selective')+' archive · '+data.archive_size.toLocaleString()+' bytes'));
          const link=node('a','Download archive');link.href=root+'/'+id+'/download';box.append(link,details('Counts and coverage',[data.manifest.counts,...data.manifest.exclusions]));
        }
        if(kind==='import'&&data.state==='preview'&&data.preview&&!busyPreviewEqual(data.preview)){renderPreview(data.preview);}
        if(kind==='import'&&data.result){$('import-result').hidden=false;$('import-result').replaceChildren(node('p',data.result.message),details('Import results',[data.result]));$('backup-import').hidden=true;}
      }
      busy=active;selection();allowImport();if(active)timer=setTimeout(poll,1000);
    }catch(e){busy=false;error(e.message);selection();allowImport();}
  }
  function busyPreviewEqual(p){return preview&&preview.archive_hash===p.archive_hash&&preview.destination===p.destination&&JSON.stringify(preview.conflicts)===JSON.stringify(p.conflicts);}
  $('backup-export').onsubmit=async event=>{event.preventDefault();if(busy)return;$('export-result').hidden=true;busy=true;selection();try{const result=await request(host.dataset.create,new FormData(event.target));exportId=result.id;remember();poll();}catch(e){busy=false;error(e.message);selection();}};
  $('backup-inspect').onsubmit=async event=>{event.preventDefault();if(busy)return;preview=null;choices={};$('import-result').hidden=true;allowImport();$('import-error').hidden=true;busy=true;try{const result=await request(host.dataset.create,new FormData(event.target));importId=result.id;remember();poll();}catch(e){busy=false;error(e.message);}};
  $('backup-inspect').elements.archive.onchange=()=>{importId=null;remember();preview=null;allowImport();$('import-preview').hidden=true;$('backup-import').hidden=true;if($('backup-inspect').elements.archive.files.length)$('backup-inspect').requestSubmit();};
  $('backup-inspect').elements.passphrase.oninput=()=>{importId=null;remember();preview=null;allowImport();};
  $('backup-import').onsubmit=async event=>{event.preventDefault();if($('import-action').disabled)return;busy=true;allowImport();try{await request(root+'/'+importId+'/apply',form({ack:$('ack-replace').checked?'REPLACE':''}));poll();}catch(e){busy=false;error(e.message);allowImport();}};
  try{const state=JSON.parse(sessionStorage.getItem(storageKey)||'{}');importId=state.importId||host.dataset.resumeImport;exportId=state.exportId;if(state.tab)document.querySelector('[data-tab="'+state.tab+'"]')?.click();if(importId||exportId)poll();}catch(e){}
  window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);});
})();
