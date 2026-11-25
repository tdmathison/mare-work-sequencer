/* Native accessible selectors keep their editing/focus state; no async defaults. */
(() => {
  function syncSelector(select){
    const option=select.selectedOptions[0],swatch=select.parentElement.querySelector('[data-tlp-selected]');
    swatch.style.setProperty('--tlp-color',option.dataset.color||'#000000');
    const help=document.getElementById(select.getAttribute('aria-describedby'));
    if(help&&option.dataset.help)help.firstChild.textContent=option.dataset.help+' TLP describes sharing boundaries, not threat severity. ';
  }
  document.addEventListener('change',event=>{const select=event.target.closest('[data-tlp-select]');if(select)syncSelector(select);});
  window.MareTlp={applySaved(page){
    document.querySelectorAll('[data-tlp-select]').forEach(syncSelector);
    const saved=page.querySelector('[data-tlp-badge]'),current=document.querySelector('[data-tlp-badge]');
    if(saved&&current){current.textContent=saved.textContent;current.setAttribute('style',saved.getAttribute('style'));}
  }};
  let serial=0,controller;
  async function refreshBoard(){
    if(!document.querySelector('[data-tlp-case]'))return;
    const current=++serial;controller?.abort();controller=new AbortController();
    const status=document.querySelector('[data-board-tlp-status]');
    try{
      const response=await fetch(location.href,{cache:'no-store',credentials:'same-origin',signal:controller.signal});
      if(!response.ok||response.redirected)throw Error();
      const page=new DOMParser().parseFromString(await response.text(),'text/html');
      if(current!==serial)return;
      if(page.body.dataset.userLayout!==document.body.dataset.userLayout)throw Error();
      for(const marker of document.querySelectorAll('[data-tlp-case]')){
        const saved=page.querySelector(`[data-tlp-case="${marker.dataset.tlpCase}"]`);if(!saved)continue;
        for(const key of ['data-tlp','aria-label','title','style'])marker.setAttribute(key,saved.getAttribute(key));
        marker.querySelector('[data-tlp-symbol]').textContent=saved.querySelector('[data-tlp-symbol]').textContent;
        marker.querySelector('.tlp-tooltip').textContent=saved.dataset.tlp;
      }
      if(status)status.textContent='';
    }catch(error){if(current===serial&&error.name!=='AbortError'&&status)status.textContent='Case TLP designations could not be refreshed. Displayed markings may be out of date; reopen the Board to retry.';}
  }
  window.addEventListener('pageshow',event=>{if(event.persisted)refreshBoard();});
  window.addEventListener('focus',refreshBoard);
})();
