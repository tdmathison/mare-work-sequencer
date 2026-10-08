(() => {
  function select(tab) {
    const tabs = [...document.querySelectorAll("[data-archive-view]")];
    for (const item of tabs)
      item.setAttribute("aria-selected", String(item === tab));
    document
      .querySelectorAll("[data-archive-pane]")
      .forEach(
        (pane) =>
          (pane.hidden = pane.dataset.archivePane !== tab.dataset.archiveView),
      );
  }
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-archive-view]");
    if (tab) select(tab);
  });
  document.addEventListener("keydown", (event) => {
    const tab = event.target.closest("[data-archive-view]");
    if (!tab || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll("[data-archive-view]")],
      next = tabs[1 - tabs.indexOf(tab)];
    select(next);
    next.focus();
  });
})();
