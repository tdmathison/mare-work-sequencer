"""Owner-scoped installed folder-plugin management; no source editing API."""

import json
import sqlite3
from flask import abort, g, request
from authorization import has_permission
import plugin_store as store


def register_plugins(app, db, audit):

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
        db().execute("INSERT OR REPLACE INTO plugin_packages VALUES(?,?)", (pid,store.archive(entries)))

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

    @app.get("/plugins/registry")
    def plugin_list():
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
                    "install",
                    "execute",
                    "versions",
                    "delete",
                    "configure",
                )
                if has_permission(g.user, "plugins:" + p, db())
            ],
            "data_permissions": sorted(store.DATA_PERMISSIONS),
        }

    @app.post("/plugins/discovery")
    def plugin_discovery():
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
                    "SELECT * FROM developer_plugins WHERE id=?",
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
                elif has_permission(g.user,"plugins:install",db()):
                    fingerprint = store.fingerprint(entries)
                    snapshot = db().execute("SELECT fingerprint FROM developer_versions WHERE plugin_id=? AND version=?",(value['id'],value['version'])).fetchone()
                    if existing['source_location'] != location:
                        invalid.append(dict(package=location,error="Identifier belongs to another installed package; no files were overwritten."))
                    elif snapshot and snapshot[0] != fingerprint:
                        invalid.append(dict(package=location,error="Installed files changed without a version increment. Increment plugin.json version and rescan."))
                    elif not snapshot:
                        try:
                            with db():
                                db().execute(
                                    "INSERT INTO developer_versions VALUES(?,?,?,?,?,?,?)",
                                    (value['id'], value['version'], fingerprint,
                                     store.archive(entries), store.dumps(value),
                                     g.user['user_uuid'], store.now()),
                                )
                                write_files(value['id'], entries)
                                db().execute(
                                    "UPDATE developer_plugins SET name=?,development='Installed',published_version=?,revision=revision+1,updated_at=? WHERE id=?",
                                    (value['name'],value['version'],store.now(),value['id']),
                                )
                        except sqlite3.IntegrityError:
                            invalid.append(dict(package=location,error="Version registered concurrently; refresh. No snapshot was overwritten."))
                            continue
                        registered.append(value['id'])
                        audit("Reloaded installed plugin " + value['id'] + " " + value['version'])
                continue
            if not has_permission(g.user, "plugins:install", db()):
                invalid.append(
                    {
                        "package": location,
                        "error": "Registration requires plugins:install permission.",
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
                    db().execute("INSERT INTO developer_versions VALUES(?,?,?,?,?,?,?)",(value['id'],value['version'],store.fingerprint(entries),store.archive(entries),store.dumps(value),g.user['user_uuid'],timestamp))
                    db().execute("UPDATE developer_plugins SET development='Installed',published_version=? WHERE id=?",(value['version'],value['id']))
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


    @app.get("/plugins/registry/<pid>")
    def plugin_detail(pid):
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


    @app.post("/plugins/registry/<pid>/delete")
    def plugin_delete(pid):
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

    @app.get("/plugins/registry/<pid>/history")
    def plugin_history(pid):
        permitted("plugins:read")
        # History remains accessible to its initiating owner after package deletion.
        rows = db().execute(
            """SELECT e.id,e.plugin_id,e.plugin_version,e.owner_uuid,e.case_id,e.mode,e.status,e.started_at,e.ended_at,e.duration,
            u.username AS initiating_user,
            CASE WHEN e.status IN ('Failed','Timed out','Output limit exceeded')
                THEN substr(json_extract(e.details,'$.stderr'),-1000) ELSE NULL END AS diagnostic_tail
            FROM plugin_executions e LEFT JOIN users u ON u.user_uuid=e.owner_uuid
            WHERE e.plugin_id=? AND e.owner_uuid=? AND e.mode='run' ORDER BY e.started_at DESC LIMIT 100""",
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
