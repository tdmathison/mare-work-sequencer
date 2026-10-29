from app import app, db
from test_api import make_user


def browser(role="Administrator"):
    uid, _ = make_user(
        "developer-shell-" + __import__("uuid").uuid4().hex[:8], role=role
    )
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="dev-csrf")
    return c, uid


def test_shared_sidebar_and_existing_destinations():
    c, _ = browser()
    page = c.get("/").text
    assert 'id="application-sidebar"' in page and 'class="admin-nav"' not in page
    for label in (
        "MIP Board",
        "Workbench",
        "Tools",
        "Plugins",
        "Metrics",
        "Users",
        "Settings",
        "Import &amp; Export",
        "Developer",
        "API",
        "SDK",
        "Editor",
        "Data Explorer",
        "Malware Families",
        "Threat Actors",
        "Dashboards",
    ):
        assert label in page, label
    assert c.get("/workbench").status_code == 200
    assert c.get("/developer/sdk").status_code == 200
    assert c.get("/developer/sdk?document=reference").status_code == 200
    assert c.get("/developer/sdk?document=../../secret").status_code == 404
    assert c.get("/developer/api").status_code == 200
    assert c.get("/api").status_code == 200


def test_developer_permissions_are_not_implied_by_case_access():
    c, uid = browser()
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('developer-limited')")
        db().execute(
            "INSERT INTO role_permissions VALUES('developer-limited','cases:read')"
        )
        db().execute("UPDATE users SET role='developer-limited' WHERE id=?", (uid,))
        db().commit()
    for path in (
        "/developer/api",
        "/api/openapi.json",
        "/developer/sdk",
        "/developer/editor",
        "/plugins",
    ):
        assert c.get(path).status_code == 403, path
    assert ">Developer<" not in c.get("/").text
    with app.app_context():
        db().execute(
            "INSERT INTO role_permissions VALUES('developer-limited','developer:sdk')"
        )
        db().commit()
    assert c.get("/developer/sdk").status_code == 200
    assert c.get("/developer/editor").status_code == 403
