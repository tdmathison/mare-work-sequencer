(() => {
  const root = document.querySelector('[data-help]');
  if (!root) return;
  let doc = JSON.parse(root.querySelector('[data-help-document]').textContent);
  const search = root.querySelector('#faq-search'), faqs = root.querySelector('[data-faqs]');
  const node = (tag, text, className) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (className) e.className = className; return e; };
  function filter() {
    const query = search.value.toLocaleLowerCase().trim(); let count = 0;
    for (const row of faqs.children) {
      const entry = doc.faqs.find(f => f.id === row.dataset.faqId);
      row.hidden = !`${entry.question}\n${entry.answer}`.toLocaleLowerCase().includes(query);
      if (row.hidden) { row.querySelector('button').setAttribute('aria-expanded', 'false'); row.querySelector('.help-answer').hidden = true; }
      else count++;
    }
    root.querySelector('[data-faq-count]').textContent = `${count} / ${doc.faqs.length} FAQs`;
    const empty = root.querySelector('[data-faq-empty]'); empty.hidden = count > 0;
    empty.textContent = doc.faqs.length ? 'No matching FAQs. Clear the search to see all questions.' : 'No FAQs configured.';
  }
  faqs.addEventListener('click', event => {
    const button = event.target.closest('h2 button'); if (!button) return;
    const expand = button.getAttribute('aria-expanded') !== 'true';
    for (const row of faqs.children) { const b = row.querySelector('button'); const open = b === button && expand; b.setAttribute('aria-expanded', String(open)); row.querySelector('.help-answer').hidden = !open; }
  });
  search.addEventListener('input', filter);
  root.querySelector('[data-clear-search]').addEventListener('click', () => { search.value = ''; filter(); search.focus(); });
  function renderGuide() {
    root.querySelector('[data-help-introduction]').textContent = doc.introduction;
    const sops = root.querySelector('[data-sops]'); sops.replaceChildren();
    for (const sop of doc.sops) { const a = node('a', sop.title + ' ↗'); a.href = sop.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.setAttribute('aria-label', sop.title + ' (opens in a new tab)'); sops.append(a); }
    if (!doc.sops.length) sops.append(node('span', 'No SOP documents configured.', 'muted'));
    faqs.replaceChildren();
    for (const entry of doc.faqs) {
      const row = node('article', undefined, 'help-faq'); row.dataset.faqId = entry.id;
      const heading = node('h2'), button = node('button', entry.question); button.type = 'button'; button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'answer-' + entry.id);
      const arrow = node('span', '⌄'); arrow.setAttribute('aria-hidden', 'true'); button.append(arrow); heading.append(button);
      const answer = node('div', undefined, 'markdown-preview help-answer'); answer.id = 'answer-' + entry.id; answer.hidden = true; answer.innerHTML = entry.html;
      row.append(heading, answer); faqs.append(row);
    }
    filter();
  }
  filter();
  const dialog = root.querySelector('dialog'); if (!dialog) return;
  const form = dialog.querySelector('form'), fields = form.querySelector('fieldset'), status = form.querySelector('[data-help-status]');
  const sopList = form.querySelector('[data-edit-sops]'), faqList = form.querySelector('[data-edit-faqs]');
  let baseline = '', busy = false;
  function values() {
    const collect = (container, kind) => [...container.children].map(row => {
      const item = {id: row.dataset.id};
      for (const key of kind === 'sops' ? ['title','url'] : ['question','answer']) item[key] = row.querySelector(`[name=${key}]`).value;
      return item;
    });
    return {revision: doc.revision, introduction: form.elements.introduction.value, sops: collect(sopList,'sops'), faqs: collect(faqList,'faqs')};
  }
  const dirty = () => baseline && JSON.stringify(values()) !== baseline;
  async function request(url, data) {
    const response = await fetch(url, {method: data ? 'POST' : 'GET', body: data, headers: {Accept:'application/json'}});
    if (response.redirected) throw Error('Session expired. Keep your edits and sign in in another tab.');
    const result = await response.json().catch(() => { throw Error('Request failed. Your edits are retained.'); });
    if (!response.ok) { if (response.status === 409) form.querySelector('[data-reload-help]').hidden = false; throw Error(result.error || 'Request failed. Your edits are retained.'); }
    return result;
  }
  function action(label, fn, className) { const b = node('button', label, className); b.type = 'button'; b.addEventListener('click', fn); return b; }
  function controls(container) { for (const [index, row] of [...container.children].entries()) { row.querySelector('[data-up]').disabled = index === 0; row.querySelector('[data-down]').disabled = index === container.children.length - 1; } }
  function add(container, kind, item = {}) {
    const row = node('details', undefined, 'help-edit-entry'); row.dataset.id = item.id || '';
    const summary = node('summary', item.title || item.question || (kind === 'sops' ? 'New SOP link' : 'New FAQ')); row.append(summary);
    const actions = node('div', undefined, 'help-entry-actions');
    const up = action('Move up', () => { if (row.previousElementSibling) container.insertBefore(row, row.previousElementSibling); controls(container); (up.disabled ? summary : up).focus(); }); up.dataset.up = '';
    const down = action('Move down', () => { if (row.nextElementSibling) container.insertBefore(row.nextElementSibling, row); controls(container); (down.disabled ? summary : down).focus(); }); down.dataset.down = '';
    actions.append(up, down, action('Delete', () => { if (confirm(`Delete "${summary.textContent}"? Save help to apply this deletion.`)) { row.querySelectorAll('[data-markdown-editor]').forEach(area => { if (area.dataset.ready) window.MareEditors.get(area).destroy(); }); row.remove(); controls(container); } }, 'button-danger'));
    row.append(actions);
    function input(key, label, maximum, multiline = false) {
      const wrap = node('label', label), field = node(multiline ? 'textarea' : 'input'); field.name = key; field.value = item[key] || ''; field.maxLength = maximum; field.required = true;
      if (!multiline) field.type = 'text'; wrap.append(field); row.append(wrap); return field;
    }
    const title = input(kind === 'sops' ? 'title' : 'question', kind === 'sops' ? 'Display title' : 'Question', kind === 'sops' ? 200 : 300);
    title.addEventListener('input', () => { summary.textContent = title.value || 'New entry'; });
    if (kind === 'sops') input('url','SharePoint SOP URL (HTTPS)',4096);
    else {
      const section = node('section', undefined, 'manual-section'), tabs = node('div', undefined, 'editor-view-tabs'), editor = node('div', undefined, 'markdown-editor');
      const area = node('textarea', undefined, 'markdown-source'); area.name = 'answer'; area.value = item.answer || ''; area.maxLength = 20000; area.required = true; area.dataset.markdownEditor = ''; area.setAttribute('aria-label', 'FAQ answer Markdown'); editor.append(area);
      const pane = node('div', undefined, 'markdown-preview'); pane.hidden = true;
      let generation = 0;
      const write = action('Write', () => { generation++; pane.hidden = true; editor.hidden = false; write.setAttribute('aria-selected','true'); preview.setAttribute('aria-selected','false'); window.MareEditors.get(area).restoreLayout(); window.MareEditors.get(area).measure(); });
      const preview = action('Preview', async () => { const seq = ++generation; window.MareEditors.get(area).preserveLayout(); editor.hidden = true; pane.hidden = false; write.setAttribute('aria-selected','false'); preview.setAttribute('aria-selected','true'); pane.textContent = 'Rendering preview…'; const body = new FormData(); body.set('csrf',root.dataset.csrf); body.set('text',area.value); try { const result = await request(root.dataset.previewUrl,body); if (seq === generation) pane.innerHTML = result.html; } catch(error) { if (seq === generation) pane.textContent = error.message; } });
      tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','FAQ answer view'); write.setAttribute('role','tab'); preview.setAttribute('role','tab'); write.setAttribute('aria-selected','true'); preview.setAttribute('aria-selected','false');
      for (const tab of [write,preview]) tab.addEventListener('keydown', event => { if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) { event.preventDefault(); const target = event.key === 'Home' ? write : event.key === 'End' ? preview : tab === write ? preview : write; target.focus(); target.click(); } });
      tabs.append(write,preview); section.append(tabs,editor,pane); row.append(section);
      row.addEventListener('toggle', () => { if (row.open) { window.MareEditors.init(row); area.dataset.ready = 'true'; window.MareEditors.get(area).measure(); } });
    }
    container.append(row); controls(container); return row;
  }
  function fill() {
    for (const area of form.querySelectorAll('[data-markdown-editor][data-ready]')) window.MareEditors.get(area).destroy();
    form.elements.introduction.value = doc.introduction; sopList.replaceChildren(); faqList.replaceChildren();
    doc.sops.forEach(item => add(sopList,'sops',item)); doc.faqs.forEach(item => add(faqList,'faqs',item));
    baseline = JSON.stringify(values()); form.querySelector('[data-reload-help]').hidden = true; status.textContent = '';
  }
  root.querySelector('[data-manage-help]').addEventListener('click', async () => { try { doc = await request(root.dataset.contentUrl); fill(); renderGuide(); dialog.showModal(); } catch(error) { root.querySelector('[data-help-feedback]').textContent = error.message; } });
  form.querySelector('[data-add-sop]').addEventListener('click', () => { const row = add(sopList,'sops'); row.open = true; row.querySelector('input').focus(); });
  form.querySelector('[data-add-faq]').addEventListener('click', () => { const row = add(faqList,'faqs'); row.open = true; row.querySelector('input').focus(); });
  function close() { if (busy) return; if (!dirty() || confirm('Discard unsaved Help changes?')) { baseline = ''; dialog.close(); } }
  form.querySelector('[data-close-help]').addEventListener('click',close);
  dialog.addEventListener('cancel',event => { event.preventDefault(); close(); });
  window.addEventListener('beforeunload',event => { if (dialog.open && dirty()) { event.preventDefault(); event.returnValue = ''; } });
  form.querySelector('[data-reload-help]').addEventListener('click', async () => { if (busy) return; if (dirty() && !confirm('Discard your edits and reload the current Help content?')) return; try { doc = await request(root.dataset.contentUrl); fill(); renderGuide(); } catch(error) { status.textContent = error.message; } });
  form.addEventListener('invalid',event => { const row = event.target.closest('details'); if (row) row.open = true; },true);
  form.addEventListener('submit',async event => {
    event.preventDefault(); if (busy) return;
    const body = new FormData(); body.set('csrf',root.dataset.csrf); body.set('document',JSON.stringify(values())); busy = true; fields.disabled = true; form.querySelector('[type=submit]').disabled = true;
    try { doc = await request(root.dataset.contentUrl,body); fill(); renderGuide(); status.textContent = 'Help saved for all analysts.'; }
    catch(error) { status.textContent = error.message; }
    finally { busy = false; fields.disabled = false; form.querySelector('[type=submit]').disabled = false; }
  });
})();
