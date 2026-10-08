(() => {
  const cid = document.querySelector(".case-tabs")?.dataset.caseId;
  if (!cid) return;
  const escape = (text) =>
    text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  function highlight(area) {
    const pre = area.previousElementSibling;
    area.parentElement.classList.add("enhanced");
    pre.innerHTML = window.MareMarkdownSyntax.renderMarkdown(area.value);
    pre.scrollTop = area.scrollTop;
    pre.scrollLeft = area.scrollLeft;
  }
  for (const dialog of document.querySelectorAll(".task-workspace-dialog")) {
    const form = dialog.querySelector("form"),
      section = dialog.querySelector(".manual-section"),
      area = section.querySelector(".markdown-input"),
      raw = section.querySelector("[data-task-raw]"),
      preview = section.querySelector("[data-task-preview]"),
      pane = section.querySelector(".markdown-preview"),
      editor = section.querySelector(".markdown-editor");
    let sequence = 0;
    function rawView() {
      sequence++;
      pane.hidden = true;
      editor.hidden = false;
      raw.setAttribute("aria-selected", "true");
      preview.setAttribute("aria-selected", "false");
    }
    raw.addEventListener("click", rawView);
    area.addEventListener("input", () => highlight(area));
    area.addEventListener("scroll", () => highlight(area));
    highlight(area);
    preview.addEventListener("click", async () => {
      const current = ++sequence;
      raw.setAttribute("aria-selected", "false");
      preview.setAttribute("aria-selected", "true");
      pane.hidden = false;
      editor.hidden = true;
      pane.textContent = "Rendering preview…";
      const data = new FormData();
      data.set("csrf", form.elements.csrf.value);
      data.set("text", area.value);
      try {
        const response = await fetch("/cases/" + cid + "/markdown-preview", {
          method: "POST",
          body: data,
        });
        const result = await response.json();
        if (!response.ok) throw Error(result.error || "Preview failed");
        if (current === sequence) pane.innerHTML = result.html;
      } catch (error) {
        if (current === sequence) pane.textContent = error.message;
      }
    });
    for (const tab of [raw, preview])
      tab.addEventListener("keydown", (event) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          const next =
            event.key === "Home"
              ? raw
              : event.key === "End"
                ? preview
                : tab === raw
                  ? preview
                  : raw;
          next.focus();
          next.click();
        }
      });
    dialog
      .querySelector("[data-close-task-dialog]")
      .addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      form.reset();
      area.dispatchEvent(new Event("input"));
      rawView();
      document.body.classList.remove("task-dialog-open");
    });
    dialog.addEventListener("cancel", () => {
      sequence++;
    });
  }
  for (const button of document.querySelectorAll("[data-open-task]"))
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.openTask);
      dialog.showModal();
      document.body.classList.add("task-dialog-open");
      dialog.querySelector(".markdown-input").dispatchEvent(new Event("input"));
      dialog.querySelector('[name="name"]').focus();
    });
})();
