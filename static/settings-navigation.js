(() => {
  'use strict';
  const dropdowns=[];
  document.querySelectorAll('.dropdown-navigation').forEach(group=>{
    const toggle=group.querySelector('.dropdown-navigation-toggle'),menu=document.getElementById(toggle.getAttribute('aria-controls'));
    let hovering=false,ignoreHover=false,pinned=false;
    const open=value=>{
      menu.hidden=!value;toggle.setAttribute('aria-expanded',String(value));
      if(value){dropdowns.forEach(other=>{if(other.group!==group)other.dismiss();});menu.style.transform='';const bounds=menu.getBoundingClientRect();const delta=Math.max(8-bounds.left,Math.min(0,innerWidth-8-bounds.right));menu.style.transform=`translateX(${delta}px)`;}
    };
    const dismiss=()=>{pinned=false;open(false);};
    dropdowns.push({group,dismiss});
    group.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse'){hovering=true;if(!ignoreHover)open(true);}});
    group.addEventListener('pointerleave',()=>{hovering=false;ignoreHover=false;if(!pinned&&!group.contains(document.activeElement))open(false);});
    toggle.onclick=()=>{
      if(menu.hidden){pinned=true;open(true);}else dismiss();
    };
    window.addEventListener('resize',()=>{if(!menu.hidden)open(true);});
    group.addEventListener('focusout',()=>setTimeout(()=>{if(!hovering&&!pinned&&!group.contains(document.activeElement))open(false);},0));
    group.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&!menu.hidden){event.preventDefault();dismiss();ignoreHover=hovering;toggle.focus();}
      if(event.key==='ArrowDown'&&event.target===toggle){event.preventDefault();open(true);menu.querySelector('a')?.focus();}
    });
    document.addEventListener('pointerdown',event=>{if(!group.contains(event.target))dismiss();});
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&!event.defaultPrevented&&!menu.hidden&&!document.querySelector('dialog[open]')) {
        event.preventDefault();dismiss();ignoreHover=hovering;toggle.focus();
      }
    });
  });
  const shell=document.querySelector('.settings-shell'),dialog=document.getElementById('settings-unsaved');
  if(!shell||!dialog)return;
  const forms=[...shell.querySelectorAll('form')].filter(form=>form.method.toLowerCase()==='post');
  function fingerprint(form) {
    return JSON.stringify([...new FormData(form)].filter(([key])=>key!=='settings_next').map(([key,value])=>[key,value instanceof File?[value.name,value.size,value.name?value.lastModified:0]:value]));
  }
  const initial=new Map(forms.map(form=>[form,fingerprint(form)]));
  const dirty=()=>forms.filter(form=>fingerprint(form)!==initial.get(form));
  let leaving=false,destination=null,submission=null;
  function review(url,form=null) {
    destination=url;submission=form;
    const changed=dirty();const save=dialog.querySelector('[data-settings-choice=save]');
    save.disabled=changed.length!==1;
    document.getElementById('settings-unsaved-message').textContent=changed.length>1?'Several forms have unsaved changes. Cancel to review them, or explicitly discard changes before continuing.':'Save your changes before leaving this category?';
    dialog.showModal();
  }
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');
    if(!link||event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download')||!dirty().length)return;
    if(link.href===location.href||link.getAttribute('href').startsWith('#'))return;
    event.preventDefault();review(link.href);
  });
  forms.forEach(form=>form.addEventListener('submit',event=>{
    if(leaving)return;
    if(dirty().some(other=>other!==form)){event.preventDefault();review(null,form);return;}
    leaving=true;
  }));
  window.addEventListener('beforeunload',event=>{if(!leaving&&dirty().length){event.preventDefault();event.returnValue='';}});
  dialog.querySelectorAll('[data-settings-choice]').forEach(button=>button.onclick=()=>{
    const choice=button.dataset.settingsChoice;
    dialog.close();if(choice==='cancel')return;
    if(choice==='discard') {
      leaving=true;
      if(submission)submission.requestSubmit();else location.assign(destination);
    } else {
      const form=dirty()[0];if(!form)return;
      if(!form.reportValidity())return;
      const target=new URL(destination||location.href);
      const next=document.createElement('input');next.type='hidden';next.name='settings_next';next.value=target.pathname+target.search+target.hash;form.append(next);
      form.requestSubmit();
    }
  });
})();
