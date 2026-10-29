"""Authenticated plugin draft API. No source is imported or executed here."""

import io
import json
import sqlite3
import zipfile
import zlib
from flask import abort, g, request, send_file
from authorization import has_permission
import plugin_store as store


def register_workspace(app, db, audit):
    def worker_status():
        from developer_worker.client import call, Unavailable

        try:
            result = call("GET", "/health")
            return {
                "available": bool(result.get("ready")),
                "message": (
                    "Isolated worker ready."
                    if result.get("ready")
                    else "Isolated worker unavailable."
                ),
            }
        except Unavailable as error:
            return {"available": False, "message": str(error)}

    def permitted(permission):
        if not has_permission(g.user, "plugins:read", db()) or not has_permission(
            g.user, permission, db()
        ):
            abort(403)

    def owned(pid, permission="plugins:read"):
        permitted(permission)
        row = (
            db()
            .execute(
                "SELECT * FROM developer_plugins WHERE id=? AND owner_uuid=? AND deleted=0",
                (pid, g.user["user_uuid"]),
            )
            .fetchone()
        )
        if row is None:
            abort(404)
        return row

    def payload():
        try:
            value = json.loads(request.form.get("payload", "{}"))
            if not isinstance(value, dict):
                raise ValueError("Expected an object.")
            return value
        except (ValueError, TypeError):
            abort(400, description="Invalid JSON payload.")

    def record(row):
        result = {
            key: row[key]
            for key in (
                "id",
                "name",
                "revision",
                "development",
                "enabled",
                "published_version",
                "created_at",
                "updated_at",
            )
        }
        result["protected"] = row["id"] in app.config.get("PROTECTED_PLUGIN_IDS", ())
        return result

    def requested_permissions(entries):
        try:
            return store.manifest(json.loads(entries["plugin.json"]["body"]))[
                "permissions"
            ]
        except (ValueError, KeyError, TypeError):
            return []

    def write_files(pid, entries):
        db().executemany(
            "INSERT INTO developer_files VALUES(?,?,?,?)",
            [
                (pid, p, item["body"], int(item["directory"]))
                for p, item in entries.items()
            ],
        )

    def create(value, entries):
        timestamp = store.now()
        try:
            with db():
                db().execute(
                    "INSERT INTO developer_plugins(id,owner_uuid,name,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (
                        value["id"],
                        g.user["user_uuid"],
                        value["name"],
                        timestamp,
                        timestamp,
                    ),
                )
                write_files(value["id"], entries)
        except sqlite3.IntegrityError:
            abort(409, description="That plugin identifier is already registered.")
        audit("Created plugin " + value["id"])
        return {"id": value["id"]}, 201

    def listed_record(row):
        result = record(row)
        if request.args.get("management") == "1":
            checked = store.static_validation(store.files(db(), row["id"]))
            result["package_valid"] = bool(
                checked["valid"] and checked["manifest"]["id"] == row["id"]
            )
            result["manifest"] = checked["manifest"]
            result["errors"] = [d["message"] for d in checked["diagnostics"]]
            if checked["manifest"] and checked["manifest"]["id"] != row["id"]:
                result["errors"].append(
                    "Manifest identifier does not match registration."
                )
        return result

    @app.get("/developer/workspace/plugins")
    def developer_plugin_list():
        permitted("plugins:read")
        return {
            "plugins": [
                listed_record(row)
                for row in db().execute(
                    "SELECT * FROM developer_plugins WHERE owner_uuid=? AND deleted=0 ORDER BY name COLLATE NOCASE,id",
                    (g.user["user_uuid"],),
                )
            ],
            "permissions": [
                p
                for p in (
                    "create",
                    "edit",
                    "validate",
                    "test",
                    "execute",
                    "debug",
                    "publish",
                    "versions",
                    "delete",
                    "configure",
                )
                if has_permission(g.user, "plugins:" + p, db())
            ],
            "templates": [{"id": k, "name": v[0]} for k, v in store.TEMPLATES.items()],
            "data_permissions": sorted(store.DATA_PERMISSIONS),
            "worker": worker_status(),
        }

    @app.post("/developer/workspace/discovery")
    def developer_plugin_discovery():
        permitted("plugins:read")
        from pathlib import Path
        from plugin_discovery import discover

        try:
            packages, invalid = discover(
                app.config.get("PLUGINS_DIR")
                or __import__("os").environ.get("MARE_PLUGINS_DIR")
                or Path(app.root_path) / "plugins"
            )
        except (OSError, ValueError) as error:
            return {"error": "Plugin discovery failed: " + str(error)}, 503
        registered = []
        for location, entries, value in packages:
            existing = (
                db()
                .execute(
                    "SELECT owner_uuid,deleted FROM developer_plugins WHERE id=?",
                    (value["id"],),
                )
                .fetchone()
            )
            if existing:
                if existing["owner_uuid"] != g.user["user_uuid"] or existing["deleted"]:
                    invalid.append(
                        {
                            "package": location,
                            "error": "Identifier already registered or reserved; no package was overwritten.",
                        }
                    )
                continue
            if not has_permission(g.user, "plugins:create", db()):
                invalid.append(
                    {
                        "package": location,
                        "error": "Registration requires plugins:create permission.",
                    }
                )
                continue
            try:
                with db():
                    timestamp = store.now()
                    db().execute(
                        "INSERT INTO developer_plugins(id,owner_uuid,name,created_at,updated_at,source_location) VALUES(?,?,?,?,?,?)",
                        (
                            value["id"],
                            g.user["user_uuid"],
                            value["name"],
                            timestamp,
                            timestamp,
                            location,
                        ),
                    )
                    write_files(value["id"], entries)
                registered.append(value["id"])
                audit("Discovered plugin " + value["id"])
            except sqlite3.IntegrityError:
                invalid.append(
                    {
                        "package": location,
                        "error": "Identifier was registered concurrently; refresh.",
                    }
                )
        return {"registered": registered, "invalid": invalid}

    @app.post("/developer/workspace/plugins")
    def developer_plugin_create():
        permitted("plugins:create")
        data = payload()
        try:
            value = store.manifest(
                {
                    **data.get("manifest", {}),
                    "schema": "mws-plugin/1",
                    "api_version": "v1",
                    "sdk_version": ">=1,<2",
                    "plugin_api": "1",
                    "entrypoint": "main.py:run",
                }
            )
            entries = store.template_files(value, data.get("template", "hello"))
        except (ValueError, TypeError, AttributeError) as error:
            abort(400, description=str(error))
        return create(value, entries)

    @app.post("/developer/workspace/import")
    def developer_plugin_import():
        permitted("plugins:create")
        upload = request.files.get("archive")
        if not upload:
            abort(400, description="Select a plugin ZIP archive.")
        try:
            entries, value = store.inspect_archive(
                upload.stream.read(store.MAX_TOTAL + 1)
            )
        except (
            ValueError,
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
        ) as error:
            abort(400, description=str(error))
        return create(value, entries)

    @app.get("/developer/workspace/plugins/<pid>")
    def developer_plugin_detail(pid):
        row = owned(pid)
        entries = store.files(db(), pid)
        result = record(row)
        checked = store.static_validation(entries)
        if checked["manifest"] and checked["manifest"]["id"] != pid:
            checked["valid"] = False
            checked["diagnostics"].append(
                {
                    "path": "plugin.json",
                    "line": 1,
                    "severity": "error",
                    "message": "Manifest identifier does not match its registration.",
                }
            )
        result.update(
            manifest=checked["manifest"],
            validation={
                "valid": checked["valid"],
                "diagnostics": checked["diagnostics"],
            },
            compatibility={
                "status": "Compatible" if checked["valid"] else "Invalid",
                "definition": "Manifest/SDK/API contract checks; installed dependencies are verified by the isolated worker.",
            },
            location="Registry package "
            + pid
            + (
                (" (imported from plugins/" + row["source_location"] + ")")
                if row["source_location"]
                else ""
            ),
            granted_permissions=[p for p in requested_permissions(entries) if has_permission(g.user,p,db())],
            requested_permissions=requested_permissions(entries),
            files=[
                {
                    "path": path,
                    "directory": v["directory"],
                    "size": len(v["body"]),
                    "sha256": store.digest(v["body"]),
                }
                for path, v in entries.items()
            ],
            fingerprint=store.fingerprint(entries),
            versions=[
                {
                    **{
                        k: r[k]
                        for k in (
                            "version",
                            "fingerprint",
                            "publisher_uuid",
                            "created_at",
                        )
                    },
                    "permissions": json.loads(r["manifest"]).get("permissions", []),
                }
                for r in db().execute(
                    "SELECT * FROM developer_versions WHERE plugin_id=? ORDER BY created_at DESC",
                    (pid,),
                )
            ],
        )
        return result

    @app.get("/developer/workspace/plugins/<pid>/file")
    def developer_plugin_file(pid):
        owned(pid)
        try:
            path = store.safe_path(request.args.get("path"))
        except ValueError as error:
            abort(400, description=str(error))
        item = (
            db()
            .execute(
                "SELECT * FROM developer_files WHERE plugin_id=? AND path=?",
                (pid, path),
            )
            .fetchone()
        )
        if item is None or item["directory"]:
            abort(404)
        return send_file(
            io.BytesIO(item["body"]),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=path.rsplit("/", 1)[-1],
        )

    @app.post("/developer/workspace/plugins/<pid>/files")
    def developer_plugin_files(pid):
        owned(pid, "plugins:edit")
        data = payload()
        try:
            revision = int(data["revision"])
            operation = data.get("operation", "save")
            path = data.get("path", "")
            changes = None
            entries = store.files(db(), pid)
            previous_permissions = requested_permissions(entries)
            if operation in ("delete", "rename", "move", "copy"):
                from plugin_file_operations import organize
                entries, changes = organize(entries, operation, data.get("paths", [path]), data.get("destination", ""), data.get("target"))
            elif operation in ("save", "create", "directory", "upload"):
                from plugin_file_operations import destination_path
                path = store.safe_path(path) if operation == "save" else destination_path(path)
                if operation != "save" and (path in entries or operation != "directory" and any(p.startswith(path + "/") for p in entries)):
                    raise ValueError("That path already exists.")
                if operation == "save" and (
                    path not in entries or entries[path]["directory"]
                ):
                    raise ValueError("Select an existing text file.")
                if operation == "upload":
                    upload = request.files.get("file")
                    if not upload:
                        raise ValueError("Select a file.")
                    body = upload.stream.read(store.MAX_FILE + 1)
                else:
                    text = data.get("text", "")
                    if not isinstance(text, str):
                        raise ValueError("Expected text.")
                    body = text.encode("utf-8")
                entries[path] = {"body": body, "directory": operation == "directory"}
            else:
                raise ValueError("Unknown file operation.")
            store.validate_tree(entries)
            # Compare-and-swap occurs in the same transaction as replacement, preventing lost updates.
            with db():
                changed = db().execute(
                    "UPDATE developer_plugins SET revision=revision+1,development='Draft',updated_at=? WHERE id=? AND owner_uuid=? AND revision=? AND deleted=0",
                    (store.now(), pid, g.user["user_uuid"], revision),
                )
                if changed.rowcount != 1:
                    abort(
                        409,
                        description="The plugin changed in another editor. Refresh before saving; your buffer has been retained.",
                    )
                try:
                    metadata = store.manifest(
                        json.loads(entries["plugin.json"]["body"])
                    )
                    if metadata["id"] == pid:
                        db().execute(
                            "UPDATE developer_plugins SET name=? WHERE id=?",
                            (metadata["name"], pid),
                        )
                except (ValueError, KeyError, TypeError):
                    pass  # Incomplete manifests remain editable drafts.
                db().execute("DELETE FROM developer_files WHERE plugin_id=?", (pid,))
                write_files(pid, entries)
        except FileNotFoundError as error:
            abort(404, description=str(error))
        except (ValueError, KeyError, TypeError) as error:
            abort(400, description=str(error))
        audit("Edited plugin " + pid + " " + operation + " " + store.dumps({"paths": data.get("paths", [path]), "destination": data.get("target", data.get("destination"))}))
        current_permissions = requested_permissions(entries)
        if current_permissions != previous_permissions:
            audit(
                "Changed plugin permissions "
                + pid
                + ": "
                + store.dumps(previous_permissions)
                + " -> "
                + store.dumps(current_permissions)
            )
        checked = store.static_validation(entries)
        return {
            "revision": revision + 1,
            "fingerprint": store.fingerprint(entries),
            "changes": changes,
            "validation": {
                "valid": checked["valid"],
                "diagnostics": checked["diagnostics"],
            },
        }

    @app.post("/developer/workspace/plugins/<pid>/static-validation")
    def developer_plugin_validate(pid):
        owned(pid, "plugins:validate")
        entries = store.files(db(), pid)
        result = store.static_validation(entries)
        # Static checks do not grant publish eligibility; import/type validation requires the isolated worker.
        audit("Static validation of plugin " + pid + ": " + str(result["valid"]))
        return result

    @app.get("/developer/workspace/plugins/<pid>/export")
    def developer_plugin_export(pid):
        owned(pid)
        return send_file(
            io.BytesIO(store.archive(store.files(db(), pid))),
            mimetype="application/zip",
            as_attachment=True,
            download_name=pid + ".zip",
        )

    @app.post("/developer/workspace/plugins/<pid>/delete")
    def developer_plugin_delete(pid):
        row = owned(pid, "plugins:delete")
        data = payload()
        if pid in app.config.get("PROTECTED_PLUGIN_IDS", ()):
            abort(403, description="Protected or built-in plugins cannot be deleted.")
        from pathlib import Path
        from plugin_discovery import retire_package
        finish = None
        try:
            with db():
                changed = db().execute(
                    "UPDATE developer_plugins SET deleted=1,enabled=0 WHERE id=? AND revision=? AND deleted=0",
                    (pid, data.get("revision")),
                )
                if changed.rowcount != 1:
                    abort(409, description="The plugin changed; refresh before deleting.")
                if row["source_location"]:
                    root = (app.config.get("PLUGINS_DIR")
                            or __import__("os").environ.get("MARE_PLUGINS_DIR")
                            or Path(app.root_path) / "plugins")
                    finish = retire_package(root, row["source_location"], pid)
        except (OSError, ValueError, TypeError) as error:
            if finish:
                finish(rollback=True)
            abort(409, description="Unable to remove installed package: " + str(error))
        except BaseException:
            if finish:
                finish(rollback=True)
            raise
        if finish:
            finish()
        # Existing executions use immutable snapshots; retain grants, history and audit.
        audit("Deleted plugin registration " + row["id"])
        return {"deleted": True, "recoverable": True}

    @app.get("/developer/workspace/plugins/<pid>/history")
    def developer_plugin_history(pid):
        permitted("plugins:read")
        # History remains accessible to its initiating owner after draft deletion.
        rows = db().execute(
            """SELECT e.id,e.plugin_id,e.plugin_version,e.owner_uuid,e.case_id,e.mode,e.status,e.started_at,e.ended_at,e.duration,
            u.username AS initiating_user,
            CASE WHEN e.status IN ('Failed','Timed out','Output limit exceeded')
                THEN substr(json_extract(e.details,'$.stderr'),-1000) ELSE NULL END AS diagnostic_tail
            FROM developer_executions e LEFT JOIN users u ON u.user_uuid=e.owner_uuid
            WHERE e.plugin_id=? AND e.owner_uuid=? ORDER BY e.started_at DESC LIMIT 100""",
            (pid, g.user["user_uuid"]),
        )
        executions = []
        for row in rows:
            item = dict(row)
            tail = item.pop("diagnostic_tail")
            lines = [line.strip() for line in (tail or "").splitlines() if line.strip()]
            item["error_summary"] = (lines[-1][:300] if lines else item["status"]) if item["status"] in ("Failed","Timed out","Output limit exceeded") else None
            executions.append(item)
        return {"executions": executions}
