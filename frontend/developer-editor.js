import { languageService } from "./developer-language";
import { debugging } from "./developer-debug";
import { DeveloperProtocol } from "./developer-protocol";
import { EditorState, Compartment } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, drawSelection, highlightActiveLine, highlightActiveLineGutter } from "@codemirror/view";
import { history, defaultKeymap, historyKeymap, indentWithTab } from "@codemirror/commands";
import { languages } from "@codemirror/language-data";
import { LanguageDescription, syntaxHighlighting, bracketMatching, indentOnInput, foldGutter, foldKeymap, indentUnit } from "@codemirror/language";
import { search, searchKeymap, highlightSelectionMatches } from "@codemirror/search";
async function mountDeveloperEditor({ theme, highlighting }) {
  const root = document.querySelector("[data-developer-editor]");
  if (!root) return;
  const q = (s) => root.querySelector(s), base = root.dataset.base, csrf = root.dataset.csrf;
  const status = q(".ide-status"), output = q("[data-console]"), tabs = q(".ide-tabs"), tree = q("[data-files]");
  const buffers = /* @__PURE__ */ new Map();
  let selected = null, plugin = null, current = null, permissions = [], view, language, debuggerUI, runTimer, runId, saving, selectionGeneration = 0;
  const wrap = new Compartment(), indent = new Compartment(), access = new Compartment();
  const preference = "mws-developer-layout:" + document.body.dataset.userLayout;
  let prefs = {};
  try {
    prefs = JSON.parse(localStorage.getItem(preference) || "{}");
  } catch {
  }
  for (const key of ["explorer", "docs"]) {
    root.classList.toggle("ide-hide-" + key, prefs[key] === false);
    q("[data-command=" + key + "]").setAttribute("aria-expanded", String(prefs[key] !== false));
  }
  function remember() {
    try {
      localStorage.setItem(preference, JSON.stringify(prefs));
    } catch {
    }
  }
  for (const [panel, key, min, max] of [[".ide-explorer", "left", 140, 320], [".ide-docs", "right", 160, 360]]) {
    const node = q(panel), handle = document.createElement("div");
    handle.className = "ide-resize";
    handle.tabIndex = 0;
    handle.role = "separator";
    handle.setAttribute("aria-label", "Resize " + (key === "left" ? "Explorer" : "SDK help"));
    handle.setAttribute("aria-orientation", "vertical");
    const apply = (value) => {
      prefs[key] = Math.max(min, Math.min(max, value));
      root.style.setProperty("--ide-" + key, prefs[key] + "px");
      handle.setAttribute("aria-valuenow", prefs[key]);
    };
    handle.setAttribute("aria-valuemin", min);
    handle.setAttribute("aria-valuemax", max);
    apply(Number(prefs[key]) || (key === "left" ? 200 : 220));
    handle.onkeydown = (e) => {
      if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
        e.preventDefault();
        apply(prefs[key] + (e.key === "ArrowRight" ? 1 : -1) * (key === "right" ? -10 : 10));
        remember();
      }
    };
    handle.onpointerdown = (e) => {
      e.preventDefault();
      const initial = e.clientX, width = prefs[key];
      handle.setPointerCapture(e.pointerId);
      handle.onpointermove = (event) => apply(width + (event.clientX - initial) * (key === "right" ? -1 : 1));
      const end = () => {
        handle.onpointermove = null;
        remember();
      };
      handle.onpointerup = end;
      handle.onpointercancel = end;
    };
    node.append(handle);
  }
  const bottom = q(".ide-bottom");
  if (prefs.bottom) bottom.style.height = prefs.bottom + "px";
  new ResizeObserver(() => {
    if (bottom.open && bottom.offsetHeight > 80) {
      prefs.bottom = bottom.offsetHeight;
      remember();
    }
  }).observe(bottom);
  function message(text) {
    status.textContent = text;
  }
  function log(value) {
    q("[data-execution-history]").hidden = true;
    output.hidden = false;
    output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    q(".ide-bottom").open = true;
  }
  async function api(path = "", data, extra) {
    const options = { credentials: "same-origin" };
    if (data !== void 0) {
      const form = extra || new FormData();
      form.set("csrf", csrf);
      form.set("payload", JSON.stringify(data));
      options.method = "POST";
      options.body = form;
    }
    const response = await fetch(base + path, options);
    if (!response.ok) {
      let text = await response.text();
      try {
        text = JSON.parse(text).error || text;
      } catch {
        const doc = new DOMParser().parseFromString(text, "text/html");
        text = doc.querySelector("p")?.textContent || response.statusText;
      }
      throw new Error(text);
    }
    return response.json();
  }
  function symbol(value) {
    q("[data-symbol-info]").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }
  function context() {
    const inputs = JSON.parse(q("[data-inputs]").value || "{}");
    return { case_id: q("[data-case]").value ? Number(q("[data-case]").value) : null, artifact: q("[data-artifact]").value || null, inputs, ...q("[data-version]").value ? { version: q("[data-version]").value } : {} };
  }
  async function openLine(path, line) {
    await openFile(path);
    const position = view.state.doc.line(Math.min(view.state.doc.lines, line + 1)).from;
    view.dispatch({ selection: { anchor: position }, effects: EditorView.scrollIntoView(position, { y: "center" }) });
  }
  const protocolOptions = { root, base: base.replace(/\/plugins$/, ""), csrf, plugin: () => selected, view: () => view, current: () => current, contents: () => view?.state.doc.toString() || "", log, symbol, inspect: symbol, open: openLine, context };
  language = languageService(protocolOptions);
  debuggerUI = debugging(protocolOptions);
  function dirty() {
    return [...buffers.values()].some((b) => b.text !== b.saved);
  }
  function tabLabels() {
    tabs.replaceChildren();
    for (const [path, b] of buffers) {
      const button = document.createElement("button");
      button.type = "button";
      button.role = "tab";
      button.setAttribute("aria-selected", String(path === current));
      button.textContent = path + (b.text !== b.saved ? " \u25CF" : "");
      button.onclick = () => openBuffer(path);
      tabs.append(button);
    }
  }
  function storeState() {
    if (current && view) {
      const b = buffers.get(current);
      b.state = view.state;
      b.text = view.state.doc.toString();
    }
  }
  function saveAll() {
    if(!saving)saving=saveBuffers().finally(()=>{saving=null;});
    return saving;
  }
  async function saveBuffers() {
    storeState();
    const pid=selected,draft=plugin;
    for(const [path,b] of [...buffers]) {
      if(b.text===b.saved)continue;
      const text=b.text;
      const result=await api('/'+pid+'/files',{revision:draft.revision,path,text});
      draft.revision=result.revision;b.saved=text;
      if(selected===pid)tabLabels();
    }
    message(dirty()?'Saved snapshot; newer edits remain unsaved.':'All files saved.');
  }
  async function guard() {
    if (!dirty()) return true;
    const dialog = document.querySelector("#plugin-unsaved");
    return new Promise((resolve) => {
      dialog.showModal();
      let done = false;
      const finish = async (choice) => {
        if (done) return;
        done = true;
        dialog.close();
        try {
          if (choice === "save") await saveAll();
          if(choice==='discard'){
            if(saving)await saving;
            for(const b of buffers.values()){b.text=b.saved;b.state=null;}
            view?.destroy();view=null;if(current)await openBuffer(current);
          }
          resolve(choice !== "cancel" && (choice!=="save"||!dirty()));
        } catch (error) {
          message(error.message);
          resolve(false);
        }
        dialog.removeEventListener("click", click);
        dialog.removeEventListener("cancel", cancel);
      };
      const click = (e) => {
        const button = e.target.closest("[data-unsaved]");
        if (button) finish(button.dataset.unsaved);
      };
      const cancel = (e) => {
        e.preventDefault();
        finish("cancel");
      };
      dialog.addEventListener("click", click);
      dialog.addEventListener("cancel", cancel);
    });
  }
  function extensions() {
    return [language.extension, debuggerUI.extension, theme, syntaxHighlighting(highlighting), lineNumbers(), history(), drawSelection(), highlightActiveLine(), highlightActiveLineGutter(), bracketMatching(), indentOnInput(), foldGutter(), search({ top: true }), highlightSelectionMatches(), keymap.of([{ key: "Mod-s", run: () => {
      saveAll().catch((e) => message(e.message));
      return true;
    } }, indentWithTab, ...defaultKeymap, ...historyKeymap, ...searchKeymap, ...foldKeymap]), wrap.of(prefs.wrap === false ? [] : EditorView.lineWrapping), indent.of(indentUnit.of(prefs.indent === "tab" ? "	" : " ".repeat(Number(prefs.indent) || 4))), access.of(EditorState.readOnly.of(!permissions.includes("edit"))), EditorView.updateListener.of((update) => {
      if (update.docChanged && current) {
        const b = buffers.get(current);
        b.text = update.state.doc.toString();
        b.state = update.state;
        tabLabels();
        language.changed();
      }
    })];
  }
  async function openBuffer(path) {
    storeState();
    const b = buffers.get(path);
    if (!b) return;
    current = path;
    if (!b.state) {
      const language2 = LanguageDescription.matchFilename(languages, path);
      let support = [];
      if (language2) try {
        support = await language2.load();
      } catch {
      }
      b.state = EditorState.create({ doc: b.text, extensions: [...extensions(), support] });
    }
    if (current !== path || buffers.get(path)!==b) return;
    if (view) view.setState(b.state);
    else view = new EditorView({ state: b.state, parent: q(".ide-code") });
    tabLabels();
    view.focus();
    debuggerUI.refresh();
    language.sync().catch((e) => message(e.message));
  }
  async function openFile(path) {
    if (buffers.has(path)) return openBuffer(path);
    const pid=selected,generation=selectionGeneration;
    const response = await fetch(base + "/" + pid + "/file?path=" + encodeURIComponent(path), { credentials: "same-origin" });
    if (!response.ok) throw new Error("Unable to open file.");
    const raw = await response.arrayBuffer();
    if(selected!==pid||generation!==selectionGeneration)return;
    let text;
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
      if (text.includes("\0")) throw new Error();
    } catch {
      log({ path, size: raw.byteLength, message: "Binary resource. Use its download link in the file explorer." });
      return;
    }
    buffers.set(path, { text, saved: text, state: null });
    await openBuffer(path);
  }
  function fileTree() {
    tree.replaceChildren();
    const nodes = /* @__PURE__ */ new Map([["", tree]]);
    const entries = [...plugin.files].sort((a, b) => a.path.localeCompare(b.path));
    function directory(path) {
      if (nodes.has(path)) return nodes.get(path);
      const split = path.lastIndexOf("/"), parent = directory(split < 0 ? "" : path.slice(0, split)), details = document.createElement("details"), summary = document.createElement("summary");
      summary.textContent = path.slice(split + 1);
      details.open = true;
      details.append(summary);
      parent.append(details);
      nodes.set(path, details);
      return details;
    }
    for (const item of entries) {
      if (item.directory) {
        directory(item.path);
        continue;
      }
      const slash = item.path.lastIndexOf("/"), parent = directory(slash < 0 ? "" : item.path.slice(0, slash)), line = document.createElement("div"), button = document.createElement("button");
      button.type = "button";
      button.textContent = item.path.slice(slash + 1);
      button.title = item.path;
      button.onclick = () => openFile(item.path).catch((e) => message(e.message));
      const download = document.createElement("a");
      download.href = base + "/" + selected + "/file?path=" + encodeURIComponent(item.path);
      download.textContent = "\u2193";
      download.setAttribute("aria-label", "Download " + item.path);
      download.className = "ide-download";
      line.className = "ide-file-line";
      line.append(button, download);
      parent.append(line);
    }
  }
  async function refreshDetail() {
    const pid=selected,result=await api("/"+pid);
    if(selected!==pid)return;
    plugin=result;
    q("[data-plugin-title]").textContent = plugin.name + " \xB7 " + plugin.development;
    const select = q("[data-version]"), previous = select.value;
    select.replaceChildren(new Option("Draft / current publication", ""));
    for (const version of plugin.versions) select.add(new Option(version.version, version.version));
    select.value = previous;
    fileTree();
  }
  async function selectPlugin(id) {
    if (id === selected) return;
    const generation=++selectionGeneration;
    if (!await guard() || generation!==selectionGeneration) return;
    await language.close();
    await debuggerUI.stop();
    if(generation!==selectionGeneration)return;
    buffers.clear();
    current = null;
    view?.destroy();
    view = null;
    selected = id;
    await refreshDetail();
    if(selected!==id||generation!==selectionGeneration)return;
    tabLabels();
    await openFile(plugin.files.find((f) => f.path === "main.py")?.path || plugin.files.find((f) => !f.directory)?.path);
    message(plugin.id + " \xB7 revision " + plugin.revision);
    renderPlugins();
  }
  let listing = [];
  function renderPlugins() {
    const needle = q("[data-plugin-search]").value.toLowerCase(), container = q("[data-plugins]");
    container.replaceChildren();
    for (const row of listing.filter((p) => (p.name + " " + p.id).toLowerCase().includes(needle))) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = row.name;
      button.setAttribute("aria-current", String(row.id === selected));
      const meta = document.createElement("small");
      meta.textContent = row.development + " \xB7 " + (row.enabled ? "Enabled" : "Disabled");
      button.append(meta);
      button.onclick = () => selectPlugin(row.id).catch((e) => message(e.message));
      container.append(button);
    }
    if (!container.children.length) {
      const empty = document.createElement("p");
      empty.textContent = "No plugins found.";
      container.append(empty);
    }
  }
  async function reload() {
    const data = await api();
    listing = data.plugins;
    permissions = data.permissions;
    root.querySelectorAll("[data-permission]").forEach((el) => {
      el.hidden = !permissions.includes(el.dataset.permission);
    });
    q("[data-worker-status]").textContent = data.worker.message;
    const templateSelect = document.querySelector("[data-templates]");
    templateSelect.replaceChildren();
    for (const t of data.templates) {
      const option = document.createElement("option");
      option.value = t.id;
      option.textContent = t.name;
      templateSelect.append(option);
    }
    const allowed = document.querySelector("[data-data-permissions]");
    allowed.replaceChildren();
    for (const name of data.data_permissions) {
      const label = document.createElement("label"), input = document.createElement("input");
      input.type = "checkbox";
      input.name = "permission";
      input.value = name;
      label.append(input, document.createTextNode(name));
      allowed.append(label);
    }
    renderPlugins();
    return data;
  }
  async function fileOperation(operation, path, extra = {}) {
    if (!selected) throw new Error("Select a plugin first.");
    const result = await api("/" + selected + "/files", { operation, path, revision: plugin.revision, ...extra });
    plugin.revision = result.revision;
    await refreshDetail();
  }
  function chooseFile(accept) {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      if (accept) input.accept = accept;
      input.onchange = () => resolve(input.files[0]);
      input.oncancel = () => resolve(null);
      input.click();
    });
  }
  const configDialog = document.querySelector("#plugin-configuration");
  configDialog.querySelector("[data-configuration-cancel]").onclick = () => configDialog.close();
  configDialog.querySelector("form").onsubmit = async (event) => {
    event.preventDefault();
    const values = {}, secrets = {}, clear_secrets = [];
    for (const input of configDialog.querySelectorAll("[name]")) {
      if (input.dataset.secret === "true") {
        if (input.value) secrets[input.name] = input.value;
      } else values[input.name] = input.dataset.enum ? JSON.parse(input.value) : input.dataset.kind === "boolean" ? input.checked : input.dataset.kind === "number" ? Number(input.value) : input.value;
    }
    for (const input of configDialog.querySelectorAll("[data-clear-secret]:checked")) clear_secrets.push(input.dataset.clearSecret);
    try {
      await api("/" + selected + "/configuration", { values, secrets, clear_secrets });
      configDialog.querySelector("[data-configuration-fields]").replaceChildren();
      configDialog.close();
      message("Configuration saved. Secret values are never returned.");
    } catch (error) {
      configDialog.querySelector("[data-configuration-error]").textContent = error.message;
    }
  };
  const wizard = document.querySelector("#plugin-wizard");
  document.querySelector("[data-wizard-cancel]").onclick = () => wizard.close();
  wizard.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const result = await api("", { template: form.get("template"), manifest: { id: form.get("id"), name: form.get("name"), description: form.get("description"), version: form.get("version"), author: form.get("author"), permissions: form.getAll("permission"), dependencies: form.get("dependencies").split("\n").map((x) => x.trim()).filter(Boolean) } });
      wizard.close();
      await reload();
      await selectPlugin(result.id);
    } catch (error) {
      wizard.querySelector("[data-wizard-error]").textContent = error.message;
    }
  });
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-command]");
    if (!button) return;
    const command = button.dataset.command;
    try {
      if (command === "new") {
        if (!await guard()) return;
        wizard.querySelector("[data-wizard-error]").textContent = "";
        wizard.showModal();
      } else if (command === "save") await saveAll();
      else if (command === "refresh") {
        if (!await guard()) return;
        const id = selected;
        selected = null;
        await reload();
        if (id) await selectPlugin(id);
      } else if (command === "export") {
        if (!selected) throw new Error("Select a plugin first.");
        if (!await guard()) return;
        location.href = base + "/" + selected + "/export";
      } else if (command === "validate") {
        if (!selected) throw new Error("Select a plugin first.");
        await saveAll();
        log(await api("/" + selected + "/static-validation", {}));
      } else if (command === "language") {
        if (!selected) throw Error("Select a plugin first.");
        await saveAll();
        await language.close();
        await language.start();
        message("Python language server connected. F12: definition \xB7 Shift F12: references \xB7 Ctrl/\u2318 Shift Space: signature.");
      } else if (command === "symbols") await language.symbols();
      else if (["validate-worker", "test", "run"].includes(command)) {
        if (!selected) throw Error("Select a plugin first.");
        await saveAll();
        const mode = command === "validate-worker" ? "validate" : command;
        const data = context();
        if(mode==='run'){const version=data.version||plugin.published_version,record=plugin.versions.find(item=>item.version===version);if(!confirm('Run published '+version+' on case '+(data.case_id??'none')+'?\nRequested API permissions: '+(record?.permissions?.join(', ')||'(none)')+'\nArtifact: '+(data.artifact||'none')))return;}
        const result = await api("/" + selected + "/" + mode, data);
        runId = result.id;
        clearInterval(runTimer);
        const poll = async () => {
          const response = await fetch(base.replace(/\/plugins$/, "") + "/executions/" + runId, { credentials: "same-origin" });
          if (!response.ok) {
            clearInterval(runTimer);
            throw Error("Worker poll failed.");
          }
          const state = await response.json();
          log(state);
          if (!["Starting", "Running"].includes(state.status)) {
            clearInterval(runTimer);
            await refreshDetail();
          }
        };
        runTimer = setInterval(() => poll().catch((e) => message(e.message)), 750);
        log(result);
      } else if (command === "cancel") {
        if (runId) {
          const client = new DeveloperProtocol({ base: base.replace(/\/plugins$/, ""), csrf });
          log(await client.http("/executions/" + runId + "/cancel", {}));
          clearInterval(runTimer);
        }
      } else if (command === "publish") {
        await saveAll();
        if (confirm("Publish this immutable version after its isolated validation and test results?")) {
          log(await api("/" + selected + "/publish", { revision: plugin.revision }));
          await refreshDetail();
        }
      } else if (command === "enable") {
        log(await api("/" + selected + "/enable", { enabled: !plugin.enabled }));
        await refreshDetail();
      } else if (command === "versions") {
        log(plugin.versions);
        const version = prompt("Published versions: " + plugin.versions.map((v) => v.version).join(", ") + ". Enter a version to roll back, or Cancel.");
        if (version) {
          log(await api("/" + selected + "/rollback", { version }));
          await refreshDetail();
        }
      } else if (command === "configure") {
        if (!selected) throw Error("Select a plugin first.");
        const data = await api("/" + selected + "/configuration");
        const dialog = document.querySelector("#plugin-configuration"), container = dialog.querySelector("[data-configuration-fields]");
        container.replaceChildren();
        for (const [name, field] of Object.entries(data.schema)) {
          const label = document.createElement("label");
          label.textContent = name + (field.required ? " *" : "");
          let input;
          if (field.enum) {
            input = document.createElement("select");
            for (const item of field.enum) {
              const option = document.createElement("option");
              option.value = JSON.stringify(item);
              option.textContent = String(item);
              input.append(option);
            }
            input.dataset.enum = "true";
          } else {
            input = document.createElement("input");
            input.type = field.secret ? "password" : field.type === "boolean" ? "checkbox" : field.type === "number" ? "number" : "text";
            if (field.type === "number") input.step = "any";
          }
          input.name = name;
          input.dataset.kind = field.type;
          input.dataset.secret = String(Boolean(field.secret));
          input.autocomplete = "off";
          if (field.secret) input.placeholder = data.configured_secrets.includes(name) ? "Configured \u2014 leave blank to retain" : "Not configured";
          else if (field.type === "boolean") input.checked = Boolean(data.values[name] ?? field.default);
          else input.value = input.dataset.enum ? JSON.stringify(data.values[name] ?? field.default ?? field.enum[0]) : data.values[name] ?? field.default ?? "";
          label.append(input);
          if (field.description) {
            const hint = document.createElement("small");
            hint.textContent = field.description;
            label.append(hint);
          }
          if (field.secret && data.configured_secrets.includes(name)) {
            const clear = document.createElement("label"), checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.dataset.clearSecret = name;
            clear.append(checkbox, document.createTextNode("Clear stored " + name));
            label.append(clear);
          }
          container.append(label);
        }
        dialog.querySelector("[data-configuration-error]").textContent = "";
        dialog.showModal();
      } else if (command === "history") {
        if (selected) {
          const data = await api("/" + selected + "/history"), container = q("[data-execution-history]");
          container.replaceChildren();
          const heading = document.createElement("p");
          heading.textContent = "Latest " + data.executions.length + " executions";
          container.append(heading);
          for (const row of data.executions) {
            const line = document.createElement("div"), button2 = document.createElement("button");
            line.className = "ide-history-row";
            const text = document.createElement("span");
            text.textContent = [row.started_at, row.mode, row.plugin_version, row.status, row.duration === null ? "" : row.duration + "s"].join(" \xB7 ");
            button2.type = "button";
            button2.textContent = "Inspect " + row.id.slice(0, 8);
            button2.onclick = async () => {
              try {
                const response = await fetch(base.replace(/\/plugins$/, "") + "/executions/" + row.id, { credentials: "same-origin" });
                if (!response.ok) throw Error("Execution is unavailable.");
                log(await response.json());
              } catch (error) {
                message(error.message);
              }
            };
            line.append(text, button2);
            container.append(line);
          }
          container.hidden = false;
          output.hidden = true;
          q(".ide-bottom").open = true;
        }
      } else if (command === "console") q(".ide-bottom").open = true;
      else if (command === "focus") root.classList.toggle("ide-focused");
      else if (command === "explorer" || command === "docs") {
        if (command === "docs" && innerWidth <= 1100) {
          const open = root.classList.toggle("ide-docs-open");
          button.setAttribute("aria-expanded", String(open));
          return;
        }
        const hidden = root.classList.toggle("ide-hide-" + command);
        prefs[command] = !hidden;
        button.setAttribute("aria-expanded", String(!hidden));
        remember();
      } else if (command === "new-file" || command === "new-directory") {
        const path = prompt(command === "new-file" ? "New relative file path" : "New relative folder path");
        if (path) {
          await fileOperation(command === "new-file" ? "create" : "directory", path);
          if (command === "new-file") await openFile(path);
        }
      } else if (command === "rename") {
        if (!current) return;
        if (!await guard()) return;
        const path = prompt("New relative path", current);
        if (path && path !== current) {
          const previous = current;
          await fileOperation("rename", current, { target: path });
          buffers.delete(previous);
          current = null;
          await openFile(path);
        }
      } else if (command === "delete-file") {
        if (!current || !confirm("Delete " + current + "?")) return;
        await fileOperation("delete", current);
        buffers.delete(current);
        current = null;
        view?.destroy();
        view = null;
        tabLabels();
        if (buffers.size) await openBuffer(buffers.keys().next().value);
      } else if (command === "close-file") {
        if (!current || !await guard()) return;
        buffers.delete(current);
        current = null;
        view?.destroy();
        view = null;
        tabLabels();
        if (buffers.size) await openBuffer(buffers.keys().next().value);
      } else if (command === "upload") {
        if (!selected) return;
        const file = await chooseFile();
        if (file) {
          const path = prompt("Relative path for upload", file.name);
          if (path) {
            const extra = new FormData();
            extra.set("file", file);
            const result = await api("/" + selected + "/files", { operation: "upload", path, revision: plugin.revision }, extra);
            plugin.revision = result.revision;
            await refreshDetail();
          }
        }
      } else if (command === "import") {
        if (!await guard()) return;
        const file = await chooseFile(".zip");
        if (file) {
          const extra = new FormData();
          extra.set("archive", file);
          const response = await fetch(base.replace(/\/plugins$/, "/import"), { method: "POST", credentials: "same-origin", body: (extra.set("csrf", csrf), extra) });
          if (!response.ok) throw new Error("Import rejected: " + (new DOMParser().parseFromString(await response.text(), "text/html").querySelector("p")?.textContent || response.statusText));
          const result = await response.json();
          await reload();
          await selectPlugin(result.id);
        }
      } else if (command === "delete-plugin") {
        if (!selected || !await guard() || !confirm("Delete this plugin registration? Execution history is retained.")) return;
        await api("/" + selected + "/delete", { revision: plugin.revision });
        selected = null;
        plugin = null;
        buffers.clear();
        current = null;
        view?.destroy();
        view = null;
        tree.replaceChildren();
        tabLabels();
        await reload();
        message("Plugin deleted.");
      }
    } catch (error) {
      message(error.message);
    }
  });
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-debug]");
    if (button) {
      saveAll().then(() => debuggerUI.action(button.dataset.debug)).catch((e) => message(e.message));
    }
  });
  q("[data-case]").addEventListener("change", async () => {
    const select = q("[data-artifact]");
    select.replaceChildren(new Option("None", ""));
    if (!q("[data-case]").value) return;
    try {
      const response = await fetch(base.replace(/\/plugins$/, "") + "/cases/" + Number(q("[data-case]").value) + "/artifacts", { credentials: "same-origin" });
      if (!response.ok) throw Error("Artifact listing requires case asset permission.");
      const value = await response.json();
      for (const item of value.artifacts) select.add(new Option(item.path + " (" + item.size + " bytes)", item.path));
    } catch (error) {
      message(error.message);
    }
  });
  q("[data-plugin-search]").addEventListener("input", renderPlugins);
  q("[data-wrap]").checked = prefs.wrap !== false;
  q("[data-wrap]").onchange = (event) => {
    prefs.wrap = event.target.checked;
    for (const b of buffers.values()) if (b.state) b.state = b.state.update({ effects: wrap.reconfigure(prefs.wrap ? EditorView.lineWrapping : []) }).state;
    if (view) view.dispatch({ effects: wrap.reconfigure(prefs.wrap ? EditorView.lineWrapping : []) });
    remember();
  };
  q("[data-indent]").value = prefs.indent || "4";
  q("[data-indent]").onchange = (event) => {
    prefs.indent = event.target.value;
    for (const b of buffers.values()) if (b.state) b.state = b.state.update({ effects: indent.reconfigure(indentUnit.of(prefs.indent === "tab" ? "	" : " ".repeat(Number(prefs.indent)))) }).state;
    if (view) view.dispatch({ effects: indent.reconfigure(indentUnit.of(prefs.indent === "tab" ? "	" : " ".repeat(Number(prefs.indent)))) });
    remember();
  };
  window.addEventListener("pagehide", () => {
    language.close();
    debuggerUI.stop();
    clearInterval(runTimer);
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.addEventListener("click", async (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.ctrlKey || event.metaKey || link.target === "_blank" || link.hasAttribute("download") || link.href.includes("/file?") || link.href === location.href || !dirty()) return;
    event.preventDefault();
    if (await guard()) location.href = link.href;
  });
  try {
    await reload();
    message("Select a plugin, import an archive, or create a new draft.");
  } catch (error) {
    message(error.message);
  }
}
export {
  mountDeveloperEditor
};
