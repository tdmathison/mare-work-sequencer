(() => {
  const interval = Number(document.body.dataset.autosaveMinutes || 5) * 60000;
  const identity = document.body.dataset.userLayout;
  const entries = [];
  let enabled = document.body.dataset.autosaveEnabled !== '0';
  let checkFailed = false;
  let checking = false, timer = null, generation = 0, synchronization = 0;
  const allowed = () => enabled && !checking;
  function display(entry) {
    entry.onCountdown?.(
      Math.max(0, Math.ceil((entry.next - Date.now()) / 1000)),
      entry.running, !allowed() || !entry.canSave(),
      checking ? (checkFailed ? 'Autosave paused: unable to verify account preference' : 'Checking autosave preference') : enabled ? 'Autosave paused' : 'Autosave disabled',
    );
  }
  function schedule() {
    if (!allowed() && timer !== null) { clearInterval(timer); timer = null; }
    if (allowed() && timer === null) timer = setInterval(tick, 1000);
    for (const entry of entries) display(entry);
  }
  function changed() {
    generation++;
    for (const entry of entries) entry.onEnabledChange?.(allowed());
    schedule();
  }
  async function tick() {
    const current = generation;
    for (const entry of entries) {
      if (!allowed() || current !== generation) return;
      display(entry);
      if (entry.running || Date.now() < entry.next) continue;
      if (!entry.canSave()) {
        entry.next = Date.now() + interval;
        display(entry);
        continue;
      }
      entry.running = true;
      display(entry);
      try { await entry.save(); }
      catch (error) { entry.onError?.(error); }
      finally {
        // Submitted requests may finish even after automatic saving is disabled.
        entry.running = false;
        entry.next = Date.now() + interval;
        display(entry);
      }
    }
  }
  async function synchronize() {
    if (!identity || identity === 'anonymous') return;
    const current = ++synchronization;
    checking = true;
    checkFailed = false;
    changed();
    try {
      const response = await fetch(window.MWS.path('/account/autosave'), {
        cache:'no-store', credentials:'same-origin', headers:{Accept:'application/json'},
      });
      if (!response.ok || response.redirected) throw Error('Session unavailable');
      const preference = await response.json();
      if (current !== synchronization) return;
      if (preference.user_uuid !== identity || typeof preference.enabled !== 'boolean')
        throw Error('Account changed');
      if (!enabled && preference.enabled)
        for (const entry of entries) entry.next = Date.now() + interval;
      enabled = preference.enabled;
      checking = false;
      changed();
    } catch (_) {
      // Keep drafts/manual Save available, but do not autosave under an unverified
      // session or stale account preference. A later activation retries the check.
      if (current === synchronization) { checking = true; checkFailed = true; changed(); }
    }
  }
  window.MareAutosave = {
    get enabled() { return allowed(); },
    synchronize,
    register(options) {
      const entry = {...options, next:Date.now() + interval, running:false};
      entries.push(entry);
      display(entry);
      return {reset() { entry.next = Date.now() + interval; display(entry); }};
    },
  };
  schedule();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) synchronize();
  });
  window.addEventListener?.('focus', synchronize);
  window.addEventListener?.('pageshow', synchronize);
})();
