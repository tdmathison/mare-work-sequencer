import {runCommand, insertBlock, pastedTable, tableMarkdown} from './markdown-commands';
const format = [['h1','Heading 1'],['h2','Heading 2'],['h3','Heading 3'],['h4','Heading 4'],['h5','Heading 5'],['h6','Heading 6'],['paragraph','Normal text'],['bold','Bold'],['italic','Italic'],['strike','Strikethrough'],['inline-code','Inline code'],['code','Fenced code block'],['bullet','Bulleted list'],['numbered','Numbered list'],['quote','Blockquote'],['rule','Horizontal rule'],['indent','Indent'],['outdent','Outdent'],['align-left','Left align'],['align-center','Center align'],['align-right','Right align']];
let dialogSequence = 0;
const insert = [['url','Link'],['image','Image'],['table','Table'],['html-table','Paste Table'],['code','Fenced code block'],['rule','Horizontal rule']];
function button(label, command) {
  const node = document.createElement('button'); node.type = 'button'; node.textContent = label;
  if (command) node.dataset.md = command;
  return node;
}
function dialog(toolbar, label) {
  const node = document.createElement('dialog'); node.setAttribute('aria-label', label);
  const heading = document.createElement('h2'); heading.textContent = label; node.append(heading); toolbar.append(node); node.addEventListener('keydown',event=>{ if(event.key === 'Escape') event.stopPropagation(); }); return node;
}
export function mountToolbar(editor) {
  const section = editor.source.closest('.manual-section');
  const toolbar = section?.querySelector('.markdown-toolbar') || document.createElement('div');
  if (!toolbar.isConnected) { toolbar.className = 'markdown-toolbar'; editor.container.before(toolbar); }
  toolbar.setAttribute('role','toolbar'); toolbar.setAttribute('aria-label','Markdown commands');
  const menuGroup = document.createElement('div'); menuGroup.className = 'markdown-toolbar-menus'; toolbar.append(menuGroup);
  const actions = document.createElement('div'); actions.className = 'markdown-toolbar-actions'; toolbar.append(actions);
  const menus = new Map();
  // Keep menus in their original DOM (including dialog/fieldset semantics),
  // but position against the viewport so scroll-container overflow cannot clip them.
  function positionMenus() {
    const viewport = window.visualViewport;
    const leftEdge = (viewport?.offsetLeft || 0) + 8;
    const topEdge = (viewport?.offsetTop || 0) + 8;
    const rightEdge = leftEdge + (viewport?.width || window.innerWidth) - 16;
    const bottomEdge = topEdge + (viewport?.height || window.innerHeight) - 16;
    for (const {menu, items} of menus.values()) {
      if (!menu.open) continue;
      const anchor = menu.querySelector('summary').getBoundingClientRect();
      const below = Math.max(0, bottomEdge - anchor.bottom);
      const above = Math.max(0, anchor.top - topEdge);
      const desired = Math.min(540, items.scrollHeight + 2);
      const upwards = desired > below && above > below;
      const available = upwards ? above : below;
      items.style.maxHeight = `${Math.min(540, available)}px`;
      items.style.left = `${Math.max(leftEdge, Math.min(anchor.left, rightEdge - items.getBoundingClientRect().width))}px`;
      items.style.top = `${upwards ? anchor.top - items.getBoundingClientRect().height : anchor.bottom}px`;
    }
  }
  let positionFrame = null;
  function schedulePosition() {
    if (![...menus.values()].some(({menu}) => menu.open)) return;
    if (positionFrame === null) positionFrame = requestAnimationFrame(() => { positionFrame = null; positionMenus(); });
  }

  for (const [label, commands] of [['Format', format], ['Insert', insert], ['View', []]]) {
    const menu = document.createElement('details'); menu.className = 'markdown-menu';
    const summary = document.createElement('summary'); summary.textContent = label; menu.append(summary);
    const items = document.createElement('div'); items.className = 'markdown-menu-items'; menu.append(items); menus.set(label, {menu, items}); menuGroup.append(menu);
    menu.addEventListener('toggle', () => { if (menu.open) positionMenus(); });
    summary.addEventListener('click', () => { for (const other of menus.values()) if (other.menu !== menu) other.menu.open = false; });
    for (const [command, text] of commands) {
      const node = button(text, command); items.append(node);
      if (command === 'image' && !section?.querySelector('.markdown-image-input')) { node.disabled = true; node.title = 'Image uploads are available in report sections and tasks.'; }
      node.addEventListener('click', () => {
        menu.open = false;
        if (command === 'image') { const picker = section.querySelector('.markdown-image-input'); picker.value = ''; picker.click(); }
        else if (command === 'table') openTable();
        else if (command === 'html-table') openPaste();
        else runCommand(editor, command);
      });
    }
  }
  const controls = new Map();
  for (const [setting, label, css] of [['wrap','Word Wrap','word-wrap'],['numbers','Line Numbers','line-numbers-toggle'],['active','Active Line Highlight','active-line-toggle'],['folding','Code Folding','code-folding-toggle']]) {
    const node = document.createElement('label'); node.className = 'editor-view-option';
    const input = document.createElement('input'); input.type = 'checkbox'; input.checked = input.defaultChecked = editor.settings[setting]; input.className = css;
    node.append(input, document.createTextNode(label)); menus.get('View').items.append(node); controls.set(setting,input);
    input.addEventListener('change', () => editor.setPreference(setting,input.checked));
  }
  const preview = section?.querySelector('.editor-preview-tab,[data-task-preview]'), raw = section?.querySelector('.editor-raw-tab,[data-task-raw]');
  const pane = section?.querySelector('.markdown-preview');
  const existingExpand = section?.querySelector('.expand-editor');
  function actionButton(attribute) {
    const node = button(''); node.dataset[attribute] = '';
    const icon = document.createElement('span'); icon.className = 'markdown-action-icon'; icon.setAttribute('aria-hidden','true');
    const label = document.createElement('span'); node.append(icon,label); actions.append(node);
    return {node, icon, label};
  }
  const previewAction = preview && raw && pane ? actionButton('editorPreview') : null;
  const expandAction = actionButton('editorExpand'), expand = expandAction.node;
  function syncActions() {
    if (previewAction) {
      previewAction.label.textContent = pane.hidden ? 'Show Preview' : 'Hide Preview';
      previewAction.icon.textContent = pane.hidden ? '◉' : '○';
      previewAction.node.setAttribute('aria-pressed',String(!pane.hidden));
    }
    const expanded = existingExpand ? existingExpand.getAttribute('aria-expanded') === 'true' : editor.workspace?.classList.contains('mare-editor-expanded');
    expandAction.label.textContent = expanded ? 'Collapse' : 'Expand';
    expandAction.icon.textContent = expanded ? '↙' : '↗';
    expand.setAttribute('aria-expanded',String(Boolean(expanded)));
  }
  function closeMenus() { for (const {menu} of menus.values()) menu.open = false; }
  previewAction?.node.addEventListener('click', () => {
    closeMenus(); (pane.hidden ? preview : raw).click(); syncActions();
  });
  if (section && !existingExpand) { expand.disabled = true; expand.title = 'Task editors already use the expanded task workspace.'; }
  expand.addEventListener('click', () => {
    closeMenus();
    if (existingExpand) existingExpand.click();
    else {
      editor.preserveLayout(); editor.workspace.classList.toggle('mare-editor-expanded');
      editor.restoreLayout(); editor.focus();
    }
    syncActions();
  });
  const actionObserver = new MutationObserver(syncActions);
  if (pane) actionObserver.observe(pane, {attributes:true,attributeFilter:['hidden']});
  if (existingExpand) actionObserver.observe(existingExpand, {attributes:true,attributeFilter:['aria-expanded']});
  if (editor.workspace) actionObserver.observe(editor.workspace, {attributes:true,attributeFilter:['class']});
  syncActions();
  const table = dialog(toolbar, 'Insert Table'); table.className = 'markdown-insert-table-dialog';
  const fields = {};
  for (const [name, label, min, max, value] of [['columns','Columns',1,20,2],['rows','Body rows (excluding header)',1,100,2]]) {
    const node = document.createElement('label'); node.textContent = label;
    const input = document.createElement('input'); Object.assign(input,{type:'number',min:String(min),max:String(max),value:String(value),required:true}); // Dialog-only validation must never block the surrounding report/task form.
    input.setAttribute('form', 'mare-table-dialog-only-' + (++dialogSequence));
    input.dataset.tableSize = name; node.append(input); table.append(node); fields[name] = input;
  }
  const tableError = document.createElement('p'); tableError.setAttribute('role','status'); table.append(tableError);
  const create = button('Insert table'); create.dataset.tableCreate = ''; const cancel = button('Cancel'); table.append(create,cancel);
  let tableSelection;
  function openTable() { if (editor.readOnly) return; tableSelection = editor.view.state.selection; tableError.textContent = ''; table.showModal(); fields.columns.focus(); }
  create.addEventListener('click', () => {
    const columns = Number(fields.columns.value), rows = Number(fields.rows.value);
    if (!Number.isInteger(columns) || columns < 1 || columns > 20 || !Number.isInteger(rows) || rows < 1 || rows > 100) { tableError.textContent = 'Choose 1–20 columns and 1–100 body rows.'; return; }
    editor.view.dispatch({selection: tableSelection});
    const values = [Array.from({length:columns},(_,i)=>'Column'+(i+1)),...Array.from({length:rows},()=>Array(columns).fill(''))];
    table.close(); insertBlock(editor,tableMarkdown(values),{header:true});
  });
  cancel.addEventListener('click',()=>table.close());
  table.addEventListener('close',()=>editor.focus());
  const paste = dialog(toolbar,'Paste Table'); paste.className = 'markdown-table-dialog';
  const label = document.createElement('label'); label.textContent = 'HTML or tab-delimited table';
  const input = document.createElement('textarea'); input.className = 'markdown-table-input'; input.rows = 10; label.append(input); paste.append(label);
  const error = document.createElement('p'); error.setAttribute('role','status'); paste.append(error);
  const convert = button('Convert'); convert.dataset.htmlTableConvert = ''; const close = button('Cancel'); close.dataset.htmlTableClose = ''; paste.append(convert,close);
  let clipboardHTML = '', clipboardPlain = '', pasteSelection;
  function openPaste() { if (editor.readOnly) return; clipboardHTML = clipboardPlain = ''; input.value = ''; error.textContent = ''; pasteSelection = editor.view.state.selection; paste.showModal(); input.focus(); }
  input.addEventListener('paste',event=>{
    clipboardHTML = event.clipboardData?.getData('text/html') || ''; clipboardPlain = event.clipboardData?.getData('text/plain') || '';
    if (clipboardHTML && pastedTable(clipboardHTML, '')) { event.preventDefault(); input.value = clipboardPlain || clipboardHTML; }
  });
  input.addEventListener('input',()=>{ clipboardHTML = clipboardPlain = ''; });
  convert.addEventListener('click',()=>{
    const result = pastedTable(clipboardHTML || input.value, clipboardPlain || input.value);
    if (!result) { error.textContent = 'Paste an HTML table or tab-delimited table text.'; return; }
    editor.view.dispatch({selection:pasteSelection}); paste.close(); insertBlock(editor,result,{afterBlock:true});
  });
  close.addEventListener('click',()=>paste.close()); paste.addEventListener('close',()=>editor.focus());
  // Capture Escape before expanded-workspace handlers, but leave CM search alone.
  toolbar.addEventListener('keydown',event=>{
    if (event.key === 'Escape' && [...menus.values()].some(({menu})=>menu.open)) {
      event.preventDefault(); event.stopPropagation(); for (const {menu} of menus.values()) menu.open = false; editor.focus();
    }
  });
  const outside = event => { if (!toolbar.contains(event.target)) for (const {menu} of menus.values()) menu.open = false; };
  const escapeExpanded = event => {
    if (event.key !== 'Escape' || event.defaultPrevented || !editor.workspace?.classList.contains('mare-editor-expanded') || toolbar.querySelector('dialog[open]')) return;
    event.preventDefault(); expand.click();
  };
  const layoutObserver = new ResizeObserver(schedulePosition);
  layoutObserver.observe(toolbar);
  window.addEventListener('resize',schedulePosition);
  document.addEventListener('scroll',schedulePosition,true);
  window.visualViewport?.addEventListener('resize',schedulePosition);
  window.visualViewport?.addEventListener('scroll',schedulePosition);
  document.addEventListener('click',outside);
  document.addEventListener('keydown',escapeExpanded);
  return {controls, destroy() {
    layoutObserver.disconnect();
    if (positionFrame !== null) cancelAnimationFrame(positionFrame);
    window.removeEventListener('resize',schedulePosition);
    document.removeEventListener('scroll',schedulePosition,true);
    window.visualViewport?.removeEventListener('resize',schedulePosition);
    window.visualViewport?.removeEventListener('scroll',schedulePosition); document.removeEventListener('click',outside); document.removeEventListener('keydown',escapeExpanded); actionObserver.disconnect(); toolbar.remove(); }};
}
