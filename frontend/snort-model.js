const EXAMPLE = `alert http $HOME_NET any -> $EXTERNAL_NET any (msg:"ET TROJAN W32/ProxyBack CnC Beacon"; flow:established,to_server; content:"GET";
http_method; content:"/ne.php"; http_uri; depth:7; content:"User-Agent|3A 20|pb|0d 0a|"; http_header; classtype:trojan-activity;
reference:url,http://researchcenter.paloaltonetworks.com/2015/12/proxyback-malware-turns-user-systems-into-proxies-without-consent/;
sid:100000; rev:1;)`;
const EMPTY = 'alert tcp any any -> any 80 (msg:"Analyst rule"; sid:1000001; rev:1;)';
const BUFFERS = ["pkt_data", "raw_data", "file_data", "http_method", "http_uri", "http_raw_uri", "http_header", "http_raw_header", "http_client_body", "http_cookie", "http_raw_body"];
const MODIFIERS = ["nocase", "fast_pattern", "offset", "depth", "distance", "within", "rawbytes", "startswith", "endswith", "width", "endian"];
const identities = ["msg", "classtype", "sid", "gid", "rev", "priority", "metadata"];
function segments(source, from, to, delimiter) {
  const out = [];
  let start = from, quote = false, escape = false, comment = false;
  for (let i = from; i < to; i++) {
    const c = source[i];
    if (comment) {
      if (c === "\n") comment = false;
      continue;
    }
    if (escape) {
      escape = false;
      continue;
    }
    if (quote && c === "\\") {
      escape = true;
      continue;
    }
    if (c === '"') {
      quote = !quote;
      continue;
    }
    if (quote) continue;
    if (c === "#") {
      comment = true;
      continue;
    }
    if (c === delimiter) {
      out.push({ from: start, to: i });
      start = i + 1;
    }
  }
  out.push({ from: start, to });
  return out;
}
function trimRange(s, r) {
  let { from, to } = r;
  while (from < to && /\s/.test(s[from])) from++;
  while (to > from && /\s/.test(s[to - 1])) to--;
  return { from, to };
}
function maskComments(source) {
  const chars = source.split(''); // UTF-16 positions must match CodeMirror ranges.
  let quote = false, escape = false, unclosed = false;
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (escape) { escape = false; continue; }
    if (quote && c === "\\") { escape = true; continue; }
    if (c === '"') { quote = !quote; continue; }
    if (quote) continue;
    if (c === '#' || source.startsWith('/*', i)) {
      let end = c === '#' ? source.indexOf('\n', i) : source.indexOf('*/', i + 2);
      if (end < 0) { if (c !== '#') unclosed = true; end = source.length; }
      else if (c !== '#') end += 2;
      for (let j = i; j < end; j++) if (!/[\r\n]/.test(source[j])) chars[j] = ' ';
      i = end - 1;
    }
  }
  return {text:chars.join(''), unclosed};
}
function parse(source, requested = "auto") {
  const result = { source, rules: [], components: [], diagnostics: [], compatibility: [], warnings: [] };
  if (new TextEncoder().encode(source).length > 1e5) {
    result.diagnostics.push("Source exceeds 100,000 UTF-8 bytes.");
    return result;
  }
  const masked = maskComments(source), lexical = masked.text;
  if (masked.unclosed) result.diagnostics.push("Unterminated block comment. Source retained.");
  let start = null, open = null, quote = false, escape = false, comment = false;
  for (let i = 0; i <= source.length; i++) {
    const c = lexical[i];
    if (comment) {
      if (c === "\n") comment = false;
      else continue;
    }
    if (escape) {
      escape = false;
      continue;
    }
    if (quote && c === "\\") {
      escape = true;
      continue;
    }
    if (c === '"') {
      if (!quote && open === null && start === null) start = i;
      quote = !quote;
      continue;
    }
    if (quote) continue;
    if (c === "#") {
      comment = true;
      continue;
    }
    if (i === source.length) {
      if (start !== null) {
        result.diagnostics.push("Incomplete rule or non-rule directive. Source retained.");
        if (open !== null) addRule(start, open, i, false);
      }
      break;
    }
    if (start === null && !/\s/.test(c)) start = i;
    if (c === "(") {
      if (open !== null) {
        result.diagnostics.push("Nested unquoted parentheses: inspector operations disabled.");
        return result;
      }
      open = i;
    } else if (c === ")") {
      if (open === null) {
        result.diagnostics.push("Unmatched closing parenthesis.");
        return result;
      }
      addRule(start, open, i, true);
      start = open = null;
    }
  }
  if (quote) result.diagnostics.push("Unclosed quoted string. Source retained.");
  if (quote && open !== null) addRule(start, open, source.length, false);
  if (/^\s*#\s*(begin|end)\b/im.test(source)) result.diagnostics.push("Block-comment syntax is source-only; associations cannot be established safely.");
  if (!result.rules.length && !result.diagnostics.length) result.diagnostics.push("No active rule. Comments and disabled rules are retained.");
  if (result.diagnostics.length) for (const c of result.components) c.safe = false;
  return result;
  function addRule(from, opening, close, complete) {
    const n = result.rules.length, header = trimRange(lexical, { from, to: opening }), tokens = [];
    const re = /!?\[[^\[\]]*\]|\S+/g;
    let m;
    while (m = re.exec(lexical.slice(header.from, header.to))) tokens.push({ text: m[0], from: header.from + m.index, to: header.from + m.index + m[0].length });
    const rule = { n, from, open: opening, close, complete, tokens, options: [], components: [] };
    result.rules.push(rule);
    if (![2, 7].includes(tokens.length) || tokens.length === 7 && !["->", "<>"].includes(tokens[4].text)) {
      result.diagnostics.push(`Rule ${n + 1}: unsupported header; use source editing.`);
      complete = false;
    }
    const add = (kind, label, options, extra = {}) => {
      const c = { id: `${n}:${kind}:${rule.components.filter((x) => x.kind === kind).length}`, kind, label, rule: n, options, spans: options.map((o) => ({ from: o.from, to: o.to })), related: [], safe: complete, ...extra };
      rule.components.push(c);
      result.components.push(c);
      return c;
    };
    add("header", "Header", [], { spans: [header], tokens, summary: tokens.map((t) => t.text).join(" ") });
    const chunks = segments(lexical, opening + 1, close, ";");
    for (let i = 0; i < chunks.length; i++) {
      let r = chunks[i];
      let leading = lexical.slice(r.from, r.to).match(/^(?:\s|#[^\n]*(?:\n|$))*/)[0];
      r = { from: r.from + leading.length, to: r.to };
      r = trimRange(lexical, r);
      if (r.from === r.to) continue;
      if (i === chunks.length - 1) {
        result.diagnostics.push(`Rule ${n + 1}: missing option semicolon.`);
        continue;
      }
      const raw = source.slice(r.from, r.to), key = raw.match(/^([\w]+)/)?.[1] || "?", colon = raw.indexOf(":");
      const o = { ...r, to: chunks[i].to + 1, bodyTo: r.to, key, colon: colon < 0 ? null : r.from + colon, value: colon < 0 ? "" : raw.slice(colon + 1).trim(), raw, safe: raw === lexical.slice(r.from,r.to) && !/#/.test(raw.replace(/"(?:\\.|[^"\\])*"/g, "")) };
      rule.options.push(o);
    }
    const legacyEvidence = rule.options.some((o) => MODIFIERS.includes(o.key));
    const ambiguous = !legacyEvidence && rule.options.some((o, i) => o.key === "content" && BUFFERS.includes(rule.options[i + 1]?.key));
    rule.dialect = requested !== "auto" ? requested : legacyEvidence ? "legacy" : ambiguous ? "ambiguous" : "snort3";
    if (rule.dialect === "snort3" && legacyEvidence) result.compatibility.push(`Rule ${n + 1}: standalone legacy content modifiers require explicit conversion or source correction.`);
    if (rule.dialect === "legacy") result.compatibility.push(`Rule ${n + 1}: legacy content modifiers; not established as Snort 3 compatible.`);
    if (rule.dialect === "ambiguous") result.compatibility.push(`Rule ${n + 1}: buffer-after-content is ambiguous. Choose Legacy or Snort 3 interpretation before using content inspectors.`);
    if (tokens.length === 7 && !["tcp", "udp", "icmp", "ip"].includes(tokens[1]?.text)) result.compatibility.push(`Rule ${n + 1}: full header protocol \u201C${tokens[1]?.text}\u201D is a service-based header. Matching requires the detected service and configured inspection; validate with the engine.`);
    let active = null, last = null, identity = [];
    for (const o of rule.options) {
      if (o.key === "content") {
        const decoded = readContent(source, o);
        const c = add("content", "Content match", [o], { content: o, buffer: rule.dialect === "legacy" ? null : active, modifiers: [], decoded, summary: decoded.error || decoded.display });
        if (c.buffer) c.related.push(c.buffer);
        if (rule.dialect === "ambiguous" || decoded.error) c.safe = false;
        last = c;
      } else if (BUFFERS.includes(o.key)) {
        if (rule.dialect === "legacy" && o.key.startsWith("http_") && last) {
          last.options.push(o);
          last.spans.push({ from: o.from, to: o.to });
          last.buffer = o;
        } else {
          const c = add("buffer", o.key, [o], { summary: o.value || "Sticky inspection buffer" });
          if (rule.dialect === "ambiguous") c.safe = false;
          active = o;
          c.selector = o;
          last = null;
        }
      } else if (MODIFIERS.includes(o.key) && rule.dialect === "legacy" && last) {
        last.modifiers.push(o);
        last.options.push(o);
        last.spans.push({ from: o.from, to: o.to });
      } else if (identities.includes(o.key)) identity.push(o);
      else if (o.key === "reference") add("reference", "Reference", [o], { summary: o.value });
      else if (o.key === "flow") add("flow", "Flow", [o], { summary: o.value });
      else add("option", o.key, [o], { summary: o.value || "Source option", buffer: active, related: active ? [active] : [] });
    }
    if (identity.length) add("identity", "Rule identity / classification", identity, { summary: identity.map((o) => `${o.key}: ${o.value}`).join(" \xB7 ") });
    for (const c of rule.components) {
      if (c.options.some((o) => !o.safe)) c.safe = false;
      if (c.kind !== "content") continue;
      c.inline = segments(source, c.content.colon + 1, c.content.bodyTo, ",").slice(1).map((r) => ({ ...trimRange(source, r), raw: source.slice(r.from, r.to).trim() }));
      c.bufferName = c.buffer?.key || "payload";
      c.label = { "http_method": "HTTP method", "http_uri": "URI match", "http_raw_uri": "Raw URI match", "http_header": "Header match", "http_raw_header": "Raw header match" }[c.bufferName] || `${c.bufferName} match`;
      c.summary = c.decoded.display + (c.modifiers.length ? " \xB7 " + c.modifiers.map((o) => o.raw).join(" ") : "") + (c.inline.length ? " \xB7 " + c.inline.map((o) => o.raw).join(", ") : "");
      if (rule.dialect === "legacy" && (c.inline.length || c.buffer?.value)) {
        c.safe = false;
        result.compatibility.push("Mixed legacy/sticky content syntax or buffer parameters require source review.");
      }
      const mods = modifierValues(c);
      c.warnings = [];
      if (c.modifiers.some((o) => ["nocase", "fast_pattern"].includes(o.key) && o.value)) c.safe = false;
      const names = [...c.modifiers.map((o) => o.key), ...c.inline.map((o) => o.raw.split(/\s+/)[0])];
      if (new Set(names).size !== names.length) {
        c.safe = false;
        c.warnings.push("Repeated modifiers are source-only; resolve duplicates explicitly.");
      }
      if (c.decoded.bytes?.length < 4 || ["GET", "POST", "HTTP/1.1"].includes(c.decoded.display)) c.warnings.push("Weak/common content: add a distinctive path, marker or independent match.");
      for (const key of ["depth", "within"]) if (/^\d+$/.test(mods[key] || "") && Number(mods[key]) < c.decoded.bytes?.length) c.warnings.push(`${key} cannot contain this match.`);
      if ((mods.offset !== void 0 || mods.depth !== void 0) && (mods.distance !== void 0 || mods.within !== void 0)) c.warnings.push("Absolute and relative positioning conflict.");
      const preceding = rule.components.filter((x) => x.kind === "content" && x.content.from < c.content.from).at(-1);
      if ((mods.distance !== void 0 || mods.within !== void 0) && (!preceding || preceding.bufferName !== c.bufferName || preceding.decoded.negated)) c.warnings.push("Relative positioning has no suitable preceding positive match in this buffer.");
      if (c.related.length && rule.components.filter((x) => x.kind === "content" && x.buffer === c.buffer).length > 1) c.warnings.push("Shared sticky buffer: changing its selector affects multiple matches.");
      result.warnings.push(...c.warnings.map((w) => `${c.label}: ${w}`));
    }
  }
}
function readContent(source, o) {
  const r = segments(source, o.colon + 1, o.bodyTo, ",")[0], raw = source.slice(r.from, r.to), match = raw.match(/^(\s*)(!?)(\s*)"((?:\\.|[^"\\])*)"\s*$/s);
  if (!match) return { error: "Incomplete or unsupported content string. Edit source to complete it.", display: raw };
  const from = r.from + match[1].length, to = r.to - raw.match(/\s*$/)[0].length;
  try {
    const bytes = decodeMixed(match[4]);
    return { from, to, negated: !!match[2], mixed: match[4], bytes, display: new TextDecoder().decode(new Uint8Array(bytes)).replace(/[\x00-\x1f]/g, "\xB7") };
  } catch (error) {
    return { error: error.message, display: match[4] };
  }
}
function decodeMixed(value) {
  let bytes = [], text = "";
  const flush = () => {
    bytes.push(...new TextEncoder().encode(text));
    text = "";
  };
  for (let i = 0; i < value.length; i++) {
    const c = value[i];
    if (c === "|") {
      flush();
      const end = value.indexOf("|", i + 1);
      if (end < 0) throw Error("Unclosed hex block.");
      const hex = value.slice(i + 1, end).replace(/\s/g, "");
      if (!hex || !/^(?:[a-f\d]{2})+$/i.test(hex)) throw Error("Hex blocks require complete byte pairs.");
      bytes.push(...hex.match(/../g).map((v) => parseInt(v, 16)));
      i = end;
    } else if (c === "\\") {
      const next = value[++i];
      if (!["\\", '"', ";", ":"].includes(next)) throw Error("Unsupported escape retained in source.");
      text += next;
    } else text += c;
  }
  flush();
  return bytes;
}
function hexBytes(input) {
  if (!input.trim()) throw Error("Paste whitespace-separated hex byte pairs.");
  const a = input.trim().split(/\s+/);
  if (a.length > 4096 || a.some((x) => !/^[a-f\d]{2}$/i.test(x))) throw Error("Use at most 4,096 whitespace-separated hex byte pairs; no offsets, ASCII columns or 0x prefixes.");
  return a.map((x) => parseInt(x, 16));
}
function encodeContent(value, mode = "mixed") {
  if (mode === "hex") return "|" + hexBytes(value).map((v) => v.toString(16).padStart(2, "0")).join(" ") + "|";
  if (mode === "mixed") {
    decodeMixed(value);
    return value;
  }
  return [...new TextEncoder().encode(value)].map((b) => b >= 32 && b <= 126 && !["|", '"', "\\"].includes(String.fromCharCode(b)) ? String.fromCharCode(b) : "|" + b.toString(16).padStart(2, "0") + "|").join("");
}
function modifierValues(c) {
  const values = {};
  for (const o of c.modifiers) values[o.key] = o.value || "true";
  for (const m of c.inline || []) {
    const [key, ...rest] = m.raw.split(/\s+/);
    values[key] = rest.join(" ") || "true";
  }
  return values;
}
function applyPatches(source, patches) {
  let last = source.length + 1;
  for (const p of [...patches].sort((a, b) => b.from - a.from)) {
    if (p.to > last || p.from < 0 || p.to < p.from || p.to > source.length) throw Error("Overlapping or stale source patches.");
    source = source.slice(0, p.from) + p.insert + source.slice(p.to);
    last = p.from;
  }
  return source;
}
function contentPatch(c, value, mode, negative) {
  if (!c.safe || c.decoded.error) throw Error("Complete syntax and resolve dialect before using this inspector.");
  return { from: c.decoded.from, to: c.decoded.to, insert: (negative ? "!" : "") + '"' + encodeContent(value, mode) + '"' };
}
function modifierPatch(model, c, key, value) {
  if (!c.safe) throw Error("Inspector unavailable for incomplete or ambiguous source.");
  if (!MODIFIERS.includes(key)) throw Error("Unknown modifier.");
  const o = c.modifiers.find((x) => x.key === key), inline = c.inline.find((x) => x.raw.split(/\s+/)[0] === key), flag = ["nocase", "fast_pattern", "rawbytes", "startswith", "endswith"].includes(key);
  if (value && !flag && !/^-?\d+$/.test(value)) throw Error("This inspector accepts integer positioning; variables remain editable in source.");
  if (o) return { from: o.from, to: o.to, insert: value ? key + (flag ? "" : ":" + value) + ";" : "" };
  if (inline) {
    const before = model.source.lastIndexOf(",", inline.from);
    return { from: before, to: inline.to, insert: value ? "," + key + (flag ? "" : " " + value) : "" };
  }
  if (!value) return null;
  return model.rules[c.rule].dialect === "legacy" ? { from: c.content.to, to: c.content.to, insert: " " + key + (flag ? "" : ":" + value) + ";" } : { from: c.content.bodyTo, to: c.content.bodyTo, insert: "," + key + (flag ? "" : " " + value) };
}
function removal(model, c) {
  if (!c.safe) throw Error("Complete syntax before removing a component.");
  if (c.kind === "header") throw Error("A rule requires a header.");
  if (c.kind === "option") throw Error("Advanced/unknown option dependencies are source-only; remove deliberately in source.");
  if (c.kind === "content") {
    const rule = model.rules[c.rule];
    if (rule.options.some((o) => o.from > c.content.from && ["pcre", "regex", "byte_test", "byte_jump", "byte_extract", "isdataat", "flowbits"].includes(o.key))) throw Error("Advanced later detection constructs may depend on this match. Resolve dependencies in source before removal.");
    const next = rule.components.filter((x) => x.kind === "content" && x.content.from > c.content.from)[0];
    if (next && ["distance", "within"].some((k) => modifierValues(next)[k] !== void 0)) throw Error("The next match has relative positioning. Resolve that dependency in source before removal.");
  }
  return c.spans.map((r) => ({ ...r, insert: "" }));
}
function movement(model, c, direction) {
  const r = model.rules[c.rule], items = r.components.filter((x) => x.kind === "reference"), i = items.indexOf(c), other = items[i + direction];
  if (!c.safe || c.kind !== "reference" || !other) throw Error("Only independent reference entries can be moved safely in this version. Detection order must be edited explicitly in source.");
  return [{ ...c.spans[0], insert: model.source.slice(other.spans[0].from, other.spans[0].to) }, { ...other.spans[0], insert: model.source.slice(c.spans[0].from, c.spans[0].to) }];
}
function conversion(model) {
  const changes = [], reasons = [];
  if (model.diagnostics.length) reasons.push("Complete the source before conversion.");
  for (const r of model.rules) {
    if (r.dialect !== "legacy") {
      reasons.push("Only explicitly recognized legacy syntax can be converted.");
      continue;
    }
    if (r.tokens.length === 7 && !["tcp", "udp", "icmp", "ip"].includes(r.tokens[1]?.text)) reasons.push("Service-specific legacy conversion is outside this version’s verified subset. Review it in source; the header will not be changed automatically.");
    const allowed = /* @__PURE__ */ new Set(["content", "flow", "reference", ...identities, ...MODIFIERS, ...BUFFERS]);
    if (r.options.some((o) => !allowed.has(o.key))) reasons.push("Unknown/context-dependent options require manual conversion review.");
    for (const c of r.components.filter((x) => x.kind === "content")) {
      const mods = modifierValues(c);
      if (!c.safe || c.inline.length || c.modifiers.some((o) => ["nocase", "fast_pattern"].includes(o.key) && o.value) || Object.keys(mods).some((k) => !["nocase", "fast_pattern", "offset", "depth"].includes(k))) reasons.push("Relative, advanced, ambiguous or mixed-dialect modifiers cannot be converted safely.");
      const before = (c.buffer?.raw || "pkt_data") + "; ";
      changes.push({ from: c.content.from, to: c.content.from, insert: before });
      if (c.buffer) changes.push({ from: c.buffer.from, to: c.buffer.to, insert: "" });
      for (const o of c.modifiers) {
        changes.push({ from: o.from, to: o.to, insert: "" });
        changes.push({ from: c.content.bodyTo, to: c.content.bodyTo, insert: "," + o.key + (o.value ? " " + o.value : "") });
      }
    }
  }
  let after = model.source;
  try {
    after = applyPatches(after, changes);
  } catch {
    reasons.push("Overlapping relationships require manual conversion.");
  }
  return { before: model.source, after, reasons: [...new Set(reasons)], safe: !reasons.length && changes.length > 0, explanation: "Move per-content legacy HTTP selectors before their matches and convert standalone modifiers to comma modifiers. Explicit pkt_data resets preserve default-payload matches. Header, unknown options and comments are retained. Engine validation and representative traffic tests remain necessary." };
}
export {
  BUFFERS,
  EMPTY,
  EXAMPLE,
  MODIFIERS,
  applyPatches,
  contentPatch,
  conversion,
  decodeMixed,
  encodeContent,
  hexBytes,
  modifierPatch,
  modifierValues,
  movement,
  parse,
  readContent,
  removal,
  segments,
  trimRange
};
