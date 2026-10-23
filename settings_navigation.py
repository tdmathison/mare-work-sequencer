"""Settings categories share existing handlers and their existing authorization."""

from urllib.parse import urlsplit
from flask import g, redirect, request, url_for
from authorization import has_permission
from navigation import SETTINGS_CATEGORY_ENDPOINTS

CATEGORIES = (
    ("general", "General", "account"),
    ("users", "Users", "users"),
    ("audit", "Audit", "audit_view"),
    ("import-export", "Import & Export", "import_export_page"),
)


def category(endpoint):
    return next(
        (
            key
            for key, endpoints in SETTINGS_CATEGORY_ENDPOINTS.items()
            if endpoint in endpoints
        ),
        None,
    )


def legacy_redirect(endpoint):
    query = request.query_string.decode("latin1")
    return redirect(url_for(endpoint) + ("?" + query if query else ""))


def saved_destination(default):
    """Honor only a known local category URL, and only after successful saves."""
    value = request.form.get("settings_next", "")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return default
    if (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path in {"/settings/" + key for key, _, _ in CATEGORIES}
    ):
        return value
    return default


def register_settings(app, db):
    @app.get("/settings")
    def settings_home():
        return legacy_redirect("account")

    @app.context_processor
    def settings_navigation():
        user = getattr(g, "user", None)
        tabs = []
        if user:
            for key, label, endpoint in CATEGORIES:
                # Web Users/Audit have always required the built-in admin role.
                allowed = (
                    key == "general"
                    or (key in ("users", "audit") and user["role"] == "Administrator")
                    or (
                        key == "import-export"
                        and has_permission(user, "backups:manage", db())
                    )
                )
                if allowed:
                    tabs.append(dict(key=key, label=label, url=url_for(endpoint)))
        return dict(
            settings_tabs=tabs,
            settings_category=category(request.endpoint),
            settings_home_url=tabs[0]["url"] if tabs else None,
        )
