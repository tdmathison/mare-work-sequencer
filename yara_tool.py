"""Authenticated YARA workspace, complete-file storage and bounded jobs."""

import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from flask import abort, g, make_response, render_template, request, send_file
from authorization import has_permission
from signature_files import LIMIT, Conflict, persist, safe_signature, version
from yara_engine import YaraEngine


def register_yara(app, db, require_tool, root, case, ensure_package, audit, safe_path):
    for key, default, low, high in [
        ("TIMEOUT", 15, 1, 60),
        ("CONCURRENCY", 2, 1, 4),
        ("JOB_TTL", 3600, 60, 86400),
        ("UPLOAD_LIMIT", 10 * 1024**2, 1024, 20 * 1024**2),
    ]:
        value = int(os.environ.get("MARE_YARA_" + key, default))
        if not low <= value <= high:
            raise ValueError("Invalid MARE_YARA_" + key)
        app.config["YARA_" + key] = value
    app.config["YARA_PYTHON"] = os.environ.get("MARE_YARA_PYTHON", sys.executable)
    engine = YaraEngine(app, root)
    app.extensions["yara_engine"] = engine
    engine.cleanup()
    drafts = Path(root) / "yara-drafts"
    drafts.mkdir(mode=0o700, exist_ok=True)

    def guard():
        require_tool(app, db, "yara-rule-editor")

    def response(data, status=200):
        result = make_response(data, status)
        result.headers["Cache-Control"] = "no-store"
        return result

    def source():
        try:
            value = json.loads(request.form.get("source_json", "null"))
        except RecursionError as error:
            raise ValueError("Source JSON is nested too deeply.") from error
        if not isinstance(value, str) or len(value.encode()) > LIMIT or "\0" in value:
            raise ValueError(
                "Provide UTF-8 source, at most 100,000 bytes, without NUL."
            )
        return value

    def access(cid, write=False):
        guard()
        for permission in (
            "cases:read",
            "cases:assets",
            *(("cases:update",) if write else ()),
        ):
            if not has_permission(g.user, permission, db()):
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
            abort(409, description="Wait for report generation before changing assets.")
        return c

    def package(cid):
        return Path(root) / "cases" / str(cid) / "mip"

    def draft_path():
        return drafts / (g.user["user_uuid"] + ".json")

    @app.get("/tools/yara-rule-editor/app/")
    def tools_yara():
        guard()
        result = make_response(render_template("yara_editor.html"))
        result.headers.update(
            {
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
            }
        )
        return result

    @app.get("/tools/yara-rule-editor/state")
    def yara_state():
        guard()
        engine.cleanup()
        try:
            draft = json.loads(draft_path().read_text())
        except (OSError, ValueError):
            draft = None
        cases = []
        if all(has_permission(g.user, p, db()) for p in ("cases:read", "cases:assets")):
            cases = [
                dict(c)
                for c in db().execute(
                    "SELECT id,number,name,stage FROM cases ORDER BY id DESC"
                )
            ]
        return response(dict(engine=engine.discover(), draft=draft, cases=cases))

    @app.post("/tools/yara-rule-editor/draft")
    def yara_draft():
        guard()
        try:
            data = dict(
                source=source(), context=json.loads(request.form.get("context", "null"))
            )
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 400000:
                raise ValueError("Draft context exceeds limits.")
            fd, name = tempfile.mkstemp(dir=drafts, prefix=".draft-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, ensure_ascii=False)
                os.replace(name, draft_path())
            finally:
                Path(name).unlink(missing_ok=True)
            return response(dict(saved=True))
        except (ValueError, TypeError, RecursionError) as error:
            return response(dict(error=str(error)), 400)

    @app.post("/tools/yara-rule-editor/download")
    def yara_download():
        guard()
        try:
            return send_file(
                io.BytesIO(source().encode()),
                download_name="analyst.yara",
                as_attachment=True,
                mimetype="text/plain",
            )
        except (ValueError, TypeError) as error:
            return response(dict(error=str(error)), 400)

    @app.get("/cases/<int:cid>/yara-files")
    def yara_files(cid):
        c = access(cid)
        files, samples = [], []
        base = package(cid)
        from itertools import chain, islice

        entries = chain((base / "signatures").rglob("*"), (base / "samples").rglob("*"))
        for p in islice(entries, 3000):
            if p.is_symlink() or not p.is_file():
                continue
            relative = p.relative_to(base).as_posix()
            if relative.startswith("signatures/") and p.suffix.lower() == ".yara":
                try:
                    safe_signature(base, relative[len("signatures/") :], ".yara")
                    files.append(
                        dict(path=relative[len("signatures/") :], size=p.stat().st_size)
                    )
                except ValueError:
                    continue
            elif relative.startswith("samples/"):
                safe_path(cid, relative)
                if p.stat().st_size <= app.config["YARA_UPLOAD_LIMIT"]:
                    samples.append(relative)
            if len(files) + len(samples) >= 1000:
                break
        editable = (
            has_permission(g.user, "cases:update", db()) and not c["workspace_locked"]
        )
        return response(dict(files=files, samples=samples, editable=bool(editable)))

    @app.get("/cases/<int:cid>/yara-file")
    def yara_open(cid):
        access(cid)
        try:
            name = request.args.get("path", "")
            p = safe_signature(package(cid), name, ".yara")
            if not p.is_file():
                abort(404)
            if p.stat().st_size > LIMIT:
                raise ValueError("File exceeds the 100,000-byte editing limit.")
            raw = p.read_bytes()
            return response(
                dict(source=raw.decode("utf-8"), version=version(raw), path=name)
            )
        except (ValueError, OSError) as error:
            return response(dict(error=str(error)), 400)

    @app.post("/cases/<int:cid>/yara-file")
    def yara_save(cid):
        access(cid, True)
        try:
            name = request.form.get("filename", "")
            result = persist(
                ensure_package(cid),
                name,
                source().encode(),
                db(),
                cid,
                expected=request.form.get("version") or None,
                suffix=".yara",
            )
            audit(f"Saved YARA file case {cid}: signatures/{name}")
            db().commit()
            return response(result)
        except (ValueError, OSError, sqlite3.Error) as error:
            return response(
                dict(
                    error=str(error),
                    conflict=isinstance(error, Conflict),
                    current=getattr(error, "current", None),
                ),
                409 if isinstance(error, Conflict) else 400,
            )

    @app.post("/tools/yara-rule-editor/jobs")
    def yara_jobs():
        guard()
        if not engine.discover()["available"]:
            return response(dict(error=engine.discover()["message"]), 503)
        try:
            if request.form.get("kind") not in ("validate", "scan"):
                raise ValueError("Choose validation or sample scan.")
            samples, labels = [], {}
            if request.form["kind"] == "scan":
                for field in ("positive", "baseline"):
                    upload = request.files.get(field)
                    relative = request.form.get(field + "_path", "")
                    if upload and relative:
                        raise ValueError("Choose an upload or a case asset, not both.")
                    if upload:
                        raw = upload.read(app.config["YARA_UPLOAD_LIMIT"] + 1)
                    elif relative:
                        cid = int(request.form.get("case_id", "0"))
                        access(cid)
                        if not relative.startswith("samples/"):
                            raise ValueError("Choose an authorized samples/ asset.")
                        path = safe_path(cid, relative)
                        if (
                            not path.is_file()
                            or path.stat().st_size > app.config["YARA_UPLOAD_LIMIT"]
                        ):
                            raise ValueError(
                                "Case asset is missing or exceeds the sample limit."
                            )
                        raw = path.read_bytes()
                    else:
                        if field == "positive":
                            raise ValueError(
                                "Choose a positive sample upload or authorized case asset."
                            )
                        continue
                    if len(raw) > app.config["YARA_UPLOAD_LIMIT"]:
                        raise ValueError("Sample exceeds upload limit.")
                    samples.append((field, raw))
                    labels[field] = (
                        Path(upload.filename.replace("\\", "/")).name[:200]
                        if upload
                        else relative
                    )
            return response(
                engine.submit(g.user["user_uuid"], source(), samples, labels), 202
            )
        except (ValueError, TypeError, OSError) as error:
            return response(dict(error=str(error)), 400)

    def owned(job):
        guard()
        if not re.fullmatch("[a-f0-9]{32}", job):
            abort(404)
        directory = engine.root / job
        try:
            state = engine.read(directory)
        except (ValueError, OSError):
            abort(404)
        if state.get("user") != g.user["user_uuid"]:
            abort(404)
        return directory, state

    @app.get("/tools/yara-rule-editor/jobs/<job>")
    def yara_job(job):
        guard()
        engine.cleanup()
        _, state = owned(job)
        state.pop("user", None)
        return response(state)

    @app.post("/tools/yara-rule-editor/jobs/<job>/cancel")
    def yara_cancel(job):
        directory, state = owned(job)
        if state["status"] in ("queued", "running"):
            (directory / "cancel").touch()
        return response(dict(cancellation_requested=True))
