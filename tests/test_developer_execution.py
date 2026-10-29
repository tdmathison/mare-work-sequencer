import base64
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
import pytest
from flask import g
from app import app, db
import developer_execution as execution
from developer_worker.supervisor import container_command, validated_snapshot
from developer_configuration import seal, unseal
from test_developer_shell import browser
from test_plugin_workspace import create, post, metadata
import plugin_store as store


def fake_worker(monkeypatch):
    jobs = {}

    def worker(method, path, value=None):
        if path == "/health":
            return {"ready": True}
        if path == "/jobs":
            key = str(len(jobs))
            jobs[key] = {"value": value, "status": "Running"}
            return dict(id=key, status="Running", messages=[], output="")
        parts = path.split("/")
        job = jobs[parts[2]]
        if path.endswith("/cancel"):
            job["status"] = "Canceled"
        return dict(
            id=parts[2],
            status=job["status"],
            duration=0.5,
            messages=[],
            output="verified output",
        )

    monkeypatch.setattr(execution, "call", worker)
    return jobs


def test_immutable_lifecycle_fingerprint_and_deletion(monkeypatch):
    client, _ = browser()
    draft = create(client)
    jobs = fake_worker(monkeypatch)
    assert (
        post(client, "plugins/hello_plugin/publish", dict(revision=1)).status_code
        == 409
    )
    for mode in ("validate", "test"):
        response = post(client, "plugins/hello_plugin/" + mode)
        assert response.status_code == 202
        eid = response.json["id"]
        jobs[str(len(jobs) - 1)]["status"] = "Succeeded"
        assert (
            client.get("/developer/workspace/executions/" + eid).json["status"]
            == "Succeeded"
        )
    assert (
        post(client, "plugins/hello_plugin/publish", dict(revision=1)).status_code
        == 200
    )
    assert (
        post(client, "plugins/hello_plugin/enable", dict(enabled=True)).status_code
        == 200
    )
    assert (
        post(
            client,
            "plugins/hello_plugin/files",
            dict(
                revision=1,
                path="main.py",
                text='def run(context):\n return "new draft"',
            ),
        ).status_code
        == 200
    )
    assert (
        post(client, "plugins/hello_plugin/publish", dict(revision=2)).status_code
        == 409
    )
    result = post(client, "plugins/hello_plugin/run")
    assert result.status_code == 202
    raw = base64.b64decode(jobs["2"]["value"]["archive"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert b"new draft" not in archive.read("main.py")
    eid = result.json["id"]
    assert (
        post(client, "plugins/hello_plugin/delete", dict(revision=2)).status_code == 200
    )
    assert (
        len(
            client.get("/developer/workspace/plugins/hello_plugin/history").json[
                "executions"
            ]
        )
        == 3
    )
    assert post(client, "executions/" + eid + "/cancel").status_code == 200
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT revoked FROM api_tokens WHERE id=(SELECT grant_id FROM developer_executions WHERE id=?)",
                (eid,),
            )
            .fetchone()[0]
        )


