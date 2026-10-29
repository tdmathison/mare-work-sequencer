"""Shared permission-aware application shell; existing destinations stay authoritative."""

from flask import abort, g, render_template, request, session, url_for
from authorization import has_permission


def register_shell(app, db):
    @app.context_processor
    def sidebar_context():
        user = getattr(g, "user", None)
        if not user:
            return dict(sidebar_items=[])
        can = lambda p: has_permission(user, p, db())
        endpoint = request.endpoint or ""
        cid = (request.view_args or {}).get("cid")
        if cid is not None and request.path.startswith("/cases/") and can("cases:read"):
            session["last_case_id"] = cid
        last = session.get("last_case_id")
        if (
            last
            and not db().execute("SELECT 1 FROM cases WHERE id=?", (last,)).fetchone()
        ):
            last = None
        items = []

        def add(label, url, icon, active=False, children=None):
            items.append(
                dict(
                    label=label,
                    url=url,
                    icon=icon,
                    active=active,
                    children=children or [],
                )
            )

        if can("cases:read"):
            add(
                "MIP Board",
                url_for("dashboard"),
                "▦",
                endpoint in ("dashboard", "create_case_page"),
            )
            add(
                "Workbench",
                url_for("detail", cid=last) if last else url_for("workbench_home"),
                "▤",
                (cid is not None and request.path.startswith("/cases/"))
                or endpoint == "workbench_home",
            )
            add("Search", url_for("mip_search"), "⌕", endpoint.startswith("mip_search"))
        tools = []
        for tool in app.extensions.get("analyst_tools", {}).values():
            if tool.enabled and (not tool.permission or can(tool.permission)):
                tools.append(
                    dict(
                        label=tool.name,
                        url=url_for("tools_workspace", tool_id=tool.identifier),
                        active=endpoint == "tools_workspace"
                        and ((request.view_args or {}).get("tool_id") or "cyberchef")
                        == tool.identifier,
                    )
                )
        if (
            tools
            and endpoint == "tools_workspace"
            and not (request.view_args or {}).get("tool_id")
        ):
            tools[0]["active"] = True
        if tools:
            add(
                "Tools",
                tools[0]["url"],
                "⚒",
                endpoint.startswith(("tools_", "yara_", "snort_")),
                tools,
            )
        if can("plugins:read"):
            add("Plugins", url_for("plugins_page"), "◇", endpoint == "plugins_page")
        if can("metrics:read"):
            add("Metrics", url_for("metrics"), "▥", endpoint == "metrics")
        if user["role"] == "Administrator":
            add("Users", url_for("users"), "♙", endpoint in ("users", "user_action"))
        add(
            "Settings",
            url_for("account"),
            "⚙",
            endpoint in ("account", "settings_home", "audit_view"),
            [
                dict(
                    label="General",
                    url=url_for("account"),
                    active=endpoint == "account",
                )
            ]
            + (
                [
                    dict(
                        label="Audit",
                        url=url_for("audit_view"),
                        active=endpoint == "audit_view",
                    )
                ]
                if user["role"] == "Administrator"
                else []
            ),
        )
        if can("backups:manage"):
            add(
                "Import & Export",
                url_for("import_export_page"),
                "⇄",
                endpoint.startswith(("backup_", "sync_import"))
                or endpoint == "import_export_page",
            )
        developer = []
        for label, permission, target in [
            ("API", "developer:api", "api_page"),
            ("SDK", "developer:sdk", "developer_sdk"),
            ("Editor", "plugins:read", "developer_editor"),
        ]:
            if can(permission):
                developer.append(
                    dict(
                        label=label,
                        url=url_for(target),
                        active=endpoint
                        in (
                            (target, "developer_api", "api_openapi")
                            if label == "API"
                            else (target,)
                        ),
                    )
                )
        if developer:
            add(
                "Developer",
                developer[0]["url"],
                "⌘",
                any(c["active"] for c in developer),
                developer,
            )
        if can("tags:read"):
            add(
                "Malware Families",
                url_for("families_workspace"),
                "♧",
                endpoint.startswith("families_"),
            )
            add(
                "Threat Actors",
                url_for("actors_workspace"),
                "⬡",
                endpoint.startswith("actors_"),
            )
            add(
                "Tags",
                url_for("tags_manager"),
                "#",
                endpoint.startswith(("tags_", "tag_")),
            )
        if can("cases:read") or can("tags:read"):
            add(
                "Data Explorer",
                url_for("data_explorer"),
                "⌗",
                endpoint == "data_explorer",
            )
        add(
            "Dashboards",
            url_for("dashboards_directory"),
            "▧",
            endpoint == "dashboards_directory",
        )
        current = next((i["label"] for i in items if i["active"]), "MWS")
        return dict(sidebar_items=items, shell_current=current)

    @app.get("/workbench")
    def workbench_home():
        if not has_permission(g.user, "cases:read", db()):
            abort(403)
        query = request.args.get("q", "").strip()[:200]
        rows = (
            db()
            .execute(
                "SELECT id,number,name FROM cases WHERE ?='' OR instr(lower(number||' '||name),lower(?))>0 ORDER BY id DESC LIMIT 100",
                (query, query),
            )
            .fetchall()
        )
        return render_template("workbench_home.html", cases=rows, query=query)
