(() => {
  const form = document.getElementById("note-form");
  if (!form || form.querySelector("fieldset:disabled")) return;
  const status = document.getElementById("draft-status");
  let timer,
    pending = false,
    saving = false;
  const backupKey = `mare-draft-${form.dataset.userId}-${form.dataset.draftUrl}`;
  const fields = ["title", "body"];
  // Recover unsent text after a network interruption. Clear only after a confirmed server save.
  try {
    const local = JSON.parse(sessionStorage.getItem(backupKey) || "null");
    if (local) {
      fields.forEach((k) => (form.elements[k].value = local[k]));
      status.textContent = "Unsent draft restored";
    }
  } catch (_) {}
  async function save() {
    if (saving) {
      pending = true;
      return;
    }
    saving = true;
    pending = false;
    status.textContent = "Saving draft…";
    const snapshot = Object.fromEntries(
      fields.map((k) => [k, form.elements[k].value]),
    );
    try {
      const data = new FormData();
      data.set("csrf", form.elements.csrf.value);
      fields.forEach((k) => data.set(k, snapshot[k]));
      const r = await fetch(form.dataset.draftUrl, {
        method: "POST",
        body: data,
      });
      const body = await r.json();
      if (!r.ok || !body.saved) throw Error();
      status.textContent = "Draft saved";
      if (fields.every((k) => form.elements[k].value === snapshot[k]))
        sessionStorage.removeItem(backupKey);
    } catch (_) {
      status.textContent = "Draft not saved — retrying on next edit";
    }
    saving = false;
    if (pending) save();
  }
  fields.forEach((k) =>
    form.elements[k].addEventListener("input", () => {
      try {
        sessionStorage.setItem(
          backupKey,
          JSON.stringify(
            Object.fromEntries(fields.map((k) => [k, form.elements[k].value])),
          ),
        );
      } catch (_) {}
      status.textContent = "Unsaved draft";
      clearTimeout(timer);
      timer = setTimeout(save, 800);
    }),
  );
  // Finish draft saving before adding the note so a late autosave cannot recreate a submitted draft.
  let submitting = false;
  form.addEventListener("submit", async (event) => {
    if (submitting) return;
    event.preventDefault();
    clearTimeout(timer);
    pending = false;
    while (saving) await new Promise((r) => setTimeout(r, 50));
    try {
      sessionStorage.removeItem(backupKey);
    } catch (_) {}
    submitting = true;
    form.requestSubmit();
  });
  window.addEventListener("beforeunload", (event) => {
    if (
      status.textContent === "Unsaved draft" ||
      status.textContent.startsWith("Draft not saved") ||
      saving
    ) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
