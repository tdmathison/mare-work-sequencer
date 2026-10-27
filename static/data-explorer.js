/* Focus Canvas. Cytoscape owns gestures; overlays never resize the canvas. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),shell=document.querySelector('.explorer-shell');if(!shell)return;
 const paths={case:'M6 2h8l4 4v16H6z M14 2v6h6 M9 12h6 M9 16h6',family:'M8 8h8v10H8z M10 8V5h4v3 M4 10h4 M16 10h4 M4 15h4 M16 15h4 M7 20l3-2 M17 20l-3-2',actor:'M12 2l8 3v6c0 5-8 11-8 11S4 16 4 11V5z M9 9a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M7 17c1-4 9-4 10 0',indicators:'M3 12h18 M12 3v18 M6 6l12 12 M18 6L6 18',references:'M9 8l3-3a4 4 0 0 1 6 6l-3 3 M15 16l-3 3a4 4 0 0 1-6-6l3-3 M8 16l8-8',reports:'M5 2h10l4 4v16H5z M8 10h8 M8 14h8 M8 18h5',files:'M2 6h8l2 2h10v13H2z',images:'M3 3h18v18H3z M5 18l5-7 4 5 3-3 3 5 M17 8h.1'};
 const svg=(kind,color)=>`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"><path d="${paths[kind]||paths.files}"/></svg>`;

 const element=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
 function putIcon(el,kind){el.replaceChildren();const doc=new DOMParser().parseFromString(svg(kind,'currentColor'),'image/svg+xml');el.append(document.importNode(doc.documentElement,true));}
 document.querySelectorAll('[data-icon]').forEach(el=>putIcon(el,el.dataset.icon));
 function button(text,action){const el=element('button',text);el.type='button';el.addEventListener('click',action);return el;}
 function link(text,href){const el=element('a',text);el.href=href;return el;}
 let cy,layout,graphRequest,detailRequest,serial=0,detailSerial=0,disposed=false,selectedId=null,originalViewport;
 let marqueeStart=null,marqueeSeed=[],gestureActive=false,gestureCanceled=false,gestureClient={x:0,y:0},followers=[],dragAnchor=null;
 let marqueeActive=false,marqueeEnd=null,marqueeFrame=null,feedbackPending=false;
 let feedbackNodes=new Set();
 const marquee=element('div',undefined,'explorer-marquee');marquee.hidden=true;marquee.setAttribute('aria-hidden','true');shell.append(marquee);
 const relationshipGroupsOpen=new Map();
 const requests=new Map(),positions=new Map(),expanded=new Set(),summaries=new Map(),summaryTasks=new Map();
 const status=(text,error=false)=>{$('explorer-status').textContent=text;$('explorer-status').classList.toggle('error',error);};
 const contentURL=id=>shell.dataset.caseTemplate.replace('/0/','/'+id+'/');
 const showContents=()=>$('explorer-show-contents').checked;
 async function json(url,signal){const res=await fetch(url,{signal,credentials:'same-origin',cache:'no-store'});if(res.redirected)throw Error('Your session requires sign-in or an account update. Open Settings or sign in again.');if(!res.ok){let message=`Unable to load data (${res.status}). Retry or open the case workspace.`;try{message=(await res.json()).error||message;}catch{}throw Error(message);}return res.json();}
 function icons(){const color=getComputedStyle(shell).getPropertyValue('--text').trim();cy.nodes().forEach(n=>n.style('background-image','data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg(n.data('category')||n.data('kind'),color))));}
 function objects(){const list=$('explorer-objects');list.replaceChildren();cy.nodes(':visible').forEach(n=>{const option=element('option',n.data('kind')==='category'?`${n.data('parentLabel')} · ${n.data('label')} (${n.data('count')})`:n.data('label'));option.value=n.id();list.append(option);});list.value=selectedId||'';}
 function primaryEdges(node){return node.connectedEdges().filter(e=>!e.data('categoryEdge'));}
 function savePositions(){if(cy&&!cy.destroyed())cy.nodes().forEach(n=>positions.set(n.id(),{...n.position()}));}
 function filterBadge(){const disabledTypes=[...document.querySelectorAll('[name=explorer-type]:not(:disabled)')].filter(el=>!el.checked).length;const count=disabledTypes+(!$('explorer-show-contents').disabled&&!showContents()?1:0);$('explorer-filter-count').textContent=count;$('explorer-filters-toggle').setAttribute('aria-label',`Filters, ${count} active`);}
 function viewCounts(){for(const kind of ['case','family','actor'])$('explorer-count-'+kind).textContent=cy.nodes().filter(n=>n.data('kind')===kind).length;}
 function safeRect(){
  const bounds=shell.getBoundingClientRect(),top=document.querySelector('.explorer-top-controls').getBoundingClientRect();
  let left=36,right=cy.width()-36,bottom=cy.height()-72,upper=top.bottom-bounds.top+25;
  if(!$('explorer-tray').hidden)bottom=Math.min(bottom,$('explorer-tray').getBoundingClientRect().top-bounds.top-24);
  if(!$('explorer-details').hidden)right=Math.min(right,$('explorer-details').getBoundingClientRect().left-bounds.left-24);
  // On a short/mobile viewport the drawer may cover the graph; fit its normal
  // canvas instead of dividing by a negative usable area.
  if(right-left<150){right=cy.width()-30;left=30;}
  if(bottom-upper<120)bottom=cy.height()-45;
  return {left,right,top:upper,bottom};
 }
 function fitView(){
  if(!cy||!cy.nodes(':visible').length)return;
  const rect=safeRect();
  for(let pass=0;pass<2;pass++){const box=cy.elements(':visible').boundingBox();const level=Math.max(.005,Math.min(2,(rect.right-rect.left)/Math.max(1,box.w),(rect.bottom-rect.top)/Math.max(1,box.h)));cy.minZoom(Math.min(.15,level));cy.viewport({zoom:level,pan:{x:rect.left+(rect.right-rect.left-box.w*level)/2-box.x1*level,y:rect.top+(rect.bottom-rect.top-box.h*level)/2-box.y1*level}});}
 }
 let layoutVersion=0;
 const layoutDefaults={mode:'clusters',direction:'tb',center:'selected',spacing:'balanced',emphasis:true};
 let layoutPreferences={...layoutDefaults};
 try{const saved=JSON.parse(localStorage.getItem('mare-explorer-layout')||'null');if(saved)for(const key of Object.keys(layoutDefaults))if(typeof saved[key]===typeof layoutDefaults[key])layoutPreferences[key]=saved[key];}catch{}
 for(const [key,values] of Object.entries({mode:['clusters','tree','radial'],direction:['tb','lr'],center:['selected','automatic'],spacing:['compact','balanced','spacious']}))if(!values.includes(layoutPreferences[key]))layoutPreferences[key]=layoutDefaults[key];
 function layoutControls(){
  $('explorer-layout').value=layoutPreferences.mode;
  for(const key of ['direction','center','spacing'])$('explorer-layout-'+key).value=layoutPreferences[key];
  $('explorer-layout-emphasis').checked=layoutPreferences.emphasis;
  document.querySelectorAll('[data-layout-setting]').forEach(el=>el.hidden=el.dataset.layoutSetting!==layoutPreferences.mode);
  $('explorer-spacing-label').textContent=layoutPreferences.mode==='radial'?'Ring spacing':'Spacing';
 }
 function connectionEmphasis(){
  if(!cy)return;
  const enabled=layoutPreferences.mode==='clusters'&&layoutPreferences.emphasis;
  cy.batch(()=>cy.nodes().filter(n=>n.data('kind')!=='category').forEach(n=>{
   const degree=new Set(primaryEdges(n).filter(e=>e.visible()).map(e=>e.source().id()===n.id()?e.target().id():e.source().id())).size;
   const boost=enabled?Math.min(12,Math.log2(degree+1)*4):0,base=n.data('kind')==='case'?70:58;
   n.style({width:base+boost,height:(n.data('kind')==='case'?80:58)+boost});
  }));
 }
 function cancelArrangement(){if(layout){layout.terminate();layout=null;layoutVersion++;status('Arrangement canceled. Auto Arrange to apply the current settings.');}}
 function arrange(){
  if(!cy)return;layout?.terminate();const version=++layoutVersion;
  connectionEmphasis();
  if(!cy.nodes(':visible').length){status('No displayed objects to arrange.');return;}
  const graph=cy,revision=serial;
  status('Arranging '+$('explorer-layout').selectedOptions[0].textContent+'…');
  layout=new Worker(shell.dataset.layoutWorker);
  layout.onmessage=event=>{
   if(disposed||version!==layoutVersion||revision!==serial||graph!==cy)return;
   layout.terminate();layout=null;
   if(event.data.error){status('Unable to arrange: '+event.data.error,true);return;}
   cy.batch(()=>{for(const [id,position] of Object.entries(event.data.positions)){const node=cy.getElementById(id);if(node.length)node.position(position);}});
   fitView();savePositions();originalViewport={zoom:cy.zoom(),pan:{...cy.pan()}};
   status('Layout settled. Objects stay in place until you drag them or Auto Arrange.');
  };
  layout.onerror=()=>{if(version===layoutVersion){layout?.terminate();layout=null;status('Unable to arrange this view. Retry Auto Arrange.',true);}};
  layout.postMessage({mode:layoutPreferences.mode,settings:layoutPreferences,center:selectedId,nodes:cy.nodes(':visible').map(n=>({id:n.id(),kind:n.data('kind'),caseNode:n.data('caseNode')})),edges:cy.edges(':visible').map(e=>({source:e.source().id(),target:e.target().id()}))});
 }
 function layoutChanged(){
  layoutPreferences={mode:$('explorer-layout').value,direction:$('explorer-layout-direction').value,center:$('explorer-layout-center').value,spacing:$('explorer-layout-spacing').value,emphasis:$('explorer-layout-emphasis').checked};
  try{localStorage.setItem('mare-explorer-layout',JSON.stringify(layoutPreferences));}catch{}
  layoutControls();arrange();
 }
 layoutControls();
 for(const id of ['explorer-layout','explorer-layout-direction','explorer-layout-center','explorer-layout-spacing','explorer-layout-emphasis'])$(id).addEventListener('change',layoutChanged);

 function closePanel(name,restore=false){const panel=$('explorer-'+name);if(panel.hidden)return;panel.hidden=true;const toggle=$('explorer-'+(name==='layout-settings'?'layout':name)+'-toggle');toggle.setAttribute('aria-expanded','false');if(restore)toggle.focus();}
 function openPanel(name){$('explorer-tooltip').hidden=true;for(const other of ['filters','help','layout-settings'])if(other!==name)closePanel(other);$('explorer-'+name).hidden=false;$(name==='layout-settings'?'explorer-layout-toggle':'explorer-'+name+'-toggle').setAttribute('aria-expanded','true');const target=$('explorer-'+name).querySelector(name==='details'?'button':'input:not(:disabled),button');target?.focus();}
 function deselect(){hideMarquee();relationshipGroupsOpen.clear();detailRequest?.abort();detailSerial++;selectedId=null;cy?.elements().unselect().removeClass('muted related');$('explorer-tray').hidden=true;closePanel('details');$('explorer-objects').value='';$('explorer-tooltip').hidden=true;}
 function init(data){
  const retainedSelection=cy&&!cy.destroyed()?cy.nodes(':selected:visible').map(n=>n.id()):[];
  const viewport=cy&&!cy.destroyed()?{zoom:cy.zoom(),pan:{...cy.pan()}}:null;
  savePositions();layout?.terminate();layout=null;layoutVersion++;cy?.destroy();requests.forEach(r=>r.abort());requests.clear();summaryTasks.clear();summaries.clear();expanded.clear();relationshipGroupsOpen.clear();detailRequest?.abort();detailSerial++;selectedId=null;$('explorer-tray').hidden=true;closePanel('details');
  const style=getComputedStyle(shell),token=name=>style.getPropertyValue(name).trim();
  const known=data.nodes.some(n=>positions.has(n.id));
  const elements=[...data.nodes.map((n,i)=>({data:{...n,caption:n.kind==='case'?n.number+'\n'+n.status:n.name},position:positions.get(n.id)||{x:(i%8)*190,y:Math.floor(i/8)*160}})),...data.edges.map(e=>({data:e}))];
  hideMarquee();feedbackNodes.clear();followers=[];marqueeStart=null;gestureActive=false;
  cy=cytoscape({container:$('explorer-canvas'),elements,layout:{name:'preset',fit:false},minZoom:.15,maxZoom:3,boxSelectionEnabled:true,selectionType:'single',desktopTapThreshold:5,touchTapThreshold:8,style:[
   {selector:'core',style:{'selection-box-color':token('--explorer-blue'),'selection-box-opacity':0,'selection-box-border-color':token('--explorer-blue'),'selection-box-border-width':0}},
   {selector:'node',style:{'background-color':token('--panel-2'),'border-color':token('--accent'),'border-width':2,width:58,height:58,label:'data(caption)',color:token('--text'),'font-family':'Inter, sans-serif','font-size':13,'text-valign':'bottom','text-margin-y':10,'text-wrap':'wrap','text-max-width':190,'background-width':28,'background-height':28}},
   {selector:'node[kind="case"]',style:{shape:'round-rectangle',width:70,height:80,'text-max-width':230,'background-width':36,'background-height':36,'border-color':token('--explorer-blue'),'border-width':2.8,'underlay-color':token('--explorer-blue'),'underlay-opacity':.12,'underlay-padding':7,'underlay-shape':'round-rectangle'}},
   {selector:'node[kind="family"]',style:{shape:'hexagon','text-wrap':'ellipsis','text-max-width':160}},
   {selector:'node[kind="actor"]',style:{shape:'pentagon','border-color':token('--muted'),'text-wrap':'ellipsis','text-max-width':160}},
   {selector:'node[kind="category"]',style:{shape:'ellipse',width:48,height:48,label:'data(count)','font-size':12,'text-valign':'center','text-margin-y':12,'background-position-y':'20%','background-width':19,'background-height':19,'border-width':1}},
   {selector:'edge',style:{width:2.4,opacity:.85,'line-color':token('--explorer-edge'),'curve-style':'bezier'}},
   {selector:'node.muted',style:{opacity:.7}},{selector:'edge.muted',style:{opacity:.58}},
   {selector:'.related',style:{'line-color':token('--accent'),'border-width':3}},{selector:'edge.related',style:{width:3.2,opacity:1}},
   {selector:':selected',style:{'border-color':token('--accent'),'border-width':4,'line-color':token('--accent')}},
   {selector:'node[kind="case"].case-hover',style:{'underlay-opacity':.19,'underlay-padding':9}},
   {selector:'node:selected, node.marquee-preview',style:{'border-color':token('--explorer-blue'),'border-width':3,'underlay-color':token('--explorer-blue'),'underlay-opacity':.5,'underlay-padding':9,opacity:1}},
   {selector:'node[kind="category"]:selected, node[kind="category"].marquee-preview',style:{'underlay-shape':'ellipse'}}
  ]});
  cy.on('zoom',()=>{const size=Math.min(30,Math.max(13,12/cy.zoom()));cy.batch(()=>{cy.nodes().style('font-size',size);cy.nodes('[kind="category"]').style('font-size',Math.min(24,size));cy.nodes('[kind="case"]').forEach((n,i)=>{const compact=cy.width()<650||cy.zoom()<.6;n.data('caption',n.data('number')+(compact?'':'\n'+n.data('status')));n.style({'text-max-width':Math.max(230,190/cy.zoom()),'text-valign':cy.width()<650&&i%2?'top':'bottom','text-margin-y':cy.width()<650&&i%2?-12:12});});});selectionFeedback();if(marqueeActive)drawMarquee();$('explorer-tooltip').hidden=true;});
  cy.on('select unselect','node',scheduleSelectionFeedback);
  icons();objects();connectionEmphasis();viewCounts();$('explorer-tally').textContent=`${data.total} objects · ${data.edges.length} relationships`;
  cy.on('tap','node,edge',event=>{
   if(event.originalEvent?.ctrlKey||event.originalEvent?.metaKey||event.originalEvent?.shiftKey){queueMicrotask(syncSelection);return;}
   select(event.target);
  });
  cy.on('tap',event=>{if(event.target===cy&&!event.originalEvent?.ctrlKey&&!event.originalEvent?.metaKey&&!event.originalEvent?.shiftKey)deselect();});
  cy.on('mousedown',event=>{
   if(event.originalEvent?.button!==0)return;
   cancelArrangement();hideMarquee();
   gestureActive=true;gestureCanceled=false;gestureClient={x:event.originalEvent.clientX,y:event.originalEvent.clientY};
   marqueeStart={...event.position};marqueeSeed=cy.nodes(':selected:visible').map(n=>n.id());
  });
  cy.on('boxstart',event=>{marqueeActive=true;marqueeEnd={...event.position};drawMarquee();});
  cy.on('mousemove',event=>{if(marqueeActive){marqueeEnd={...event.position};if(marqueeFrame===null)marqueeFrame=requestAnimationFrame(()=>{marqueeFrame=null;drawMarquee();});}});
  cy.on('boxend',event=>{
   const graph=cy,start=marqueeStart,end=event.position,seed=marqueeSeed.slice(),canceled=gestureCanceled;
   hideMarquee();
   queueMicrotask(()=>{
    if(graph!==cy||!start)return;
    const ids=new Set(seed);
    if(!canceled)cy.nodes(':visible').forEach(n=>{const p=n.position();if(p.x>=Math.min(start.x,end.x)&&p.x<=Math.max(start.x,end.x)&&p.y>=Math.min(start.y,end.y)&&p.y<=Math.max(start.y,end.y))ids.add(n.id());});
    cy.elements().unselect();cy.nodes(':visible').filter(n=>ids.has(n.id())).select();syncSelection();
   });
  });
  cy.on('grabon','node',event=>{
   cancelArrangement();followers=[];dragAnchor=event.target;
   const moving=event.target.selected()?cy.nodes(':selected'):event.target;
   for(const parent of moving.filter(n=>n.data('kind')==='case'))for(const child of cy.nodes().filter(n=>n.data('caseNode')===parent.id()&&!moving.contains(n)))followers.push({parent,child,parentStart:{...parent.position()},childStart:{...child.position()}});
  });
  cy.on('grab','node',cancelArrangement);
  cy.on('drag','node',event=>{if(event.target!==dragAnchor)return;cy.batch(()=>followers.forEach(({parent,child,parentStart,childStart})=>{if(!child.removed())child.position({x:childStart.x+parent.position('x')-parentStart.x,y:childStart.y+parent.position('y')-parentStart.y});}));});
  cy.on('freeon','node',()=>{followers=[];dragAnchor=null;savePositions();});cy.on('dragfree','node',savePositions);
  cy.on('remove','node',()=>{const graph=cy;queueMicrotask(()=>{if(cy===graph&&!cy.destroyed())syncSelection();});});
  cy.on('mouseover','node,edge',event=>{const item=event.target;if(item.isNode()&&item.data('kind')==='case')item.addClass('case-hover');const tip=$('explorer-tooltip');tip.textContent=item.isEdge()?item.data('explanation'):item.data('kind')==='category'?`${item.data('label')}: ${item.data('count')} · ${item.data('parentLabel')}`:item.data('label')+(item.data('tag')?' · '+item.data('tag'):'');const p=event.renderedPosition||item.renderedPosition();tip.style.left=Math.max(12,Math.min(p.x+18,cy.width()-270))+'px';tip.style.top=Math.max(12,Math.min(p.y+18,cy.height()-90))+'px';tip.hidden=false;});cy.on('mouseout','node,edge',event=>{event.target.removeClass('case-hover');$('explorer-tooltip').hidden=true;});cy.on('pan',()=>{$('explorer-tooltip').hidden=true;});
  if(!data.nodes.length){if(viewport)cy.viewport(viewport);status('No accessible objects match this view. Change the search or type filters.');return;}
  if(viewport&&known)cy.viewport(viewport);else arrange();
  if(retainedSelection.length){cy.nodes(':visible').filter(n=>retainedSelection.includes(n.id())).select();syncSelection();}
  originalViewport={zoom:cy.zoom(),pan:{...cy.pan()}};status(data.scope+' · '+data.limit+'-object view limit. Search includes immediate neighbors.');
 }
 function selectionFeedback(){
  if(!cy||cy.destroyed())return;
  feedbackPending=false;
  const active=cy.nodes(':selected, .marquee-preview'),ids=new Set(active.map(n=>n.id()));
  cy.batch(()=>{
   for(const node of feedbackNodes)if(node.cy()===cy&&!node.removed()&&!ids.has(node.id()))node.removeStyle('border-width underlay-padding');
   // Keep the crisp outline and boundary halo legible in screen pixels.
   active.style({'border-width':3/cy.zoom(),'underlay-padding':9/cy.zoom()});
  });
  feedbackNodes=new Set(active);
 }
 function scheduleSelectionFeedback(){if(!feedbackPending){feedbackPending=true;queueMicrotask(selectionFeedback);}}
 function drawMarquee(){
  if(!marqueeActive||!marqueeStart||!marqueeEnd||!cy)return;
  const zoom=cy.zoom(),pan=cy.pan(),x1=marqueeStart.x*zoom+pan.x,y1=marqueeStart.y*zoom+pan.y,x2=marqueeEnd.x*zoom+pan.x,y2=marqueeEnd.y*zoom+pan.y;
  Object.assign(marquee.style,{left:Math.min(x1,x2)+'px',top:Math.min(y1,y2)+'px',width:Math.abs(x2-x1)+'px',height:Math.abs(y2-y1)+'px'});marquee.hidden=false;
  const seed=new Set(marqueeSeed);
  cy.batch(()=>cy.nodes().forEach(node=>{
   const p=node.position(),inside=node.visible()&&p.x>=Math.min(marqueeStart.x,marqueeEnd.x)&&p.x<=Math.max(marqueeStart.x,marqueeEnd.x)&&p.y>=Math.min(marqueeStart.y,marqueeEnd.y)&&p.y<=Math.max(marqueeStart.y,marqueeEnd.y);
   node.toggleClass('marquee-preview',node.visible()&&(inside||seed.has(node.id())));
  }));
  selectionFeedback();
 }
 function hideMarquee(){
  marqueeActive=false;marquee.hidden=true;
  if(marqueeFrame!==null){cancelAnimationFrame(marqueeFrame);marqueeFrame=null;}
  if(cy&&!cy.destroyed()){cy.nodes('.marquee-preview').removeClass('marquee-preview');selectionFeedback();}
 }
 function syncSelection(){
  if(!cy||cy.destroyed())return;
  cy.elements(':selected').filter(n=>!n.isNode()||!n.visible()).unselect();
  const chosen=cy.nodes(':selected:visible');
  if(!chosen.length){deselect();return;}
  if(chosen.length===1){select(chosen[0]);return;}
  cancelArrangement();selectedId=null;relationshipGroupsOpen.clear();detailRequest?.abort();detailSerial++;closePanel('details');
  cy.elements().addClass('muted').removeClass('related');chosen.closedNeighborhood().removeClass('muted').addClass('related');objects();
  const counts=new Map();chosen.forEach(n=>counts.set(n.data('kind'),(counts.get(n.data('kind'))||0)+1));
  $('explorer-tray').hidden=false;putIcon($('explorer-tray-icon'),'files');$('explorer-tray-icon').className='';
  $('explorer-tray-title').textContent=`${chosen.length} objects selected`;$('explorer-tray-title').title='';
  $('explorer-tray-subtitle').textContent='Drag any selected object to move the group.';$('explorer-tray-subtitle').dataset.stage='';
  $('explorer-tray-summary').replaceChildren(...[...counts].map(([kind,count])=>element('span',`${{case:'Cases',family:'Malware Families',actor:'Threat Actors',category:'MIP categories'}[kind]} ${count}`)));
  for(const id of ['explorer-open','explorer-expand','explorer-details-toggle'])$(id).hidden=true;
  $('explorer-clear-selection').hidden=false;$('explorer-deselect').setAttribute('aria-label','Clear Selection');
  $('explorer-detail-body').replaceChildren();
 }
 function pruneSelection(){
  if(!cy)return;
  const selected=cy.nodes(':selected'),hidden=selected.filter(n=>!n.visible());
  if(hidden.length){hidden.unselect();syncSelection();}
 }
 function cancelGesture(){
  if(!gestureActive)return;gestureCanceled=true;
  window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0,clientX:gestureClient.x,clientY:gestureClient.y}));
  gestureActive=false;followers=[];hideMarquee();savePositions();
 }
 const gestureEnd=()=>{gestureActive=false;hideMarquee();};
 window.addEventListener('mouseup',gestureEnd);window.addEventListener('blur',cancelGesture);document.addEventListener('pointercancel',cancelGesture);
 const modifier=/Mac|iPhone|iPad/.test(navigator.platform)?'⌘':'CTRL';
 $('explorer-selection-hint').textContent=`${modifier} + drag to select • Drag selected objects to move.`;
 function summaryFor(node){
  if(summaries.has(node.id()))return Promise.resolve(summaries.get(node.id()));
  if(summaryTasks.has(node.id()))return summaryTasks.get(node.id());
  const controller=new AbortController(),revision=serial;requests.set(node.id(),controller);
  const task=json(contentURL(node.data('uid')),controller.signal).then(data=>{if(disposed||revision!==serial)throw new DOMException('Stale summary','AbortError');summaries.set(node.id(),data);return data;}).finally(()=>{if(requests.get(node.id())===controller){requests.delete(node.id());summaryTasks.delete(node.id());}});
  summaryTasks.set(node.id(),task);return task;
 }
 function syncExpansionControl(node){const control=$('explorer-expand');control.hidden=node.data('kind')!=='case';control.textContent=expanded.has(node.id())?'Collapse Standard MIP':'Expand Standard MIP';control.disabled=!showContents()&&!expanded.has(node.id());control.onclick=()=>toggleCase(node);}
 function caseSummary(node,data){
  if(selectedId!==node.id())return;
  const summary=$('explorer-tray-summary');summary.replaceChildren();
  for(const group of data.categories){summary.append(button(group.label+' '+group.count,async()=>{if(!showContents()){$('explorer-show-contents').checked=true;contentsVisibility();}if(!expanded.has(node.id()))await toggleCase(node);const child=cy?.getElementById(node.id()+':'+group.kind);if(child?.length)select(child);}));}
  if(!data.categories.length)summary.append(element('span','No visible nonempty categories'));
  summary.title=data.note+(data.restricted.length?' Some categories are hidden by permissions.':'');
 }
 function select(node){
  $('explorer-details-toggle').hidden=false;$('explorer-clear-selection').hidden=true;$('explorer-deselect').setAttribute('aria-label','Deselect object');
  if(selectedId!==node.id()){cancelArrangement();relationshipGroupsOpen.clear();}
  selectedId=node.id();cy.elements().unselect().addClass('muted').removeClass('related');node.select();(node.isEdge()?node.union(node.connectedNodes()):node.closedNeighborhood()).removeClass('muted').addClass('related');objects();detailRequest?.abort();detailSerial++;
  const data=node.data(),kind=data.kind,tray=$('explorer-tray');tray.hidden=false;
  putIcon($('explorer-tray-icon'),kind==='category'?data.category:kind||'references');$('explorer-tray-icon').className=kind||'';
  $('explorer-tray-title').textContent=node.isEdge()?'Relationship':kind==='case'?data.number:kind==='category'?data.label:data.name;
  $('explorer-tray-title').title=data.label||data.explanation;
  $('explorer-tray-subtitle').textContent=node.isEdge()?data.explanation:kind==='case'?data.status+' · '+primaryEdges(node).length+' relationships':kind==='category'?data.parentLabel:data.tag;
  $('explorer-tray-subtitle').dataset.stage=kind==='case'?data.stage:'';
  const open=$('explorer-open');open.hidden=!data.url;if(data.url){open.href=data.url;open.textContent={case:'Open Case',family:'Open Malware Family',actor:'Open Threat Actor'}[kind];}
  syncExpansionControl(node);$('explorer-tray-summary').replaceChildren(element('span',node.isEdge()?node.source().data('label')+' ↔ '+node.target().data('label'):kind==='category'?data.count+' included items':primaryEdges(node).length+' relationships'));
  if(node.isEdge()){$('explorer-detail-body').replaceChildren(element('h3','Relationship'),element('p',data.explanation),element('p',node.source().data('label')+' ↔ '+node.target().data('label')));return;}
  if(kind==='category'){openPanel('details');category(node);return;}
  const body=$('explorer-detail-body');body.replaceChildren(element('h3',data.name),element('p',kind==='case'?data.number+' · '+data.status:data.tag));
  if(data.aliases?.length)body.append(element('p','Aliases: '+data.aliases.join(' · ')));
  body.append(link({case:'Open Case',family:'Open Malware Family',actor:'Open Threat Actor'}[kind],data.url));
  if(kind==='case'){
   body.append(element('p','Saved Standard package without optional malware samples. Counts describe composition, not export readiness.','muted'));
   summaryFor(node).then(result=>caseSummary(node,result)).catch(error=>{if(error.name!=='AbortError'&&selectedId===node.id())$('explorer-tray-summary').replaceChildren(element('span','MIP summary unavailable. Retry by refreshing data.'));});
  }
  immediateRelationships(node,body);
 }
 function immediateRelationships(node,body){
  body.append(element('h4','Immediate relationships'));
  const groups=new Map(['case','family','actor'].map(kind=>[kind,new Map()]));
  primaryEdges(node).forEach(edge=>{
   const other=edge.source().id()===node.id()?edge.target():edge.source(),group=groups.get(other.data('kind'));
   if(!group)return;
   if(!group.has(other.id()))group.set(other.id(),{node:other,explanations:new Set()});
   group.get(other.id()).explanations.add(edge.data('explanation'));
  });
  if(![...groups.values()].some(group=>group.size)){body.append(element('p','No configured relationships in this view.','muted'));return;}
  body.append(element('p','Links select objects in the graph. Use the selected object’s Open action to visit its page.','explorer-relationship-hint muted'));
  for(const [kind,objects] of groups){
   if(!objects.size)continue;
   const label={case:'Cases',family:'Malware Families',actor:'Threat Actors'}[kind],group=element('section',undefined,'explorer-relationship-group');
   group.dataset.relationshipKind=kind;
   const heading=element('h5'),toggle=button('',()=>{
    const open=toggle.getAttribute('aria-expanded')!=='true';
    relationshipGroupsOpen.set(kind,open);toggle.setAttribute('aria-expanded',String(open));table.hidden=!open;
   });
   toggle.className='explorer-relationship-toggle';
   const icon=element('span',undefined,'explorer-relationship-icon');icon.setAttribute('aria-hidden','true');putIcon(icon,kind);
   const chevron=element('span',undefined,'explorer-relationship-chevron');chevron.setAttribute('aria-hidden','true');
   toggle.append(icon,element('span',`${label} (${objects.size})`),chevron);heading.append(toggle);
   const table=element('table',undefined,'explorer-relationship-table');table.id='explorer-relationships-'+kind;table.setAttribute('aria-label',label+' immediate relationships');
   const open=relationshipGroupsOpen.get(kind)??true;table.hidden=!open;toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-controls',table.id);
   const head=element('thead'),headers=element('tr');
   for(const title of kind==='case'?['Case','Title']:['Object','Tag']){const th=element('th',title);th.scope='col';headers.append(th);}
   head.append(headers);const rows=element('tbody');
   for(const {node:other,explanations} of objects.values()){
    const data=other.data(),row=element('tr'),object=element('td'),value=element('td',kind==='case'?data.name:data.tag);
    if(kind!=='case')value.className='explorer-relationship-tag';
    const selectLink=link(kind==='case'?data.number:data.name,data.url);
    selectLink.title=`Select ${data.label} in graph. ${[...explanations].filter(Boolean).join(' ')}`;
    selectLink.setAttribute('aria-label',`Select ${data.label} in graph`);
    selectLink.addEventListener('click',event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();select(other);});
    object.append(selectLink);row.append(object,value);rows.append(row);
   }
   table.append(head,rows);group.append(heading,table);body.append(group);
  }
 }
 function childPosition(parent,index,total){
  const center=parent.position(),others=cy.nodes(':visible');let best,bestClearance=-Infinity;
  for(let ring=0;ring<4;ring++)for(let slot=0;slot<12;slot++){
   const angle=2*Math.PI*(slot/12+index/Math.max(1,total)),radius=145+ring*65,point={x:center.x+radius*Math.cos(angle),y:center.y+radius*Math.sin(angle)};
   const clearance=others.reduce((min,n)=>{const box=n.boundingBox();return Math.min(min,Math.hypot(Math.max(box.x1-point.x,0,point.x-box.x2),Math.max(box.y1-point.y,0,point.y-box.y2)));},Infinity);
   if(clearance>bestClearance){bestClearance=clearance;best=point;}if(clearance>38)return point;
  }
  return best;
 }
 async function toggleCase(node){
  cancelArrangement();
  const control=$('explorer-expand');
  if(expanded.has(node.id())){const hadSelection=cy.nodes(':selected').length>0;cy.nodes().filter(n=>n.data('caseNode')===node.id()).remove();if(hadSelection)syncSelection();expanded.delete(node.id());syncExpansionControl(node);objects();return;}
  if(!showContents())return;control.disabled=true;const revision=serial;
  try{const data=await summaryFor(node);if(disposed||revision!==serial||!cy.hasElementWithId(node.id())||!showContents())return;
   if(expanded.has(node.id()))return;
   data.categories.forEach((group,index)=>{const id=node.id()+':'+group.kind;cy.add([{data:{id,kind:'category',label:group.label,caption:'',category:group.kind,count:group.count,caseNode:node.id(),caseId:node.data('uid'),parentLabel:node.data('label')},position:childPosition(node,index,data.categories.length)},{data:{id:'edge:'+id,source:node.id(),target:id,categoryEdge:true,explanation:group.definition}}]);});
   expanded.add(node.id());icons();objects();const rect=safeRect(),children=cy.nodes().filter(n=>n.data('caseNode')===node.id());if(children.some(n=>{const p=n.renderedPosition();return p.x<rect.left||p.x>rect.right||p.y<rect.top||p.y>rect.bottom;}))fitView();status(data.note+(data.restricted.length?' Some categories are hidden by permissions.':''));
  }catch(error){if(error.name!=='AbortError')status(error.message,true);}finally{if(selectedId===node.id())syncExpansionControl(node);}
 }
 function contentsVisibility(){
  if(cy){const cats=cy.nodes('[kind="category"]');cats.union(cats.connectedEdges()).style('display',showContents()?'element':'none');if(selectedId&&cy.getElementById(selectedId).length)syncExpansionControl(cy.getElementById(selectedId));objects();}
  pruneSelection();filterBadge();saveURL();
 }
 async function category(node,page=0){
  detailRequest?.abort();detailRequest=new AbortController();const version=++detailSerial,body=$('explorer-detail-body');body.replaceChildren(element('h3',node.data('label')),element('p','Loading category…'));
  try{const data=await json(contentURL(node.data('caseId'))+'/'+node.data('category')+'?page='+page,detailRequest.signal);if(disposed||version!==detailSerial)return;
   body.replaceChildren(element('h3',data.label+' · '+data.count),element('p',node.data('parentLabel')),element('p',data.definition,'muted'));
   if(data.columns.length){if(node.data('category')!=='references'){
    const indicators=node.data('category')==='indicators',wrapper=element('div',undefined,'explorer-table'),table=element('table'),head=element('tr');
    // Project only the details view; keep the authorized records and page intact.
    const columns=indicators?['Type','Value']:data.columns;
    const indexes=indicators?['type','value'].map((name,index)=>{const found=data.columns.findIndex(column=>column.trim().toLowerCase()===name);return found<0?index:found;}):data.columns.map((_,index)=>index);
    if(indicators)table.className='explorer-indicator-table';
    columns.forEach(name=>{const th=element('th',name);th.scope='col';head.append(th);});
    const thead=element('thead');thead.append(head);table.append(thead);const tbody=element('tbody');
    data.items.forEach(item=>{const row=element('tr');indexes.forEach(index=>row.append(element('td',item.cells[index]??'')));tbody.append(row);});
    table.append(tbody);wrapper.append(table);body.append(wrapper);
   }
    if(node.data('category')==='references'){const list=element('ul',undefined,'explorer-items');data.items.forEach(item=>{const row=element('li'),value=item.cells[0];try{const url=new URL(value);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password){const a=link(value,url.href);a.target='_blank';a.rel='noopener noreferrer';row.append(a);}else row.append(element('span',value));}catch{row.append(element('span',value));}row.append(element('p',item.cells[1]||''));list.append(row);});body.append(list);}
   }else{const list=element('ul',undefined,'explorer-items');data.items.forEach(item=>{const row=element('li');row.append(element('span',item.filename));if(item.download)row.append(element('br'),link('Download',item.download));if(item.generated)row.append(element('p','Generated during export','muted'));list.append(row);});body.append(list);}
   if(!data.count)body.append(element('p','No items remain in this saved category. Refresh the graph to update its summary.'));
   if(data.pages>1){body.append(element('p',`Page ${data.page+1} of ${data.pages}`));if(data.page>0)body.append(button('Previous items',()=>category(node,data.page-1)));if(data.page+1<data.pages)body.append(button('Next items',()=>category(node,data.page+1)));}
  }catch(error){if(error.name!=='AbortError'&&version===detailSerial)body.append(element('p',error.message));}
 }

 function saveURL(){const params=new URLSearchParams({q:$('explorer-query').value});const checked=[...document.querySelectorAll('[name=explorer-type]:checked')];checked.forEach(input=>params.append('type',input.value));if(!checked.length)params.set('type','none');if(!showContents())params.set('contents','0');const url=new URL(location.href);url.search=params.toString();history.replaceState(null,'',url);}
 async function load(){const version=++serial;graphRequest?.abort();graphRequest=new AbortController();const params=new URLSearchParams({q:$('explorer-query').value});document.querySelectorAll('[name=explorer-type]:checked').forEach(input=>params.append('type',input.value));status('Loading relationships…');filterBadge();
  try{const data=params.has('type')?await json(shell.dataset.source+'?'+params,graphRequest.signal):{nodes:[],edges:[],total:0,scope:'No object types selected',limit:400};if(disposed||version!==serial)return;init(data);saveURL();}
  catch(error){if(error.name!=='AbortError'&&version===serial){status((cy?'Showing the previous view. ':'')+error.message,true);if(!cy)$('explorer-tally').textContent='Graph unavailable';}}
 }
 $('explorer-search').onsubmit=event=>{event.preventDefault();load();};document.querySelectorAll('[name=explorer-type]').forEach(input=>input.onchange=load);$('explorer-show-contents').onchange=contentsVisibility;
 $('explorer-filters-reset').onclick=()=>{document.querySelectorAll('[name=explorer-type]').forEach(input=>input.checked=!input.disabled);$('explorer-show-contents').checked=true;load();};
 for(const name of ['filters','help','layout-settings'])$(name==='layout-settings'?'explorer-layout-toggle':'explorer-'+name+'-toggle').onclick=()=>{$('explorer-'+name).hidden?openPanel(name):closePanel(name,true);};
 document.querySelectorAll('[data-close]').forEach(el=>el.onclick=()=>closePanel(el.dataset.close,true));
 $('explorer-details-toggle').onclick=()=>{$('explorer-details').hidden?openPanel('details'):closePanel('details',true);};$('explorer-details-close').onclick=()=>closePanel('details',true);
 $('explorer-clear-selection').onclick=()=>{deselect();$('explorer-canvas').focus();};
 $('explorer-deselect').onclick=()=>{deselect();$('explorer-canvas').focus();};
 const outside=event=>{for(const name of ['filters','help','layout-settings'])if(!$('explorer-'+name).hidden&&!$('explorer-'+name).contains(event.target)&&!$(name==='layout-settings'?'explorer-layout-toggle':'explorer-'+name+'-toggle').contains(event.target))closePanel(name);};
 const escape=event=>{if(event.key!=='Escape')return;if(gestureActive){event.preventDefault();cancelGesture();deselect();queueMicrotask(deselect);return;}if(cy?.nodes(':selected').length>1||(cy?.nodes(':selected').length&&document.activeElement===$('explorer-canvas'))){event.preventDefault();cancelGesture();deselect();return;}const focused=['filters','help','layout-settings','details'].find(name=>!$('explorer-'+name).hidden&&$('explorer-'+name).contains(document.activeElement));for(const name of focused?[focused]:['details','filters','help','layout-settings'])if(!$('explorer-'+name).hidden){event.preventDefault();closePanel(name,true);return;}if(!$('explorer-tray').hidden){deselect();$('explorer-canvas').focus();}};
 document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
 $('explorer-reload').onclick=load;$('explorer-arrange').onclick=arrange;$('explorer-fit').onclick=fitView;
 const zoom=factor=>{if(cy)cy.zoom({level:Math.max(cy.minZoom(),Math.min(3,cy.zoom()*factor)),renderedPosition:{x:cy.width()/2,y:cy.height()/2}});};
 $('explorer-zoom-in').onclick=()=>zoom(1.25);$('explorer-zoom-out').onclick=()=>zoom(.8);$('explorer-reset').onclick=()=>{if(cy&&originalViewport)cy.viewport(originalViewport);};
 $('explorer-objects').onchange=event=>{const node=cy?.getElementById(event.target.value);if(node?.length){closePanel('help');select(node);if(node.data('kind')!=='category')$('explorer-details-toggle').focus();}};
 $('explorer-canvas').onkeydown=event=>{if(!cy)return;const moves={ArrowLeft:{x:50,y:0},ArrowRight:{x:-50,y:0},ArrowUp:{x:0,y:50},ArrowDown:{x:0,y:-50}};if(moves[event.key]){event.preventDefault();cy.panBy(moves[event.key]);}else if(['+','=','-'].includes(event.key)){event.preventDefault();zoom(event.key==='-'?.8:1.25);}};
 function sizeCanvas(){const height=Math.max(innerWidth<=650?480:320,Math.floor(innerHeight-shell.getBoundingClientRect().top-scrollY-16));shell.style.setProperty('--explorer-height',height+'px');}
 sizeCanvas();let previousSize={w:0,h:0};const observer=new ResizeObserver(()=>{if(!cy)return;const w=$('explorer-canvas').clientWidth,h=$('explorer-canvas').clientHeight;cy.resize();if(previousSize.w&&(w!==previousSize.w||h!==previousSize.h))fitView();previousSize={w,h};});observer.observe($('explorer-canvas'));window.addEventListener('resize',sizeCanvas);
 window.addEventListener('pagehide',()=>{hideMarquee();disposed=true;serial++;detailSerial++;graphRequest?.abort();detailRequest?.abort();requests.forEach(r=>r.abort());layout?.terminate();layoutVersion++;observer.disconnect();window.removeEventListener('resize',sizeCanvas);document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);window.removeEventListener('mouseup',gestureEnd);window.removeEventListener('blur',cancelGesture);document.removeEventListener('pointercancel',cancelGesture);cy?.destroy();});window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
 const initial=new URLSearchParams(location.search);$('explorer-query').value=initial.get('q')||'';if(initial.has('type'))document.querySelectorAll('[name=explorer-type]').forEach(input=>input.checked=!input.disabled&&initial.getAll('type').includes(input.value));$('explorer-show-contents').checked=initial.get('contents')!=='0';filterBadge();load();
})();
