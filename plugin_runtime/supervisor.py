"""Dedicated rootless-Podman supervisor. Run as a separate unprivileged service user.

The web service communicates only through this private Unix socket. No container
engine socket, database, application directory or credentials enter a container.
"""

import base64
from http.server import BaseHTTPRequestHandler
import io
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.request
import urllib.parse
import zipfile

MAX_OUTPUT = 256 * 1024
MODES = {"run"}


def container_command(image, name, snapshot, gateway, mode, engine="podman"):
    if engine not in ("docker", "podman"):
        raise ValueError("Unsupported container engine.")
    if not re.fullmatch(r"(?:[a-zA-Z0-9./:_-]+@)?sha256:[a-f0-9]{64}", image):
        raise ValueError(
            "Configure an administrator-built image pinned by SHA-256 digest."
        )
    if mode not in MODES:
        raise ValueError("Unsupported worker mode.")
    command = [
        engine,
        "run",
        "--rm",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--user=10001:10001",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--cpus=1",
        "--memory=512m",
        "--memory-swap=512m",
        "--ulimit",
        "nofile=128:128",
        "--ulimit",
        "core=0:0",
        "--log-driver=none",
        "--tmpfs",
        "/work:rw,nosuid,nodev,size=64m,mode=1777",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
        "--mount",
        f"type=bind,src={snapshot},dst=/snapshot,ro=true",
        "--mount",
        f"type=bind,src={gateway},dst=/gateway,ro=true",
        image,
        mode,
    ]

    return command


