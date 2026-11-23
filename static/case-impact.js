(() => {
  const panel = document.querySelector('[data-impact-panel]');
  if (!panel) return;
  const form = panel.querySelector('form'), toggle = form.elements.impact_confirmed;
  const type = form.elements.impact_type, summary = form.elements.impact_summary;
  const fields = form.querySelector('[data-impact-fields]');
  const status = form.querySelector('[data-impact-status]');
  const confirmedAt = form.querySelector('[data-impact-confirmed-at]');
  const key = 'mws-impact-panel-' + document.body.dataset.userLayout + '-' + panel.dataset.caseId;
  try { const state = sessionStorage.getItem(key); if (state !== null) panel.open = state === 'open'; } catch {}
  panel.addEventListener('toggle', () => { try { sessionStorage.setItem(key, panel.open ? 'open' : 'closed'); } catch {} });
  function reveal() {
    fields.hidden = !toggle.checked;
    type.required = summary.required = toggle.checked;
  }
  reveal();

  const snapshot = () => JSON.stringify([toggle.checked, type.value, summary.value]);
  const remoteSnapshot = remote => JSON.stringify([
    remote.elements.impact_confirmed.checked,
    remote.elements.impact_type.value,
    remote.elements.impact_summary.value,
  ]);
  // Acknowledged raw drafts and normalized server values are different baselines.
  // Server normalization must never become a write to the editing buffer.
  let acknowledged = snapshot(), persisted = acknowledged;
  let saving = false, timer, dueAt = 0, generation = 0;
  const dirty = () => acknowledged !== snapshot();
  function updateConfirmedAt(value) {
    if (!value || !confirmedAt) return;
    const time = confirmedAt.querySelector('time');
    if (time.dateTime !== value) {
      time.dateTime = value;
      time.textContent = value;
    }
    confirmedAt.hidden = false;
  }
  function updateBadge(confirmed) {
    const badge = panel.querySelector('[data-impact-state]');
    badge.className = confirmed ? 'impact-badge' : 'muted';
    badge.textContent = confirmed ? '★ Impact' : 'Not recorded';
  }
  window.MareCaseImpact = {
    generation: () => generation,
    apply(page, requestedGeneration) {
      if (requestedGeneration !== undefined && requestedGeneration !== generation) return false;
      const remote = page.querySelector('[data-impact-form]');
      if (!remote) return false;
      const incoming = remoteSnapshot(remote);
      if (saving || dirty()) {
        if (incoming !== persisted && !saving) {
          status.textContent = 'Saved impact changed elsewhere; your unsaved edits are retained.';
          return true;
        }
        return false;
      }
      // Even a pristine, focused editor owns its raw text and selection. A matching
      // server baseline is merely our last normalized save, not an external edit.
      if (form.contains(document.activeElement)) return false;
      if (incoming !== persisted) {
        if (toggle.checked !== remote.elements.impact_confirmed.checked) toggle.checked = remote.elements.impact_confirmed.checked;
        if (type.value !== remote.elements.impact_type.value) type.value = remote.elements.impact_type.value;
        if (summary.value !== remote.elements.impact_summary.value) summary.value = remote.elements.impact_summary.value;
        reveal();
        acknowledged = snapshot();
        persisted = incoming;
        generation++;
        updateBadge(toggle.checked);
      }
      updateConfirmedAt(remote.querySelector('[data-impact-confirmed-at] time')?.dateTime);
      form.querySelector('fieldset').disabled = remote.querySelector('fieldset').disabled;
      return false;
    },
  };
  if (toggle.disabled || form.querySelector('fieldset:disabled')) return;

  // Validate non-whitespace content without normalizing the editing buffer.
  const valid = () => !toggle.checked || (type.value && /\S/.test(summary.value) && summary.value.length <= 4000);
  function queueAfterPause() {
    clearTimeout(timer);
    timer = setTimeout(save, Math.max(0, dueAt - Date.now()));
  }
  async function save() {
    if (saving || !dirty()) return;
    if (!valid()) {
      status.textContent = 'Confirmed impact requires an outcome type and a nonempty Impact Summary.';
      return;
    }
    const pending = snapshot();
    saving = true;
    status.textContent = 'Saving impact…';
    const body = new FormData(form);
    body.set('ajax', '1');
    try {
      const response = await fetch(form.action, {method: 'POST', body, redirect: 'error'});
      const data = await response.json();
      if (!response.ok || !data.saved) throw Error(data.error || 'Impact could not be saved.');
      acknowledged = pending;
      // FormData submits CRLF, while textarea.value and parsed HTML expose LF.
      // Normalize only this server comparison value, never the live draft.
      persisted = JSON.stringify([Boolean(data.impact_confirmed), data.impact_type || '',
        (data.impact_summary || '').replace(/\r\n?/g, '\n')]);
      generation++;
      status.textContent = dirty() ? 'Unsaved impact changes' : 'Impact saved.';
      updateBadge(data.impact_confirmed);
      updateConfirmedAt(data.impact_confirmed_at);
      // Impact is independent metadata. No Workbench refresh or input assignment.
    } catch (error) {
      status.textContent = error.message;
    } finally {
      saving = false;
      if (dirty() && snapshot() !== pending) queueAfterPause();
    }
  }
  function edited() {
    generation++;
    reveal();
    status.textContent = dirty() ? 'Unsaved impact changes' : 'Impact saved.';
    dueAt = Date.now() + 700;
    queueAfterPause();
  }
  form.addEventListener('input', edited);
  form.addEventListener('change', edited);
  form.addEventListener('submit', event => {
    event.preventDefault();
    clearTimeout(timer);
    if (!valid()) form.reportValidity();
    save();
  });
  window.MareAutosave?.register({
    canSave: () => dirty() && valid() && !saving && Date.now() >= dueAt,
    save,
    onError: error => { status.textContent = error.message; },
  });
  window.addEventListener('beforeunload', event => {
    if (dirty() || saving) { event.preventDefault(); event.returnValue = ''; }
  });
})();
