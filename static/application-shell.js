(() => {
 const body=document.body,sidebar=document.getElementById('application-sidebar');if(!sidebar)return;
 const key='mare-shell:'+body.dataset.userLayout,menu=document.getElementById('sidebar-menu'),backdrop=document.getElementById('sidebar-backdrop'),collapse=document.getElementById('sidebar-collapse');let preferences={};
 try{preferences=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
 const save=()=>{try{localStorage.setItem(key,JSON.stringify(preferences));}catch{}};
 function drawer(open){body.classList.toggle('sidebar-drawer-open',open);backdrop.hidden=!open;menu.setAttribute('aria-expanded',String(open));if(open)sidebar.querySelector('a').focus();else menu.focus();}
 function collapsed(value){body.classList.toggle('sidebar-collapsed',value);collapse.setAttribute('aria-expanded',String(!value));collapse.setAttribute('aria-label',value?'Expand sidebar':'Collapse sidebar');collapse.querySelector('[aria-hidden]').textContent=value?'⇥':'⇤';preferences.collapsed=value;save();}
 collapsed(Boolean(preferences.collapsed));collapse.onclick=()=>collapsed(!body.classList.contains('sidebar-collapsed'));
 for(const toggle of sidebar.querySelectorAll('[data-group]')){const panel=document.getElementById(toggle.getAttribute('aria-controls')),name=toggle.dataset.group;let open=toggle.getAttribute('aria-expanded')==='true'||Boolean(preferences.groups?.[name]);const set=value=>{panel.hidden=!value;toggle.setAttribute('aria-expanded',String(value));};set(open);toggle.onclick=()=>{open=panel.hidden;set(open);preferences.groups={...preferences.groups,[name]:open};save();};}
 menu.onclick=()=>drawer(!body.classList.contains('sidebar-drawer-open'));backdrop.onclick=()=>drawer(false);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&body.classList.contains('sidebar-drawer-open')){event.preventDefault();drawer(false);}if(event.key==='Tab'&&body.classList.contains('sidebar-drawer-open')){const nodes=[...sidebar.querySelectorAll('a,button')].filter(n=>n.getClientRects().length);if(event.shiftKey&&document.activeElement===nodes[0]){event.preventDefault();nodes.at(-1).focus();}else if(!event.shiftKey&&document.activeElement===nodes.at(-1)){event.preventDefault();nodes[0].focus();}}});
 matchMedia('(min-width:901px)').addEventListener('change',event=>{if(event.matches){body.classList.remove('sidebar-drawer-open');backdrop.hidden=true;menu.setAttribute('aria-expanded','false');}});
})();
