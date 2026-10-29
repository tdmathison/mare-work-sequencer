import { StateEffect, StateField, RangeSet } from "@codemirror/state";
import { gutter, GutterMarker, Decoration, EditorView, keymap } from "@codemirror/view";
import { DeveloperProtocol } from "./developer-protocol";
const setPoints = StateEffect.define(), setLine = StateEffect.define();
class Breakpoint extends GutterMarker {
  toDOM() {
    const span = document.createElement("span");
    span.textContent = "\u25CF";
    span.className = "ide-breakpoint";
    span.title = "Breakpoint";
    return span;
  }
}
const point = new Breakpoint();
function debugging({ base, csrf, plugin, current, view, log, inspect, open, context }) {
  const points = /* @__PURE__ */ new Map();
  let protocol, threadId, stopped;
  const markerField = StateField.define({ create: () => RangeSet.empty, update(markers, tr) {
    markers = markers.map(tr.changes);
    for (const e of tr.effects) if (e.is(setPoints)) markers = RangeSet.of(e.value.map((pos) => point.range(pos)));
    return markers;
  } });
  const lineField = StateField.define({ create: () => Decoration.none, update(value, tr) {
    value = value.map(tr.changes);
    for (const e of tr.effects) if (e.is(setLine)) value = e.value === null ? Decoration.none : Decoration.set([Decoration.line({ class: "ide-debug-line" }).range(e.value)]);
    return value;
  }, provide: (field) => EditorView.decorations.from(field) });
  function refresh() {
    const v = view();
    if (!v) return;
    const selected = [...points.get(current()) || []].filter((line) => line <= v.state.doc.lines).sort((a, b) => a - b).map((line) => v.state.doc.line(line).from);
    v.dispatch({ effects: setPoints.of(selected) });
  }
  async function sendPoints() {
    if (!protocol) return;
    for (const [path, lines] of points) await protocol.request("setBreakpoints", { source: { path: "/work/" + path }, breakpoints: [...lines].map((line) => ({ line })) });
  }
  function toggle() {
    const v = view();
    if (!v || !current()?.endsWith(".py")) return;
    const number = v.state.doc.lineAt(v.state.selection.main.head).number, set = points.get(current()) || /* @__PURE__ */ new Set();
    if (set.has(number)) set.delete(number);
    else set.add(number);
    points.set(current(), set);
    refresh();
    sendPoints().catch((e) => log(e.message));
  }
  const extension = [keymap.of([{ key: "F9", run: () => {
    toggle();
    return true;
  } }]), markerField, lineField, gutter({ class: "ide-breakpoint-gutter", markers: (v) => v.state.field(markerField), initialSpacer: () => point, domEventHandlers: { mousedown(v, line, event2) {
    if (!current()?.endsWith(".py")) return false;
    const number = v.state.doc.lineAt(line.from).number;
    const set = points.get(current()) || /* @__PURE__ */ new Set();
    if (set.has(number)) set.delete(number);
    else set.add(number);
    points.set(current(), set);
    refresh();
    sendPoints().catch((e) => log(e.message));
    event2.preventDefault();
    return true;
  } } })];
  async function scopes(frameId) {
    const result = await protocol.request("scopes", { frameId });
    const values = [];
    for (const scope of result.scopes || []) {
      const vars = await protocol.request("variables", { variablesReference: scope.variablesReference, start: 0, count: 100 });
      values.push({ scope: scope.name, variables: vars.variables });
    }
    inspect(values);
  }
  async function event(message) {
    if (message.event === "initialized") {
      await sendPoints();
      await protocol.request("configurationDone", {});
    } else if (message.event === "stopped") {
      threadId = message.body.threadId;
      const result = await protocol.request("stackTrace", { threadId, levels: 30 });
      inspect(result.stackFrames);
      const frame = result.stackFrames?.find((f) => f.source?.path?.startsWith("/work/"));
      if (frame) {
        stopped = { path: frame.source.path.slice(6), line: frame.line };
        await open(stopped.path, frame.line - 1);
        refreshLine();
        await scopes(frame.id);
      }
    } else if (message.event === "output") log(message.body.output);
    else if (message.event === "terminated") await stop();
  }
  function refreshLine() {
    const v = view();
    if (!v) return;
    const line = stopped?.path === current() && stopped.line <= v.state.doc.lines ? v.state.doc.line(stopped.line).from : null;
    v.dispatch({ effects: setLine.of(line) });
  }
  async function start() {
    if (protocol) await stop();
    protocol = new DeveloperProtocol({ base, csrf, id: plugin(), mode: "debug", onOutput: log, onEvent: (message) => event(message).catch((e) => log(e.message)) });
    await protocol.start(context());
    await protocol.request("initialize", {});
    protocol.request("launch", {}).catch((e) => log(e.message));
  }
  async function action(command) {
    if (command === "breakpoint") return toggle();
    if (command === "start") return start();
    if (command === "stop") return stop();
    if (!protocol) throw Error("Start a debug session first.");
    if (!threadId) {
      const result = await protocol.request("threads");
      threadId = result.threads?.[0]?.id;
    }
    await protocol.request(command, { threadId });
    if (command !== "pause") {
      stopped = null;
      refreshLine();
    }
  }
  async function stop() {
    await protocol?.close();
    protocol = null;
    stopped = null;
    refreshLine();
  }
  return { extension, action, refresh() {
    refresh();
    refreshLine();
  }, stop };
}
export {
  debugging
};
