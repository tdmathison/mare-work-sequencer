"""Owner-bound execution of installed, enabled immutable plugin packages."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import sqlite3
import uuid
from flask import abort, g, request
from authorization import has_permission
from plugin_runtime.client import call, Unavailable
import plugin_store as store

def enforce_grant(connection):
    """Called after existing bearer authentication and before any REST handler."""
    grant = connection.execute(
        "SELECT * FROM developer_grants WHERE token_id=?", (g.api_token_id,)
    ).fetchone()
    if grant is None:
        return
    g.plugin_permissions = frozenset(json.loads(grant["permissions"]))
    path = request.path
    case_id = (request.view_args or {}).get("case_id")
    asset = (request.view_args or {}).get("relative_path")
    if asset is not None:
        if (
            case_id != grant["case_id"]
            or not path.startswith(f"/api/v1/cases/{case_id}/assets/")
            or request.method != "GET"
            or not grant["artifact"]
            or asset != grant["artifact"]
        ):
            abort(
                403,
                description="Only the explicitly selected artifact is available to this execution.",
            )
        return
    if (
        case_id != grant["case_id"]
        or not re.fullmatch(
            r"/api/v1/cases/\d+(?:/(?:indicators|references|report(?:/mappings)?|notes(?:/\d+)?|tasks(?:/\d+)?|readiness))?",
            path,
        )
        or request.method == "DELETE"
    ):
        abort(
            403,
            description="Plugin grants are limited to explicitly authorized data on the selected case.",
        )


def register_execution(app, db, audit):
    @app.before_request
    def plugin_expired_runs():
        if not request.path.startswith("/plugins/") or not getattr(
            g, "user", None
        ):
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat(
            timespec="seconds"
        )
        with db():
            db().execute(
                "UPDATE api_tokens SET revoked=? WHERE id IN (SELECT grant_id FROM developer_executions WHERE status IN ('Starting','Running') AND started_at<?)",
                (store.now(), cutoff),
            )
            db().execute(
                "UPDATE developer_executions SET status='Expired',ended_at=? WHERE status IN ('Starting','Running') AND started_at<?",
                (store.now(), cutoff),
            )

    def owned(pid, permission):
        if not has_permission(g.user, "plugins:read", db()) or not has_permission(
            g.user, "plugins:" + permission, db()
        ):
            abort(403)
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

    def body():
        try:
            value = json.loads(request.form.get("payload", "{}"))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError):
            abort(400, description="Expected a JSON payload.")

    def worker(method, path, data=None):
        try:
            return call(method, path, data)
        except Unavailable as error:
            abort(503, description=str(error))

    def execution(eid):
        row = (
            db()
            .execute(
                "SELECT * FROM developer_executions WHERE id=? AND owner_uuid=?",
                (eid, g.user["user_uuid"]),
            )
            .fetchone()
        )
        if row is None:
            abort(404)
        if not has_permission(g.user, "plugins:read", db()) or not has_permission(
            g.user,
            "plugins:"
            + "execute",
            db(),
        ):
            abort(403)
        return row

    def update(row, result):
        finished = result["status"] not in ("Starting", "Running")
        with db():
            db().execute(
                "UPDATE developer_executions SET status=?,duration=?,details=?,ended_at=? WHERE id=?",
                (
                    result["status"],
                    result.get("duration"),
                    store.dumps(
                        {
                            key: result[key]
                            for key in ("output", "stdout", "stderr", "events", "exit_code")
                            if key in result
                        }
                    ),
                    store.now() if finished else None,
                    row["id"],
                ),
            )
            if finished:
                db().execute(
                    "UPDATE api_tokens SET revoked=? WHERE id=?",
                    (store.now(), row["grant_id"]),
                )
        return {**result, "id": row["id"]}

    def start(pid):
        mode = "run"
        row = owned(pid, "execute")
        data = body()
        if set(data) - {"version", "case_id", "artifact", "inputs"}:
            abort(400, description="Unsupported operational execution fields.")
        worker("GET", "/health")
        entries = store.files(db(), pid)
        version = data.get("version")
        if mode == "run":
            if not row["enabled"] or not row["published_version"]:
                abort(409, description="Select an enabled published plugin.")
            version = version or row["published_version"]
        if version:
            if not isinstance(version, str):
                abort(400, description="Invalid version.")
            snapshot = (
                db()
                .execute(
                    "SELECT * FROM developer_versions WHERE plugin_id=? AND version=?",
                    (pid, version),
                )
                .fetchone()
            )
            if not snapshot:
                abort(404)
            raw = snapshot["archive"]
            fingerprint = snapshot["fingerprint"]
            value = json.loads(snapshot["manifest"])
        if value["id"] != pid:
            abort(
                400, description="The manifest identifier must match its registration."
            )
        cid = data.get("case_id")
        if cid is not None:
            if (
                type(cid) is not int
                or not db()
                .execute("SELECT id FROM cases WHERE id=?", (cid,))
                .fetchone()
            ):
                abort(404)
            if not has_permission(g.user, "cases:read", db()):
                abort(403)
        artifact = data.get("artifact") or None
        if artifact:
            if (
                cid is None
                or not isinstance(artifact, str)
                or "cases:assets" not in value.get("permissions", [])
                or not has_permission(g.user, "cases:assets", db())
            ):
                abort(403)
            from app import safe_path

            target = safe_path(cid, artifact)
            if (
                not target.is_file()
                or target.is_symlink()
                or target.stat().st_size > 8 * 1024 * 1024
            ):
                abort(
                    400,
                    description="Select an existing authorized artifact of at most 8 MiB.",
                )
        inputs = data.get("inputs", {})
        if not isinstance(inputs, dict) or len(store.dumps(inputs)) > 16000:
            abort(400, description="Inputs must be an object under 16 KB.")
        from developer_configuration import resolved

        try:
            configuration, secrets_config = resolved(
                row,
                value,
                app.config["SECRET_KEY"],
                require=True,
            )
        except ValueError as error:
            abort(400, description=str(error))
        if (
            mode == "run"
            and cid is not None
            and db()
            .execute(
                "SELECT 1 FROM developer_executions WHERE case_id=? AND mode='run' AND status IN ('Starting','Running')",
                (cid,),
            )
            .fetchone()
        ):
            abort(
                409, description="Another plugin is already running against this case."
            )
        requested = value.get("permissions", [])
        if any(not has_permission(g.user, p, db()) for p in requested):
            abort(403, description="You do not hold all requested plugin permissions.")
        permissions = requested
        eid = uuid.uuid4().hex
        token = secrets.token_urlsafe(48)
        timestamp = store.now()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=11)).isoformat(
            timespec="seconds"
        )
        try:
            with db():
                tid = (
                    db()
                    .execute(
                        "INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created,expires) VALUES(?,?,?,?,?,?)",
                        (
                            g.user["id"],
                            "Plugin execution " + eid,
                            hashlib.sha256(token.encode()).hexdigest(),
                            token[:8],
                            timestamp,
                            expires,
                        ),
                    )
                    .lastrowid
                )
                db().execute(
                    "INSERT INTO developer_grants(token_id,execution_id,permissions,case_id,artifact) VALUES(?,?,?,?,?)",
                    (tid, eid, store.dumps(permissions), cid, artifact),
                )
                db().execute(
                    "INSERT INTO developer_executions(id,plugin_id,plugin_version,fingerprint,owner_uuid,case_id,mode,status,started_at,snapshot,grant_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        pid,
                        value["version"],
                        fingerprint,
                        g.user["user_uuid"],
                        cid,
                        mode,
                        "Starting",
                        timestamp,
                        raw,
                        tid,
                    ),
                )
        except sqlite3.IntegrityError:
            abort(
                409,
                description="Another plugin started against this case; retry after it finishes.",
            )

        try:
            result = call(
                "POST",
                "/jobs",
                {
                    "mode": mode,
                    "archive": base64.b64encode(raw).decode(),
                    "token": token if permissions else "",
                    "secrets": secrets_config,
                    "context": {
                        "case_id": cid,
                        "artifact": artifact,
                        "inputs": inputs,
                        "configuration": configuration,
                    },
                },
            )
        except Unavailable as error:
            with db():
                db().execute(
                    "UPDATE api_tokens SET revoked=? WHERE id=?", (store.now(), tid)
                )
                db().execute(
                    "UPDATE developer_executions SET status='Failed',ended_at=? WHERE id=?",
                    (store.now(), eid),
                )
            abort(503, description=str(error))
        with db():
            db().execute(
                "UPDATE developer_executions SET worker_id=?,status=? WHERE id=?",
                (result["id"], result["status"], eid),
            )
        audit(
            "Plugin "
            + mode
            + " "
            + pid
            + " version "
            + value["version"]
            + " execution "
            + eid
        )
        return {**result, "id": eid}, 202

    @app.post("/plugins/registry/<pid>/run")
    def plugin_execute(pid):
        return start(pid)

    @app.get("/plugins/executions/<eid>")
    def plugin_execution_poll(eid):
        row = execution(eid)
        if row["status"] not in ("Starting", "Running"):
            return {
                "id": eid,
                "status": row["status"],
                "duration": row["duration"],
                **json.loads(row["details"]),
            }
        return update(row, worker("GET", "/jobs/" + row["worker_id"]))

    @app.post("/plugins/executions/<eid>/cancel")
    def plugin_execution_cancel(eid):
        row = execution(eid)
        # Revoke API capability even if the worker is unreachable.
        with db():
            db().execute(
                "UPDATE api_tokens SET revoked=? WHERE id=?",
                (store.now(), row["grant_id"]),
            )
        result = worker("POST", "/jobs/" + row["worker_id"] + "/cancel", {})
        audit("Canceled plugin execution " + eid)
        return update(row, result)


    @app.post("/plugins/registry/<pid>/enable")
    def plugin_enable(pid):
        row = owned(pid, "versions")
        data = body()
        if type(data.get("enabled")) is not bool:
            abort(400)
        if data["enabled"]:
            checked = store.static_validation(store.files(db(), pid))
            if not checked["valid"] or checked["manifest"]["id"] != pid:
                abort(
                    409,
                    description="Correct the invalid manifest/package before enabling. The active installed snapshot was not reloaded.",
                )
        if data["enabled"] and not row["published_version"]:
            abort(409, description="Install a valid package first.")
        with db():
            db().execute(
                "UPDATE developer_plugins SET enabled=? WHERE id=?",
                (data["enabled"], pid),
            )
        audit(("Enabled" if data["enabled"] else "Disabled") + " plugin " + pid)
        return {"enabled": data["enabled"]}

    @app.post("/plugins/registry/<pid>/rollback")
    def plugin_rollback(pid):
        owned(pid, "versions")
        data = body()
        version = data.get("version")
        if (
            not db()
            .execute(
                "SELECT 1 FROM developer_versions WHERE plugin_id=? AND version=?",
                (pid, version),
            )
            .fetchone()
        ):
            abort(404)
        with db():
            db().execute(
                "UPDATE developer_plugins SET published_version=? WHERE id=?",
                (version, pid),
            )
        audit("Rolled back plugin " + pid + " to " + version)
        return {"version": version}
