"""Authenticated editor-first Snort workspace and existing-case integration."""

import io
import json
import os
from pathlib import Path
import re
import tempfile
import sqlite3
from flask import abort, g, request, render_template, make_response, send_file
from authorization import has_permission
from signature_files import (
    LIMIT,
    Conflict,
    analyze,
    document,
    selected_source,
    save_selected,
    safe_signature,
    persist,
    version,
)
from snort_engine import Engine, capture_format


def register_snort(app, db, require_tool, root, case, ensure_package, audit):
    for key, default, minimum, maximum in [
        ("TIMEOUT", 30, 1, 60),
        ("UPLOAD_LIMIT", 20 * 1024**2, 1024, 40 * 1024**2),
        ("CONCURRENCY", 2, 1, 4),
        ("JOB_TTL", 3600, 60, 86400),
    ]:
        value = int(os.environ.get("MARE_SNORT_" + key, default))
        if not minimum <= value <= maximum:
            raise ValueError("Invalid MARE_SNORT_" + key)
        app.config["SNORT_" + key] = value
    for key in ("EXECUTABLE", "PROFILE", "RUNNER"):
        app.config["SNORT_" + key] = os.environ.get("MARE_SNORT_" + key, "")
    app.config["SNORT_PCAPNG"] = os.environ.get("MARE_SNORT_PCAPNG") == "1"
    engine = Engine(app, root)
    app.extensions["snort_engine"] = engine
    engine.cleanup()
    drafts = Path(root) / "snort-drafts"
    drafts.mkdir(mode=0o700, exist_ok=True)

    def guard():
        require_tool(app, db, "snort-rule-builder")

    def response(value, status=200):
        r = make_response(value, status)
        r.headers["Cache-Control"] = "no-store"
        return r

    def source():
        try:
            value = json.loads(request.form.get("source_json", '""'))
        except (ValueError, RecursionError) as error:
            raise ValueError("Source must be a JSON-encoded string.") from error
        if not isinstance(value, str) or len(value.encode()) > LIMIT or "\x00" in value:
            raise ValueError("Rule source exceeds limits or contains NUL.")
        return value

    def access(cid, write=False):
        guard()
        for p in ("cases:read", "cases:assets", *(("cases:update",) if write else ())):
            if not has_permission(g.user, p, db()):
                abort(403)
        c = case(cid)
        if (
            write
            and db()
            .execute(
                "SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')",
                (cid,),
            )
            .fetchone()
        ):
            abort(409, description="Wait for report generation before editing assets.")
        return c

    def package(cid):
        return Path(root) / "cases" / str(cid) / "mip"

    def draft_path():
        return drafts / (g.user["user_uuid"] + ".json")

    @app.get("/tools/snort-rule-builder/app/")
    def tools_snort():
        guard()
        r = make_response(render_template("snort_builder.html"))
        r.headers.update(
            {
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
            }
        )
        return r

    @app.get("/tools/snort-rule-builder/state")
    def snort_state():
        guard()
        engine.cleanup()
        draft = None
        try:
            draft = json.loads(draft_path().read_text())
        except (OSError, ValueError):
            pass
        cases = []
        if all(has_permission(g.user, p, db()) for p in ("cases:read", "cases:assets")):
            cases = [
                dict(row)
                for row in db().execute(
                    "SELECT id,number,name,stage,owner_required FROM cases ORDER BY id DESC"
                )
            ]
        return response(dict(engine=engine.discover(), draft=draft, cases=cases))

    @app.post("/tools/snort-rule-builder/draft")
    def snort_draft():
        guard()
        try:
            payload = dict(
                source=source(), context=json.loads(request.form.get("context", "null"))
            )
            if len(json.dumps(payload)) > 400000:
                raise ValueError("Draft context exceeds limits.")
            fd, name = tempfile.mkstemp(dir=drafts, prefix=".draft-")
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(payload, stream)
                os.replace(name, draft_path())
            finally:
                Path(name).unlink(missing_ok=True)
            return response(dict(saved=True))
        except (ValueError, TypeError, RecursionError) as error:
            return response(dict(error=str(error)), 400)

    @app.post("/tools/snort-rule-builder/download")
    def snort_download():
        guard()
        try:
            return send_file(
                io.BytesIO(source().encode()),
                as_attachment=True,
                download_name="analyst.rules",
                mimetype="text/plain",
            )
        except (ValueError, TypeError) as error:
            return response(dict(error=str(error)), 400)

    @app.get("/cases/<int:cid>/snort-signatures")
    def snort_inventory(cid):
        c = access(cid)
        files = []
        sids = {}
        for p in sorted((package(cid) / "signatures").rglob("*")):
            if p.suffix.lower() != ".rules" or not p.is_file():
                continue
            relative = p.relative_to(package(cid) / "signatures").as_posix()
            try:
                p = safe_signature(package(cid), relative)
                if p.stat().st_size > LIMIT:
                    files.append(
                        dict(
                            path=relative, count=0, reason="File exceeds editor limit."
                        )
                    )
                    continue
                raw = p.read_bytes()
                info = document(raw, relative)
                ids = [
                    r["sid"]
                    for r in info["rules"]
                    if re.fullmatch(r"\d{1,10}", r["sid"])
                ]
                for sid in ids:
                    sids.setdefault(str(int(sid)), []).append(relative)
                files.append(
                    dict(
                        path=relative,
                        count=info["count"],
                        reason=info["reason"],
                        version=version(raw),
                    )
                )
            except (ValueError, OSError):
                continue
        editable = (
            has_permission(g.user, "cases:update", db())
            and c["stage"] in (1, 2)
            and (not c["owner_required"] or c["owner_active"])
        )
        return response(
            dict(
                files=files,
                editable=bool(editable),
                duplicate_sids={k: v for k, v in sids.items() if len(v) > 1},
                sid_index=sids,
            )
        )

    @app.get("/cases/<int:cid>/snort-signature")
    def snort_open(cid):
        access(cid)
        try:
            p = safe_signature(package(cid), request.args.get("path", ""))
            if not p.is_file():
                abort(404)
            if p.stat().st_size > LIMIT:
                raise ValueError("File exceeds editor limit.")
            raw = p.read_bytes()
            return response(
                dict(
                    source=raw.decode("utf-8"),
                    document=document(raw, request.args["path"]),
                    version=version(raw),
                    path=request.args["path"],
                )
            )
        except (ValueError, OSError) as error:
            return response(dict(error=str(error)), 400)

    @app.post("/cases/<int:cid>/snort-rule")
    def snort_save(cid):
        access(cid, True)
        name = request.form.get("filename", "")
        try:
            raw = source().encode()
            selected_source(raw)
            if request.form.get("operation") == "replace":
                result = save_selected(
                    ensure_package(cid),
                    name,
                    raw,
                    db(),
                    cid,
                    request.form.get("version"),
                    int(request.form.get("start", "-1")),
                    int(request.form.get("end", "-1")),
                )
            else:
                if request.form.get("origin_path"):
                    origin = safe_signature(
                        package(int(request.form.get("origin_cid", "0"))),
                        request.form["origin_path"],
                    )
                    destination = safe_signature(package(cid), name)
                    if origin == destination or (
                        origin.exists()
                        and destination.exists()
                        and os.path.samefile(origin, destination)
                    ):
                        raise ValueError(
                            "Save As requires a separate destination; use Save to replace only the selected signature."
                        )
                result = persist(
                    ensure_package(cid),
                    name,
                    raw,
                    db(),
                    cid,
                    expected=request.form.get("version") or None,
                )
                info = document(raw)
                result.update(document=info, selected=info["rules"][0])
            audit(
                f"Saved Snort signature case {cid}: {name} (operation={request.form.get('operation','save-as')}, range={request.form.get('start','new')}:{request.form.get('end','new')})"
            )
            db().commit()
            return response(result)
        except (ValueError, OSError, sqlite3.Error) as error:
            audit(f"Snort save failed case {cid}: {name}: {error}")
            return response(
                dict(
                    error=str(error),
                    conflict=isinstance(error, Conflict),
                    current_version=getattr(error, "current", None),
                ),
                409 if isinstance(error, Conflict) else 400,
            )

    @app.post("/cases/<int:cid>/snort-signatures/normalize")
    def snort_normalize(cid):
        access(cid)
        return response(
            dict(
                error="Automatic splitting is disabled. Open the file and select a signature."
            ),
            410,
        )

    @app.post("/tools/snort-rule-builder/jobs")
    def snort_jobs():
        guard()
        engine.cleanup()
        info = engine.discover()
        if not info["available"]:
            return response(dict(error=info["message"], status=info["status"]), 503)
        try:
            captures = []
            if request.form.get("kind") == "pcap":
                for field in ("target", "baseline"):
                    f = request.files.get(field)
                    if not f:
                        if field == "target":
                            raise ValueError("Choose a target capture.")
                        continue
                    raw = f.read(app.config["SNORT_UPLOAD_LIMIT"] + 1)
                    if len(raw) > app.config["SNORT_UPLOAD_LIMIT"]:
                        raise ValueError("Capture exceeds upload limit.")
                    capture_format(raw, app.config["SNORT_PCAPNG"])
                    captures.append((field, raw))
            elif request.form.get("kind") != "validate":
                raise ValueError("Choose validation or offline PCAP processing.")
            return response(engine.submit(g.user["user_uuid"], source(), captures), 202)
        except (ValueError, OSError, TypeError) as error:
            return response(dict(error=str(error)), 400)

    def owned(job):
        guard()
        if not re.fullmatch("[a-f0-9]{32}", job):
            abort(404)
        directory = engine.root / job
        try:
            state = engine.read(directory)
        except (OSError, ValueError):
            abort(404)
        if state.get("user") != g.user["user_uuid"]:
            abort(404)
        return directory, state

    @app.get("/tools/snort-rule-builder/jobs/<job>")
    def snort_job(job):
        engine.cleanup()
        _, state = owned(job)
        state.pop("user", None)
        return response(state)

    @app.post("/tools/snort-rule-builder/jobs/<job>/cancel")
    def snort_cancel(job):
        directory, state = owned(job)
        if state["status"] in ("queued", "running"):
            (directory / "cancel").touch()
        return response(dict(cancellation_requested=True))
