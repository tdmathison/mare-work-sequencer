/* Temporary research views. The graph remains the authorized source of objects. */
(() => {
 'use strict';
 const api=window.MareExplorer,$=id=>document.getElementById(id);if(!api)return;
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const controls=el('div');controls.className='explorer-research-controls';document.querySelector('.explorer-top-controls').after(controls);
 const action=(name,fn)=>{const b=el('button',name);b.type='button';b.onclick=fn;return b;};
 const focusButton=action('Focus',()=>focusSelected());$('explorer-tray').querySelector('.explorer-tray-actions').append(focusButton);
 const focusBar=el('div');focusBar.className='explorer-focus-bar';focusBar.hidden=true;controls.append(focusBar);
 let focusState=null,focusHistory=[],generation=0,focusEpoch=0;
 function primary(){return api.cy().nodes().filter(n=>n.data('kind')!=='category'&&!n.data('temporary'));}
 function notice(text){api.status(text);}
 function selected(){return api.cy()?.nodes(':selected').filter(n=>n.data('kind')!=='category');}
 function sync(){const chosen=selected();focusButton.hidden=!chosen||chosen.length!==1||chosen[0].data('temporary');}
 function applyFocus(){
  if(!focusState)return;window.MareExplorerResearch?.clearPaths?.();const cy=api.cy(),root=cy.getElementById(focusState.id);
  if(!root.length){exitFocus();notice('Focused object is no longer available.');return;}
  const keep=new Set([root.id()]),queue=[[root.id(),0]];
  for(let i=0;i<queue.length;i++){const [id,d]=queue[i];if(d>=focusState.depth)continue;cy.getElementById(id).connectedEdges().filter(e=>!e.data('categoryEdge')).forEach(e=>{const other=e.source().id()===id?e.target():e.source();if(other.data('kind')!=='category'&&!keep.has(other.id())){keep.add(other.id());queue.push([other.id(),d+1]);}});}
  cy.nodes('[kind="category"]').forEach(n=>{if(keep.has(n.data('caseNode')))keep.add(n.id());});api.visibility(keep);cy.nodes().removeClass('focus-root');root.addClass('focus-root');
  focusBar.replaceChildren(el('strong',`Focus: ${root.data('kind')==='case'?root.data('number'):root.data('name')} · Depth ${focusState.depth}`));
  focusBar.append(action('− level',()=>{focusState.depth=Math.max(1,focusState.depth-1);applyFocus();}),action('+ level',()=>{focusState.depth=Math.min(8,focusState.depth+1);applyFocus();}),action('Back',backFocus),action('Exit Focus',exitFocus));
  focusBar.querySelectorAll('button')[0].disabled=focusState.depth===1;focusBar.querySelectorAll('button')[1].disabled=focusState.depth===8;focusBar.querySelectorAll('button')[2].disabled=!focusHistory.length;
  focusBar.append(el('small','Depth follows direct entity relationships in the active filters. Filters and permissions can exclude related objects.'));
  focusBar.hidden=false;
 }
 function focusSelected(){focusEpoch++;const node=selected()?.[0];if(!node)return;if(focusState)focusHistory.push({...focusState});else focusState={base:api.snapshot()};focusState={...focusState,id:node.id(),depth:1};applyFocus();api.fit();}
 function backFocus(){if(focusHistory.length){focusState=focusHistory.pop();applyFocus();const root=api.cy().getElementById(focusState.id);if(root.length)api.select(root);api.fit();}}
 async function exitFocus(){if(!focusState)return;const version=++focusEpoch,state=focusState.base;focusState=null;focusHistory=[];focusButton.disabled=true;focusBar.replaceChildren(el('span','Restoring previous view…'));api.cy().nodes().removeClass('focus-root');try{await api.restore(state,true);if(version===focusEpoch)focusBar.hidden=true;}catch(error){if(version===focusEpoch){focusBar.replaceChildren(el('span',error.message),action('Retry restoration',()=>{focusState={base:state};exitFocus();}));notice(error.message);}}finally{focusButton.disabled=false;}}
 document.addEventListener('explorer-selection',sync);
 document.addEventListener('explorer-data',()=>{if(focusState)applyFocus();sync();});
 window.MareExplorerResearch={focus:()=>focusState?{id:focusState.id,depth:focusState.depth}:null,applyFocus,notice,controls,el,action,api,$,primary,selected,sync,setFocus(value){focusEpoch++;if(value&&!api.cy().hasElementWithId(value.id)){focusState=null;focusHistory=[];focusBar.hidden=true;notice('View partially restored: the saved focus object is unavailable.');return;}focusState=value?{...value,base:api.snapshot()}:null;focusHistory=[];focusBar.hidden=!value;if(value)applyFocus();},next:()=>++generation,current:value=>value===generation};
 sync();
})();
(() => {
 const R=window.MareExplorerResearch;if(!R)return;const {api,$,el,action,controls}=R,shell=document.querySelector('.explorer-shell');
 async function request(url,data){const options={credentials:'same-origin',cache:'no-store'};if(data){const form=new FormData();form.set('csrf',document.querySelector('input[name=csrf]').value);for(const [key,value] of Object.entries(data))form.set(key,typeof value==='string'?value:JSON.stringify(value));Object.assign(options,{method:'POST',body:form});}const response=await fetch(url,options);if(response.redirected)throw Error('Sign in again before continuing.');let result;try{result=await response.json();}catch{throw Error(`Request failed (${response.status}). Retry or narrow the search scope.`);}if(!response.ok)throw Error(result.error||'Request failed. Retry.');return result;}
 function panel(name){const node=el('section');node.className='explorer-popover explorer-research-panel';node.setAttribute('role','dialog');node.setAttribute('aria-label',name==='Find Connections'?'Connection search dialog':name);node.hidden=true;node.tabIndex=-1;const heading=el('div');heading.className='explorer-panel-heading';const closeButton=action('×',()=>close());closeButton.setAttribute('aria-label','Close '+name);heading.append(el('h2',name),closeButton);node.append(heading);shell.append(node);const toggle=action(name,()=>node.hidden?open():close());const chevron=el('span','⌄');chevron.setAttribute('aria-hidden','true');toggle.append(chevron);toggle.setAttribute('aria-expanded','false');node.id='explorer-research-'+name.toLowerCase().replaceAll(' ','-');toggle.setAttribute('aria-controls',node.id);controls.append(toggle);
  function close(){node.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus();}function open(){document.querySelectorAll('.explorer-research-panel').forEach(p=>{p.hidden=true;document.querySelector(`[aria-controls="${p.id}"]`)?.setAttribute('aria-expanded','false');});node.hidden=false;toggle.setAttribute('aria-expanded','true');node.focus();}
  node.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}});document.addEventListener('pointerdown',e=>{if(!node.hidden&&!node.contains(e.target)&&!toggle.contains(e.target)){node.hidden=true;toggle.setAttribute('aria-expanded','false');}});
  return {node,toggle,open,close};}
 function field(parent,title,input){const label=el('label',title);input.setAttribute('aria-label',title);label.append(input);parent.append(label);return input;}
 const views=panel('Saved Views'),list=field(views.node,'Saved view',el('select')),name=field(views.node,'View name',el('input')),description=field(views.node,'View description',el('textarea')),message=el('p');message.setAttribute('role','status');name.maxLength=120;description.maxLength=1000;description.rows=2;
 let active=null,stored=null,openVersion=0;
 const config=()=>({...api.snapshot(),focus:R.focus(),shared:R.shared?.()||{enabled:false,types:['md5','sha1','sha256','domain','ip','url'],minimum:1}});
 async function refresh(){const result=await request('/data-explorer/views');list.replaceChildren(el('option','Choose a saved view'));list.firstChild.value='';if(!result.views.length)list.firstChild.textContent='No saved views yet';for(const view of result.views){const option=el('option',view.name);option.value=view.id;list.append(option);}list.value=active||'';}
 async function run(fn){try{message.textContent='Working…';await fn();message.textContent='Ready';}catch(error){message.textContent=error.message;}}
 const openButton=action('Open View',()=>run(async()=>{if(!list.value)return;const version=++openVersion;const result=await request('/data-explorer/views/'+list.value);if(version!==openVersion)return;active=result.id;stored=result.configuration;name.value=result.name;description.value=result.description;R.setFocus(null);const restricted=await R.prepareShared?.(stored.shared);const missing=await api.restore(stored);if(version!==openVersion)return;await R.refreshShared?.();R.setFocus(stored.focus);if(missing||restricted){message.textContent='Some objects or settings could not be restored.';api.status('View partially restored: saved objects or settings are unavailable under the current permissions and filters.');}views.close();}));
 const save=async(asNew=false,metadataOnly=false)=>{const configuration=metadataOnly&&stored?stored:config();const result=await request(active&&!asNew?'/data-explorer/views/'+active+'/update':'/data-explorer/views',{name:name.value,description:description.value,configuration});active=result.id||active;stored=configuration;await refresh();};
 views.node.append(openButton,action('Save View',()=>run(()=>save(true))),action('Save Changes',()=>run(()=>{if(!active)throw Error('Open a saved view first.');return save();})),action('Save As',()=>run(()=>save(true))),action('Rename / Edit Description',()=>run(()=>{if(!active)throw Error('Open a saved view first.');return save(false,true);})),action('Delete View',()=>run(async()=>{if(!active)throw Error('Open a saved view first.');await request('/data-explorer/views/'+active+'/delete',{});active=null;stored=null;await refresh();})),message);
 views.toggle.addEventListener('click',()=>{if(!views.node.hidden)run(refresh);});
 Object.assign(R,{request,panel,field,config});
})();
(() => {
 const R=window.MareExplorerResearch;if(!R)return;const {api,$,el,action,request,panel,field,controls}=R;
 let evidenceVersion=0,pathVersion=0,choiceVersion=0,pathState=null,pathIndex=0,pathVisual=null,pathGraph=null;
 function params(all=false){const state=api.snapshot(),p=new URLSearchParams({q:state.query,scope:all?'all':'filtered'});(state.types.length?state.types:['none']).forEach(t=>p.append('type',t));const shared=R.shared?.();if(shared?.enabled&&shared.types.length&&Number.isInteger(shared.minimum)&&shared.minimum>=1&&shared.minimum<=100){p.set('shared','1');p.set('minimum',shared.minimum);shared.types.forEach(t=>p.append('indicator_type',t));}return p;}
 async function evidence(source,target){const version=++evidenceVersion,body=$('explorer-detail-body');api.openDetails();body.replaceChildren(el('h3','Relationship evidence'),el('p','Loading supporting records…'));
  try{const p=params(true);p.set('source',source);p.set('target',target);const result=await request('/data-explorer/evidence?'+p);if(version!==evidenceVersion)return;
   const title=el('h3',result.relationship_type),a=el('a',result.source.label),b=el('a',result.target.label);a.href=result.source.url;b.href=result.target.url;
   body.replaceChildren(title,a,el('p','connected through'),b,el('p',result.computed?'Computed relationship':'Recorded relationship'),el('p',result.reason));
   const list=el('ul');for(const item of result.evidence){const row=el('li'),link=el('a',item.label);link.href=item.url;row.append(link);list.append(row);}body.append(list);
   if(result.indicators?.length){const table=el('table');table.className='explorer-evidence-table';const head=el('tr');for(const name of ['Type','Value']){const th=el('th',name);th.scope='col';head.append(th);}const thead=el('thead');thead.append(head);const rows=el('tbody');for(const item of result.indicators){const row=el('tr');row.append(el('td',item.type),el('td',item.value));rows.append(row);}table.append(thead,rows);body.append(table);if(result.evidence_limited)body.append(el('p','Showing the first 200 shared indicators. Open the supporting Cases to inspect all saved records.'));body.append(el('p','Matching indicators show overlap and do not establish common attribution.'));}
  }catch(error){if(version===evidenceVersion)body.replaceChildren(el('h3','Relationship evidence'),el('p',error.message));}
 }
 document.addEventListener('explorer-selection',()=>{evidenceVersion++;const edge=api.cy()?.edges(':selected')[0];if(edge)evidence(edge.source().id(),edge.target().id());});
 const connections=panel('Find Connections'),source=field(connections.node,'Connection source',el('select')),target=field(connections.node,'Connection destination',el('select')),all=field(connections.node,'Search all authorized entity data',el('input'));all.type='checkbox';all.style.width='auto';const resultArea=el('div');resultArea.setAttribute('role','status');
 async function choices(){const version=++choiceVersion;const before=[source.value,target.value];let nodes;if(all.checked){const p=params(true);const data=await request('/data-explorer/connection-objects?'+p);if(version!==choiceVersion)return;nodes=data.nodes;}else nodes=R.primary().filter(n=>n.visible()).map(n=>n.data());for(const [i,select] of [source,target].entries()){select.replaceChildren(el('option','Choose an object'));select.firstChild.value='';nodes.forEach(n=>{const option=el('option',n.label);option.value=n.id;select.append(option);});select.value=before[i];}}
 function clearPaths(){pathVersion++;if(pathVisual){const cy=api.cy();if(pathGraph===cy){cy.elements().filter(n=>n.data('temporary')).remove();for(const [id,classes,display] of pathVisual){const item=cy.getElementById(id);if(item.length){item.classes(classes);item.style('display',display);}}api.decorate();pathState=null;api.syncSelection();}pathVisual=null;pathGraph=null;}pathState=null;resultArea.replaceChildren();}
 function showPath(){const cy=api.cy(),path=pathState.paths[pathIndex];if(!path)return;cy.elements().addClass('muted').removeClass('path-member');const used=new Set(path);cy.nodes().filter(n=>used.has(n.id())).removeClass('muted').addClass('path-member');
  resultArea.replaceChildren(el('p',`Connected through ${path.length-1} ${path.length===2?'relationship':'relationships'} · path ${pathIndex+1} of ${pathState.paths.length}.`));
  resultArea.append(el('p',path.map(id=>cy.getElementById(id).data('label')).join(' → ')));
  if(all.checked)resultArea.append(el('p','All authorized scope: path objects may be outside the current filters and are shown temporarily.'));
  if(pathState.limited||pathState.shared_limited)resultArea.append(el('p','Results are limited by graph, depth, time, path or shared-indicator limits.'));
  for(let i=1;i<path.length;i++){const a=path[i-1],b=path[i],edge=cy.edges().filter(e=>new Set([e.source().id(),e.target().id()]).has(a)&&new Set([e.source().id(),e.target().id()]).has(b))[0];if(edge){edge.removeClass('muted').addClass('path-member');resultArea.append(action(edge.data('explanation'),()=>evidence(a,b)));}}
  const prev=action('Previous path',()=>{pathIndex--;showPath();}),next=action('Next path',()=>{pathIndex++;showPath();});prev.disabled=pathIndex===0;next.disabled=pathIndex+1===pathState.paths.length;resultArea.append(prev,next,action('Clear Results',clearPaths));
 }
 async function find(){clearPaths();const version=++pathVersion;resultArea.textContent='Finding bounded shortest connections…';try{const p=params(all.checked);p.set('source',source.value);p.set('target',target.value);if(!all.checked)p.set('ids',JSON.stringify(R.primary().filter(n=>n.visible()).map(n=>n.id())));const result=await request('/data-explorer/connections?'+p);if(version!==pathVersion)return;pathState=result;pathIndex=0;
   if(!result.paths.length){resultArea.textContent=result.limited||result.shared_limited?'No connection found within the traversal limits.':'No connection exists in this search scope.';return;}
   const cy=api.cy();pathGraph=cy;pathVisual=cy.elements().map(n=>[n.id(),n.classes(),n.style('display')]);const center=cy.getElementById(source.value).length?cy.getElementById(source.value).position():{x:0,y:0};
   result.nodes.forEach((n,i)=>{if(!cy.hasElementWithId(n.id))cy.add({data:{...n,caption:n.kind==='case'?n.number:n.name,temporary:true},position:{x:center.x+200*Math.cos(i),y:center.y+200*Math.sin(i)}});else cy.getElementById(n.id).style('display','element');});result.edges.forEach(e=>{if(!cy.hasElementWithId(e.id))cy.add({data:{...e,temporary:true}});});api.decorate();showPath();
  }catch(error){if(version===pathVersion)resultArea.textContent=error.message;}}
 connections.node.append(action('Find Connections',find),action('Clear Results',clearPaths),resultArea);connections.toggle.addEventListener('click',()=>{if(!connections.node.hidden)choices().catch(e=>resultArea.textContent=e.message);});all.onchange=()=>choices().catch(e=>resultArea.textContent=e.message);
 const groupAction=action('Find Connections',async()=>{connections.open();await choices();const nodes=R.selected();source.value=nodes[0].id();target.value=nodes[1].id();});$('explorer-tray').querySelector('.explorer-tray-actions').append(groupAction);
 document.addEventListener('explorer-selection',()=>{groupAction.hidden=R.selected()?.length!==2;});document.addEventListener('explorer-data',()=>{clearPaths();});groupAction.hidden=true;
 Object.assign(R,{evidence,clearPaths,params});
})();
(() => {
 const R=window.MareExplorerResearch;if(!R)return;const {api,$,el,action,panel,field,request}=R;
 const sharedPanel=panel('Shared Indicators'),enabled=field(sharedPanel.node,'Enable Shared Indicators',el('input'));enabled.type='checkbox';enabled.disabled=document.querySelector('.explorer-shell').dataset.sharedAllowed!=='1';enabled.style.width='auto';const checks=[];
 for(const type of ['md5','sha1','sha256','domain','ip','url']){const check=field(sharedPanel.node,type.toUpperCase(),el('input'));check.type='checkbox';check.checked=true;check.value=type;check.style.width='auto';checks.push(check);}
 const minimum=field(sharedPanel.node,'Minimum shared indicators',el('input'));minimum.type='number';minimum.min=1;minimum.max=100;minimum.value='1';const status=el('p');status.setAttribute('role','status');sharedPanel.node.append(el('p','Dashed blue lines show computed overlap, not common attribution. Filenames and unsupported types are excluded. IP, IP-SRC and IP-DST remain distinct types.'),status);
 let version=0;
 const settings=()=>({enabled:enabled.checked,types:checks.filter(c=>c.checked).map(c=>c.value),minimum:Number(minimum.value)});
 async function refresh(){const revision=++version,cy=api.cy();if(!cy)return;R.clearPaths();const selectedComputed=cy.edges('[?computed]:selected').length;cy.edges('[?computed]').remove();if(selectedComputed)api.syncSelection();if(!enabled.checked){status.textContent=enabled.disabled?'Shared Indicators require case and indicator read permissions.':'Shared Indicators are off.';R.applyFocus();if(cy.nodes(':selected').length)api.syncSelection();return;}
  const options=settings();if(!options.types.length||!Number.isInteger(options.minimum)||options.minimum<1||options.minimum>100){status.textContent='Select at least one supported type and a minimum from 1 to 100.';return;}
  status.textContent='Computing authorized indicator overlap…';const p=R.params();
  try{const result=await request('/data-explorer/shared-indicators?'+p);if(revision!==version||cy!==api.cy())return;cy.batch(()=>result.edges.filter(e=>cy.hasElementWithId(e.source)&&cy.hasElementWithId(e.target)).forEach(e=>cy.add({data:e})));status.textContent=(result.limited?'Limited results. ':'')+(result.edges.length?result.edges.length+' computed relationships. ':result.limited?'No matches found within these limits. ':'No matching shared indicators in this view. ')+result.note;R.applyFocus();api.decorate();if(cy.nodes(':selected').length)api.syncSelection();}catch(error){if(revision===version)status.textContent=error.message;}
 }
 for(const control of [enabled,minimum,...checks])control.addEventListener('change',refresh);
 document.addEventListener('explorer-data',()=>refresh());
 R.shared=settings;R.prepareShared=async value=>{const state=value||{enabled:false,types:checks.map(c=>c.value),minimum:1};enabled.checked=state.enabled&&!enabled.disabled;if(state.enabled&&enabled.disabled)api.status('View partially restored: Shared Indicators require case and indicator read permissions.');checks.forEach(c=>c.checked=state.types.includes(c.value));minimum.value=state.minimum;return state.enabled&&enabled.disabled;};R.refreshShared=refresh;
})();
