(() => {
  const keywords = {
    python: new Set(
      "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(
        " ",
      ),
    ),
    bash: new Set(
      "alias break case cd command continue declare do done echo elif else esac eval exec exit export fi for function if in local printf read readonly return select set shift source test then time trap typeset ulimit umask unalias unset until while".split(
        " ",
      ),
    ),
    javascript: new Set(
      "async await break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield".split(
        " ",
      ),
    ),
  };
  const pythonBuiltins = new Set(
    "bool dict enumerate float int len list map max min print range set str sum tuple type zip".split(
      " ",
    ),
  );
  function renderLine(line, language) {
    const lang = (language || "").toLowerCase().replace(/[^a-z0-9]/g, ""),
      keywordSet =
        keywords[lang] ||
        (lang === "py" ? keywords.python : null) ||
        (["sh", "shell", "zsh"].includes(lang) ? keywords.bash : null) ||
        (["js", "jsx", "ts", "tsx", "typescript"].includes(lang)
          ? keywords.javascript
          : null),
      hashComments = [
        "python",
        "py",
        "bash",
        "sh",
        "shell",
        "zsh",
        "yaml",
        "yml",
        "toml",
        "ruby",
        "perl",
      ].includes(lang);
    let result = "",
      index = 0;
    while (index < line.length) {
      const character = line[index],
        next = line[index + 1];
      if (
        (hashComments && character === "#") ||
        (!hashComments && character === "/" && (next === "/" || next === "*")) ||
        (["sql"].includes(lang) && character === "-" && next === "-")
      ) {
        result += '<span class="md-token-comment">' +
          escape(line.slice(index)) +
          "</span>";
        break;
      }
      if (
        character === "'" ||
        character === '"' ||
        (character === "`" && ["javascript", "js", "typescript", "ts"].includes(lang))
      ) {
        let end = index + 1;
        while (end < line.length) {
          if (line[end] === "\\") end += 2;
          else if (line[end++] === character) break;
        }
        result +=
          '<span class="md-token-string">' +
          escape(line.slice(index, end)) +
          "</span>";
        index = end;
        continue;
      }
      if (character === "$" && /[A-Za-z_{]/.test(next || "")) {
        let end = index + 1;
        while (end < line.length && /[A-Za-z0-9_{}]/.test(line[end])) end++;
        result +=
          '<span class="md-token-variable">' +
          escape(line.slice(index, end)) +
          "</span>";
        index = end;
        continue;
      }
      const word = /^[A-Za-z_$][\w$]*/.exec(line.slice(index));
      if (word) {
        const value = word[0],
          following = line.slice(index + value.length),
          tokenClass = keywordSet?.has(value)
            ? "md-token-keyword"
            : lang === "python" && pythonBuiltins.has(value)
              ? "md-token-builtin"
              : /^\s*\(/.test(following)
                ? "md-token-function"
                : "";
        result += tokenClass
          ? '<span class="' + tokenClass + '">' + escape(value) + "</span>"
          : escape(value);
        index += value.length;
        continue;
      }
      const number = /^\d+(?:\.\d+)?/.exec(line.slice(index));
      if (number) {
        result +=
          '<span class="md-token-number">' + number[0] + "</span>";
        index += number[0].length;
        continue;
      }
      result += escape(character);
      index++;
    }
    return result;
  }
  function escape(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function renderMarkdown(text) {
    function renderInline(line) {
      if (/^\s*#{1,6}\s/.test(line))
        return '<span class="md-heading">' + escape(line) + "</span>";
      let result = "",
        last = 0;
      const pattern = /`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\)]+\)/g;
      for (const match of line.matchAll(pattern)) {
        result +=
          escape(line.slice(last, match.index)) +
          '<span class="' +
          (match[0][0] === "["
            ? "md-link"
            : match[0][0] === "`"
              ? "md-inline-code"
              : "md-emphasis") +
          '">' +
          escape(match[0]) +
          "</span>";
        last = match.index + match[0].length;
      }
      return result + escape(line.slice(last));
    }
    function isClosingFence(line, marker) {
      const match = /^\s*(`+|~+)\s*$/.exec(line);
      return match && match[1][0] === marker[0] && match[1].length >= marker.length;
    }
    const lines = text.split("\n"),
      rendered = [];
    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      const line = lines[lineIndex],
        opening = /^\s*(`{3,}|~{3,})(.*)$/.exec(line);
      if (!opening) {
        rendered.push(renderInline(line));
        continue;
      }
      rendered.push('<span class="md-code">' + escape(line) + "</span>");
      const marker = opening[1],
        language = opening[2].trim().split(/\s+/)[0] || "";
      let closingIndex = lineIndex + 1;
      while (
        closingIndex < lines.length &&
        !isClosingFence(lines[closingIndex], marker)
      )
        closingIndex++;
      const codeLines = lines.slice(lineIndex + 1, closingIndex);
      codeLines.forEach((codeLine, codeIndex) => {
        const position =
          codeLines.length === 1
            ? "single"
            : codeIndex === 0
              ? "first"
              : codeIndex === codeLines.length - 1
                ? "last"
                : "middle";
        rendered.push(
          '<span class="md-code-block-line md-code-block-' +
            position +
            '">' +
            renderLine(codeLine, language) +
            "</span>",
        );
      });
      if (closingIndex < lines.length) {
        rendered.push(
          '<span class="md-code">' + escape(lines[closingIndex]) + "</span>",
        );
        lineIndex = closingIndex;
      } else {
        lineIndex = lines.length;
      }
    }
    return rendered.join("\n") + "\n";
  }
  window.MareMarkdownSyntax = { renderLine, renderMarkdown };
})();