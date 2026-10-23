"""Local derived MIP index. No source writes, URL fetching, or artifact execution."""

import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from flask import abort, g, render_template, request, url_for
from authorization import has_permission
from mip import CATEGORIES
from reporting import is_backup

MAX_BYTES = 16 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_MEMBERS = 4000
MAX_EXPANDED = 128 * 1024 * 1024
MAX_FILES = 20000
MAX_INDEX_TEXT = 64 * 1024 * 1024
MAX_RECORDS = 40000
MAX_GROUP_FINDINGS = 200
REFRESH_SECONDS = 120
KINDS = {
    "metadata": "Case metadata",
    "indicators": "Indicators",
    "references": "References",
    "reports": "Reports",
    "notes": "Notes",
    "tasks": "Tasks",
    "filenames": "Filenames",
    "other": "Other file contents",
}
PERMISSIONS = {
    "indicators": "indicators:read",
    "references": "references:read",
    "reports": "reports:read",
}
TEXT_SUFFIXES = set(
    ".csv .tsv .txt .md .markdown .json .jsonl .ndjson .xml .html .htm .yaml .yml .py .py_ .ps1 .js .ts .sh .bat .cmd .vbs .sql .yara .yar .rule .rules .sig .log .ini .cfg .conf .rst .c .h .cpp .java .rb .toml .sigma .lua .go .rs .asm .s .ioc .strings .eml .sct .ipynb".split()
)
PRIVATE = {
    "workflow.sqlite3",
    "session.key",
    "api-keys.key",
    "credentials",
    ".env",
    "case-data.json",
}


def normalize(value):
    return (
        value.casefold()
        .replace("[.]", ".")
        .replace("(.)", ".")
        .replace("[:]", ":")
        .replace("[@]", "@")
        .replace("hxxps://", "https://")
        .replace("hxxp://", "http://")
    )


def match_spans(text, query):
    # Compile escaped literals only; callers cannot supply regular expressions.
    needle = normalize(query)
    if not needle:
        return
    tokens = re.findall(r"https?://|.", needle, re.S)
    alternatives = {
        ".": r"(?:\.|\[\.\]|\(\.\))",
        ":": r"(?::|\[:\])",
        "@": r"(?:@|\[@\])",
        "https://": r"(?:https|hxxps)(?::|\[:\])//",
        "http://": r"(?:http|hxxp)(?::|\[:\])//",
    }
    pattern = "".join(alternatives.get(token, re.escape(token)) for token in tokens)
    for match in re.finditer(pattern, text, re.I):
        yield match.start(), match.end()


def snippets(text, query, document=False):
    count, representatives = 0, []
    for span in match_spans(text, query):
        count += 1
        if len(representatives) < 3:
            representatives.append(span)
    excerpts = []
    for left, right in representatives:
        start, end = max(0, left - 85), min(len(text), right + 140)
        fragment = text[start:end]
        parts, cursor = [], 0
        for a, b in match_spans(fragment, query):
            parts.extend(
                [
                    {"text": fragment[cursor:a], "highlight": False},
                    {"text": fragment[a:b], "highlight": True},
                ]
            )
            cursor = b
        parts.append({"text": fragment[cursor:], "highlight": False})
        location = f"Line {text.count(chr(10), 0, left) + 1}"
        if document:
            line_start = text.rfind("\n", 0, left) + 1
            label = re.match(
                r"(Page \d+|Paragraph \d+|Table \d+, row \d+):", text[line_start:]
            )
            if label:
                location = label.group(1)
        excerpts.append({"location": location, "parts": parts})
    return count, excerpts


def safe_member(info):
    name = info.filename.rstrip("/")
    return (
        bool(name)
        and len(name) <= 2048
        and len(name.split("/")) <= 32
        and not name.startswith("/")
        and not any(c in name for c in ("\\", ":", "\x00"))
        and all(p not in ("", ".", "..") for p in name.split("/"))
        and not stat.S_ISLNK(info.external_attr >> 16)
    )


def excluded(name):
    parts = PurePosixPath(name).parts
    return (
        is_backup(name)
        or any(
            p.startswith(".")
            or p.lower() in PRIVATE
            or p.lower() in ("samples", "report-jobs", "users", "search-index")
            for p in parts
        )
        or Path(name).suffix.lower() in (".sqlite", ".sqlite3", ".db", ".key")
    )


