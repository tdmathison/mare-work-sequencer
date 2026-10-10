/* Small tag controls; server-confirmed POSTs use the existing session and CSRF. */
(()=>{
  const search = async (query, signal) => {
    const response = await fetch(`/tags/search?q=${encodeURIComponent(query)}`, {signal});
    if (!response.ok) throw Error('Unable to load tags. Please try again.');
    const data=await response.json();data.tags.exactId=data.exact_id;return data.tags;
  };
  const updateCaseTags=async (form, action, body)=>{
    const bar=form.closest('#case-tags'), feedback=bar.querySelector('[role=status]');
    if(bar.dataset.saving==='true')return false;
    bar.dataset.saving='true';
    try{
      const response=await fetch(action,{method:'POST',body,headers:{Accept:'application/json'},redirect:'error'});
      const data=await response.json().catch(()=>({error:'Unable to update tags. Please try again.'}));
      if(!response.ok||!Array.isArray(data.tags))throw Error(data.error||'Unable to update tags. Please try again.');
      // Only chips change. Keep the page and existing editor DOM/state intact.
      const scroll={x:window.scrollX,y:window.scrollY};
      const nested=[...document.querySelectorAll('.cm-scroller, textarea, .markdown-preview, .editor-preview')].map(el=>({el,x:el.scrollLeft,y:el.scrollTop}));
      const root=document.documentElement, anchor=root.style.overflowAnchor;
      root.style.overflowAnchor='none';
      const current=new Map([...bar.querySelectorAll('.tag-chip[data-tag-id]')].map(chip=>[Number(chip.dataset.tagId),chip]));
      const ids=new Set(data.tags.map(tag=>tag.id));
      let removedFocus=false;
      for(const [id,chip] of current)if(!ids.has(id)){removedFocus ||= chip.contains(document.activeElement);chip.remove();}
      for(const tag of data.tags)if(!current.has(tag.id)){
        const chip=document.createElement('span');chip.className='tag-chip';chip.dataset.tagId=tag.id;
        chip.title=`${tag.name} — assigned ${tag.assigned_at} by ${tag.assigned_by||'unknown user'}`;
        chip.append(document.createTextNode(tag.name));
        const remove=document.createElement('form');remove.method='post';remove.action=`/cases/${bar.querySelector('[data-tag-case]').dataset.tagCase}/tags/${tag.id}/remove`;
        remove.append(form.querySelector('[name=csrf]').cloneNode(true));
        const button=document.createElement('button');button.type='button';button.dataset.removeTag='';button.setAttribute('aria-label',`Remove ${tag.name} from case`);button.textContent='×';remove.append(button);chip.append(remove);
        bar.insertBefore(chip,bar.querySelector('.tag-autocomplete'));
      }
      feedback.textContent='';
      if(removedFocus)bar.querySelector('input[name=name]')?.focus({preventScroll:true});
      for(const {el,x,y} of nested){if(el.scrollLeft!==x)el.scrollLeft=x;if(el.scrollTop!==y)el.scrollTop=y;}
      window.scrollTo({left:scroll.x,top:scroll.y,behavior:'instant'});
      await new Promise(resolve=>requestAnimationFrame(()=>{root.style.overflowAnchor=anchor;resolve();}));
      return true;
    }catch(error){
      const root=document.documentElement,anchor=root.style.overflowAnchor,x=window.scrollX,y=window.scrollY;
      root.style.overflowAnchor='none';feedback.textContent=error.message;
      window.scrollTo({left:x,top:y,behavior:'instant'});
      await new Promise(resolve=>requestAnimationFrame(()=>{root.style.overflowAnchor=anchor;resolve();}));
      return false;
    }
    finally{delete bar.dataset.saving;}
  };
  document.querySelector('#case-tags')?.addEventListener('click',event=>{
    const button=event.target.closest('[data-remove-tag]');if(!button)return;
    event.preventDefault();const form=button.closest('form');updateCaseTags(form,form.action,new FormData(form));
  });
  document.querySelectorAll('.tag-autocomplete').forEach(form=>{
    const input=form.querySelector('input[name=name]'), list=form.querySelector('[role=listbox]'), feedback=form.querySelector('[role=status]');
    let options=[], active=-1, controller, timer, revision=0;
    const close=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;};
    const highlight=()=>{list.querySelectorAll('[role=option]').forEach((row,i)=>row.setAttribute('aria-selected',String(i===active)));if(active>=0){input.setAttribute('aria-activedescendant',`tag-option-${active}`);const row=list.children[active];if(row){if(row.offsetTop<list.scrollTop)list.scrollTop=row.offsetTop;else if(row.offsetTop+row.offsetHeight>list.scrollTop+list.clientHeight)list.scrollTop=row.offsetTop+row.offsetHeight-list.clientHeight;}}else input.removeAttribute('aria-activedescendant');};
    const submit=async option=>{
      if(!option)return;
      input.value=option.name;
      const action=option.id ? `/cases/${form.dataset.tagCase}/tags/${option.id}/assign` : `/cases/${form.dataset.tagCase}/tags/create`;
      clearTimeout(timer);revision++;controller?.abort();close();
      const submitted=input.value;
      if(await updateCaseTags(form,action,new FormData(form))){if(input.value===submitted)input.value='';options=[];}
    };
    const load=async()=>{
      const version=++revision;controller?.abort();controller=new AbortController();
      const typed=input.value.trim();if(!typed){close();return;}
      try{
        const tags=await search(typed,controller.signal);if(version!==revision||input.value.trim()!==typed)return;
        options=tags.map(tag=>({id:tag.id,name:tag.name,exact:tag.id===tags.exactId}));
        if(form.dataset.canCreate==='true'&&!tags.exactId)options.push({name:typed});
        active=-1;list.replaceChildren();
        options.forEach((option,i)=>{const row=document.createElement('li');row.id=`tag-option-${i}`;row.setAttribute('role','option');row.setAttribute('aria-selected','false');row.textContent=option.id?option.name:`Create “${option.name}”`;row.addEventListener('mousedown',e=>e.preventDefault());row.addEventListener('click',()=>submit(option));list.append(row);});
        list.hidden=!options.length;input.setAttribute('aria-expanded',String(!!options.length));feedback.textContent='';
      }catch(error){if(error.name!=='AbortError'){feedback.textContent=error.message;close();}}
    };
    input.addEventListener('input',()=>{revision++;controller?.abort();close();options=[];clearTimeout(timer);timer=setTimeout(load,120);});
    input.addEventListener('focus',load);
    input.addEventListener('blur',()=>setTimeout(close,100));
    input.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();clearTimeout(timer);revision++;controller?.abort();close();}
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();if(!options.length)return;list.hidden=false;input.setAttribute('aria-expanded','true');active=event.key==='ArrowDown'?(active+1)%options.length:(active<=0?options.length-1:active-1);highlight();
      }
    });
    form.addEventListener('submit',event=>{
      event.preventDefault();const typed=input.value.trim();
      if(active>=0&&!list.hidden){submit(options[active]);return;}
      // No implicit first partial match: the server reuses exact names atomically.
      if(form.dataset.canCreate==='true'){submit({name:typed});return;}
      const exact=options.find(option=>option.exact);
      if(exact)submit(exact);else feedback.textContent='Select an existing tag. Your role cannot create tags.';
    });
  });
  const drawer=document.querySelector('#tag-filter-drawer');
  if(!drawer)return;
  const toggleButtons=document.querySelectorAll('[data-filter-toggle]');
  const toggle=()=>{drawer.hidden=!drawer.hidden;toggleButtons.forEach(button=>button.setAttribute('aria-expanded',String(!drawer.hidden)));if(!drawer.hidden)drawer.querySelector('input:not([type=hidden])')?.focus();else toggleButtons[0]?.focus();};
  toggleButtons.forEach(button=>button.addEventListener('click',toggle));
  drawer.addEventListener('keydown',event=>{if(event.key==='Escape'&&!drawer.hidden){event.preventDefault();toggle();}});
  const form=drawer.querySelector('form'),input=form.querySelector('[data-filter-search]'),list=form.querySelector('[data-filter-tags]'),feedback=form.querySelector('[role=status]');
  const selected=new Set(JSON.parse(form.dataset.selected)),cache=new Map(Object.entries(JSON.parse(form.dataset.labels)).map(([id,name])=>[Number(id),{id:Number(id),name}]));let controller,timer,revision=0;
  const fields=()=>{form.querySelectorAll('input[data-tag-id]').forEach(field=>field.remove());for(const id of selected){const field=document.createElement('input');field.type='hidden';field.name='tag';field.value=id;field.dataset.tagId=id;form.append(field);}};
  const load=async()=>{
    const version=++revision;controller?.abort();controller=new AbortController();
    try{
      const tags=await search(input.value,controller.signal);if(version!==revision)return;
      tags.forEach(tag=>cache.set(tag.id,tag));
      const rows=[...selected].map(id=>cache.get(id)||{id,name:`Selected tag #${id}`}).concat(tags.filter(tag=>!selected.has(tag.id)));
      list.replaceChildren();for(const tag of rows){const label=document.createElement('label'),checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=selected.has(tag.id);checkbox.addEventListener('change',()=>{checkbox.checked?selected.add(tag.id):selected.delete(tag.id);fields();});label.append(checkbox,document.createTextNode(tag.name));list.append(label);}feedback.textContent=tags.length===100?'Showing 100 matches. Narrow your search.':'';fields();
    }catch(error){if(error.name!=='AbortError')feedback.textContent=error.message;}
  };
  input.addEventListener('input',()=>{revision++;controller?.abort();clearTimeout(timer);timer=setTimeout(load,120);});
  form.querySelector('[data-clear-tags]').addEventListener('click',()=>{selected.clear();fields();input.value='';form.querySelector('[name=match]').value='any';form.requestSubmit();});
  fields();load();
})();
