"""Shared permission-aware application shell; existing destinations stay authoritative."""

from flask import abort, g, render_template, request, session, url_for
from authorization import has_permission
from dashboard_directory import DASHBOARDS
from navigation import SETTINGS_CATEGORY_ENDPOINTS


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
                        identifier=tool.identifier,
                        icon=tool.icon,
                        url=url_for("tools_workspace", tool_id=tool.identifier),
                        active=endpoint == "tools_workspace"
                        and (
                            (request.view_args or {}).get("tool_id") == tool.identifier
                            if (request.view_args or {}).get("tool_id")
                            else not tools
                        ),
                    )
                )
        if can("tags:read"):
            intelligence=[
                dict(label="Malware Families",url=url_for("families_workspace"),icon="♧",active=endpoint.startswith("families_")),
                dict(label="Threat Actors",url=url_for("actors_workspace"),icon="⬡",active=endpoint.startswith("actors_")),
                dict(label="Tags",url=url_for("tags_manager"),icon="#",active=endpoint.startswith(("tags_","tag_"))),
            ]
            add("Intelligence",url_for("families_workspace"),"♧",any(child['active'] for child in intelligence),intelligence)
        add(
            "Dashboards",
            url_for("dashboards_directory"),
            "▧",
            endpoint == "dashboards_directory"
            or any(item.endpoint == endpoint for item in DASHBOARDS),
        )
        if tools:
            add(
                "Tools",
                tools[0]["url"],
                "⚒",
                endpoint.startswith(("tools_", "yara_", "snort_")),
                tools,
            )
        if can("cases:read") or can("tags:read"):
            add(
                "Data Explorer",
                url_for("data_explorer"),
                "⌗",
                endpoint == "data_explorer",
            )

        settings = [
            dict(
                label="General",
                icon="⚙",
                url=url_for("account"),
                active=endpoint in SETTINGS_CATEGORY_ENDPOINTS["general"],
            )
        ]
        # Match the existing Administrator-only Users and Audit web routes.
        if user["role"] == "Administrator":
            settings.append(
                dict(
                    label="Users",
                    icon="♙",
                    url=url_for("users"),
                    active=endpoint in SETTINGS_CATEGORY_ENDPOINTS["users"],
                )
            )
        if user["role"] == "Administrator":
            settings.append(
                dict(
                    label="Audit",
                    icon="▤",
                    url=url_for("audit_view"),
                    active=endpoint in SETTINGS_CATEGORY_ENDPOINTS["audit"],
                )
            )
        if can("backups:manage"):
            settings.append(
                dict(
                    label="Import & Export",
                    icon="⇄",
                    url=url_for("import_export_page"),
                    active=endpoint in SETTINGS_CATEGORY_ENDPOINTS["import-export"],
                )
            )
        add(
            "Settings",
            url_for("account"),
            "⚙",
            any(child["active"] for child in settings),
            settings,
        )

        developer = []
        for label, permission, target, icon in [
            ("API", "developer:api", "api_page", "⇆"),
            ("SDK", "developer:sdk", "developer_sdk", "▥"),
            ("Plugins", "plugins:read", "plugins_page", "◇"),
        ]:
            if can(permission):
                developer.append(
                    dict(
                        label=label,
                        icon=icon,
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
                any(child["active"] for child in developer),
                developer,
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