def role(name):
    parts = PurePosixPath(name).parts
    if Path(name).name == "manifest.json":
        return "metadata"
    if "iocs" in parts:
        return "indicators"
    if Path(name).name == "references.csv":
        return "references"
    if Path(name).name == "reverse-engineering-notes.md":
        return "notes"
    if "reports" in parts or Path(name).suffix.lower() in (".docx", ".pdf"):
        return "reports"
    return "other"


def checked_source(path, root):
    path.resolve(strict=True).relative_to(root.resolve())
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError("Source symlinks are not searched")
        if current == current.parent:
            raise ValueError("Source is outside managed storage")
        current = current.parent


def file_key(path, member="", field=""):
    return "file:" + json.dumps([str(path), member, field])


def identity(path):
    st = path.stat()
    return f"{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}"


def parse_document(raw, suffix):
    """Executed in a size-limited, time-bounded helper; never runs source code."""
    if suffix == ".docx":
        from docx import Document

        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if (
                len(infos) > MAX_MEMBERS
                or sum(i.file_size for i in infos) > MAX_EXPANDED
                or any(not safe_member(i) or i.flag_bits & 1 for i in infos)
            ):
                raise ValueError("Unsafe, encrypted, or oversized DOCX container")
        doc = Document(io.BytesIO(raw))
        from docx.oxml.ns import qn

        def paragraph_text(element):
            return "".join(
                (
                    node.text or ""
                    if node.tag == qn("w:t")
                    else (
                        "\t"
                        if node.tag == qn("w:tab")
                        else "\n" if node.tag in (qn("w:br"), qn("w:cr")) else ""
                    )
                )
                for node in element.iter()
            )

        lines, paragraphs, tables = [], 0, 0
        for element in doc.element.body:
            if element.tag == qn("w:tbl"):
                tables += 1
                for row_number, row in enumerate(element.xpath("./w:tr"), 1):
                    cells = [
                        " ".join(paragraph_text(p) for p in cell.xpath(".//w:p"))
                        for cell in row.xpath("./w:tc")
                    ]
                    lines.append(
                        f"Table {tables}, row {row_number}: " + "\t".join(cells)
                    )
            elif element.tag == qn("w:p"):
                paragraphs += 1
                lines.append(f"Paragraph {paragraphs}: " + paragraph_text(element))
        return "\n".join(lines)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")
    if len(reader.pages) > 500:
        raise ValueError("PDF exceeds 500-page limit")
    lines = [
        f'Page {i+1}: {page.extract_text() or ""}'
        for i, page in enumerate(reader.pages)
    ]
    if not any(line.split(":", 1)[1].strip() for line in lines):
        raise ValueError(
            "PDF has no extractable text; scanned PDFs need OCR (unsupported)"
        )
    return "\n".join(lines)


def extract(raw, name):
    suffix = Path(name).suffix.lower()
    if len(raw) > MAX_BYTES:
        return "", "Oversized: exceeds 16 MiB"
    try:
        if suffix in (".docx", ".pdf"):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--extract", suffix],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if result.returncode:
                return (
                    "",
                    result.stderr.decode(errors="replace")[-500:]
                    or "Unreadable document",
                )
            text = result.stdout.decode("utf-8")
        elif suffix in TEXT_SUFFIXES or not suffix:
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = raw.decode("utf-16")
            else:
                text = raw.decode("utf-8-sig")
            if "\x00" in text:
                return "", "Binary content is unsupported"
        else:
            return "", "Unsupported format; filename searched only"
        if len(text) > MAX_TEXT:
            return text[:MAX_TEXT], "Partial content: exceeds 2 million characters"
        return text, ""
    except subprocess.TimeoutExpired:
        return "", "Document extraction exceeded 10 seconds"
    except (ValueError, UnicodeError, OSError) as exc:
        return "", f"Unreadable: {exc}"


