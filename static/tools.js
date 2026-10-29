(() => {
  const workspace = document.getElementById('tools-workspace');
  if (!workspace) return;
  const tabs = [...workspace.querySelectorAll('[role="tab"]')];
  let selecting = false, historyIndex = Number.isInteger(history.state?.mareTools?.index) ? history.state.mareTools.index : 0, restoringHistory = false;
  const initial = tabs.find(tab => tab.getAttribute('aria-selected') === 'true');
  if (initial) history.replaceState({...history.state,mareTools:{id:initial.dataset.tool,index:historyIndex}},'');
  async function select(tab, push = true) {
    if (selecting || !tab) return false;
    const previous = tabs.find(item => item.getAttribute('aria-selected') === 'true');
    if (previous && previous !== tab) {
      const frame = document.getElementById(previous.getAttribute('aria-controls')).querySelector('iframe');
      let guard;
      try { guard = frame.contentWindow?.mareCanLeaveTool; } catch (_) { /* Cross-origin tools cannot expose a leave hook. */ }
      if (typeof guard === 'function') { selecting = true; try { if (!await guard()) return false; } catch (_) { return false; } finally { selecting = false; } }
    }
    tabs.forEach(item => {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(item.getAttribute('aria-controls'));
      panel.hidden = !active;
      const frame = panel.querySelector('iframe');
      if (active && !frame.hasAttribute('src')) frame.src = frame.dataset.src;
    });
    document.querySelectorAll('[data-navigation-tool]').forEach(link => {
      if (link.dataset.navigationTool === tab.dataset.tool) link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    });
    if (push && previous !== tab) history.pushState({mareTools:{id:tab.dataset.tool,index:++historyIndex}},'',tab.dataset.url);
    return true;
  }
  // Handle workspace links before embedded editors' document leave listeners.
  // Keep normal new-tab/modified-click behavior and reuse the same leave hook.
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');
    if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download')||link.origin!==location.origin)return;
    const tab=tabs.find(tab=>new URL(tab.dataset.url,location.href).pathname===link.pathname) || (link.pathname===new URL(workspace.dataset.toolsHome,location.href).pathname?tabs[0]:null);
    if(!tab)return;
    event.preventDefault();select(tab);
  });
  window.addEventListener('popstate',async event=>{
    if(restoringHistory){restoringHistory=false;return;}
    const state=event.state?.mareTools;
    if(!state)return;
    const tab=tabs.find(tab=>tab.dataset.tool===state.id),delta=state.index-historyIndex;
    if(await select(tab,false))historyIndex=state.index;
    else if(delta){restoringHistory=true;history.go(-delta);}
  });
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); tabs[next].focus(); select(tabs[next]); }
    });
  });
  const expand = document.getElementById('tools-expand');
  function toggle(force) {
    const expanded = workspace.classList.toggle('expanded', force);
    expand.textContent = expanded ? 'Restore' : 'Expand';
    expand.setAttribute('aria-pressed', String(expanded));
    document.body.classList.toggle('tools-expanded', expanded);
  }
  expand.addEventListener('click', () => toggle());
  document.addEventListener('keydown', event => { if (event.key === 'Escape') toggle(false); });
  const selected = tabs.find(tab => tab.getAttribute('aria-selected') === 'true');
  if (selected) select(selected, false);
  function resize() {
    workspace.style.setProperty('--workspace-height', `${Math.max(420, window.innerHeight - workspace.getBoundingClientRect().top - 20)}px`);
  }
  window.addEventListener('resize', resize);
  resize();
})();
