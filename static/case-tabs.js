(() => {
  const list = document.querySelector(".case-tabs");
  if (!list) return;
  const allTabs = [...list.querySelectorAll('[role="tab"]')];
  let tabs = allTabs.filter((tab) => !tab.disabled);
  const key = `mare-case-tab-${list.dataset.userId}-${list.dataset.caseId}`;
  function select(tab, focus = false) {
    window.MwsTabs.setActive(list,tab);
    try {
      sessionStorage.setItem(key, tab.id);
    } catch (_) {}
    if (focus) tab.focus();
  }
  let saved;
  try {
    saved = sessionStorage.getItem(key);
  } catch (_) {}
  function routeTab(url, fallback) {
    tabs = allTabs.filter(tab => !tab.disabled);
    fallback = fallback && !fallback.disabled ? fallback : tabs[0];
    const anchor = document.getElementById(url.hash.slice(1))?.closest('.case-tab-panel') ||
      (url.hash.startsWith('#readiness-') ? document.getElementById('panel-package') : null);
    return tabs.find(tab => anchor && tab.getAttribute('aria-controls') === anchor.id) ||
      tabs.find(tab => tab.id === 'tab-' + url.searchParams.get('tab')) || fallback;
  }
  function publishRoute() {
    window.dispatchEvent(new CustomEvent('mare:case-route'));
  }
  const initialURL = new URL(location.href);
  const initialTab = routeTab(initialURL, tabs.find(tab => tab.id === saved) || tabs[0]);
  select(initialTab);
  initialURL.searchParams.set('tab', initialTab.id.replace('tab-', ''));
  history.replaceState(history.state, '', initialURL);
  function reveal(id) {
    const target = document.getElementById(id);
    if (target) {
      if (target.tagName === "DETAILS") target.open = true;
      target.scrollIntoView({ block: "start" });
    }
  }
  if (location.hash)
    requestAnimationFrame(() => reveal(location.hash.slice(1)));
  function navigateURL(destination, focus = false) {
    const url = new URL(destination, location.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname) return false;
    const tab = routeTab(url);
    url.searchParams.set('tab', tab.id.replace('tab-', ''));
    if (url.href !== location.href) history.pushState(history.state, '', url);
    select(tab, focus);
    publishRoute();
    if (url.hash) reveal(url.hash.slice(1));
    return true;
  }
  // Delegate so refreshed checklists and generated-content links share routing.
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-case-tab]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (navigateURL(link.href)) event.preventDefault();
  });
  function navigate(tab, focus = false) {
    const url = new URL(location.href);
    url.searchParams.set('tab', tab.id.replace('tab-', ''));
    url.hash = '';
    navigateURL(url, focus);
  }
  window.MareCaseNavigation = { navigate: navigateURL };
  window.MwsTabs.bind(list, tab => navigate(tab, true));
  function syncRoute() {
    select(routeTab(new URL(location.href)));
    publishRoute();
    if (location.hash) reveal(location.hash.slice(1));
  }
  window.addEventListener('popstate', syncRoute);
  window.addEventListener('hashchange', syncRoute);
  publishRoute();
})();