def archive_metadata_fields(meta):
    if not isinstance(meta, dict) or meta.get("schema") != "mare-case-state/1":
        raise ValueError("Unsupported RAW case metadata")
    case = meta.get("case", {})
    for field in (
        "number",
        "name",
        "description",
        "stage",
        "external_system",
        "external_number",
        "created",
    ):
        yield "case:" + field, "metadata", "Case " + field, str(
            case.get(field, "") or ""
        )
    owner = case.get("assigned_user")
    if isinstance(owner, dict):
        yield "case:owner", "metadata", "Assigned owner", str(owner.get("username", ""))
    for kind, fields in (
        ("notes", ("title", "body", "author")),
        ("tasks", ("title", "body", "priority", "state")),
    ):
        for n, item in enumerate(meta.get("records", {}).get(kind, [])[:10000], 1):
            yield f"{kind}:{n}", kind, f"{kind[:-1].title()} {n}", "\n".join(
                str(item.get(field, "") or "") for field in fields
            )
    indicators = meta.get("indicators", {})
    sections = indicators.get("sections") or [
        {
            "id": "legacy",
            "title": "",
            "description": "",
            "rows": indicators.get("rows", []),
        }
    ]
    for n, section in enumerate(sections[:100], 1):
        for field in ("title", "description"):
            yield f"ioc:{n}:{field}", "indicators", f"Indicator section {n}: {field}", str(
                section.get(field, "")
            )
        for row, values in enumerate(section.get("rows", [])[:10000], 1):
            yield f"ioc:{n}:row:{row}", "indicators", f"Indicator section {n}, row {row}", "\n".join(
                map(str, values)
            )
    for row, values in enumerate(meta.get("references", {}).get("rows", [])[:10000], 1):
        yield f"reference:{row}", "references", f"Reference row {row}", "\n".join(
            map(str, values)
        )


