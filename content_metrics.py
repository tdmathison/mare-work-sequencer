"""Durable, content-free addition identities and a rebuildable current inventory.

Collectors run at migration and inside the existing CaseSync write transaction,
never while serving a chart. SQL triggers cover shared object services/API writes.
"""

from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
import re
from collections import defaultdict, deque

KINDS = {
    "families": "Malware Families",
    "actors": "Threat Actors",
    "tags": "Tags",
    "snort": "Snort signatures",
    "yara": "YARA signatures",
    "pdf": "PDF reports",
    "indicators": "Indicators",
    "references": "Reference links",
    "scripts": "Scripts",
    "samples": "Malware samples",
}
COLORS = dict(
    zip(
        KINDS,
        [
            "#d9ae58",
            "#8cbcff",
            "#ba9ce8",
            "#69c6b4",
            "#e8a1bb",
            "#eea76c",
            "#a9c8e0",
            "#c6c969",
            "#b0afa9",
            "#e58f88",
        ],
    )
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ready(con):
    return bool(
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='content_events'"
        ).fetchone()
    )


def hashed(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def coverage_start(con):
    row = con.execute(
        "SELECT coverage_start FROM content_metrics_state WHERE id=1"
    ).fetchone()
    return row[0] if row else now()


@contextmanager
def restoring(con):
    if not ready(con):
        yield
        return
    con.execute("INSERT OR IGNORE INTO content_metrics_state VALUES(1,?,0)", (now(),))
    con.execute("UPDATE content_metrics_state SET restoring=restoring+1 WHERE id=1")
    try:
        yield
    finally:
        con.execute(
            "UPDATE content_metrics_state SET restoring=max(0,restoring-1) WHERE id=1"
        )


def restore_call(function):
    @wraps(function)
    def wrapped(connection, *args, **kwargs):
        with restoring(connection):
            return function(connection, *args, **kwargs)

    return wrapped


def export_events(con, scope, scope_id):
    if not ready(con):
        return None
    payload = {
        "version": 1,
        "scope_id": scope_id,
        "events": [
            dict(r)
            for r in con.execute(
                "SELECT event_id,kind,source_key,added_at,live FROM content_events WHERE scope=? AND scope_id=? ORDER BY event_id",
                (scope, scope_id),
            )
        ],
    }
    if scope == "case":
        payload["slots"] = [
            dict(r)
            for r in con.execute(
                "SELECT position,source_key,content_hash FROM content_reference_slots WHERE scope_id=? ORDER BY position",
                (scope_id,),
            )
        ]
        payload["asset_types"] = [
            dict(r)
            for r in con.execute(
                "SELECT path,kind FROM content_asset_types WHERE case_id=(SELECT case_id FROM sync_cases WHERE case_uuid=?) ORDER BY path",
                (scope_id,),
            )
        ]
    return payload


def validate_events(payload):
    if payload is None:
        return
    if (
        not isinstance(payload, dict)
        or set(payload) - {"slots", "asset_types"} != {"version", "scope_id", "events"}
        or payload["version"] != 1
        or not isinstance(payload["scope_id"], str)
        or len(payload["scope_id"]) > 100
        or not isinstance(payload["events"], list)
        or len(payload["events"]) > 100000
    ):
        raise ValueError("Invalid content metric provenance.")
    slots = payload.get("slots", [])
    assets = payload.get("asset_types", [])
    if (
        not isinstance(slots, list)
        or len(slots) > 10000
        or not isinstance(assets, list)
        or len(assets) > 100000
    ):
        raise ValueError("Invalid metric identities.")
    positions = set()
    sources = set()
    for slot in slots:
        if (
            not isinstance(slot, dict)
            or set(slot) != {"position", "source_key", "content_hash"}
            or not isinstance(slot["position"], int)
            or not 0 <= slot["position"] < 10000
            or any(
                not isinstance(slot[k], str) or len(slot[k]) != 64
                for k in ("source_key", "content_hash")
            )
        ):
            raise ValueError("Invalid reference metric identity.")
        if slot["position"] in positions or slot["source_key"] in sources:
            raise ValueError("Duplicate reference metric identity.")
        positions.add(slot["position"])
        sources.add(slot["source_key"])
    for asset in assets:
        if (
            not isinstance(asset, dict)
            or set(asset) != {"path", "kind"}
            or asset["kind"] not in ("snort", "yara", "pdf")
            or not isinstance(asset["path"], str)
            or not asset["path"].startswith(
                ("reports/", "supporting/") if asset["kind"] == "pdf" else "signatures/"
            )
            or len(asset["path"]) > 1000
            or any(part in ("..", "") for part in asset["path"].split("/"))
        ):
            raise ValueError("Invalid asset classification.")
    seen = set()
    for event in payload["events"]:
        if (
            not isinstance(event, dict)
            or set(event) != {"event_id", "kind", "source_key", "added_at", "live"}
            or event["kind"] not in KINDS
            or event["live"] not in (0, 1)
            or any(
                not isinstance(event[k], str) or not 1 <= len(event[k]) <= 200
                for k in ("event_id", "source_key")
            )
            or event["event_id"] in seen
        ):
            raise ValueError("Invalid content metric event.")
        if event["added_at"] is not None:
            if not isinstance(event["added_at"], str) or len(event["added_at"]) > 100:
                raise ValueError("Invalid content metric date.")
        seen.add(event["event_id"])


def restore_events(con, payload, scope, scope_id):
    validate_events(payload)
    if payload is None or not ready(con):
        return
    # Copies with a new Case identity are independent additions at import time.
    copied = payload["scope_id"] != scope_id
    if scope == "case":
        con.execute("DELETE FROM content_reference_slots WHERE scope_id=?", (scope_id,))
        for slot in payload.get("slots", []):
            con.execute(
                "INSERT INTO content_reference_slots VALUES(?,?,?,?)",
                (scope_id, slot["position"], slot["source_key"], slot["content_hash"]),
            )
        for asset in payload.get("asset_types", []):
            con.execute(
                "INSERT OR REPLACE INTO content_asset_types SELECT case_id,?,? FROM sync_cases WHERE case_uuid=?",
                (asset["path"], asset["kind"], scope_id),
            )
    for event in payload["events"]:
        if copied and not event["live"]:
            continue
        if scope == "case" and event["kind"] in ("families", "actors", "tags"):
            raise ValueError("Invalid Case metric scope.")
        eid = (
            uuid.uuid5(uuid.NAMESPACE_URL, scope_id + ":" + event["event_id"]).hex
            if copied
            else event["event_id"]
        )
        if (
            copied
            and con.execute(
                "SELECT 1 FROM content_events WHERE scope=? AND scope_id=? AND kind=? AND source_key=? AND live=1",
                (scope, scope_id, event["kind"], event["source_key"]),
            ).fetchone()
        ):
            continue
        existing = con.execute(
            "SELECT scope,scope_id,kind,source_key FROM content_events WHERE event_id=?",
            (eid,),
        ).fetchone()
        if existing and tuple(existing) != (
            scope,
            scope_id,
            event["kind"],
            event["source_key"],
        ):
            raise ValueError("Metric identity conflicts with another object.")
        if scope == "case" and event["live"]:
            con.execute(
                "UPDATE content_events SET live=0 WHERE scope=? AND scope_id=? AND kind=? AND source_key=? AND event_id<>?",
                (scope, scope_id, event["kind"], event["source_key"], eid),
            )
        # Existing authoritative identities win on retries; no historical replay.
        con.execute(
            "INSERT INTO content_events VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET live=max(content_events.live,excluded.live),added_at=coalesce(content_events.added_at,excluded.added_at)",
            (
                eid,
                event["kind"],
                scope,
                scope_id,
                event["source_key"],
                now() if copied else event["added_at"],
                now(),
                event["live"],
            ),
        )


OBJECTS = [
    ("malware_families", "families", "profile", "id", "created_at", None),
    ("threat_actors", "actors", "profile", "id", "created_at", None),
    ("family_osint", "references", "profile", "family_id", None, None),
    ("actor_osint", "references", "profile", "actor_id", None, None),
    (
        "family_reports",
        "pdf",
        "profile",
        "family_id",
        "uploaded_at",
        "file_type='application/pdf'",
    ),
    (
        "actor_reports",
        "pdf",
        "profile",
        "actor_id",
        "uploaded_at",
        "file_type='application/pdf'",
    ),
]


def initialize(con, root):
    # Existing prototype-tag installations must remain able to run their explicit migration.
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='family_tag_identities'"
    ).fetchone():
        return
    con.executescript(
        """CREATE TABLE IF NOT EXISTS content_events(event_id TEXT PRIMARY KEY,kind TEXT NOT NULL,scope TEXT NOT NULL,scope_id TEXT NOT NULL,source_key TEXT NOT NULL,added_at TEXT,observed_at TEXT NOT NULL,live INTEGER NOT NULL CHECK(live IN (0,1)));
    CREATE INDEX IF NOT EXISTS content_events_period ON content_events(kind,added_at,scope,live);
    CREATE INDEX IF NOT EXISTS content_events_scope ON content_events(scope,scope_id,source_key,live);
    CREATE UNIQUE INDEX IF NOT EXISTS content_current_case_identity ON content_events(scope_id,kind,source_key) WHERE scope='case' AND live=1;
    CREATE TABLE IF NOT EXISTS content_metrics_state(id INTEGER PRIMARY KEY CHECK(id=1),coverage_start TEXT NOT NULL,restoring INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS content_reference_slots(scope_id TEXT NOT NULL,position INTEGER NOT NULL,source_key TEXT NOT NULL,content_hash TEXT NOT NULL,PRIMARY KEY(scope_id,position));
    CREATE TABLE IF NOT EXISTS content_asset_types(case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,path TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(case_id,path));"""
    )
    first = not con.execute(
        "SELECT 1 FROM schema_migrations WHERE name='content-metrics-v1'"
    ).fetchone()
    con.execute("INSERT OR IGNORE INTO content_metrics_state VALUES(1,?,0)", (now(),))
    for table, kind, scope, parent, date, predicate in OBJECTS:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            continue
        key = f"'{table}:'||id"
        key_new = f"'{table}:'||NEW.id"
        key_old = f"'{table}:'||OLD.id"
        where = " WHERE " + predicate if predicate else ""
        con.execute(
            f"INSERT OR IGNORE INTO content_events SELECT {key},'{kind}','{scope}',{parent},id,{date if date else 'NULL'},?,1 FROM {table}{where}",
            (now(),),
        )
        condition = "NEW." + predicate if predicate else "1"
        timestamp = (
            "NEW." + date
            if date
            else "CASE WHEN (SELECT restoring FROM content_metrics_state WHERE id=1)>0 THEN NULL ELSE strftime('%Y-%m-%dT%H:%M:%S+00:00','now') END"
        )
        con.executescript(
            f"""CREATE TRIGGER IF NOT EXISTS metrics_{table}_insert AFTER INSERT ON {table} WHEN {condition} BEGIN
          INSERT INTO content_events VALUES({key_new},'{kind}','{scope}',NEW.{parent},NEW.id,{timestamp},strftime('%Y-%m-%dT%H:%M:%S+00:00','now'),1)
          ON CONFLICT(event_id) DO UPDATE SET live=1;
        END;
        CREATE TRIGGER IF NOT EXISTS metrics_{table}_delete BEFORE DELETE ON {table} BEGIN UPDATE content_events SET live=0 WHERE event_id={key_old}; END;"""
        )
    con.execute(
        "INSERT OR IGNORE INTO content_events SELECT 'tags:'||i.identity,'tags','global','',i.identity,t.created_at,?,1 FROM tags t JOIN family_tag_identities i ON t.id=i.tag_id",
        (now(),),
    )
    con.executescript(
        """CREATE TRIGGER IF NOT EXISTS metrics_tag_insert AFTER INSERT ON family_tag_identities BEGIN
      INSERT OR IGNORE INTO content_events VALUES('tags:'||NEW.identity,'tags','global','',NEW.identity,CASE WHEN (SELECT restoring FROM content_metrics_state WHERE id=1)>0 THEN NULL ELSE (SELECT created_at FROM tags WHERE id=NEW.tag_id) END,strftime('%Y-%m-%dT%H:%M:%S+00:00','now'),1); END;
    CREATE TRIGGER IF NOT EXISTS metrics_tag_identity AFTER UPDATE OF identity ON family_tag_identities WHEN NEW.identity<>OLD.identity BEGIN
      UPDATE OR IGNORE content_events SET event_id='tags:'||NEW.identity,source_key=NEW.identity WHERE event_id='tags:'||OLD.identity;
      DELETE FROM content_events WHERE event_id='tags:'||OLD.identity;
      UPDATE content_events SET live=1 WHERE event_id='tags:'||NEW.identity; END;
    CREATE TRIGGER IF NOT EXISTS metrics_tag_date AFTER UPDATE OF created_at ON tags BEGIN UPDATE content_events SET added_at=NEW.created_at WHERE event_id='tags:'||(SELECT identity FROM family_tag_identities WHERE tag_id=NEW.id) AND added_at IS NULL; END;
    CREATE TRIGGER IF NOT EXISTS metrics_tag_delete BEFORE DELETE ON family_tag_identities BEGIN UPDATE content_events SET live=0 WHERE event_id='tags:'||OLD.identity; END;
    CREATE TRIGGER IF NOT EXISTS metrics_case_delete BEFORE DELETE ON cases BEGIN UPDATE content_events SET live=0 WHERE scope='case' AND scope_id=(SELECT case_uuid FROM sync_cases WHERE case_id=OLD.id); END;"""
    )
    if first:
        for row in con.execute("SELECT id FROM cases").fetchall():
            collect_case(con, root, row[0], legacy=True)
    con.execute("INSERT OR IGNORE INTO schema_migrations VALUES('content-metrics-v1')")
    con.commit()


