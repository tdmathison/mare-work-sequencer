import base64
import io
import json
import threading
import zipfile
import pytest
from app import app, db
import plugin_store as store
from developer_worker.supervisor import Job
from test_developer_shell import browser
from test_plugin_workspace import metadata, post, create
from test_developer_execution import fake_worker


def install(folder, pid="disk_plugin", name="Disk plugin"):
    value = metadata(pid)
    value["name"] = name
    path = folder / pid
    path.mkdir(parents=True)
    for relative, item in store.template_files(value, "hello").items():
        target = path / relative
        if item["directory"]:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item["body"])
    return path


def test_pages_are_distinct_and_edit_resolves_owned_identifier():
    client, _ = browser()
    create(client)
    management = client.get("/plugins").text
    assert (
        "data-plugin-management" in management
        and "data-developer-editor" not in management
    )
    assert "ide-code" not in management and 'data-debug="stepIn"' not in management
    editor = client.get("/developer/editor?plugin=hello_plugin")
    assert editor.status_code == 200 and 'data-selected="hello_plugin"' in editor.text
    for removed in (
        "data-case",
        "data-version",
        "ide-docs",
        'data-debug="start"',
        'data-command="publish"',
        'data-command="export"',
    ):
        assert removed not in editor.text
    assert editor.text.count("data-console-tab=") == 2
    assert client.get("/developer/editor?plugin=../../etc/passwd").status_code == 400
    assert client.get("/developer/editor?plugin=unknown_plugin").status_code == 404
    other, _ = browser()
    assert other.get("/developer/editor?plugin=hello_plugin").status_code == 404


def test_directory_discovery_uses_existing_registry_and_surfaces_invalid(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(app.config, "PLUGINS_DIR", str(tmp_path))
    install(tmp_path, "zulu_plugin", "Zulu")
    install(tmp_path, "alpha_plugin", "alpha")
    (tmp_path / "unrelated").mkdir()
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "plugin.json").write_text("{}")
    unsafe = install(tmp_path, "unsafe_plugin")
    (unsafe / "leak").symlink_to("/etc/passwd")
    client, _ = browser()
    assert client.post("/developer/workspace/discovery").status_code == 403
    result = post(client, "discovery")
    assert result.status_code == 200
    assert sorted(result.json["registered"]) == ["alpha_plugin", "zulu_plugin"]
    assert {item["package"] for item in result.json["invalid"]} == {
        "broken",
        "unsafe_plugin",
    }
    assert post(client, "discovery").json["registered"] == []
    rows = client.get("/developer/workspace/plugins?management=1").json["plugins"]
    assert [r["name"] for r in rows] == ["alpha", "Zulu"]
    detail = client.get("/developer/workspace/plugins/alpha_plugin").json
    assert detail["manifest"]["author"] == "Analyst" and detail["manifest"][
        "permissions"
    ] == ["cases:read"]
    assert "plugins/alpha_plugin" in detail["location"] and detail["enabled"] == 0
    assert detail["validation"]["valid"] and detail["published_version"] is None
    # Refresh never replaces an edited registry snapshot with the directory copy.
    assert (
        post(
            client,
            "plugins/alpha_plugin/files",
            dict(revision=1, path="main.py", text="def run(context): return 5"),
        ).status_code
        == 200
    )
    post(client, "discovery")
    assert (
        b"return 5"
        in client.get(
            "/developer/workspace/plugins/alpha_plugin/file?path=main.py"
        ).data
    )


