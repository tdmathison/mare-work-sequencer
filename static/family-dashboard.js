/* Public wall display: snapshot refresh, workload paging and 20px/s strip motion
   have independent lifecycles, following the Cases dashboard components. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let zone='UTC', snapshot=null, stopped=false, busy=false, pending=null, serial=0;
  let controller, refreshTimer, rotationTimer, frame, lastSuccess=null;
  let page=0, pages=1, libraryPage=0, libraryPages=1, rotationPaused=false;
  function node(tag, cls, text) {
    const el=document.createElement(tag);if(cls)el.className=cls;
    if(text!==undefined)el.textContent=text;return el;
  }
  function date(value) {
    const parsed=new Date(value);
    return value && Number.isFinite(parsed.getTime()) ? new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeZone:zone}).format(parsed) : null;
  }
  function reconcile(host,value,build) {
    const key=JSON.stringify([zone,value]);if(host.dataset.snapshot===key)return false;
    host.replaceChildren(...build());host.dataset.snapshot=key;return true;
  }
  function card(item,kind) {
    const el=node('article',kind);
    el.append(node(kind==='spotlight-content'?'h2':'h3','',item.name),node('span','family-tag',item.tag));
    el.querySelector('.family-tag').title=item.tag;el.querySelector('h2,h3').title=item.name;
    if(kind!=='completed-card')el.append(node('p','case-description',item.short_description||'No short description provided.'));
    if(kind==='spotlight-content') {
      const metrics=node('div','focus-metrics');
      for(const [key,label] of [['linked_cases','Linked cases'],['in_progress','In progress'],['osint_links','OSINT links'],['reports_collected','Reports collected']]) {
        const value=node('div');value.append(node('strong','',item[key]),node('span','',label));metrics.append(value);
      }
      el.append(metrics);
    } else el.append(node('p','family-counts',kind==='active-card'?`${item.in_progress} in progress · ${item.linked_cases} linked cases`:`${item.linked_cases} linked cases · ${item.reports_collected} reports`));
    if(kind!=='completed-card' && date(item.updated_at))el.append(node('p','case-date','Profile updated '+date(item.updated_at)));
    return el;
  }
  class FamilyStrip {
    constructor() {
      this.viewport=document.querySelector('.strip-viewport');this.track=document.querySelector('.strip-track');this.group=$('tracked');
      this.paused=false;this.offset=0;this.last=0;this.width=0;this.moving=false;
      this.observer=new ResizeObserver(()=>this.measure());
      $('strip-pause').onclick=()=>{this.paused=!this.paused;this.controls();};
      this.viewport.onkeydown=event=>{
        if(this.moving&&['ArrowLeft','ArrowRight'].includes(event.key)) {
          event.preventDefault();
          this.offset=(this.offset+(event.key==='ArrowRight'?296:-296)+this.width)%this.width;
          this.paint();
        }
      };
    }
    controls() {
      $('strip-pause').textContent=this.paused?'Resume scrolling':'Pause scrolling';
      $('strip-pause').setAttribute('aria-pressed',String(this.paused));$('strip-pause').disabled=!this.moving;
    }
    update(items,changedPage) {
      if(reconcile(this.group,items,()=>items.map(i=>card(i,'completed-card')))) {
        if(changedPage)this.offset=0;
        this.measure();
      }
      $('library-empty').hidden=items.length>0;
    }
    measure() {
      this.track.querySelectorAll('[data-copy]').forEach(el=>el.remove());
      this.width=this.group.getBoundingClientRect().width+16;
      this.moving=!reduced.matches && this.group.children.length>1 && this.width-16>this.viewport.clientWidth;
      if(this.moving) {
        const copy=this.group.cloneNode(true);copy.removeAttribute('id');copy.removeAttribute('data-snapshot');
        copy.dataset.copy='';copy.setAttribute('aria-hidden','true');copy.inert=true;this.track.append(copy);
        this.offset%=this.width;
      } else this.offset=0;
      this.viewport.style.overflowX=this.moving?'hidden':'auto';this.paint();this.controls();
    }
    paint(){this.track.style.transform=`translateX(${-this.offset}px)`;}
    tick(time) {
      const elapsed=this.last?Math.min(time-this.last,100):0;this.last=time;
      const section=document.querySelector('.completed-section');
      if(this.moving&&!this.paused&&!document.hidden&&!section.matches(':hover')&&!section.contains(document.activeElement)) {
        const next=this.offset+elapsed*.02;
        if(next>=this.width && libraryPages>1 && !busy)load(page,(libraryPage+1)%libraryPages);
        this.offset=next%this.width;this.paint();
      }
    }
  }
  const strip=new FamilyStrip();
  function pageControls() {
    const count=snapshot?.pagination.total||0;
    $('page-position').textContent=`${count} families · Page ${page+1} of ${pages} · ${reduced.matches?'Manual paging':'Rotates every 25 seconds'}`;
    $('previous').disabled=$('next').disabled=pages<=1;
    $('active-pause').disabled=pages<=1||reduced.matches;
    $('active-pause').textContent=rotationPaused?'Resume rotation':'Pause rotation';
    $('active-pause').setAttribute('aria-pressed',String(rotationPaused));
    $('library-position').textContent=`${snapshot?.library_pagination.total||0} tracked · Library page ${libraryPage+1} of ${libraryPages}`;
    $('library-previous').disabled=$('library-next').disabled=libraryPages<=1;
  }
  $('active-pause').onclick=()=>{rotationPaused=!rotationPaused;pageControls();};
  $('previous').onclick=()=>load((page-1+pages)%pages,libraryPage);
  $('next').onclick=()=>load((page+1)%pages,libraryPage);
  $('library-previous').onclick=()=>load(page,(libraryPage-1+libraryPages)%libraryPages);
  $('library-next').onclick=()=>load(page,(libraryPage+1)%libraryPages);
  function status(stale) {
    $('update-status').classList.toggle('stale',stale);
    $('update-status').textContent=(stale?'Unable to refresh · Data may be stale · ':'')+(lastSuccess?'Last successful update: '+new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'medium',timeZone:zone}).format(lastSuccess):'No successful update yet');
  }
  async function load(activePage=page,trackedPage=libraryPage) {
    if(stopped)return;
    const token=++serial;
    if(busy){pending=[activePage,trackedPage];return;}
    busy=true;const aborter=new AbortController();controller=aborter;
    const timeout=setTimeout(()=>aborter.abort(),20000);
    try {
      const response=await fetch(`${document.body.dataset.source}?page=${activePage}&library_page=${trackedPage}`,{signal:aborter.signal,credentials:'omit',cache:'no-store'});
      if(!response.ok)throw Error('Refresh failed');const data=await response.json();
      if(stopped||token!==serial)return;
      const changedLibrary=libraryPage!==data.library_pagination.page;
      snapshot=data;zone=data.timezone;page=data.pagination.page;pages=data.pagination.pages;
      libraryPage=data.library_pagination.page;libraryPages=data.library_pagination.pages;
      for(const [key,value] of Object.entries(data.metrics))$(key).textContent=value;
      reconcile($('featured'),data.featured,()=>data.featured?[card(data.featured,'spotlight-content')]:[node('h2','','Research starts with a family.'),node('p','case-description','No malware-family profiles have been added yet.')]);
      reconcile($('active'),data.investigations,()=>data.investigations.length?data.investigations.map(i=>card(i,'active-card')):[node('p','case-description','No family investigations currently in progress')]);
      strip.update(data.tracked,changedLibrary);pageControls();lastSuccess=new Date(data.updated_at);$('display-zone').textContent=zone;status(false);
    } catch(error) {if(!stopped&&token===serial)status(true);}
    finally {
      clearTimeout(timeout);busy=false;
      if(pending&&!stopped){const next=pending;pending=null;load(...next);}
    }
  }
  function animate(time){if(stopped)return;strip.tick(time);frame=requestAnimationFrame(animate);}
  function visibility(){if(!document.hidden)load();}
  function motion(){strip.measure();pageControls();}
  function start() {
    stopped=false;strip.last=0;strip.observer.observe(strip.viewport);strip.observer.observe(strip.group);
    reduced.addEventListener('change',motion);document.addEventListener('visibilitychange',visibility);
    load();refreshTimer=setInterval(()=>load(),60000);
    rotationTimer=setInterval(()=>{
      const section=document.querySelector('.investigations');
      if(!busy&&pages>1&&!rotationPaused&&!reduced.matches&&!document.hidden&&!section.matches(':hover')&&!section.contains(document.activeElement))load((page+1)%pages,libraryPage);
    },25000);
    frame=requestAnimationFrame(animate);
  }
  window.addEventListener('pagehide',()=>{
    stopped=true;serial++;pending=null;controller?.abort();clearInterval(refreshTimer);clearInterval(rotationTimer);cancelAnimationFrame(frame);strip.observer.disconnect();
    reduced.removeEventListener('change',motion);document.removeEventListener('visibilitychange',visibility);
  });
  window.addEventListener('pageshow',event=>{if(event.persisted)start();});
  start();
})();
