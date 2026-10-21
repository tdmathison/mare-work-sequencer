import { EditorState, Compartment, Transaction } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, drawSelection, hoverTooltip } from "@codemirror/view";
import { history, historyKeymap, defaultKeymap, indentWithTab, undo, redo, undoDepth, redoDepth, isolateHistory } from "@codemirror/commands";
import { StreamLanguage, syntaxHighlighting, bracketMatching, indentOnInput, codeFolding, foldGutter, foldKeymap, foldService, indentUnit } from "@codemirror/language";
import { autocompletion, completionKeymap, startCompletion } from "@codemirror/autocomplete";
import { setDiagnostics, lintGutter } from "@codemirror/lint";
import { search, searchKeymap } from "@codemirror/search";
import { PROFILE, START, MODULES, META, SNIPPETS, lex, analyze, ruleAt, suggestions, metadataEdit } from "./yara-language";
function mountYaraTool({ theme, highlighting }) {
  const root = document.querySelector("[data-yara-tool]");
  if (!root || root.dataset.initialized) return;
  root.dataset.initialized = "true";
  const $ = (s) => root.querySelector(s), $$ = (s) => [...root.querySelectorAll(s)];
  let cases = [], caseId = "", opened = null, clean = START, exact = START, newline = "\n", revision = 0, documentGeneration = 0, loading = false, ready = false, draftTimer, checkTimer, uiTimer, job = null, jobSerial = 0, engine = { available: false }, compilerProblems = [], analysis = analyze(START), draftQueue = Promise.resolve(), leaving = false, importPreview = null;
  const wrap = new Compartment(), hist = new Compartment();
  const language = StreamLanguage.define({ startState: () => ({ comment: false, depth: 0, section: null }), token(stream, state) {
    if (state.comment) {
      if (stream.skipTo("*/")) {
        stream.match("*/");
        state.comment = false;
      } else stream.skipToEnd();
      return "comment";
    }
    if (stream.eatSpace()) return null;
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match("/*")) {
      state.comment = true;
      return "comment";
    }
    if (stream.match(/"(?:\\.|[^"\\])*"?/)) return "string";
    if (stream.match(/\/(?:\\.|[^/\\])+\/[is]*/)) return "regexp";
    if (stream.match(/[$#@!][A-Za-z_]\w*/)) return "variableName";
    if (stream.match(/\b(?:rule|private|global|import|include|meta|strings|condition|and|or|not|any|all|of|them|for|in|at|true|false|defined|matches|contains|ascii|wide|nocase|fullword|xor|base64|base64wide)\b/)) {
      if (["meta", "strings", "condition"].includes(stream.current())) state.section = stream.current();
      return "keyword";
    }
    if (stream.match(/\b(?:0x[\da-fA-F]+|\d+(?:KB|MB)?)\b/)) return "number";
    const char = stream.next();
    if (char === "{") state.depth++;
    if (char === "}") {
      state.depth = Math.max(0, state.depth - 1);
      if (!state.depth) state.section = null;
    }
    return null;
  }, indent(state, textAfter, context) {
    const closing = /^\s*}/.test(textAfter), section = /^\s*(meta|strings|condition)\s*:/.test(textAfter);
    return Math.max(0, state.depth - (closing ? 1 : 0) + (state.section && !closing && !section ? 1 : 0)) * context.unit;
  }, languageData: { commentTokens: { line: "//", block: { open: "/*", close: "*/" } } } });
  const completion = (context) => {
    const result = suggestions(context.state.doc.toString(), context.pos);
    return { ...result, validFor: /^[$#@!]?\w*$/ };
  };
  const view = new EditorView({ parent: $("[data-yara-editor]"), state: EditorState.create({ doc: START, extensions: [
    hist.of(history()),
    lineNumbers(),
    drawSelection(),
    theme,
    syntaxHighlighting(highlighting),
    language,
    indentUnit.of("    "),
    bracketMatching(),
    indentOnInput(),
    codeFolding(),
    foldGutter(),
    search(),
    lintGutter(),
    autocompletion({ override: [completion] }),
    wrap.of(EditorView.lineWrapping),
    keymap.of([indentWithTab, ...completionKeymap, ...foldKeymap, ...searchKeymap, ...historyKeymap, ...defaultKeymap]),
    foldService.of((state, start, end) => {
      const tokens = lex(state.doc.toString()).tokens.filter((t) => t.kind === "punct");
      let index = tokens.findIndex((t) => t.from >= start && t.from <= end && t.value === "{");
      if (index < 0) return null;
      const open = tokens[index];
      let depth = 1;
      for (index++; index < tokens.length; index++) {
        if (tokens[index].value === "{") depth++;
        if (tokens[index].value === "}") {
          depth--;
          if (!depth) return { from: open.to, to: tokens[index].from };
        }
      }
      return null;
    }),
    hoverTooltip((v, pos) => {
      const text = v.state.doc.toString(), word = text.slice(0, pos).match(/[\w.]*$/)?.[0] + text.slice(pos).match(/^\w*/)?.[0], parts = word.split("."), description = parts.length === 2 ? MODULES[parts[0]]?.[parts[1]] : null;
      if (!description) return null;
      return { pos, end: pos, create() {
        const dom = document.createElement("div");
        dom.textContent = PROFILE + " \xB7 " + word + " \xB7 " + description;
        return { dom };
      } };
    }),
    EditorView.contentAttributes.of({ "aria-label": "YARA source" }),
    EditorView.updateListener.of((update) => {
      $("[data-undo]").disabled = !undoDepth(update.state);
      $("[data-redo]").disabled = !redoDepth(update.state);
      if (update.docChanged && !loading) {
        revision++;
        exact = null;
        compilerProblems = [];
        $("[data-validation]").textContent = "Changed since last validation";
        status();
        scheduleDraft();
        clearTimeout(checkTimer);
        checkTimer = setTimeout(() => {
          if (engine.available && !job) run("validate");
        }, 1500);
      }
      if (update.docChanged || update.selectionSet) {
        clearTimeout(uiTimer);
        uiTimer = setTimeout(refresh, 80);
      }
    })
  ] }) });
  root.yaraView = view;
  const doc = () => view.state.doc.toString();
  const source = () => exact !== null ? exact : doc().replaceAll("\n", newline);
  const dirty = () => source() !== clean;
  function status() {
    $("[data-file]").textContent = opened ? `Case ${opened.cid} \xB7 signatures/${opened.path}` : "Standalone draft";
    $("[data-dirty]").textContent = dirty() ? "Unsaved changes" : "Saved / unchanged";
    for (const b of $$("[data-file-path]")) b.setAttribute("aria-current", String(opened && String(opened.cid) === caseId && b.dataset.filePath === opened.path));
  }
  function notice(text) {
    $("[data-status]").textContent = text;
  }
  function button(label, fn) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.onclick = () => Promise.resolve().then(fn).catch((e) => notice(e.message));
    return b;
  }
  async function api(path, fields) {
    const options = { redirect: "error" };
    if (fields) {
      const data = new FormData();
      data.set("csrf", root.dataset.csrf);
      for (const [key, value] of Object.entries(fields)) if (value !== null && value !== void 0) data.set(key, value);
      options.method = "POST";
      options.body = data;
    }
    const response = await fetch(path, options);
    if (response.headers.get("content-type")?.includes("application/json")) {
      const result = await response.json();
      if (!response.ok) throw Object.assign(Error(result.error || "Request failed."), result, { status: response.status });
      return result;
    }
    if (!response.ok) throw Error("Request failed (" + response.status + "). Check permissions or session.");
    return response;
  }
  const tool = (path, fields) => api("/tools/yara-rule-editor/" + path, fields);
  const caseCall = (cid, path, fields) => api("/cases/" + cid + "/" + path, fields);
  function choice(title, message, options) {
    const dialog = $("[data-choice]");
    $("[data-choice-title]").textContent = title;
    $("[data-choice-message]").textContent = message;
    $("[data-choice-buttons]").replaceChildren();
    return new Promise((resolve) => {
      function finish(value) {
        dialog.close();
        resolve(value);
      }
      for (const [key, label] of options) $("[data-choice-buttons]").append(button(label, () => finish(key)));
      dialog.oncancel = (e) => {
        e.preventDefault();
        finish("cancel");
      };
      dialog.showModal();
    });
  }
  function load(text, context = null, saved = text) {
    documentGeneration++;
    loading = true;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, selection: { anchor: 0 }, effects: hist.reconfigure([]), annotations: Transaction.addToHistory.of(false) });
    view.dispatch({ effects: hist.reconfigure(history()) });
    loading = false;
    revision++;
    exact = text;
    newline = text.includes("\r\n") ? "\r\n" : "\n";
    opened = context;
    clean = saved;
    compilerProblems = [];
    $("[data-validation]").textContent = engine.available ? "Not checked" : "Engine unavailable";
    refresh();
    status();
    scheduleDraft();
  }
  function edit(change, selection) {
    view.dispatch({ changes: change, selection, annotations: [isolateHistory.of("full"), Transaction.userEvent.of("input.helper")], scrollIntoView: false });
    refresh();
  }
  function jump(from, to = from) {
    view.dispatch({ selection: { anchor: from, head: to }, effects: EditorView.scrollIntoView(from, { y: "center" }) });
    view.focus();
  }
  function problemList(holder, items) {
    holder.replaceChildren();
    if (!items.length) {
      holder.textContent = "No reported diagnostics; this is not compiler validation.";
      return;
    }
    for (const d of items) {
      const from = d.from ?? view.state.doc.line(Math.min(d.line || 1, view.state.doc.lines)).from, to = d.to ?? from;
      const line = view.state.doc.lineAt(Math.min(from, view.state.doc.length)).number;
      holder.append(button(`${d.severity} \xB7 ${d.origin || "compiler"} \xB7 line ${line}, column ${d.column ?? "unavailable"} \xB7 ${d.message}`, () => jump(Math.min(from, view.state.doc.length), Math.min(to, view.state.doc.length))));
    }
  }
  function refresh() {
    analysis = analyze(doc());
    root.yaraAnalysis = analysis;
    root.yaraAnalysisSource = doc();
    problemList($("[data-language-problems]"), analysis.diagnostics);
    problemList($("[data-compiler-problems]"), compilerProblems);
    const diagnostics = [...analysis.diagnostics, ...compilerProblems.map((d) => ({ ...d, from: view.state.doc.line(Math.min(d.line || 1, view.state.doc.lines)).from, to: view.state.doc.line(Math.min(d.line || 1, view.state.doc.lines)).to }))];
    view.dispatch(setDiagnostics(view.state, diagnostics));
    const context = suggestions(doc(), view.state.selection.main.head);
    $("[data-completion-context]").textContent = context.message || "Suggestions at the remembered editor cursor. Function details are curated for " + PROFILE + ".";
    $("[data-completions]").replaceChildren();
    for (const option of context.options.filter((o) => o.label.toLowerCase().startsWith(doc().slice(context.from, view.state.selection.main.head).toLowerCase())).slice(0, 40)) {
      const b = button(option.label + (option.detail ? " \u2014 " + option.detail : ""), () => {
        const current2 = suggestions(doc(), view.state.selection.main.head);
        if (!current2.options.some((o) => o.label === option.label)) throw Error("Cursor context changed; request completion again.");
        const pos = view.state.selection.main.head;
        edit({ from: current2.from, to: pos, insert: option.label }, { anchor: current2.from + option.label.length });
      });
      $("[data-completions]").append(b);
    }
    const selector = $("[data-meta-rule]"), previous = selector.value, current = ruleAt(analysis, view.state.selection.main.head);
    selector.replaceChildren(new Option("Choose a rule\u2026", ""));
    for (const rule of analysis.rules) selector.add(new Option(rule.name, rule.name + "@" + rule.from));
    selector.value = current ? current.name + "@" + current.from : analysis.rules.some((r) => r.name + "@" + r.from === previous) ? previous : "";
  }
  function draftContext() {
    return { opened, clean, caseId };
  }
  function scheduleDraft() {
    if (!ready) return;
    $("[data-draft]").textContent = "Recoverable draft pending\u2026";
    clearTimeout(draftTimer);
    draftTimer = setTimeout(persistDraft, 600);
  }
  function persistDraft() {
    const text = source(), context = draftContext(), atRevision = revision;
    draftQueue = draftQueue.catch(() => {
    }).then(() => tool("draft", { source_json: JSON.stringify(text), context: JSON.stringify(context) })).then(() => {
      if (revision === atRevision) $("[data-draft]").textContent = "Recoverable account draft saved.";
    }, (e) => {
      $("[data-draft]").textContent = "Draft save failed: " + e.message;
    });
    return draftQueue;
  }
  async function canLeave() {
    if (leaving) return false;
    if (!dirty()) return true;
    leaving = true;
    try {
      await persistDraft();
      const answer = await choice("Unsaved YARA document", "Save before replacing this draft or leaving the tool?", [["save", "Save"], ["discard", "Discard"], ["cancel", "Cancel"]]);
      if (answer === "cancel") return false;
      if (answer === "save") return await save(false) && !dirty();
      return true;
    } finally {
      leaving = false;
    }
  }
  window.mareCanLeaveTool = canLeave;
  window.addEventListener("beforeunload", (event) => {
    if (dirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  if (window.parent !== window) window.parent.document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || !dirty() || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || link.target === "_blank" || link.origin !== location.origin) return;
    event.preventDefault();
    canLeave().then((allowed) => {
      if (allowed) {
        clean = source();
        window.parent.location.assign(link.href);
      }
    });
  });
  function filterCases() {
    const previous = caseId;
    const select = $("[data-case]");
    select.replaceChildren(new Option("Standalone", ""));
    for (const c of cases.filter((c2) => `${c2.number} ${c2.name}`.toLowerCase().includes($("[data-case-search]").value.toLowerCase()) || String(c2.id) === previous)) select.add(new Option(c.number + " \xB7 " + c.name, c.id));
    select.value = previous;
  }
  async function inventory() {
    const requested = caseId;
    $("[data-files]").replaceChildren();
    for (const kind of ["positive", "baseline"]) $("[data-" + kind + "-path]").replaceChildren(new Option("No case asset", ""));
    if (!caseId) {
      $("[data-browser-status]").textContent = "Choose a case to browse files. The draft stays unchanged.";
      return;
    }
    $("[data-browser-status]").textContent = "Loading\u2026";
    try {
      const data = await caseCall(caseId, "yara-files");
      if (requested !== caseId) return;
      $("[data-browser-status]").textContent = data.files.length ? `${data.files.length} .yara file(s) \xB7 ${data.editable ? "editable" : "read-only case"}` : "No .yara files in signatures/.";
      for (const file of data.files) {
        const b = button(file.path, () => openFile(requested, file.path));
        b.dataset.filePath = file.path;
        $("[data-files]").append(b);
      }
      for (const kind of ["positive", "baseline"]) for (const path of data.samples) $("[data-" + kind + "-path]").add(new Option(path, path));
      status();
    } catch (e) {
      if (requested === caseId) $("[data-browser-status]").textContent = e.message;
    }
  }
  async function openFile(cid, path) {
    if (!await canLeave()) return;
    const current = revision, data = await caseCall(cid, "yara-file?path=" + encodeURIComponent(path));
    if (current !== revision || String(cid) !== caseId) throw Error("Document or browser case changed while loading; draft preserved. Retry opening.");
    load(data.source, { cid, path, version: data.version });
    notice("Loaded complete file; imports, comments and all rules retained.");
  }
  async function write(cid, path, expected, overwrite = false) {
    const snapshot = source(), atRevision = revision, generation = documentGeneration;
    let result;
    try {
      result = await caseCall(cid, "yara-file", { filename: path, version: expected || "", source_json: JSON.stringify(snapshot) });
    } catch (e) {
      if (e.conflict && overwrite && e.current) {
        const answer = await choice("Replace existing destination?", "This destination exists or changed. Replace its complete contents with this draft?", [["replace", "Replace destination"], ["cancel", "Cancel"]]);
        if (answer !== "replace") return false;
        return write(cid, path, e.current, false);
      }
      throw Error(e.conflict ? "File changed on disk. Draft retained. Reopen explicitly or Save As to another path." : e.message);
    }
    if (documentGeneration !== generation) {
      notice("Previous document snapshot saved; current document retained.");
      return false;
    }
    opened = { cid, path, version: result.version };
    clean = snapshot;
    status();
    scheduleDraft();
    if (revision !== atRevision) {
      notice("Snapshot saved; newer edits remain unsaved.");
      return false;
    }
    if (String(cid) === caseId) await inventory();
    notice("Saved complete document to signatures/" + path);
    return true;
  }
  function saveAs() {
    const dialog = $("[data-save-dialog]");
    $("[data-save-error]").textContent = "";
    $("[data-destination]").replaceChildren();
    for (const c of cases) $("[data-destination]").add(new Option(c.number + " \xB7 " + c.name, c.id));
    $("[data-destination]").value = caseId || String(cases[0]?.id || "");
    $("[data-filename]").value = opened?.path || "analyst.yara";
    dialog.showModal();
    return new Promise((resolve) => {
      let busy = false;
      const finish = (value) => {
        dialog.close();
        resolve(value);
      };
      $("[data-dismiss-save]").onclick = () => {
        if (!busy) finish(false);
      };
      dialog.oncancel = (e) => {
        e.preventDefault();
        if (!busy) finish(false);
      };
      $("[data-confirm-save]").onclick = async () => {
        if (busy) return;
        busy = true;
        try {
          const cid = $("[data-destination]").value;
          if (!cid) throw Error("Choose a case you may modify.");
          if (await write(cid, $("[data-filename]").value, null, true)) finish(true);
        } catch (e) {
          $("[data-save-error]").textContent = e.message;
        } finally {
          busy = false;
        }
      };
    });
  }
  async function save(asNew) {
    try {
      return asNew || !opened ? await saveAs() : await write(opened.cid, opened.path, opened.version);
    } catch (e) {
      notice(e.message);
      return false;
    }
  }
  $("[data-new]").onclick = async () => {
    if (await canLeave()) load(START);
  };
  $("[data-save]").onclick = () => save(false);
  $("[data-save-as]").onclick = () => save(true);
  $("[data-download]").onclick = async () => {
    try {
      const response = await tool("download", { source_json: JSON.stringify(source()) }), url = URL.createObjectURL(await response.blob()), a = document.createElement("a");
      a.href = url;
      a.download = opened?.path.split("/").at(-1) || "analyst.yara";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notice(e.message);
    }
  };
  $("[data-case-search]").oninput = filterCases;
  $("[data-case]").onchange = (event) => {
    caseId = event.target.value;
    scheduleDraft();
    inventory();
  };
  $("[data-refresh]").onclick = inventory;
  $("[data-undo]").onclick = () => undo(view);
  $("[data-redo]").onclick = () => redo(view);
  $("[data-complete]").onclick = () => {
    view.focus();
    startCompletion(view);
  };
  let wordWrap = true;
  const options = $("[data-options]"), optionsButton = options.querySelector("summary"), optionsMenu = options.querySelector("#yara-options-menu"), wrapCheckbox = $("[data-wrap]");
  function setWrap(enabled) {
    wordWrap = enabled;
    wrapCheckbox.checked = enabled;
    view.dispatch({ effects: wrap.reconfigure(enabled ? EditorView.lineWrapping : []) });
  }
  function positionOptions() {
    if (!options.open) return;
    const viewport = window.visualViewport, left = (viewport?.offsetLeft || 0) + 8, top = (viewport?.offsetTop || 0) + 8;
    const right = left + (viewport?.width || innerWidth) - 16, bottom = top + (viewport?.height || innerHeight) - 16;
    const anchor = optionsButton.getBoundingClientRect();
    const below = Math.max(0, bottom - anchor.bottom), above = Math.max(0, anchor.top - top);
    const upwards = optionsMenu.scrollHeight > below && above > below;
    optionsMenu.style.maxHeight = Math.max(0, upwards ? above : below) + "px";
    optionsMenu.style.maxWidth = Math.max(0, right - left) + "px";
    const bounds = optionsMenu.getBoundingClientRect();
    optionsMenu.style.left = Math.max(left, Math.min(anchor.right - bounds.width, right - bounds.width)) + "px";
    optionsMenu.style.top = Math.max(top, upwards ? anchor.top - bounds.height : anchor.bottom) + "px";
  }
  function openOptions(open) {
    options.open = open;
    optionsButton.setAttribute("aria-expanded", String(open));
    positionOptions();
  }
  options.addEventListener("toggle", () => openOptions(options.open));
  options.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      openOptions(true);
      wrapCheckbox.focus({ preventScroll: true });
    } else if (event.key === "Escape" && options.open) {
      event.preventDefault();
      event.stopPropagation();
      openOptions(false);
      optionsButton.focus({ preventScroll: true });
    }
  });
  options.addEventListener("focusout", (event) => {
    if (event.relatedTarget && !options.contains(event.relatedTarget)) openOptions(false);
  });
  document.addEventListener("pointerdown", (event) => {
    if (!options.contains(event.target)) openOptions(false);
  });
  window.addEventListener("resize", positionOptions);
  document.addEventListener("scroll", positionOptions, true);
  window.visualViewport?.addEventListener("resize", positionOptions);
  window.visualViewport?.addEventListener("scroll", positionOptions);
  new ResizeObserver(positionOptions).observe($(".yara-editor-toolbar"));
  wrapCheckbox.onchange = () => { setWrap(wrapCheckbox.checked); layout(); };
  const layoutKey = "mare-yara-layout:" + root.dataset.user;
  function layout() {
    root.style.setProperty("--yara-height", $("[data-height]").value + "px");
    view.requestMeasure();
    try {
      localStorage.setItem(layoutKey, JSON.stringify({ height: $("[data-height]").value, collapsed: $("#yara-dock").hidden, wrap: wordWrap }));
    } catch {
    }
  }
  $("[data-height]").oninput = layout;
  $("[data-collapse]").onclick = () => {
    const dock = $("#yara-dock");
    dock.hidden = !dock.hidden;
    $("[data-collapse]").textContent = dock.hidden ? "Show dock" : "Collapse dock";
    $("[data-collapse]").setAttribute("aria-expanded", String(!dock.hidden));
    layout();
  };
  try {
    const saved = JSON.parse(localStorage.getItem(layoutKey) || "null");
    if (saved) {
      setWrap(saved.wrap !== false);
      $("[data-height]").value = Math.min(850, Math.max(240, Number(saved.height) || 440));
      if (saved.collapsed) $("[data-collapse]").click();
    }
  } catch {
  }
  layout();
  for (const tab of $$("[data-tab]")) {
    tab.onclick = () => {
      for (const other of $$("[data-tab]")) {
        const active = other === tab;
        other.setAttribute("aria-selected", String(active));
        other.tabIndex = active ? 0 : -1;
        $("#yara-panel-" + other.dataset.tab).hidden = !active;
      }
      refresh();
    };
    tab.onkeydown = (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const tabs = $$("[data-tab]"), index = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (tabs.indexOf(tab) + (e.key === "ArrowLeft" ? -1 : 1) + tabs.length) % tabs.length;
      tabs[index].click();
      tabs[index].focus();
    };
  }
  function snippets() {
    const term = $("[data-snippet-search]").value.toLowerCase();
    $("[data-snippets]").replaceChildren();
    for (const [name, text, requires] of SNIPPETS.filter((x) => x.join(" ").toLowerCase().includes(term))) {
      const section = document.createElement("section"), h = document.createElement("h3"), p = document.createElement("p"), code = document.createElement("pre");
      h.textContent = name;
      p.textContent = requires;
      code.textContent = text;
      const action = (replace) => {
        const range = view.state.selection.main, from = replace ? range.from : range.head, to = replace ? range.to : range.head;
        const placeholder = text.match(/sample|group/)?.[0], at = placeholder ? text.indexOf(placeholder) : -1;
        edit({ from, to, insert: text }, { anchor: at >= 0 ? from + at : from + text.length, head: at >= 0 ? from + at + placeholder.length : from + text.length });
        notice("Inserted snippet only; existing Boolean logic and imports were not changed.");
      };
      section.append(h, p, code, button("Insert at cursor", () => action(false)), button("Replace selection", () => action(true)));
      $("[data-snippets]").append(section);
    }
  }
  $("[data-snippet-search]").oninput = snippets;
  snippets();
  function metadataSuggestions() {
    const term = $("[data-meta-search]").value.toLowerCase();
    $("[data-meta-suggestions]").replaceChildren();
    for (const [key, purpose] of Object.entries(META).filter((x) => x.join(" ").toLowerCase().includes(term))) {
      const section = document.createElement("section"), p = document.createElement("p");
      p.textContent = key + " \u2014 " + purpose + " \xB7 Example syntax: " + key + ' = "your value"';
      section.append(p, button("Use " + key, () => {
        $("[data-meta-key]").value = key;
        $("[data-meta-value]").focus({ preventScroll: true });
      }));
      $("[data-meta-suggestions]").append(section);
    }
  }
  $("[data-meta-search]").oninput = metadataSuggestions;
  metadataSuggestions();
  $("[data-meta-insert]").onclick = () => {
    try {
      const current = analyze(doc()), rule = current.rules.find((r) => r.name + "@" + r.from === $("[data-meta-rule]").value), result = metadataEdit(doc(), rule, $("[data-meta-key]").value.trim(), $("[data-meta-value]").value, $("[data-meta-type]").value);
      if (result.existing) {
        jump(result.existing.from, result.existing.to);
        $("[data-meta-status]").textContent = "Key already exists. Selected it for direct source editing; no duplicate was added.";
      } else {
        edit(result.change);
        $("[data-meta-status]").textContent = "Inserted metadata into " + rule.name + ".";
      }
    } catch (e) {
      $("[data-meta-status]").textContent = e.message;
    }
  };
  $("[data-preview-import]").onclick = () => {
    const name = $("[data-module]").value;
    if (analyze(doc()).imports.includes(name)) {
      notice("Import already exists; no duplicate added.");
      return;
    }
    importPreview = { revision, from: doc().startsWith("\uFEFF") ? 1 : 0, insert: 'import "' + name + '"\n' };
    $("[data-import-preview]").textContent = "+ " + importPreview.insert + "\nExisting source remains unchanged.";
    $("[data-import-preview]").hidden = $("[data-apply-import]").hidden = false;
  };
  $("[data-apply-import]").onclick = () => {
    if (!importPreview || importPreview.revision !== revision) {
      notice("Source changed. Preview the import again.");
      return;
    }
    edit({ from: importPreview.from, insert: importPreview.insert });
    $("[data-import-preview]").hidden = $("[data-apply-import]").hidden = true;
    importPreview = null;
  };
  async function run(kind) {
    if (job) {
      notice("Wait for or cancel the active job.");
      return;
    }
    if (!engine.available) {
      notice("Engine unavailable; install the pinned optional compiler.");
      return;
    }
    const serial = ++jobSerial, atRevision = revision, text = source();
    job = { pending: true };
    $("[data-validation]").textContent = "Checking";
    $("[data-validate]").disabled = $("[data-scan]").disabled = true;
    try {
      const fields = { kind, source_json: JSON.stringify(text) };
      if (kind === "scan") {
        for (const key of ["positive", "baseline"]) {
          if ($("[data-" + key + "]").files[0]) fields[key] = $("[data-" + key + "]").files[0];
          fields[key + "_path"] = $("[data-" + key + "-path]").value;
        }
        fields.case_id = caseId;
      }
      const result = await tool("jobs", fields);
      if (serial !== jobSerial) return;
      job = { id: result.id, revision: atRevision, serial };
      $("[data-cancel]").disabled = false;
      poll();
    } catch (e) {
      job = null;
      $("[data-validation]").textContent = revision === atRevision ? "Errors" : "Changed since last validation";
      notice(e.message);
      $("[data-job-status]").textContent = e.message;
      $("[data-validate]").disabled = $("[data-scan]").disabled = !engine.available;
    }
  }
  async function poll() {
    const current = job;
    if (!current?.id) return;
    try {
      const result = await tool("jobs/" + current.id);
      if (job !== current) return;
      $("[data-job-status]").textContent = result.status + " \xB7 " + PROFILE;
      if (["queued", "running"].includes(result.status)) {
        setTimeout(poll, 300);
        return;
      }
      job = null;
      $("[data-cancel]").disabled = true;
      $("[data-validate]").disabled = $("[data-scan]").disabled = !engine.available;
      if (current.revision !== revision) {
        $("[data-validation]").textContent = "Changed since last validation";
        $("[data-job-status]").textContent += " \xB7 older-source results discarded";
        return;
      }
      compilerProblems = result.diagnostics || [];
      refresh();
      $("[data-validation]").textContent = result.status === "cancelled" ? "Not checked (cancelled)" : result.compiled ? result.status === "completed" ? "Valid for " + PROFILE : "Compiled; scan errors" : "Errors";
      const holder = $("[data-results]");
      holder.replaceChildren();
      if (result.error) {
        const p = document.createElement("p");
        p.textContent = result.error;
        holder.append(p);
      }
      for (const sample of result.results || []) {
        const h = document.createElement("h3");
        h.textContent = (sample.sample === "baseline" ? "Benign baseline" : "Positive sample") + " \xB7 " + (result.sample_names?.[sample.sample] || sample.sample) + " \xB7 " + sample.status;
        holder.append(h);
        if (sample.error) {
          const p = document.createElement("p");
          p.textContent = sample.error;
          holder.append(p);
        }
        for (const match of sample.matches) {
          const pre = document.createElement("pre");
          pre.textContent = "Rule: " + match.rule + "\n" + match.strings.map((s) => `${s.identifier} \xB7 offset ${s.offset}, length ${s.length}, hex preview ${s.preview}`).join("\n");
          holder.append(pre);
        }
      }
      if (result.execution) {
        const details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
        summary.textContent = "Bounded execution logs";
        pre.textContent = (result.execution.stderr || "") + "\nExit: " + result.execution.code + " \xB7 " + (result.execution.reason || "");
        details.append(summary, pre);
        holder.append(details);
      }
    } catch (e) {
      if (job === current) {
        job = null;
        $("[data-job-status]").textContent = e.message;
        $("[data-validation]").textContent = "Errors";
        $("[data-cancel]").disabled = true;
        $("[data-validate]").disabled = $("[data-scan]").disabled = !engine.available;
      }
    }
  }
  $("[data-validate]").onclick = () => run("validate");
  $("[data-scan]").onclick = () => run("scan");
  $("[data-cancel]").onclick = () => job?.id && tool("jobs/" + job.id + "/cancel", {}).catch((e) => notice(e.message));
  $("[data-validate]").disabled = $("[data-scan]").disabled = true;
  refresh();
  status();
  const startup = revision;
  tool("state").then(async (state) => {
    engine = state.engine;
    cases = state.cases;
    $("[data-engine]").textContent = PROFILE + " \xB7 " + engine.message;
    $("[data-profile]").textContent = PROFILE;
    $("[data-validate]").disabled = $("[data-scan]").disabled = !engine.available;
    if (revision === startup && state.draft) {
      const context = state.draft.context || {};
      caseId = String(context.caseId || "");
      load(state.draft.source, context.opened || null, context.clean ?? state.draft.source);
    }
    ready = true;
    filterCases();
    await inventory();
    $("[data-validation]").textContent = engine.available ? "Not checked" : "Engine unavailable";
    root.dataset.ready = "true";
    root.dataset.recovered = state.draft ? "true" : "false";
    $("[data-draft]").textContent = state.draft ? "Recovered account draft." : "Standalone draft ready.";
    if (state.draft) notice("Recovered your complete account draft; case files have not been changed.");
    scheduleDraft();
  }).catch((e) => notice(e.message));
}
export {
  mountYaraTool
};
