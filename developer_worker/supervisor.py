"""Dedicated rootless-Podman supervisor. Run as a separate unprivileged service user.

The web service communicates only through this private Unix socket. No container
engine socket, database, application directory or credentials enter a container.
"""

import base64
from collections import deque
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
MODES = {"validate", "test", "run", "language", "debug"}


def container_command(image, name, snapshot, gateway, mode):
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", image):
        raise ValueError(
            "Configure an administrator-built image pinned by SHA-256 digest."
        )
    if mode not in MODES:
        raise ValueError("Unsupported worker mode.")
    return [
        "podman",
        "run",
        "--rm",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--user=10001:10001",
        "--read-only",
        "--timeout=" + str(600 if mode in ("language", "debug") else 60),
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
        "-i",
        image,
        mode,
    ]


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
        path = self.path
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
        if job.mode != "run" and self.command != "GET":
            self.send_error(403, "Development sessions are read-only.")
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 2 * 1024 * 1024:
            self.send_error(413)
            return
        request = urllib.request.Request(
            job.origin + path,
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
        if job.mode != "run":
            self.send_error(
                403, "External connections are unavailable in development sessions."
            )
            return
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
        self.name = "mws-dev-" + self.id
        self.mode = value["mode"]
        self.started = time.monotonic()
        self.ended = None
        self.status = "Starting"
        self.output = bytearray()
        self.messages = deque()
        self.message_bytes = 0
        self.lock = threading.RLock()
        self.rpc_lock = threading.Lock()
        self.sequence = 0
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
        self.gateway = UnixServer(str(gateway / "api.sock"), Gateway)
        self.gateway.job = self
        os.chmod(gateway / "api.sock", 0o666)
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        try:
            self.process = subprocess.Popen(
                container_command(
                    supervisor.image, self.name, str(snapshot), str(gateway), self.mode
                ),
                stdin=subprocess.PIPE,
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
        protocol = self.mode in ("language", "debug")
        threading.Thread(
            target=self.read_protocol if protocol else self.read_output,
            args=() if protocol else (self.process.stdout,),
            daemon=True,
        ).start()
        threading.Thread(
            target=self.read_output, args=(self.process.stderr,), daemon=True
        ).start()
        threading.Thread(target=self.monitor, daemon=True).start()

    def append(self, raw):
        with self.lock:
            remaining = MAX_OUTPUT - len(self.output)
            self.output.extend(raw[: max(0, remaining)])
        if len(raw) > remaining:
            self.stop("Output limit exceeded")

    def read_output(self, stream):
        while True:
            chunk = stream.read1(4096)
            if not chunk:
                break
            self.append(chunk)

    def read_protocol(self):
        try:
            while True:
                headers = {}
                while True:
                    line = self.process.stdout.readline(8192)
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    name, value = line.decode().split(":", 1)
                    headers[name.lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if not 0 < length <= MAX_OUTPUT:
                    raise ValueError("Protocol message too large.")
                body = self.process.stdout.read(length)
                if len(body) != length:
                    return
                message = json.loads(body)
                with self.lock:
                    if (
                        len(self.messages) >= 250
                        or self.message_bytes + length > MAX_OUTPUT
                    ):
                        raise ValueError("Protocol queue exceeded limit.")
                    self.messages.append(message)
                    self.message_bytes += length
        except (OSError, ValueError):
            self.stop("Protocol limit exceeded")

    def exchange(self, message):
        if self.mode not in ("language", "debug"):
            raise ValueError("Not a development session.")
        with self.rpc_lock:
            body = json.dumps(message).encode()
            if len(body) > MAX_OUTPUT:
                raise ValueError("Protocol message exceeds limit.")
            if self.status != "Running":
                raise ValueError("Session ended.")
            self.process.stdin.write(
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            self.process.stdin.flush()
        return self.poll()

    def poll(self):
        with self.lock:
            messages = list(self.messages)
            self.messages.clear()
            self.message_bytes = 0
            output = bytes(self.output).decode("utf-8", "replace")
        # Tokens are never passed to the container, but redact defensively as well.
        if self.token:
            output = output.replace(self.token, "[REDACTED]")
        for secret in self.secrets.values():
            if secret:
                output = output.replace(secret, "[REDACTED]")
        return {
            "id": self.id,
            "status": self.status,
            "duration": round((self.ended or time.monotonic()) - self.started, 3),
            "output": output,
            "messages": messages,
        }

    def stop(self, status="Canceled"):
        with self.lock:
            if self.status not in ("Starting", "Running"):
                return
            self.status = status
        # Engine command has a fixed argv and service-owned container name.
        try:
            subprocess.run(
                ["podman", "kill", "--signal", "KILL", self.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                env=self.supervisor.environment,
            )
        finally:
            if self.process and self.process.poll() is None:
                self.process.kill()

    def monitor(self):
        timeout = 600 if self.mode in ("language", "debug") else 60
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
            with self.lock:
                if self.status == "Running":
                    self.status = (
                        "Succeeded" if self.process.returncode == 0 else "Failed"
                    )
                self.ended = time.monotonic()
            self.gateway.shutdown()
            self.gateway.server_close()
            shutil.rmtree(self.folder, ignore_errors=True)


class Supervisor:
    def __init__(self, root, image, origin):
        if os.geteuid() == 0:
            raise RuntimeError("Run the worker as a dedicated non-root user.")
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.image = image
        self.origin = origin.rstrip("/")
        self.connectors = json.loads(
            os.environ.get("MARE_DEVELOPER_CONNECTORS_JSON", "{}")
        )
        self.jobs = {}
        self.lock = threading.Lock()
        if not re.fullmatch(r"https://[^/?#@]+(?:/[^?#]*)?", self.origin):
            raise ValueError("Configure the trusted HTTPS API origin.")
        self.environment = {
            k: v
            for k, v in os.environ.items()
            if k
            in ("PATH", "HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "LANG")
        }
        result = subprocess.run(
            ["podman", "info", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=self.environment,
        )
        host = json.loads(result.stdout).get("host", {})
        security = host.get("security", {})
        if not security.get("rootless") or not security.get("seccompEnabled"):
            raise RuntimeError(
                "Rootless Podman with default seccomp confinement is required."
            )
        if host.get("cgroupVersion") != "v2" or not {"cpu", "memory", "pids"}.issubset(
            set(host.get("cgroupControllers", []))
        ):
            raise RuntimeError(
                "Delegated cgroup v2 CPU, memory and PID controllers are required."
            )
        container_command(image, "check", "/unused", "/unused", "validate")

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
                result = {"ready": True, "isolation": "rootless-podman", "protocol": 1}
            elif self.command == "POST" and self.path == "/jobs":
                result = supervisor.create(value)
            else:
                match = re.fullmatch(r"/jobs/([a-f0-9]{32})(/cancel|/rpc)?", self.path)
                if not match or match[1] not in supervisor.jobs:
                    raise ValueError("Session not found.")
                job = supervisor.jobs[match[1]]
                if match[2] == "/cancel" and self.command == "POST":
                    job.stop()
                    result = job.poll()
                elif match[2] == "/rpc" and self.command == "POST":
                    result = job.exchange(value)
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
    args = parser.parse_args()
    supervisor = Supervisor(args.work, args.image, args.api_origin)
    location = Path(args.socket)
    if location.exists():
        raise RuntimeError("Socket already exists; stop the old service first.")
    server = UnixServer(str(location), Handler)
    server.supervisor = supervisor
    os.chmod(location, 0o660)
    try:
        server.serve_forever()
    finally:
        for job in supervisor.jobs.values():
            job.stop()
        server.server_close()
        location.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
