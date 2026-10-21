import { Compartment, EditorState, StateEffect, StateField, Transaction } from "@codemirror/state";
import { EditorView, Decoration, keymap, lineNumbers, drawSelection } from "@codemirror/view";
import { history, historyKeymap, defaultKeymap, undo, redo, undoDepth, redoDepth, isolateHistory } from "@codemirror/commands";
import { StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { EXAMPLE, EMPTY, BUFFERS, MODIFIERS, parse, modifierValues, contentPatch, modifierPatch, removal, movement, conversion, hexBytes, encodeContent } from "./snort-model";
import { captureTarget, resolveTarget, planInsertion } from "./snort-insertion";
import { CATALOG } from "./snort-catalog";
import {ACTIONS,PROTOCOLS,SERVICES,ADDRESSES,PORTS,FLOW_GROUPS,flowTokens,validateFlow} from "./snort-options";
const language = StreamLanguage.define({ token(s) {
  if (s.eatSpace()) return null;
  if (s.match(/^#.*/)) return "comment";
  if (s.match(/^"(?:\\.|[^"\\])*"/)) return "string";
  if (s.match(/^\$[\w]+/)) return "variableName";
  if (s.match(/^\b\d+\b/)) return "number";
  if (s.match(/^[\w]+(?=\s*[:;(])/)) return "keyword";
  s.next();
  return null;
} });
const highlight = StateEffect.define(), marks = StateField.define({ create: () => Decoration.none, update(value, tr) {
  value = value.map(tr.changes);
  for (const e of tr.effects) if (e.is(highlight)) value = Decoration.set(e.value, true);
  return value;
}, provide: (f) => EditorView.decorations.from(f) });
function mountSnortTool({ theme, highlighting }) {
  const root = document.querySelector("[data-snort-tool]");
  if (!root || root.dataset.initialized) return;
  root.dataset.initialized = "true";
  const $ = (s) => root.querySelector(s), $$ = (s) => [...root.querySelectorAll(s)];
  let model = parse(""), selected = null, parseTimer, draftTimer, opened = null, fileDocument = null, clean = "", caseId = "", cases = [], files = [], sidIndex = {}, inventoryId = 0, draftBusy = false, ready = false, navigating = false, internal = false, exact = null, newline = "\n", engine = null, job = null, submitted = null, pollTimer, draftRevision = 0;
  let insertionTarget=null, insertionError="", modifierTarget=null, configPreview=null;
  const workflowResults={byte:null,library:null};
  const wrap = new Compartment(), hist = new Compartment();
  const view = new EditorView({ parent: $("[data-rule-editor]"), state: EditorState.create({ extensions: [hist.of(history()), keymap.of([...historyKeymap, ...defaultKeymap]), lineNumbers(), drawSelection(), theme, syntaxHighlighting(highlighting), language, marks, wrap.of(EditorView.lineWrapping), EditorView.contentAttributes.of({ "aria-label": "Snort rule source" }), EditorView.updateListener.of((update) => {
    $("[data-undo]").disabled = !undoDepth(view.state);
    $("[data-redo]").disabled = !redoDepth(view.state);
    if (update.docChanged && !internal) {
      mapWorkflowTargets(update);
      exact = null;
      changed();
      clearTimeout(parseTimer);
      parseTimer = setTimeout(reparse, 180);
    }
    if (update.selectionSet && !internal) queueMicrotask(() => {
      if (model.source === doc()) selectAt(view.state.selection.main.head);
    });
  })] }) });
  root.snortView = view;
  const doc = () => view.state.doc.toString();
  const source = () => exact !== null ? exact : doc().replaceAll("\n", newline);
  const dirty = () => source() !== clean;
  function notice(message) {
    $("[data-status]").textContent = message;
  }
  function fileStatus() {
    $("[data-file]").textContent = opened ? `${cases.find((c) => String(c.id) === String(opened.cid))?.number || opened.cid} \xB7 signatures/${opened.path} \xB7 ${opened.whole ? "Whole-file inspection" : `Signature ${opened.position} of ${opened.total} \xB7 ${opened.message || "(no message)"} \xB7 SID ${opened.sid || "\u2014"}`}` : "Standalone draft";
    $("[data-change-signature]").disabled = !opened;
    $("[data-save]").disabled = !!opened?.whole;
    $("[data-download]").textContent = opened?.whole ? "Download inspected source" : "Download selected signature";
    $("[data-dirty]").textContent = dirty() ? "Unsaved changes" : "Saved / unchanged";
    for (const b of $$("[data-file-path]")) b.setAttribute("aria-current", String(opened && String(opened.cid) === caseId && opened.path === b.dataset.filePath));
  }
  function changed() {
    draftRevision++;
    if (ready) $("[data-draft]").textContent = "Modified \xB7 draft pending.";
    fileStatus();
    $("[data-validation]").textContent = "Current source is not engine-validated.";
    if (submitted !== null && submitted !== source()) $("[data-job]").textContent = "Source changed; previous results belong to the submitted version.";
    clearTimeout(draftTimer);
    if (ready) draftTimer = setTimeout(saveDraft, 700);
  }
  async function call(url, fields) {
    const options = { redirect: "error" };
    if (fields) {
      const body = new FormData();
      body.set("csrf", root.dataset.csrf);
      for (const [k, v] of Object.entries(fields)) if (v !== void 0 && v !== null) body.set(k === "source" ? "source_json" : k, k === "source" ? JSON.stringify(v) : v);
      options.method = "POST";
      options.body = body;
    }
    const response = await fetch(url, options);
    let data;
    try {
      data = await response.json();
    } catch {
      throw Error(`HTTP ${response.status}: request failed. Check login, size limits and permissions.`);
    }
    if (!response.ok) throw Object.assign(Error(data.error || `HTTP ${response.status}: request refused.`), data);
    return data;
  }
  const tool = (path, fields) => call("/tools/snort-rule-builder/" + path, fields);
  const caseCall = (cid, path, fields) => call(`/cases/${cid}/${path}`, fields);
  function button(label, fn) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", () => Promise.resolve().then(fn).catch((e) => notice(e.message)));
    return b;
  }
  function choice(title, message, options) {
    const d = $("[data-choice]");
    $("[data-choice-title]").textContent = title;
    $("[data-choice-message]").textContent = message;
    $("[data-choice-buttons]").replaceChildren();
    d.showModal();
    return new Promise((resolve) => {
      const finish = (v) => {
        d.close();
        d.oncancel = null;
        resolve(v);
      };
      for (const [key, label] of options) $("[data-choice-buttons]").append(button(label, () => finish(key)));
      d.oncancel = (e) => {
        e.preventDefault();
        finish("cancel");
      };
    });
  }
  async function confirm(text) {
    return await choice("Confirm change", text, [["yes", "Confirm"], ["cancel", "Cancel"]]) === "yes";
  }
  function load(text, context = null) {
    internal = true;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, selection: { anchor: 0 }, annotations: Transaction.addToHistory.of(false), effects: hist.reconfigure([]) });
    view.dispatch({ effects: hist.reconfigure(history()) });
    internal = false;
    exact = text;
    newline = text.includes("\r\n") ? "\r\n" : "\n";
    opened = context ? { ...context, whole: context.whole ?? context.start === void 0 } : null;
    clean = text;
    selected = null;
    insertionTarget=null;insertionError="";modifierTarget=null;workflowResults.byte=workflowResults.library=null;
    $("[data-byte-view]").hidden=$("[data-library-view]").hidden=true;
    reparse();
    changed();
  }
  function patches(changes) {
    if (model.source !== doc()) reparse();
    if (!changes.length) return;
    exact = null;
    view.dispatch({ changes: changes.filter(Boolean), annotations: [isolateHistory.of("full"), Transaction.userEvent.of("input.inspector")], scrollIntoView: false });
    clearTimeout(parseTimer);
    reparse();
  }
  function reparse() {
    model = parse(doc(), $("[data-dialect]").value);
    if (opened?.whole) {
      model.diagnostics.unshift("Whole-file inspection: selected-rule inspectors and saving are disabled.");
      for (const c of model.components) c.safe = false;
    }
    root.snortModel = model;
    const old = selected;
    selected = model.components.find((c) => c.id === old?.id) || null;
    renderOutline();
    renderInspector();
    renderReview();
    paint();
    $("[data-parse]").textContent = model.diagnostics.length ? model.diagnostics.join(" ") : `Parsed ${model.rules.length} rule(s) \xB7 ${model.compatibility.length ? "compatibility review required" : "parsing is not engine validation"}`;
    if (view.hasFocus) selectAt(view.state.selection.main.head);
    refreshWorkflows();
  }
  function current() {
    if (model.source !== doc()) {
      reparse();
      throw Error("Source was reparsed. Review the selection and try again.");
    }
    if (!selected) throw Error("Select a component.");
    return selected;
  }
  function selectAt(position) {
    const options = model.components.filter((c2) => c2.spans.some((r) => r.from <= position && position <= r.to));
    const c = options.find((c2) => c2.kind === "buffer") || options.find((c2) => c2.kind === "content") || options[0];
    if (c && c.id !== selected?.id) {
      selected = c;
      if(c.kind==="content"&&c.safe)modifierTarget=captureTarget(model,c,"after");
      renderOutline();
      renderInspector();
      paint();
    }
  }
  function selectComponent(c, scroll = true) {
    selected = c;
    if(c.kind==="content"&&c.safe)modifierTarget=captureTarget(model,c,"after");
    renderOutline();
    renderInspector();
    paint();
    refreshWorkflows();
    if (scroll && c.spans[0]) view.dispatch({ effects: EditorView.scrollIntoView(c.spans[0].from, { y: "nearest" }), scrollIntoView: false });
  }
  function paint() {
    const decorations = [];
    if (selected) {
      const primary = selected.spans;
      const related = selected.kind === "buffer" ? model.components.filter((c) => c.buffer === selected.selector).flatMap((c) => c.spans) : selected.related.map((o) => ({ from: o.from, to: o.to }));
      for (const [list2, css] of [[related, "snort-related"], [primary, "snort-primary"]]) for (const r of list2) if (r.to > r.from && r.to <= view.state.doc.length) decorations.push(Decoration.mark({ class: css }).range(r.from, r.to));
      $("[data-breadcrumb]").textContent = `Rule ${selected.rule + 1} / ${selected.label} \xB7 ${selected.summary || ""}`;
    } else $("[data-breadcrumb]").textContent = "Rule source \xB7 choose a component";
    if (model.diagnostics.length && view.state.doc.length) decorations.push(Decoration.mark({ class: "snort-parse-error" }).range(view.state.doc.length - 1, view.state.doc.length));
    view.dispatch({ effects: highlight.of(decorations) });
  }
  function renderOutline() {
    const target = $("[data-outline]");
    target.replaceChildren();
    for (const rule of model.rules) {
      for (const [title, kinds] of [["Traffic scope", ["header", "flow"]], ["Match groups", ["content", "buffer", "option"]], ["Rule identity", ["identity", "reference"]]]) {
        const h = document.createElement("h3");
        h.textContent = (model.rules.length > 1 ? `Rule ${rule.n + 1} \xB7 ` : "") + title;
        target.append(h);
        for (const c of rule.components.filter((c2) => kinds.includes(c2.kind))) {
          const b = button((c.warnings?.length || !c.safe ? "\u26A0 " : "") + c.label, () => selectComponent(c));
          b.dataset.component = c.id;
          b.setAttribute("aria-pressed", String(c.id === selected?.id));
          const s = document.createElement("small");
          s.textContent = c.summary || "";
          b.append(s);
          target.append(b);
        }
      }
    }
    if (!model.components.length) target.textContent = "Complete a rule header and options to inspect components.";
  }
  function input(parent, label, value, type = "text", options = null) {
    const l = document.createElement("label");
    l.textContent = label;
    const field = document.createElement(options ? "select" : "input");
    field.setAttribute('aria-label',label);
    if (options) {
      for (const v of options) field.add(new Option(v, v));
    } else field.type = type;
    if (type === "checkbox") field.checked = !!value;
    else field.value = value ?? "";
    if(type==='checkbox'){
      l.textContent='';l.className='snort-check';const text=document.createElement('span');text.textContent=label;l.append(field,text);
    }else l.append(field);
    parent.append(l);
    return field;
  }
  let headerLayoutObserver;
  function renderInspector() {
    headerLayoutObserver?.disconnect();
    const target = $("[data-inspector]");
    target.replaceChildren();
    target.classList.remove("snort-header-inspector");
    $("[data-inspector-error]").textContent = "";
    if (!selected) {
      target.textContent = "Select a source or outline component.";
      return;
    }
    const c = selected;
    const title = document.createElement("p");
    title.textContent = c.label + (c.kind === "content" ? ` \xB7 ${c.bufferName} (${model.rules[c.rule].dialect})` : "");
    target.append(title);
    const preview = document.createElement("pre");
    preview.textContent = c.spans.map((r) => doc().slice(r.from, r.to)).join("\n");
    target.append(preview);
    if (c.related.length) {
      const p = document.createElement("p");
      p.textContent = "The blue secondary highlight is the shared sticky buffer. Changing it affects other matches too.";
      target.append(p);
    }
    const fields = document.createElement("div");
    fields.className = "snort-fields";
    target.append(fields);
    if(c.kind==='content'&&c.safe){
      const actions=document.createElement('div');actions.className='snort-actions';
      for(const side of ['before','after'])actions.append(button('Insert '+side,()=>{chooseTarget(current(),side);notice('New match will be inserted '+side+' '+current().label+'.');}));
      actions.append(button('Add modifier',()=>{modifierTarget=captureTarget(model,current(),'after');$('[data-tab="library"]').click();refreshWorkflows();$('[data-library-match]').focus({preventScroll:true});}));target.append(actions);
    }
    const edits = [];
    let apply = null;
    if (c.safe && c.kind === "header") {
      const labels = c.tokens.length === 2 ? ["Action", "Service"] : ["Action", "Protocol/service", "Source address", "Source port", "Direction", "Destination address", "Destination port"];
      target.classList.add('snort-header-inspector');
      fields.classList.add('snort-header-fields');
      const row = (name) => {
        const group = document.createElement('div');
        group.className = 'snort-header-row';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', name + ' fields');
        fields.append(group);
        return group;
      };
      const headingRow = row('Action and protocol');
      const sourceAddressRow = c.tokens.length > 2 ? row('Source address') : null;
      const sourcePortRow = c.tokens.length > 2 ? row('Source port') : null;
      sourcePortRow?.classList.add('snort-header-source-port');
      const destinationAddressRow = c.tokens.length > 2 ? row('Destination address') : null;
      const destinationPortRow = c.tokens.length > 2 ? row('Destination port') : null;
      const directionRow = c.tokens.length > 2 ? row('Direction') : null;
      const parents = [headingRow, headingRow, sourceAddressRow, sourcePortRow, directionRow, destinationAddressRow, destinationPortRow];
      c.tokens.forEach((token,i)=>{
        const parent = parents[i];
        const name=labels[i];let read;
        if(i===0||i===4){
          const choices=i===0?ACTIONS:['->','<>'];
          const f=input(parent,name,token.text,'text',[...new Set([...choices,token.text])]);read=()=>f.value;
        }else if(i===1){
          const choices=c.tokens.length===2?SERVICES:[...PROTOCOLS,...SERVICES];
          const f=input(parent,name,choices.includes(token.text)?token.text:'__custom__','text',[...choices,'__custom__']);f.options[f.options.length-1].textContent='Custom…';
          const cell=document.createElement('div');parent.append(cell);cell.append(f.parentElement);
          const custom=input(cell,'Custom '+name,choices.includes(token.text)?'':token.text);custom.parentElement.hidden=f.value!=='__custom__';
          f.onchange=()=>{custom.parentElement.hidden=f.value!=='__custom__';if(!custom.parentElement.hidden)custom.focus({preventScroll:true});};read=()=>f.value==='__custom__'?custom.value:f.value;
        }else{
          const f=input(parent,name,token.text);const choices=i===2||i===5?ADDRESSES:PORTS;
          const picker=input(parent,name+' presets','','text',['',...choices]);picker.options[0].textContent='Choose a preset…';
          picker.onchange=()=>{if(picker.value)f.value=picker.value;picker.value='';};read=()=>f.value;
        }
        edits.push(()=>read()===token.text?null:{from:token.from,to:token.to,insert:read()});
      });
      if (directionRow) {
        // Split only the second column; intrinsic select widths must not resize it.
        const portOptions = document.createElement('div');
        portOptions.className = 'snort-header-port-options';
        const presets = sourcePortRow.lastElementChild;
        sourcePortRow.append(portOptions);
        portOptions.append(presets);
        const direction = directionRow.firstElementChild;
        headerLayoutObserver = new ResizeObserver(([entry]) => {
          const wide = entry.contentRect.width >= 600;
          const destination = wide ? portOptions : directionRow;
          if (direction.parentElement !== destination) {
            const focused = direction.contains(document.activeElement) ? document.activeElement : null;
            destination.append(direction);
            focused?.focus({preventScroll:true});
          }
          directionRow.hidden = wide;
        });
        headerLayoutObserver.observe(fields);
      }
      const hint=document.createElement('p');hint.textContent='Address/port variables and service names are common presets, not confirmation that they exist in the configured profile. Custom values, variables, lists, CIDRs and ranges remain editable.';target.append(hint);
      apply = () => {
        const values = edits.map((fn) => fn()).filter(Boolean);
        if (values.some((v) => !v.insert.trim() || /[();"\r\n#]/.test(v.insert))) throw Error("Header fields cannot contain directives, parentheses or newlines. Lists, CIDRs, ranges, variables and negation are accepted.");
        patches(values);
      };
    } else if (c.safe && c.kind === "content") {
      const mode = input(fields, "Representation", "mixed", "text", ["mixed", "text", "hex"]);
      const value = input(fields, "Content", c.decoded.mixed);
      const neg = input(fields, "Negated content", c.decoded.negated, "checkbox");
      const mods = modifierValues(c), controls = {};
      for (const key of ["nocase", "fast_pattern", "offset", "depth", "distance", "within"]) controls[key] = input(fields, key, ["nocase", "fast_pattern"].includes(key) ? !!mods[key] : mods[key] || "", ["nocase", "fast_pattern"].includes(key) ? "checkbox" : "text");
      const buffer = input(fields, "Associated buffer", c.bufferName, "text", ["payload", ...BUFFERS]);
      const p = document.createElement("p");
      p.textContent = `Decoded: ${c.decoded.display}. Positioning is measured inside ${c.bufferName}; relative matches depend on earlier matches in the same buffer. Other modifiers remain in source.`;
      target.append(p);
      apply = async () => {
        const absolute = controls.offset.value !== "" || controls.depth.value !== "", relative = controls.distance.value !== "" || controls.within.value !== "";
        if (absolute && relative) throw Error("Offset/depth cannot be combined with distance/within.");
        if (neg.checked && controls.fast_pattern.checked) throw Error("Negated fast_pattern eligibility requires engine/source review; this inspector does not enable it.");
        const changes = [];
        if (value.value !== c.decoded.mixed || mode.value !== "mixed" || neg.checked !== c.decoded.negated) changes.push(contentPatch(c, value.value, mode.value, neg.checked));
        for (const [key, f] of Object.entries(controls)) {
          const v = f.type === "checkbox" ? f.checked ? "true" : "" : f.value;
          if ((mods[key] || "") !== v) changes.push(modifierPatch(model, c, key, v));
        }
        if (buffer.value !== c.bufferName) {
          if (model.rules[c.rule].dialect === "legacy") {
            if (!buffer.value.startsWith("http_")) throw Error("Legacy buffer changes outside HTTP require source editing.");
            if (c.buffer) changes.push({ from: c.buffer.from, to: c.buffer.bodyTo, insert: buffer.value });
            else changes.push({ from: c.content.to, to: c.content.to, insert: " " + buffer.value + ";" });
          } else {
            if (!await confirm("Changing this buffer may affect later matches. An explicit selector before this match changes the shared inspection context. Continue?")) return;
            changes.push({ from: c.content.from, to: c.content.from, insert: (buffer.value === "payload" ? "pkt_data" : buffer.value) + "; " });
          }
        }
        patches(changes.filter(Boolean));
      };
    } else if (c.safe && c.kind === "buffer") {
      const o = c.options[0], name = input(fields, "Sticky buffer", o.key, "text", BUFFERS), field = input(fields, "Buffer parameters (for example field user-agent)", o.value);
      apply = async () => {
        if (/[;()\r\n]/.test(field.value)) throw Error("Edit complex parameters in source.");
        if (await confirm("Change this sticky buffer? All related matches are highlighted in blue.")) patches([{ from: o.from, to: o.bodyTo, insert: name.value + (field.value ? ":" + field.value : "") }]);
      };
    } else if (c.safe && c.kind === "reference") {
      const o = c.options[0], comma = o.value.indexOf(","), type = input(fields, "Reference type", comma < 0 ? "" : o.value.slice(0, comma)), value = input(fields, "Reference value", comma < 0 ? o.value : o.value.slice(comma + 1));
      apply = () => {
        if (!type.value || !value.value || /[;,\r\n]/.test(type.value) || /[;\r\n]/.test(value.value)) throw Error("Enter a reference type and value without statement delimiters.");
        const a = o.colon + 1;
        patches([{ from: a, to: o.bodyTo, insert: type.value + "," + value.value }]);
      };
    } else if(c.safe&&c.kind==='flow'){
      const o=c.options[0],value=input(fields,'flow',o.value),picker=input(fields,'Add flow option','','text',[]);
      picker.add(new Option('Choose an option…',''));
      for(const [label,choices]of FLOW_GROUPS){const group=document.createElement('optgroup');group.label=label;for(const choice of choices)group.append(new Option(choice,choice));picker.append(group);}
      const chips=document.createElement('div');chips.className='snort-actions snort-flow-values';target.append(chips);
      function refresh(){
        chips.replaceChildren();const tokens=flowTokens(value.value);
        for(const token of tokens){const b=button(token+' ×',()=>{value.value=flowTokens(value.value).filter(t=>t!==token).join(',');refresh();});b.setAttribute('aria-label','Remove flow option '+token);chips.append(b);}
        for(const option of picker.options){if(!option.value)continue;const group=FLOW_GROUPS.find(([,choices])=>choices.includes(option.value));option.disabled=tokens.includes(option.value)||group[1].some(v=>tokens.includes(v));}
      }
      picker.onchange=()=>{if(picker.value&&!flowTokens(value.value).includes(picker.value))value.value=[...flowTokens(value.value),picker.value].join(',');picker.value='';refresh();};value.oninput=refresh;refresh();
      apply=()=>{validateFlow(value.value);if(value.value!==o.value)patches([{from:o.colon+1,to:o.bodyTo,insert:value.value}]);};
    } else if (c.safe && c.kind==='identity') {
      for (const o of c.options) {
        let display = o.value;
        const isMessage = o.key === "msg";
        if (isMessage) {
          try {
            display = JSON.parse(o.value);
          } catch {
            display = o.value;
          }
        }
        const f = input(fields, o.key, display);
        edits.push(() => {
          if (f.value === String(display)) return null;
          if ((o.key === "msg" ? /[\r\n\x00]/ : /[;\r\n\x00]/).test(f.value)) throw Error("Use source editing for embedded semicolons or newlines.");
          if (["sid", "rev", "priority", "gid"].includes(o.key) && !/^\d+$/.test(f.value)) throw Error(o.key + " requires a nonnegative integer.");
          let v = f.value;
          if (o.key === "msg") v = JSON.stringify(v);
          return { from: o.colon === null ? o.from : o.colon + 1 + doc().slice(o.colon + 1, o.bodyTo).match(/^\s*/)[0].length, to: o.bodyTo, insert: o.colon === null ? o.key + (v ? ":" + v : "") : v };
        });
      }
      apply = async () => {
        if (c.kind === "buffer" && !await confirm("Changing a sticky buffer affects all related matches highlighted in blue. Continue?")) return;
        patches(edits.map((f) => f()).filter(Boolean));
      };
    }
    if (apply) {
      target.append(button("Apply inspector changes", async () => {
        try {
          current();
          await apply();
        } catch (e) {
          $("[data-inspector-error]").textContent = e.message;
        }
      }));
    } else {
      const p = document.createElement("p");
      p.textContent = "Source editing only for this component or incomplete/ambiguous syntax. Nothing is dropped.";
      target.append(p);
    }
    if (c.kind !== "header") {
      const removeButton = button("Remove component", async () => {
        try {
          current();
          const changes = removal(model, c);
          if (await confirm("Remove this component? Buffer removal changes related matches; other dependencies may require source review.")) patches(changes);
        } catch (e) {
          $("[data-inspector-error]").textContent = e.message;
        }
      });
      removeButton.disabled = !c.safe || c.kind === "option";
      target.append(removeButton);
    }
    for (const [step, label] of [[-1, "Move up"], [1, "Move down"]]) {
      const b = button(label, () => {
        try {
          current();
          patches(movement(model, c, step));
        } catch (e) {
          $("[data-inspector-error]").textContent = e.message;
        }
      });
      const references = model.rules[c.rule].components.filter((x) => x.kind === "reference");
      b.disabled = c.kind !== "reference" || !c.safe || !references[references.indexOf(c) + step];
      target.append(b);
    }
    const actionRow = document.createElement("div");
    actionRow.className = "snort-actions snort-inspector-actions";
    for (const node of [...target.children]) if (node.matches("button,a")) actionRow.append(node);
    target.append(actionRow);
  }
  function list(target, items, empty) {
    target.replaceChildren();
    if (!items.length) {
      target.textContent = empty;
      return;
    }
    const ul = document.createElement("ul");
    for (const text of items) {
      const li = document.createElement("li");
      li.textContent = text;
      ul.append(li);
    }
    target.append(ul);
  }
  function renderReview() {
    const collisions = [];
    const counts = {};
    for (const r of model.rules) for (const o of r.options.filter((o2) => o2.key === "sid")) {
      const sid = o.value;
      if (!/^\d+$/.test(sid)) continue;
      const canonical = String(Number(sid));
      counts[canonical] = (counts[canonical] || 0) + 1;
      const paths = (sidIndex[canonical] || []).filter((p) => !(opened && String(opened.cid) === caseId && opened.path === p));
      if (paths.length) collisions.push("SID " + sid + " also appears in " + paths.join(", "));
    }
    for (const [k, n] of Object.entries(counts)) if (n > 1) collisions.push("SID " + k + " is repeated in the current source.");
    list($("[data-diagnostics]"), model.diagnostics, "Lexical structure parsed; this is not engine validation.");
    list($("[data-compatibility]"), model.compatibility, "No known curated compatibility finding; full compatibility remains unverified.");
    list($("[data-quality]"), [...model.warnings, ...(doc().includes("REPLACE_ME")?["Incomplete template: replace REPLACE_ME in source before engine validation." ]:[]), ...collisions], "No curated warning. This does not establish detection quality.");
  }
  function targetLabel(c,side){return side==='end'?'End of option block':`${side==='before'?'Before':'After'} ${c.label}: ${c.summary || c.id}`;}
  function track(anchor,update){
    if(!anchor)return null;
    let touched=false;
    update.changes.iterChangedRanges((a,b)=>{if(a===b?a>anchor.from&&a<anchor.to:a<anchor.to&&b>anchor.from)touched=true;});
    if(touched)return null;
    return {...anchor,from:update.changes.mapPos(anchor.from,1),to:update.changes.mapPos(anchor.to,-1)};
  }
  function mapWorkflowTargets(update){
    if(insertionTarget){const mapped=track(insertionTarget,update);if(!mapped)insertionError='Insertion target changed or was removed. Choose a new location below.';insertionTarget=mapped;}
    if(modifierTarget)modifierTarget=track(modifierTarget,update);
    for(const key of ['byte','library'])workflowResults[key]=track(workflowResults[key],update);
  }
  function targetChoices(){
    if(model.diagnostics.length||opened?.whole)return [];
    const rules=model.rules.filter(r=>r.complete&&r.dialect!=='ambiguous');
    return rules.flatMap(r=>{
      const matches=r.components.filter(c=>c.kind==='content'&&c.safe);
      const header=r.components.find(c=>c.kind==='header'&&c.safe);
      return [...matches.flatMap(c=>['before','after'].map(side=>({c,side}))),...(header?[{c:header,side:'end'}]:[])];
    });
  }
  function chooseTarget(c,side){insertionTarget=captureTarget(model,c,side);insertionError='';refreshWorkflows();}
  function refreshWorkflows(){
    if(model.source!==doc()){reparse();return;}
    const choices=targetChoices();
    if(insertionTarget){try{resolveTarget(model,insertionTarget);}catch(e){insertionTarget=null;insertionError=e.message;}}
    if(!insertionTarget&&!insertionError&&model.rules.length===1){
      const matches=choices.filter(x=>x.side==='after');
      const candidate=matches.at(-1)||choices.find(x=>x.side==='end');
      if(candidate)try{const t=captureTarget(model,candidate.c,candidate.side);planInsertion(model,t,'content:"preview";','payload');insertionTarget=t;}catch(e){insertionError=e.message;}
    }
    for(const holder of $$('[data-insertion-controls]')){
      const hadFocus=holder.contains(document.activeElement);
      holder.replaceChildren();
      const select=input(holder,'Insertion location','','text',['']);select.options[0].textContent='Choose insertion location…';
      for(const {c,side}of choices){const key=c.id+':'+side;select.add(new Option(targetLabel(c,side),key));if(insertionTarget&&captureTarget(model,c,side).from===insertionTarget.from&&c.kind===insertionTarget.kind&&side===insertionTarget.side)select.value=key;}
      select.onchange=()=>{const chosen=choices.find(x=>x.c.id+':'+x.side===select.value);if(chosen)chooseTarget(chosen.c,chosen.side);else{insertionTarget=null;insertionError='Choose an insertion location below.';refreshWorkflows();}};
      const description=document.createElement('p');description.setAttribute('role','status');
      description.textContent=insertionTarget?'New component will be inserted '+targetLabel(resolveTarget(model,insertionTarget),insertionTarget.side).replace(/^./,c=>c.toLowerCase())+'.':insertionError||'Complete a rule and select its syntax interpretation to enable insertion.';
      holder.append(description);if(hadFocus)select.focus({preventScroll:true});
    }
    let matched=false;
    for(const name of ['library','byte']){
      const match=$('[data-'+name+'-match]'),hadFocus=document.activeElement===match;
      match.replaceChildren(new Option('Choose a content match…',''));
      for(const c of model.components.filter(c=>c.kind==='content'&&c.safe)){
        match.add(new Option(c.label+': '+c.summary,c.id));
        if(modifierTarget&&captureTarget(model,c,'after').from===modifierTarget.from&&model.source.slice(modifierTarget.from,modifierTarget.to)===modifierTarget.text){match.value=c.id;matched=true;}
      }
      if(hadFocus)match.focus({preventScroll:true});
    }
    if(!matched)modifierTarget=null;
    refreshBytePreview();configPreview?.();
  }
  function workflowEdit(plan,message,status,placeholder=false){
    patches([plan.change]);
    const c=model.components.find(c=>c.kind==='content'&&c.content.from>=plan.from&&c.content.from<plan.to)||model.components.find(c=>c.spans.some(s=>s.from>=plan.from&&s.from<plan.to));
    if(c){selectComponent(c,false);workflowResults[status==='[data-byte-status]'?'byte':'library']=captureTarget(model,c,'after');}
    if(placeholder){const at=doc().indexOf('REPLACE_ME',plan.from);if(at>=0&&at<plan.to)view.dispatch({selection:{anchor:at,head:at+10},scrollIntoView:false});$('[data-validation]').textContent='Incomplete source template: configure the selected placeholder and validate with Snort.';}
    $(status).textContent=message+' '+plan.effect;
    $(status==='[data-byte-status]'?'[data-byte-view]':'[data-library-view]').hidden=false;
    notice(message);
  }
  function insertOption(syntax,buffer=null,status='[data-library-status]',placeholder=false){
    if(model.source!==doc())reparse();
    const plan=planInsertion(model,insertionTarget,syntax,buffer);
    workflowEdit(plan,'Added '+(buffer!==null?'content match.':'option; review its source syntax.'),status,placeholder);
  }
  function applyModifier(name,value){
    if(model.source!==doc())reparse();
    if(!modifierTarget)throw Error('Choose a content match using the selector in Option library.');
    const c=resolveTarget(model,modifierTarget);
    if(c.kind!=='content')throw Error('Choose a content match.');
    const old=modifierValues(c);
    if(old[name]!==undefined){selectComponent(c,false);workflowResults.library=captureTarget(model,c,'after');const existing=c.modifiers.find(o=>o.key===name)||c.inline.find(o=>o.raw.split(/\s+/)[0]===name);if(existing)view.dispatch({selection:{anchor:existing.from,head:existing.to},scrollIntoView:false});$('[data-library-status]').textContent='Already applied: '+name+' on '+c.label+'.';$('[data-library-view]').hidden=false;return;}
    if(name==='fast_pattern'&&c.decoded.negated)throw Error('Negated content cannot be assigned fast_pattern by this workflow.');
    if(['offset','depth'].includes(name)&&['distance','within'].some(k=>old[k]!==undefined)||['distance','within'].includes(name)&&['offset','depth'].some(k=>old[k]!==undefined))throw Error('Remove conflicting absolute/relative positioning before applying this modifier.');
    const at=c.content.from;patches([modifierPatch(model,c,name,value)]);
    const updated=model.components.find(x=>x.kind==='content'&&x.content.from===at);if(updated){selectComponent(updated,false);workflowResults.library=captureTarget(model,updated,'after');}
    $('[data-library-status]').textContent='Applied '+name+' to '+(updated?.label||'content match')+'.';$('[data-library-view]').hidden=false;
  }
  for(const name of ['library','byte'])$('[data-'+name+'-match]').onchange=e=>{const c=model.components.find(c=>c.id===e.target.value);modifierTarget=c?captureTarget(model,c,'after'):null;refreshWorkflows();};
  for(const key of ['byte','library'])$('[data-'+key+'-view]').onclick=()=>{try{if(model.source!==doc())reparse();const c=resolveTarget(model,workflowResults[key]);$('[data-tab="construct"]').click();selectComponent(c);}catch(e){$('[data-'+key+'-status]').textContent='The result changed. Select it in the current outline. '+e.message;}};
  function configureOption(item){
    const target=$('[data-library-config]');target.hidden=false;target.replaceChildren();
    const h=document.createElement('h3');h.textContent='Configure '+item.name;target.append(h);
    const isContent=item.name==='content'||BUFFERS.includes(item.name),modifier=MODIFIERS.includes(item.name);
    const value=input(target,isContent?'Content value':modifier?'Modifier value':'Option source',isContent?'':modifier?'':item.syntax);
    let buffer=null;
    if(isContent){buffer=input(target,'Inspection buffer',BUFFERS.includes(item.name)?item.name:'payload','text',['payload',...BUFFERS]);}
    const explanation=document.createElement('p');explanation.setAttribute('role','status');target.append(explanation);
    const preview=()=>{try{if(isContent){const syntax='content:"'+encodeContent(value.value,'text')+'";';const plan=planInsertion(model,insertionTarget,syntax,buffer.value);explanation.textContent=syntax+' '+plan.effect;}else explanation.textContent=modifier?'Apply to the chosen content match; existing modifiers are selected without duplication.':'Advanced source insertion: review all required values and cursor effects. REPLACE_ME is incomplete syntax; it is selected for editing, not engine-validated.';}catch(e){explanation.textContent=e.message;}};
    configPreview=preview;value.oninput=preview;if(buffer)buffer.onchange=preview;preview();
    const apply=button(isContent?'Add content match':modifier?'Apply '+item.name:'Insert source template',()=>{
      try{
        if(isContent){if(!value.value)throw Error('Enter a nonempty content value.');insertOption('content:"'+encodeContent(value.value,'text')+'";',buffer.value);}
        else if(modifier){if(!value.value)throw Error('Enter the required modifier value.');applyModifier(item.name,value.value);}
        else{
          if(!value.value.trim())throw Error('Enter option source.');
          const probe=parse('alert tcp any any -> any 80 ('+value.value+')','snort3');
          if(probe.diagnostics.length||probe.rules.length!==1||probe.rules[0].options.length!==1||probe.rules[0].options[0].key!==item.name)
            throw Error('Enter exactly one '+item.name+' option ending with a semicolon. Use its dedicated buffer/content controls for other components.');
          if(['msg','sid','rev','classtype','priority','metadata','flow'].includes(item.name)){
            const c=resolveTarget(model,insertionTarget),rule=model.rules[c.rule];
            const existing=rule.components.find(x=>x.options.some(o=>o.key===item.name));
            if(existing){selectComponent(existing,false);workflowResults.library=captureTarget(model,existing,'after');$('[data-library-status]').textContent=item.name+' already exists. Use View in Construct to edit it.';$('[data-library-view]').hidden=false;return;}
          }
          insertOption(value.value,null,'[data-library-status]',value.value.includes('REPLACE_ME'));
        }
      }catch(e){$('[data-library-status]').textContent=e.message;}
    });target.append(apply);
    value.focus({preventScroll:true});
  }
  $('[data-add]').onclick=()=>{
    const item=CATALOG.find(x=>x.name===$('[data-add-kind]').value);
    $('[data-tab="library"]').click();configureOption(item);
  };
  function library() {
    const term=$('[data-library-search]').value.toLowerCase(),target=$('[data-library]');target.replaceChildren();
    for(const item of CATALOG.filter(x=>`${x.name} ${x.description} ${x.group}`.toLowerCase().includes(term))){
      const div=document.createElement('div');div.className='snort-option';
      const h=document.createElement('h3');h.textContent=item.group+' · '+item.name;
      const p=document.createElement('p');p.textContent=item.description;
      const code=document.createElement('code');code.textContent=item.syntax;
      const modifier=MODIFIERS.includes(item.name),flag=['nocase','fast_pattern'].includes(item.name);
      const action=button(modifier?'Apply '+item.name:BUFFERS.includes(item.name)?'Add match in '+item.name:item.name==='content'?'Add content match':'Configure '+item.name,()=>{
        try{if(modifier&&flag)applyModifier(item.name,'true');else configureOption(item);}catch(e){$('[data-library-status]').textContent=e.message;$('[data-library-match]').focus({preventScroll:true});}
      });
      div.append(h,p,code,action);target.append(div);
    }
  }
  function docs(){
    const term=$('[data-docs-search]').value.toLowerCase(),target=$('[data-docs-list]');target.replaceChildren();
    const references=[
      {group:'Rule writing',name:'Snort 3 rule guide',url:'https://docs.snort.org/rules/'},
      ...[['actions','Rule actions'],['protocols','Protocols and services'],['ips','Addresses and variables'],['ports','Ports'],['direction','Direction'],['service_rules','Service headers']].map(([path,name])=>({group:'Traffic scope',name,url:'https://docs.snort.org/rules/headers/'+path})),
      ...CATALOG.map(item=>({group:item.group,name:item.name,url:item.url}))
    ];
    for(const group of [...new Set(references.map(r=>r.group))]){
      const items=references.filter(r=>r.group===group&&`${r.group} ${r.name}`.toLowerCase().includes(term));if(!items.length)continue;
      const section=document.createElement('section'),h=document.createElement('h3');h.textContent=group;section.append(h);const list=document.createElement('ul');
      for(const item of items){const li=document.createElement('li'),a=document.createElement('a');a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=item.name;li.append(a);list.append(li);}section.append(list);target.append(section);
    }
    if(!target.children.length)target.textContent='No matching documentation.';
  }
  $('[data-docs-search]').oninput=docs;docs();
  $("[data-library-search]").addEventListener("input", library);
  $("[data-dialect]").addEventListener("change", () => {
    reparse();
    changed();
  });
  for (const b of $$("[data-tab]")) {
    b.addEventListener("click", () => {
      refreshWorkflows();
      for (const tab of $$("[data-tab]")) {
        const active = tab === b;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
        $("#snort-panel-" + tab.dataset.tab).hidden = !active;
      }
    });
    b.addEventListener("keydown", (e) => {
      const tabs = $$("[data-tab]");
      if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) {
        e.preventDefault();
        const i = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (tabs.indexOf(b) + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        tabs[i].click();
        tabs[i].focus({ preventScroll: true });
      }
    });
  }
  $("[data-undo]").onclick = () => undo(view);
  $("[data-redo]").onclick = () => redo(view);
  $("[data-wrap]").onchange = (e) => view.dispatch({ effects: wrap.reconfigure(e.target.checked ? EditorView.lineWrapping : []) });
  $("[data-height]").oninput = (e) => {
    root.style.setProperty("--snort-editor-height", e.target.value + "px");
    view.requestMeasure();
    try {
      localStorage.setItem("mare-snort-editor-height:" + root.dataset.user, e.target.value);
    } catch {
    }
  };
  try {
    const h = Number(localStorage.getItem("mare-snort-editor-height:" + root.dataset.user));
    if (h >= 180 && h <= 800) {
      $("[data-height]").value = h;
      root.style.setProperty("--snort-editor-height", h + "px");
    }
  } catch {
  }
  $("[data-copy]").onclick = () => navigator.clipboard.writeText(source()).then(() => notice("Copied."), () => notice("Clipboard unavailable; select and copy source manually."));
  async function download() {
    const body = { source: source() };
    const data = new FormData();
    data.set("csrf", root.dataset.csrf);
    data.set("source_json", JSON.stringify(body.source));
    const response = await fetch("/tools/snort-rule-builder/download", { method: "POST", body: data });
    if (!response.ok) throw Error("Download failed.");
    const url = URL.createObjectURL(await response.blob()), a = document.createElement("a");
    a.href = url;
    a.download = "analyst.rules";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1e3);
  }
  $("[data-download]").onclick = () => download().catch((e) => notice(e.message));
  $("[data-format]").onclick = async () => {
    if (!await confirm("Explicitly format option separators? Comments/unknown syntax are retained. Formatting is undoable.")) return;
    reparse();
    if (model.diagnostics.length) return notice("Complete syntax before formatting.");
    const changes = [];
    for (const r of model.rules) for (const o of r.options) {
      const end = o.to;
      const next = r.options.find((x) => x.from >= end);
      if (next && /^\s*$/.test(doc().slice(end, next.from))) changes.push({ from: end, to: next.from, insert: "\n    " });
    }
    patches(changes);
  };
  $("[data-example]").onclick = () => navigate(async () => {
    load(EXAMPLE);
    clean = "";
    changed();
  });
  $("[data-new]").onclick = () => navigate(async () => load(EMPTY));
  $("[data-conversion]").onclick = () => {
    reparse();
    const result = conversion(model), before = doc();
    $("[data-before]").textContent = result.before;
    $("[data-after]").textContent = result.after;
    $("[data-conversion-notes]").textContent = result.explanation;
    $("[data-conversion-errors]").textContent = result.reasons.join(" ");
    $("[data-apply-conversion]").disabled = !result.safe;
    $("[data-diff]").showModal();
    $("[data-apply-conversion]").onclick = () => {
      if (doc() !== before) {
        $("[data-conversion-errors]").textContent = "Source changed. Close and preview again.";
        return;
      }
      patches([{ from: 0, to: doc().length, insert: result.after }]);
      $("[data-dialect]").value = "snort3";
      reparse();
      $("[data-diff]").close();
    };
  };
  $("[data-close-diff]").onclick = () => $("[data-diff]").close();
  async function saveDraft() {
    if (draftBusy || !ready) return;
    draftBusy = true;
    const revision = draftRevision, text = source(), context = { opened, clean, caseId, dialect: $("[data-dialect]").value };
    try {
      await tool("draft", { source: text, context: JSON.stringify(context) });
      $("[data-draft]").textContent = text === source() ? "Draft saved to your account; case-file state is shown separately." : "New edits pending draft save.";
    } catch (e) {
      $("[data-draft]").textContent = "Draft save failed: " + e.message;
    } finally {
      draftBusy = false;
      if (revision !== draftRevision) {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(saveDraft, 200);
      }
    }
  }
  function filterCases() {
    const term = $("[data-case-search]").value.toLowerCase();
    $("[data-case]").replaceChildren(new Option("Standalone draft", ""));
    for (const c of cases) if (String(c.id) === caseId || `${c.number} ${c.name}`.toLowerCase().includes(term)) $("[data-case]").add(new Option(`${c.number} \xB7 ${c.name}`, c.id));
    $("[data-case]").value = caseId;
  }
  async function inventory() {
    const cid = caseId, ticket = ++inventoryId;
    if (!cid) {
      files = [];
      sidIndex = {};
      renderFiles();
      return;
    }
    $("[data-browser-status]").textContent = "Loading signatures\u2026";
    const data = await caseCall(cid, "snort-signatures");
    if (ticket !== inventoryId || cid !== caseId) return;
    files = data.files;
    sidIndex = data.sid_index || {};
    renderFiles();
    renderReview();
    const notices = [];
    for (const [sid, paths] of Object.entries(data.duplicate_sids)) notices.push(`Duplicate SID ${sid}: ${paths.join(", ")}`);
    $("[data-browser-status]").textContent = notices.join(" ") || (!files.length ? "No .rules files in this case." : "Files refreshed; multi-rule files remain intact.");
  }
  function renderFiles() {
    const target = $("[data-files]");
    target.replaceChildren();
    for (const f of files) {
      const b = button(f.path.split("/").at(-1), () => navigate(() => openFile(caseId, f.path)));
      b.dataset.filePath = f.path;
      const small = document.createElement("small");
      small.textContent = f.path + (f.reason ? " \xB7 " + f.reason : f.count > 1 ? ` \xB7 ${f.count} rules` : "");
      b.append(small);
      target.append(b);
    }
    if (!files.length) target.textContent = caseId ? "No .rules files." : "Choose a case or keep a standalone draft.";
    fileStatus();
  }
  function fileContext(cid, path, document2, rule = null) {
    return { cid, path, version: document2.version, fileSource: document2.source, whole: !rule, start: rule?.start, end: rule?.end, position: rule?.position, total: document2.count, message: rule?.message || "", sid: rule?.sid || "" };
  }
  async function chooseSignature(data) {
    const dialog = $("[data-signature-dialog]");
    let selection = null;
    $("[data-signature-search]").value = "";
    $("[data-signature-preview]").textContent = "Choose a signature to preview.";
    $("[data-load-signature]").disabled = true;
    $("[data-signature-summary]").textContent = `${data.count} active signatures \xB7 ${data.disabled} disabled/commented rules \xB7 ${data.directives.length} preserved directives. Source order is independent of SID. Boundary detection does not validate Snort syntax. ${data.reason || ""}`;
    function render() {
      const term = $("[data-signature-search]").value.toLowerCase(), list2 = $("[data-signatures]");
      list2.replaceChildren();
      for (const r of data.rules.filter((r2) => `${r2.position} ${r2.message} ${r2.sid} ${r2.revision} ${r2.header}`.toLowerCase().includes(term))) {
        const b = button(`${r.position}. ${r.message || "(no message)"}`, () => {
          selection = r;
          $("[data-signature-preview]").textContent = r.source;
          $("[data-load-signature]").disabled = false;
          render();
        });
        b.dataset.signaturePosition = r.position;
        b.setAttribute("aria-pressed", String(selection?.position === r.position));
        const details = document.createElement("small");
        details.textContent = `SID ${r.sid || "\u2014"} \xB7 rev ${r.revision || "\u2014"} \xB7 lines ${r.line_start}\u2013${r.line_end} \xB7 ${r.header}`;
        b.append(details);
        list2.append(b);
      }
      if (!list2.children.length) list2.textContent = "No matching signatures.";
    }
    render();
    dialog.showModal();
    return new Promise((resolve) => {
      const finish = (r) => {
        dialog.close();
        dialog.oncancel = null;
        resolve(r);
      };
      $("[data-signature-search]").oninput = () => {
        selection = null;
        $("[data-signature-preview]").textContent = "Choose a signature to preview.";
        $("[data-load-signature]").disabled = true;
        render();
      };
      $("[data-load-signature]").onclick = () => finish(selection);
      $("[data-cancel-signature]").onclick = () => finish(null);
      dialog.oncancel = (e) => {
        e.preventDefault();
        finish(null);
      };
    });
  }
  async function openFile(cid, path) {
    const before = source(), data = await caseCall(cid, "snort-signature?path=" + encodeURIComponent(path));
    if (before !== source()) throw Error("Source changed while opening; edits preserved. Retry.");
    let rule = null, inspect = false;
    if (data.document.reason && data.document.count) {
      const answer = await choice("Partially readable rule file", data.document.reason + " Only the completed prefix signatures have proven boundaries. Repair the reported region in source before accessing later signatures.", [["choose", "Select safe signatures"], ["inspect", "Inspect whole file"], ["cancel", "Cancel"]]);
      if (answer === "cancel") return;
      inspect = answer === "inspect";
    }
    if (!inspect) {
      if (data.document.count > 1) {
        rule = await chooseSignature(data.document);
        if (!rule) return;
      } else if (data.document.count === 1) rule = data.document.rules[0];
      else {
        const answer = await choice("Whole-file inspection", data.document.reason + " Selected-rule saving will be disabled. Download and repair the file, then reopen it.", [["inspect", "Inspect whole file"], ["cancel", "Cancel"]]);
        if (answer !== "inspect") return;
      }
    }
    if (before !== source()) throw Error("Source changed while choosing; current edits preserved.");
    fileDocument = data.document;
    load(rule ? rule.source : data.source, fileContext(cid, path, data.document, rule));
    notice(`${data.document.reason || ""} ${data.document.disabled} disabled/commented rules and ${data.document.directives.length} directives preserved outside the selected signature.`);
  }
  $("[data-change-signature]").onclick = () => opened && navigate(() => openFile(opened.cid, opened.path));
  async function navigate(task) {
    if (navigating || !ready) return;
    navigating = true;
    try {
      if (dirty()) {
        const answer = await choice("Unsaved changes", "Save the current rule before replacing it?", [["save", "Save current rule"], ["discard", "Discard changes"], ["cancel", "Cancel"]]);
        if (answer === "cancel") return;
        if (answer === "save" && (!await saveFile(false) || dirty())) return;
      }
      await task();
    } catch (e) {
      notice(e.message);
    } finally {
      navigating = false;
      fileStatus();
    }
  }
  async function writeFile(cid, name, expected = null, replace = false) {
    if (!cid) throw Error("Select a destination case.");
    if (!replace && opened && String(cid) === String(opened.cid) && name === opened.path) throw Error("Save As requires a separate destination. Use Save rule to replace only the selected signature.");
    if (replace && opened?.whole) throw Error("Whole-file inspection has no safe selected rule. Download the source or use a valid single-rule document with Save As.");
    const before = source();
    notice("Saving selected signature\u2026");
    let result;
    try {
      result = await caseCall(cid, "snort-rule", { filename: name, source: before, version: expected, operation: replace ? "replace" : "save-as", origin_cid: !replace ? opened?.cid : null, origin_path: !replace ? opened?.path : null, start: replace ? opened.start : null, end: replace ? opened.end : null });
    } catch (e) {
      if (e.conflict && replace) {
        const answer = await choice("File changed", "Selected-rule overwrite is blocked. Reload the file (discarding local edits) or keep your edits and use Save as.", [["reload", "Reload file"], ["save-as", "Save as"], ["cancel", "Cancel"]]);
        if (answer === "reload") await openFile(cid, name);
        else if (answer === "save-as") return await saveAs();
        return false;
      }
      if (e.conflict) {
        if (await confirm("Destination exists or changed. Overwrite this separate file? The original selected file is not removed.")) return writeFile(cid, name, e.current_version, false);
        return false;
      }
      throw e;
    }
    if (source() !== before) {
      notice("Submitted version saved; newer edits remain unsaved.");
      if (replace) {
        opened = { ...opened, ...fileContext(cid, name, result.document, result.selected) };
      }
      return false;
    }
    fileDocument = result.document;
    opened = fileContext(cid, name, result.document, result.selected);
    if (source() !== result.selected.source) {
      internal = true;
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: result.selected.source }, annotations: Transaction.addToHistory.of(false) });
      internal = false;
      exact = result.selected.source;
      newline = result.selected.source.includes("\r\n") ? "\r\n" : "\n";
      reparse();
    }
    clean = source();
    caseId = String(cid);
    filterCases();
    fileStatus();
    draftRevision++;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 100);
    await inventory();
    notice(`Saved signature ${opened.position} of ${opened.total} in signatures/${name}.`);
    return !dirty();
  }
  async function saveAs() {
    const dialog = $("[data-save-dialog]");
    $("[data-destination]").value = opened?.cid || caseId;
    $("[data-filename]").value = opened ? opened.path.replace(/\.rules$/i, "-signature.rules") : "analyst.rules";
    $("[data-save-error]").textContent = "";
    dialog.showModal();
    return new Promise((resolve) => {
      let busy = false;
      const finish = (value) => {
        dialog.close();
        dialog.oncancel = null;
        resolve(value);
      };
      $("[data-confirm-save]").onclick = async () => {
        if (busy) return;
        busy = true;
        try {
          if (await writeFile($("[data-destination]").value, $("[data-filename]").value)) finish(true);
        } catch (e) {
          $("[data-save-error]").textContent = e.message;
        } finally {
          busy = false;
        }
      };
      $("[data-dismiss-save]").onclick = () => {
        if (!busy) finish(false);
      };
      dialog.oncancel = (e) => {
        e.preventDefault();
        if (!busy) finish(false);
      };
      $("[data-save-download]").onclick = async () => {
        if (busy) return;
        busy = true;
        const text = source();
        try {
          await download();
          dialog.close();
          if (await confirm("Download requested. Continue only if you have saved the downloaded rule. Browser completion is not assumed.") && source() === text) {
            clean = text;
            fileStatus();
            resolve(true);
          } else dialog.showModal();
        } catch (e) {
          $("[data-save-error]").textContent = e.message;
        } finally {
          busy = false;
        }
      };
    });
  }
  async function saveFile(asNew) {
    try {
      return !opened || asNew ? await saveAs() : await writeFile(opened.cid, opened.path, opened.version, true);
    } catch (e) {
      notice(e.message);
      return false;
    }
  }
  $("[data-save]").onclick = () => saveFile(false);
  $("[data-save-as]").onclick = () => saveFile(true);
  $("[data-case-search]").oninput = filterCases;
  $("[data-case]").onchange = (e) => {
    const cid = e.target.value;
    e.target.value = caseId;
    navigate(async () => {
      caseId = cid;
      filterCases();
      load(EMPTY);
      await inventory();
    });
  };
  $("[data-refresh]").onclick = () => inventory().catch((e) => $("[data-browser-status]").textContent = e.message);
  let bytes = [], anchor = 0, cursor = 0, dragging = false, parsedHex = "";
  function refreshBytePreview(){
    const add=$('[data-bytes-add]'),position=$('[data-bytes-position]');
    position.disabled=true;
    try{
      const value=selectionContent(),values=bytes.slice(value.a,value.b);
      $('[data-byte-preview]').textContent=`Offsets [${value.a}, ${value.b}) · ${values.length} bytes\nHex: ${values.map(v=>v.toString(16).padStart(2,'0')).join(' ')}\nASCII: ${values.map(v=>v>=32&&v<=126?String.fromCharCode(v):'.').join('')}\ncontent:"${value.mixed}";`;
      const c=modifierTarget?resolveTarget(model,modifierTarget):null,origin=$('[data-origin]').value;
      position.disabled=!(c?.kind==='content'&&c.safe&&['payload','application'].includes(origin)&&(origin==='payload'?['payload','pkt_data'].includes(c.bufferName):$('[data-origin-buffer]').value===c.bufferName));
      try{
        const plan=planInsertion(model,insertionTarget,'content:"'+value.mixed+'";',$('[data-byte-buffer]').value);
        $('[data-byte-effect]').textContent=plan.effect;add.disabled=false;
      }catch(e){add.disabled=true;$('[data-byte-effect]').textContent=e.message;}
    }catch(e){add.disabled=true;$('[data-byte-effect]').textContent=e.message;$('[data-byte-preview]').textContent='No current byte preview: '+e.message;}
    position.title=position.disabled?'Choose a safe content match and matching transport-payload or exact application-buffer origin. No frame decoding is performed.':'';
  }
  for(const name of ['hex','representation','byte-buffer','origin','origin-buffer']){
    $('[data-'+name+']').addEventListener('input',refreshBytePreview);
    $('[data-'+name+']').addEventListener('change',refreshBytePreview);
  }
  function range() {
    const a = Number($("[data-byte-start]").value), b = Number($("[data-byte-end]").value);
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b <= a || b > bytes.length) throw Error("Select a nonempty byte range within the parsed bytes.");
    if (parsedHex !== $("[data-hex]").value) throw Error("Read the edited bytes again before selecting.");
    return [a, b];
  }
  function byteSelection(a, b) {
    anchor = a;
    cursor = b;
    $("[data-byte-start]").value = Math.min(a, b);
    $("[data-byte-end]").value = Math.max(a, b) + 1;
    for (const cell of $$("[data-byte]")) cell.setAttribute("aria-pressed", String(Number(cell.dataset.byte) >= Math.min(a, b) && Number(cell.dataset.byte) <= Math.max(a, b)));
    $("[data-byte-selection]").textContent = `Selection [${Math.min(a, b)}, ${Math.max(a, b) + 1}) \xB7 ${Math.abs(a - b) + 1} bytes`;
    refreshBytePreview();
  }
  $("[data-read-bytes]").onclick = () => {
    try {
      bytes = hexBytes($("[data-hex]").value);
      parsedHex = $("[data-hex]").value;
      const target = $("[data-byte-grid]");
      target.replaceChildren();
      for (let offset = 0; offset < bytes.length; offset += 16) {
        const row = document.createElement("div");
        row.className = "snort-byte-row";
        const label = document.createElement("span");
        label.textContent = offset.toString(16).padStart(4, "0");
        row.append(label);
        for (let i = offset; i < Math.min(offset + 16, bytes.length); i++) {
          const b = button(bytes[i].toString(16).padStart(2, "0"), () => byteSelection(i, i));
          b.dataset.byte = i;
          b.setAttribute("aria-label", `Byte ${i}: ${bytes[i].toString(16)}, ${bytes[i] >= 32 && bytes[i] < 127 ? String.fromCharCode(bytes[i]) : "nonprintable"}`);
          b.setAttribute("aria-pressed", "false");
          b.addEventListener("pointerdown", (e) => {
            if (e.button !== 0) return;
            dragging = true;
            byteSelection(i, i);
          });
          b.addEventListener("pointerenter", () => {
            if (dragging) byteSelection(anchor, i);
          });
          b.addEventListener("keydown", (e) => {
            const step = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: -16, ArrowDown: 16 }[e.key];
            if (step) {
              e.preventDefault();
              const n = Math.max(0, Math.min(bytes.length - 1, i + step));
              byteSelection(e.shiftKey ? anchor : n, n);
              $(`[data-byte="${n}"]`).focus({ preventScroll: true });
            }
          });
          row.append(b);
        }
        const ascii = document.createElement("code");
        ascii.textContent = bytes.slice(offset, offset + 16).map((v) => v >= 32 && v < 127 ? String.fromCharCode(v) : ".").join("");
        row.append(ascii);
        target.append(row);
      }
      byteSelection(0, 0);
      $("[data-byte-status]").textContent = `Read ${bytes.length} bytes.`;
    } catch (e) {
      $("[data-byte-status]").textContent = e.message;refreshBytePreview();
    }
  };
  document.addEventListener("pointerup", () => dragging = false);
  $("[data-byte-grid]").addEventListener("click", (e) => {
    if (e.detail > 0) e.stopImmediatePropagation();
  }, true);
  for (const field of ["[data-byte-start]", "[data-byte-end]"]) $(field).oninput = () => {
    try {
      const [a, b] = range();
      byteSelection(a, b - 1);
    } catch {refreshBytePreview();
    }
  };
  function selectionContent() {
    const [a, b] = range();
    const values = bytes.slice(a, b), rep = $("[data-representation]").value;
    if (rep === "text") {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(values));
      return { a, b, mixed: encodeContent(text, "text") };
    }
    if (rep === "mixed") return { a, b, mixed: values.map((v) => v >= 32 && v <= 126 && ![34, 92, 124].includes(v) ? String.fromCharCode(v) : "|" + v.toString(16).padStart(2, "0") + "|").join("") };
    return { a, b, mixed: "|" + values.map((v) => v.toString(16).padStart(2, "0")).join(" ") + "|" };
  }
  function byteAction(kind) {
    try {
      const value = selectionContent();
      if(kind==='add'){insertOption('content:"'+value.mixed+'";',$('[data-byte-buffer]').value,'[data-byte-status]');return;}
      if(!modifierTarget)throw Error("Choose a content match for replacement or positioning in this tab.");
      const c=resolveTarget(model,modifierTarget);
      if (kind === "replace") patches([contentPatch(c, value.mixed, "mixed", c.decoded.negated)]);
      else {
        if (c.kind !== "content") throw Error("Select a content match.");
        const origin = $("[data-origin]").value;
        if (origin === "frame") throw Error("Full frames are not decoded. Supply transport payload or exact inspection-buffer bytes.");
        if (origin === "payload" && !["payload", "pkt_data"].includes(c.bufferName) || origin === "application" && $("[data-origin-buffer]").value !== c.bufferName) throw Error("Input origin must match the selected inspection buffer.");
        const mods = modifierValues(c);
        if (mods.distance || mods.within) throw Error("Remove relative positioning explicitly before applying absolute positioning.");
        patches([modifierPatch(model, c, "offset", String(value.a)), modifierPatch(model, c, "depth", String(value.b - value.a))].filter(Boolean));
      }
      $("[data-byte-status]").textContent = "Applied explicit byte action.";
    } catch (e) {
      $("[data-byte-status]").textContent = e.message;
    }
  }
  $("[data-bytes-add]").onclick = () => byteAction("add");
  $("[data-bytes-replace]").onclick = () => byteAction("replace");
  $("[data-bytes-position]").onclick = () => byteAction("position");
  function logs(target, title, result) {
    if (!result) return;
    const d = document.createElement("details"), s = document.createElement("summary"), p = document.createElement("pre");
    s.textContent = title + (result.success ? " \xB7 success" : " \xB7 failed " + (result.reason || ""));
    p.textContent = `exit ${result.code}
${result.stdout || ""}
${result.stderr || ""}`;
    d.append(s, p);
    target.append(d);
  }
  async function poll() {
    try {
      const data = await tool("jobs/" + job), target = $("[data-job]");
      target.replaceChildren();
      const p = document.createElement("p");
      p.textContent = `${data.status} \xB7 ${data.engine} \xB7 profile ${data.profile}` + (data.error ? " \xB7 " + data.error : "") + (submitted !== source() ? " \xB7 Results refer to an older submitted source." : "");
      target.append(p);
      logs($("[data-job]"), "Validation diagnostics", data.validation);
      $("[data-validation]").textContent = submitted !== source() ? "Submitted source differs from current edits." : data.validation?.success ? "Snort validated the submitted rule/profile." : data.validation ? "Engine validation failed; see diagnostics." : "Validation pending.";
      for (const result of data.results) {
        const section = document.createElement("section");
        const h = document.createElement("h3");
        h.textContent = `${result.capture} \xB7 ${result.execution.success ? result.alert_count + " alerts (successful execution)" : "execution failed"}`;
        section.append(h);
        const pre = document.createElement("pre");
        pre.textContent = result.alerts.map((a) => JSON.stringify(a)).join("\n") || (result.execution.success ? "No matching alerts." : "No successful result.");
        section.append(pre);
        logs(section, "Execution logs", result.execution);
        target.append(section);
      }
      const active = ["queued", "running"].includes(data.status);
      $("[data-cancel]").disabled = !active;
      if (active) pollTimer = setTimeout(poll, 500);
      else {
        job = null;
        $("[data-validate]").disabled = $("[data-test]").disabled = !engine?.available;
      }
    } catch (e) {
      notice(e.message);
    }
  }
  async function execute(kind) {
    if (job) return;
    try {
      submitted = source();
      const fields = { source: submitted, kind };
      if (kind === "pcap") {
        fields.target = $("[data-target]").files[0];
        fields.baseline = $("[data-baseline]").files[0];
      }
      const result = await tool("jobs", fields);
      job = result.id;
      $("[data-validate]").disabled = $("[data-test]").disabled = true;
      $("[data-cancel]").disabled = false;
      poll();
    } catch (e) {
      notice(e.message);
    }
  }
  $("[data-validate]").onclick = () => execute("validate");
  $("[data-test]").onclick = () => execute("pcap");
  $("[data-cancel]").onclick = () => job && tool("jobs/" + job + "/cancel", {}).catch((e) => notice(e.message));
  new ResizeObserver(() => view.requestMeasure()).observe($("[data-rule-editor]"));
  load(EMPTY);
  const startupRevision = draftRevision;
  tool("state").then(async (state) => {
    engine = state.engine;
    cases = state.cases;
    for (const c of cases) $("[data-destination]").add(new Option(`${c.number} \xB7 ${c.name}`, c.id));
    $("[data-engine]").textContent = (engine.version ? engine.version + " \xB7 " : "") + engine.message;
    $("[data-validate]").disabled = $("[data-test]").disabled = !engine.available;
    const draft = draftRevision === startupRevision ? state.draft : null;
    caseId = draft?.context?.caseId || "";
    $("[data-dialect]").value = draft?.context?.dialect || "auto";
    if (draftRevision === startupRevision) {
      load(draft?.source || EMPTY, draft?.context?.opened || null);
      clean = draft?.context?.clean ?? source();
    }
    ready = true;
    if (draftRevision !== startupRevision && !draft) {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(saveDraft, 700);
    }
    filterCases();
    fileStatus();
    library();
    try {
      await inventory();
    } catch (e) {
      $("[data-browser-status]").textContent = e.message;
    }
    $("[data-draft]").textContent = draft ? "Loaded account draft." : "Standalone draft ready.";
  }).catch((e) => notice(e.message));
}
export {
  mountSnortTool
};