def classify_asset(con, cid, path, kind):
    if ready(con):
        con.execute(
            "INSERT OR REPLACE INTO content_asset_types VALUES(?,?,?)",
            (cid, path, kind),
        )


def classify_uploaded_asset(con, cid, relative, target):
    """Shared web/REST asset-upload classification; never filename-only PDF typing."""
    path = Path(target)
    if (
        relative.split("/")[0] in ("reports", "supporting")
        and path.suffix.lower() == ".pdf"
    ):
        with path.open("rb") as source:
            is_pdf = source.read(5) == b"%PDF-"
        if is_pdf:
            classify_asset(con, cid, relative, "pdf")


def collect_case(con, root, cid, legacy=False):
    if not ready(con):
        return
    from indicators import load_table
    from references import load_references

    installation = con.execute(
        "SELECT value FROM site_settings WHERE name='installation_uuid'"
    ).fetchone()
    con.execute(
        "INSERT OR IGNORE INTO sync_cases(case_id,case_uuid,origin_uuid) VALUES(?,?,?)",
        (
            cid,
            str(uuid.uuid4()),
            installation[0] if installation else str(uuid.uuid4()),
        ),
    )
    scope_id = con.execute(
        "SELECT case_uuid FROM sync_cases WHERE case_id=?", (cid,)
    ).fetchone()[0]
    entries = []
    undated_sources = set()
    legacy_candidates = {}
    occurrences = defaultdict(int)
    for section in load_table(lambda: con, cid)["sections"]:
        for index, row in enumerate(section["rows"]):
            if not any(str(cell).strip() for cell in row):
                continue
            metas = section.get("row_meta", [])
            meta = metas[index] if index < len(metas) else None
            token = json.dumps(row, ensure_ascii=False)
            occurrence = occurrences[token]
            occurrences[token] += 1
            legacy_locator = "legacy-indicator:" + token + ":" + str(occurrence)
            if meta and meta.get("id"):
                legacy_candidates[hashed("indicator:" + meta["id"])] = hashed(
                    legacy_locator
                )
            entries.append(
                (
                    "indicators",
                    (
                        "indicator:" + meta["id"]
                        if meta and meta.get("id")
                        else legacy_locator
                    ),
                    meta.get("created") if meta else None,
                )
            )
    # Match existing rows before positional edits, preserving identities on reorder.
    references = [
        (index, row)
        for index, row in enumerate(load_references(lambda: con, cid)["rows"])
        if row[0].strip()
    ]
    slots = [
        dict(r)
        for r in con.execute(
            "SELECT * FROM content_reference_slots WHERE scope_id=?", (scope_id,)
        )
    ]
    assignments = {}
    used = set()
    by_digest = defaultdict(deque)
    by_position = {slot["position"]: slot for slot in slots}
    for slot in slots:
        by_digest[slot["content_hash"]].append(slot)
    for index, row in references:
        digest = hashed(json.dumps(row, ensure_ascii=False))
        old = by_digest[digest].popleft() if by_digest[digest] else None
        if old:
            assignments[index] = old["source_key"]
            used.add(old["source_key"])
    con.execute("DELETE FROM content_reference_slots WHERE scope_id=?", (scope_id,))
    unused = deque(slot for slot in slots if slot["source_key"] not in used)
    for index, row in references:
        source = assignments.get(index)
        if source is None:
            old = by_position.get(index)
            if old and old["source_key"] in used:
                old = None
            while unused and unused[0]["source_key"] in used:
                unused.popleft()
            if old is None and unused:
                old = unused.popleft()
            source = (
                old["source_key"] if old else hashed("reference:" + uuid.uuid4().hex)
            )
            used.add(source)
        con.execute(
            "INSERT INTO content_reference_slots VALUES(?,?,?,?)",
            (scope_id, index, source, hashed(json.dumps(row, ensure_ascii=False))),
        )
        entries.append(("references", source, None))
    folder = Path(root) / "cases" / str(cid) / "mip"
    classifications = {
        r["path"]: r["kind"]
        for r in con.execute(
            "SELECT path,kind FROM content_asset_types WHERE case_id=?", (cid,)
        )
    }
    from reporting import is_backup
    from reporting import OUTPUT

    report = con.execute("SELECT report_path FROM cases WHERE id=?", (cid,)).fetchone()
    generated_pdf = (
        Path((report[0] if report and report[0] else OUTPUT))
        .with_suffix(".pdf")
        .as_posix()
    )
    safe_folder = (
        not folder.is_symlink()
        and not folder.parent.is_symlink()
        and folder.resolve().is_relative_to(Path(root).resolve())
    )
    paths = {
        r[0] for r in con.execute("SELECT path FROM artifacts WHERE case_id=?", (cid,))
    }
    registered = set(paths)
    # Structured RAW directories also hold older records without artifact captions.
    for category in ("scripts", "signatures", "reports", "supporting"):
        parent = folder / category
        if safe_folder and parent.is_dir() and not parent.is_symlink():
            paths.update(
                path.relative_to(folder).as_posix()
                for path in parent.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and (
                    category in ("scripts", "signatures")
                    or path.suffix.lower() == ".pdf"
                )
            )
    for rel in sorted(paths if safe_folder else []):
        path = folder / rel
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.resolve().is_relative_to(folder.resolve())
            or is_backup(rel)
        ):
            continue
        from package_status import meaningful
        if not meaningful(path):continue
        category = rel.split("/")[0]
        kind = classifications.get(rel)
        if category == "samples":
            kind = "samples"  # Explicit asset-manager category, not filename.
        elif category == "scripts":
            kind = "scripts"
        elif (
            category in ("reports", "supporting")
            and not kind
            and path.suffix.lower() == ".pdf"
            and rel not in (generated_pdf, Path(OUTPUT).with_suffix(".pdf").as_posix())
        ):
            with path.open("rb") as stream:
                kind = "pdf" if stream.read(5) == b"%PDF-" else None
            if kind:
                classify_asset(con, cid, rel, kind)
        elif (
            category == "signatures"
            and not kind
            and path.suffix.lower() == ".rules"
            and path.stat().st_size <= 100000
        ):
            from signature_files import document

            try:
                if document(path.read_bytes())["count"] > 0:
                    kind = "snort"
            except (ValueError, UnicodeError):
                pass
        elif (
            category == "signatures"
            and not kind
            and path.suffix.lower() in (".yar", ".yara")
            and path.stat().st_size <= 100000
        ):
            # Conservative legacy recognition adds evidence beyond the suffix.
            try:
                text = path.read_text(encoding="utf-8-sig")
                masked = re.sub(
                    r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', " ", text, flags=re.S
                )
                if re.search(
                    r"\brule\s+[A-Za-z_]\w*(?:\s*:\s*[\w\s]+)?\s*\{", masked
                ) and re.search(r"\bcondition\s*:", masked):
                    kind = "yara"
            except (ValueError, UnicodeError):
                pass
        if kind in ("snort", "yara") and rel not in classifications:
            classify_asset(con, cid, rel, kind)
        if kind in KINDS:
            locator = "asset:" + rel
            if rel not in registered:
                undated_sources.add(locator)
            entries.append((kind, locator, None))
    previous = list(
        con.execute(
            "SELECT * FROM content_events WHERE scope='case' AND scope_id=? AND live=1",
            (scope_id,),
        )
    )
    prior = {(event["kind"], event["source_key"]): event for event in previous}
    claimed = {
        (kind, locator if kind == "references" else hashed(locator))
        for kind, locator, _ in entries
    }
    claimed.update(("indicators", source) for source in legacy_candidates.values())
    unknown = deque(
        event
        for event in previous
        if event["kind"] == "indicators"
        and event["added_at"] is None
        and ("indicators", event["source_key"]) not in claimed
    )
    keys = set()
    for kind, locator, date in entries:
        source = locator if kind == "references" else hashed(locator)
        keys.add((kind, source))
        existing = prior.get((kind, source))
        # First saving legacy rows can initialize STIX IDs without adding entries.
        if (
            not existing
            and kind == "indicators"
            and locator.startswith("indicator:indicator--")
        ):
            existing = prior.get(("indicators", legacy_candidates.get(source)))
            if existing is None and unknown:
                existing = unknown.popleft()
            if existing:
                con.execute(
                    "UPDATE content_events SET source_key=? WHERE event_id=?",
                    (source, existing["event_id"]),
                )
                keys.add((kind, existing["source_key"]))
        if not existing:
            con.execute(
                "INSERT INTO content_events VALUES(?,?,?,?,?,?,?,1)",
                (
                    uuid.uuid4().hex,
                    kind,
                    "case",
                    scope_id,
                    source,
                    date or (None if legacy or locator in undated_sources else now()),
                    now(),
                ),
            )
    for event in previous:
        if (event["kind"], event["source_key"]) not in keys:
            con.execute(
                "UPDATE content_events SET live=0 WHERE event_id=?",
                (event["event_id"],),
            )
