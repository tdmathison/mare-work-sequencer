(() => {
  const workspace = document.getElementById('tools-workspace');
  if (!workspace) return;
  const tabs = [...workspace.querySelectorAll('[role="tab"]')];
  function select(tab) {
    tabs.forEach(item => {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(item.getAttribute('aria-controls'));
      panel.hidden = !active;
      const frame = panel.querySelector('iframe');
      if (active && !frame.hasAttribute('src')) frame.src = frame.dataset.src;
    });
  }
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
  if (selected) select(selected);
  function resize() {
    workspace.style.setProperty('--workspace-height', `${Math.max(420, window.innerHeight - workspace.getBoundingClientRect().top - 20)}px`);
  }
  window.addEventListener('resize', resize);
  resize();
})();
