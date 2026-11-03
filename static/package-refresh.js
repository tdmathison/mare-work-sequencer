/* One document-scoped revalidation path over the existing Case page and tab APIs.
 * No persistent cache: saved data is scoped to this Case and authenticated user.
 * Editor modules own their buffers and revisions; never replace their panels. */
(() => {
  const tabs = document.querySelector('.case-tabs');
  if (!tabs) return;
  const cid = tabs.dataset.caseId, user = tabs.dataset.userId;
  const status = document.getElementById('case-data-status');
  let sequence = 0, controller, activation = 0;
  const active = () => tabs.querySelector('[aria-selected="true"]')?.id.replace('tab-', '');
  const dependencies = {
    tasks: ['tasks', 'notes', 'workbench', 'review'],
    notes: ['notes', 'report', 'package', 'workbench', 'review'],
    indicators: ['indicators', 'report', 'package', 'notes', 'workbench', 'review'],
    references: ['references', 'report', 'package', 'notes', 'workbench', 'review'],
    report: ['report', 'package', 'notes', 'workbench', 'review'],
    package: ['package', 'report', 'indicators', 'references', 'notes', 'workbench', 'review'],
  };
  function replaceSaved(page, selector) {
    const current = document.querySelector(selector), updated = page.querySelector(selector);
    if (current && updated && current.innerHTML !== updated.innerHTML)
      current.innerHTML = updated.innerHTML;
  }
  function apply(page) {
    const oldStage = document.querySelector('#case-heading .badge')?.textContent;
    const newStage = page.querySelector('#case-heading .badge')?.textContent;
    if (oldStage !== newStage) {
      const stage = document.querySelector('.stage-panel');
      const dirty = [...stage.querySelectorAll('input[name],select[name]')].some(field=>field.value !== (field.tagName==='SELECT' ? [...field.options].find(o=>o.defaultSelected)?.value || field.options[0]?.value : field.defaultValue));
      if (!dirty && !stage.contains(document.activeElement)) replaceSaved(page, '.stage-panel');
    }
    replaceSaved(page, '#case-state-notices');
    replaceSaved(page, '#case-heading');
    for (const id of ['completion-review', 'completion-workbench']) replaceSaved(page, '#'+id);
    for (const kind of ['standard', 'raw']) replaceSaved(page, `[data-archive-pane="${kind}"]`);
    for (const selector of ['.stage-panel > .eyebrow', '.stage-panel > h2', '.stage-panel > p', '.stage-strip']) replaceSaved(page, selector);
    const bar = document.getElementById('case-tags'), nextBar = page.getElementById('case-tags');
    if (bar && nextBar && bar.dataset.saving !== 'true') {
      const incoming = new Map([...nextBar.querySelectorAll('.tag-chip[data-tag-id]')].map(chip=>[chip.dataset.tagId,chip]));
      for (const chip of bar.querySelectorAll('.tag-chip[data-tag-id]')) {
        const next = incoming.get(chip.dataset.tagId);
        if (!next) chip.remove();
        else { if (chip.innerHTML !== next.innerHTML) chip.innerHTML = next.innerHTML; chip.title = next.title; incoming.delete(chip.dataset.tagId); }
      }
      for (const chip of incoming.values()) bar.insertBefore(chip,bar.querySelector('.tag-autocomplete'));
    }
    for (const form of document.querySelectorAll('.stage-panel > form')) {
      const next = [...page.querySelectorAll('.stage-panel > form')].find(f=>f.getAttribute('action')===form.getAttribute('action'));
      const dirty = [...form.elements].some(field=>'value' in field && field.name && field.value !== (field.tagName==='SELECT' ? [...field.options].find(o=>o.defaultSelected)?.value || field.options[0]?.value : field.defaultValue));
      if (next && !dirty && !form.contains(document.activeElement) && next.innerHTML !== form.innerHTML) form.innerHTML = next.innerHTML;
    }
    const history = document.getElementById('stage-history'), nextHistory = page.getElementById('stage-history');
    if (history && nextHistory && !history.contains(document.activeElement)) replaceSaved(page, '#stage-history');
    // Update pristine metadata fields in place. A dirty form keeps its draft and
    // selection, rather than acquiring a new server baseline behind the analyst.
    let conflict = false;
    for (const form of document.querySelectorAll('#case-details form')) {
      const updated = [...page.querySelectorAll('#case-details form')].find(f => f.getAttribute('action') === form.getAttribute('action'));
      if (!updated) continue;
      for (const field of form.querySelectorAll('input[name],textarea[name],select[name]')) {
        const next = updated.elements.namedItem(field.name);
        if (!next || field.name === 'csrf') continue;
        const baseline = field.tagName === 'SELECT' ? [...field.options].find(o=>o.defaultSelected)?.value || '' : field.defaultValue;
        if (field.value !== baseline) { if (next.value !== baseline) conflict = true; continue; }
        if (field.value !== next.value) field.value = next.value;
        if (field.tagName === 'SELECT') for (const option of field.options) option.defaultSelected = option.value === next.value;
        else field.defaultValue = next.value;
      }
    }
    for (const root of document.querySelectorAll('#indicator-workspace,#reference-workspace')) {
      const next = page.getElementById(root.id);
      if (next) root.dataset.locked = next.dataset.locked;
    }
    // Permissions/locks remain server-owned; leave all inputs and editor DOM intact.
    for (const form of document.querySelectorAll('form[action]')) {
      const next = [...page.querySelectorAll('form[action]')].find(f => f.getAttribute('action') === form.getAttribute('action'));
      if (!next) continue;
      const fields = [...form.querySelectorAll('fieldset.workflow-controls')];
      [...next.querySelectorAll('fieldset.workflow-controls')].forEach((fieldset,index) => {
        if (fields[index]) fields[index].disabled = fieldset.disabled;
      });
    }
    for (const tab of tabs.querySelectorAll('[role=tab]')) {
      const next = page.getElementById(tab.id);
      if (next) { tab.disabled = next.disabled; tab.title = next.title; }
    }
    const samples = document.getElementById('include-samples-option');
    if (samples) {
      samples.hidden = page.getElementById(samples.id).hidden;
      if (samples.hidden) samples.querySelector('input').checked = false;
    }
    const archive = document.querySelector('#panel-review form[action$="/archive"] fieldset');
    const nextAck = page.querySelector('#panel-review input[name=acknowledge]');
    const ack = archive?.querySelector('input[name=acknowledge]');
    if (archive && nextAck && !ack) archive.prepend(nextAck.closest('label').cloneNode(true));
    else if (ack && !nextAck) ack.closest('label').remove();
    return conflict;
  }
  async function savedPage() {
    const current = ++sequence;
    controller?.abort(); controller = new AbortController();
    const response = await fetch(`/cases/${cid}`, {cache:'no-store', credentials:'same-origin', signal:controller.signal});
    if (!response.ok || response.redirected) throw Error('Unable to refresh saved Case data. Check your session and retry; drafts are retained.');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    const identity = page.querySelector('.case-tabs');
    if (identity?.dataset.caseId !== cid || identity?.dataset.userId !== user)
      throw Error('Case or signed-in user changed. Your drafts are retained; reopen the Case in the correct session.');
    if (current !== sequence) return null;
    return {conflict:apply(page)};
  }
  async function refreshTab(tab) {
    const loaders = {tasks:window.MareTaskCase, notes:window.MareCaseNotes,
      indicators:window.MareIndicators, references:window.MareReferences,
      package:window.MareArtifactRegister, report:window.MareReport, workbench:window.MareAssets};
    await loaders[tab]?.refresh();
  }
  async function revalidate(tab = active(), source) {
    const current = ++activation;
    status.textContent = 'Refreshing saved Case data…';
    try {
      const result = await savedPage();
      if (!result || current !== activation) return;
      if (tab !== source) await refreshTab(tab);
      if (current !== activation) return;
      status.textContent = result.conflict ? 'Saved Case details changed; your unsaved edits are retained. Review them before saving.' : '';
    } catch (error) {
      if (current === activation && error.name !== 'AbortError') {
        status.textContent = error.message + ' Displayed saved data may be out of date. ';
        const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = 'Retry';
        retry.onclick = () => revalidate(); status.append(retry);
      }
    }
  }
  function invalidate(source) {
    // Always reconcile both server-rendered checklists; refresh an affected active
    // editor through its own revision-aware loader, never by replacing its DOM.
    const tab = active();
    return revalidate((dependencies[source] || [tab]).includes(tab) ? tab : null, source);
  }
  window.MareCaseData = {revalidate, invalidate};
  // Preserve the existing integration point used by report/indicator saves.
  window.MarePackage = {refresh: caseId => String(caseId) === cid ? invalidate('package') : Promise.resolve()};
  window.addEventListener('mare:case-route', () => revalidate());
  window.addEventListener('pageshow', event => { if (event.persisted) revalidate(); });
})();
