import { autocompletion } from "@codemirror/autocomplete";
import { hoverTooltip, keymap } from "@codemirror/view";
import { setDiagnostics } from "@codemirror/lint";
import { DeveloperProtocol } from "./developer-protocol";
function languageService({ root, base, csrf, plugin, view, current, contents, log, symbol, open }) {
  let protocol, version = 0, timer;
  const opened = /* @__PURE__ */ new Map();
  const uri = (path) => "file:///work/" + path.split("/").map(encodeURIComponent).join("/");
  const position = (v, offset) => {
    const line = v.state.doc.lineAt(offset);
    return { line: line.number - 1, character: offset - line.from };
  };
  async function sync() {
    if (!protocol || !current()) return;
    const path = current();
    if (!path.endsWith(".py")) return;
    const text = contents();
    if (opened.get(path) === text) return;
    if (!opened.has(path)) await protocol.notify("textDocument/didOpen", { textDocument: { uri: uri(path), languageId: "python", version: ++version, text } });
    else await protocol.notify("textDocument/didChange", { textDocument: { uri: uri(path), version: ++version }, contentChanges: [{ text }] });
    opened.set(path, text);
  }
  async function request(method, offset) {
    if (!protocol) return null;
    await sync();
    return protocol.request(method, { textDocument: { uri: uri(current()) }, position: position(view(), offset), context: { includeDeclaration: true } });
  }
  function plain(value) {
    if (!value) return "";
    if (Array.isArray(value)) return value.map(plain).join("\n");
    return typeof value === "string" ? value : value.value || value.label || JSON.stringify(value);
  }
  async function navigate(method) {
    const v = view();
    if (!v) return;
    const result = await request(method, v.state.selection.main.head);
    const list = Array.isArray(result) ? result : result ? [result] : [];
    if (method === "textDocument/references") {
      symbol(list.map((item) => ({ file: item.uri, line: item.range?.start?.line + 1 })));
      return;
    }
    const target = list[0], path = target?.uri || target?.targetUri;
    if (path?.startsWith("file:///work/")) await open(decodeURIComponent(path.slice(13)), target.range?.start?.line || target.targetRange?.start?.line || 0);
    else symbol("Definition is in an installed dependency; see SDK documentation.");
  }
  const extension = [autocompletion({ override: [async (context) => {
    if (!protocol) return null;
    const result = await request("textDocument/completion", context.pos);
    const items = Array.isArray(result) ? result : result?.items || [];
    const word = context.matchBefore(/[\w]*/);
    return { from: word?.from ?? context.pos, options: items.map((item) => ({ label: item.label, type: item.kind === 3 ? "function" : item.kind === 2 ? "method" : item.kind === 7 ? "class" : "variable", detail: item.detail, info: async () => {
      const resolved = await protocol.request("completionItem/resolve", item);
      const dom = document.createElement("div");
      dom.className = "ide-hover";
      dom.textContent = [resolved.detail, plain(resolved.documentation)].filter(Boolean).join("\n");
      return dom;
    }, apply: item.insertTextFormat === 2 ? item.label : item.insertText || item.label })) };
  }] }), hoverTooltip(async (v, offset) => {
    if (!protocol) return null;
    const result = await request("textDocument/hover", offset);
    if (!result) return null;
    return { pos: offset, create: () => {
      const dom = document.createElement("div");
      dom.className = "ide-hover";
      dom.textContent = plain(result.contents);
      return { dom };
    } };
  }), keymap.of([{ key: "F12", run: () => {
    navigate("textDocument/definition").catch((e) => log(e.message));
    return true;
  } }, { key: "Shift-F12", run: () => {
    navigate("textDocument/references").catch((e) => log(e.message));
    return true;
  } }, { key: "Mod-Shift-Space", run: () => {
    request("textDocument/signatureHelp", view().state.selection.main.head).then((result) => symbol(result?.signatures?.map((s) => s.label + "\n" + plain(s.documentation)).join("\n") || "No signature available.")).catch((e) => log(e.message));
    return true;
  } }])];
  async function start() {
    protocol = new DeveloperProtocol({ base, csrf, id: plugin(), mode: "language", onOutput: log, onEvent: (message) => {
      if (message.method === "textDocument/publishDiagnostics" && message.params.uri === uri(current())) {
        const v = view();
        if (!v) return;
        const diagnostics = (message.params.diagnostics || []).map((d) => {
          const line = v.state.doc.line(Math.min(v.state.doc.lines, d.range.start.line + 1));
          const end = v.state.doc.line(Math.min(v.state.doc.lines, d.range.end.line + 1));
          return { from: Math.min(line.to, line.from + d.range.start.character), to: Math.min(end.to, end.from + d.range.end.character), severity: d.severity === 1 ? "error" : d.severity === 2 ? "warning" : "info", message: d.message };
        });
        v.dispatch(setDiagnostics(v.state, diagnostics));
      }
    } });
    await protocol.start();
    await protocol.request("initialize", { capabilities: { textDocument: { completion: { completionItem: { snippetSupport: false } }, hover: { contentFormat: ["plaintext"] } } } });
    await protocol.notify("initialized", {});
    await sync();
  }
  return { extension, start, changed() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        await sync();
        const v = view();
        if (protocol && v && /[,(]/.test(v.state.doc.sliceString(Math.max(0, v.state.selection.main.head - 1), v.state.selection.main.head))) {
          const result = await request("textDocument/signatureHelp", v.state.selection.main.head);
          if (result?.signatures?.length) symbol(result.signatures.map((s) => s.label).join("\n"));
        }
      } catch (e) {
        log(e.message);
      }
    }, 350);
  }, sync, async symbols() {
    await sync();
    symbol(await protocol.request("textDocument/documentSymbol", { textDocument: { uri: uri(current()) } }));
  }, async close() {
    clearTimeout(timer);
    await protocol?.close();
    protocol = null;
    opened.clear();
  } };
}
export {
  languageService
};
