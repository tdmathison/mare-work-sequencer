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
        return {
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

    @app.get("/developer/workspace/plugins")
    def developer_plugin_list():
        permitted("plugins:read")
        return {
            "plugins": [
                record(row)
                for row in db().execute(
                    "SELECT * FROM developer_plugins WHERE owner_uuid=? AND deleted=0 ORDER BY name,id",
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
        result.update(
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
            path = store.safe_path(data["path"])
            operation = data.get("operation", "save")
            entries = store.files(db(), pid)
            previous_permissions = requested_permissions(entries)
            if operation == "delete":
                if path not in entries:
                    abort(404)
                entries = {
                    p: v
                    for p, v in entries.items()
                    if p != path and not p.startswith(path + "/")
                }
            elif operation == "rename":
                target = store.safe_path(data["target"])
                if path not in entries:
                    abort(404)
                moved = {
                    target + p[len(path) :]: v
                    for p, v in entries.items()
                    if p == path or p.startswith(path + "/")
                }
                retained = {
                    p: v
                    for p, v in entries.items()
                    if p != path and not p.startswith(path + "/")
                }
                if set(moved) & set(retained):
                    raise ValueError("The destination already exists.")
                entries = {**retained, **moved}
            elif operation in ("save", "create", "directory", "upload"):
                if operation != "save" and path in entries:
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
        except (ValueError, KeyError, TypeError) as error:
            abort(400, description=str(error))
        audit("Edited plugin " + pid + " " + operation + " " + path)
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
        return {"revision": revision + 1, "fingerprint": store.fingerprint(entries)}

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
        with db():
            changed = db().execute(
                "UPDATE developer_plugins SET deleted=1,enabled=0 WHERE id=? AND revision=?",
                (pid, data.get("revision")),
            )
            if changed.rowcount != 1:
                abort(409, description="The plugin changed; refresh before deleting.")
        audit("Deleted plugin registration " + row["id"])
        return {"deleted": True}

    @app.get("/developer/workspace/plugins/<pid>/history")
    def developer_plugin_history(pid):
        permitted("plugins:read")
        # History remains accessible to its initiating owner after draft deletion.
        return {
            "executions": [
                dict(r)
                for r in db().execute(
                    "SELECT id,plugin_id,plugin_version,owner_uuid,case_id,mode,status,started_at,ended_at,duration FROM developer_executions WHERE plugin_id=? AND owner_uuid=? ORDER BY started_at DESC LIMIT 100",
                    (pid, g.user["user_uuid"]),
                )
            ]
        }
