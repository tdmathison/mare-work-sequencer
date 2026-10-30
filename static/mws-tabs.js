/* Authoritative tab interactions. Adapters own only routing and business guards. */
(() => {
  const children=list=>[...list.querySelectorAll(':scope > .mws-tab')];
  const available=tab=>!tab.disabled&&tab.getAttribute('aria-disabled')!=='true';
  const bindings=new WeakMap();
  function reveal(tab){
    const list=tab.closest('.mws-tabs');if(!list)return;
    const edge=list.getBoundingClientRect(),bounds=tab.getBoundingClientRect();
    if(bounds.left<edge.left)list.scrollLeft-=edge.left-bounds.left;
    else if(bounds.right>edge.right)list.scrollLeft+=bounds.right-edge.right;
  }
  function setActive(list,identifier,{panels=true}={}){
    const tabs=children(list),selected=typeof identifier==='string'?tabs.find(tab=>tab.id===identifier):identifier;
    if(!tabs.includes(selected)||!available(selected))return false;
    const visible=new Set(selected.getAttribute('aria-controls')?.split(/\s+/)||[]);
    for(const tab of tabs){
      const active=tab===selected;
      if(tab.tagName==='A'){
        if(active)tab.setAttribute('aria-current','page');else tab.removeAttribute('aria-current');
      }else{
        tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
      }
    }
    if(panels){
      const controlled=new Set(tabs.flatMap(tab=>(tab.getAttribute('aria-controls')||'').split(/\s+/)).filter(Boolean));
      for(const id of controlled){const panel=document.getElementById(id);if(panel)panel.hidden=!visible.has(id);}
    }
    reveal(selected);return true;
  }
  function bind(list,configuration={}){
    if(!list)return;if(bindings.has(list))return bindings.get(list);
    const options=typeof configuration==='function'?{onSelect:configuration}:configuration;
    const select=options.onSelect||((tab)=>setActive(list,tab,options));
    const direct=event=>{const tab=event.target.closest('.mws-tab');return tab?.parentElement===list?tab:null;};
    list.dataset.tabsBound='true';
    list.addEventListener('click',event=>{
      const tab=direct(event);if(!tab)return;
      if(!available(tab)){event.preventDefault();return;}
      // Links keep native navigation, modifier clicks and existing leave guards.
      if(tab.tagName!=='A')select(tab);
    });
    list.addEventListener('keydown',event=>{
      const tabs=children(list).filter(available),index=tabs.indexOf(direct(event));if(index<0)return;
      let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;
      if(event.key==='ArrowLeft')next=(index-1+tabs.length)%tabs.length;
      if(event.key==='Home')next=0;if(event.key==='End')next=tabs.length-1;
      if(next===undefined)return;
      event.preventDefault();const tab=tabs[next];tab.focus({preventScroll:true});reveal(tab);select(tab);
    });
    list.addEventListener('focusin',event=>{const tab=direct(event);if(tab)reveal(tab);});
    if(options.activeId)setActive(list,options.activeId,options);
    const active=list.querySelector('[aria-selected=true],[aria-current=page]');if(active)reveal(active);
    const controller={setActive:identifier=>setActive(list,identifier,options)};
    bindings.set(list,controller);return controller;
  }
  window.MwsTabs={bind,setActive,reveal};
  const focusKey='mws-tabs-keyboard-focus';let requested;
  try{requested=JSON.parse(sessionStorage.getItem(focusKey)||'null');sessionStorage.removeItem(focusKey);}catch(_){}
  document.querySelectorAll('.mws-tabs[data-tabs-links]').forEach(list=>{
    bind(list,tab=>{try{sessionStorage.setItem(focusKey,JSON.stringify({url:tab.href,at:Date.now()}));}catch(_){}tab.click();});
    const active=list.querySelector('[aria-current=page]');
    if(active&&requested?.url===location.href&&Date.now()-requested.at<30000){active.focus({preventScroll:true});reveal(active);}
  });
})();