class SearchIndex:
    def __init__(self, app, root, db, case_query):
        self.app, self.root, self.db, self.case_query = app, root, db, case_query
        self.directory = root / "search-index"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.lock = threading.Lock()
        self.dirty = True
        self.invalidation = self.directory / "changed"
        with self.connect() as con:
            con.executescript(
                """CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,key TEXT UNIQUE,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS status(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT);
            INSERT OR IGNORE INTO status VALUES(1,'{"state":"pending","updated":0,"skipped":[]}');"""
            )
        os.chmod(self.directory / "index.sqlite3", 0o600)

    def connect(self):
        self.directory.mkdir(mode=0o700, exist_ok=True)
        missing = not (self.directory / "index.sqlite3").exists()
        con = sqlite3.connect(self.directory / "index.sqlite3", timeout=10)
        if missing:
            con.executescript("""CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,key TEXT UNIQUE,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS status(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT);
            INSERT OR IGNORE INTO status VALUES(1,'{"state":"pending","updated":0,"skipped":[]}');""")
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def invalidate(self):
        self.dirty = True
        try:
            self.invalidation.touch()
        except OSError:
            self.app.logger.warning(
                "Could not publish MIP index invalidation; periodic refresh remains available",
                exc_info=True,
            )

    def status(self):
        with self.connect() as con:
            return json.loads(
                con.execute("SELECT payload FROM status WHERE id=1").fetchone()[0]
            )

    def set_status(self, value):
        with self.connect() as con:
            con.execute("UPDATE status SET payload=? WHERE id=1", (json.dumps(value),))

    def database_documents(self):
        for row in self.db().execute(self.case_query).fetchall():
            case = dict(row)
            cid = case["id"]

            def record(key, label, kind, text, tab="workbench"):
                content = str(text or "")
                return {
                    "key": f"db:{cid}:{key}",
                    "case": case,
                    "cid": cid,
                    "kind": kind,
                    "label": label,
                    "text": content[:MAX_TEXT],
                    "source": "current",
                    "version": "Current workspace",
                    "type": "Database",
                    "fingerprint": hashlib.sha256(content.encode()).hexdigest(),
                    "tab": tab,
                    "anchor": (
                        "note-" + key.split(":")[1]
                        if key.startswith("notes:")
                        else (
                            "task-" + key.split(":")[1]
                            if key.startswith("tasks:")
                            else "case-details" if kind == "metadata" else ""
                        )
                    ),
                    "warning": (
                        "Partial database field: exceeds 2 million characters"
                        if len(content) > MAX_TEXT
                        else ""
                    ),
                }

            for field in (
                "number",
                "external_number",
                "external_system",
                "name",
                "description",
                "creator_name",
                "owner_name",
            ):
                yield record(field, f"Case {field}", "metadata", case.get(field))
            for table, fields in (
                ("notes", ("title", "body", "author")),
                ("tasks", ("title", "body", "priority", "state")),
            ):
                for item in self.db().execute(
                    f"SELECT * FROM {table} WHERE case_id=?", (cid,)
                ):
                    doc = record(
                        f'{table}:{item["id"]}',
                        f'{table[:-1].title()} {item["id"]}',
                        table,
                        "\n".join(str(item[field] or "") for field in fields),
                        "tasks" if table == "tasks" else "workbench",
                    )
                    doc["fields"] = list(fields)
                    yield doc
            for item in self.db().execute(
                "SELECT path,description FROM artifacts WHERE case_id=?", (cid,)
            ):
                yield record(
                    f'artifact:{item["path"]}',
                    f'Artifact description: {item["path"]}',
                    role(item["path"]),
                    item["description"],
                    "package",
                )
            from indicators import load_table

            for section in load_table(self.db, cid)["sections"]:
                for field in ("title", "description"):
                    yield record(
                        f'ioc:{section["id"]}:{field}',
                        f'Indicator section {section["id"]}: {field}',
                        "indicators",
                        section[field],
                        "indicators",
                    )
                for n, values in enumerate(section["rows"], 1):
                    yield record(
                        f'ioc:{section["id"]}:row:{n}',
                        f'Indicator section {section["id"]}, row {n}',
                        "indicators",
                        "\n".join(values),
                        "indicators",
                    )
            from references import load_references

            for n, values in enumerate(load_references(self.db, cid)["rows"], 1):
                yield record(
                    f"reference:{n}",
                    f"Reference row {n}",
                    "references",
                    "\n".join(values),
                    "references",
                )

    def schedule(self):
        status = self.status()
        changed = (
            self.invalidation.stat().st_mtime_ns if self.invalidation.exists() else 0
        )
        if (
            status.get("state") == "ready"
            and not self.dirty
            and changed <= status.get("change_stamp", 0)
            and time.time() - status.get("updated", 0) < REFRESH_SECONDS
        ):
            return
        if not self.lock.acquire(blocking=False):
            return
        self.dirty = False
        self.set_status(status | {"state": "indexing"})
        threading.Thread(
            target=self._background, daemon=True, name="mare-mip-index"
        ).start()

    def _background(self):
        try:
            from contextlib import nullcontext
            workspace = self.app.extensions.get("backup_workspace")
            if workspace:
                from backup_workspace import lock
            with (lock(workspace.maintenance, False) if workspace else nullcontext()):
                with self.app.app_context():
                    self.refresh()
        finally:
            self.lock.release()

    def refresh(self):
        import fcntl

        with (self.directory / "refresh.lock").open("a") as lockfile:
            try:
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            self._refresh_locked()

    def _refresh_locked(self):
        started = time.monotonic()
        change_stamp = (
            self.invalidation.stat().st_mtime_ns if self.invalidation.exists() else 0
        )
        status = {
            "state": "indexing",
            "change_stamp": change_stamp,
            "updated": 0,
            "skipped": [],
            "files": 0,
            "documents": 0,
            "archives": 0,
        }
        self.set_status(status)
        try:
            with self.connect() as con:
                previous = {
                    key: json.loads(payload)
                    for key, payload in con.execute("SELECT key,payload FROM documents")
                }
            docs = []
            text_budget = 0
            for doc in self.database_documents():
                if (
                    len(docs) >= MAX_RECORDS
                    or text_budget + len(doc["text"].encode()) > MAX_INDEX_TEXT
                ):
                    status["partial"] = (
                        "Database record/text limit reached; coverage is incomplete."
                    )
                    break
                text_budget += len(doc["text"].encode())
                docs.append(doc)
            cases = {row["id"]: dict(row) for row in self.db().execute(self.case_query)}
            archive_meta = None
            archive_fingerprint = ""

            def skip(cid, path, reason):
                status["skipped_total"] = status.get("skipped_total", 0) + 1
                if len(status["skipped"]) < 500:
                    status["skipped"].append(
                        {"cid": cid, "path": path, "reason": reason}
                    )

            def file_doc(
                path,
                name,
                cid,
                archive="",
                member="",
                raw=None,
                field="",
                filename_only="",
            ):
                nonlocal text_budget
                fingerprint = archive_fingerprint if archive else identity(path)
                key = file_key(path, member, field)
                item = {
                    "key": key,
                    "case": cases.get(cid),
                    "cid": cid,
                    "kind": role(name),
                    "label": name,
                    "source": "archive" if archive else "current",
                    "version": archive or "Current workspace",
                    "type": Path(name).suffix.lower().lstrip(".") or "Text",
                    "path": str(path),
                    "member": member,
                    "fingerprint": fingerprint,
                    "text": "",
                    "warning": "",
                    "archive_case": archive_meta if archive else None,
                }
                old = previous.get(key)
                if filename_only:
                    item["warning"] = filename_only if filename_only != "mirror" else ""
                elif old and old["fingerprint"] == fingerprint:
                    item["text"], item["warning"] = old["text"], old["warning"]
                else:
                    try:
                        if raw is None:
                            source_stat = path.stat()
                            if not stat.S_ISREG(source_stat.st_mode):
                                item["warning"] = "Non-regular files are not searched"
                            elif source_stat.st_size > MAX_BYTES:
                                item["warning"] = (
                                    "Oversized: exceeds 16 MiB; filename searched only"
                                )
                            else:
                                with path.open("rb") as source:
                                    raw = source.read(MAX_BYTES + 1)
                        if raw is not None:
                            if field:
                                item["text"] = raw.decode("utf-8")[:MAX_TEXT]
                            else:
                                item["text"], item["warning"] = extract(raw, name)
                        if identity(path) != fingerprint:
                            item["text"], item["warning"] = (
                                "",
                                "Changed during indexing; retry search",
                            )
                    except (OSError, ValueError) as exc:
                        item["warning"] = f"Unreadable: {exc}"
                size = len(item["text"].encode())
                if text_budget + size > MAX_INDEX_TEXT:
                    item["text"], item["warning"] = (
                        "",
                        "Index text budget (64 MiB) reached; filename searched only",
                    )
                else:
                    text_budget += size
                if item["warning"]:
                    skip(
                        cid,
                        (archive + " → " if archive else "") + name,
                        item["warning"],
                    )
                docs.append(item)
                status["files"] += 1

            archive_paths = {}
            for cid in cases:
                root = self.root / "cases" / str(cid) / "mip"
                if not root.exists():
                    continue
                try:
                    checked_source(root, self.root)
                except (OSError, ValueError) as exc:
                    skip(cid, str(cid), str(exc))
                    continue
                for folder, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not excluded(d) and not (Path(folder) / d).is_symlink()
                    ]
                    for name in files:
                        path = Path(folder) / name
                        rel = path.relative_to(root).as_posix()
                        if (
                            excluded(rel)
                            or path.is_symlink()
                            or rel.split("/")[0] not in CATEGORIES
                        ):
                            continue
                        if (
                            status["files"] >= MAX_FILES
                            or time.monotonic() - started > 90
                        ):
                            skip(cid, rel, "Indexing file/time limit reached")
                            continue
                        # Generated mirrors are represented by database rows, not duplicated.
                        if rel in ("iocs/indicators.csv", "iocs/indicators.stix.json", "supporting/references.csv"):
                            file_doc(path, rel, cid, filename_only="mirror")
                            continue
                        if path.suffix.lower() == ".zip":
                            archive_paths[path] = cid
                        else:
                            file_doc(path, rel, cid)
            archive_root = self.root / "archives"
            if archive_root.exists():
                try:
                    checked_source(archive_root, self.root)
                except (OSError, ValueError) as exc:
                    skip(None, "archives", str(exc))
                    archive_root = self.directory / "not-scanned"
            for folder, dirs, files in os.walk(archive_root, followlinks=False):
                dirs[:] = [
                    d
                    for d in dirs
                    if not excluded(d) and not (Path(folder) / d).is_symlink()
                ]
                for name in files:
                    path = Path(folder) / name
                    if (
                        path.suffix.lower() == ".zip"
                        and not path.is_symlink()
                        and not excluded(name)
                    ):
                        archive_paths[path] = None
            for path in sorted(archive_paths):
                if status["files"] >= MAX_FILES or time.monotonic() - started > 90:
                    skip(None, path.name, "Indexing file/time limit reached")
                    continue
                cid = archive_paths[path]
                archive_start = len(docs)
                archive_label = path.relative_to(self.root).as_posix()
                try:
                    checked_source(path, self.root)
                    archive_fingerprint = identity(path)
                    if not stat.S_ISREG(path.stat().st_mode):
                        raise ValueError("Non-regular archives are not searched")
                    if path.stat().st_size > MAX_EXPANDED:
                        raise ValueError("Archive container exceeds 128 MiB")
                    with zipfile.ZipFile(path) as archive:
                        members = archive.infolist()
                        if (
                            len(members) > MAX_MEMBERS
                            or sum(i.file_size for i in members) > MAX_EXPANDED
                        ):
                            raise ValueError(
                                "Archive exceeds 4,000 members or 128 MiB expanded size"
                            )
                        if len({i.filename for i in members}) != len(members) or any(
                            not safe_member(i) for i in members
                        ):
                            raise ValueError(
                                "Archive has traversal, symlinks, duplicate, or unsafe members"
                            )
                        manifests = [
                            i
                            for i in members
                            if PurePosixPath(i.filename).name == "manifest.json"
                            and i.file_size <= MAX_BYTES
                            and not i.flag_bits & 1
                        ]
                        if len(manifests) != 1:
                            raise ValueError(
                                "Not a recognized Standard/RAW MIP archive (one manifest required)"
                            )
                        manifest = json.loads(archive.read(manifests[0]))
                        if manifest.get("schema") != "mare-mip/2.0" or manifest.get(
                            "archive_type"
                        ) not in ("standard", "raw"):
                            raise ValueError("Unsupported MIP manifest")
                        cid = next(
                            (
                                id
                                for id, c in cases.items()
                                if c["number"] == manifest.get("case_number")
                            ),
                            None,
                        )
                        archive_meta = {
                            "number": str(manifest.get("case_number", "Unknown")),
                            "name": str(manifest.get("title", path.name)),
                            "external_number": str(
                                manifest.get("external_reference", {}).get("number", "")
                            ),
                        }
                        status["archives"] += 1
                        for info in members:
                            if info.is_dir():
                                continue
                            if (
                                status["files"] >= MAX_FILES
                                or time.monotonic() - started > 90
                            ):
                                skip(
                                    cid,
                                    archive_label,
                                    "Indexing file/time limit reached",
                                )
                                break
                            name = info.filename
                            if PurePosixPath(name).name == "case-data.json":
                                if (
                                    info.file_size <= MAX_BYTES
                                    and not info.flag_bits & 1
                                ):
                                    meta = json.loads(archive.read(info))
                                    for (
                                        field,
                                        kind,
                                        label,
                                        content,
                                    ) in archive_metadata_fields(meta):
                                        if (
                                            status["files"] >= MAX_FILES
                                            or len(docs) >= MAX_RECORDS
                                            or time.monotonic() - started > 90
                                        ):
                                            skip(
                                                cid,
                                                name,
                                                "Indexing record/file/time limit reached",
                                            )
                                            break
                                        file_doc(
                                            path,
                                            name + " → " + label,
                                            cid,
                                            archive_label,
                                            name,
                                            content.encode(),
                                            field,
                                        )
                                        docs[-1]["kind"], docs[-1]["type"] = (
                                            kind,
                                            "JSON metadata",
                                        )
                                else:
                                    skip(
                                        cid, name, "Encrypted or oversized RAW metadata"
                                    )
                                continue
                            if excluded(name):
                                continue
                            if (
                                info.flag_bits & 1
                                or info.file_size > MAX_BYTES
                                or (
                                    info.file_size > 1024 * 1024
                                    and info.file_size / max(info.compress_size, 1)
                                    > 200
                                )
                            ):
                                file_doc(
                                    path,
                                    name,
                                    cid,
                                    archive_label,
                                    name,
                                    filename_only="Encrypted, oversized, or excessive compression ratio; filename searched only",
                                )
                                continue
                            if Path(name).suffix.lower() == ".zip":
                                file_doc(
                                    path,
                                    name,
                                    cid,
                                    archive_label,
                                    name,
                                    filename_only="Nested archives are not searched; filename searched only",
                                )
                                continue
                            old = previous.get(file_key(path, name))
                            raw = (
                                b""
                                if old and old["fingerprint"] == identity(path)
                                else archive.read(info)
                            )
                            file_doc(path, name, cid, archive_label, name, raw)
                    if identity(path) != archive_fingerprint:
                        del docs[archive_start:]
                        skip(
                            cid,
                            archive_label,
                            "Archive changed during indexing; retry search",
                        )
                except (
                    OSError,
                    ValueError,
                    zipfile.BadZipFile,
                    RuntimeError,
                    KeyError,
                    TypeError,
                    AttributeError,
                ) as exc:
                    skip(cid, archive_label, str(exc))
            with self.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                seen = set()
                for doc in docs:
                    old = previous.get(doc["key"])
                    doc["id"] = (
                        old["id"]
                        if old and old["fingerprint"] == doc["fingerprint"]
                        else uuid.uuid4().hex
                    )
                    doc["normalized"] = normalize(doc["text"])
                    doc["normalized_label"] = normalize(doc["label"])
                    seen.add(doc["key"])
                    con.execute(
                        "INSERT OR REPLACE INTO documents VALUES(?,?,?)",
                        (doc["id"], doc["key"], json.dumps(doc)),
                    )
                for key in set(previous) - seen:
                    con.execute("DELETE FROM documents WHERE key=?", (key,))
                status.update(
                    state="ready",
                    updated=time.time(),
                    documents=len(docs),
                    elapsed=round(time.monotonic() - started, 2),
                )
                con.execute(
                    "UPDATE status SET payload=? WHERE id=1", (json.dumps(status),)
                )
        except Exception:
            self.app.logger.exception("MIP indexing failed")
            status.update(
                state="error",
                updated=time.time(),
                error="Index refresh failed. Check server logs and data-directory permissions; retry the search.",
            )
            self.set_status(status)

    def allowed(self, doc):
        if not has_permission(g.user, "cases:read", self.db()):
            return False
        if doc.get("cid") is None and g.user["role"] != "Administrator":
            return False
        if (
            doc.get("cid") is not None
            and not self.db()
            .execute("SELECT 1 FROM cases WHERE id=?", (doc["cid"],))
            .fetchone()
        ):
            return False
        if doc["type"] != "Database" and not has_permission(
            g.user, "cases:assets", self.db()
        ):
            return False
        return has_permission(
            g.user, PERMISSIONS.get(doc["kind"], "cases:read"), self.db()
        )

    def query(self, text, kind="everything", source="all", stage="", page=1):
        groups = {}
        query_started = time.monotonic()
        partial = ""
        with self.connect() as con:
            rows = con.execute(
                "SELECT payload FROM documents WHERE instr(json_extract(payload,'$.normalized'),?)>0 OR instr(json_extract(payload,'$.normalized_label'),?)>0",
                (normalize(text), normalize(text)),
            ).fetchall()
        for (payload,) in rows:
            if time.monotonic() - query_started > 5:
                partial = "Search time limit reached; totals are partial. Narrow your query or filters."
                break
            doc = json.loads(payload)
            if kind == "filenames" and doc["type"] == "Database":
                continue
            if (
                not self.allowed(doc)
                or (source != "all" and doc["source"] != source)
                or (kind not in ("everything", "filenames") and doc["kind"] != kind)
            ):
                continue
            if stage and (not doc["case"] or str(doc["case"]["stage"]) != stage):
                continue
            content = doc["label"] if kind == "filenames" else doc["text"]
            count, excerpts = snippets(content, text, doc["type"] in ("docx", "pdf"))
            if kind == "everything":
                names, name_excerpts = snippets(doc["label"], text)
                count += names
                excerpts = (excerpts + name_excerpts)[:3]
            if not count:
                continue
            key = (
                str(doc["cid"])
                if doc["cid"] is not None
                else "unassociated:" + doc["version"]
            )
            group = groups.setdefault(
                key,
                {
                    "case": doc["case"],
                    "archive_case": doc.get("archive_case"),
                    "title": doc["version"],
                    "findings": [],
                },
            )
            group["findings"].append(
                {
                    k: doc[k]
                    for k in ("id", "label", "type", "source", "version", "kind")
                }
                | {"count": count, "excerpts": excerpts, "warning": doc["warning"]}
            )
        values = list(groups.values())
        total = len(values)
        pages = max(1, (total + 9) // 10)
        page = max(1, min(page, pages))
        artifacts = sum(len(x["findings"]) for x in values)
        selected = values[(page - 1) * 10 : page * 10]
        for group in selected:
            group["artifact_total"] = len(group["findings"])
            group["limited"] = len(group["findings"]) > MAX_GROUP_FINDINGS
            group["findings"] = group["findings"][:MAX_GROUP_FINDINGS]
        return {
            "groups": selected,
            "packages": total,
            "artifacts": artifacts,
            "page": page,
            "pages": pages,
            "partial": partial,
        }

    def finding(self, result_id):
        with self.connect() as con:
            row = con.execute(
                "SELECT payload FROM documents WHERE id=?", (result_id,)
            ).fetchone()
        if not row:
            abort(410, description="Finding no longer exists. Run the search again.")
        doc = json.loads(row[0])
        if not self.allowed(doc):
            abort(403)
        stale = False
        if doc["type"] == "Database":
            current = next(
                (d for d in self.database_documents() if d["key"] == doc["key"]), None
            )
            stale = not current or current["fingerprint"] != doc["fingerprint"]
        else:
            path = Path(doc["path"])
            try:
                checked_source(path, self.root)
                stale = identity(path) != doc["fingerprint"]
            except (OSError, ValueError):
                stale = True
        if stale:
            abort(
                409,
                description="This source changed or was deleted after indexing. Run the search again.",
            )
        return doc


def register_search(app, root, db, case_query, stages):
    index = SearchIndex(app, root, db, case_query)
    app.extensions["mip_search"] = index

    @app.context_processor
    def search_context():
        return {
            "can_mip_search": bool(g.get("user"))
            and has_permission(g.user, "cases:read", db())
        }

    def authorize():
        if not has_permission(g.user, "cases:read", db()):
            abort(403)

    @app.after_request
    def invalidate_search(response):
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and response.status_code < 400
        ):
            index.invalidate()
        if request.endpoint in (
            "mip_search",
            "mip_search_results",
            "mip_search_finding",
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/search")
    def mip_search():
        authorize()
        return render_template("mip_search.html", kinds=KINDS)

    @app.get("/search/results")
    def mip_search_results():
        authorize()
        text = request.args.get("q", "").strip()
        kind, source, stage = (
            request.args.get(k, default)
            for k, default in (("kind", "everything"), ("source", "all"), ("stage", ""))
        )
        if (
            len(text) > 300
            or kind not in {"everything", *KINDS}
            or source not in ("all", "current", "archive")
            or stage not in ("", *map(str, range(len(stages))))
        ):
            return {
                "error": "Invalid search filters or query longer than 300 characters."
            }, 400
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            return {"error": "Invalid page."}, 400
        index.schedule()
        result = (
            index.query(text, kind, source, stage, page)
            if text
            else {"groups": [], "packages": 0, "artifacts": 0, "page": 1, "pages": 1}
        )
        status = index.status()
        status["skipped"] = [
            item
            for item in status.get("skipped", [])
            if has_permission(g.user, "cases:assets", db())
            and has_permission(
                g.user, PERMISSIONS.get(role(item["path"]), "cases:read"), db()
            )
            and (
                (
                    item["cid"] is not None
                    and db()
                    .execute("SELECT 1 FROM cases WHERE id=?", (item["cid"],))
                    .fetchone()
                )
                or g.user["role"] == "Administrator"
            )
        ]
        return result | {"status": status}

    @app.get("/search/findings/<result_id>")
    def mip_search_finding(result_id):
        authorize()
        doc = index.finding(result_id)
        query = request.args.get("q", "")[:300]
        count, excerpts = (
            snippets(doc["text"], query, doc["type"] in ("docx", "pdf"))
            if query
            else (0, [])
        )
        case_url = f'/cases/{doc["cid"]}' if doc["cid"] is not None else ""
        asset_url = ""
        if doc["source"] == "current" and doc["type"] != "Database":
            asset_url = url_for("file", cid=doc["cid"], path=doc["label"], download=1)
        section_url = (
            case_url
            + "?tab="
            + doc.get("tab", "package")
            + ("#" + doc["anchor"] if doc.get("anchor") else "")
            if case_url
            else ""
        )
        return render_template(
            "mip_search_finding.html",
            doc=doc,
            search_url=url_for(
                "mip_search",
                **{
                    key: request.args[key]
                    for key in ("q", "kind", "source", "stage", "page")
                    if key in request.args
                },
            ),
            excerpts=excerpts,
            case_url=case_url,
            section_url=section_url,
            asset_url=asset_url,
        )


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--extract":
    try:
        # macOS/Linux address-space cap where supported. Wall time is enforced by parent.
        import resource

        if sys.platform != "darwin":
            resource.setrlimit(
                resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024)
            )
        resource.setrlimit(resource.RLIMIT_CPU, (8, 10))
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Document exceeds extraction size limit")
        result = parse_document(raw, sys.argv[2])
        if len(result) > MAX_TEXT:
            result = result[:MAX_TEXT] + "\n[Content truncated at 2 million characters]"
        sys.stdout.buffer.write(result.encode("utf-8"))
    except Exception as exc:
        sys.stderr.write(str(exc))
        sys.exit(1)
