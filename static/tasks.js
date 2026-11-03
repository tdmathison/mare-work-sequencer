(() => {
  const cid = document.querySelector(".case-tabs")?.dataset.caseId;
  if (!cid) return;
  function initialize(dialog) {
    if (dialog.dataset.initialized || !dialog.querySelector("[data-task-raw]")) return;
    dialog.dataset.initialized = 'true';
    window.MareEditors.init(dialog);
    const form = dialog.querySelector("form"),
      section = dialog.querySelector(".manual-section"),
      area = section.querySelector(".markdown-source"),
      raw = section.querySelector("[data-task-raw]"),
      preview = section.querySelector("[data-task-preview]"),
      pane = section.querySelector(".markdown-preview"),
      editor = section.querySelector(".markdown-editor");
    let sequence = 0, submitting = false;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (submitting) return;
      submitting = true;
      const status = section.querySelector('[data-editor-status]');
      try {
        await window.MareTaskCase.ensureEditable();
        const response = await fetch(form.action, {method:'POST', body:new FormData(form)});
        const identity = new DOMParser().parseFromString(await response.text(),'text/html').querySelector('.case-tabs');
        if (!response.ok || identity?.dataset.caseId !== cid || identity?.dataset.userId !== document.querySelector('.case-tabs').dataset.userId)
          throw Error('Task could not be saved. Check your session and Case permissions; your draft is retained.');
        dialog.close();
        await window.MareTaskCase.refresh();
        await window.MareCaseData.invalidate('tasks');
      } catch (error) { status.textContent = error.message; }
      finally { submitting = false; }
    });
    function rawView() {
      sequence++;
      pane.hidden = true;
      editor.hidden = false;
      markdown.restoreLayout();
      raw.setAttribute("aria-selected", "true");
      preview.setAttribute("aria-selected", "false");
    }
    raw.addEventListener("click", rawView);
    const markdown = window.MareEditors.get(area);
    preview.addEventListener("click", async () => {
      const current = ++sequence;
      raw.setAttribute("aria-selected", "false");
      preview.setAttribute("aria-selected", "true");
      markdown.preserveLayout();
      pane.hidden = false;
      editor.hidden = true;
      pane.textContent = "Rendering preview…";
      const data = new FormData();
      data.set("csrf", form.elements.csrf.value);
      data.set("text", markdown.getValue());
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
      markdown.measure();
      rawView();
      document.body.classList.remove("task-dialog-open");
    });
    dialog.addEventListener("cancel", () => {
      sequence++;
    });
  }
  for (const dialog of document.querySelectorAll('.task-workspace-dialog')) initialize(dialog);
  window.MareTaskDialogs = { async open(task) {
    let dialog = document.getElementById('edit-task-dialog-'+task.id);
    if (!dialog) {
      const response = await fetch('/cases/'+cid, {cache:'no-store'});
      if (!response.ok || response.redirected) throw Error('Unable to load the task editor. Your other drafts are retained.');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      dialog = page.getElementById('edit-task-dialog-'+task.id);
      if (!dialog) throw Error('This task is no longer available. Refresh the task list.');
      document.getElementById('panel-tasks').append(dialog); initialize(dialog);
    }
    const form = dialog.querySelector('form');
    form.elements.name.value = task.title; form.elements.priority.value = task.priority; form.elements.state.value = task.state;
    window.MareEditors.get(dialog.querySelector('.markdown-source')).setValue(task.body || '');
    dialog.showModal(); document.body.classList.add('task-dialog-open');
    window.MareEditors.get(dialog.querySelector('.markdown-source')).measure();
  }};
  for (const button of document.querySelectorAll("[data-open-task]"))
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.openTask);
      dialog.showModal();
      document.body.classList.add("task-dialog-open");
      window.MareEditors.get(dialog.querySelector(".markdown-source")).measure();
      dialog.querySelector('[name="name"]').focus();
    });
})();
