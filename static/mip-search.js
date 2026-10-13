(() => {
  const form=document.getElementById('mip-search-form'); if(!form)return;
  const results=document.getElementById('mip-search-results'),status=document.getElementById('search-status'),pagination=document.getElementById('search-pagination');
  const expandAll=document.getElementById('search-expand-all'),collapseAll=document.getElementById('search-collapse-all');
  function setExpanded(button,expanded){
    const content=document.getElementById(button.getAttribute('aria-controls'));
    content.hidden=!expanded;
    button.setAttribute('aria-expanded',String(expanded));
    button.setAttribute('aria-label',`${expanded?'Collapse':'Expand'} results for ${button.dataset.caseLabel}`);
    button.querySelector('span').textContent=expanded?'▾':'▸';
  }
  function updateFoldControls(){expandAll.disabled=collapseAll.disabled=!results.querySelector('.search-group-toggle');}
  results.addEventListener('click',event=>{const button=event.target.closest('.search-group-toggle');if(button&&results.contains(button))setExpanded(button,button.getAttribute('aria-expanded')!=='true');});
  for(const [button,expanded] of [[expandAll,true],[collapseAll,false]])button.addEventListener('click',()=>{for(const toggle of results.querySelectorAll('.search-group-toggle'))setExpanded(toggle,expanded);});
  let generation=0,timer,controller,params;
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  function link(text,url,button=false){const a=el('a',text);a.href=url;if(button)a.className='button-secondary';return a;}
  function render(data){
    results.replaceChildren();pagination.replaceChildren();
    const indexing=data.status.state==='indexing'||data.status.state==='pending';
    status.textContent=`${data.packages} matching packages · ${data.artifacts} matching artifacts. ${indexing?'Indexing in progress; results are incomplete.':data.status.state==='error'?data.status.error:data.packages?'':'No matching results.'}`;
    if(data.status.partial||data.partial)status.textContent+=' '+(data.partial||data.status.partial);
    document.getElementById('search-coverage').textContent=`${data.status.documents||0} indexed records/artifacts · ${data.status.files||0} files · ${data.status.archives||0} retained archives · ${data.status.skipped_total||0} skipped/partial files (up to 500 shown). ${data.status.updated?'Last refresh: '+new Date(data.status.updated*1000).toLocaleString():''}`;
    const skipped=document.getElementById('search-skipped');skipped.replaceChildren();
    for(const item of data.status.skipped||[])skipped.append(el('li',`${item.path}: ${item.reason}`));
    for(const [index,group] of data.groups.entries()){
      const panel=el('section');panel.className='panel mip-search';const c=group.case;
      const header=el('div');header.className='search-group-header';
      const toggle=el('button');toggle.type='button';toggle.className='search-group-toggle';toggle.dataset.caseLabel=c?.number||group.archive_case?.number||group.title||'Unknown case';
      const icon=el('span');icon.setAttribute('aria-hidden','true');toggle.append(icon);toggle.setAttribute('aria-controls',`search-group-content-${index}`);
      header.append(toggle,el('h2',c?`${c.number}${c.external_number?' · '+c.external_number:''} — ${c.name}`:`Unassociated archive — ${group.archive_case?.number||'Unknown case'}${group.archive_case?.external_number?' · '+group.archive_case.external_number:''} — ${group.archive_case?.name||group.title}`));panel.append(header);
      const summary=el('p',`${c?form.elements.stage.options[Number(c.stage)+1]?.textContent+' · ':'Current stage unavailable · '}${group.artifact_total} matching artifacts${group.limited?' (first 200 shown; narrow your search)':''}`);
      if(c){summary.append(document.createTextNode(' · '),link('Open case',`/cases/${c.id}`,true));} panel.append(summary);
      const wrapper=el('div');wrapper.className='search-table-wrap';wrapper.id=toggle.getAttribute('aria-controls');const table=el('table');table.className='search-result-table';
      const head=el('thead'),hr=el('tr');for(const title of ['Artifact / field','Data type','Source','Match location','Matching excerpt','Finding'])hr.append(el('th',title));head.append(hr);table.append(head);
      const body=el('tbody');
      for(const finding of group.findings){
        const row=el('tr');row.append(el('td',finding.label),el('td',finding.type),el('td',`${finding.source==='archive'?'Stored archive':'Current workspace'}${finding.source==='archive'?' — '+finding.version:''}`),el('td',`${finding.count} matches · ${finding.excerpts.map(e=>e.location).join(', ')}`));
        const cell=el('td');for(const excerpt of finding.excerpts){const p=el('p');for(const part of excerpt.parts)p.append(el(part.highlight?'mark':'span',part.text));cell.append(p);}if(finding.warning)cell.append(el('small',finding.warning));row.append(cell);
        const action=el('td');action.append(link('Open finding',`/search/findings/${finding.id}?`+params,true));row.append(action);body.append(row);
      }table.append(body);wrapper.append(table);panel.append(wrapper);results.append(panel);setExpanded(toggle,true);
    }
    updateFoldControls();
    if(data.pages>1){for(const [text,page] of [['Previous',data.page-1],['Next',data.page+1]]){const button=el('button',text);button.type='button';button.disabled=page<1||page>data.pages;button.onclick=()=>{params.set('page',page);search(generation);};pagination.append(button);}pagination.append(el('span',`Page ${data.page} of ${data.pages}`));}
    return indexing;
  }
  async function search(token){
    clearTimeout(timer);controller?.abort();controller=new AbortController();status.textContent='Searching…';
    try{const response=await fetch('/search/results?'+params,{signal:controller.signal,headers:{Accept:'application/json'}});if(!response.ok||!response.headers.get('content-type')?.includes('application/json'))throw Error('Search unavailable. Check your login and filters, then retry.');const data=await response.json();if(token!==generation)return;const indexing=render(data);if(indexing)timer=setTimeout(()=>search(token),1500);}
    catch(error){if(error.name!=='AbortError')status.textContent=error.message;}
  }
  form.addEventListener('submit',event=>{event.preventDefault();params=new URLSearchParams(new FormData(form));if(!params.get('q').trim()){status.textContent='Enter a search term.';return;}history.replaceState(null,'','/search?'+params);search(++generation);});
  form.addEventListener('reset',()=>{++generation;clearTimeout(timer);controller?.abort();results.replaceChildren();updateFoldControls();pagination.replaceChildren();status.textContent='Enter a search to inspect accessible packages.';history.replaceState(null,'','/search');});
  const initial=new URLSearchParams(location.search);for(const key of ['q','kind','source','stage']){const value=initial.get(key);if(value!==null)form.elements[key].value=value;}
  if(initial.get('q')?.trim()){params=new URLSearchParams(new FormData(form));if(initial.get('page'))params.set('page',initial.get('page'));search(++generation);}
})();
