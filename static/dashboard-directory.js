(() => {
  const directory = document.querySelector('.dashboard-directory');
  if (!directory) return;
  const search = directory.querySelector('#dashboard-search');
  const filters = [...directory.querySelectorAll('button[data-visibility]')];
  const rows = [...directory.querySelectorAll('.directory-row')];
  let visibility = 'all', announcement;
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    let count = 0;
    rows.forEach(row => {
      row.hidden = !(visibility === 'all' || visibility === row.dataset.visibility) || !row.dataset.search.toLocaleLowerCase().includes(query);
      if (!row.hidden) count++;
    });
    directory.querySelectorAll('.directory-group').forEach(group => {
      group.hidden = !group.querySelector('.directory-row:not([hidden])');
    });
    directory.querySelector('.directory-empty').hidden = count !== 0;
    clearTimeout(announcement);
    announcement = setTimeout(() => {
      directory.querySelector('[role=status]').textContent = `${count} dashboard${count === 1 ? '' : 's'}`;
    }, 250);
  }
  search.addEventListener('input', filter);
  filters.forEach(button => button.addEventListener('click', () => {
    visibility = button.dataset.visibility;
    filters.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    filter();
  }));
})();
