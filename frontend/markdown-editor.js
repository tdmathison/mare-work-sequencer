import {Annotation, Compartment, EditorState, Transaction} from '@codemirror/state';
import {EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, rectangularSelection, placeholder} from '@codemirror/view';
import {defaultKeymap, history, historyKeymap, indentWithTab, isolateHistory} from '@codemirror/commands';
import {markdown, markdownLanguage} from '@codemirror/lang-markdown';
import {languages} from '@codemirror/language-data';
import {HighlightStyle, syntaxHighlighting, bracketMatching, indentOnInput, codeFolding, foldGutter, foldKeymap} from '@codemirror/language';
import {search, searchKeymap, highlightSelectionMatches} from '@codemirror/search';
import {tags} from '@lezer/highlight';
import './markdown-editor.css';
import {mountToolbar} from './markdown-toolbar';
import {runCommand, pastedTable, insertBlock} from './markdown-commands';

const instances = new WeakMap();
const mounted = new Set();
const programmatic = Annotation.define();
const silent = Annotation.define();
const theme = EditorView.theme({
  '&': {height: '100%', color: 'var(--text)', backgroundColor: 'var(--bg)', fontSize: '14px'},
  '.cm-scroller': {fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, Menlo, monospace', lineHeight: '22px', overflow: 'auto'},
  '.cm-content': {padding: '14px 0', caretColor: 'var(--text)'},
  '.cm-line': {padding: '0 14px'},
  '.cm-cursor, .cm-dropCursor': {borderLeftColor: 'var(--accent)'},
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {backgroundColor: 'var(--accent-dim)'},
  '.cm-gutters': {backgroundColor: 'var(--panel)', color: 'var(--muted)', borderRight: '1px solid var(--line)'},
  '.cm-placeholder': {color: 'var(--muted)'},
  '.cm-activeLine': {backgroundColor: 'var(--panel-2)'},
  '.cm-activeLineGutter': {backgroundColor: 'var(--panel-2)', color: 'var(--accent)'},
  '.cm-panels, .cm-tooltip': {backgroundColor: 'var(--panel)', color: 'var(--text)', borderColor: 'var(--line)'},
  '.cm-searchMatch': {backgroundColor: 'var(--accent-dim)', outline: '1px solid var(--accent)'},
  '.cm-searchMatch-selected': {backgroundColor: 'var(--accent)', color: 'var(--bg)'},
}, {dark: true});
const highlighting = HighlightStyle.define([
  {tag: [tags.heading, tags.heading1, tags.heading2, tags.heading3, tags.heading4, tags.heading5, tags.heading6], color: 'var(--accent)'},
  {tag: tags.emphasis, color: 'var(--muted)', fontStyle: 'italic'},
  {tag: tags.strong, color: 'var(--accent)'},
  {tag: [tags.link, tags.url, tags.string], color: 'var(--ok)'},
  {tag: [tags.keyword, tags.atom, tags.bool, tags.number], color: 'var(--accent)'},
  {tag: [tags.comment, tags.meta, tags.processingInstruction], color: 'var(--muted)'},
  {tag: [tags.monospace, tags.function(tags.variableName), tags.typeName], color: 'var(--text)'},
]);

function imageFiles(transfer) {
  const items = [...(transfer?.items || [])];
  // Rich/text clipboard pastes retain text, even when they also contain an image.
  if ([...(transfer?.types || [])].some(type => /^text\//i.test(type) || type === 'application/rtf')) return [];
  return items.filter(item => item.kind === 'file' && item.type.startsWith('image/')).map(item => item.getAsFile()).filter(Boolean);
}

class MarkdownEditor {
  constructor(source) {
    this.source = source;
    this.form = source.form;
    this.wrap = new Compartment();
    this.access = new Compartment();
    this.numbers = new Compartment();
    this.active = new Compartment();
    this.folding = new Compartment();
    this.settings = {wrap: source.dataset.wordWrap !== 'false', numbers: true, active: true, folding: true};
    this.listeners = new Set();
    this.layoutSnapshot = null;
    this.createdContainer = !source.parentElement.classList.contains('markdown-editor');
    this.container = source.parentElement;
    if (this.createdContainer) {
      this.container = document.createElement('div');
      this.container.className = 'markdown-editor standalone-markdown-editor';
      source.before(this.container);
      this.container.append(source);
      this.workspace = document.createElement('div');
      this.workspace.className = 'mare-editor-workspace';
      this.container.before(this.workspace);
      this.workspace.append(this.container);
    }
    this.host = document.createElement('div');
    this.host.className = 'mare-editor-host';
    source.before(this.host);
    const wrapControl = source.closest('.manual-section')?.querySelector('.word-wrap');
    const wrapping = wrapControl ? wrapControl.checked : this.settings.wrap;
    this.settings.wrap = wrapping;
    this.readOnly = source.matches(':disabled') || source.readOnly;
    const maxLength = source.maxLength;
    const label = source.getAttribute('aria-label') || source.labels?.[0]?.textContent.trim() || source.id || source.name || 'Markdown';
    this.view = new EditorView({
      parent: this.host,
      state: EditorState.create({
        doc: source.value,
        extensions: [
          this.numbers.of(lineNumbers()), this.active.of([highlightActiveLineGutter(), highlightActiveLine()]),
          this.folding.of([codeFolding(), foldGutter(), keymap.of(foldKeymap)]),
          EditorState.allowMultipleSelections.of(true),
          history(), drawSelection(), rectangularSelection(), bracketMatching(), indentOnInput(),
          markdown({base: markdownLanguage, codeLanguages: languages}),
          syntaxHighlighting(highlighting), search(), highlightSelectionMatches(),
          keymap.of([...searchKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
          this.wrap.of(wrapping ? EditorView.lineWrapping : []),
          this.access.of([EditorState.readOnly.of(this.readOnly), EditorView.editable.of(!this.readOnly)]),
          theme, source.placeholder ? placeholder(source.placeholder) : [],
          EditorView.contentAttributes.of({'aria-label': label, 'aria-multiline': 'true', tabindex: '0', spellcheck: 'false'}),
          EditorState.transactionFilter.of(transaction => {
            if (transaction.docChanged && !transaction.annotation(programmatic) && maxLength >= 0 && transaction.newDoc.length > maxLength && transaction.newDoc.length > transaction.startState.doc.length) return [];
            return transaction;
          }),
          EditorView.updateListener.of(update => {
            if (!update.docChanged) return;
            if (this.layoutSnapshot) {
              for (const transaction of update.transactions) this.layoutSnapshot = this.layoutSnapshot?.map(transaction.changes);
            }
            source.value = update.state.doc.toString();
            this.view.contentDOM.removeAttribute('aria-invalid');
            if (update.transactions.every(transaction => transaction.annotation(silent))) return;
            source.dispatchEvent(new Event('input', {bubbles: true}));
            for (const listener of this.listeners) listener(this.getValue(), update);
          }),
          EditorView.domEventHandlers({
            dragover: event => {
              if (!this.readOnly && [...(event.dataTransfer?.types || [])].includes('Files') && source.closest('.manual-section')) { event.preventDefault(); return true; }
              return false;
            },
            drop: event => {
              if (!event.dataTransfer?.files.length || !source.closest('.manual-section')) return false;
              event.preventDefault();
              if (!this.readOnly) {
                const position = this.view.posAtCoords({x: event.clientX, y: event.clientY});
                if (position !== null) this.setSelection(position, position);
                this.upload([...event.dataTransfer.files]);
              }
              return true;
            },
            paste: event => {
              const files = imageFiles(event.clipboardData);
              if (!files.length || !source.closest('.manual-section')) return false;
              event.preventDefault();
              if (!this.readOnly) this.upload(files);
              return true;
            },
          }),
        ],
      }),
    });
    source.hidden = true;
    this.toolbar = mountToolbar(this);
    this.resize = new ResizeObserver(() => this.view.requestMeasure());
    this.resize.observe(this.container);
    this.invalid = event => { event.preventDefault(); this.view.contentDOM.setAttribute('aria-invalid', 'true'); this.focus(); };
    source.addEventListener('invalid', this.invalid);
    this.reset = () => queueMicrotask(() => {
      this.setValue(source.value, {notify: true, history: false});
      for (const [name, control] of this.toolbar.controls) this.setPreference(name, control.checked);
    });
    this.form?.addEventListener('reset', this.reset);
    this.wrapChange = () => this.setWordWrap(wrapControl.checked);
    wrapControl?.addEventListener('change', this.wrapChange);
    this.wrapControl = wrapControl;
    this.sync = event => {
      if (source.name && !source.matches(':disabled')) event.formData.set(source.name, this.getValue());
    };
    this.form?.addEventListener('formdata', this.sync);
    mounted.add(this);
  }
  getValue() { return this.view.state.doc.toString(); }
  setValue(value, {notify = false, history: addHistory = false} = {}) {
    value = String(value ?? '');
    const old = this.getValue();
    if (value === old) return;
    // A minimal change maps the existing selection rather than resetting the editor.
    let from = 0, oldEnd = old.length, newEnd = value.length;
    while (from < oldEnd && from < newEnd && old[from] === value[from]) from++;
    while (oldEnd > from && newEnd > from && old[oldEnd - 1] === value[newEnd - 1]) { oldEnd--; newEnd--; }
    const changes = this.view.state.changes({from, to: oldEnd, insert: value.slice(from, newEnd)});
    const snapshot = this.view.scrollSnapshot().map(changes);
    this.view.dispatch({changes, effects: snapshot ? [snapshot] : [], annotations: [programmatic.of(true), silent.of(!notify), Transaction.addToHistory.of(addHistory)]});
  }
  selection() { const {anchor, head, from, to} = this.view.state.selection.main; return {anchor, head, from, to}; }
  setSelection(anchor, head = anchor) {
    const max = this.view.state.doc.length;
    this.view.dispatch({selection: {anchor: Math.max(0, Math.min(anchor, max)), head: Math.max(0, Math.min(head, max))}});
  }
  insert(text, from = this.selection().from, to = this.selection().to) {
    if (this.readOnly) return;
    this.view.dispatch({changes: {from, to, insert: text}, selection: {anchor: from + text.length}, scrollIntoView: true, annotations: isolateHistory.of('full'), userEvent: 'input'});
    this.focus();
  }
  replaceMatches(pattern, replacement = '') {
    if (this.readOnly) return;
    const changes = [...this.getValue().matchAll(pattern)].map(match => ({from: match.index, to: match.index + match[0].length, insert: replacement}));
    if (changes.length) {
      const changeSet = this.view.state.changes(changes);
      const snapshot = this.view.scrollSnapshot().map(changeSet);
      this.view.dispatch({changes: changeSet, effects: snapshot ? [snapshot] : [], userEvent: 'input'});
    }
  }
  setWordWrap(enabled) { this.setPreference('wrap', enabled); }
  setPreference(name, enabled) {
    if (!['wrap','numbers','active','folding'].includes(name)) throw new Error('Unknown editor preference');
    enabled = Boolean(enabled); this.settings[name] = enabled;
    if (this.toolbar) this.toolbar.controls.get(name).checked = enabled;
    const extension = name === 'wrap' ? (enabled ? EditorView.lineWrapping : []) : name === 'numbers' ? (enabled ? lineNumbers() : []) : name === 'active' ? (enabled ? [highlightActiveLine(), highlightActiveLineGutter()] : []) : (enabled ? [codeFolding(), foldGutter(), keymap.of(foldKeymap)] : []);
    this.view.dispatch({effects: [this[name].reconfigure(extension), this.view.scrollSnapshot()]});
    this.view.requestMeasure();
  }
  command(name) { runCommand(this, name); }
  insertBlock(text, options) { insertBlock(this, text, options); }
  setReadOnly(enabled) { this.source.readOnly = Boolean(enabled); this.syncReadOnly(); }
  syncReadOnly() {
    const enabled = this.source.matches(':disabled') || this.source.readOnly;
    if (enabled === this.readOnly) return;
    this.readOnly = enabled;
    this.view.dispatch({effects: this.access.reconfigure([EditorState.readOnly.of(enabled), EditorView.editable.of(!enabled)])});
  }
  focus() { this.view.focus(); }
  measure() { this.view.requestMeasure(); }
  preserveLayout() { this.layoutSnapshot = this.view.scrollSnapshot(); }
  restoreLayout() { if (this.layoutSnapshot) this.view.dispatch({effects: this.layoutSnapshot}); this.layoutSnapshot = null; this.measure(); }
  onChange(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  upload(files) { this.source.dispatchEvent(new CustomEvent('markdown-images', {detail: {files}, bubbles: true})); }
  destroy() {
    this.resize.disconnect();
    this.source.removeEventListener('invalid', this.invalid);
    this.form?.removeEventListener('reset', this.reset);
    this.form?.removeEventListener('formdata', this.sync);
    this.wrapControl?.removeEventListener('change', this.wrapChange);
    this.toolbar.destroy();
    this.view.destroy();
    this.host.remove();
    this.source.hidden = false;
    if (this.createdContainer) { this.workspace.before(this.source); this.workspace.remove(); }
    mounted.delete(this);
    instances.delete(this.source);
    this.listeners.clear();
  }
}
function create(source) {
  if (instances.has(source)) return instances.get(source);
  const editor = new MarkdownEditor(source);
  instances.set(source, editor);
  return editor;
}
function get(source) { return instances.get(source) || create(source); }
window.MareEditors = {
  create, get, pastedTable,
  init: (root = document) => root.querySelectorAll('textarea[data-markdown-editor]').forEach(create),
  getValue: source => get(source).getValue(),
  setValue: (source, value, options) => get(source).setValue(value, options),
};
window.MareEditors.init();
if (document.fonts?.ready) document.fonts.ready.then(() => { for (const editor of mounted) editor.measure(); });
// Fieldset locking and dialog/tab visibility belong to the existing application.
new MutationObserver(records => {
  for (const editor of mounted) {
    if (!editor.source.isConnected) { editor.destroy(); continue; }
    if (records.some(record => record.attributeName === 'disabled' || record.attributeName === 'readonly')) editor.syncReadOnly();
    if (records.some(record => record.target.contains(editor.source) && ['hidden', 'open', 'class'].includes(record.attributeName))) editor.measure();
  }
}).observe(document.body, {attributes: true, subtree: true, childList: true, attributeFilter: ['disabled', 'readonly', 'hidden', 'open', 'class']});
