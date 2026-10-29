"""Server-side safeguards shared by inventory context actions."""
import json
import pytest
from app import app, db
from test_developer_shell import browser
from test_plugin_workspace import create, post
from test_plugin_pages import install
from test_developer_execution import fake_worker


def discovered(tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "PLUGINS_DIR", str(tmp_path))
    package = install(tmp_path)
    client, uid = browser()
    assert post(client, "discovery").status_code == 200
    return client, uid, package


def test_delete_retires_only_recorded_package_and_keeps_snapshot(tmp_path, monkeypatch):
    client, _, package = discovered(tmp_path, monkeypatch)
    unrelated = install(tmp_path, "other_plugin")
    response = post(client, "plugins/disk_plugin/delete", dict(revision=1, path=str(unrelated)))
    assert response.status_code == 200 and response.json["recoverable"]
    assert not package.exists() and unrelated.exists()
    recovered = list((tmp_path / ".mws-deleted").iterdir())
    assert len(recovered) == 1
    assert json.loads((recovered[0] / "plugin.json").read_text())["id"] == "disk_plugin"
    with app.app_context():
        assert db().execute("SELECT deleted FROM developer_plugins WHERE id='disk_plugin'").fetchone()[0] == 1
        assert db().execute("SELECT count(*) FROM developer_files WHERE plugin_id='disk_plugin'").fetchone()[0]
    assert not client.get("/developer/workspace/plugins").json["plugins"]
    assert "disk_plugin" not in post(client, "discovery").json["registered"]


def test_stale_delete_cannot_move_package(tmp_path, monkeypatch):
    client, _, package = discovered(tmp_path, monkeypatch)
    assert post(client, "plugins/disk_plugin/delete", dict(revision=99)).status_code == 409
    assert package.exists()


def test_protected_plugin_cannot_be_deleted(tmp_path, monkeypatch):
    client, _, package = discovered(tmp_path, monkeypatch)
    monkeypatch.setitem(app.config, "PROTECTED_PLUGIN_IDS", {"disk_plugin"})
    assert client.get("/developer/workspace/plugins/disk_plugin").json["protected"]
    assert post(client, "plugins/disk_plugin/delete", dict(revision=1)).status_code == 403
    assert package.exists()


@pytest.mark.parametrize("kind", ["package", "recovery", "manifest", "traversal", "identity"])
def test_delete_rejects_filesystem_escapes_and_replaced_packages(tmp_path, monkeypatch, kind):
    client, _, package = discovered(tmp_path, monkeypatch)
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    if kind == "package":
        package.rename(tmp_path / "saved")
        package.symlink_to(outside, target_is_directory=True)
    elif kind == "recovery":
        (tmp_path / ".mws-deleted").symlink_to(outside, target_is_directory=True)
    elif kind == "manifest":
        (package / "plugin.json").unlink()
        (package / "plugin.json").symlink_to(sentinel)
    elif kind == "identity":
        value = json.loads((package / "plugin.json").read_text())
        value["id"] = "replacement_plugin"
        (package / "plugin.json").write_text(json.dumps(value))
    else:
        with app.app_context():
            db().execute("UPDATE developer_plugins SET source_location='../outside' WHERE id='disk_plugin'")
            db().commit()
    assert post(client, "plugins/disk_plugin/delete", dict(revision=1)).status_code == 409
    assert sentinel.read_text() == "keep" and package.exists()
    with app.app_context():
        assert db().execute("SELECT deleted FROM developer_plugins WHERE id='disk_plugin'").fetchone()[0] == 0


def test_unauthorized_context_mutations_are_rejected(tmp_path, monkeypatch):
    client, uid, package = discovered(tmp_path, monkeypatch)
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('plugin-reader')")
        db().execute("INSERT INTO role_permissions VALUES('plugin-reader','plugins:read')")
        db().execute("UPDATE users SET role='plugin-reader' WHERE id=?", (uid,))
        db().commit()
    for action, data in (("enable", {"enabled": True}), ("enable", {"enabled": False}), ("delete", {"revision": 1})):
        assert post(client, "plugins/disk_plugin/" + action, data).status_code == 403
    assert package.exists()
    other, _ = browser()
    assert post(other, "plugins/disk_plugin/delete", dict(revision=1)).status_code == 404


def test_delete_preserves_active_execution_history(monkeypatch):
    client, _ = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    started = post(client, "plugins/hello_plugin/develop")
    assert started.status_code == 202
    assert post(client, "plugins/hello_plugin/delete", dict(revision=1)).status_code == 200
    assert client.get("/developer/workspace/executions/" + started.json["id"]).json["status"] == "Running"
    assert len(client.get("/developer/workspace/plugins/hello_plugin/history").json["executions"]) == 1
    assert post(client, "plugins/hello_plugin/develop").status_code == 404


def test_retirement_rollback_restores_files(tmp_path):
    from plugin_discovery import retire_package
    package = install(tmp_path)
    finish = retire_package(tmp_path, "disk_plugin", "disk_plugin")
    assert not package.exists()
    finish(rollback=True)
    assert package.exists()
    assert not list((tmp_path / ".mws-deleted").iterdir())


def test_nested_symlink_is_moved_without_touching_target(tmp_path, monkeypatch):
    client, _, package = discovered(tmp_path, monkeypatch)
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("keep")
    (package / "link").symlink_to(sentinel)
    assert post(client, "plugins/disk_plugin/delete", dict(revision=1)).status_code == 200
    assert sentinel.read_text() == "keep"


def test_symlinked_plugin_root_is_rejected(tmp_path, monkeypatch):
    client, _, package = discovered(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setitem(app.config, "PLUGINS_DIR", str(alias))
    assert post(client, "plugins/disk_plugin/delete", dict(revision=1)).status_code == 409
    assert package.exists()
