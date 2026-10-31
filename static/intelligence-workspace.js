/* Delegation also covers the Tags workspace's in-place document fragments. */
(() => {
  // Scroll only the directory, without moving the page or the details pane.
  function revealSelection(scope = document) {
    scope.querySelectorAll('.intelligence-directory-list').forEach(list => {
      const selected = list.querySelector('.family-choice[aria-current=page]');
      if (!selected || !list.getClientRects().length) return;
      const row = selected.getBoundingClientRect(), bounds = list.getBoundingClientRect();
      if (row.top < bounds.top) list.scrollTop -= bounds.top - row.top;
      else if (row.bottom > bounds.bottom) list.scrollTop += row.bottom - bounds.bottom;
    });
  }
  window.MwsIntelligenceWorkspace = {revealSelection};
  revealSelection();
  function fitFilters(filters) {
    if (!filters.open) return;
    const fields = filters.querySelector('.intelligence-filter-fields');
    fields.style.transform = '';
    const bounds = fields.getBoundingClientRect();
    const shift = Math.max(16 - bounds.left, Math.min(0, innerWidth - 16 - bounds.right));
    fields.style.transform = `translateX(${shift}px)`;
  }
  document.addEventListener('toggle', event => {
    if (event.target.matches('.intelligence-filters')) fitFilters(event.target);
  }, true);
  window.addEventListener('resize', () => document.querySelectorAll('.intelligence-filters[open]').forEach(fitFilters));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.intelligence-filters[open]').forEach(filters => {
      filters.open = false; filters.querySelector('summary').focus();
    });
  });
  document.addEventListener('click', event => {
    document.querySelectorAll('.intelligence-filters[open]').forEach(filters => {
      if (!filters.contains(event.target)) filters.open = false;
    });
    const back = event.target.closest('[data-workspace-back]');
    if (!back) return;
    const workspace = back.closest('[data-intelligence-workspace]');
    workspace.dataset.mobileDetail = 'false';
    revealSelection(workspace);
    const directory = workspace.querySelector('.intelligence-directory');
    const target = directory.querySelector('[aria-current=page]') || directory.querySelector('a');
    target?.focus({preventScroll:true});
    directory.scrollIntoView({block:'nearest'});
  });
})();
