(() => {
  const root = document.getElementById("reference-workspace");
  if (!root) return;
  const cid = root.dataset.caseId,
    locked = root.dataset.locked === "true",
    status = document.getElementById("reference-status"),
    table = document.getElementById("reference-table");
  let state,
    dirty = false,
    busy = false;
  function changed() {
    dirty = true;
    status.textContent = "Unsaved changes";
  }
  function editable() {
    root.querySelector("fieldset").disabled = locked || busy;
    table
      .querySelectorAll("td[data-column]")
      .forEach(
        (cell) =>
          (cell.contentEditable = locked || busy ? "false" : "plaintext-only"),
      );
  }
  function focusCell(row, column) {
    table.tBodies[0].rows[row]
      ?.querySelector(`td[data-column="${column}"]`)
      ?.focus();
  }
  function render() {
    table.tHead.replaceChildren();
    table.tBodies[0].replaceChildren();
    const head = table.tHead.insertRow();
    for (const name of ["Link", "Description", ""]) {
      const cell = document.createElement("th");
      cell.textContent = name;
      cell.scope = "col";
      head.append(cell);
    }
    state.rows.forEach((row, index) => {
      const tr = table.tBodies[0].insertRow();
      row.forEach((value, column) => {
        const cell = tr.insertCell();
        cell.dataset.column = column;
        cell.textContent = value;
        cell.tabIndex = locked ? -1 : 0;
        cell.setAttribute(
          "aria-label",
          `Row ${index + 1}, ${state.columns[column]}`,
        );
        cell.setAttribute("role", "textbox");
        cell.setAttribute("aria-multiline", "true");
        cell.addEventListener("input", () => {
          state.rows[index][column] = cell.innerText.replace(/\r/g, "");
          changed();
        });
        cell.addEventListener("keydown", (event) => {
          if (locked || busy) return;
          if (event.key === "Tab") {
            event.preventDefault();
            let next = index * 2 + column + (event.shiftKey ? -1 : 1);
            if (next < 0) {
              document.getElementById("add-reference").focus();
              return;
            }
            if (next >= state.rows.length * 2) {
              state.rows.push(["", ""]);
              changed();
              render();
            }
            focusCell(Math.floor(next / 2), next % 2);
          } else if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (index === state.rows.length - 1) {
              state.rows.push(["", ""]);
              changed();
              render();
            }
            focusCell(index + 1, column);
          }
        });
        cell.addEventListener("paste", (event) => {
          if (locked || busy) {
            event.preventDefault();
            return;
          }
          event.preventDefault();
          const text = event.clipboardData.getData("text/plain"),
            selection = window.getSelection();
          if (!selection.rangeCount) return;
          const range = selection.getRangeAt(0);
          if (!cell.contains(range.commonAncestorContainer)) return;
          range.deleteContents();
          const node = document.createTextNode(text);
          range.insertNode(node);
          range.setStartAfter(node);
          range.collapse(true);
          selection.removeAllRanges();
          selection.addRange(range);
          state.rows[index][column] = cell.innerText.replace(/\r/g, "");
          changed();
        });
      });
      const action = tr.insertCell(),
        remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Delete";
      remove.className = "reference-delete";
      remove.setAttribute("aria-label", `Delete reference row ${index + 1}`);
      remove.disabled = locked;
      remove.addEventListener("click", () => {
        if (busy || locked) return;
        state.rows.splice(index, 1);
        changed();
        render();
      });
      action.append(remove);
    });
    editable();
  }
  function addRow() {
    state.rows.push(["", ""]);
    changed();
    render();
    focusCell(state.rows.length - 1, 0);
  }
  async function request(path, data) {
    const response = await fetch(
      `/cases/${cid}/references${path}`,
      data ? { method: "POST", body: data } : {},
    );
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Request failed");
    return result;
  }
  function data() {
    const form = new FormData();
    form.set("csrf", root.dataset.csrf);
    form.set("revision", state.revision);
    return form;
  }
  async function save() {
    const form = data();
    form.set("rows", JSON.stringify(state.rows));
    state = await request("", form);
    dirty = false;
    autosaveTimer.reset();
    status.textContent = "Saved to supporting/references.csv";
    render();
  }
  function run(fn) {
    return async () => {
      if (busy || locked || !state) return;
      busy = true;
      editable();
      try {
        await fn();
      } catch (e) {
        status.textContent = e.message;
      } finally {
        busy = false;
        editable();
      }
    };
  }
  document.getElementById("add-reference").addEventListener("click", () => {
    if (state && !busy && !locked) addRow();
  });
  document.getElementById("save-references").addEventListener(
    "click",
    run(async () => {
      autosaveTimer.reset();
      await save();
    }),
  );
  request("")
    .then((result) => {
      state = result;
      render();
      status.textContent = locked
        ? "Read-only. Reopen the case to edit references."
        : "Ready. Click a cell to edit; Tab moves between cells, Enter moves down, and Shift+Enter adds a line break.";
    })
    .catch((e) => (status.textContent = e.message));
  const autosaveTimer = window.MareAutosave.register({
    onCountdown: (seconds, running, paused) => {
      const label = document.getElementById("save-references-countdown");
      if (label)
        label.textContent = running
          ? "Autosaving…"
          : paused
            ? "Autosave paused"
            : "Autosave in " +
              Math.floor(seconds / 60) +
              ":" +
              String(seconds % 60).padStart(2, "0");
    },
    canSave: () => state && !busy && !locked,
    save: async () => {
      busy = true;
      const snapshot = JSON.stringify(state.rows),
        form = data();
      form.set("rows", snapshot);
      form.set("automatic", "1");
      try {
        const result = await request("", form);
        state.revision = result.revision;
        dirty = JSON.stringify(state.rows) !== snapshot;
        status.textContent =
          "Autosaved to supporting/references.csv at " +
          new Date().toLocaleTimeString() +
          (dirty ? " — newer changes pending" : "");
      } finally {
        busy = false;
      }
    },
    onError: (error) => {
      status.textContent = "Autosave failed: " + error.message;
    },
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty || busy) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
