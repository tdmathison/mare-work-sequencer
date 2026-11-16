(() => {
  const basePath = document.currentScript.dataset.basePath;
  window.MWS_CONFIG = Object.freeze({basePath});
  function mount(value, internal) {
    if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return value;
    if (!internal && basePath && (value === basePath || ['/','?','#'].some(suffix => value.startsWith(basePath + suffix)))) return value;
    return basePath + value;
  }
  // path() accepts internal routes, even when the mount matches a route stem.
  // url() accepts either an internal or an already mounted URL and is idempotent.
  window.MWS = Object.freeze({path: value => mount(value, true), url: value => mount(value, false)});
})();