def test_development_grants_are_read_only_case_scoped_and_never_in_snapshot(
    monkeypatch,
):
    client, uid = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    with app.app_context():
        cid = (
            db()
            .execute(
                "INSERT INTO cases(number,name,stage,created) VALUES('DEV-1','Selected',1,'2026')"
            )
            .lastrowid
        )
        other = (
            db()
            .execute(
                "INSERT INTO cases(number,name,stage,created) VALUES('DEV-2','Other',1,'2026')"
            )
            .lastrowid
        )
        db().commit()
    result = post(client, "plugins/hello_plugin/test", dict(case_id=cid))
    assert result.status_code == 202
    value = jobs["0"]["value"]
    headers = {"Authorization": "Bearer " + value["token"]}
    assert value["token"] not in base64.b64decode(value["archive"]).decode("latin1")
    assert client.get("/api/v1/cases/" + str(cid), headers=headers).status_code == 200
    for path in (
        "/api/v1/cases",
        "/api/v1/tokens",
        "/api/v1/users",
        "/api/v1/metrics",
        "/api/v1/cases/" + str(other),
        f"/api/v1/cases/{cid}/assets",
    ):
        assert client.get(path, headers=headers).status_code == 403, path
    assert (
        client.patch(
            "/api/v1/cases/" + str(cid), json={"name": "forbidden"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        post(client, "executions/" + result.json["id"] + "/cancel").status_code == 200
    )
    assert client.get("/api/v1/cases/" + str(cid), headers=headers).status_code == 401


def test_protocol_boundary_and_session_ownership(monkeypatch):
    client, _ = browser()
    create(client)
    fake_worker(monkeypatch)
    eid = post(client, "plugins/hello_plugin/debug").json["id"]
    for message in (
        {"type": "request", "command": "attach"},
        {"type": "request", "command": "evaluate"},
        {
            "type": "request",
            "command": "setBreakpoints",
            "arguments": {"source": {"path": "/etc/passwd"}, "breakpoints": []},
        },
        {
            "type": "request",
            "command": "setBreakpoints",
            "arguments": {
                "source": {"path": "/work/main.py"},
                "breakpoints": [{"line": 1, "condition": "steal()"}],
            },
        },
    ):
        assert post(client, "executions/" + eid + "/rpc", message).status_code == 400
    other, _ = browser()
    assert other.get("/developer/workspace/executions/" + eid).status_code == 404
    assert post(other, "executions/" + eid + "/cancel").status_code == 404
    for uri in (
        "file:///etc/passwd",
        "file:///work/../etc/passwd",
        "file:///work/%2e%2e/x",
        "https://example.com",
    ):
        with pytest.raises(ValueError):
            execution.protocol_message(
                "language",
                dict(
                    method="textDocument/didOpen", params={"textDocument": {"uri": uri}}
                ),
            )
    assert (
        execution.protocol_message(
            "debug",
            {
                "type": "request",
                "command": "launch",
                "arguments": {"program": "/etc/passwd", "env": {"MWS_API_KEY": "bad"}},
            },
        )["arguments"]["program"]
        == "/opt/mws/debug_launcher.py"
    )


def test_rootless_container_resource_and_filesystem_contract():
    args = container_command(
        "localhost/mws@sha256:" + "a" * 64,
        "owned",
        "/tmp/snapshot",
        "/tmp/gateway",
        "run",
    )
    for value in (
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=512m",
        "--cpus=1",
        "--pull=never",
    ):
        assert value in args
    assert not any(
        "docker.sock" in part or "/data" in part or "--privileged" in part
        for part in args
    )
    with pytest.raises(ValueError):
        container_command("mutable:latest", "owned", "/tmp/a", "/tmp/b", "run")
    raw = store.archive(store.template_files(metadata(), "hello"))
    assert validated_snapshot(base64.b64encode(raw)) == raw
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../outside", "bad")
    with pytest.raises(ValueError):
        validated_snapshot(base64.b64encode(bad.getvalue()))


def test_configuration_encryption_types_redaction_and_exports():
    client, _ = browser()
    create(client)
    value = metadata()
    value["configuration"] = {
        "api_key": {"type": "string", "secret": True, "required": True},
        "maximum": {"type": "number", "default": 5},
        "enabled": {"type": "boolean"},
    }
    assert (
        post(
            client,
            "plugins/hello_plugin/files",
            dict(revision=1, path="plugin.json", text=json.dumps(value)),
        ).status_code
        == 200
    )
    config = post(
        client,
        "plugins/hello_plugin/configuration",
        dict(
            values={"maximum": 10, "enabled": False},
            secrets={"api_key": "very-private-secret"},
        ),
    )
    assert config.status_code == 200 and "very-private-secret" not in config.text
    assert config.json["configured_secrets"] == ["api_key"]
    assert (
        "very-private-secret"
        not in client.get(
            "/developer/workspace/plugins/hello_plugin/configuration"
        ).text
    )
    assert (
        post(
            client, "plugins/hello_plugin/configuration", dict(values={"maximum": True})
        ).status_code
        == 400
    )
    assert (
        post(
            client,
            "plugins/hello_plugin/configuration",
            dict(values={"api_key": "bad"}),
        ).status_code
        == 400
    )
    with app.app_context():
        row = db().execute("SELECT * FROM developer_plugins").fetchone()
        assert b"very-private-secret" not in row["secret_box"]
        assert unseal(row["secret_box"], app.config["SECRET_KEY"]) == {
            "api_key": "very-private-secret"
        }
    exported = client.get("/developer/workspace/plugins/hello_plugin/export").data
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert all(
            b"very-private-secret" not in archive.read(n) for n in archive.namelist()
        )


def test_selected_artifact_grant_does_not_allow_other_assets(monkeypatch):
    from app import ensure_package

    client, uid = browser()
    create(client)
    jobs = fake_worker(monkeypatch)
    with app.app_context():
        cid = (
            db()
            .execute(
                "INSERT INTO cases(number,name,stage,created) VALUES('ART-1','Artifact case',1,'2026')"
            )
            .lastrowid
        )
        db().commit()
        root = ensure_package(cid)
        (root / "scripts" / "chosen sample.txt").write_bytes(b"authorized bytes")
        (root / "scripts" / "other.txt").write_bytes(b"not selected")
    value = metadata()
    value["permissions"] = ["cases:read", "cases:assets"]
    assert (
        post(
            client,
            "plugins/hello_plugin/files",
            dict(revision=1, path="plugin.json", text=json.dumps(value)),
        ).status_code
        == 200
    )
    listed = client.get(f"/developer/workspace/cases/{cid}/artifacts")
    assert listed.status_code == 200 and any(
        a["path"] == "scripts/chosen sample.txt" for a in listed.json["artifacts"]
    )
    result = post(
        client,
        "plugins/hello_plugin/test",
        dict(case_id=cid, artifact="scripts/chosen sample.txt"),
    )
    assert result.status_code == 202
    headers = {"Authorization": "Bearer " + jobs["0"]["value"]["token"]}
    assert jobs["0"]["value"]["context"]["artifact"] == "scripts/chosen sample.txt"
    assert (
        client.get(
            f"/api/v1/cases/{cid}/assets/scripts/chosen%20sample.txt", headers=headers
        ).data
        == b"authorized bytes"
    )
    assert (
        client.get(
            f"/api/v1/cases/{cid}/assets/scripts/other.txt", headers=headers
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/cases/{cid}/assets", headers=headers).status_code == 403
    assert (
        client.post(f"/api/v1/cases/{cid}/assets", headers=headers).status_code == 403
    )


def test_worker_refuses_missing_resource_isolation(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from developer_worker.supervisor import Supervisor

    monkeypatch.setattr("developer_worker.supervisor.os.geteuid", lambda: 1000)
    for host in (
        {"security": {"rootless": False, "seccompEnabled": True}},
        {"security": {"rootless": True, "seccompEnabled": False}},
        {
            "security": {"rootless": True, "seccompEnabled": True},
            "cgroupVersion": "v1",
            "cgroupControllers": ["cpu", "memory", "pids"],
        },
        {
            "security": {"rootless": True, "seccompEnabled": True},
            "cgroupVersion": "v2",
            "cgroupControllers": ["cpu"],
        },
    ):
        monkeypatch.setattr(
            "developer_worker.supervisor.subprocess.run",
            lambda *a, **kw: SimpleNamespace(stdout=json.dumps({"host": host})),
        )
        with pytest.raises(RuntimeError):
            Supervisor(
                tmp_path, "localhost/mws@sha256:" + "a" * 64, "https://mws.example.test"
            )
