(() => {
  function replaceLastPlainDot(hostname) {
    let position = hostname.lastIndexOf(".");
    while (
      position >= 0 &&
      hostname.slice(position - 1, position + 2) === "[.]"
    )
      position = hostname.lastIndexOf(".", position - 1);
    return position < 0
      ? hostname
      : hostname.slice(0, position) + "[.]" + hostname.slice(position + 1);
  }
  function defangIndicator(value) {
    let result = value
      .replace(/https:\/\//gi, "hxxps://")
      .replace(/http:\/\//gi, "hxxp://");
    const url = result.match(/^(.*?hxxps?:\/\/)([^/?#]+)(.*)$/i);
    if (url) {
      const authority = url[2],
        separator = authority.lastIndexOf("@"),
        userInfo = separator >= 0 ? authority.slice(0, separator + 1) : "",
        hostPort = separator >= 0 ? authority.slice(separator + 1) : authority;
      if (hostPort.startsWith("[")) return result;
      const port = hostPort.match(/:\d+$/),
        hostname = port ? hostPort.slice(0, -port[0].length) : hostPort;
      return (
        url[1] +
        userInfo +
        replaceLastPlainDot(hostname) +
        (port ? port[0] : "") +
        url[3]
      );
    }
    const trimmed = value.trim(),
      candidate = trimmed.replace(/\[\.\]/g, "."),
      domain =
        /^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9-]{2,63}\.?$/,
      ipv4 = /^(?:\d{1,3}\.){3}\d{1,3}$/;
    if (!domain.test(candidate) && !ipv4.test(candidate)) return result;
    const start = value.indexOf(trimmed);
    return (
      value.slice(0, start) +
      replaceLastPlainDot(trimmed) +
      value.slice(start + trimmed.length)
    );
  }
  function refangIndicator(value) {
    return value
      .replace(/\[\.\]/g, ".")
      .replace(/hxxps:\/\//gi, "https://")
      .replace(/hxxp:\/\//gi, "http://");
  }
  window.MareIndicatorValues = {
    defang: defangIndicator,
    refang: refangIndicator,
  };
  const root = document.getElementById("indicator-workspace");
  if (!root) return;
  const cid = root.dataset.caseId,
    locked = root.dataset.locked === "true",
    status = document.getElementById("indicator-status"),
    container = document.getElementById("indicator-sections");
  let state,
    dirty = false,
    busy = false,
    importTarget = null,
    editTarget = null, importFormat = "csv", importPreview = null, previewGeneration = 0;
  function changed() {
    dirty = true;
    status.textContent = "Unsaved changes";
    updateDownloadState();
    showValidation();
    highlightDuplicates();
  }
  function updateDownloadState(){
    document.getElementById("download-indicator-stix").disabled=locked||busy||Boolean(state&&!dirty&&!state.stix.available);
  }
  function typeInfo(value){return state.types.find(item=>item.name.toLowerCase()===value.trim().toLowerCase())||state.types.find(item=>[item.label,...item.aliases].some(alias=>alias.toLowerCase()===value.trim().toLowerCase()));}
  // Cache only authoritative results for the exact live row object/content.
  // Row indices alone become stale after edits, deletion or an in-flight save.
  const validation = new WeakMap();
  const signature = row => JSON.stringify(row);
  let openError = null;
  const errorTip = document.createElement("div");
  errorTip.id = "indicator-validation-error";
  errorTip.className = "indicator-validation-tooltip";
  errorTip.setAttribute("role", "tooltip");
  errorTip.hidden = true;
  root.append(errorTip);
  function closeError() {
    openError?.setAttribute("aria-expanded", "false");
    openError = null;
    errorTip.hidden = true;
  }
  function showError(control) {
    closeError();
    openError = control;
    control.setAttribute("aria-expanded", "true");
    errorTip.textContent = control.dataset.error;
    errorTip.dataset.validation = control.parentElement.dataset.validation;
    errorTip.hidden = false;
    const rect = control.getBoundingClientRect();
    errorTip.style.left = Math.max(8, Math.min(rect.left, innerWidth - errorTip.offsetWidth - 8)) + "px";
    errorTip.style.top = Math.max(8, rect.bottom + 6 + errorTip.offsetHeight <= innerHeight - 8
      ? rect.bottom + 6 : rect.top - errorTip.offsetHeight - 6) + "px";
  }
  document.addEventListener("pointerdown", event => {
    if (!openError?.contains(event.target)) closeError();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeError(); });
  window.addEventListener("scroll", closeError, true);
  window.addEventListener("resize", closeError);
  function rememberValidation() {
    const duplicates = new Set((state.stix?.duplicates || []).map(item => item.section_id + ":" + item.row));
    const issues = new Map((state.stix?.issues || []).map(issue => [issue.section_id + ":" + issue.row, issue.reason]));
    for (const section of state.sections) section.rows.forEach((row, index) => {
      validation.set(row, {signature: signature(row), error: issues.get(section.id + ":" + (index + 1)), duplicate: duplicates.has(section.id + ":" + (index + 1))});
    });
  }
  function showValidation() {
    for (const section of state.sections) {
      const body = container.querySelector('[data-section="' + section.id + '"] tbody');
      if (!body) continue;
      [...body.rows].forEach((tr, index) => {
        const row = section.rows[index], slot = tr.querySelector(".indicator-validation-slot");
        if (!row || !slot) return;
        const result = validation.get(row);
        const kind = !row.some(value => value.trim()) ? "blank"
          : !result || result.signature !== signature(row) ? "pending"
          : result.error ? "invalid" : result.duplicate ? "duplicate" : "valid";
        if (slot.dataset.validation === kind && slot.dataset.error === (result?.error || "")) return;
        if (slot.contains(openError)) closeError();
        slot.replaceChildren();
        slot.dataset.validation = kind;
        slot.dataset.error = result?.error || "";
        if (kind === "blank" || kind === "pending") return;
        const icon = document.createElement(kind === "valid" ? "span" : "button");
        icon.className = "indicator-validation-icon";
        // Match the application's existing text-symbol status/disclosure icons.
        icon.textContent = kind === "valid" ? "✓" : kind === "duplicate" ? "⚠" : "✕";
        icon.setAttribute("aria-label", kind === "valid" ? "Valid indicator" : kind === "duplicate" ? "Duplicate rows detected" : "Invalid indicator: " + result.error);
        if (kind === "valid") icon.setAttribute("role", "img");
        else {
          icon.type = "button";
          icon.dataset.error = kind === "duplicate" ? "Duplicate rows detected" : result.error;
          icon.setAttribute("aria-describedby", errorTip.id);
          icon.setAttribute("aria-expanded", "false");
          icon.addEventListener("mouseenter", () => showError(icon));
          icon.addEventListener("mouseleave", () => { if (document.activeElement !== icon) closeError(); });
          icon.addEventListener("focus", () => showError(icon));
          icon.addEventListener("blur", closeError);
          icon.addEventListener("click", event => { event.stopPropagation(); showError(icon); });
          // Let the button use native keyboard activation instead of cell navigation.
          icon.addEventListener("keydown", event => {
            event.stopPropagation();
            if (event.key === "Escape") closeError();
            if (event.key === "Tab") {
              event.preventDefault();
              (event.shiftKey ? tr.cells[0].querySelector("input") : tr.cells[1]).focus({preventScroll:true});
            }
          });
        }
        slot.append(icon);
      });
    }
  }
  function editable() {
    root.querySelector("fieldset").disabled = locked || busy;
    container
      .querySelectorAll("td[data-column]")
      .forEach(
        (cell) =>
          (cell.contentEditable = locked || busy || cell.dataset.column==='0' ? "false" : "plaintext-only"),
      );
    container.querySelectorAll('td[data-column="0"] input').forEach(input=>input.disabled=locked||busy);
    updateDownloadState();
  }
  function focusCell(section,row,column){
    const cell=container.querySelector('[data-section="'+section.id+'"] tbody')?.rows[row]?.querySelector('td[data-column="'+column+'"]');
    (cell?.querySelector("input")||cell)?.focus();
  }
  function button(text, action) {
    const node = document.createElement("button");
    node.type = "button";
    node.textContent = text;
    node.addEventListener("click", action);
    return node;
  }
  function transformValues(section, transform) {
    let changedValues = false;
    for (const row of section.rows) {
      const value = transform(row[1]);
      if (value !== row[1]) {
        row[1] = value;
        changedValues = true;
      }
    }
    if (changedValues) {
      changed();
      render();
    } else status.textContent = "No indicator values needed this change.";
  }
  function highlightDuplicates() {
    const focused = document.activeElement?.closest(".indicator-table tbody tr");
    const article = focused?.closest(".indicator-section");
    const section = state?.sections.find(item => item.id === article?.dataset.section);
    const value = section?.rows[focused?.sectionRowIndex]?.[1];
    for (const item of state?.sections || []) {
      const body = container.querySelector('[data-section="' + item.id + '"] tbody');
      if (!body) continue;
      [...body.rows].forEach((tr, index) => {
        tr.classList.toggle("indicator-duplicate-match", tr !== focused && Boolean(value?.trim()) && item.rows[index]?.[1] === value);
      });
    }
  }
  container.addEventListener("focusin", highlightDuplicates);
  container.addEventListener("focusout", () => queueMicrotask(highlightDuplicates));
  function removeDuplicates(section) {
    const seen = new Set(), rows = [], metadata = [];
    section.rows.forEach((row, index) => {
      const value = row[1];
      if (value.trim() && seen.has(value)) return;
      if (value.trim()) seen.add(value);
      rows.push(row);
      metadata.push(section.row_meta?.[index] ?? null);
    });
    const removed = section.rows.length - rows.length;
    if (removed) {
      section.rows = rows;
      if (section.row_meta) section.row_meta = metadata;
      changed();
      render();
      container.querySelector('[data-section="' + section.id + '"] .indicator-remove-duplicates').focus({preventScroll:true});
    }
    status.textContent = removed
      ? `Removed ${removed} duplicate row${removed === 1 ? "" : "s"}; first instances preserved. Unsaved changes.`
      : "No duplicate values in this section.";
  }
  function render() {
    closeError();
    if (!dirty) rememberValidation();
    container.replaceChildren();
    for (const section of state.sections) {
      const article = document.createElement("article");
      article.className = "indicator-section";
      article.dataset.section = section.id;
      const heading = document.createElement("h3");
      heading.textContent = section.title;
      const description = document.createElement("p");
      description.className = "indicator-section-description";
      description.textContent = section.description;
      const actions = document.createElement("div");
      actions.className = "report-actions";
      const add = button("Add row", () => {
        if (locked || busy) return;
        section.rows.push(["", "", ""]);
        if(section.row_meta)section.row_meta.push(null);
        changed();
        render();
        focusCell(section, section.rows.length - 1, 0);
      });
      actions.append(
        add,
        button(
          "Import",
          run(async () => {
            if (dirty) await save();
            importTarget = section.id;
            document.getElementById("indicator-import-target").textContent =
              "Section: " + section.title;
            document.getElementById("indicator-csv-file").value = "";
            document.getElementById("indicator-csv-text").value = "";
            document.getElementById("indicator-stix-file").value = "";
            selectImportFormat("csv");
            document.getElementById("indicator-import-dialog").showModal();
          }),
        ),
      );
      actions.append(
        button(
          "Defang",
          run(() => transformValues(section, defangIndicator)),
        ),
        button(
          "Refang",
          run(() => transformValues(section, refangIndicator)),
        ),
      );
      const deduplicate = button("Remove duplicates", () => {
        if (!locked && !busy) removeDuplicates(section);
      });
      deduplicate.className = "indicator-remove-duplicates";
      actions.append(deduplicate);
      actions.append(
        button("Edit section", () => {
          if (locked || busy) return;
          editTarget = section.id;
          const form = document.getElementById("indicator-section-form");
          form.elements.title.value = section.title;
          form.elements.description.value = section.description;
          document.getElementById("indicator-section-title").textContent =
            "Edit section";
          form.querySelector('[type="submit"]').textContent = "Apply changes";
          document.getElementById("indicator-section-dialog").showModal();
        }),
      );
      if (section.id !== "default")
        actions.append(
          button("Delete section", () => {
            if (locked || busy) return;
            if (
              !confirm(
                'Delete section "' +
                  section.title +
                  '" and all ' +
                  section.rows.length +
                  " indicator rows in it? Save table to apply this deletion.",
              )
            )
              return;
            state.sections = state.sections.filter(
              (item) => item.id !== section.id,
            );
            changed();
            render();
          }),
        );
      const wrap = document.createElement("div");
      wrap.className = "indicator-table-wrap";
      const table = document.createElement("table");
      table.className = "indicator-table";
      const head = table.createTHead().insertRow();
      for (const name of ["type", "value", "description", ""]) {
        const cell = document.createElement("th");
        cell.textContent = name;
        cell.scope = "col";
        head.append(cell);
      }
      const body = table.createTBody();
      section.rows.forEach((row, index) => {
        const tr = body.insertRow();
        row.forEach((value, column) => {
          const cell = tr.insertCell();
          cell.dataset.column = column;
          cell.textContent = value;
          cell.tabIndex = locked ? -1 : 0;
          cell.setAttribute(
            "aria-label",
            section.title +
              ", row " +
              (index + 1) +
              ", " +
              state.columns[column],
          );
          cell.setAttribute("role", "textbox");
          cell.setAttribute("aria-multiline", "true");
          if(column===0){
            cell.contentEditable="false";
            const input=document.createElement("input");input.type="text";input.classList.add("indicator-type-input");input.value=value;input.setAttribute("list","indicator-type-options");input.setAttribute("aria-label",cell.getAttribute("aria-label"));input.setAttribute("role","combobox");input.setAttribute("aria-autocomplete","list");input.disabled=locked||busy;
            const controls=document.createElement("div");controls.className="indicator-type-controls";
            const slot=document.createElement("span");slot.className="indicator-validation-slot";
            input.addEventListener("input",()=>{row[0]=input.value;changed();});
            input.addEventListener("keydown",event=>{if(event.key==="Enter")event.stopPropagation();});
            controls.append(input,slot);cell.replaceChildren(controls);
          }
          cell.addEventListener("input", () => {
            if(column===0)return;
            section.rows[index][column] = cell.innerText.replace(/\r/g, "");
            changed();
          });
          cell.addEventListener("keydown", (event) => {
            if (locked || busy) return;
            if (event.key === "Tab") {
              if (column === 0 && !event.shiftKey && event.target === cell.querySelector("input")) {
                const error = cell.querySelector("button.indicator-validation-icon");
                if (error) { event.preventDefault(); error.focus({preventScroll:true}); return; }
              }
              event.preventDefault();
              let next = index * 3 + column + (event.shiftKey ? -1 : 1);
              if (next < 0) {
                add.focus();
                return;
              }
              if (next >= section.rows.length * 3) {
                section.rows.push(["", "", ""]);
        if(section.row_meta)section.row_meta.push(null);
                changed();
                render();
              }
              focusCell(section, Math.floor(next / 3), next % 3);
            } else if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (index === section.rows.length - 1) {
                section.rows.push(["", "", ""]);
        if(section.row_meta)section.row_meta.push(null);
                changed();
                render();
              }
              focusCell(section, index + 1, column);
            }
          });
          cell.addEventListener("paste", (event) => {
            if(column===0)return;
            event.preventDefault();
            if (locked || busy) return;
            const selection = window.getSelection();
            if (!selection.rangeCount) return;
            const range = selection.getRangeAt(0);
            if (!cell.contains(range.commonAncestorContainer)) return;
            range.deleteContents();
            const node = document.createTextNode(
              event.clipboardData.getData("text/plain"),
            );
            range.insertNode(node);
            range.setStartAfter(node);
            range.collapse(true);
            selection.removeAllRanges();
            selection.addRange(range);
            if(column===0)return;
            section.rows[index][column] = cell.innerText.replace(/\r/g, "");
            changed();
          });
        });
        const action = tr.insertCell(),
          remove = button("Delete", () => {
            if (locked || busy) return;
            section.rows.splice(index, 1);
            section.row_meta?.splice(index,1);
            changed();
            render();
          });
        remove.className = "indicator-delete";
        remove.setAttribute(
          "aria-label",
          "Delete " + section.title + " row " + (index + 1),
        );
        action.append(remove);
      });
      wrap.append(table);
      article.append(heading, description, actions, wrap);
      container.append(article);
    }
    editable();showValidation();highlightDuplicates();
  }
  async function request(path, data) {
    const response = await fetch(
      "/cases/" + cid + "/indicators" + path,
      data ? { method: "POST", body: data } : {},
    );
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Request failed");
    return result;
  }
  async function refreshPackage() {
    await window.MarePackage?.refresh(cid);
  }
  function data() {
    const form = new FormData();
    form.set("csrf", root.dataset.csrf);
    form.set("revision", state.revision);
    return form;
  }
  async function save() {
    const form = data();
    form.set("sections", JSON.stringify(state.sections));
    state = await request("", form);
    dirty = false;
    autosaveTimer.reset();
    status.textContent = state.stix.available ? "All sections saved to CSV and STIX (refanged machine-readable values)." : "Draft and CSV saved. STIX unavailable: correct flagged rows.";
    render();
    await refreshPackage();
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
  document.getElementById("save-indicators").addEventListener(
    "click",
    run(async () => {
      autosaveTimer.reset();
      await save();
    }),
  );
  document
    .getElementById("add-indicator-section")
    .addEventListener("click", () => {
      if (locked || busy || !state) return;
      editTarget = null;
      const form = document.getElementById("indicator-section-form");
      form.reset();
      document.getElementById("indicator-section-title").textContent =
        "Add new section";
      form.querySelector('[type="submit"]').textContent = "Add section";
      document.getElementById("indicator-section-dialog").showModal();
    });
  document
    .getElementById("indicator-section-form")
    .addEventListener("submit", (event) => {
      event.preventDefault();
      if (locked || busy || !state) return;
      const form = event.target,
        title = form.elements.title.value.trim();
      if (!title) {
        form.elements.title.focus();
        return;
      }
      if (editTarget) {
        const section = state.sections.find((item) => item.id === editTarget);
        if (!section) return;
        section.title = title;
        section.description = form.elements.description.value;
      } else
        state.sections.push({
          id:
            "section-" +
            Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
              value.toString(16).padStart(2, "0"),
            ).join(""),
          title: title,
          description: form.elements.description.value,
          rows: [],
        });
      changed();
      render();
      document.getElementById("indicator-section-dialog").close();
      const target = editTarget
        ? container.querySelector('[data-section="' + editTarget + '"]')
        : container.lastElementChild;
      target?.scrollIntoView({ block: "nearest" });
      editTarget = null;
    });
  document.querySelectorAll("[data-close-indicator-dialog]").forEach((node) =>
    node.addEventListener("click", () => {
      if (!busy) node.closest("dialog").close();
    }),
  );
  function clearPreview(){
    previewGeneration++;importPreview=null;
    document.getElementById("indicator-import-preview").replaceChildren();
    document.getElementById("indicator-import-status").textContent="";
    document.getElementById("confirm-indicator-import").disabled=true;
  }
  function selectImportFormat(format){
    importFormat=format;clearPreview();
    document.querySelectorAll("[data-indicator-format]").forEach(tab=>{
      const active=tab.dataset.indicatorFormat===format;tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden=!active;
    });
  }
  const tabs=[...document.querySelectorAll("[data-indicator-format]")];
  tabs.forEach(tab=>{
    tab.addEventListener("click",()=>selectImportFormat(tab.dataset.indicatorFormat));
    tab.addEventListener("keydown",event=>{
      if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
      event.preventDefault();const next=event.key==="Home"?tabs[0]:event.key==="End"?tabs[1]:tabs[1-tabs.indexOf(tab)];selectImportFormat(next.dataset.indicatorFormat);next.focus();
    });
  });
  ["indicator-csv-file","indicator-csv-text","indicator-stix-file"].forEach(id=>document.getElementById(id).addEventListener("input",clearPreview));
  document.getElementById("indicator-import-dialog").addEventListener("close",clearPreview);
  document.getElementById("preview-indicator-import").addEventListener("click",run(async()=>{
    clearPreview();const generation=previewGeneration,form=data(),message=document.getElementById("indicator-import-status");
    form.set("section_id",importTarget);form.set("format",importFormat);
    try{
    if(importFormat==="csv"){
      const file=document.getElementById("indicator-csv-file").files[0],text=document.getElementById("indicator-csv-text").value;
      if(file&&text.trim())throw Error("Choose a CSV file or pasted CSV, not both.");form.set("csv",file||text);
    }else{
      const file=document.getElementById("indicator-stix-file").files[0];if(!file)throw Error("Choose a STIX JSON file.");form.set("stix",file);
    }
    message.textContent="Validating import…";
      const preview=await request("/import/preview",form);
      if(generation!==previewGeneration)return;
      importPreview=preview;const host=document.getElementById("indicator-import-preview");
      const ready=preview.rows.filter(item=>!item.reason&&!item.duplicate).length;
      message.textContent=`${ready} supported rows ready · ${preview.rows.filter(item=>item.reason).length} need correction · ${preview.skipped.length} unsupported/skipped · ${preview.rows.filter(item=>item.duplicate).length} exact destination duplicates · ${preview.rows.filter(item=>item.normalized).length} normalized aliases.`;
      for(const item of preview.rows){
        const line=document.createElement("div");line.className="indicator-preview-row";
        const accept=document.createElement("input");accept.type="checkbox";accept.checked=true;accept.setAttribute("aria-label","Accept this row");item.accept=accept;
        line.append(accept);
        item.row.forEach((value,index)=>{const field=document.createElement(index===0?"input":"textarea");field.value=value;field.setAttribute("aria-label",["Type","Value","Description"][index]);if(index===0){field.classList.add("indicator-type-input");field.setAttribute("list","indicator-type-options");}field.addEventListener("input",()=>{item.row[index]=field.value;});line.append(field);});
        const reason=document.createElement("small");reason.textContent=item.reason?"Needs correction: "+item.reason:item.duplicate?"Exact duplicate in destination (skipped by default)":"Ready";line.append(reason);
        if(item.unknown){
          for(const kind of ["text","other"]){const button=document.createElement("button");button.type="button";button.textContent="Use "+kind;button.addEventListener("click",()=>{item.original_type=item.original_type??item.row[0];item.row[0]=kind;item.to_ids=false;line.querySelector('input[list]').value=kind;reason.textContent="Contextual "+kind+"; original type retained: "+item.original_type;});line.append(button);}
        }
        host.append(line);
      }
      for(const skipped of preview.skipped){const item=document.createElement("p");item.textContent=`Skipped ${skipped.type} ${skipped.id}: ${skipped.reason}`;host.append(item);}
      document.getElementById("confirm-indicator-import").disabled=!preview.rows.length;
    }catch(error){message.textContent=error.message;throw error;}
  }));
  document.getElementById("confirm-indicator-import").addEventListener("click",run(async()=>{
    if(!importPreview||importPreview.section_id!==importTarget)throw Error("Preview this upload before applying it.");
    const form=data();form.set("revision",importPreview.revision);form.set("section_id",importTarget);form.set("skip_duplicates",document.getElementById("indicator-skip-duplicates").checked?"1":"0");
    const accepted=importPreview.rows.filter(item=>item.accept.checked);
    form.set("accepted_rows",JSON.stringify(accepted.map(item=>item.row)));
    form.set("accepted_original_types",JSON.stringify(accepted.map(item=>item.original_type??null)));
    form.set("accepted_intents",JSON.stringify(accepted.map(item=>item.to_ids??null)));
    try{
      const result=await request("/import",form);state=result;dirty=false;autosaveTimer.reset();render();
      status.textContent=`Added ${result.added} rows; skipped ${result.skipped_duplicates} duplicates. ${result.stix.available?'CSV/STIX saved.':'Draft/CSV saved; correct flagged rows for STIX.'}`;
      document.getElementById("indicator-import-dialog").close();await refreshPackage();
    }catch(error){document.getElementById("indicator-import-status").textContent=error.message;throw error;}
  }));
  document.getElementById("download-indicator-stix").addEventListener("click",run(async()=>{
    await save();if(!state.stix.available)throw Error("STIX unavailable: correct the flagged section/row errors, then save again.");
    const response=await fetch(`/cases/${cid}/indicators/stix`);if(!response.ok){const error=await response.json();throw Error(error.error);}
    const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");link.href=url;link.download="indicators.stix.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }));
  request("")
    .then((result) => {
      state = result;
      const options=document.getElementById("indicator-type-options");
      for(const item of [...state.types].sort((a,b)=>a.category.localeCompare(b.category)||a.name.localeCompare(b.name))){const option=document.createElement("option");option.value=item.name;option.label=item.category+" — "+item.label+([...item.aliases,...item.search_aliases].length?" — "+[...item.aliases,...item.search_aliases].join(", "):"");options.append(option);}
      render();
      status.textContent = locked
        ? "Read-only. Reopen the case to edit indicators."
        : "Ready. Click a cell to edit; Tab moves between cells, Enter moves down, and Shift+Enter adds a line break.";
    })
    .catch((e) => (status.textContent = e.message));
  const autosaveTimer = window.MareAutosave.register({
    onCountdown: (seconds, running, paused) => {
      const label = document.getElementById("save-indicators-countdown");
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
      const snapshot = JSON.stringify(state.sections),
        form = data();
      form.set("sections", snapshot);
      form.set("automatic", "1");
      try {
        const result = await request("", form);
        state.revision = result.revision;
        const newerChanges=JSON.stringify(state.sections)!==snapshot,submitted=JSON.parse(snapshot);
        // Keep section/row objects referenced by live cell event handlers. Even
        // concurrent edits need the IDs allocated by the completed save.
        for(const section of state.sections){
          const saved=result.sections.find(item=>item.id===section.id),before=submitted.find(item=>item.id===section.id);
          if(!saved||!before)continue;
          section.row_meta=saved.row_meta;section.stix_meta=saved.stix_meta;
          section.rows.forEach((row,index)=>{
            if(JSON.stringify(row)!==JSON.stringify(before.rows[index]))return;
            row[0]=saved.rows[index][0];
            const input=container.querySelector('[data-section="'+section.id+'"] tbody')?.rows[index]?.querySelector('td[data-column="0"] input');
            if(input&&input.value!==row[0])input.value=row[0];
          });
        }
        state.stix=newerChanges?{...state.stix,available:false}:result.stix;
        dirty = newerChanges;
        if(!newerChanges)rememberValidation();
        showValidation();
        status.textContent =
          "Autosaved to iocs/indicators.csv at " +
          new Date().toLocaleTimeString() +
          (dirty ? " — newer changes pending" : result.stix.available ? " — STIX current" : " — STIX unavailable; correct flagged rows");
        await refreshPackage();
      } finally {
        busy = false;updateDownloadState();
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
