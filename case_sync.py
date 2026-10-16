"""Case snapshot identities and validated revision DAGs; no automatic merging."""

import contextlib
import copy
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from flask import g, has_request_context, request
from mip import CATEGORIES
from tagging import name as tag_name
from reporting import is_backup, SECTIONS

MAX_REVISIONS = 10000


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def durable_json(path, value):
    temporary = path.with_suffix(".pending")
    with temporary.open("wb") as output:
        output.write(encoded(value))
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Malformed synchronization UUID.")
    return value


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024**2):
            result.update(chunk)
    return result.hexdigest()


def synchronized_file(rel):
    return (
        rel.split("/")[0] in CATEGORIES
        and not is_backup(rel)
        and rel != 'iocs/indicators.stix.json'
        and not rel.startswith("samples/")
        and rel != "reports/reverse-engineering-notes.md"
    )


def logical_snapshot(validated, folder):
    c, sections, refs, records, images, sequence, tags = copy.deepcopy(validated)
    files = {
        p.relative_to(folder).as_posix(): digest(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
        and not p.is_symlink()
        and synchronized_file(p.relative_to(folder).as_posix())
        and not (
            p.parent == folder / "reports/sections"
            and p.stem in SECTIONS
            and p.stat().st_size == 0
        )
    }
    # Local task row IDs used in image section labels are not portable identity.
    for image in images:
        if image["section"].startswith("task-"):
            matches = [
                i
                for i, row in enumerate(records["tasks"])
                if image["name"] in row["body"]
            ]
            image["section"] = (
                "task-index-" + str(matches[0]) if matches else "task-draft"
            )
    readiness = {row["category"]: row for row in records["readiness"]}
    records["readiness"] = []
    for category in CATEGORIES:
        row = readiness.get(
            category, {"category": category, "status": "Pending", "reason": ""}
        )
        if (
            row["status"] == "Pending"
            and row["reason"] == "Content changed; review this category."
        ):
            row["reason"] = ""
        records["readiness"].append(row)
    for key in ("artifacts", "readiness", "deferred"):
        records[key].sort(key=lambda row: encoded(row))
    records["artifacts"] = [row for row in records["artifacts"] if row["path"] in files]
    return {
        "case": {
            key: c.get(key, "") if c.get(key) is not None else ""
            for key in (
                "name",
                "description",
                "external_system",
                "external_number",
                "stage",
                "report_path",
            )
        },
        "records": records,
        "indicators": sections,
        "references": refs,
        "images": sorted(images, key=lambda row: row["name"]),
        "sequence": sequence,
        "tags": sorted((tags or {}).get("tags", [])),
        "files": files,
    }


def canonical_tag_snapshot(snapshot):
    snapshot = copy.deepcopy(snapshot)
    snapshot['tags'] = sorted({tag_name(value) for value in snapshot['tags']})
    return snapshot


def equivalent_snapshot(left, right):
    """Compare canonical tag semantics only AFTER authenticating raw revisions."""
    try:
        return canonical_tag_snapshot(left) == canonical_tag_snapshot(right)
    except ValueError:
        return left == right  # Keep unremediated local legacy names unchanged.


def fingerprint(snapshot):
    return hashlib.sha256(encoded(snapshot)).hexdigest()


def validate_graph(sync, computed):
    if (
        not isinstance(sync, dict)
        or sync.get("schema") != "mare-case-sync/1"
        or sync.get("complete") is not True
    ):
        raise ValueError("Missing complete synchronization metadata; review required.")
    for key in ("case_uuid", "origin_uuid", "revision_uuid", "exporter_uuid"):
        identity(sync.get(key))
    graph = sync.get("revisions")
    if not isinstance(graph, list) or not 1 <= len(graph) <= MAX_REVISIONS:
        raise ValueError("Missing or excessive revision ancestry.")
    nodes = {}
    for entry in graph:
        if not isinstance(entry, dict) or set(entry) != {
            "uuid",
            "parents",
            "fingerprint",
            "created",
            "installation",
        }:
            raise ValueError("Invalid revision definition.")
        key = identity(entry["uuid"])
        identity(entry["installation"])
        if (
            key in nodes
            or not isinstance(entry["parents"], list)
            or len(entry["parents"]) > 2
            or len(set(entry["parents"])) != len(entry["parents"])
        ):
            raise ValueError("Duplicate revision or invalid parents.")
        for parent in entry["parents"]:
            identity(parent)
        if (
            not isinstance(entry["fingerprint"], str)
            or len(entry["fingerprint"]) != 64
            or any(c not in "0123456789abcdef" for c in entry["fingerprint"])
        ):
            raise ValueError("Invalid revision fingerprint.")
        try:
            datetime.fromisoformat(entry["created"].replace("Z", "+00:00"))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Invalid revision date.")
        nodes[key] = entry
    if (
        sync["revision_uuid"] not in nodes
        or nodes[sync["revision_uuid"]]["fingerprint"] != computed
    ):
        raise ValueError(
            "Incoming revision fingerprint does not match validated content."
        )
    # Iterative DFS avoids stack exhaustion on untrusted ancestry.
    done = set()
    for key in nodes:
        stack = [(key, False)]
        active = set()
        while stack:
            current, leaving = stack.pop()
            if leaving:
                active.remove(current)
                done.add(current)
                continue
            if current in done:
                continue
            if current in active:
                raise ValueError("Cyclic revision ancestry.")
            if current not in nodes:
                raise ValueError("Incomplete revision ancestry.")
            active.add(current)
            stack.append((current, True))
            stack.extend((parent, False) for parent in nodes[current]["parents"])
    return nodes


def descends(nodes, child, ancestor):
    seen = set()
    pending = [child]
    while pending:
        current = pending.pop()
        if current == ancestor:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(nodes.get(current, {}).get("parents", []))
    return False


class SyncConnection(sqlite3.Connection):
    """Existing route commit calls defer until content and revision commit together."""

    def execute(self, sql, parameters=()):
        if (
            sql.strip().upper() == "BEGIN IMMEDIATE"
            and self.in_transaction
            and has_request_context()
            and getattr(g, "sync_transaction", False)
        ):
            return super().execute("SELECT 1")
        return super().execute(sql, parameters)

    def commit(self):
        if not (has_request_context() and getattr(g, "sync_transaction", False)):
            super().commit()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.rollback()
        else:
            self.commit()
        return False


class CaseSync:
    def __init__(self, app, root, db, metadata, validate):
        self.app, self.root, self.db, self.metadata, self.validate = (
            app,
            root,
            db,
            metadata,
            validate,
        )
        with app.app_context():
            self.initialize()
        app.extensions["case_sync"] = self

        @app.before_request
        def start_sync_transaction():
            mutating = request.method in ("POST", "PUT", "PATCH", "DELETE")
            case_page = bool(
                (request.view_args or {}).get("cid")
                or (request.view_args or {}).get("case_id")
            )
            if getattr(g, "user", None) and (mutating or case_page):
                self.acquire()
                if "case_import_sync" in app.extensions:
                    app.extensions["case_import_sync"].recover_interrupted()
                g.sync_transaction = mutating

        handlers = app.before_request_funcs[None]
        handlers.remove(start_sync_transaction)
        handlers.insert(
            next(
                i for i, handler in enumerate(handlers) if handler.__name__ == "protect"
            )
            + 1,
            start_sync_transaction,
        )

        @app.after_request
        def finish_sync_transaction(response):
            if getattr(g, "sync_transaction", False):
                try:
                    if response.status_code < 400:
                        self.reconcile_dirty()
                        sqlite3.Connection.commit(self.db())
                    else:
                        self.db().rollback()
                finally:
                    g.sync_transaction = False
            return response

        @app.teardown_appcontext
        def unlock_sync(error):
            if "sync_lock" in g:
                os.close(g.pop("sync_lock"))

    def initialize(self):
        con = self.db()
        con.executescript(
            """
        CREATE TABLE IF NOT EXISTS sync_dirty(case_id INTEGER PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS sync_cases(case_id INTEGER PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,case_uuid TEXT UNIQUE NOT NULL,origin_uuid TEXT NOT NULL,revision_uuid TEXT,provenance TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS sync_revisions(uuid TEXT PRIMARY KEY,case_uuid TEXT NOT NULL,definition TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_imports(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,filename TEXT NOT NULL,checksum TEXT NOT NULL,user_uuid TEXT NOT NULL,created REAL NOT NULL,completed REAL,stage TEXT NOT NULL,status TEXT NOT NULL,plan TEXT NOT NULL,outcomes TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS sync_legacy(source_hash TEXT PRIMARY KEY,case_uuid TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_recovery(id TEXT PRIMARY KEY,case_id INTEGER,previous_revision TEXT,result_revision TEXT,location TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS immutable_sync_identity BEFORE UPDATE OF case_uuid,origin_uuid ON sync_cases WHEN NEW.case_uuid != OLD.case_uuid OR NEW.origin_uuid != OLD.origin_uuid BEGIN SELECT RAISE(ABORT,'Case synchronization identity is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_installation_identity BEFORE UPDATE ON site_settings WHEN OLD.name='installation_uuid' AND NEW.value!=OLD.value BEGIN SELECT RAISE(ABORT,'Installation identity is immutable'); END;
        """
        )
        columns = {
            row["name"] for row in con.execute("PRAGMA table_info(sync_imports)")
        }
        if "user_uuid" not in columns:
            con.execute(
                "ALTER TABLE sync_imports ADD COLUMN user_uuid TEXT NOT NULL DEFAULT ''"
            )
        for table in (
            "notes",
            "tasks",
            "history",
            "deferred",
            "readiness",
            "artifacts",
            "indicator_tables",
            "indicator_sections",
            "reference_tables",
            "report_images",
            "figure_sequence",
            "case_tags",
        ):
            for event, reference in [
                ("INSERT", "NEW"),
                ("UPDATE", "NEW"),
                ("DELETE", "OLD"),
            ]:
                con.execute(
                    f"CREATE TRIGGER IF NOT EXISTS sync_dirty_{table}_{event} AFTER {event} ON {table} BEGIN INSERT OR IGNORE INTO sync_dirty SELECT {reference}.case_id WHERE EXISTS(SELECT 1 FROM cases WHERE id={reference}.case_id); END"
                )
        con.executescript(
            """
        CREATE TRIGGER IF NOT EXISTS sync_dirty_case_insert AFTER INSERT ON cases BEGIN INSERT OR IGNORE INTO sync_dirty VALUES(NEW.id); END;
        CREATE TRIGGER IF NOT EXISTS sync_dirty_case_update AFTER UPDATE OF name,description,stage,external_system,external_number,report_path ON cases BEGIN INSERT OR IGNORE INTO sync_dirty VALUES(NEW.id); END;
        CREATE TRIGGER IF NOT EXISTS sync_dirty_tag_name AFTER UPDATE OF name ON tags BEGIN INSERT OR IGNORE INTO sync_dirty SELECT case_id FROM case_tags WHERE tag_id=NEW.id; END;
        """
        )
        self.installation()
        for row in con.execute("SELECT id FROM cases").fetchall():
            state = self.ensure(row["id"])
            if not state["revision_uuid"]:
                self.reconcile(row["id"])
        con.commit()

    def installation(self):
        self.db().execute(
            "INSERT OR IGNORE INTO site_settings VALUES('installation_uuid',?)",
            (str(uuid.uuid4()),),
        )
        return (
            self.db()
            .execute("SELECT value FROM site_settings WHERE name='installation_uuid'")
            .fetchone()[0]
        )

    def ensure(self, cid):
        self.db().execute(
            "INSERT OR IGNORE INTO sync_cases(case_id,case_uuid,origin_uuid) VALUES(?,?,?)",
            (cid, str(uuid.uuid4()), self.installation()),
        )
        return (
            self.db()
            .execute("SELECT * FROM sync_cases WHERE case_id=?", (cid,))
            .fetchone()
        )

    def acquire(self):
        if "sync_lock" not in g:
            import fcntl

            fd = os.open(self.root / ".case-sync.lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except Exception:
                os.close(fd)
                raise
            g.sync_lock = fd

    @contextlib.contextmanager
    def locked(self):
        existing = "sync_lock" in g
        self.acquire()
        try:
            yield
        finally:
            if not existing:
                os.close(g.pop("sync_lock"))

    def snapshot(self, cid):
        return logical_snapshot(
            self.validate(self.metadata(cid), allow_legacy_tags=True), self.root / "cases" / str(cid) / "mip"
        )

    def graph(self, case_uuid):
        return {
            row["uuid"]: json.loads(row["definition"])
            for row in self.db().execute(
                "SELECT uuid,definition FROM sync_revisions WHERE case_uuid=?",
                (case_uuid,),
            )
        }

    def merge_graph(self, case_uuid, nodes):
        for key, node in nodes.items():
            row = (
                self.db()
                .execute(
                    "SELECT case_uuid,definition FROM sync_revisions WHERE uuid=?",
                    (key,),
                )
                .fetchone()
            )
            if row and (
                row["case_uuid"] != case_uuid or json.loads(row["definition"]) != node
            ):
                raise ValueError(
                    "Conflicting ancestry definition for an existing revision UUID."
                )
        for key, node in nodes.items():
            self.db().execute(
                "INSERT OR IGNORE INTO sync_revisions VALUES(?,?,?)",
                (key, case_uuid, encoded(node).decode()),
            )

    def new_revision(self, cid, content_hash, parents, adopt=True):
        state = self.ensure(cid)
        key = str(uuid.uuid4())
        node = {
            "uuid": key,
            "parents": parents,
            "fingerprint": content_hash,
            "created": datetime.now(timezone.utc).isoformat(),
            "installation": self.installation(),
        }
        self.merge_graph(state["case_uuid"], {key: node})
        if adopt:
            self.db().execute(
                "UPDATE sync_cases SET revision_uuid=? WHERE case_id=?", (key, cid)
            )
        return key

    def reconcile(self, cid):
        state = self.ensure(cid)
        content_hash = fingerprint(self.snapshot(cid))
        nodes = self.graph(state["case_uuid"])
        if (
            not state["revision_uuid"]
            or nodes[state["revision_uuid"]]["fingerprint"] != content_hash
        ):
            self.new_revision(
                cid,
                content_hash,
                [state["revision_uuid"]] if state["revision_uuid"] else [],
            )
        return (
            self.db()
            .execute("SELECT * FROM sync_cases WHERE case_id=?", (cid,))
            .fetchone()
        )

    def reconcile_dirty(self):
        ids = {
            row["case_id"]
            for row in self.db().execute("SELECT case_id FROM sync_dirty")
        }
        cid = (request.view_args or {}).get(
            "cid", (request.view_args or {}).get("case_id")
        )
        if cid is not None:
            ids.add(cid)
        for cid in ids:
            if self.db().execute("SELECT 1 FROM cases WHERE id=?", (cid,)).fetchone():
                self.reconcile(cid)
        self.db().execute("DELETE FROM sync_dirty")

    def reconcile_all(self):
        for row in self.db().execute("SELECT id FROM cases").fetchall():
            self.reconcile(row["id"])

    def export(self, cid):
        self.acquire()
        state = self.reconcile(cid)
        self.db().commit()
        return {
            "schema": "mare-case-sync/1",
            "complete": True,
            "case_uuid": state["case_uuid"],
            "origin_uuid": state["origin_uuid"],
            "revision_uuid": state["revision_uuid"],
            "exporter_uuid": self.installation(),
            "revisions": list(self.graph(state["case_uuid"]).values()),
            "source_creator": json.loads(state["provenance"]).get("source_creator")
            or self.metadata(cid).get("source_creator"),
            "provenance": json.loads(state["provenance"]),
        }
