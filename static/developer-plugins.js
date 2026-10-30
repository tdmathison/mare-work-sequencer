(() => {
  const root=document.querySelector('[data-plugin-management]');if(!root)return;
  const layout=window.MarePluginLayout(root),base=root.dataset.base,csrf=root.dataset.csrf,q=s=>root.querySelector(s),status=q('[data-management-status]');
  let rows=[],permissions=[],selected=null,detail=null,selection=0,busy=false,filter='all',tab='overview',configurationDirty=false,tabGeneration=0,historyIndex=Number.isInteger(history.state?.marePlugins?.index)?history.state.marePlugins.index:0,restoringHistory=false;
  const element=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
  const describe=value=>value===undefined||value===null||value===''||Array.isArray(value)&&!value.length?'Not specified':typeof value==='string'?value:JSON.stringify(value,null,2);
  async function api(path='',data){const options={credentials:'same-origin',cache:'no-store'};if(data!==undefined){const form=new FormData();form.set('csrf',csrf);form.set('payload',JSON.stringify(data));options.method='POST';options.body=form;}const response=await fetch(path==='@discovery'?'/plugins/discovery':base+path,options);if(!response.ok){const raw=await response.text();let message;try{message=JSON.parse(raw).error;}catch{}throw Error(message||new DOMParser().parseFromString(raw,'text/html').querySelector('p')?.textContent||response.statusText);}return response.json();}
  let menu=null,menuGeneration=0,menuPlugin=null;
  const fail=error=>{status.textContent=error.message;};
  function leave(){if(!configurationDirty)return true;if(!confirm('Discard unsaved configuration changes?'))return false;configurationDirty=false;return true;}
  function matches(row,type){return type==='all'||type==='errors'&&!row.package_valid||type==='enabled'&&!!row.enabled||type==='disabled'&&!row.enabled;}
  function renderList(){
    const list=q('[data-installed-plugins]'),query=q('[data-plugin-search]').value.trim().toLocaleLowerCase();list.replaceChildren();
    for(const button of root.querySelectorAll('[data-plugin-filter]')){button.setAttribute('aria-pressed',String(button.dataset.pluginFilter===filter));button.querySelector('small').textContent=rows.filter(row=>matches(row,button.dataset.pluginFilter)).length;}
    const visible=rows.filter(row=>matches(row,filter)&&[row.name,row.id,row.manifest?.description].some(value=>value?.toLocaleLowerCase().includes(query)));
    for(const row of visible){const value=row.manifest||{},button=element('button',undefined,'plugin-list-entry');button.type='button';button.disabled=busy;button.setAttribute('aria-current',String(row.id===selected));button.dataset.pluginId=row.id;button.setAttribute('aria-haspopup','menu');button.oncontextmenu=event=>contextMenu(event,row.id);button.onkeydown=event=>{if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10'){const bounds=button.getBoundingClientRect();contextMenu({preventDefault:()=>event.preventDefault(),clientX:bounds.left+20,clientY:bounds.bottom},row.id);}};
      const title=element('span');title.dataset.rowTitle='';title.append(element('strong',value.name||row.name),element('small',value.version||'Version not specified'));
      const description=element('span',value.description||'No description specified');description.dataset.rowDescription='';description.title=value.description||'';
      button.append(title,description,element('small',(!row.package_valid?'Error · ':'')+(row.enabled?'Enabled':'Disabled')));button.onclick=()=>{closeMenu(false);if(!busy&&leave())select(row.id,true).catch(fail);};list.append(button);
    }
    if(!visible.length)list.append(element('p',rows.length?'No plugins match these filters.':'No plugins installed. Install a package in the configured plugin directory.'));
  }
  function section(title,items){const container=element('section'),heading=element('h3',title),list=element('dl');for(const [label,value] of items)list.append(element('dt',label),element('dd',describe(value)));container.append(heading,list);return container;}
  function updateHeader(){const value=detail.manifest||{};q('[data-management-empty]').hidden=true;q('[data-plugin-details]').hidden=false;q('[data-detail-name]').textContent=value.name||detail.name;q('[data-detail-name]').title=value.name||detail.name;q('[data-detail-byline]').textContent=[value.version,value.author,detail.enabled?'Enabled':'Disabled',detail.validation.valid?null:'Invalid package'].filter(Boolean).join(' · ');q('[data-detail-description]').textContent=value.description||'No description specified';
    const enable=q('[data-enable]'),disable=q('[data-disable]');enable.hidden=!!detail.enabled;disable.hidden=!detail.enabled;enable.disabled=busy||!detail.validation.valid||!permissions.includes('versions');disable.disabled=busy||!permissions.includes('versions');
  }
  async function renderTab(){
    const generation=selection,renderToken=++tabGeneration,pid=selected,panel=q('[data-plugin-metadata]'),value=detail.manifest||{},requested=detail.requested_permissions||[];configurationDirty=false;panel.replaceChildren();panel.scrollTop=0;panel.setAttribute('aria-labelledby','plugin-tab-'+tab);
    window.MwsTabs.setActive(q('.plugin-detail-tabs'),'plugin-tab-'+tab);
    if(tab==='overview')panel.append(section('Package',[['Name',value.name||detail.name],['Identifier',detail.id],['Description',value.description],['Version',value.version],['Author',value.author],['Entry point',value.entrypoint],['Package location',detail.location],['Declared capabilities',value.capabilities]]),section('Validation & compatibility',[['Manifest validation',detail.validation.valid?'Valid':'Invalid'],['SDK version',value.sdk_version],['API version',value.api_version],['Compatibility',detail.compatibility.status+' · '+detail.compatibility.definition],['Registration / validation errors',detail.validation.diagnostics.map(item=>item.message)]]));
    else if(tab==='permissions'){
      panel.append(element('p','Declarations do not grant access. Runtime access is limited by your current application permissions, the manifest, and execution mode.'));
      panel.append(section('REST API scopes',[['Declared read scopes',requested.filter(p=>p.endsWith(':read'))],['Declared write / other scopes',requested.filter(p=>!p.endsWith(':read'))],['Currently authorized scopes',detail.granted_permissions],['Not authorized for your account',requested.filter(p=>!detail.granted_permissions.includes(p))]]),section('Capabilities & network',[['Capabilities',value.capabilities],['External API requirements',value.external_api],['Network requirements',value.network],['Runtime network policy','Containers have no direct network access. Approved connectors are available only to authorized operational runs.']]));
    }else if(tab==='dependencies')panel.append(section('Requirements',[['Python version',value.python_version],['MWS SDK',value.sdk_version],['MWS API',value.api_version],['Python dependencies',value.dependencies],['Compatibility',detail.compatibility.status+' · '+detail.compatibility.definition],['Dependency / validation errors',detail.validation.diagnostics.map(item=>item.message)]]),element('p','Opening this tab does not install dependencies. A worker administrator must review dependencies and rebuild the approved image.'));
    else if(tab==='configuration'){
      const fields=value.configuration||{};if(!Object.keys(fields).length){panel.append(element('p','This plugin declares no configuration settings.'));return;}
      if(!permissions.includes('configure')){panel.append(section('Declared configuration',Object.entries(fields).map(([name,field])=>[name,field.type+(field.secret?' · secret':'')])) ,element('p','Configuration access requires plugins:configure.'));return;}
      panel.append(element('p','Loading configuration…'));try{const data=await api('/'+pid+'/configuration');if(generation!==selection||renderToken!==tabGeneration||tab!=='configuration')return;renderConfiguration(data);}catch(error){if(generation===selection&&renderToken===tabGeneration&&tab==='configuration')panel.replaceChildren(element('p',error.message));}
    }else if(tab==='activity'){
      panel.append(element('p','Loading activity…'));try{const data=await api('/'+pid+'/history');if(generation!==selection||renderToken!==tabGeneration||tab!=='activity')return;panel.replaceChildren();if(!data.executions.length){panel.append(element('p','No execution activity yet.'));return;}
        const table=element('table'),head=element('thead'),row=element('tr'),body=element('tbody');for(const label of ['Started','Status / mode','Duration','Initiated by','Error']){const cell=element('th',label);cell.scope='col';row.append(cell);}head.append(row);for(const run of data.executions){const tr=element('tr');for(const text of [run.started_at,run.status+' · '+run.mode,run.duration===null?'In progress':run.duration+'s',run.initiating_user||run.owner_uuid,run.error_summary||'—'])tr.append(element('td',text));body.append(tr);}table.append(head,body);panel.append(table);
      }catch(error){if(generation===selection&&renderToken===tabGeneration&&tab==='activity')panel.replaceChildren(element('p',error.message));}
    }
  }
  function renderConfiguration(data){
    const panel=q('[data-plugin-metadata]'),form=element('form',undefined,'plugin-configuration'),inputs=new Map();panel.replaceChildren(form);
    for(const [name,field] of Object.entries(data.schema)){
      const label=element('label',name+(field.required?' *':''));let input;
      if(field.enum||field.secret&&field.type==='boolean'){input=element('select');input.append(new Option(field.secret?'Leave unchanged':'Choose a value',''));for(const value of field.enum||[true,false])input.add(new Option(String(value),JSON.stringify(value)));if(!field.secret&&name in data.values)input.value=JSON.stringify(data.values[name]);}
      else{input=element('input');input.type=field.secret?'password':field.type==='boolean'?'checkbox':field.type==='number'?'number':'text';if(field.type==='number'&&!field.secret)input.step='any';if(!field.secret){if(field.type==='boolean')input.checked=!!data.values[name];else input.value=data.values[name]??'';}}
      input.name=name;input.autocomplete='off';input.required=!!field.required&&!field.secret&&field.type!=='boolean';label.append(input);if(field.description)label.append(element('small',field.description));
      let clear;if(field.secret){label.append(element('small',data.configured_secrets.includes(name)?'Secret configured; stored value is never displayed.':'No stored secret. Leave blank to preserve the existing value.'));const clearLabel=element('span',undefined,'secret-clear');clear=element('input');clear.type='checkbox';clear.setAttribute('aria-label','Clear secret '+name);clearLabel.append(clear,document.createTextNode('Clear stored secret'));label.append(clearLabel);}
      form.append(label);inputs.set(name,{input,clear,field});
    }
    const actions=element('div',undefined,'dialog-actions'),save=element('button','Save configuration'),reset=element('button','Reset changes'),notice=element('p');notice.setAttribute('role','status');save.type='submit';reset.type='button';reset.onclick=()=>{configurationDirty=false;renderConfiguration(data);};actions.append(reset,save);form.append(actions,notice);form.oninput=()=>configurationDirty=true;form.onchange=()=>configurationDirty=true;
    form.onsubmit=async event=>{event.preventDefault();const payload={values:{},secrets:{},clear_secrets:[]};try{for(const [name,{input,clear,field}] of inputs){if(clear?.checked){payload.clear_secrets.push(name);continue;}let value;if(field.type==='boolean'&&!field.secret&&!field.enum)value=input.checked;else if(input.tagName==='SELECT'){if(!input.value)continue;value=JSON.parse(input.value);}else{if(field.secret&&!input.value)continue;if(field.type==='number'){if(!input.value)continue;value=Number(input.value);}else if(field.type==='boolean'){if(!['true','false'].includes(input.value))throw Error(name+' must be true or false');value=input.value==='true';}else value=input.value;}payload[field.secret?'secrets':'values'][name]=value;}
      save.disabled=true;const pid=selected,generation=selection,renderToken=tabGeneration,result=await api('/'+pid+'/configuration',payload);if(generation!==selection||renderToken!==tabGeneration)return;configurationDirty=false;renderConfiguration(result);status.textContent='Configuration saved.';
    }catch(error){notice.textContent=error.message;}finally{save.disabled=false;}};
  }
  async function select(id,push=false){const generation=++selection,result=await api('/'+id);if(selection!==generation)return;selected=id;detail=result;layout.save({lastPlugin:id});const url=new URL(location.href);url.searchParams.set('plugin',id);if(push)history.pushState({marePlugins:{id,index:++historyIndex}},'',url);else history.replaceState({...history.state,marePlugins:{id,index:historyIndex}},'',url);updateHeader();renderList();await renderTab();status.textContent=detail.validation.valid?'Manifest loaded.':'Invalid package; repair the installed package and rescan. The installed version has not been reloaded.';}
  async function refresh(){closeMenu(false);if(!leave())return;status.textContent='Discovering plugins…';let discovery;try{discovery=await api('@discovery',{});}catch(error){discovery={invalid:[{package:'plugins',error:error.message}]};}const data=await api('?management=1');rows=data.plugins;permissions=data.permissions;const errors=q('[data-discovery-errors]');errors.hidden=!discovery.invalid.length;errors.querySelector('ul').replaceChildren(...discovery.invalid.map(item=>element('li',item.package+': '+item.error)));renderList();const wanted=new URL(location.href).searchParams.get('plugin')||selected||layout.prefs.lastPlugin;const id=rows.find(row=>row.id===wanted)?.id||rows[0]?.id;if(id)await select(id);else{selected=null;detail=null;++selection;layout.save({lastPlugin:null});const url=new URL(location.href);url.searchParams.delete('plugin');history.replaceState(history.state,'',url);q('[data-management-empty]').hidden=false;q('[data-plugin-details]').hidden=true;status.textContent='No installed plugins.';}}
  async function enable(enabled){if(busy||!detail||!leave())return;busy=true;const pid=selected,revision=detail.revision;updateHeader();renderList();try{await api('/'+pid+'/enable',{enabled});await refresh();status.textContent=enabled?'Plugin enabled.':'Plugin disabled. Existing executions continue on their original snapshot.';}catch(error){fail(error);}finally{busy=false;if(detail)updateHeader();renderList();}}
  function closeMenu(restore=true){++menuGeneration;if(menu){menu.remove();menu=null;if(restore)root.querySelector('[data-plugin-id="'+menuPlugin+'"]')?.focus();}menuPlugin=null;}
  async function contextMenu(event,pid){
    event.preventDefault();closeMenu(false);if(busy)return;
    const generation=menuGeneration;
    try{
      if(selected!==pid){if(!leave())return;await select(pid,true);}
      if(generation!==menuGeneration||selected!==pid||!detail)return;
      menuPlugin=pid;
      const current=detail,valid=current.validation.valid&&current.compatibility.status==='Compatible';
      const enableReason=!permissions.includes('versions')?'Requires plugin version management permission.':current.enabled?'Plugin is already enabled.':!valid?'Invalid or incompatible package. Repair the installed package and rescan.':!current.published_version?'Install a valid package first.':'';
      const choices=[
        ['Enable','✓',enableReason,()=>enable(true)],
        ['Disable','⊘',!permissions.includes('versions')?'Requires plugin version management permission.':!current.enabled?'Plugin is already disabled.':'',()=>enable(false)],
        ['Delete','×',current.protected?'Protected or built-in plugins cannot be deleted.':!permissions.includes('delete')?'Requires plugin deletion permission.':'',()=>confirmDelete(current)],
      ];
      menu=element('div',undefined,'plugin-context-menu');menu.setAttribute('role','menu');menu.setAttribute('aria-label','Plugin actions');menu.tabIndex=-1;
      for(const [name,icon,reason,action] of choices){
        if(name==='Delete'){const separator=element('div',undefined,'plugin-menu-separator');separator.setAttribute('role','separator');menu.append(separator);}
        const button=element('button');button.type='button';button.setAttribute('role','menuitem');button.setAttribute('aria-label',name);button.dataset.pluginAction=name.toLowerCase();button.disabled=!!reason;button.title=reason;button.setAttribute('aria-disabled',String(!!reason));
        const glyph=element('span',icon,'plugin-menu-icon');glyph.setAttribute('aria-hidden','true');button.append(glyph,document.createTextNode(name));
        button.onclick=()=>{closeMenu();if(selected!==pid)return;Promise.resolve().then(action).catch(fail);};menu.append(button);
      }
      const explanation=choices.find(([name,,reason])=>name==='Enable'&&reason&&!current.enabled)?.[2];if(explanation){const note=element('p',explanation,'plugin-menu-explanation');note.id='plugin-menu-explanation';menu.append(note);menu.querySelector('[data-plugin-action=enable]').setAttribute('aria-describedby',note.id);}
      document.body.append(menu);const bounds=menu.getBoundingClientRect();menu.style.left=Math.max(4,Math.min(event.clientX,innerWidth-bounds.width-4))+'px';menu.style.top=Math.max(4,Math.min(event.clientY,innerHeight-bounds.height-4))+'px';(menu.querySelector('button:not(:disabled)')||menu).focus();
      menu.onkeydown=e=>{const buttons=[...menu.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(document.activeElement);if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}else if(e.key==='Escape'||e.key==='Tab'){e.preventDefault();closeMenu();}};
    }catch(error){if(generation===menuGeneration)fail(error);}
  }
  document.addEventListener('pointerdown',event=>{if(!menu?.contains(event.target))closeMenu(false);});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
  window.addEventListener('resize',()=>closeMenu(false));
  const deleteDialog=document.getElementById('plugin-delete');let deletion=null;
  function confirmDelete(plugin){if(busy||!permissions.includes('delete')||plugin.protected||!leave())return;deletion={id:plugin.id,revision:plugin.revision,name:plugin.manifest?.name||plugin.name};deleteDialog.querySelector('[data-delete-title]').textContent='Delete plugin "'+deletion.name+'"?';deleteDialog.querySelector('[data-delete-error]').textContent='';deleteDialog.showModal();deleteDialog.querySelector('[data-delete-cancel]').focus();}
  deleteDialog.querySelector('[data-delete-cancel]').onclick=()=>deleteDialog.close();
  deleteDialog.querySelector('form').onsubmit=async event=>{event.preventDefault();if(!deletion||busy)return;const target=deletion,submit=deleteDialog.querySelector('[type=submit]');busy=true;submit.disabled=true;
    try{await api('/'+target.id+'/delete',{revision:target.revision});deleteDialog.close();configurationDirty=false;selected=null;detail=null;const url=new URL(location.href);url.searchParams.delete('plugin');history.replaceState(history.state,'',url);layout.save({lastPlugin:null});await refresh();status.textContent='Plugin "'+target.name+'" deleted. Its package and registry snapshot are retained for recovery.';}
    catch(error){deleteDialog.querySelector('[data-delete-error]').textContent=error.message;fail(error);}
    finally{busy=false;submit.disabled=false;if(detail)updateHeader();renderList();}
  };
  q('[data-enable]').onclick=()=>enable(true);q('[data-disable]').onclick=()=>enable(false);q('[data-plugin-refresh]').onclick=()=>{if(!busy)refresh().catch(fail);};q('[data-plugin-search]').oninput=()=>{closeMenu(false);renderList();};
  for(const button of root.querySelectorAll('[data-plugin-filter]'))button.onclick=()=>{closeMenu(false);filter=button.dataset.pluginFilter;renderList();};
  async function changeTab(button){if(leave()){tab=button.dataset.detailTab;await renderTab();}}
  window.MwsTabs.bind(q('.plugin-detail-tabs'),button=>changeTab(button).catch(fail));
  window.addEventListener('popstate',async event=>{if(restoringHistory){restoringHistory=false;return;}const state=event.state?.marePlugins;if(!state)return;const delta=state.index-historyIndex;if(leave()){historyIndex=state.index;select(state.id).catch(fail);}else if(delta){restoringHistory=true;history.go(-delta);}});
  window.addEventListener('pageshow',event=>{if(event.persisted&&!busy&&!configurationDirty)refresh().catch(fail);});document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy&&!configurationDirty)refresh().catch(fail);});
  window.addEventListener('beforeunload',event=>{if(configurationDirty){event.preventDefault();event.returnValue='';}});document.addEventListener('click',event=>{if(event.target.closest('a[href]')&&configurationDirty&&!leave())event.preventDefault();});
  refresh().catch(fail);
})();
