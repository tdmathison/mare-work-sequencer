from html.parser import HTMLParser

import pytest
from flask import request

from app import app, db, run, ensure_package, package
from authorization import initialize_roles
from navigation import SECTION_ENDPOINTS, navigation_section
from tagging import create


class NavigationParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inside = False
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("class") == "admin-nav":
            self.inside = True
        if self.inside and tag == "a":
            self.links.append(attrs)

    def handle_endtag(self, tag):
        if tag == "nav":
            self.inside = False


@pytest.mark.parametrize("role", ["User", "Administrator"])
def test_rendered_application_sections(role, monkeypatch):
    monkeypatch.setattr(app.extensions["mip_search"], "schedule", lambda: None)
    with app.app_context():
        initialize_roles(db())
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES('nav','unused',?,0)",
            (role,),
        ).lastrowid
        cid = run(
            "INSERT INTO cases(number,name,description,stage,created,owner,creator) VALUES('NAV-001','Navigation','',1,'now',?,?)",
            (uid, uid),
        ).lastrowid
        ensure_package(cid)
        (package(cid) / "supporting" / "navigation.md").write_text("# Navigation")
        tid, _ = create(db(), "NAVIGATION_TAG")
        db().commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="nav-token")
    pages = {
        "/": "/",
        "/cases/new": "/",
        f"/cases/{cid}": "/",
        f"/cases/{cid}/file?path=supporting/navigation.md": "/",
        "/search": "/search",
        "/metrics": "/metrics",
        "/tags": "/tags",
        f"/tags/{tid}": "/tags",
        "/tools": "/tools",
        "/tools/text-manipulation": "/tools",
        "/account": "/account",
        "/api": "/api",
        "/import-export": "/import-export",
    }
    if role == "Administrator":
        pages.update({"/users": "/users", "/audit": "/audit"})
    for path, parent in pages.items():
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
        links = NavigationParser(response.get_data(as_text=True)).links
        assert [
            link["href"] for link in links if link.get("aria-current") == "page"
        ] == [parent], path
        assert ("/users" in [link["href"] for link in links]) == (
            role == "Administrator"
        )
        assert ("/audit" in [link["href"] for link in links]) == (
            role == "Administrator"
        )
    if role == "User":
        assert client.get("/users").status_code == 403
        assert client.get("/audit").status_code == 403


@pytest.mark.parametrize("section,endpoints", SECTION_ENDPOINTS.items())
def test_endpoint_mapping(section, endpoints):
    registered = {rule.endpoint for rule in app.url_map.iter_rules()}
    for endpoint in endpoints:
        assert endpoint in registered
        assert navigation_section(endpoint) == section


@pytest.mark.parametrize(
    "path,method,expected",
    [
        ("/cases/1/tags/create", "POST", "board"),
        ("/tags/create", "POST", "tags"),
        ("/account/templates/1", "GET", "settings"),
        ("/search/findings/example", "GET", "search"),
        ("/cases/1/file", "GET", "board"),
        ("/cases/1/backup", "POST", "board"),
        ("/import-export/import-raw", "POST", "import_export"),
        ("/tools/cyberchef/app/main.js", "GET", "tools"),
        ("/account?next=/users&section=search", "GET", "settings"),
        ("/login", "GET", None),
        ("/not-a-page", "GET", None),
    ],
)
def test_matched_routes_and_parent_sections(path, method, expected):
    with app.test_request_context(path, method=method):
        assert navigation_section(request.endpoint, request.view_args) == expected
