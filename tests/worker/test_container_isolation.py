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
    reason="Requires a Linux rootless Podman worker and reviewed image digest",
)


def test_actual_container_boundary(tmp_path):
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
    supervisor = Supervisor(
        tmp_path, os.environ["MARE_TEST_WORKER_IMAGE"], "https://example.invalid"
    )
    result = supervisor.create(
        {
            "mode": "test",
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
    finally:
        job.stop()
