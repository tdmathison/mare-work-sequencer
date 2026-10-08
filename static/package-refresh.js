(() => {
  async function refresh(caseId) {
    try {
      const response = await fetch(`/cases/${caseId}?tab=package`, {
        cache: "no-store",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) return;
      const page = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      for (const id of ["panel-package", "panel-review"]) {
        const current = document.getElementById(id),
          updated = page.getElementById(id);
        if (current && updated) current.innerHTML = updated.innerHTML;
      }
    } catch (_) {}
  }
  const caseId = document.querySelector(".asset-form")?.dataset.caseId,
    assetList = document.getElementById("asset-files");
  if (caseId && assetList) {
    let timer;
    new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => refresh(caseId), 60);
    }).observe(assetList, { childList: true, subtree: true });
  }
  window.MarePackage = { refresh };
})();
