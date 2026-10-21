"""Lossless rule-file inventory and atomic version-checked signature edits."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

LIMIT = 100_000
ACTIONS = (
    "alert",
    "log",
    "pass",
    "drop",
    "block",
    "reject",
    "react",
    "rewrite",
    "sdrop",
)


def version(raw):
    return hashlib.sha256(raw).hexdigest()


class ScanFailure(ValueError):
    """A lexical failure plus the independently completed prefix, never guessed recovery."""

    def __init__(self, reason, position, spans, directives, disabled):
        super().__init__(reason)
        self.position = position
        self.spans = list(spans)
        self.directives = list(directives)
        self.disabled = disabled


def _without_comments(source, strict=False):
    """Mask comments without moving offsets; quoted comment markers are literal."""
    result = list(source)
    i = 0
    quote = escape = False
    while i < len(source):
        c = source[i]
        if escape:
            escape = False
        elif quote and c == "\\":
            escape = True
        elif c == '"':
            quote = not quote
        elif not quote and (c == "#" or source.startswith("/*", i)):
            end = source.find("\n", i) if c == "#" else source.find("*/", i + 2)
            if end < 0 and c != "#" and strict:
                raise ValueError("Block comment crossing a directive line is unsupported; inspect the whole file.")
            end = len(source) if end < 0 else end if c == "#" else end + 2
            for j in range(i, end):
                if source[j] not in "\r\n":
                    result[j] = " "
            i = end
            continue
        i += 1
    if strict and quote:
        raise ValueError("Unterminated quoted directive; inspect the whole file.")
    return "".join(result)


def scan(source, allow_directives=True):
    """Lexical boundaries; never interpret SIDs as identities or enable comments.

    Outside rules, only recognized single-line directives are skippable. Complex
    configuration/block syntax fails closed for selected-rule editing.
    """
    if len(source.encode()) > LIMIT or "\x00" in source:
        raise ValueError("Rule source exceeds 100,000 UTF-8 bytes or contains NUL.")
    spans = []
    directives = []
    disabled = 0
    i = 0
    block = False

    def fail(reason, position=None):
        raise ScanFailure(reason, i if position is None else position, spans, directives, disabled)

    while i < len(source):
        if source.startswith("/*", i) and not block:
            end = source.find("*/", i + 2)
            if end < 0:
                fail("Unterminated block comment; close it with */.")
            i = end + 2
            continue
        if source[i].isspace():
            i += 1
            continue
        line_end = source.find("\n", i)
        if line_end < 0:
            line_end = len(source)
        if source[i] == "#":
            text = source[i:line_end].strip()
            if re.match(r"#\s*(?:begin|end)\b", text, re.I) and not re.fullmatch(
                r"#\s*(?:begin|end)\s*", text, re.I
            ):
                fail(
                    "Ambiguous disabled block marker; inspect the whole file."
                )
            if re.fullmatch(r"#\s*begin\s*", text, re.I):
                if block:
                    fail("Nested disabled block; inspect the whole file.")
                block = True
            elif re.fullmatch(r"#\s*end\s*", text, re.I):
                if not block:
                    fail("Unmatched disabled block terminator.")
                block = False
            if re.match(r"#\s*(?:" + "|".join(ACTIONS) + r")\s", text):
                disabled += 1
            i = line_end
            continue
        if block:
            if re.match(r"(?:" + "|".join(ACTIONS) + r")\s", source[i:line_end]):
                disabled += 1
            i = line_end
            continue
        word = re.match(r"[A-Za-z_]\w*", source[i:])
        if not word:
            fail(
                "Unrecognized text outside a rule; inspect the whole file."
            )
        if word[0] not in ACTIONS:
            try:
                text = _without_comments(source[i:line_end], strict=True)
            except ValueError as error:
                fail(str(error))
            if (
                not allow_directives
                or word[0]
                not in (
                    "var",
                    "ipvar",
                    "portvar",
                    "include",
                    "config",
                    "preprocessor",
                    "output",
                    "ruletype",
                )
                or any(c in text for c in "(){}")
                or text.rstrip().endswith("\\")
            ):
                fail(
                    "Unsupported or multiline directive; inspect the whole file. No source was changed."
                )
            directives.append(text)
            i = line_end
            continue
        start = i
        opening = None
        quoted = escaped = comment = False
        quote_start = None
        while i < len(source):
            c = source[i]
            if comment:
                if c in "\r\n":
                    comment = False
                i += 1
                continue
            if escaped:
                escaped = False
                i += 1
                continue
            if quoted and c == "\\":
                escaped = True
                i += 1
                continue
            if c == '"':
                if not quoted:
                    quote_start = i
                quoted = not quoted
                i += 1
                continue
            if quoted:
                i += 1
                continue
            if source.startswith("/*", i):
                end = source.find("*/", i + 2)
                if end < 0:
                    fail("Unterminated block comment; close it with */.")
                i = end + 2
                continue
            if c in "“”":
                fail('Typographic quote outside an ASCII-quoted value. Replace delimiter quotes with ASCII double quotes.')
            if c == "#":
                comment = True
                i += 1
                continue
            if c == "(":
                if opening is not None:
                    fail(
                        'Unexpected opening parenthesis inside the option block. Check for a missing ASCII opening quote in msg/content/pcre/regex; nested option blocks are not supported.'
                    )
                header = re.sub(r"\\\r?\n", " ", _without_comments(source[start:i]))
                tokens = re.findall(r"!?\[[^\[\]]*\]|\S+", header)
                if (
                    len(tokens) not in (2, 7)
                    or tokens[0] not in ACTIONS
                    or not re.fullmatch(r"[A-Za-z][\w-]*", tokens[1])
                    or (len(tokens) == 7 and tokens[4] not in ("->", "<>"))
                    or any(c in header for c in '"#;={}')
                ):
                    fail("Unsupported rule header; inspect the whole file.")
                opening = i
            elif c == ")":
                if opening is None:
                    fail("Unmatched rule parenthesis.")
                body = re.sub(
                    r'"(?:\\.|[^"\\])*"|#[^\r\n]*',
                    lambda m: '""' if m[0].startswith('"') else "",
                    _without_comments(source[opening + 1 : i]),
                )
                if not body.strip().endswith(";"):
                    fail(
                        "Missing option semicolon; selected-rule saving is unsafe."
                    )
                spans.append((start, i + 1, opening))
                i += 1
                break
            i += 1
        else:
            fail(
                "Unterminated quoted value; check ASCII quotes and escapes." if quoted else "Incomplete rule; missing closing option parenthesis.",
                quote_start if quoted else opening if opening is not None else start,
            )
    if block:
        fail("Unclosed disabled block; inspect the whole file.")
    return spans, directives, disabled


def boundaries(source):
    spans, _, _ = scan(source, False)
    if not spans:
        raise ValueError("No active complete rule.")
    return [(a, b) for a, b, _ in spans]


def options(source, start, end):
    """Semicolon statements outside strings/comments, for display metadata only."""
    source = _without_comments(source)
    quote = escape = comment = False
    begin = start
    result = []
    for i in range(start, end):
        c = source[i]
        if comment:
            if c in "\r\n":
                comment = False
                begin = i + 1
            continue
        if escape:
            escape = False
            continue
        if quote and c == "\\":
            escape = True
            continue
        if c == '"':
            quote = not quote
            continue
        if quote:
            continue
        if c == "#":
            comment = True
            continue
        if c == ";":
            text = source[begin:i].strip()
            key, sep, value = text.partition(":")
            if sep:
                result.append((key.strip(), value.strip()))
            begin = i + 1
    return result


def document(raw, filename="<rules>"):
    result = dict(
        version=version(raw),
        source="",
        rules=[],
        count=0,
        reason="",
        diagnostics=[],
        directives=[],
        disabled=0,
    )
    try:
        if len(raw) > LIMIT:
            raise ValueError("File exceeds 100,000 UTF-8 bytes.")
        text = raw.decode("utf-8-sig")
        bom = 3 if raw.startswith(b"\xef\xbb\xbf") else 0
        result["source"] = raw.decode("utf-8")
        try:
            spans, directives, disabled = scan(text)
        except ScanFailure as error:
            spans, directives, disabled = error.spans, error.directives, error.disabled
            position = min(error.position, len(text))
            line = text.count("\n", 0, position) + 1
            column = position - text.rfind("\n", 0, position)
            line_start = text.rfind("\n", 0, position) + 1
            line_end = text.find("\n", position)
            if line_end < 0:
                line_end = len(text)
            excerpt = text[max(line_start, position - 60):min(line_end, position + 100)].rstrip("\r")
            result["diagnostics"] = [dict(filename=filename, line=line, column=column,
                position=position, reason=str(error), excerpt=excerpt)]
            result["reason"] = (f"{filename}:{line}:{column}: {error} Source: {excerpt} "
                f"{len(spans)} safely recognized signature(s). Scanning stopped; subsequent regions are unverified.")
        result.update(directives=directives, disabled=disabled)
        for n, (a, b, opening) in enumerate(spans):
            metadata = {}
            for key, value in options(text, opening + 1, b - 1):
                if key in ("msg", "sid", "rev") and key not in metadata:
                    if key == "msg":
                        try:
                            value = json.loads(value)
                        except ValueError:
                            pass
                    metadata[key] = str(value)
            result["rules"].append(
                dict(
                    position=n + 1,
                    start=bom + len(text[:a].encode()),
                    end=bom + len(text[:b].encode()),
                    source=text[a:b],
                    line_start=text[:a].count("\n") + 1,
                    line_end=text[:b].count("\n") + 1,
                    header=text[a:opening].strip(),
                    message=metadata.get("msg", ""),
                    sid=metadata.get("sid", ""),
                    revision=metadata.get("rev", ""),
                )
            )
        result["count"] = len(spans)
        if not spans and not result["reason"]:
            result["reason"] = (
                "No active rules. Comments/disabled rules and directives are preserved; inspect the whole file."
            )
    except (ValueError, UnicodeError) as error:
        result.update(rules=[], count=0, reason=str(error))
    return result


def analyze(raw):
    info = document(raw)
    return dict(count=info["count"], reason=info["reason"])


def safe_signature(package, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or len(relative) > 400
        or "\\" in relative
        or any(ord(c) < 32 for c in relative)
        or PurePosixPath(relative).is_absolute()
        or any(p in ("", ".", "..") for p in relative.split("/"))
        or PurePosixPath(relative).suffix.lower() != ".rules"
    ):
        raise ValueError("Use a relative .rules filename within signatures/.")
    package = Path(package)
    if package.is_symlink() or package.parent.is_symlink():
        raise ValueError("Symbolic package paths are not allowed.")
    base = package.resolve() / "signatures"
    target = base / relative
    for path in [target, *target.parents]:
        if path.is_symlink():
            raise ValueError("Symbolic signature paths are not allowed.")
        if path == base:
            break
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError("Unsafe signature path.")
    return target


@contextmanager
def locked(package):
    import fcntl

    directory = Path(package).parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".signatures.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


class Conflict(FileExistsError):
    def __init__(self, message, current=None, kind="version"):
        super().__init__(message)
        self.current = current
        self.kind = kind


def _write(package, relative, raw, connection, cid, description="", expected=None):
    """Caller holds the case lock; preserve the complete file as supplied."""
    if len(raw) > LIMIT or b"\0" in raw:
        raise ValueError("Rule source exceeds limits or contains NUL.")
    target = safe_signature(package, relative)
    if target.exists() and target.stat().st_size > LIMIT:
        raise ValueError("Existing file exceeds editor limits; original retained.")
    original = target.read_bytes() if target.exists() else None
    current = version(original) if original is not None else None
    if current != expected:
        raise Conflict(
            "File changed, already exists or was removed. Reload or Save As; no replacement location was guessed.",
            current,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    old = connection.execute(
        "SELECT description,usage FROM artifacts WHERE case_id=? AND path=?",
        (cid, "signatures/" + relative),
    ).fetchone()
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=".rule-")
    published = False
    connection.execute("SAVEPOINT signatures")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        if original is None:
            os.link(name, target)
        else:
            os.replace(name, target)
        published = True
        connection.execute(
            "INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)",
            (
                cid,
                "signatures/" + relative,
                old["description"] if old else description,
                old["usage"] if old else "",
            ),
        )
        connection.execute(
            "INSERT OR REPLACE INTO readiness VALUES(?,'signatures','Pending','Content changed; review this category.')",
            (cid,),
        )
        connection.execute("RELEASE signatures")
        return dict(
            paths=["signatures/" + relative],
            version=version(raw),
            notice="",
            split=False,
        )
    except BaseException:
        connection.execute("ROLLBACK TO signatures")
        connection.execute("RELEASE signatures")
        if published:
            if original is None:
                target.unlink(missing_ok=True)
            else:
                restore_fd, restore = tempfile.mkstemp(
                    dir=target.parent, prefix=".restore-"
                )
                with os.fdopen(restore_fd, "wb") as out:
                    out.write(original)
                os.replace(restore, target)
        raise
    finally:
        Path(name).unlink(missing_ok=True)


def persist(package, relative, raw, connection, cid, description="", expected=None):
    """Whole-file upload/Save As. Never split, normalize, or combine files."""
    with locked(package):
        return _write(package, relative, raw, connection, cid, description, expected)


def selected_source(raw):
    info = document(raw)
    if info["count"] != 1 or info["reason"] or info["directives"] or info["disabled"]:
        raise ValueError(
            "The editor must contain exactly one complete active rule, without directives or disabled rules."
        )
    rule = info["rules"][0]
    if raw[: rule["start"]].strip() or raw[rule["end"] :].strip():
        raise ValueError(
            "Keep comments outside the selected rule in whole-file inspection; the editor must contain the rule only."
        )
    return rule


def save_selected(
    package, relative, replacement, connection, cid, expected, start, end
):
    with locked(package):
        target = safe_signature(package, relative)
        if not target.is_file():
            raise Conflict("Original file was removed. Reload or Save As.")
        if target.stat().st_size > LIMIT:
            raise ValueError("Original file exceeds editor limits.")
        original = target.read_bytes()
        if version(original) != expected:
            raise Conflict(
                "File changed since opening. Reload or Save As; selected-rule overwrite is blocked.",
                version(original),
            )
        info = document(original, relative)
        selected = next(
            (r for r in info["rules"] if r["start"] == start and r["end"] == end), None
        )
        if not selected:
            raise ValueError(
                "Selected range does not match an active rule in this snapshot. Reload the file."
            )
        edited = selected_source(replacement)
        updated = original[:start] + replacement + original[end:]
        parsed = document(updated, relative)
        # The uncertain suffix must remain identical in lexical context and position
        # (adjusted only by the selected replacement length). No resynchronization.
        shift = len(updated.decode("utf-8-sig")) - len(original.decode("utf-8-sig"))
        before_errors = [(d["position"] + shift, d["reason"]) for d in info["diagnostics"]]
        after_errors = [(d["position"], d["reason"]) for d in parsed["diagnostics"]]
        if before_errors != after_errors or parsed["count"] != info["count"]:
            raise ValueError("Updated boundaries are unsafe; original file retained.")
        index = selected["position"] - 1
        current = parsed["rules"][index]
        if (
            current["start"] != start + edited["start"]
            or current["end"] != start + edited["end"]
        ):
            raise ValueError(
                "Replacement would consume surrounding source; original retained."
            )
        result = _write(package, relative, updated, connection, cid, expected=expected)
        result.update(document=parsed, selected=current)
        return result