def test_manifest_metadata_errors_and_enable_state_are_not_silently_changed(
    monkeypatch,
):
    client, _ = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    for mode in ("validate", "test"):
        result = post(client, "plugins/hello_plugin/" + mode).json
        jobs[str(len(jobs) - 1)]["status"] = "Succeeded"
        client.get("/developer/workspace/executions/" + result["id"])
    assert (
        post(client, "plugins/hello_plugin/publish", {"revision": 1}).status_code == 200
    )
    assert (
        post(client, "plugins/hello_plugin/enable", {"enabled": True}).status_code
        == 200
    )
    value = metadata()
    value["name"] = "Updated manifest name"
    value["description"] = "New manifest description"
    assert (
        post(
            client,
            "plugins/hello_plugin/files",
            dict(revision=1, path="plugin.json", text=json.dumps(value)),
        ).status_code
        == 200
    )
    detail = client.get("/developer/workspace/plugins/hello_plugin").json
    assert (
        detail["enabled"] == 1
        and detail["name"] == "Updated manifest name"
        and detail["manifest"]["description"] == "New manifest description"
    )
    result = post(
        client,
        "plugins/hello_plugin/files",
        dict(revision=2, path="plugin.json", text='{"broken":'),
    )
    assert result.status_code == 200 and not result.json["validation"]["valid"]
    detail = client.get("/developer/workspace/plugins/hello_plugin").json
    assert detail["enabled"] == 1 and not detail["validation"]["valid"]
    assert (
        post(client, "plugins/hello_plugin/enable", {"enabled": True}).status_code
        == 409
    )
    assert (
        post(client, "plugins/hello_plugin/enable", {"enabled": False}).status_code
        == 200
    )
    assert not client.get("/developer/workspace/plugins?management=1").json["plugins"][
        0
    ]["package_valid"]


