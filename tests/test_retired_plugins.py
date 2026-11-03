"""Removal migration and old archive compatibility; no feature implementation."""

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path
import pytest
from app import app, db, ROOT
from test_api import make_user
import retired_plugins as retired

SECRET = b"legacy-only-package-and-secret-material-729343"


@pytest.fixture(autouse=True)
def remove_legacy_fixture_tables():
    yield
    with app.app_context():
        retired.retire(db())


def legacy(con, token_id):
    con.executescript(
        """
    CREATE TABLE developer_plugins(id TEXT PRIMARY KEY,secret_box BLOB);
    CREATE TABLE plugin_packages(plugin_id TEXT REFERENCES developer_plugins(id),archive BLOB);
    CREATE TABLE developer_versions(plugin_id TEXT REFERENCES developer_plugins(id),archive BLOB);
    CREATE TABLE developer_files(plugin_id TEXT REFERENCES developer_plugins(id),body BLOB);
    CREATE TABLE developer_executions(id TEXT,grant_id INTEGER,worker_id TEXT,status TEXT);
    CREATE TABLE developer_grants(token_id INTEGER,execution_id TEXT);
    INSERT INTO developer_plugins VALUES('old',NULL);
    INSERT OR IGNORE INTO schema_migrations VALUES('developer-workspace-v1');
    INSERT OR IGNORE INTO schema_migrations VALUES('retire-developer-editor-v1');
    INSERT INTO role_permissions VALUES('Administrator','plugins:read');
    INSERT INTO site_settings VALUES('plugins_runtime','obsolete');
    INSERT INTO site_settings VALUES('supported-setting','keep');
    """
    )
    con.execute("UPDATE developer_plugins SET secret_box=?", (SECRET,))
    con.execute("INSERT INTO plugin_packages VALUES(?,?)", ("old", SECRET))
    con.execute(
        "INSERT INTO developer_executions VALUES(?,?,?,?)",
        ("old-job", token_id, "a" * 32, "Running"),
    )
    con.execute("INSERT INTO developer_grants VALUES(?,?)", (token_id, "old-job"))
    con.commit()


def session_client(uid):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="retire-csrf")
    return client


def credentials():
    uid, personal = make_user("retirement-admin", role="Administrator")
    with app.app_context():
        delegated = (
            db()
            .execute(
                "INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created) VALUES(?,'delegated',?,'retired','now')",
                (uid, hashlib.sha256(b"delegated-secret").hexdigest()),
            )
            .lastrowid
        )
        db().commit()
    return uid, personal, delegated


