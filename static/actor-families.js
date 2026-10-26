(() => {
 const entry=document.querySelector('[data-actor-family-entry]');if(!entry)return;
 const input=entry.querySelector('[role=combobox]'), list=entry.querySelector('[role=listbox]'), chips=entry.querySelector('.family-aliases'), status=entry.querySelector('[role=status]');
 let timer,controller,revision=0,active=-1,options=[];
 const selected=()=>[...chips.querySelectorAll('input')].map(el=>el.value);
 const close=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;};
 function add(item){
  if(selected().includes(item.id)){status.textContent='This family is already selected.';return;}
  if(selected().length>=100){status.textContent='Choose at most 100 families.';return;}
  const chip=document.createElement('span');chip.className='tag-chip actor-family-chip';const label=document.createElement('span');label.textContent=`${item.name} · ${item.tag}`;
  const hidden=document.createElement('input');hidden.type='hidden';hidden.name='known_families';hidden.value=item.id;
  const remove=document.createElement('button');remove.type='button';remove.dataset.removeFamily='';remove.setAttribute('aria-label',`Remove family ${item.name}`);remove.textContent='×';chip.append(label,hidden,remove);chips.append(chip);input.value='';close();input.focus();status.textContent=`Added ${item.name}.`;
 }
 async function load(){const version=++revision;controller?.abort();controller=new AbortController();try{
  const response=await fetch(entry.dataset.searchUrl+'?q='+encodeURIComponent(input.value),{signal:controller.signal});if(!response.ok)throw Error('Unable to load families. Retry your search.');
  const data=await response.json();if(version!==revision)return;options=data.families.filter(item=>!selected().includes(item.id));list.replaceChildren();active=-1;
  options.forEach((item,index)=>{const row=document.createElement('li');row.id=`actor-family-option-${index}`;row.setAttribute('role','option');row.setAttribute('aria-selected','false');row.textContent=`${item.name} · ${item.tag}`;row.addEventListener('mousedown',e=>e.preventDefault());row.addEventListener('click',()=>add(item));list.append(row);});
  list.hidden=!options.length;input.setAttribute('aria-expanded',String(!!options.length));status.textContent=options.length?'Select a family. Showing up to 50 matches; refine your search.':'No matching configured families.';
 }catch(error){if(error.name!=='AbortError'){status.textContent=error.message;close();}}}
 input.addEventListener('input',()=>{revision++;controller?.abort();close();clearTimeout(timer);status.textContent='Loading families…';timer=setTimeout(load,150);});input.addEventListener('focus',load);input.addEventListener('blur',()=>setTimeout(close,150));
 input.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}if(event.key==='Enter'){event.preventDefault();if(active>=0&&!list.hidden)add(options[active]);else status.textContent='Select a configured family from the list.';}if(['ArrowDown','ArrowUp'].includes(event.key)&&options.length){event.preventDefault();list.hidden=false;input.setAttribute('aria-expanded','true');active=event.key==='ArrowDown'?(active+1)%options.length:(active<=0?options.length-1:active-1);[...list.children].forEach((el,i)=>el.setAttribute('aria-selected',String(i===active)));input.setAttribute('aria-activedescendant',list.children[active].id);list.children[active].scrollIntoView({block:'nearest'});}});
 chips.addEventListener('click',event=>{const button=event.target.closest('[data-remove-family]');if(!button)return;button.closest('.actor-family-chip').remove();input.focus();status.textContent='Association removed.';});
})();