def test_case_independent_development_run_uses_draft_and_scoped_read_grant(monkeypatch):
    client, _ = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    with app.app_context():
        cid = (
            db()
            .execute(
                "INSERT INTO cases(number,name,created,stage) VALUES('DEV-INDEPENDENT','Case', '2026',1)"
            )
            .lastrowid
        )
        db().commit()
    result = post(client, "plugins/hello_plugin/develop")
    assert result.status_code == 202
    assert (
        jobs["0"]["value"]["mode"] == "develop"
        and jobs["0"]["value"]["context"]["case_id"] is None
    )
    headers = {"Authorization": "Bearer " + jobs["0"]["value"]["token"]}
    assert client.get("/api/v1/cases", headers=headers).status_code == 200
    assert client.get("/api/v1/cases/" + str(cid), headers=headers).status_code == 200
    assert (
        client.patch(
            "/api/v1/cases/" + str(cid), headers=headers, json={"name": "no"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    detail = client.get("/developer/workspace/plugins/hello_plugin").json
    assert (
        not detail["enabled"]
        and detail["published_version"] is None
        and detail["versions"] == []
    )
    assert (
        post(client, "plugins/hello_plugin/develop", {"case_id": cid}).status_code
        == 400
    )
    assert (
        post(client, "plugins/hello_plugin/develop", {"version": "1.0.0"}).status_code
        == 400
    )


def test_development_run_permissions_and_stream_persistence(monkeypatch):
    client, uid = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    result = post(client, "plugins/hello_plugin/develop").json
    worker_id = "0"

    def worker(method, path, value=None):
        return {
            "id": worker_id,
            "status": "Failed",
            "duration": 0.5,
            "output": "legacy",
            "exit_code": 1,
            "stdout": "printed\n",
            "stderr": "Traceback: error\n",
            "events": [{"sequence": 1, "stream": "stdout", "timestamp": 1}],
        }

    monkeypatch.setattr("developer_execution.call", worker)
    output = client.get("/developer/workspace/executions/" + result["id"]).json
    assert output["exit_code"] == 1
    assert output["stdout"] == "printed\n" and output["stderr"] == "Traceback: error\n"
    assert (
        client.get("/developer/workspace/executions/" + result["id"]).json["stderr"]
        == output["stderr"]
    )
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('only-read-plugins')")
        db().execute(
            "INSERT INTO role_permissions VALUES('only-read-plugins','plugins:read')"
        )
        db().execute("UPDATE users SET role='only-read-plugins' WHERE id=?", (uid,))
        db().commit()
    assert post(client, "plugins/hello_plugin/develop").status_code == 403
    assert (
        post(client, "plugins/hello_plugin/enable", {"enabled": True}).status_code
        == 403
    )


def test_worker_stdout_and_stderr_remain_separate_and_redacted():
    job = Job.__new__(Job)
    job.output = bytearray()
    job.exit_code = None
    job.streams = {"stdout": bytearray(), "stderr": bytearray()}
    job.events = []
    job.lock = threading.RLock()
    job.messages = []
    job.message_bytes = 0
    job.token = "super-secret"
    job.secrets = {"api_key": "private-key"}
    job.started = 0
    job.ended = 1
    job.id = "job"
    job.status = "Succeeded"
    job.append(b"print line\n", "stdout")
    job.append(b"exception super-secret private-key\n", "stderr")
    result = job.poll()
    assert (
        result["stdout"] == "print line\n"
        and "exception [REDACTED] [REDACTED]" in result["stderr"]
    )
    assert (
        "exception" not in result["stdout"]
        and "super-secret" not in json.dumps(result)
        and "private-key" not in json.dumps(result)
    )
    assert [event["stream"] for event in result["events"]] == ["stdout", "stderr"]


def test_discovery_requires_create_and_reports_scan_failures(tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "PLUGINS_DIR", str(tmp_path))
    install(tmp_path)
    client, uid = browser()
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('discovery-reader')")
        db().execute("INSERT INTO role_permissions VALUES('discovery-reader','plugins:read')")
        db().execute("UPDATE users SET role='discovery-reader' WHERE id=?", (uid,))
        db().commit()
    result = post(client, "discovery")
    assert result.status_code == 200 and not result.json["registered"]
    assert "plugins:create" in result.json["invalid"][0]["error"]
    assert not client.get("/developer/workspace/plugins").json["plugins"]
    monkeypatch.setattr("plugin_discovery.discover", lambda root: (_ for _ in ()).throw(OSError("scan denied")))
    result = post(client, "discovery")
    assert result.status_code == 503 and "scan denied" in result.json["error"]


def test_discovery_migration_preserves_existing_registry_snapshots():
    import sqlite3
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE schema_migrations(name TEXT PRIMARY KEY)")
    store.initialize(connection)
    connection.execute("ALTER TABLE developer_plugins DROP COLUMN source_location")
    connection.execute("INSERT INTO developer_plugins(id,owner_uuid,name,enabled,published_version,created_at,updated_at) VALUES('old_plugin','owner','Old',1,'1.0.0','before','before')")
    connection.execute("INSERT INTO developer_files VALUES('old_plugin','main.py',?,0)", (b'original snapshot',))
    connection.commit()
    store.initialize(connection)
    store.initialize(connection)
    assert connection.execute("SELECT enabled,published_version,source_location FROM developer_plugins").fetchone() == (1,'1.0.0',None)
    assert connection.execute("SELECT body FROM developer_files").fetchone()[0] == b'original snapshot'
    connection.close()


def test_control_center_metadata_permissions_configuration_and_activity(monkeypatch):
    client, uid = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    run = post(client, 'plugins/hello_plugin/develop').json
    jobs['0']['status'] = 'Failed'
    client.get('/developer/workspace/executions/' + run['id'])
    with app.app_context():
        db().execute('UPDATE developer_executions SET details=? WHERE id=?', (json.dumps({'stderr':'Traceback\nValueError: deliberate failure\n'}),run['id']))
        username = db().execute('SELECT username FROM users WHERE id=?',(uid,)).fetchone()[0]
        db().execute("INSERT INTO roles(name) VALUES('control-center-reader')")
        db().execute("INSERT INTO role_permissions VALUES('control-center-reader','plugins:read')")
        db().execute("UPDATE users SET role='control-center-reader' WHERE id=?",(uid,))
        db().commit()
    inventory = client.get('/developer/workspace/plugins?management=1').json['plugins']
    assert inventory[0]['manifest']['description'] == 'Example'
    assert inventory[0]['manifest']['version'] == '1.0.0'
    detail = client.get('/developer/workspace/plugins/hello_plugin').json
    assert detail['requested_permissions'] == ['cases:read']
    assert detail['granted_permissions'] == []
    assert client.get('/developer/workspace/plugins/hello_plugin/configuration').status_code == 403
    history = client.get('/developer/workspace/plugins/hello_plugin/history').json['executions']
    assert history[0]['initiating_user'] == username
    assert history[0]['error_summary'] == 'ValueError: deliberate failure'
    assert 'details' not in history[0]
    other, _ = browser()
    assert other.get('/developer/workspace/plugins/hello_plugin/history').json['executions'] == []