def test_retirement_preserves_supported_data_and_cancels_before_drop(monkeypatch):
    uid, personal, delegated = credentials()
    with app.app_context():
        con = db()
        legacy(con, delegated)
        con.execute(
            "INSERT INTO audit(actor,action,created) VALUES('old analyst','Ran plugin before retirement','2026')"
        )
        con.commit()
        calls = []

        def cancel(worker_id):
            assert con.execute(
                "SELECT revoked FROM api_tokens WHERE id=?", (delegated,)
            ).fetchone()[0]
            assert (
                con.execute("SELECT count(*) FROM developer_executions").fetchone()[0]
                == 1
            )
            calls.append(worker_id)

        monkeypatch.setattr(retired, "cancel_legacy_job", cancel)
        assert retired.retire(con, live=True)
        assert calls == ["a" * 32]
        assert not set(retired.TABLES).intersection(
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
        assert (
            con.execute("SELECT 1 FROM api_tokens WHERE id=?", (delegated,)).fetchone()
            is None
        )
        assert (
            con.execute(
                "SELECT count(*) FROM role_permissions WHERE permission GLOB 'plugins:*'"
            ).fetchone()[0]
            == 0
        )
        assert (
            con.execute(
                "SELECT value FROM site_settings WHERE name='supported-setting'"
            ).fetchone()[0]
            == "keep"
        )
        assert (
            con.execute(
                "SELECT 1 FROM site_settings WHERE name='plugins_runtime'"
            ).fetchone()
            is None
        )
        assert con.execute(
            "SELECT 1 FROM audit WHERE action='Ran plugin before retirement'"
        ).fetchone()
        markers = {r[0] for r in con.execute("SELECT name FROM schema_migrations")}
        assert {
            "developer-workspace-v1",
            "retire-developer-editor-v1",
            retired.MIGRATION,
        } <= markers
        assert not retired.retire(con, live=True)
    client = session_client(uid)
    assert "Ran plugin before retirement" in client.get("/settings/audit").text
    assert client.get("/api/v1/me", headers=personal).status_code == 200
    assert (
        client.get(
            "/api/v1/me", headers={"Authorization": "Bearer delegated-secret"}
        ).status_code
        == 401
    )


def test_failed_shutdown_keeps_records_but_revokes_capability(monkeypatch):
    _, _, delegated = credentials()
    with app.app_context():
        con = db()
        legacy(con, delegated)

        def fail(_):
            raise RuntimeError("Shutdown not confirmed")

        monkeypatch.setattr(retired, "cancel_legacy_job", fail)
        with pytest.raises(RuntimeError, match="Shutdown"):
            retired.retire(con, live=True)
        assert con.execute(
            "SELECT revoked FROM api_tokens WHERE id=?", (delegated,)
        ).fetchone()[0]
        assert (
            con.execute("SELECT count(*) FROM developer_executions").fetchone()[0] == 1
        )


def test_no_feature_routes_permissions_sdk_or_directory_requirement(monkeypatch):
    uid, personal, _ = credentials()
    client = session_client(uid)
    assert all(
        "/plugins" not in r.rule and "/developer/editor" not in r.rule
        for r in app.url_map.iter_rules()
    )
    for path in (
        "/plugins",
        "/plugins/registry",
        "/plugins/discovery",
        "/plugins/executions/old",
        "/api/v1/plugins",
    ):
        assert client.get(path, headers=personal).status_code == 404
    from authorization import PERMISSIONS

    assert not any(p.startswith("plugins:") for p in PERMISSIONS)
    from mws_sdk import MWSClient, AsyncMWSClient

    with MWSClient(base_url="https://example.invalid", api_key="unused") as sdk:
        assert not hasattr(sdk, "plugins") and hasattr(sdk, "cases")
    with app.app_context():
        assert not set(retired.TABLES).intersection(
            r[0]
            for r in db().execute("SELECT name FROM sqlite_master WHERE type='table'")
        )

    # Merely starting/requesting Developer must never enumerate an installed folder.
    def forbid(*args, **kwargs):
        raise AssertionError("Unexpected directory enumeration")

    monkeypatch.setattr(Path, "iterdir", forbid)
    assert client.get("/developer/sdk").status_code == 200
    assert client.get("/api").status_code == 200


def old_archive(tmp_path):
    from test_malware_families import make_backup

    uid, _, delegated = credentials()
    client = session_client(uid)
    with app.app_context():
        from malware_families import initialize

        initialize(db())
    raw = make_backup(client)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    path = tmp_path / "legacy.sqlite3"
    path.write_bytes(files["data/workflow.sqlite3"])
    with sqlite3.connect(path) as con:
        legacy(con, delegated)
    files["data/workflow.sqlite3"] = path.read_bytes()
    files["data/plugins/operator-owned/main.py"] = (
        b'raise RuntimeError("must never be imported")'
    )
    manifest = json.loads(files["installation.json"])
    for name in ("data/workflow.sqlite3", "data/plugins/operator-owned/main.py"):
        manifest["files"][name] = dict(
            size=len(files[name]), sha256=hashlib.sha256(files[name]).hexdigest()
        )
    files["installation.json"] = json.dumps(manifest).encode()
    archive = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name, value in files.items():
            z.writestr(name, value)
    return archive, files


def test_old_complete_backup_skips_code_credentials_and_settings(tmp_path, monkeypatch):
    archive, _ = old_archive(tmp_path)
    monkeypatch.setattr(
        retired,
        "cancel_legacy_job",
        lambda _: pytest.fail("Archive recovery must never call a live worker"),
    )
    from installation_backup import restore_installation

    destination = tmp_path / "restored"
    result = restore_installation(archive, destination)
    assert result["plugins_skipped"] and "skipped" in result["message"]
    assert not (destination / "plugins").exists()
    with sqlite3.connect(destination / "workflow.sqlite3") as con:
        assert con.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert not set(retired.TABLES).intersection(
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        )
        assert (
            con.execute(
                "SELECT 1 FROM site_settings WHERE name='plugins_runtime'"
            ).fetchone()
            is None
        )
        assert (
            con.execute(
                "SELECT value FROM site_settings WHERE name='supported-setting'"
            ).fetchone()[0]
            == "keep"
        )
    assert SECRET not in (destination / "workflow.sqlite3").read_bytes()


@pytest.mark.parametrize(
    "name", ["data/plugins/../../escape.py", "data/plugins/../escape.py"]
)
def test_even_skipped_legacy_paths_are_validated(tmp_path, name):
    archive, files = old_archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr(name, b"bad")
    from installation_backup import restore_installation

    with pytest.raises(ValueError):
        restore_installation(archive, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_current_exports_omit_retired_directories_but_leave_operator_files(tmp_path):
    from test_malware_families import make_backup

    uid, _, _ = credentials()
    client = session_client(uid)
    path = ROOT / "plugins" / "operator-package" / "main.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SECRET)
    try:
        archive = make_backup(client)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert not any(name.startswith("data/plugins/") for name in z.namelist())
        assert path.read_bytes() == SECRET
    finally:
        path.unlink()
        path.parent.rmdir()
        path.parent.parent.rmdir()


@pytest.mark.parametrize("status", ["Canceled", "Succeeded", "Failed", "Timed out"])
def test_one_time_shutdown_uses_only_recorded_cancel_rpc(monkeypatch, status):
    from types import SimpleNamespace

    calls = []
    channel = SimpleNamespace(
        settimeout=lambda _: None, connect=lambda path: calls.append(("connect", path))
    )
    connection = SimpleNamespace(
        sock=None,
        request=lambda *args: calls.append(args),
        getresponse=lambda: SimpleNamespace(
            status=200, read=lambda _: json.dumps({"status": status}).encode()
        ),
        close=lambda: calls.append(("closed",)),
    )
    monkeypatch.setenv("MARE_PLUGIN_WORKER_SOCKET", "/tmp/retired-test.sock")
    monkeypatch.setattr(retired.socket, "socket", lambda *args: channel)
    monkeypatch.setattr(
        retired.http.client, "HTTPConnection", lambda *args, **kwargs: connection
    )
    retired.cancel_legacy_job("a" * 32)
    assert calls[0] == ("connect", "/tmp/retired-test.sock")
    assert calls[1][:3] == ("POST", "/jobs/" + "a" * 32 + "/cancel", "{}")
    assert calls[-1] == ("closed",)
