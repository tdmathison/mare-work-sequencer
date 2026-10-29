"""Real Editor API -> Unix RPC -> container test; requires a deployment engine."""
import os
from pathlib import Path
import tempfile
import threading
import time

import pytest

from developer_worker.supervisor import Handler, Supervisor, UnixServer
from test_developer_shell import browser
from test_plugin_workspace import create, post


@pytest.mark.skipif(not os.environ.get("MARE_TEST_WORKER_IMAGE"),
                    reason="Requires an actual Linux rootless execution worker")
def test_editor_api_runs_hello_through_isolated_worker(monkeypatch):
    # Keep Unix socket paths below platform length limits.
    with tempfile.TemporaryDirectory(prefix="mws-rpc-", dir="/tmp") as directory:
        supervisor = Supervisor(Path(directory) / "jobs", os.environ["MARE_TEST_WORKER_IMAGE"],
                                "https://example.invalid",
                                engine=os.environ.get("MARE_TEST_WORKER_ENGINE", "podman"))
        location = str(Path(directory) / "worker.sock")
        server = UnixServer(location, Handler)
        server.supervisor = supervisor
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv("MARE_DEVELOPER_WORKER_SOCKET", location)
        try:
            client, _ = browser()
            create(client)
            saved = post(client, "plugins/hello_plugin/files", dict(
                revision=1, path="main.py",
                text='def run(context):\n print("Hello World")\n context.log("Hello diagnostic")\n'))
            assert saved.status_code == 200
            started = post(client, "plugins/hello_plugin/develop")
            assert started.status_code == 202, started.text
            eid = started.json["id"]
            deadline = time.monotonic() + 75
            result = started.json
            while result["status"] in ("Starting", "Running") and time.monotonic() < deadline:
                time.sleep(.1)
                response = client.get("/developer/workspace/executions/" + eid)
                assert response.status_code == 200, response.text
                result = response.json
            assert result["status"] == "Succeeded", result
            assert result["exit_code"] == 0
            assert "Hello World" in result["stdout"]
            assert "Hello diagnostic" in result["stderr"]
            assert "Hello diagnostic" not in result["stdout"]
            assert all(job.cleaned.is_set() and not job.folder.exists() for job in supervisor.jobs.values())
            assert client.get("/developer/workspace/executions/" + eid).json["exit_code"] == 0
        finally:
            for job in supervisor.jobs.values():
                job.stop()
                job.cleaned.wait(25)
            server.shutdown()
            server.server_close()
            thread.join(5)
