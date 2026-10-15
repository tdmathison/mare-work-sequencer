(() => {
  const form=document.querySelector('.sync-review [data-sync-form]');
  if(!form)return;
  const model=JSON.parse(document.getElementById('sync-review-model').textContent);
  const rows=[...form.querySelectorAll('[data-sync-row]')];
  function setExpanded(button,expanded){
    document.getElementById(button.getAttribute('aria-controls')).hidden=!expanded;
    button.setAttribute('aria-expanded',String(expanded));
    button.querySelector('[data-sync-chevron]').textContent=expanded?'▾':'▸';
  }
  function refresh(){
    const counts={new:0,update:0,replacement:0,unchanged:0,older:0,invalid:0,unresolved:0,kept:0,linked:0,applied:0};
    const skipped=[];
    for(const row of rows){
      const decision=row.querySelector('[data-sync-decision]')?.value||'';
      const target=row.querySelector('[data-sync-target]');
      const done=row.dataset.done==='true';
      let action=done?'applied':(model.actions[row.dataset.classification]?.[decision]||'unresolved');
      if(target){target.required=!done&&decision==='link';if(target.required&&!target.value)action='unresolved';}
      counts[action]++;
      if(!done){
        row.querySelector('[data-sync-effective]').textContent=decision==='link'&&!target?.value?'Pending — choose a link destination':model.labels[action];
        row.querySelector('[data-sync-effective]').dataset.effectiveAction=action;
      }
      const warning=row.querySelector('[data-sync-replacement]');if(warning)warning.hidden=decision!=='replace';
      if(['unchanged','older','invalid','unresolved','kept','linked','applied'].includes(action)){
        const li=document.createElement('li');li.textContent=`${row.dataset.caseLabel}: ${model.labels[action]}`;skipped.push(li);
      }
    }
    form.querySelector('[data-sync-plan]').textContent=`${counts.new} new · ${counts.update} updates · ${counts.replacement} replacement${counts.replacement===1?'':'s'} · ${counts.unchanged+counts.kept+counts.linked} no changes · ${counts.unresolved} unresolved · ${counts.older} skipped older · ${counts.invalid} invalid${counts.applied?` · ${counts.applied} already processed`:''}${counts.linked?` · ${counts.linked} provenance-only links`:''}`;
    const list=form.querySelector('[data-sync-skipped]');
    if(!skipped.length){const li=document.createElement('li');li.textContent='None.';skipped.push(li);}
    list.replaceChildren(...skipped);
  }
  form.addEventListener('click',event=>{
    const toggle=event.target.closest('[data-sync-toggle]');
    if(toggle){setExpanded(toggle,toggle.getAttribute('aria-expanded')!=='true');return;}
    const bulk=event.target.closest('[data-sync-bulk]');
    if(bulk)for(const button of form.querySelectorAll('[data-sync-toggle]'))setExpanded(button,bulk.dataset.syncBulk==='expand');
  });
  form.addEventListener('change',refresh);
  form.addEventListener('invalid',event=>{
    const panel=event.target.closest('[data-sync-panel]');
    if(panel){const button=[...form.querySelectorAll('[data-sync-toggle]')].find(button=>button.getAttribute('aria-controls')===panel.id);if(button)setExpanded(button,true);}
  },true);
  refresh();
})();
