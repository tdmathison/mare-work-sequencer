/* Non-sensitive, per-user plugin preferences and accessible inventory splitter. */
window.MarePluginLayout = function(root) {
  const key='mare-plugins:'+document.body.dataset.userLayout;
  let prefs={};try{const value=JSON.parse(localStorage.getItem(key)||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))prefs=value;}catch{}
  if(!Object.keys(prefs).length){try{const oldKey='mare-workspace:'+document.body.dataset.userLayout,old=JSON.parse(localStorage.getItem(oldKey)||'{}');for(const name of ['inventoryWidth','lastPlugin'])if(name in old)prefs[name]=old[name];localStorage.removeItem(oldKey);}catch{}}
  const save=patch=>{Object.assign(prefs,patch);try{localStorage.setItem(key,JSON.stringify(prefs));}catch{}};
  function splitter(handle,{variable,initial,min,max,store}) {
    let value=Number(prefs[store]);if(!Number.isFinite(value))value=initial;
    let preferred=value;
    function set(next){preferred=next;value=Math.max(min(),Math.min(max(),next));root.style.setProperty(variable,value+'px');handle.setAttribute('aria-valuenow',Math.round(value));handle.setAttribute('aria-valuemin',Math.round(min()));handle.setAttribute('aria-valuemax',Math.round(max()));}
    set(value);let gesture;
    handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();gesture={position:event.clientX,value};handle.setPointerCapture(event.pointerId);document.body.classList.add('workspace-resizing');});
    handle.addEventListener('pointermove',event=>{if(!gesture)return;const delta=(event.clientX)-gesture.position;set(gesture.value+delta);});
    const finish=()=>{if(!gesture)return;gesture=null;document.body.classList.remove('workspace-resizing');save({[store]:value});};
    for(const event of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(event,finish);
    handle.addEventListener('keydown',event=>{const forward='ArrowRight',back='ArrowLeft';if(![forward,back,'Home','End'].includes(event.key))return;event.preventDefault();set(event.key==='Home'?min():event.key==='End'?max():value+(event.key===forward?20:-20));save({[store]:value});});
    new ResizeObserver(()=>set(preferred)).observe(root);
  }
  splitter(root.querySelector('[data-inventory-splitter]'),{variable:'--inventory-width',initial:330,min:()=>Math.min(240,root.clientWidth*.35),max:()=>Math.max(140,root.clientWidth*.45),store:'inventoryWidth'});
  return {prefs,save};
};
