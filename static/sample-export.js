(() => {
  const form = document.querySelector('#panel-review form[action$="/archive"]');
  const categorySelect = document.querySelector(
    '.asset-form select[name="category"]',
  );
  const caseId = document.querySelector(".asset-form")?.dataset.caseId;
  const standard = form?.querySelector(
    'button[name="archive_type"][value="standard"]',
  );
  const option = form?.querySelector("#include-samples-option");
  const checkbox = option?.querySelector('input[name="include_samples"]');
  if (!form || !standard || !option || !checkbox || !caseId) return;
  async function update() {
    try {
      const response = await fetch(
        "/cases/" + caseId + "/assets?category=samples",
        { cache: "no-store" },
      );
      if (!response.ok) return;
      const result = await response.json();
      const hasSamples = result.files.some(
        (file) =>
          file.path.startsWith("samples/") &&
          file.path.toLowerCase().endsWith(".zip"),
      );
      option.hidden = !hasSamples;
      if (!hasSamples) checkbox.checked = false;
    } catch (_) {}
  }
  categorySelect?.addEventListener("change", () => {
    if (categorySelect.value === "samples") update();
  });
  window.addEventListener("mare:assets-changed", (event) => {
    if (event.detail?.category === "samples") update();
  });
  update();
})();
