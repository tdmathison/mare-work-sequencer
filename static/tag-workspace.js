/* Progressive enhancement: existing tag URLs/forms remain authoritative. */
(() => {
  let root=document.querySelector('[data-tag-workspace]');if(!root)return;
  let generation=0;
  function bind(){
    for(const tabs of root.querySelectorAll('.mws-tabs'))window.MwsTabs.bind(tabs,tab=>tab.click());
    const url=new URL(root.dataset.selectedUrl,location.origin);
    if(['#tag-edit','#tag-delete','#tag-merge'].includes(location.hash))url.hash=location.hash;
    history.replaceState(history.state,'',url);
    const disclosure=url.hash&&root.querySelector(url.hash);if(disclosure){disclosure.open=true;disclosure.scrollIntoView({block:'nearest'});}
  }
  async function navigate(url,push=true,focus='detail'){
    const current=++generation,scroll=root.querySelector('.intelligence-directory-list').scrollTop;
    root.setAttribute('aria-busy','true');root.querySelector('[data-tag-status]').textContent='Loading tags…';
    try{
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store',headers:{Accept:'text/html'}});
      if(response.status===404){const fallback=new URL('/tags',location.origin);fallback.search=new URL(url,location.origin).search;await navigate(fallback,push,focus);return;}
      if(!response.ok)throw Error('Unable to load tags ('+response.status+'). Try again.');
      const document=new DOMParser().parseFromString(await response.text(),'text/html');
      const next=document.querySelector('[data-tag-workspace]');
      if(!next)throw Error('Your session may have expired. Refresh this page to sign in.');
      if(current!==generation)return;
      root.replaceWith(next);root=next;
      if(push)history.pushState({},'',url);
      bind();root.querySelector('.intelligence-directory-list').scrollTop=scroll;
      window.MwsIntelligenceWorkspace.revealSelection(root);
      const disclosure=location.hash&&root.querySelector(location.hash);
      if(disclosure)disclosure.querySelector('input:not([type=hidden])')?.focus();
      else if(focus==='tab')root.querySelector('.tag-detail-tabs [aria-current=page]')?.focus({preventScroll:true});
      else if(focus==='search')root.querySelector('[name=q]').focus({preventScroll:true});
      else root.querySelector('.tag-detail').focus({preventScroll:true});
    }catch(error){if(current===generation)root.querySelector('[data-tag-status]').textContent=error.message;}
    finally{if(current===generation)root.removeAttribute('aria-busy');}
  }
  document.addEventListener('click',event=>{
    if(!root.contains(event.target))return;
    const link=event.target.closest('a[data-tag-nav]');
    if(link&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&event.button===0){event.preventDefault();navigate(link.href,true,link.closest('.mws-tabs')?'tab':link.closest('.tag-directory')&&!link.dataset.tagId?'search':'detail');return;}
    if(event.target.closest('[data-tag-create]')){const dialog=root.querySelector('[data-tag-create-dialog]');dialog.showModal();dialog.querySelector('[name=name]').focus();}
    if(event.target.closest('[data-tag-create-cancel]'))root.querySelector('[data-tag-create-dialog]').close();
  });
  document.addEventListener('submit',event=>{
    if(!root.contains(event.target)||!event.target.matches('[data-tag-search]'))return;
    event.preventDefault();const url=new URL(event.target.action,location.origin);
    url.search=new URLSearchParams(new FormData(event.target));navigate(url,true,'search');
  });
  window.addEventListener('popstate',()=>navigate(location.href,false));
  bind();
})();
