/* Read-only examples share the application's CodeMirror bundle and theme. */
import {EditorState} from '@codemirror/state';
import {EditorView, lineNumbers, drawSelection} from '@codemirror/view';
import {syntaxHighlighting} from '@codemirror/language';
import {python} from '@codemirror/lang-python';

const examples = new WeakMap();
export function mountPythonExamples({theme, highlighting}) {
  document.querySelectorAll('[data-python-example]').forEach(source => {
    if (examples.has(source)) return;
    const host = document.createElement('div');
    host.className = 'api-python-host';
    source.before(host);
    const view = new EditorView({parent: host, state: EditorState.create({doc: source.value, extensions: [
      theme, lineNumbers(), drawSelection(), python(), syntaxHighlighting(highlighting),
      EditorState.readOnly.of(true), EditorView.editable.of(false),
      EditorView.contentAttributes.of({'aria-label': source.getAttribute('aria-label'), tabindex: '0', 'aria-readonly': 'true'}),
    ]})});
    source.hidden = true;
    examples.set(source, view);
    const resize = new ResizeObserver(() => view.requestMeasure());
    resize.observe(host);
    const cleanup = new MutationObserver(() => {
      if (!source.isConnected) { resize.disconnect(); cleanup.disconnect(); view.destroy(); examples.delete(source); }
    });
    cleanup.observe(document.body, {childList: true, subtree: true});
    document.fonts?.ready.then(() => view.requestMeasure());
  });
}
