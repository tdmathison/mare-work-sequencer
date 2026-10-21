"""Bounded offline jobs. Execution requires an administrator's isolated runner."""

import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import threading
import time
import uuid
from signature_files import boundaries


def capture_format(raw, pcapng=False):
    if len(raw) < 24:
        raise ValueError("Capture is truncated; provide a PCAP file.")
    if raw[:4] == b"\x0a\x0d\x0d\x0a":
        if not pcapng:
            raise ValueError(
                "PCAPNG is disabled until the administrator confirms engine support. Use PCAP."
            )
        endian = (
            "<"
            if raw[8:12] == b"\x4d\x3c\x2b\x1a"
            else ">" if raw[8:12] == b"\x1a\x2b\x3c\x4d" else None
        )
        if not endian:
            raise ValueError("Invalid PCAPNG byte-order marker.")
        cursor = 0
        while cursor < len(raw):
            if cursor + 12 > len(raw):
                raise ValueError("Truncated PCAPNG block.")
            size = struct.unpack_from(endian + "I", raw, cursor + 4)[0]
            if (
                size < 12
                or size % 4
                or cursor + size > len(raw)
                or struct.unpack_from(endian + "I", raw, cursor + size - 4)[0] != size
            ):
                raise ValueError("Malformed PCAPNG block.")
            cursor += size
        return
    endian = {
        b"\xd4\xc3\xb2\xa1": "<",
        b"\xa1\xb2\xc3\xd4": ">",
        b"\x4d\x3c\xb2\xa1": "<",
        b"\xa1\xb2\x3c\x4d": ">",
    }.get(raw[:4])
    if not endian or struct.unpack_from(endian + "HH", raw, 4) != (2, 4):
        raise ValueError("Not a supported PCAP 2.4 capture.")
    snap = struct.unpack_from(endian + "I", raw, 16)[0]
    if not snap:
        raise ValueError("PCAP snap length must be positive.")
    cursor = 24
    while cursor < len(raw):
        if cursor + 16 > len(raw):
            raise ValueError("Truncated PCAP packet header.")
        size, original = struct.unpack_from(endian + "II", raw, cursor + 8)
        if size > snap or size > original or cursor + 16 + size > len(raw):
            raise ValueError("Invalid PCAP packet lengths.")
        cursor += 16 + size


def remove_work(path):
    # An engine cannot escape the mount, but it can change its output modes.
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    os.chmod(path, 0o700)
    for directory, children, _ in os.walk(path, followlinks=False):
        os.chmod(directory, 0o700)
        for child in children:
            p = Path(directory) / child
            if not p.is_symlink():
                os.chmod(p, 0o700)
    shutil.rmtree(path)


