"""Artifact Register adapters over existing Case file services."""

import json
import tempfile
import zipfile
from flask import abort, g, request, send_file
from authorization import has_permission
from package_status import inventory, states


def register(app, db, case, package, safe_path):
    @app.get("/cases/<int:cid>/package-register")
    def package_register(cid):
        if not has_permission(g.user, "cases:read", db()):
            abort(403)
        c = case(cid)
        counts, rows = inventory(db(), c, package(cid))
        from package_status import carriers

        derived = carriers(db(), cid)
        can_assets = has_permission(g.user, "cases:assets", db())
        can_update = has_permission(g.user, "cases:update", db())
        query = request.args.get("q", "").strip().casefold()[:200]
        section = request.args.get("section", "")
        kind = request.args.get("type", "")
        kinds = sorted({r["type"] for r in rows})
        for row in rows:
            path = row["path"]
            row["download"] = bool(path and can_assets)
            row["bulk_download"] = row["download"] and (
                row["section"] != "samples"
                or has_permission(g.user, "samples:export", db())
            )
            row["remove"] = bool(
                path and not row["owner"] and can_assets and not c["workspace_locked"]
            )
            row["editable"] = (
                row["editable"] and can_assets and not c["workspace_locked"]
            )
            row["size"] = (
                len(derived[path])
                if path in derived
                else (package(cid) / path).stat().st_size if path else None
            )
        rows = [
            r
            for r in rows
            if (not section or r["section"] == section)
            and (not kind or r["type"] == kind)
            and (not query or query in (r["name"] + " " + (r["path"] or "")).casefold())
        ]
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            page = 1
        total = len(rows)
        page = min(page, max(1, (total + 49) // 50))
        return (
            {
                "rows": rows[(page - 1) * 50 : page * 50],
                "total": total,
                "page": page,
                "pages": max(1, (total + 49) // 50),
                "types": kinds,
                "sections": states(db(), c, package(cid)),
                "locked": c["workspace_locked"],
                "can_add": any(
                    has_permission(g.user, p, db())
                    for p in (
                        "cases:update",
                        "indicators:write",
                        "references:write",
                        "reports:write",
                    )
                ),
                "can_upload": can_assets and not c["workspace_locked"],
                "can_applicability": can_update and not c["workspace_locked"],
                "sample_download": has_permission(g.user, "samples:export", db()),
            },
            200,
            {"Cache-Control": "private, no-store"},
        )

    @app.post("/cases/<int:cid>/package-register/download")
    def package_bulk_download(cid):
        c = case(cid)
        if not has_permission(g.user, "cases:assets", db()):
            abort(403)
        try:
            paths = json.loads(request.form.get("paths", "[]"))
        except ValueError:
            abort(400)
        if (
            not isinstance(paths, list)
            or not paths
            or len(paths) > 200
            or any(not isinstance(p, str) for p in paths)
        ):
            abort(400)
        _, rows = inventory(db(), c, package(cid))
        allowed = {r["path"] for r in rows if r["path"]}
        paths = list(dict.fromkeys(paths))
        if not set(paths) <= allowed:
            abort(400)
        if any(p.startswith("samples/") for p in paths) and not has_permission(
            g.user, "samples:export", db()
        ):
            abort(403)
        from package_status import carriers

        derived = carriers(db(), cid)
        files = [(p, derived[p] if p in derived else safe_path(cid, p)) for p in paths]
        if (
            sum(len(p) if isinstance(p, bytes) else p.stat().st_size for _, p in files)
            > 100 * 1024 * 1024
        ):
            abort(413)
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        try:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
                for relative, path in files:
                    if isinstance(path, bytes):
                        z.writestr(relative, path)
                    else:
                        z.write(path, relative)
            output.seek(0)
            response = send_file(
                output,
                as_attachment=True,
                download_name=c["number"] + "-artifacts.zip",
                mimetype="application/zip",
            )
            response.call_on_close(output.close)
            return response
        except Exception:
            output.close()
            raise