def validated_snapshot(encoded):
    # Independent bounded extraction checks at the execution boundary.
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Archive exceeds limit.")
    total = 0
    compressed_total = 0
    seen = set()
    types = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > 200:
            raise ValueError("Too many files.")
        for entry in archive.infolist():
            path = entry.filename.rstrip("/")
            parts = path.split("/")
            if (
                not path
                or len(path.encode("utf-8")) > 240
                or path.startswith("/")
                or "\\" in path
                or ":" in path
                or any(
                    p in ("", "..", ".")
                    or p.casefold()
                    in (".git", ".env", ".venv", "logs", "secrets", "__pycache__")
                    for p in parts
                )
                or any(ord(c) < 32 for c in path)
            ):
                raise ValueError("Unsafe archive path.")
            mode = (entry.external_attr >> 16) & 0o170000
            if (
                mode not in (0, 0o100000, 0o040000)
                or entry.flag_bits & 1
                or path.casefold() in seen
            ):
                raise ValueError("Unsafe archive entry.")
            seen.add(path.casefold())
            types[path] = entry.is_dir()
            compressed_total += entry.compress_size
            if compressed_total > 20 * 1024 * 1024 or entry.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise ValueError("Archive compression exceeds supported limits.")
            total += entry.file_size
            if entry.file_size > 2 * 1024 * 1024 or total > 20 * 1024 * 1024:
                raise ValueError("Archive expansion exceeds limits.")
            archive.read(entry)
        for path in types:
            for i in range(1, len(path.split("/"))):
                parent = "/".join(path.split("/")[:i])
                if parent in types and not types[parent]:
                    raise ValueError("File/directory conflict.")
    return raw


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Gateway(BaseHTTPRequestHandler):
    """A per-container API bridge; real bearer credentials remain in supervisor memory."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_PUT(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def do_DELETE(self):
        self.forward()

    def forward(self):
        job = self.server.job
        # This independent allowlist supplements the authoritative scoped API grant.
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.scheme or parsed.netloc or len(parsed.query) > 4096:
            self.send_error(403)
            return
        path = parsed.path
        if path == "/external" and self.command == "POST":
            self.external(job)
            return
        decoded = urllib.parse.unquote(path, errors="strict")
        artifact_path = (
            "/api/v1/cases/"
            + str(job.context.get("case_id"))
            + "/assets/"
            + str(job.context.get("artifact"))
        )
        if "/assets/" in decoded and (
            decoded != artifact_path or self.command != "GET"
        ):
            self.send_error(403, "Select an authorized artifact first.")
            return
        prefix = "/api/v1/cases/" + str(job.context.get("case_id"))
        if (
            not job.token
            or not (path == prefix or path.startswith(prefix + "/"))
            or any(c in decoded for c in ("\\", "..", "?", "#"))
        ):
            self.send_error(403, "Only the selected case is accessible.")
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 2 * 1024 * 1024:
            self.send_error(413)
            return
        request = urllib.request.Request(
            job.origin + self.path,
            data=self.rfile.read(size) if size else None,
            method=self.command,
            headers={
                "Authorization": "Bearer " + job.token,
                "Content-Type": self.headers.get("Content-Type", "application/json"),
            },
        )
        try:
            upstream = urllib.request.build_opener(NoRedirect).open(request, timeout=15)
        except urllib.error.HTTPError as error:
            upstream = error
        except (OSError, ValueError):
            self.send_error(502, "API gateway unavailable.")
            return
        with upstream:
            body = upstream.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                self.send_error(413)
                return
            # Never forward cookies, redirects, or unrelated upstream headers.
            self.send_response(upstream.status)
            self.send_header(
                "Content-Type", upstream.headers.get("Content-Type", "application/json")
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def external(self, job):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16000:
                raise ValueError("Invalid connector request.")
            value = json.loads(self.rfile.read(size))
            name = value.get("service")
            path = value.get("path", "")
            connector = job.supervisor.connectors.get(name)
            if (
                not connector
                or not isinstance(path, str)
                or not re.fullmatch(r"/[A-Za-z0-9/_-]*", path)
                or ".." in path
            ):
                raise ValueError("Connector or path is not approved.")
            origin = connector["origin"]
            if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?", origin):
                raise ValueError("Invalid connector origin.")
            secret = job.secrets.get(connector.get("secret_field", ""))
            headers = {}
            if secret:
                headers[connector.get("header", "Authorization")] = (
                    connector.get("prefix", "Bearer ") + secret
                )
            request = urllib.request.Request(
                origin + path, headers=headers, method="GET"
            )
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=10
            ) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("Connector response exceeds limit.")
                result = json.loads(raw)
            text = json.dumps(result)
            for secret in job.secrets.values():
                if secret:
                    text = text.replace(secret, "[REDACTED]")
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, KeyError, TypeError, OSError):
            self.send_error(502, "Approved connector request failed.")


class Job:
    def __init__(self, supervisor, value):
        self.supervisor = supervisor
        self.id = uuid.uuid4().hex
        self.name = "mws-plugin-" + self.id
        self.mode = value["mode"]
        self.started = time.monotonic()
        self.ended = None
        self.exit_code = None
        self.requested_status = None
        self.cleaned = threading.Event()
        self.status = "Starting"
        self.output = bytearray()
        self.streams = {"stdout": bytearray(), "stderr": bytearray()}
        self.events = []
        self.readers = []
        self.lock = threading.RLock()
        self.process = None
        self.secrets = value.get("secrets", {})
        self.token = value.get("token", "")
        self.origin = supervisor.origin
        self.context = value.get("context", {})
        raw = validated_snapshot(value["archive"])
        self.folder = Path(tempfile.mkdtemp(prefix="job-", dir=supervisor.root))
        snapshot = self.folder / "snapshot"
        snapshot.mkdir(mode=0o755)
        gateway = self.folder / "gateway"
        gateway.mkdir(mode=0o755)
        (snapshot / "plugin.zip").write_bytes(raw)
        (snapshot / "context.json").write_text(
            json.dumps({**self.context, "mode": self.mode})
        )
        for file in snapshot.iterdir():
            file.chmod(0o644)
        self.gateway = UnixServer(str(gateway / "api.sock"), Gateway)
        self.gateway.job = self
        os.chmod(gateway / "api.sock", 0o666)
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        try:
            self.process = subprocess.Popen(
                container_command(
                    supervisor.image, self.name, str(snapshot), str(gateway), self.mode, supervisor.engine
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                env=supervisor.environment,
            )
        except Exception:
            self.gateway.shutdown()
            self.gateway.server_close()
            shutil.rmtree(self.folder)
            raise
        self.status = "Running"
        self.append(b"[diagnostic] Isolated execution started.\n", "stderr")
        stdout_reader = threading.Thread(target=self.read_output,args=(self.process.stdout,"stdout"),daemon=True)
        stderr_reader = threading.Thread(
            target=self.read_output, args=(self.process.stderr, "stderr"), daemon=True
        )
        self.readers = [stdout_reader, stderr_reader]
        for reader in self.readers:
            reader.start()
        threading.Thread(target=self.monitor, daemon=True).start()

    def append(self, raw, channel="stdout"):
        with self.lock:
            remaining = MAX_OUTPUT - len(self.output)
            chunk = raw[: max(0, remaining)]
            self.output.extend(chunk)
            self.streams[channel].extend(chunk)
            if chunk:
                self.events.append(
                    {
                        "sequence": len(self.events) + 1,
                        "timestamp": time.time(),
                        "stream": channel,
                        "bytes": len(chunk),
                    }
                )
        if len(raw) > remaining or len(self.events) > 512:
            self.stop("Output limit exceeded")

    def read_output(self, stream, channel="stdout"):
        while True:
            chunk = stream.read1(4096)
            if not chunk:
                break
            self.append(chunk, channel)



    def poll(self):
        with self.lock:
            output = bytes(self.output).decode("utf-8", "replace")
            streams = {
                key: bytes(raw).decode("utf-8", "replace")
                for key, raw in self.streams.items()
            }
            events = [dict(event) for event in self.events]

        def redact(text):
            for secret in [self.token, *self.secrets.values()]:
                if secret:
                    text = text.replace(secret, "[REDACTED]")
            return text

        streams = {key: redact(text) for key, text in streams.items()}
        # Tokens are never passed to the container, but redact defensively as well.
        if self.token:
            output = output.replace(self.token, "[REDACTED]")
        for secret in self.secrets.values():
            if secret:
                output = output.replace(secret, "[REDACTED]")
        return {
            "id": self.id,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration": round((self.ended or time.monotonic()) - self.started, 3),
            "output": output,
            **streams,
            "events": events,
        }

    def stop(self, status="Canceled"):
        with self.lock:
            if self.status not in ("Starting", "Running") or self.requested_status:
                return
            self.requested_status = status
        # Engine command has a fixed argv and service-owned container name.
        try:
            subprocess.run(
                [self.supervisor.engine, "kill", "--signal", "KILL", self.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                env=self.supervisor.environment,
            )
        finally:
            if self.process and self.process.poll() is None:
                self.process.kill()

    def monitor(self):
        timeout = 60
        try:
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    self.stop("Timed out")
                except (OSError, subprocess.SubprocessError):
                    pass
                self.process.wait(timeout=15)
        finally:
            for reader in self.readers:
                reader.join(timeout=2)
            # Explicit removal also handles a killed CLI or a failed attach. Never
            # leave a container behind merely because the client process exited.
            try:
                subprocess.run(
                    [self.supervisor.engine, "rm", "--force", self.name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, env=self.supervisor.environment,
                )
            finally:
                self.gateway.shutdown()
                self.gateway.server_close()
                shutil.rmtree(self.folder, ignore_errors=True)
                with self.lock:
                    self.exit_code = self.process.returncode
                    self.status = self.requested_status or (
                        "Succeeded" if self.exit_code == 0 else "Failed"
                    )
                    self.ended = time.monotonic()
                    self.append(("[diagnostic] Execution " + self.status + "; exit code " + str(self.exit_code) + ".\n").encode(), "stderr")
                self.cleaned.set()



class Supervisor:
    def __init__(self, root, image, origin, engine="podman"):
        if os.geteuid() == 0:
            raise RuntimeError("Run the worker as a dedicated non-root user.")
        if engine not in ("docker", "podman"):
            raise ValueError("Unsupported container engine.")
        self.engine = engine
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.image = image
        self.origin = origin.rstrip("/")
        self.connectors = json.loads(
            os.environ.get("MARE_PLUGIN_CONNECTORS_JSON", "{}")
        )
        self.jobs = {}
        self.lock = threading.Lock()
        if not re.fullmatch(r"https://[^/?#@]+(?:/[^?#]*)?", self.origin):
            raise ValueError("Configure the trusted HTTPS API origin.")
        self.environment = {
            k: v
            for k, v in os.environ.items()
            if k
            in ("PATH", "HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "LANG", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")
        }
        result = subprocess.run(
            [engine, "info", "--format", "{{json .}}" if engine == "docker" else "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=self.environment,
        )
        info = json.loads(result.stdout)
        if engine == "docker":
            options = info.get("SecurityOptions", [])
            if not any("rootless" in option for option in options) or not any(
                "seccomp" in option and "unconfined" not in option for option in options
            ):
                raise RuntimeError("Rootless Docker with default seccomp confinement is required.")
            if (str(info.get("CgroupVersion")) != "2"
                or info.get("CgroupDriver") != "systemd"
                or not all(info.get(key) for key in ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit"))):
                raise RuntimeError("Docker requires cgroup v2 with systemd and CPU, memory, swap and PID limits.")
        else:
            host = info.get("host", {})
            security = host.get("security", {})
            if not security.get("rootless") or not security.get("seccompEnabled"):
                raise RuntimeError("Rootless Podman with default seccomp confinement is required.")
            if host.get("cgroupVersion") != "v2" or not {"cpu", "memory", "pids"}.issubset(
                set(host.get("cgroupControllers", []))
            ):
                raise RuntimeError("Delegated cgroup v2 CPU, memory and PID controllers are required.")
        container_command(image, "check", "/unused", "/unused", "run", engine)
        self.health()

    def health(self):
        # A configured socket alone does not mean the engine/image is available.
        subprocess.run(
            [self.engine, "image", "inspect", self.image], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10,
            env=self.environment,
        )
        return {"ready": True, "isolation": "rootless-" + self.engine, "protocol": 1}

    def create(self, value):
        with self.lock:
            # Bounded retained history; authoritative records live in MWS.
            self.jobs = {
                key: j
                for key, j in self.jobs.items()
                if j.status in ("Starting", "Running")
                or time.monotonic() - j.started < 3600
            }
            if (
                len(self.jobs) >= 32
                or sum(j.status == "Running" for j in self.jobs.values()) >= 4
            ):
                raise ValueError("Worker capacity reached.")
            job = Job(self, value)
            self.jobs[job.id] = job
            return job.poll()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 29 * 1024 * 1024:
                raise ValueError("Request exceeds limit.")
            value = json.loads(self.rfile.read(length)) if length else {}
            supervisor = self.server.supervisor
            if self.command == "GET" and self.path == "/health":
                result = supervisor.health()
            elif self.command == "POST" and self.path == "/jobs":
                result = supervisor.create(value)
            else:
                match = re.fullmatch(r"/jobs/([a-f0-9]{32})(/cancel)?", self.path)
                if not match or match[1] not in supervisor.jobs:
                    raise ValueError("Session not found.")
                job = supervisor.jobs[match[1]]
                if match[2] == "/cancel" and self.command == "POST":
                    job.stop()
                    job.cleaned.wait(timeout=20)
                    result = job.poll()
                elif not match[2] and self.command == "GET":
                    result = job.poll()
                else:
                    raise ValueError("Unsupported operation.")
            body = json.dumps(result).encode()
            self.send_response(200)
        except (
            ValueError,
            KeyError,
            TypeError,
            OSError,
            subprocess.SubprocessError,
        ) as error:
            body = json.dumps({"error": str(error)[:500]}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--api-origin", required=True)
    parser.add_argument("--engine", choices=("docker", "podman"), default="podman")
    args = parser.parse_args()
    supervisor = Supervisor(args.work, args.image, args.api_origin, args.engine)
    location = Path(args.socket)
    if location.exists():
        raise RuntimeError("Socket already exists; stop the old service first.")
    server = UnixServer(str(location), Handler)
    server.supervisor = supervisor
    os.chmod(location, 0o660)
    import signal

    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    finally:
        for job in supervisor.jobs.values():
            job.stop()
        for job in supervisor.jobs.values():
            job.cleaned.wait(timeout=25)
        server.server_close()
        location.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
