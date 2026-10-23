import io
from urllib.parse import urlsplit
import pytest
from app import app, db
from authorization import initialize_roles
from werkzeug.security import generate_password_hash


def login(role="Administrator"):
    with app.app_context():
        initialize_roles(db())
        uid = (
            db()
            .execute(
                "INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",
                ("settings-test", generate_password_hash("settings-password"), role),
            )
            .lastrowid
        )
        db().commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="settings-test")
    return client, uid


def post(c, path, **values):
    return c.post(path, data={"csrf": "settings-test", **values})


def test_canonical_categories_and_query_preserving_bookmarks():
    c, _ = login()
    for old, new in [
        ("/account", "/settings/general"),
        ("/users", "/settings/users"),
        ("/audit", "/settings/audit"),
        ("/import-export", "/settings/import-export"),
        ("/backup-restore", "/settings/import-export"),
    ]:
        response = c.get(old + "?actor=alice&page=3&filter=a%26b")
        assert response.status_code == 302
        assert response.location == new + "?actor=alice&page=3&filter=a%26b"
        page = c.get(new)
        assert page.status_code == 200
        assert "<h1>Settings</h1>" in page.text
        assert 'aria-current="page">SETTINGS' in page.text
        assert (
            'aria-current="page">'
            + {
                "/settings/general": "General",
                "/settings/users": "Users",
                "/settings/audit": "Audit",
                "/settings/import-export": "Import &amp; Export",
            }[new]
            in page.text
        )
    assert c.get("/settings").location == "/settings/general"
    assert c.get("/settings/unknown").status_code == 404
    general = c.get("/settings/general").text
    assert "<h2>Backup &amp; Restore</h2>" not in general
    assert "Database &amp; Installation backup" not in general
    assert "Sample archive protection" in general
    backup = c.get("/settings/import-export").text
    assert "Complete application backup" in backup and 'id="import-tab"' in backup


def test_permissions_filter_categories_and_preserve_mutation_boundaries():
    c, _ = login("User")
    html = c.get("/settings/general").text
    assert "/settings/general" in html
    for path in ["/settings/users", "/settings/audit", "/settings/import-export"]:
        assert path not in html
        assert c.get(path).status_code == 403
    assert (
        post(c, "/settings/users", username="unauthorized", role="User").status_code
        == 403
    )
    assert post(c, "/users/1/reset").status_code == 403
    assert c.get("/audit/export.csv").status_code == 403
    assert (
        post(c, "/backup-restore/jobs", kind="export", areas=["tags"]).status_code
        == 403
    )
    assert c.post("/account/autosave", data={"autosave_minutes": 2}).status_code == 403
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('Backup specialist')")
        db().execute(
            "INSERT INTO role_permissions VALUES('Backup specialist','backups:manage')"
        )
        db().execute("UPDATE users SET role='Backup specialist'")
        db().commit()
    html = c.get("/settings/general").text
    assert (
        "/settings/import-export" in html
        and "/settings/users" not in html
        and "/settings/audit" not in html
    )
    assert c.get("/settings/import-export").status_code == 200


def test_existing_forms_canonical_posts_validation_and_safe_save_continuation():
    c, uid = login()
    assert (
        post(
            c,
            "/account/autosave",
            autosave_minutes="7",
            settings_next="/settings/audit?actor=alice",
        ).location
        == "/settings/audit?actor=alice"
    )
    assert (
        post(
            c,
            "/account/autosave",
            autosave_minutes="bad",
            settings_next="/settings/users",
        ).location
        == "/settings/general"
    )
    assert (
        post(
            c,
            "/account/board-view",
            board_view="table",
            settings_next="https://example.com",
        ).location
        == "/settings/general"
    )
    with app.app_context():
        assert db().execute(
            "SELECT autosave_minutes,board_view FROM users WHERE id=?", (uid,)
        ).fetchone()[:] == (7, "table")
    result = post(
        c,
        "/settings/users",
        username="new-settings-user",
        role="User",
        settings_next="/settings/audit",
    )
    assert result.location == "/settings/audit"
    with app.app_context():
        new = (
            db()
            .execute("SELECT * FROM users WHERE username='new-settings-user'")
            .fetchone()
        )
        assert new and new["forced"] == 1
        new_id = new["id"]
    assert post(c, f"/users/{new_id}/toggle").location == "/settings/users"
    with app.app_context():
        assert (
            db().execute("SELECT active FROM users WHERE id=?", (new_id,)).fetchone()[0]
            == 0
        )
    assert (
        post(
            c,
            "/settings/general",
            current="wrong",
            password="a-new-password",
            confirm="a-new-password",
            settings_next="/settings/users",
        ).status_code
        == 200
    )
    response = post(
        c,
        "/settings/general",
        current="settings-password",
        password="a-new-password",
        confirm="a-new-password",
        settings_next="/settings/users",
    )
    assert response.location == "/settings/users"
