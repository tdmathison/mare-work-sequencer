/* No credentials in config, URLs, storage or startup API calls. */
(() => {
  'use strict';
  const root = document.querySelector('[data-api-documentation]');
  if (!root) return;
  const status = root.querySelector('[data-api-status]');
  let ui;
  let apiBase;
  const forget = () => ui?.authActions.logout(['bearerAuth']);
  const message = text => { status.textContent = text; };
  async function specification() {
    const response = await fetch(root.dataset.specUrl, {credentials: 'same-origin', cache: 'no-store', redirect: 'error', headers: {Accept: 'application/json'}});
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Documentation session unavailable. Sign in again and reload the API tab.');
    const spec = await response.json();
    if (spec.openapi !== '3.0.3') throw new Error('The OpenAPI specification could not be loaded.');
    return spec;
  }
  async function start() {
    try {
      const spec = await specification();
      if (typeof window.SwaggerUIBundle !== 'function') throw new Error('Local Swagger UI assets are missing. Run npm ci and npm run build:api-docs, then reload.');
      apiBase = new URL(spec.servers[0].url, location.origin);
      ui = window.SwaggerUIBundle({
        spec, dom_id: '#swagger-ui', layout: 'BaseLayout',
        presets: [window.SwaggerUIBundle.presets.apis],
        validatorUrl: null, persistAuthorization: false, queryConfigEnabled: false,
        docExpansion: 'none', displayRequestDuration: true, deepLinking: false,
        defaultModelsExpandDepth: -1,
        requestInterceptor: async request => {
          // The existing API intentionally authenticates only with bearer tokens.
          // Gate this documentation client separately on the live web session.
          try { await specification(); }
          catch (error) { forget(); message('Session ended. Sign in again and reload before executing requests.'); throw error; }
          const target = new URL(request.url, location.href);
          if (target.origin !== location.origin || !target.pathname.startsWith(apiBase.pathname + '/')) throw new Error('Only this deployment’s public API may be called.');
          request.credentials = 'omit';
          return request;
        },
      });
      message('Ready. Requests run only when you choose Execute.');
    } catch (error) {
      message(`Interactive documentation unavailable. ${error.message} Use the raw specification link or reload after signing in.`);
    }
  }
  window.addEventListener('pagehide', forget);
  document.querySelector('form[action$="/logout"]')?.addEventListener('submit', forget);
  root.querySelector('[data-reveal-token]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const panel = button.closest('[data-new-token]');
    const output = panel.querySelector('[data-token-status]');
    button.disabled = true;
    try {
      const response = await fetch(panel.dataset.revealUrl, {method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        body: new URLSearchParams({csrf: root.querySelector('input[name="csrf"]').value})});
      if (!response.ok) throw new Error('Token unavailable. Create another token if it was already revealed.');
      panel.querySelector('[data-token-secret]').textContent = (await response.json()).token;
      output.textContent = 'Copy this token now; it is shown once. ';
      window.addEventListener('pagehide', () => { panel.querySelector('[data-token-secret]').textContent = ''; }, {once: true});
    } catch (error) { output.textContent = error.message; }
  });
  root.querySelector('[data-copy-python]').addEventListener('click', async () => {
    const source = root.querySelector('[data-python-example]');
    const output = root.querySelector('[data-copy-status]');
    try {
      await navigator.clipboard.writeText(source.value);
      output.textContent = 'Code copied.';
    } catch (_) { output.textContent = 'Clipboard unavailable. Select and copy the code in the read-only editor.'; }
  });
  start();
})();
