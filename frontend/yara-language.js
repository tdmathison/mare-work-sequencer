// Curated classic YARA 4.5.4 assistance; lexical ranges are not compiler validation.
const PROFILE = "classic YARA 4.5.4";
const START = 'rule analyst_rule {\n    strings:\n        $sample = "REPLACE_ME" ascii\n    condition:\n        $sample\n}\n';
const MODULES = {
  pe: { is_pe: "Boolean: PE file", number_of_sections: "Integer section count", entry_point: "Entry point RVA", imphash: "imphash() \u2192 string", imports: "imports(dll, function) \u2192 boolean", sections: "sections[index].name \u2192 string", MACHINE_I386: "PE x86 machine constant" },
  elf: { type: "ELF file type", machine: "ELF machine", entry_point: "Entry point address", number_of_sections: "Integer section count" },
  math: { entropy: "entropy(offset, size) \u2192 float", mean: "mean(offset, size) \u2192 float", in_range: "in_range(value, lower, upper) \u2192 boolean" },
  hash: { md5: "md5(offset, size) \u2192 string", sha256: "sha256(offset, size) \u2192 string", sha1: "sha1(offset, size) \u2192 string" },
  time: { now: "now() \u2192 integer" },
  dotnet: { is_dotnet: "Boolean: .NET file", version: "Runtime version string" }
};
const META = { author: "Analyst or team (user supplied)", description: "Rule purpose", reference: "Reference text or URL (never fetched)", date: "Creation date convention", modified: "Review date convention", version: "Team version convention", malware_family: "Family attribution (user supplied)", sample_sha256: "Known sample SHA-256 (user supplied)" };
const FUNCTIONS = { filesize: "File size in bytes", uint8: "uint8(offset) \u2192 integer", uint16: "uint16(offset) \u2192 integer", uint16be: "uint16be(offset) \u2192 integer", uint32: "uint32(offset) \u2192 integer", uint32be: "uint32be(offset) \u2192 integer", int8: "int8(offset) \u2192 integer", int16: "int16(offset) \u2192 integer", int32: "int32(offset) \u2192 integer" };
const SNIPPETS = [
  ["Any string", "any of them", "Requires declared strings"],
  ["All strings", "all of them", "Requires declared strings"],
  ["String group", "2 of ($group*)", "Replace group prefix; at least two matching declarations"],
  ["Offset", "$sample at 0", "Replace sample; absolute file offset"],
  ["Range", "$sample in (0..1024)", "Replace sample; file offset range"],
  ["Occurrences", "#sample > 2", "Replace sample; occurrence count"],
  ["Match offset", "@sample[1] == 0", "Replace sample; first occurrence offset"],
  ["Match length", "!sample[1] > 4", "Replace sample; first occurrence length"],
  ["File size", "filesize < 1MB", "File-size constraint"],
  ["File signature", "uint16(0) == 0x5A4D", "Little-endian MZ header"],
  ["Loop", "for any of them : ( $ at 0 )", "Requires declared strings"],
  ["PE module", "pe.is_pe and pe.number_of_sections > 3", 'Requires import "pe"; no automatic import']
];
function lex(source) {
  const tokens = [], diagnostics = [];
  let i = 0;
  const add = (kind, from, to) => tokens.push({ kind, from, to, value: source.slice(from, to) });
  while (i < source.length) {
    if (/\s/.test(source[i])) {
      i++;
      continue;
    }
    const start = i, c = source[i];
    if (source.startsWith("//", i)) {
      const end = source.indexOf("\n", i);
      i = end < 0 ? source.length : end;
      add("comment", start, i);
      continue;
    }
    if (source.startsWith("/*", i)) {
      const end = source.indexOf("*/", i + 2);
      i = end < 0 ? source.length : end + 2;
      add("comment", start, i);
      if (end < 0) diagnostics.push({ from: start, to: i, severity: "error", message: "Unterminated block comment", origin: "lexical" });
      continue;
    }
    if (c === '"' || c === "/" && ["=", "matches"].includes(tokens.filter((t) => t.kind !== "comment").at(-1)?.value)) {
      const endChar = c;
      let escape = false, closed = false, bracket = false;
      i++;
      for (; i < source.length; i++) {
        if (escape) {
          escape = false;
          continue;
        }
        if (source[i] === "\\") {
          escape = true;
          continue;
        }
        if (c === "/") {
          if (source[i] === "[") bracket = true;
          if (source[i] === "]") bracket = false;
        }
        if (source[i] === endChar && !bracket) {
          i++;
          closed = true;
          break;
        }
      }
      add(c === '"' ? "string" : "regexp", start, i);
      if (!closed) diagnostics.push({ from: start, to: i, severity: "error", message: "Unterminated literal", origin: "lexical" });
      continue;
    }
    const word = source.slice(i).match(/^(?:[$#@!][A-Za-z_][\w]*|[A-Za-z_][\w]*|0x[\da-fA-F]+|\d+)/);
    if (word) {
      i += word[0].length;
      add("word", start, i);
    } else {
      add("punct", i, ++i);
    }
  }
  return { tokens, diagnostics };
}
function analyze(source) {
  const { tokens, diagnostics } = lex(source), live = tokens.filter((t) => t.kind !== "comment"), rules = [], imports = [];
  for (let i = 0; i < live.length; i++) {
    if (live[i].value === "import" && live[i + 1]?.kind === "string") imports.push(live[i + 1].value.slice(1, -1));
    if (live[i].value !== "rule" || live[i + 1]?.kind !== "word") continue;
    const name = live[i + 1].value;
    let j = i + 2;
    while (j < live.length && live[j].value !== "{") j++;
    if (j === live.length) continue;
    const open = live[j];
    let depth = 1, k = j + 1;
    const sections = [];
    for (; k < live.length; k++) {
      const t = live[k];
      if (t.value === "{") depth++;
      if (t.value === "}") {
        depth--;
        if (!depth) break;
      }
      if (depth === 1 && ["meta", "strings", "condition"].includes(t.value) && live[k + 1]?.value === ":") sections.push({ name: t.value, from: t.from, start: live[k + 1].to });
    }
    const close = live[k], rule = { name, from: live[i].from, open: open.to, to: close?.to ?? source.length, close: close?.from ?? source.length, complete: !!close, sections, strings: [] };
    if (!close) diagnostics.push({ from: open.from, to: open.to, severity: "error", message: "Unclosed rule/hex block; helpers require a complete rule", origin: "lexical" });
    for (let n = 0; n < sections.length; n++) {
      const section = sections[n];
      section.end = sections[n + 1]?.from ?? rule.close;
    }
    const strings = sections.find((s) => s.name === "strings");
    if (strings) {
      for (let n = j + 1; n < k; n++) if (live[n].from >= strings.start && live[n].to <= strings.end && /^\$\w+$/.test(live[n].value) && live[n + 1]?.value === "=") rule.strings.push(live[n].value);
    }
    rules.push(rule);
    i = k;
  }
  return { tokens, diagnostics, rules, imports };
}
function ruleAt(model, pos) {
  return model.rules.find((r) => r.from <= pos && pos <= r.to);
}
function suggestions(source, pos) {
  const model = analyze(source), rule = ruleAt(model, pos), token = model.tokens.find((t) => t.from < pos && (pos < t.to || pos === t.to && (t.kind === "comment" && t.value.startsWith("//") || model.diagnostics.some(d => d.from === t.from && d.message.startsWith("Unterminated")))));
  if (token && ["comment", "string", "regexp"].includes(token.kind)) return { from: pos, options: [], message: "Completion is suppressed inside comments and literals." };
  const before = source.slice(0, pos), word = before.match(/[$#@!]?\w*$/)[0], from = pos - word.length;
  const module = before.slice(0, from).match(/\b(\w+)\.$/)?.[1];
  if (module) {
    if (!model.imports.includes(module)) return { from, options: [], message: `Import "${module}" before using its members. Preview an import below.` };
    return { from, options: Object.entries(MODULES[module] || {}).map(([label, detail]) => ({ label, detail, type: detail.includes("(") ? "function" : "property" })) };
  }
  const section = rule?.sections.find((s) => s.start <= pos && (pos < s.end || pos === s.end && !rule.complete));
  if (section?.name === "meta") return { from, options: Object.keys(META).map((label) => ({ label, detail: META[label], type: "property" })) };
  if (section?.name === "strings") {
    const line = before.slice(before.lastIndexOf("\n") + 1), definition = line.match(/\$\w+\s*=\s*("(?:\\.|[^"\\])*"|\/(?:\\.|[^/\\])*\/|\{[^}]*\})\s+(.*)$/);
    if (!definition) return { from, options: [], message: "Declare a string identifier and literal before requesting modifiers." };
    const used = new Set(definition[2].split(/\s+/));
    let choices = ["ascii", "wide", "nocase", "fullword", "private"];
    if (definition[1].startsWith("{")) choices = ["private"];
    else if (!definition[1].startsWith("/") && !["nocase", "fullword", "xor", "base64", "base64wide"].some((x) => used.has(x))) choices.push("xor", "base64", "base64wide");
    if (["base64", "base64wide"].some((x) => used.has(x))) choices = ["private"];
    if (used.has("xor")) choices = ["ascii", "wide", "private"];
    return { from, options: choices.filter((label) => !used.has(label)).map((label) => ({ label, type: "keyword", detail: "Classic YARA string modifier" })) };
  }
  if (section?.name === "condition") return { from, options: [...["and", "or", "not", "any", "all", "of", "them", "for", "in", "at", "true", "false", "defined"].map((label) => ({ label, type: "keyword" })), ...Object.entries(FUNCTIONS).map(([label, detail]) => ({ label, detail, type: detail.includes("(") ? "function" : "variable" })), ...(rule?.strings || []).flatMap((id) => ["$", "#", "@", "!"].map((prefix) => ({ label: prefix + id.slice(1), type: "variable", detail: "Local string reference" }))), ...model.rules.filter((r) => r !== rule).map((r) => ({ label: r.name, type: "variable", detail: "Rule dependency" })), ...model.imports.map((label) => ({ label, type: "namespace", detail: "Imported module" }))] };
  return { from, options: (rule ? ["meta", "strings", "condition"].filter((label) => !rule.sections.some((s) => s.name === label)) : ["import", "rule", "private", "global"]).map((label) => ({ label, type: "keyword" })) };
}
function encodeString(value) {
  return '"' + [...new TextEncoder().encode(value)].map((b) => b === 34 ? '\\"' : b === 92 ? "\\\\" : b >= 32 && b <= 126 ? String.fromCharCode(b) : "\\x" + b.toString(16).padStart(2, "0")).join("") + '"';
}
function metadataEdit(source, rule, key, value, type) {
  if (!rule?.complete || analyze(source).diagnostics.length) throw Error("Choose a complete, lexically safe rule for metadata insertion.");
  if (!/^[A-Za-z_]\w*$/.test(key)) throw Error("Use an ASCII identifier for the metadata key.");
  let literal;
  if (type === "String") literal = encodeString(value);
  else if (type === "Boolean") {
    if (!["true", "false"].includes(value.trim())) throw Error("Boolean value must be true or false.");
    literal = value.trim();
  } else {
    if (!/^-?\d+$/.test(value.trim()) || BigInt(value.trim()) < -(2n ** 63n) || BigInt(value.trim()) > 2n ** 63n - 1n) throw Error("Use a signed 64-bit integer.");
    literal = value.trim();
  }
  const section = rule.sections.find((s) => s.name === "meta"), tokens = lex(source).tokens.filter((t) => t.kind !== "comment");
  if (section) {
    const found = tokens.find((t, i) => t.from >= section.start && t.to <= section.end && t.value === key && tokens[i + 1]?.value === "=");
    if (found) return { existing: found };
  }
  const insert = section ? `
        ${key} = ${literal}
` : `
    meta:
        ${key} = ${literal}
`;
  const from = section ? section.start : rule.open;
  return { change: { from, insert } };
}
export {
  META,
  MODULES,
  PROFILE,
  SNIPPETS,
  START,
  analyze,
  encodeString,
  lex,
  metadataEdit,
  ruleAt,
  suggestions
};
