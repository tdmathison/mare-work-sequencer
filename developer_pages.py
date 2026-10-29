"""Native Developer documentation pages backed by the shipped SDK sources."""

import re
from pathlib import Path
from flask import abort, g, render_template, request
from markupsafe import Markup
from authorization import has_permission
from markdown_support import markdown_parser

DOCUMENTS = {
    "guide": ("SDK guide", "sdk/README.md"),
    "reference": ("API reference", "sdk/docs/API_REFERENCE.md"),
    "coverage": ("Endpoint coverage", "sdk/docs/API_COVERAGE.md"),
    "compatibility": ("Compatibility", "sdk/docs/DISCOVERY.md"),
}


def register_developer_pages(app, db):
    @app.get("/developer/sdk")
    def developer_sdk():
        if not has_permission(g.user, "developer:sdk", db()):
            abort(403)
        selected = request.args.get("document", "guide")
        if selected not in DOCUMENTS:
            abort(404)
        title, relative = DOCUMENTS[selected]
        source = (Path(app.root_path) / relative).read_text()
        parser = markdown_parser()
        tokens = parser.parse(source)
        sections = []
        used = {}
        for index, token in enumerate(tokens):
            if token.type == "heading_open":
                text = tokens[index + 1].content
                slug = (
                    re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "section"
                )
                used[slug] = used.get(slug, 0) + 1
                slug += ("-" + str(used[slug])) if used[slug] > 1 else ""
                token.attrSet("id", slug)
                sections.append(dict(title=text, id=slug, level=token.tag))
        content = Markup(parser.renderer.render(tokens, parser.options, {}))
        return render_template(
            "developer_sdk.html",
            document=selected,
            title=title,
            documents=DOCUMENTS,
            sections=sections,
            content=content,
        )

    @app.get("/developer/editor")
    def developer_editor():
        if not has_permission(g.user, "plugins:read", db()):
            abort(403)
        pid = request.args.get("plugin")
        if pid:
            if not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", pid):
                abort(400)
            if (
                not db()
                .execute(
                    "SELECT 1 FROM developer_plugins WHERE id=? AND owner_uuid=? AND deleted=0",
                    (pid, g.user["user_uuid"]),
                )
                .fetchone()
            ):
                abort(404)
        return render_template("developer_editor.html", selected_plugin=pid or "")

    @app.get("/plugins")
    def plugins_page():
        if not has_permission(g.user, "plugins:read", db()):
            abort(403)
        return render_template("developer_plugins.html")