class Engine:
    def __init__(self, app, root):
        self.app = app
        self.root = Path(root) / "snort-jobs"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.cached = None
        self.cached_at = 0

    def run(self, args, work, cancel=lambda: False):
        process = subprocess.Popen(
            args,
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/nonexistent"},
        )
        logs = {"stdout": bytearray(), "stderr": bytearray()}
        sel = selectors.DefaultSelector()
        begin = time.monotonic()
        reason = ""
        for name in logs:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            sel.register(stream, selectors.EVENT_READ, name)

        def stop():
            if process.poll() is not None:
                return
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Some host sandboxes deny group signaling. The required runner
                # must kill its sandbox when its direct parent process dies.
                if process.poll() is None:
                    process.kill()

        try:
            while sel.get_map() or process.poll() is None:
                if cancel():
                    reason = "cancelled"
                if time.monotonic() - begin > self.app.config["SNORT_TIMEOUT"]:
                    reason = "timeout"
                if reason:
                    stop()
                for key, _ in sel.select(0.05):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data:
                        sel.unregister(key.fileobj)
                        continue
                    log = logs[key.data]
                    previous = len(log)
                    log.extend(data[: max(0, 65536 - previous)])
                    if len(data) + previous > 65536:
                        reason = reason or "output_limit"
                if reason and process.poll() is not None:
                    break
            code = process.wait(timeout=3)
            return dict(
                code=code,
                success=code == 0 and not reason,
                reason=reason,
                **{k: v.decode("utf-8", "replace") for k, v in logs.items()},
            )
        finally:
            if process.poll() is None:
                stop()
                process.wait(timeout=3)
            sel.close()
            process.stdout.close()
            process.stderr.close()

    def discover(self):
        if self.cached and time.time() - self.cached_at < 300:
            return self.cached
        result = dict(
            available=False,
            status="missing_engine",
            message="Snort is not configured. Editing, drafts and saving remain available.",
            version="",
            modules=[],
        )
        exe = self.app.config["SNORT_EXECUTABLE"]
        profile = self.app.config["SNORT_PROFILE"]
        runner = self.app.config["SNORT_RUNNER"]
        if exe and Path(exe).is_absolute() and os.access(exe, os.X_OK):
            try:
                detection = self.run([exe, "-V"], self.root)
                result["version"] = (detection["stdout"] + detection["stderr"])[:500]
                if not re.search(
                    r"(?:Version\s*|Snort\+\+\s*)3\.", result["version"], re.I
                ):
                    result.update(
                        status="unsupported_engine",
                        message="A Snort 3 engine is required.",
                    )
                elif (
                    not profile
                    or not Path(profile).is_absolute()
                    or not Path(profile).is_file()
                ):
                    result.update(
                        status="missing_configuration",
                        message="Administrator must configure a dedicated Snort profile.",
                    )
                elif (
                    os.name != "posix"
                    or not runner
                    or not Path(runner).is_absolute()
                    or not os.access(runner, os.X_OK)
                ):
                    result.update(
                        status="missing_isolation",
                        message="Administrator must install a least-privilege isolated offline runner.",
                    )
                else:
                    help_text = self.run([exe, "--help-options"], self.root)
                    text = help_text["stdout"] + help_text["stderr"]
                    modules = self.run([exe, "--list-modules"], self.root)
                    result["modules"] = re.findall(
                        r"\b[a-z][a-z_]+\b", modules["stdout"]
                    )[:2000]
                    if not all(
                        flag in text
                        for flag in ("-T", "-R", "-r", "-c", "--lua", "-A", "-l")
                    ):
                        result.update(
                            status="unsupported_capabilities",
                            message="Installed engine does not advertise required offline flags.",
                        )
                    else:
                        result.update(
                            available=True,
                            status="configured",
                            message="Snort 3 configured; each job validates the dedicated profile and current source before PCAP execution.",
                        )
            except (OSError, ValueError) as error:
                result.update(
                    status="discovery_failed",
                    message="Engine discovery failed: " + str(error),
                )
        self.cached = result
        self.cached_at = time.time()
        return result

    def write(self, directory, state):
        state["updated"] = time.time()
        temporary = directory / "status.tmp"
        temporary.write_text(json.dumps(state))
        os.replace(temporary, directory / "status.json")

    def read(self, directory):
        return json.loads((directory / "status.json").read_text())

    def cleanup(self):
        if os.name != "posix":
            return
        import fcntl

        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                with (directory / "lease").open("a+b") as lease:
                    try:
                        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        continue
                    try:
                        state = self.read(directory)
                    except (OSError, ValueError):
                        if (
                            time.time() - directory.stat().st_mtime
                            > self.app.config["SNORT_TIMEOUT"] * 3 + 60
                        ):
                            remove_work(directory / "work")
                            shutil.rmtree(directory)
                        continue
                    if state["status"] in ("queued", "running"):
                        remove_work(directory / "work")
                        state.update(
                            status="failed", error="Worker stopped before completion."
                        )
                        self.write(directory, state)
                    if (
                        time.time() - state["updated"]
                        > self.app.config["SNORT_JOB_TTL"]
                    ):
                        shutil.rmtree(directory)
            except (OSError, ValueError, KeyError):
                continue

    def submit(self, user, source, captures):
        import fcntl

        boundaries(source)
        if len(boundaries(source)) > 100:
            raise ValueError("At most 100 active rules per execution.")
        slot = None
        for i in range(self.app.config["SNORT_CONCURRENCY"]):
            stream = (self.root / f".slot-{i}").open("a+b")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                slot = stream
                break
            except BlockingIOError:
                stream.close()
        if slot is None:
            raise ValueError("Execution capacity is busy. Retry after a job finishes.")
        directory = self.root / uuid.uuid4().hex
        directory.mkdir(mode=0o700)
        lease = (directory / "lease").open("a+b")
        fcntl.flock(lease, fcntl.LOCK_EX)
        try:
            work = directory / "work"
            work.mkdir(mode=0o700)
            (work / "current.rules").write_bytes(source.encode())
            for name, raw in captures:
                (work / (name + ".pcap")).write_bytes(raw)
            state = dict(
                id=directory.name,
                user=user,
                status="queued",
                results=[],
                engine=self.discover()["version"],
                profile=Path(self.app.config["SNORT_PROFILE"]).name,
            )
            self.write(directory, state)
            queued = dict(state)
            queued.pop("user")
            threading.Thread(
                target=self.execute,
                args=(directory, state, slot, lease, captures),
                daemon=True,
            ).start()
            return queued
        except BaseException:
            lease.close()
            slot.close()
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def execute(self, directory, state, slot, lease, captures):
        try:
            state["status"] = "running"
            self.write(directory, state)
            cancel = lambda: (directory / "cancel").exists()
            base = [
                self.app.config["SNORT_RUNNER"],
                self.app.config["SNORT_EXECUTABLE"],
                self.app.config["SNORT_PROFILE"],
                str(directory / "work"),
            ]
            flags = [
                "-c",
                "/profile/" + Path(self.app.config["SNORT_PROFILE"]).name,
                "-R",
                "/work/current.rules",
            ]
            result = self.run(base + flags + ["-T"], directory / "work", cancel)
            state["validation"] = result
            if not result["success"]:
                raise ValueError(
                    result["reason"]
                    or "Engine rule/profile validation failed; see diagnostics."
                )
            for name, _ in captures:
                output = directory / "work" / "alert_json.txt"
                output.unlink(missing_ok=True)
                result = self.run(
                    base
                    + flags
                    + [
                        "-r",
                        "/work/" + name + ".pcap",
                        "-A",
                        "alert_json",
                        "-l",
                        "/work",
                        "--lua",
                        "alert_json = { file = true, fields = 'timestamp pkt_num proto src_ap dst_ap rule msg' }",
                    ],
                    directory / "work",
                    cancel,
                )
                entry = dict(capture=name, execution=result, alerts=[], alert_count=0)
                state["results"].append(entry)
                if not result["success"]:
                    raise ValueError(
                        result["reason"] or "PCAP execution failed; see diagnostics."
                    )
                if output.exists() or output.is_symlink():
                    fd = os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        meta = os.fstat(stream.fileno())
                        if (
                            not stat.S_ISREG(meta.st_mode)
                            or meta.st_size >= 16 * 1024 * 1024
                        ):
                            raise ValueError("Unsafe or oversized engine alert output.")
                        for line in stream:
                            alert = json.loads(line)
                            if not isinstance(alert, dict) or "rule" not in alert:
                                raise ValueError("Malformed alert output.")
                            entry["alert_count"] += 1
                            if len(entry["alerts"]) < 200:
                                entry["alerts"].append(alert)
                self.write(directory, state)
            state["status"] = "completed"
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            state.update(
                status="cancelled" if (directory / "cancel").exists() else "failed",
                error=str(error),
            )
        finally:
            try:
                remove_work(directory / "work")
            except OSError as error:
                state.update(
                    status="failed", error="Temporary cleanup failed: " + str(error)
                )
            try:
                self.write(directory, state)
            finally:
                lease.close()
                slot.close()
