(() => {
  const list = document.querySelector(".case-tabs");
  if (!list) return;
  const allTabs = [...list.querySelectorAll('[role="tab"]')];
  const tabs = allTabs.filter((tab) => !tab.disabled);
  const key = `mare-case-tab-${list.dataset.caseId}`;
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
  const requested = new URLSearchParams(location.search).get("tab");
  const anchorPanel =
    location.hash &&
    document.getElementById(location.hash.slice(1))?.closest(".case-tab-panel");
  select(
    tabs.find(
      (tab) =>
        anchorPanel && tab.getAttribute("aria-controls") === anchorPanel.id,
    ) ||
      tabs.find((tab) => tab.id === "tab-" + requested) ||
      tabs.find((tab) => tab.id === saved) ||
      tabs[0],
  );
  const initialURL = new URL(location.href);
  initialURL.searchParams.set('tab',list.querySelector('[aria-selected="true"]').id.replace('tab-',''));
  history.replaceState(history.state,'',initialURL);
  function reveal(id) {
    const target = document.getElementById(id);
    if (target) {
      if (target.tagName === "DETAILS") target.open = true;
      target.scrollIntoView({ block: "start" });
    }
  }
  if (location.hash)
    requestAnimationFrame(() => reveal(location.hash.slice(1)));
  document.querySelectorAll("[data-case-tab]").forEach((link) =>
    link.addEventListener("click", (event) => {
      const tab = tabs.find(
        (item) => item.id === "tab-" + link.dataset.caseTab,
      );
      if (!tab) return;
      event.preventDefault();
      select(tab);
      history.replaceState(null, "", link.getAttribute("href"));
      reveal(link.dataset.caseTarget);
    }),
  );
  function navigate(tab, focus = false) {
    select(tab, focus);
    const url = new URL(location.href);
    url.searchParams.set("tab", tab.id.replace("tab-", ""));
    url.hash = "";
    if(url.href!==location.href)history.pushState(history.state, "", url);
  }
  window.MwsTabs.bind(list,tab=>navigate(tab,true));
  window.addEventListener('popstate',()=>{const requested=new URLSearchParams(location.search).get('tab');select(tabs.find(tab=>tab.id==='tab-'+requested)||tabs[0]);});
})();
