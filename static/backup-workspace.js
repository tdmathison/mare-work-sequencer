(() => {
  'use strict';
  const host=document.getElementById('backup-workspace');if(!host)return;
  const $=id=>document.getElementById(id),root=host.dataset.jobs.replace('/JOB',''),csrf=host.dataset.csrf;
  const selected=[...document.querySelectorAll('#backup-export [name=areas]:enabled')];
  const complete=$('complete-backup');let stopped=false,timer,preview=null,choices={},importId=null,exportId=null,busy=false,resultVersion=null;
  const storageKey='mare-backup-workspace:'+host.dataset.owner;
  function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
  function remember(){try{sessionStorage.setItem(storageKey,JSON.stringify({importId,exportId,tab:document.querySelector('[data-tab][aria-selected="true"]')?.dataset.tab}));}catch(e){}}
  function selection(){
    const chosen=selected.filter(c=>c.checked),deps=[...new Set(chosen.flatMap(c=>c.dataset.dependencies.split(',').filter(Boolean)))].filter(d=>!chosen.some(c=>c.value===d));
    $('selection-summary').textContent=complete.checked?'Complete recovery: all implemented areas plus accounts, credentials, settings, audit, keys and stored files.':chosen.length?'Selective transfer: '+chosen.map(c=>c.getAttribute('aria-label')).join(', ')+(deps.length?'. Automatically includes required '+deps.join(', ')+' identities and relationship mappings.':'. Selecting all rows still excludes system-level data.'):'Choose at least one data area.';
    $('export-action').disabled=!chosen.length||busy;for(const control of $('backup-inspect').querySelectorAll('input,button'))control.disabled=busy;$('inspect-action').disabled=busy;$('backup-export').elements.passphrase.required=complete.checked;
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
  function allowImport(){$('confirm-import').disabled=busy;$('ack-replace').disabled=busy;const blocking=!preview||preview.blocking.length||preview.conflicts.length||busy||!$('confirm-import').checked||preview.complete&&!$('ack-replace').checked;$('import-action').disabled=!!blocking;}
  $('ack-replace').onchange=allowImport;$('confirm-import').onchange=allowImport;
  const importView=window.MWSBackupImport.create({onChoice(key,value){if(value===undefined)return choices[key]||'';choices[key]=value;preview=null;allowImport();},onRefresh:refreshPreview});
  function details(label,items){const d=node('details'),s=node('summary',label),list=node('ul');for(const item of items){list.append(node('li',typeof item==='string'?item:Object.entries(item).map(([key,value])=>key.replaceAll('_',' ')+': '+value).join(' · ')));}d.append(s,list);return d;}
  function renderPreview(p){preview=p;importView.renderPreview(p);allowImport();}
  async function refreshPreview(){if(!importId||busy)return;preview=null;resultVersion=null;busy=true;allowImport();try{await request(root+'/'+importId+'/preview',form({choices:JSON.stringify(choices),passphrase:$('backup-inspect').elements.passphrase.value}));poll();}catch(e){busy=false;error(e.message);}}
  async function poll(){
    clearTimeout(timer);if(stopped)return;
    try{
      let active=false;
      for(const [kind,id] of [['export',exportId],['import',importId]]){
        if(!id)continue;const data=await request(root+'/'+id);if(kind==='import'&&id!==importId)continue;const status=$(kind+'-status');status.hidden=false;status.textContent=data.state+' · '+data.phase;
        if(data.state==='queued'||data.state==='running'){active=true;if(kind==='import'&&data.execution_started_at&&importView.step!==4)importView.executing();continue;}
        if(data.state==='failed'){error(data.error||'Some items failed. Review the result.');}
        if(kind==='export'&&data.state==='completed'){
          const box=$('export-result');box.hidden=false;box.replaceChildren(node('p',(data.complete?'Complete':'Selective')+' archive · '+data.archive_name+' · '+data.archive_size.toLocaleString()+' bytes'));
          const link=node('a','Download archive');link.href=root+'/'+id+'/download';box.append(link,details('Counts and coverage',[data.manifest.counts,...data.manifest.exclusions]));
        }
        if(kind==='import'&&data.state==='preview'&&data.preview&&!busyPreviewEqual(data.preview)){renderPreview(data.preview);}
        if(kind==='import'&&(data.result||data.state==='failed')&&resultVersion!==id+data.updated_at){resultVersion=id+data.updated_at;importView.renderResults(data);}
      }
      busy=active;selection();allowImport();if(active)timer=setTimeout(poll,1000);
    }catch(e){busy=false;error(e.message);selection();allowImport();}
  }
  function busyPreviewEqual(p){return preview&&preview.archive_hash===p.archive_hash&&preview.destination===p.destination&&JSON.stringify(preview.conflicts)===JSON.stringify(p.conflicts);}
  $('backup-export').onsubmit=async event=>{event.preventDefault();if(busy)return;$('export-result').hidden=true;busy=true;selection();try{const result=await request(host.dataset.create,new FormData(event.target));exportId=result.id;remember();poll();}catch(e){busy=false;error(e.message);selection();}};
  $('backup-inspect').onsubmit=async event=>{event.preventDefault();if(busy)return;preview=null;choices={};$('import-result').hidden=true;resultVersion=null;importView.reset();allowImport();$('import-error').hidden=true;busy=true;try{const result=await request(host.dataset.create,new FormData(event.target));importId=result.id;remember();poll();}catch(e){busy=false;error(e.message);}};
  $('backup-inspect').elements.archive.onchange=()=>{if(busy)return;importView.reset();resultVersion=null;const file=$('backup-inspect').elements.archive.files[0];$('archive-selected').textContent=file?file.name+' · '+file.size.toLocaleString()+' bytes':'No archive selected.';importId=null;remember();preview=null;allowImport();$('import-preview').hidden=true;$('backup-import').hidden=true;if($('backup-inspect').elements.archive.files.length)$('backup-inspect').requestSubmit();};
  $('backup-inspect').elements.passphrase.oninput=()=>{if(busy)return;importView.reset();resultVersion=null;importId=null;remember();preview=null;allowImport();};
  $('backup-import').onsubmit=async event=>{event.preventDefault();if($('import-action').disabled)return;busy=true;allowImport();importView.executing();try{await request(root+'/'+importId+'/apply',form({ack:$('ack-replace').checked?'REPLACE':''}));poll();}catch(e){busy=false;error(e.message);importView.renderResults({state:'failed',error:e.message,preview});allowImport();}};
  const drop=$('archive-drop');for(const event of ['dragover','drop'])drop.addEventListener(event,e=>{e.preventDefault();if(busy)return;if(event==='drop'&&e.dataTransfer.files.length){$('backup-inspect').elements.archive.files=e.dataTransfer.files;$('backup-inspect').elements.archive.dispatchEvent(new Event('change'));}});
  try{const state=JSON.parse(sessionStorage.getItem(storageKey)||'{}');importId=state.importId||host.dataset.resumeImport;exportId=state.exportId;if(state.tab)document.querySelector('[data-tab="'+state.tab+'"]')?.click();if(importId||exportId)poll();}catch(e){}
  window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);});
})();
