"""Docker adapter contracts; these tests do not prove container isolation."""
import json
from types import SimpleNamespace

import pytest

from plugin_runtime.supervisor import Supervisor, container_command

IMAGE = "sha256:" + "a" * 64


def docker_info():
    return dict(SecurityOptions=["name=rootless", "name=seccomp,profile=builtin"],
                CgroupVersion="2", CgroupDriver="systemd", MemoryLimit=True,
                SwapLimit=True, CpuCfsQuota=True, PidsLimit=True)


def test_docker_argv_has_limits_without_podman_only_flags():
    args = container_command(IMAGE, "job", "/snapshot", "/gateway", "run", "docker")
    assert args[:3] == ["docker", "run", "--rm"]
    for flag in ("--network=none", "--user=10001:10001", "--read-only",
                 "--cap-drop=ALL", "--security-opt=no-new-privileges",
                 "--pids-limit=64", "--cpus=1", "--memory=512m",
                 "--memory-swap=512m", "--pull=never"):
        assert flag in args
    assert not any(arg.startswith("--timeout") for arg in args)
    assert not any(arg in args for arg in ("--privileged", "--pid=host", "--network=host"))
    assert args[-2:] == [IMAGE, "run"]


@pytest.mark.parametrize("change", [
    {"SecurityOptions": ["name=seccomp,profile=builtin"]},
    {"SecurityOptions": ["name=rootless"]},
    {"CgroupVersion": "1"}, {"CgroupDriver": "cgroupfs"},
    {"MemoryLimit": False}, {"CpuCfsQuota": False}, {"PidsLimit": False},
])
def test_docker_fails_closed_without_isolation(monkeypatch, tmp_path, change):
    info = {**docker_info(), **change}
    monkeypatch.setattr("plugin_runtime.supervisor.os.geteuid", lambda: 1000)
    monkeypatch.setattr("plugin_runtime.supervisor.subprocess.run",
                        lambda *a, **kw: SimpleNamespace(stdout=json.dumps(info)))
    with pytest.raises(RuntimeError):
        Supervisor(tmp_path, IMAGE, "https://mws.example.test", "docker")


def test_docker_startup_checks_pinned_image_and_preserves_only_engine_config(monkeypatch, tmp_path):
    calls = []
    def command(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=json.dumps(docker_info()))
    monkeypatch.setattr("plugin_runtime.supervisor.subprocess.run", command)
    monkeypatch.setattr("plugin_runtime.supervisor.os.geteuid", lambda: 1000)
    monkeypatch.setenv("DATABASE_PASSWORD", "forbidden")
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/user/1000/docker.sock")
    supervisor = Supervisor(tmp_path, IMAGE, "https://mws.example.test", "docker")
    assert supervisor.health()["isolation"] == "rootless-docker"
    assert calls[1][0] == ["docker", "image", "inspect", IMAGE]
    assert "DATABASE_PASSWORD" not in supervisor.environment
    assert supervisor.environment["DOCKER_HOST"].endswith("docker.sock")


@pytest.mark.parametrize("timed_out", [False, True])
def test_job_completion_waits_for_cleanup_and_reports_streams(monkeypatch, tmp_path, timed_out):
    import base64
    import io
    import subprocess
    from plugin_runtime.supervisor import Job
    import plugin_store as store
    from plugin_fixtures import metadata, package_entries

    calls = []
    def gateway(path, handler):
        from pathlib import Path
        Path(path).touch()
        return SimpleNamespace(serve_forever=lambda: None, shutdown=lambda: None,
                               server_close=lambda: None)
    monkeypatch.setattr("plugin_runtime.supervisor.UnixServer", gateway)
    class Process:
        def __init__(self):
            self.stdout = io.BytesIO(b"hello\n")
            self.stderr = io.BytesIO(b"exception details\n")
            self.stdin = io.BytesIO()
            self.returncode = None
            self.waits = 0
        def wait(self, timeout):
            self.waits += 1
            if timed_out and self.waits == 1:
                assert timeout == 60
                raise subprocess.TimeoutExpired("docker", timeout)
            self.returncode = -9 if timed_out else 0
            return self.returncode
        def poll(self):
            return self.returncode
        def kill(self):
            self.returncode = -9

    def spawn(args, **kwargs):
        calls.append(args)
        snapshot = next(arg for arg in args if "dst=/snapshot" in arg).split("src=", 1)[1].split(",", 1)[0]
        from pathlib import Path
        assert all(file.stat().st_mode & 0o044 == 0o044 for file in Path(snapshot).iterdir())
        return Process()
    monkeypatch.setattr("plugin_runtime.supervisor.subprocess.Popen", spawn)
    monkeypatch.setattr("plugin_runtime.supervisor.subprocess.run", lambda args, **kw: calls.append(args))
    supervisor = SimpleNamespace(root=tmp_path, image=IMAGE, engine="docker",
                                 origin="https://example.invalid", environment={})
    job = Job(supervisor, dict(mode="run", context={},
                              archive=base64.b64encode(store.archive(package_entries(metadata()))).decode()))
    assert job.cleaned.wait(5)
    assert not job.folder.exists()
    result = job.poll()
    assert result["stdout"] == "hello\n"
    assert "exception details" in result["stderr"]
    assert "[diagnostic]" in result["stderr"]
    assert result["status"] == ("Timed out" if timed_out else "Succeeded")
    assert result["exit_code"] == (-9 if timed_out else 0)
    assert ["docker", "rm", "--force", job.name] in calls
    if timed_out:
        assert ["docker", "kill", "--signal", "KILL", job.name] in calls
