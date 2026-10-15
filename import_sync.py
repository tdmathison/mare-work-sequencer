"""Account-bound staged imports, per-case decisions, and recoverable replacement."""

import copy
import json
import os
import shutil
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path
from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for
from authorization import has_permission
from case_sync import (
    durable_json,
    encoded,
    digest,
    fingerprint,
    logical_snapshot,
    validate_graph,
    descends,
    synchronized_file,
)
from tagging import restore as restore_tags
from sync_review import decision_model, review_context

TTL = 3600


class ImportSync:
    def __init__(self, app, root, db, sync, backups, allocate, now):
        (
            self.app,
            self.root,
            self.db,
            self.sync,
            self.backups,
            self.allocate,
            self.now,
        ) = (app, root, db, sync, backups, allocate, now)
        app.extensions["case_import_sync"] = self
        self.staging = root / "sync-staging"
        self.recovery = root / "sync-recovery"
        self.staging.mkdir(mode=0o700, exist_ok=True)
        self.recovery.mkdir(mode=0o700, exist_ok=True)
        app.add_url_rule(
            "/import-export/review/<operation>", "sync_import_review", self.review
        )
        app.add_url_rule(
            "/import-export/apply/<operation>",
            "sync_import_apply",
            self.apply,
            methods=["POST"],
        )
        app.add_url_rule(
            "/api/v1/backups/review/<operation>", "sync_api_review", self.review
        )
        app.add_url_rule(
            "/api/v1/backups/apply/<operation>",
            "sync_api_apply",
            self.apply,
            methods=["POST"],
        )
        with app.app_context():
            self.sync.acquire()
            self.recover_interrupted()

    def permission(self):
        if not getattr(g, "user", None):
            abort(403)
        if self.api() and not has_permission(g.user, "backups:manage", self.db()):
            abort(403)

    def api(self):
        return request.path.startswith("/api/v1/")

    def owner(self, case):
        source = case.get("assigned_user")
        if isinstance(source, dict):
            row = (
                self.db()
                .execute(
                    "SELECT id FROM users WHERE user_uuid=? AND username=?",
                    (source.get("user_uuid"), source.get("username")),
                )
                .fetchone()
            )
            if row:
                return row[0]
        return None

    def lookup(self, operation):
        try:
            uuid.UUID(operation)
        except (ValueError, AttributeError):
            abort(404)
        row = (
            self.db()
            .execute(
                "SELECT * FROM sync_imports WHERE id=? AND user_id=? AND user_uuid=?",
                (operation, g.user["id"], g.user["user_uuid"]),
            )
            .fetchone()
        )
        if not row:
            abort(404)
        if row["status"] == "preview" and row["created"] + TTL < time.time():
            shutil.rmtree(self.staging / operation, ignore_errors=True)
            abort(410, "Import preview expired. Upload the archive again.")
        return row

    def classify(self, validated, meta, folder):
        incoming = logical_snapshot(validated, folder)
        content_hash = fingerprint(incoming)
        result = {
            "title": validated[0]["name"],
            "incoming_number": validated[0].get("number", ""),
            "fingerprint": content_hash,
            "case_uuid": None,
            "destination_id": None,
            "destination_number": None,
            "local_revision": None,
            "incoming_revision": None,
            "reason": "",
            "owner_warning": "",
            "summary": None,
            "classification": "review",
            "suggestions": [],
        }
        source = meta.get("sync")
        nodes = {}
        if source is not None:
            try:
                nodes = validate_graph(source, content_hash)
                result.update(
                    case_uuid=source["case_uuid"],
                    incoming_revision=source["revision_uuid"],
                )
                local = (
                    self.db()
                    .execute(
                        "SELECT cases.id,cases.number,sync_cases.origin_uuid FROM cases JOIN sync_cases ON cases.id=sync_cases.case_id WHERE case_uuid=?",
                        (source["case_uuid"],),
                    )
                    .fetchone()
                )
                if local and local["origin_uuid"] != source["origin_uuid"]:
                    raise ValueError("Origin identity disagrees with the local case.")
                known = self.sync.graph(source["case_uuid"])
                for key in nodes:
                    existing = (
                        self.db()
                        .execute(
                            "SELECT case_uuid,definition FROM sync_revisions WHERE uuid=?",
                            (key,),
                        )
                        .fetchone()
                    )
                    if existing and (
                        existing["case_uuid"] != source["case_uuid"]
                        or json.loads(existing["definition"]) != nodes[key]
                    ):
                        raise ValueError("Conflicting ancestry definitions.")
                if not local:
                    result.update(
                        classification="new",
                        reason="Permanent case UUID is absent on this installation.",
                    )
                else:
                    self.describe_local(result, local["id"], incoming)
                    state = self.sync.reconcile(local["id"])
                    result["local_revision"] = state["revision_uuid"]
                    combined = {**known, **nodes}
                    if fingerprint(self.sync.snapshot(local["id"])) == content_hash:
                        result.update(
                            classification="unchanged",
                            reason="Validated synchronized content matches; no content will be replaced.",
                        )
                    elif descends(
                        combined, source["revision_uuid"], state["revision_uuid"]
                    ):
                        result.update(
                            classification="update",
                            reason="Incoming revision descends from the destination revision.",
                        )
                    elif descends(
                        combined, state["revision_uuid"], source["revision_uuid"]
                    ):
                        result.update(
                            classification="older",
                            reason="Destination revision descends from the incoming revision.",
                        )
                    else:
                        result.update(
                            classification="conflict",
                            reason="Independent revision branches; explicit decision required.",
                        )
            except (ValueError, TypeError, AttributeError, KeyError) as error:
                result.update(classification="invalid", reason=str(error))
        else:
            match = (
                self.db()
                .execute(
                    "SELECT case_id FROM sync_legacy JOIN sync_cases USING(case_uuid) WHERE source_hash=?",
                    (content_hash,),
                )
                .fetchone()
            )
            if match:
                self.describe_local(result, match["case_id"], incoming)
                state = self.sync.reconcile(match["case_id"])
                result["local_revision"] = state["revision_uuid"]
                result.update(
                    classification="unchanged",
                    reason="Identical previously accepted legacy package; the current destination is retained.",
                )
            else:
                result["reason"] = (
                    "Legacy archive has no permanent identity. Explicitly treat as new or link; suggestions are not identity matches."
                )
                result["suggestions"] = [
                    dict(row)
                    for row in self.db().execute(
                        "SELECT id,number,name FROM cases WHERE name=? OR (external_number!='' AND external_number=?) LIMIT 20",
                        (validated[0]["name"], validated[0].get("external_number", "")),
                    )
                ]
        mapped = self.owner(validated[0])
        result["owner_warning"] = (
            "Incoming owner maps to an existing account."
            if mapped
            else "Incoming owner is unmatched or absent; applying incoming ownership will make the case Unassigned."
        )
        if result["destination_id"]:
            existing_owner = (
                self.db()
                .execute(
                    "SELECT owner FROM cases WHERE id=?", (result["destination_id"],)
                )
                .fetchone()[0]
            )
            if existing_owner != mapped:
                result[
                    "owner_warning"
                ] += " Existing owner differs and will be preserved unless explicitly changed."
        return result

    def describe_local(self, result, cid, incoming):
        local = (
            self.db().execute("SELECT number FROM cases WHERE id=?", (cid,)).fetchone()
        )
        if not local:
            raise ValueError("Destination case no longer exists.")
        snapshot = self.sync.snapshot(cid)
        before, after = snapshot["files"], incoming["files"]
        result.update(destination_id=cid, destination_number=local["number"])
        result["summary"] = {
            "metadata_fields": [
                key
                for key in incoming["case"]
                if snapshot["case"].get(key) != incoming["case"][key]
            ],
            "local_stage": snapshot["case"]["stage"],
            "incoming_stage": incoming["case"]["stage"],
            "files": {
                "added": sorted(set(after) - set(before)),
                "removed": sorted(set(before) - set(after)),
                "changed": sorted(
                    key for key in set(before) & set(after) if before[key] != after[key]
                ),
            },
            "records": {
                key: {
                    "before": len(snapshot["records"][key]),
                    "after": len(rows),
                    "changed": snapshot["records"][key] != rows,
                }
                for key, rows in incoming["records"].items()
            },
        }

    def preview(self, upload, single):
        self.permission()
        self.sync.acquire()
        self.recover_interrupted()
        if not upload:
            abort(400, "Choose a backup ZIP.")
        # Expired staging contains no long-lived archive copies.
        for row in (
            self.db()
            .execute(
                "SELECT id FROM sync_imports WHERE status='preview' AND created<?",
                (time.time() - TTL,),
            )
            .fetchall()
        ):
            shutil.rmtree(self.staging / row["id"], ignore_errors=True)
        operation = str(uuid.uuid4())
        directory = self.staging / operation
        directory.mkdir(mode=0o700)
        try:
            plans, catalog = self.backups["stage_upload"](upload, single, directory)
            items = []
            for folder, validated, meta in plans:
                classified = self.classify(validated, meta, folder / "mip")
                items.append(
                    {
                        "folder": folder.name,
                        "meta": meta,
                        "expected_files": logical_snapshot(validated, folder / "mip")[
                            "files"
                        ],
                        "staged_files": {
                            p.relative_to(folder / "mip").as_posix(): digest(p)
                            for p in (folder / "mip").rglob("*")
                            if p.is_file()
                        },
                        "preview": classified,
                    }
                )
            source = directory / ("single.zip" if single else "backup.zip")
            plan = {"items": items, "catalog": catalog}
            self.db().execute(
                "INSERT INTO sync_imports(id,user_id,filename,checksum,user_uuid,created,stage,status,plan) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    operation,
                    g.user["id"],
                    Path(upload.filename or "backup.zip").name,
                    digest(source),
                    g.user["user_uuid"],
                    time.time(),
                    operation,
                    "preview",
                    encoded(plan).decode(),
                ),
            )
            self.db().execute(
                "INSERT INTO audit(actor,action,created) VALUES(?,?,?)",
                (
                    g.user["username"],
                    f"Sync import {operation}: preview staged for {len(items)} cases; archive SHA-256 {digest(source)}",
                    self.now(),
                ),
            )
            if self.api():
                return (
                    jsonify(
                        operation=operation,
                        cases=[item["preview"] for item in items],
                        apply_url="/api/v1/backups/apply/" + operation,
                    ),
                    202,
                )
            return redirect(url_for("sync_import_review", operation=operation))
        except (
            ValueError,
            KeyError,
            TypeError,
            zipfile.BadZipFile,
            UnicodeError,
            RuntimeError,
            RecursionError,
            OverflowError,
            OSError,
        ) as error:
            message = (
                "Archive validation failed."
                if isinstance(error, OSError)
                else str(error)[:1000]
            )
            source = directory / (
                "single.zip" if (directory / "single.zip").exists() else "backup.zip"
            )
            checksum = digest(source) if source.is_file() else ""
            outcome = {
                "index": 0,
                "case_uuid": None,
                "classification": "invalid",
                "action": "Invalid/failed",
                "reason": message,
            }
            self.db().execute(
                "INSERT OR REPLACE INTO sync_imports(id,user_id,user_uuid,filename,checksum,created,completed,stage,status,plan,outcomes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    operation,
                    g.user["id"],
                    g.user["user_uuid"],
                    Path(upload.filename or "backup.zip").name,
                    checksum,
                    time.time(),
                    time.time(),
                    operation,
                    "complete",
                    encoded({"items": [], "catalog": None}).decode(),
                    encoded([outcome]).decode(),
                ),
            )
            self.record_outcome(operation, outcome)
            sqlite3.Connection.commit(self.db())
            shutil.rmtree(directory, ignore_errors=True)
            if self.api():
                return jsonify(operation=operation, error=message), 400
            flash("Import failed; no cases were added. " + message)
            return redirect("/import-export")
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def review(self, operation):
        self.permission()
        row = self.lookup(operation)
        plan = json.loads(row["plan"])
        outcomes = json.loads(row["outcomes"])
        items = [item["preview"] for item in plan["items"]]
        if self.api():
            return jsonify(
                operation=operation,
                status=row["status"],
                cases=items,
                outcomes=outcomes,
            )
        return render_template(
            "import_review.html",
            **review_context(plan, outcomes),
            operation=operation,
            items=items,
            outcomes=outcomes,
            status=row["status"],
            totals={
                key: sum(item["classification"] == key for item in items)
                for key in (
                    "new",
                    "update",
                    "unchanged",
                    "older",
                    "conflict",
                    "review",
                    "invalid",
                )
            },
            destinations=self.db()
            .execute("SELECT id,number,name FROM cases ORDER BY id DESC")
            .fetchall(),
        )

    def record_outcome(self, operation, result):
        # Audit stores counts and identities, never file contents or textual diffs.
        self.db().execute(
            "INSERT INTO audit(actor,action,created) VALUES(?,?,?)",
            (
                g.user["username"],
                f"Sync import {operation}: " + encoded(result).decode(),
                self.now(),
            ),
        )

    def persist_case_outcome(self, operation, outcome):
        row = (
            self.db()
            .execute("SELECT plan,outcomes FROM sync_imports WHERE id=?", (operation,))
            .fetchone()
        )
        plan = json.loads(row["plan"])
        plan["items"][outcome["index"]]["done"] = True
        outcomes = [
            item
            for item in json.loads(row["outcomes"])
            if item["index"] != outcome["index"]
        ] + [outcome]
        self.record_outcome(operation, outcome)
        self.db().execute(
            "UPDATE sync_imports SET plan=?,outcomes=? WHERE id=?",
            (encoded(plan).decode(), encoded(outcomes).decode(), operation),
        )

    def recovery_snapshot(self, cid, result_revision):
        state = self.sync.reconcile(cid)
        key = str(uuid.uuid4())
        directory = self.recovery / key
        directory.mkdir(mode=0o700)
        destination = self.root / "cases" / str(cid)
        try:
            shutil.copytree(destination, directory / "case", symlinks=True)
            records = {}
            for row in (
                self.db()
                .execute("SELECT name FROM sqlite_master WHERE type='table'")
                .fetchall()
            ):
                name = row["name"]
                columns = [
                    c["name"]
                    for c in self.db().execute(
                        'PRAGMA table_info("' + name.replace('"', '""') + '")'
                    )
                ]
                if "case_id" in columns:
                    records[name] = [
                        dict(record)
                        for record in self.db().execute(
                            'SELECT * FROM "'
                            + name.replace('"', '""')
                            + '" WHERE case_id=?',
                            (cid,),
                        )
                    ]
            document = {
                "case": dict(
                    self.db()
                    .execute("SELECT * FROM cases WHERE id=?", (cid,))
                    .fetchone()
                ),
                "records": records,
                "revisions": self.sync.graph(state["case_uuid"]),
                "previous_revision": state["revision_uuid"],
                "result_revision": result_revision,
                "case_id": cid,
            }
            durable_json(directory / "snapshot.json", document)
            durable_json(
                directory / "journal.json",
                {
                    "case_id": cid,
                    "previous_revision": state["revision_uuid"],
                    "result_revision": result_revision,
                    "status": "prepared",
                    "case_uuid": state["case_uuid"],
                },
            )
            self.db().execute(
                "INSERT INTO sync_recovery VALUES(?,?,?,?,?,?)",
                (key, cid, state["revision_uuid"], result_revision, key, "prepared"),
            )
            return key, directory
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def recover_interrupted(self):
        # Durable journal is outside the transaction: recover old filesystem if
        # DB revision did not commit, otherwise finalize the accepted package.
        for journal in self.recovery.glob("*/journal.json"):
            data = json.loads(journal.read_text())
            if data["status"] != "prepared":
                continue
            row = (
                self.db()
                .execute(
                    "SELECT revision_uuid,case_uuid FROM sync_cases WHERE case_id=?",
                    (data["case_id"],),
                )
                .fetchone()
            )
            if row and data.get("case_uuid") and row["case_uuid"] != data["case_uuid"]:
                data["status"] = "manual review: destination identity changed"
                durable_json(journal, data)
                continue
            marker = (
                self.db()
                .execute(
                    "SELECT result_revision FROM sync_recovery WHERE id=?",
                    (journal.parent.name,),
                )
                .fetchone()
            )
            if not marker or marker["result_revision"] != data["result_revision"]:
                dest = self.root / "cases" / str(data["case_id"])
                old = journal.parent / "old-case"
                if data.get("new"):
                    if dest.exists():
                        shutil.rmtree(dest)
                elif old.exists():
                    if dest.exists():
                        shutil.rmtree(dest)
                    old.rename(dest)
                elif (journal.parent / "case").exists():
                    replacement = journal.parent / "restore"
                    shutil.copytree(journal.parent / "case", replacement, symlinks=True)
                    if dest.exists():
                        shutil.rmtree(dest)
                    replacement.rename(dest)
                data["status"] = "rolled back after interruption"
            else:
                data["status"] = "committed"
                shutil.rmtree(journal.parent / "old-case", ignore_errors=True)
            durable_json(journal, data)

    def apply_one(self, operation, index, item, decision, ownership, target):
        planned_action = decision_model(
            item['preview']['classification'], decision, ownership, target, validate_target=False
        )
        preview = item["preview"]
        classification = preview["classification"]
        outcome = {
            "index": index,
            "case_uuid": preview["case_uuid"],
            "incoming_number": preview["incoming_number"],
            "destination_number": preview["destination_number"],
            "previous_revision": preview["local_revision"],
            "incoming_revision": preview["incoming_revision"],
            "classification": classification,
            "decision": decision,
            "ownership_decision": ownership,
            "action": "Conflict unresolved",
            "reason": preview["reason"],
            "recovery": None,
        }
        if planned_action == "invalid":
            outcome.update(action="Invalid/failed")
            return outcome
        if classification in ("conflict", "review") and decision not in (
            "keep",
            "replace",
            "new",
            "link",
        ):
            return outcome
        validated = self.sync.validate(item["meta"])
        staged = self.staging / operation / item["folder"]
        folder = staged / "mip"
        if any(path.is_symlink() for path in folder.rglob("*")):
            raise ValueError("Staged symlink rejected.")
        incoming = logical_snapshot(validated, folder)
        all_files = {
            p.relative_to(folder).as_posix(): digest(p)
            for p in folder.rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        if (
            all_files != item["staged_files"]
            or fingerprint(incoming) != preview["fingerprint"]
            or incoming["files"] != item["expected_files"]
        ):
            raise ValueError("Staged content changed; upload again.")
        source = item["meta"].get("sync")
        nodes = validate_graph(source, preview["fingerprint"]) if source else {}
        cid = preview["destination_id"]
        if classification == "review" and decision == "link":
            decision_model(classification, decision, ownership, target)
            cid = int(target)
            self.describe_local(preview, cid, incoming)
            state = self.sync.reconcile(cid)
            self.db().execute(
                "INSERT OR REPLACE INTO sync_legacy VALUES(?,?)",
                (preview["fingerprint"], state["case_uuid"]),
            )
            provenance = json.loads(state["provenance"])
            provenance.setdefault("legacy_sources", []).append(preview["fingerprint"])
            self.db().execute(
                "UPDATE sync_cases SET provenance=? WHERE case_id=?",
                (encoded(provenance).decode(), cid),
            )
            outcome.update(
                action="Kept local",
                case_uuid=state["case_uuid"],
                previous_revision=state["revision_uuid"],
                result_revision=state["revision_uuid"],
                reason="Legacy source explicitly linked as provenance. Local content retained because legacy schemas cannot guarantee completeness.",
                destination_number=preview["destination_number"],
            )
            return outcome
        if cid:
            state = self.sync.reconcile(cid)
            if state["revision_uuid"] != preview["local_revision"]:
                raise ValueError(
                    "Destination changed after preview. Upload again for refreshed review."
                )
        if classification == "unchanged":
            if source:
                self.sync.merge_graph(source["case_uuid"], nodes)
            outcome.update(action="Unchanged")
            return outcome
        if classification == "older":
            outcome.update(action="Skipped older")
            return outcome
        if planned_action == "kept":
            outcome.update(action="Kept local")
            return outcome
        if source and cid and classification == "conflict" and decision != "replace":
            return outcome
        if classification == "review" and decision != "new":
            return outcome
        if (
            cid
            and self.db()
            .execute(
                "SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",
                (cid,),
            )
            .fetchone()
        ):
            raise ValueError(
                "Active report generation blocks replacement; retry after it finishes."
            )
        c = validated[0]
        owner = self.owner(c)
        revision = source["revision_uuid"] if source else None
        recovery = None
        committed = False
        swapped = False
        new = False
        destination = None
        con = self.db()
        con.execute("SAVEPOINT sync_case")
        try:
            if cid:
                previous = state["revision_uuid"]
                case_uuid = state["case_uuid"]
                if nodes:
                    self.sync.merge_graph(case_uuid, nodes)
                if classification == "conflict" or not source:
                    revision = self.sync.new_revision(
                        cid,
                        preview["fingerprint"],
                        list(
                            dict.fromkeys([previous] + ([revision] if revision else []))
                        ),
                        adopt=False,
                    )
                key, recovery = self.recovery_snapshot(cid, revision)
                outcome["recovery"] = key
                destination = self.root / "cases" / str(cid)
                replacement = recovery / "replacement"
                shutil.copytree(destination, replacement, symlinks=True)
                # Replace the synchronized snapshot, retain local recovery folders,
                # sample payloads, and private data excluded by RAW exports.
                for path in sorted((replacement / "mip").rglob("*"), reverse=True):
                    if (path.is_file() or path.is_symlink()) and synchronized_file(
                        path.relative_to(replacement / "mip").as_posix()
                    ):
                        path.unlink()
                if (replacement / "mip").is_symlink():
                    raise ValueError("Existing package root must not be a symlink.")
                shutil.copytree(folder, replacement / "mip", dirs_exist_ok=True)
                con.execute(
                    "UPDATE cases SET name=?,description=?,stage=?,external_system=?,external_number=?,report_path=? WHERE id=?",
                    (
                        c["name"],
                        c.get("description", ""),
                        c["stage"],
                        c.get("external_system", ""),
                        c.get("external_number", ""),
                        c.get("report_path", ""),
                        cid,
                    ),
                )
                if ownership == "incoming":
                    con.execute("UPDATE cases SET owner=? WHERE id=?", (owner, cid))
            else:
                number = self.allocate(con)
                cid = con.execute(
                    "INSERT INTO cases(number,name,description,stage,created,owner,external_system,external_number,creator,creator_username,owner_required,report_path) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)",
                    (
                        number,
                        c["name"],
                        c.get("description", ""),
                        c["stage"],
                        self.now(),
                        owner,
                        c.get("external_system", ""),
                        c.get("external_number", ""),
                        g.user["id"],
                        g.user["username"],
                        c.get("report_path", ""),
                    ),
                ).lastrowid
                new = True
                destination = self.root / "cases" / str(cid)
                if destination.exists():
                    raise ValueError("Destination directory already exists.")
                case_uuid = source["case_uuid"] if source else str(uuid.uuid4())
                origin = source["origin_uuid"] if source else self.sync.installation()
                con.execute(
                    "INSERT INTO sync_cases(case_id,case_uuid,origin_uuid,provenance) VALUES(?,?,?,?)",
                    (
                        cid,
                        case_uuid,
                        origin,
                        encoded(
                            {
                                "source_creator": (
                                    source.get("source_creator")
                                    if source
                                    else item["meta"].get("source_creator")
                                ),
                                "source_case_number": c.get("number"),
                                "legacy": not bool(source),
                            }
                        ).decode(),
                    ),
                )
                if nodes:
                    self.sync.merge_graph(case_uuid, nodes)
                else:
                    revision = self.sync.new_revision(cid, preview["fingerprint"], [])
                replacement = staged
            if new:
                key = str(uuid.uuid4())
                recovery = self.recovery / key
                recovery.mkdir(mode=0o700)
                durable_json(
                    recovery / "journal.json",
                    {
                        "case_id": cid,
                        "previous_revision": None,
                        "result_revision": revision,
                        "status": "prepared",
                        "new": True,
                        "case_uuid": case_uuid,
                    },
                )
                con.execute(
                    "INSERT INTO sync_recovery VALUES(?,?,?,?,?,?)",
                    (key, cid, None, revision, key, "prepared"),
                )
                outcome["recovery"] = key
            self.backups["restore_records"](con, cid, copy.deepcopy(validated))
            con.execute(
                "UPDATE sync_cases SET revision_uuid=? WHERE case_id=?", (revision, cid)
            )
            if not source:
                con.execute(
                    "INSERT OR REPLACE INTO sync_legacy VALUES(?,?)",
                    (preview["fingerprint"], case_uuid),
                )
            destination.parent.mkdir(exist_ok=True)
            if not new:
                destination.rename(recovery / "old-case")
            replacement.rename(destination)
            swapped = True
            if fingerprint(self.sync.snapshot(cid)) != preview["fingerprint"]:
                raise ValueError("Restored content fingerprint differs; rolled back.")
            outcome.update(
                case_uuid=case_uuid,
                destination_number=con.execute(
                    "SELECT number FROM cases WHERE id=?", (cid,)
                ).fetchone()[0],
                result_revision=revision,
                action=(
                    "Imported new"
                    if new
                    else (
                        "Replaced by explicit decision"
                        if classification == "conflict" or not source
                        else "Updated existing"
                    )
                ),
                reason="Complete validated synchronized snapshot applied; no item-level merge.",
            )
            outcome["completed_at"] = self.now()
            self.persist_case_outcome(operation, outcome)
            con.execute("RELEASE sync_case")
            sqlite3.Connection.commit(con)
            committed = True
            outcome["_persisted"] = True
            if recovery:
                journal = recovery / "journal.json"
                data = json.loads(journal.read_text())
                data["status"] = "committed"
                durable_json(journal, data)
                shutil.rmtree(recovery / "old-case", ignore_errors=True)
                con.execute(
                    "UPDATE sync_recovery SET status='committed' WHERE id=?",
                    (outcome["recovery"],),
                )
            return outcome
        except Exception:
            if committed:
                outcome["_persisted"] = True
                outcome[
                    "reason"
                ] += " Recovery cleanup will be finalized on the next startup/import."
                return outcome
            con.execute("ROLLBACK TO sync_case")
            con.execute("RELEASE sync_case")
            if swapped and destination.exists():
                shutil.rmtree(destination)
            if recovery and (recovery / "old-case").exists():
                (recovery / "old-case").rename(destination)
            if recovery:
                journal = recovery / "journal.json"
                data = json.loads(journal.read_text())
                data["status"] = "rolled back"
                durable_json(journal, data)
            raise

    def apply(self, operation):
        self.permission()
        self.sync.acquire()
        self.recover_interrupted()
        row = self.lookup(operation)
        if row["status"] != "preview":
            return self.review(operation)
        plan = json.loads(row["plan"])
        outcomes = []
        prior = {item["index"]: item for item in json.loads(row["outcomes"])}
        restore_tags(self.db(), plan["catalog"])
        choices = request.get_json(silent=True) or {}
        for index, item in enumerate(plan["items"]):
            if item.get("done"):
                outcomes.append(prior[index])
                continue
            decision = request.form.get(
                f"decision-{index}", choices.get(str(index), {}).get("decision", "")
            )
            ownership = request.form.get(
                f"owner-{index}", choices.get(str(index), {}).get("owner", "local")
            )
            target = request.form.get(
                f"target-{index}", choices.get(str(index), {}).get("target")
            )
            try:
                outcome = self.apply_one(
                    operation, index, item, decision, ownership, target
                )
            except (ValueError, OSError, sqlite3.Error, KeyError) as error:
                outcome = {
                    "index": index,
                    "case_uuid": item["preview"]["case_uuid"],
                    "action": "Failed and rolled back",
                    "reason": str(error),
                }
            item["done"] = outcome["action"] not in (
                "Conflict unresolved",
                "Failed and rolled back",
            )
            outcomes.append(outcome)
            if not outcome.pop("_persisted", False):
                self.record_outcome(operation, outcome)
            self.db().execute(
                "UPDATE sync_imports SET plan=?,outcomes=? WHERE id=?",
                (encoded(plan).decode(), encoded(outcomes).decode(), operation),
            )
            sqlite3.Connection.commit(self.db())
        unresolved = any(
            outcome["action"] == "Conflict unresolved" for outcome in outcomes
        )
        self.db().execute(
            "UPDATE sync_imports SET status=?,completed=? WHERE id=?",
            (
                "preview" if unresolved else "complete",
                None if unresolved else time.time(),
                operation,
            ),
        )
        if not unresolved:
            shutil.rmtree(self.staging / operation, ignore_errors=True)
        if "mip_search" in self.app.extensions:
            self.app.extensions["mip_search"].invalidate()
        if self.api():
            return jsonify(
                operation=operation,
                outcomes=outcomes,
                status="preview" if unresolved else "complete",
            )
        return redirect(url_for("sync_import_review", operation=operation))
