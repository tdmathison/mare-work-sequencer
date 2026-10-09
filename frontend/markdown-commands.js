import {EditorSelection} from '@codemirror/state';
import {indentMore, indentLess, isolateHistory} from '@codemirror/commands';

// A selection ending at the start of a line excludes that final line.
function selectedLines(state) {
  const lines = new Map();
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from), last = state.doc.lineAt(range.to > range.from ? range.to - 1 : range.to);
    for (let n = first.number; n <= last.number; n++) lines.set(n, state.doc.line(n));
  }
  return [...lines.values()].sort((a, b) => a.from - b.from);
}
function dispatch(view, changes, selection) {
  view.dispatch({changes, ...(selection ? {selection} : {}), annotations: isolateHistory.of('full'), userEvent: 'input', scrollIntoView: true});
  view.focus();
}
function lines(view, transform) {
  const changes = selectedLines(view.state).map((line, index) => {
    const next = transform(line.text, index); let from = 0, oldEnd = line.text.length, newEnd = next.length;
    while (from < oldEnd && from < newEnd && line.text[from] === next[from]) from++;
    while (oldEnd > from && newEnd > from && line.text[oldEnd - 1] === next[newEnd - 1]) { oldEnd--; newEnd--; }
    return {from: line.from + from, to: line.from + oldEnd, insert: next.slice(from,newEnd)};
  });
  // CodeMirror maps all existing ranges through the transaction.
  dispatch(view, changes);
}
function inline(view, marker) {
  const {state} = view;
  const changes = state.changeByRange(range => {
    const text = state.sliceDoc(range.from, range.to), size = marker.length;
    if (text.length >= size * 2 && text.startsWith(marker) && text.endsWith(marker)) {
      const insert = text.slice(size, -size);
      return {changes: {from: range.from, to: range.to, insert}, range: EditorSelection.range(range.from, range.from + insert.length)};
    }
    if (range.from >= size && state.sliceDoc(range.from - size, range.from) === marker && state.sliceDoc(range.to, range.to + size) === marker) {
      return {changes: [{from: range.from - size, to: range.from, insert: ''}, {from: range.to, to: range.to + size, insert: ''}], range: EditorSelection.range(range.from - size, range.to - size)};
    }
    return {changes: {from: range.from, to: range.to, insert: marker + text + marker}, range: EditorSelection.range(range.from + size, range.to + size)};
  });
  dispatch(view, changes.changes, changes.selection);
}
export function insertBlock(editor, text, {header = false} = {}) {
  if (editor.readOnly) return;
  const view = editor.view, range = view.state.selection.main;
  const before = view.state.sliceDoc(0, range.from), after = view.state.sliceDoc(range.to);
  const prefix = before && !before.endsWith('\n\n') ? (before.endsWith('\n') ? '\n' : '\n\n') : '';
  const suffix = after && !after.startsWith('\n\n') ? (after.startsWith('\n') ? '\n' : '\n\n') : '\n\n';
  const insert = prefix + text + suffix;
  const position = range.from + prefix.length + (header ? 2 : text.length);
  dispatch(view, {from: range.from, to: range.to, insert}, EditorSelection.cursor(position));
}
export function runCommand(editor, command) {
  if (editor.readOnly) return;
  const view = editor.view;
  if (/^h[1-6]$/.test(command) || command === 'paragraph') {
    const prefix = command === 'paragraph' ? '' : '#'.repeat(Number(command[1])) + ' ';
    lines(view, text => prefix + text.replace(/^ {0,3}#{1,6}(?:[ \t]+|$)/, ''));
  } else if (['bold', 'italic', 'strike', 'inline-code'].includes(command)) {
    let marker = {bold: '**', italic: '*', strike: '~~', 'inline-code': '`'}[command];
    // Code spans containing backticks need a longer delimiter.
    if (command === 'inline-code') {
      const selected = view.state.sliceDoc(view.state.selection.main.from, view.state.selection.main.to);
      if (!/^`+[\s\S]*`+$/.test(selected)) {
        const runs = selected.match(/`+/g) || [];
        marker = '`'.repeat(Math.max(0, ...runs.map(run => run.length)) + 1);
      } else marker = selected.match(/^`+/)[0];
    }
    inline(view, marker);
  } else if (command === 'bullet' || command === 'numbered' || command === 'quote') {
    const selected = selectedLines(view.state);
    const active = command === 'quote' ? /^[ \t]*> / : command === 'bullet' ? /^[ \t]*- / : /^[ \t]*\d+\. /;
    const remove = selected.every(line => active.test(line.text));
    const pattern = command === 'quote' ? /^([ \t]*)> ?/ : /^([ \t]*)(?:[-+*]|\d+[.)])[ \t]+/;
    lines(view, (text, i) => {
      const plain = text.replace(pattern, '$1');
      if (remove) return plain;
      const indent = plain.match(/^[ \t]*/)[0];
      const marker = command === 'quote' ? '> ' : command === 'bullet' ? '- ' : `${i + 1}. `;
      return indent + marker + plain.slice(indent.length);
    });
  } else if (command === 'indent' || command === 'outdent') {
    (command === 'indent' ? indentMore : indentLess)(view); view.focus();
  } else if (command === 'url') {
    const range = view.state.selection.main, text = view.state.sliceDoc(range.from, range.to) || 'link text';
    dispatch(view, {from: range.from, to: range.to, insert: `[${text}](https://example.com)`}, EditorSelection.range(range.from + text.length + 3, range.from + text.length + 22));
  } else if (command === 'code') {
    const range = view.state.selection.main, first = view.state.doc.lineAt(range.from), last = view.state.doc.lineAt(range.to > range.from ? range.to - 1 : range.to);
    const text = view.state.sliceDoc(first.from, last.to);
    const fence = '`'.repeat(Math.max(3, ...((text.match(/`+/g) || []).map(run => run.length + 1))));
    const insert = `${fence}\n${text}\n${fence}`;
    dispatch(view, {from: first.from, to: last.to, insert}, EditorSelection.range(first.from + fence.length + 1, first.from + fence.length + 1 + text.length));
  } else if (command === 'rule') insertBlock(editor, '---');
  else if (command.startsWith('align-')) {
    const selected = selectedLines(view.state), first = selected[0], last = selected.at(-1);
    const text = view.state.sliceDoc(first.from, last.to);
    dispatch(view, {from: first.from, to: last.to, insert: `::: ${command}\n${text}\n:::`});
  }
}
export function escapeCell(value) {
  return String(value).replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim().replace(/\\/g, '\\\\').replace(/\|/g, '\\|');
}
export function tableMarkdown(values) {
  const columns = Math.max(0, ...values.map(row => row.length));
  if (!columns || !values.length) return '';
  const rows = values.map(row => Array.from({length: columns}, (_, i) => escapeCell(row[i] ?? '')));
  return [rows[0], Array(columns).fill('---'), ...rows.slice(1)].map(row => '| ' + row.join(' | ') + ' |').join('\n');
}
export function pastedTable(html, plain = html) {
  const parsed = new DOMParser().parseFromString(html || '', 'text/html');
  const tables = [...parsed.querySelectorAll('table')].filter(table => !table.parentElement.closest('table'));
  const converted = tables.map(table => {
    const rows = [...table.rows].filter(row => row.closest('table') === table), values = [];
    rows.forEach((row, r) => {
      values[r] ||= []; let column = 0;
      for (const cell of row.cells) {
        while (values[r][column] !== undefined) column++;
        const content = cell.cloneNode(true);
        content.querySelectorAll('script,style,template').forEach(node => node.remove());
        content.querySelectorAll('br').forEach(node => node.replaceWith(parsed.createTextNode(' ')));
        content.querySelectorAll('p,div,li').forEach(node => { node.before(' '); node.after(' '); });
        const width = Math.min(1000, Math.max(1, cell.colSpan));
        const height = cell.getAttribute('rowspan') === '0' ? rows.length - r : Math.min(rows.length - r, Math.max(1, cell.rowSpan));
        for (let dr = 0; dr < height; dr++) {
          values[r + dr] ||= [];
          for (let dc = 0; dc < width; dc++) values[r + dr][column + dc] = dr === 0 && dc === 0 ? content.textContent || '' : '';
        }
        column += width;
      }
    });
    return tableMarkdown(values);
  }).filter(Boolean);
  if (converted.length) return converted.join('\n\n');
  if (!plain?.includes('\t')) return '';
  const rows = plain.replace(/\r\n?/g, '\n').split('\n');
  // Remove only the clipboard's terminal newline; keep empty cells and rows.
  if (rows.at(-1) === '') rows.pop();
  return tableMarkdown(rows.map(row => row.split('\t')));
}
