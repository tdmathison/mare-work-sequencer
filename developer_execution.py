"""Owner-bound immutable executions and language/debug session broker."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit, unquote
from flask import abort, g, request
from authorization import has_permission
from developer_worker.client import call, Unavailable
import plugin_store as store

LSP_METHODS = {
    "initialize",
    "initialized",
    "textDocument/didOpen",
    "textDocument/didChange",
    "textDocument/didClose",
    "textDocument/completion",
    "completionItem/resolve",
    "textDocument/hover",
    "textDocument/signatureHelp",
    "textDocument/definition",
    "textDocument/references",
    "textDocument/documentSymbol",
    "workspace/symbol",
    "shutdown",
    "exit",
}
DAP_COMMANDS = {
    "initialize",
    "launch",
    "configurationDone",
    "setBreakpoints",
    "setExceptionBreakpoints",
    "threads",
    "stackTrace",
    "scopes",
    "variables",
    "continue",
    "pause",
    "next",
    "stepIn",
    "stepOut",
    "disconnect",
    "terminate",
    "exceptionInfo",
}


def protocol_message(kind, value):
    if not isinstance(value, dict) or len(json.dumps(value)) > 256 * 1024:
        raise ValueError("Invalid development message.")
    if kind == "language":
        if "method" not in value:
            result = value.get("result")
            if (
                set(value) - {"jsonrpc", "id", "result"}
                or "id" not in value
                or not (
                    result is None
                    or isinstance(result, list)
                    and len(result) <= 30
                    and all(item is None for item in result)
                )
            ):
                raise ValueError(
                    "Only empty language-server configuration replies are accepted."
                )
            return value
        if value.get("method") not in LSP_METHODS:
            raise ValueError("Unsupported language request.")

        def paths(node):
            if isinstance(node, dict):
                for key, item in node.items():
                    if key in ("uri", "rootUri") and item is not None:
                        if not isinstance(item, str):
                            raise ValueError("Language paths must be inside /work.")
                        location = urlsplit(item)
                        path = unquote(location.path, errors="strict")
                        if (
                            location.scheme != "file"
                            or location.netloc
                            or location.query
                            or location.fragment
                            or not (path == "/work" or path.startswith("/work/"))
                        ):
                            raise ValueError("Language paths must be inside /work.")
                        if path != "/work":
                            store.safe_path(path[6:])
                    if (
                        key in ("rootPath", "initializationOptions", "processId")
                        and item is not None
                    ):
                        raise ValueError(
                            "Client process and arbitrary language configuration are forbidden."
                        )
                    paths(item)
            elif isinstance(node, list):
                for item in node:
                    paths(item)

        paths(value.get("params", {}))
        if value["method"] == "initialize":
            value = {
                **value,
                "params": {
                    "processId": None,
                    "rootUri": "file:///work",
                    "capabilities": value.get("params", {}).get("capabilities", {}),
                    "workspaceFolders": [{"uri": "file:///work", "name": "Plugin"}],
                },
            }
    elif kind == "debug":
        if value.get("type") != "request" or value.get("command") not in DAP_COMMANDS:
            raise ValueError(
                "Unsupported debug request; attach and expression evaluation are forbidden."
            )
        command = value["command"]
        args = value.get("arguments", {})
        if not isinstance(args, dict):
            raise ValueError("Invalid debug arguments.")
        if command == "launch":
            value = {
                **value,
                "arguments": {
                    "program": "/opt/mws/debug_launcher.py",
                    "cwd": "/work",
                    "console": "internalConsole",
                    "justMyCode": True,
                    "stopOnEntry": False,
                    "redirectOutput": True,
                    "env": {},
                },
            }
        elif command == "setBreakpoints":
            source = args.get("source", {})
            path = source.get("path", "")
            if (
                not isinstance(path, str)
                or not path.startswith("/work/")
                or ".." in path
                or "\\" in path
            ):
                raise ValueError("Breakpoints must be inside the plugin workspace.")
            points = args.get("breakpoints", [])
            if (
                not isinstance(points, list)
                or len(points) > 200
                or any(
                    not isinstance(p, dict)
                    or type(p.get("line")) is not int
                    or not 1 <= p["line"] <= 100000
                    or set(p) - {"line"}
                    for p in points
                )
            ):
                raise ValueError("Only bounded line breakpoints are supported.")
            value = {
                **value,
                "arguments": {"source": {"path": path}, "breakpoints": points},
            }
        elif command in (
            "variables",
            "scopes",
            "stackTrace",
            "continue",
            "pause",
            "next",
            "stepIn",
            "stepOut",
            "exceptionInfo",
        ):
            allowed = {
                "variablesReference",
                "frameId",
                "threadId",
                "startFrame",
                "levels",
                "start",
                "count",
                "singleThread",
                "granularity",
            }
            if set(args) - allowed:
                raise ValueError("Unsupported debug arguments.")
        elif command == "initialize":
            value = {
                **value,
                "arguments": {
                    "clientID": "mws",
                    "adapterID": "python",
                    "linesStartAt1": True,
                    "columnsStartAt1": True,
                    "pathFormat": "path",
                    "supportsVariableType": True,
                },
            }
        elif command == "disconnect":
            value = {**value, "arguments": {"terminateDebuggee": True}}
    else:
        raise ValueError("Invalid development session kind.")
    return value


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
    def developer_expired_sessions():
        if not request.path.startswith("/developer/workspace/") or not getattr(
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
            + {"run": "execute", "language": "edit"}.get(row["mode"], row["mode"]),
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
                    store.dumps({"output": result.get("output", "")[: 256 * 1024]}),
                    store.now() if finished else None,
                    row["id"],
                ),
            )
            if finished:
                db().execute(
                    "UPDATE api_tokens SET revoked=? WHERE id=?",
                    (store.now(), row["grant_id"]),
                )
                if row["mode"] in ("validate", "test") and result["status"] not in (
                    "Canceled",
                    "Expired",
                ):
                    current = store.fingerprint(store.files(db(), row["plugin_id"]))
                    if current == row["fingerprint"]:
                        db().execute(
                            "UPDATE developer_plugins SET development=? WHERE id=?",
                            (
                                (
                                    (
                                        "Validated"
                                        if row["mode"] == "validate"
                                        else "Tested"
                                    )
                                    if result["status"] == "Succeeded"
                                    else "Failed"
                                ),
                                row["plugin_id"],
                            ),
                        )
        return {**result, "id": row["id"]}

    def start(pid, mode):
        row = owned(pid, {"run": "execute", "language": "edit"}.get(mode, mode))
        data = body()
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
        else:
            checked = store.static_validation(entries)
            if not checked["valid"]:
                return checked, 400
            value = checked["manifest"]
            raw = store.archive(entries)
            fingerprint = store.fingerprint(entries)
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
                require=mode in ("validate", "test", "run", "debug"),
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
        permissions = (
            requested
            if mode == "run"
            else [
                p
                for p in requested
                if p in store.READ_PERMISSIONS or p == "cases:assets" and artifact
            ]
        )
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
                            "Developer execution " + eid,
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
                    "token": token,
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

    for mode in ("validate", "test", "run", "debug", "language"):

        def action(pid, mode=mode):
            return start(pid, mode)

        app.add_url_rule(
            "/developer/workspace/plugins/<pid>/" + mode,
            "developer_execute_" + mode,
            action,
            methods=["POST"],
        )

    @app.get("/developer/workspace/cases/<int:cid>/artifacts")
    def developer_case_artifacts(cid):
        if not all(
            has_permission(g.user, p, db())
            for p in ("plugins:read", "cases:read", "cases:assets")
        ):
            abort(403)
        from app import case, package, safe_path, is_backup

        case(cid)
        root = package(cid)
        return {
            "artifacts": [
                {"path": path.relative_to(root).as_posix(), "size": path.stat().st_size}
                for path in sorted(root.rglob("*"))
                if path.is_file()
                and not path.is_symlink()
                and not is_backup(path.relative_to(root).as_posix())
                and path.stat().st_size <= 8 * 1024 * 1024
            ]
        }

    @app.get("/developer/workspace/executions/<eid>")
    def developer_execution_poll(eid):
        row = execution(eid)
        if row["status"] not in ("Starting", "Running"):
            return {
                "id": eid,
                "status": row["status"],
                "duration": row["duration"],
                **json.loads(row["details"]),
                "messages": [],
            }
        return update(row, worker("GET", "/jobs/" + row["worker_id"]))

    @app.post("/developer/workspace/executions/<eid>/cancel")
    def developer_execution_cancel(eid):
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

    @app.post("/developer/workspace/executions/<eid>/rpc")
    def developer_execution_rpc(eid):
        row = execution(eid)
        try:
            value = protocol_message(row["mode"], body())
        except (ValueError, TypeError, RecursionError) as error:
            abort(400, description=str(error))
        return update(row, worker("POST", "/jobs/" + row["worker_id"] + "/rpc", value))

    @app.post("/developer/workspace/plugins/<pid>/publish")
    def developer_plugin_publish(pid):
        row = owned(pid, "publish")
        data = body()
        entries = store.files(db(), pid)
        checked = store.static_validation(entries)
        if not checked["valid"]:
            return checked, 400
        value = checked["manifest"]
        if any(
            not has_permission(g.user, p, db()) for p in value.get("permissions", [])
        ):
            abort(403, description="You do not hold all requested plugin permissions.")
        from developer_configuration import resolved

        try:
            resolved(row, value, app.config["SECRET_KEY"], require=True)
        except ValueError as error:
            abort(400, description=str(error))
        fingerprint = store.fingerprint(entries)
        if value["id"] != pid:
            abort(400, description="Manifest identifier does not match registration.")
        if data.get("revision") != row["revision"]:
            abort(409, description="Draft changed; refresh before publishing.")
        for mode in ("validate", "test"):
            if (
                not db()
                .execute(
                    "SELECT 1 FROM developer_executions WHERE plugin_id=? AND fingerprint=? AND mode=? AND status='Succeeded'",
                    (pid, fingerprint, mode),
                )
                .fetchone()
            ):
                abort(
                    409,
                    description="The current snapshot must pass isolated validation and testing before publication.",
                )
        try:
            with db():
                # Acquire write lock and recheck revision, so concurrent draft edits cannot race publication.
                changed = db().execute(
                    "UPDATE developer_plugins SET development='Published',published_version=? WHERE id=? AND revision=?",
                    (value["version"], pid, row["revision"]),
                )
                if changed.rowcount != 1:
                    abort(409)
                db().execute(
                    "INSERT INTO developer_versions VALUES(?,?,?,?,?,?,?)",
                    (
                        pid,
                        value["version"],
                        fingerprint,
                        store.archive(entries),
                        store.dumps(value),
                        g.user["user_uuid"],
                        store.now(),
                    ),
                )
        except sqlite3.IntegrityError:
            abort(
                409,
                description="That version is immutable; increment the manifest version.",
            )
        audit("Published plugin " + pid + " " + value["version"])
        return {"version": value["version"]}

    @app.post("/developer/workspace/plugins/<pid>/enable")
    def developer_plugin_enable(pid):
        row = owned(pid, "versions")
        data = body()
        if type(data.get("enabled")) is not bool:
            abort(400)
        if data["enabled"] and not row["published_version"]:
            abort(409, description="Publish a validated and tested version first.")
        with db():
            db().execute(
                "UPDATE developer_plugins SET enabled=? WHERE id=?",
                (data["enabled"], pid),
            )
        audit(("Enabled" if data["enabled"] else "Disabled") + " plugin " + pid)
        return {"enabled": data["enabled"]}

    @app.post("/developer/workspace/plugins/<pid>/rollback")
    def developer_plugin_rollback(pid):
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
