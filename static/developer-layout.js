/* Non-sensitive, per-user workspace preferences and accessible splitters. */
window.MareDeveloperWorkspace = function(root, kind) {
  const key='mare-workspace:'+document.body.dataset.userLayout;
  let prefs={};try{const value=JSON.parse(localStorage.getItem(key)||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))prefs=value;}catch{}
  const save=patch=>{Object.assign(prefs,patch);try{localStorage.setItem(key,JSON.stringify(prefs));}catch{}};
  function splitter(handle,{axis,variable,initial,min,max,store}) {
    let value=Number(prefs[store]);if(!Number.isFinite(value))value=initial;
    let preferred=value;
    function set(next){preferred=next;value=Math.max(min(),Math.min(max(),next));root.style.setProperty(variable,value+'px');handle.setAttribute('aria-valuenow',Math.round(value));handle.setAttribute('aria-valuemin',Math.round(min()));handle.setAttribute('aria-valuemax',Math.round(max()));}
    set(value);let gesture;
    handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();gesture={position:axis==='x'?event.clientX:event.clientY,value};handle.setPointerCapture(event.pointerId);document.body.classList.add('workspace-resizing');});
    handle.addEventListener('pointermove',event=>{if(!gesture)return;const delta=(axis==='x'?event.clientX:event.clientY)-gesture.position;set(gesture.value+(axis==='y'?-delta:delta));});
    const finish=()=>{if(!gesture)return;gesture=null;document.body.classList.remove('workspace-resizing');save({[store]:value});};
    for(const event of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(event,finish);
    handle.addEventListener('keydown',event=>{const forward=axis==='x'?'ArrowRight':'ArrowUp',back=axis==='x'?'ArrowLeft':'ArrowDown';if(![forward,back,'Home','End'].includes(event.key))return;event.preventDefault();set(event.key==='Home'?min():event.key==='End'?max():value+(event.key===forward?20:-20));save({[store]:value});});
    new ResizeObserver(()=>set(preferred)).observe(root);
  }
  if(kind==='editor'){
    splitter(root.querySelector('[data-explorer-splitter]'),{axis:'x',variable:'--explorer-width',initial:240,min:()=>140,max:()=>Math.max(140,Math.min(480,root.clientWidth*.55)),store:'explorerWidth'});
    splitter(root.querySelector('[data-console-splitter]'),{axis:'y',variable:'--console-height',initial:200,min:()=>70,max:()=>Math.max(70,root.querySelector('.ide-center').clientHeight*.55),store:'consoleHeight'});
    const button=root.querySelector('[data-explorer-toggle]');
    const visible=value=>{root.classList.toggle('explorer-hidden',!value);button.setAttribute('aria-expanded',String(value));};
    visible(prefs.explorerVisible??matchMedia('(min-width:700px)').matches);
    button.onclick=()=>{const value=root.classList.contains('explorer-hidden');visible(value);save({explorerVisible:value});};
    const auto=root.querySelector('[data-auto-sidebar]'),collapse=document.getElementById('sidebar-collapse');
    let previous,temporary=false;
    function applySidebar(value){if(value&&!temporary&&matchMedia('(min-width:901px)').matches){previous=document.body.classList.contains('sidebar-collapsed');if(!previous)collapse.click();temporary=true;}else if(!value&&temporary){if(document.body.classList.contains('sidebar-collapsed')!==previous)collapse.click();temporary=false;}}
    auto.checked=!!prefs.autoSidebar;auto.onchange=()=>{save({autoSidebar:auto.checked});applySidebar(auto.checked);};
    // Shell initialization runs before this factory. Restore its persisted state
    // on exit, including ordinary navigation and BFCache transitions.
    if(document.readyState==='complete')applySidebar(auto.checked);else document.addEventListener('DOMContentLoaded',()=>applySidebar(auto.checked),{once:true});window.addEventListener('pagehide',()=>applySidebar(false));window.addEventListener('pageshow',event=>{if(event.persisted)applySidebar(auto.checked);});
  }else splitter(root.querySelector('[data-inventory-splitter]'),{axis:'x',variable:'--inventory-width',initial:330,min:()=>Math.min(240,root.clientWidth*.35),max:()=>Math.max(140,root.clientWidth*.45),store:'inventoryWidth'});
  return {prefs,save};
};
