/* Palette preferences and visibility never modify CodeMirror or its history. */
(() => {
  const palette = document.querySelector('.text-commands');
  if (!palette) return;
  const search = palette.querySelector('[data-command-search]');
  const categories = [...palette.querySelectorAll('[data-command-category]')];
  const originals = [...palette.querySelectorAll('[data-original-category] [data-command-row]')];
  const rows = [...palette.querySelectorAll('[data-command-row]')];
  const metadata = new Map(originals.map(row => [row.dataset.commandId, {
    name: row.querySelector('.text-command-name').textContent,
    terms: [...row.querySelectorAll('.text-command-name,.text-command-description')].map(label => label.textContent).join(' ').toLowerCase(),
  }]));
  const expanded = new Map(categories.map(category => [category, category.hasAttribute('data-favorites-category')]));
  const key = 'mare-text-favorites:' + palette.closest('[data-text-tool]').dataset.userPreferences;
  let favorites = new Set();
  try {
    const stored = JSON.parse(localStorage.getItem(key) || '[]');
    if (Array.isArray(stored)) favorites = new Set(stored.filter(id => metadata.has(id)));
  } catch { /* Storage may be unavailable; the in-page palette still works. */ }
  function save() {
    try { localStorage.setItem(key, JSON.stringify([...metadata.keys()].filter(id => favorites.has(id)))); } catch {}
  }
  const searchExpanded = new Map(categories.map(category => [category, true]));
  let previousQuery = '';
  function render() {
    const query = search.value.trim().toLowerCase();
    if (query && query !== previousQuery) for (const category of categories) searchExpanded.set(category, true);
    previousQuery = query;
    const matches = new Set([...metadata].filter(([, item]) => item.terms.includes(query)).map(([id]) => id));
    for (const row of rows) {
      const id = row.dataset.commandId, starred = favorites.has(id);
      row.hidden = !matches.has(id) || (row.closest('[data-favorites-category]') !== null && !starred);
      const star = row.querySelector('[data-favorite]');
      star.setAttribute('aria-pressed', String(starred));
      star.setAttribute('aria-label', `${starred ? 'Remove' : 'Add'} ${metadata.get(id).name} ${starred ? 'from' : 'to'} favorites`);
      star.firstElementChild.textContent = starred ? '★' : '☆';
    }
    for (const category of categories) {
      const hasMatches = Boolean(category.querySelector('[data-command-row]:not([hidden])'));
      category.hidden = Boolean(query) && !hasMatches;
      const open = query ? hasMatches && searchExpanded.get(category) : expanded.get(category);
      category.querySelector('[data-category-toggle]').setAttribute('aria-expanded', String(open));
      category.querySelector('[data-category-content]').hidden = !open;
    }
    palette.querySelector('[data-favorites-empty]').hidden = favorites.size !== 0 || Boolean(query);
    palette.querySelector('[data-command-empty]').hidden = matches.size !== 0;
    palette.querySelector('[data-command-results]').textContent = query ? `${matches.size} of ${metadata.size} commands` : `${metadata.size} commands`;
  }
  palette.addEventListener('click', event => {
    const star = event.target.closest('[data-favorite]');
    if (star) {
      const id = star.dataset.favorite, removingFavoriteRow = favorites.has(id) && star.closest('[data-favorites-category]');
      favorites.has(id) ? favorites.delete(id) : favorites.add(id);
      save(); render();
      if (removingFavoriteRow) {
        const header = palette.querySelector('[data-favorites-category] [data-category-toggle]');
        (header.getClientRects().length ? header : search).focus({preventScroll:true});
      }
      return;
    }
    const toggle = event.target.closest('[data-category-toggle]');
    if (toggle) {
      const category = toggle.closest('[data-command-category]');
      const choices = search.value.trim() ? searchExpanded : expanded;
      choices.set(category, toggle.getAttribute('aria-expanded') !== 'true'); render();
    }
    if (event.target.closest('[data-categories-expand],[data-categories-collapse]')) {
      const open = Boolean(event.target.closest('[data-categories-expand]'));
      const choices = search.value.trim() ? searchExpanded : expanded;
      for (const category of categories) choices.set(category, open);
      render();
    }
  });
  search.addEventListener('input', render);
  palette.querySelectorAll('[data-command-reset]').forEach(button => button.addEventListener('click', () => {
    search.value = ''; render(); search.focus();
  }));
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); search.value = ''; render(); }
  });
  render();
})();
