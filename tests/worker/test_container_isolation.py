"""Run explicitly on the deployment worker; no insecure local execution fallback."""

import base64
import os
from pathlib import Path
import time
import pytest
import plugin_store as store
from developer_worker.supervisor import Supervisor

pytestmark = pytest.mark.skipif(
    not os.environ.get("MARE_TEST_WORKER_IMAGE"),
    reason="Requires a Linux rootless Docker/Podman worker and reviewed image digest",
)


@pytest.mark.parametrize("mode", ["test", "develop"])
def test_actual_container_boundary(tmp_path, mode):
    value = dict(
        schema="mws-plugin/1",
        id="isolation_probe",
        name="Isolation probe",
        description="",
        version="1.0.0",
        author="Test",
        entrypoint="main.py:run",
        api_version="v1",
        sdk_version=">=1,<2",
        plugin_api="1",
        permissions=[],
        dependencies=[],
    )
    entries = store.template_files(value, "hello")
    entries["tests/test_plugin.py"][
        "body"
    ] = b"""import os,socket
from pathlib import Path
import pytest

def test_boundary():
    assert os.getuid()==10001
    for path in ('/data/workflow.sqlite3','/var/run/docker.sock','/run/podman/podman.sock','/Users','/app'):
        assert not Path(path).exists()
    with pytest.raises(OSError):Path('/etc/isolation-write').write_text('blocked')
    with pytest.raises(OSError):socket.create_connection(('1.1.1.1',443),timeout=1)
    assert not any('SECRET' in key or 'TOKEN' in key or 'API_KEY' in key for key in os.environ)
"""
    if mode == "develop":
        entries["main.py"]["body"] = entries["tests/test_plugin.py"]["body"] + b"""
def run(context):
    test_boundary()
    assert context.case_id is None
    print("development stdout", flush=True)
    context.log("development diagnostic")
    return {"developed": True}
"""
    supervisor = Supervisor(
        tmp_path, os.environ["MARE_TEST_WORKER_IMAGE"], "https://example.invalid",
        engine=os.environ.get("MARE_TEST_WORKER_ENGINE", "podman"),
    )
    result = supervisor.create(
        {
            "mode": mode,
            "archive": base64.b64encode(store.archive(entries)).decode(),
            "context": {},
        }
    )
    job = supervisor.jobs[result["id"]]
    try:
        until = time.monotonic() + 75
        while job.status in ("Starting", "Running") and time.monotonic() < until:
            time.sleep(0.1)
        assert job.status == "Succeeded", job.poll()
        assert job.cleaned.wait(5)
        assert not job.folder.exists()
        assert job.poll()["exit_code"] == 0
        if mode == "develop":
            output = job.poll()
            assert "development stdout" in output["stdout"]
            assert '"developed": true' in output["stdout"]
            assert "development diagnostic" in output["stderr"]
            assert "development diagnostic" not in output["stdout"]
    finally:
        job.stop()


@pytest.mark.parametrize("scenario", ["hello", "exception", "timeout", "cancel"])
def test_actual_execution_lifecycle(tmp_path, scenario):
    import subprocess
    value = dict(schema="mws-plugin/1", id="hello_plugin", name="Hello World",
                 description="", version="1.0.0", author="Test", entrypoint="main.py:run",
                 api_version="v1", sdk_version=">=1,<2", plugin_api="1",
                 permissions=[], dependencies=[])
    entries = store.template_files(value, "hello")
    source = {
        "hello": 'def run(context):\n print("Hello World")\n context.log("Hello diagnostic")\n',
        "exception": 'def run(context):\n raise ValueError("deliberate failure")\n',
        "timeout": 'import time\ndef run(context):\n time.sleep(120)\n',
        "cancel": 'import time\ndef run(context):\n print("ready", flush=True)\n time.sleep(120)\n',
    }[scenario]
    entries["main.py"]["body"] = source.encode()
    supervisor = Supervisor(tmp_path, os.environ["MARE_TEST_WORKER_IMAGE"],
                            "https://example.invalid",
                            engine=os.environ.get("MARE_TEST_WORKER_ENGINE", "podman"))
    result = supervisor.create(dict(mode="develop", context={},
                                   archive=base64.b64encode(store.archive(entries)).decode()))
    job = supervisor.jobs[result["id"]]
    try:
        if scenario == "cancel":
            deadline = time.monotonic() + 15
            while "ready" not in job.poll()["stdout"] and time.monotonic() < deadline:
                time.sleep(.1)
            assert "ready" in job.poll()["stdout"]
            job.stop()
        assert job.cleaned.wait(80), job.poll()
        result = job.poll()
        assert not job.folder.exists()
        assert result["exit_code"] is not None
        assert "[diagnostic]" in result["stderr"]
        if scenario == "hello":
            assert result["status"] == "Succeeded"
            assert result["exit_code"] == 0
            assert "Hello World" in result["stdout"]
            assert "Hello diagnostic" in result["stderr"]
        elif scenario == "exception":
            assert result["status"] == "Failed"
            assert "ValueError: deliberate failure" in result["stderr"]
            assert "ValueError" not in result["stdout"]
        else:
            assert result["status"] == ("Canceled" if scenario == "cancel" else "Timed out")
        listed = subprocess.run([supervisor.engine, "ps", "-aq", "--filter", "name=" + job.name],
                                capture_output=True, text=True, check=True,
                                env=supervisor.environment)
        assert not listed.stdout.strip()
    finally:
        job.stop()
        job.cleaned.wait(25)
