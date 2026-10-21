"""Classic YARA jobs reusing MARE's bounded process/lease/cleanup infrastructure."""

import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys
import threading
import time
import uuid
from snort_engine import Engine, remove_work


class YaraEngine(Engine):
    def __init__(self, app, root):
        # Existing generic process and file-lease methods use legacy config keys.
        # Adapt only those limits; do not alter Snort configuration or validation.
        self.app = SimpleNamespace(
            config={
                "SNORT_TIMEOUT": app.config["YARA_TIMEOUT"],
                "SNORT_JOB_TTL": app.config["YARA_JOB_TTL"],
            }
        )
        self.config = app.config
        self.root = Path(root) / "yara-jobs"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.worker = str(Path(__file__).parent / "deploy/yara-worker.py")
        self.python = app.config["YARA_PYTHON"]
        self.cached = None
        self.cached_at = 0

    def discover(self):
        if self.cached and time.time() - self.cached_at < 60:
            return self.cached
        info = dict(
            available=False,
            version="",
            profile="classic YARA 4.5.4",
            message="Engine unavailable. Install requirements-yara.txt; editing and saving remain available.",
        )
        if (
            os.name == "posix"
            and Path(self.python).is_absolute()
            and os.access(self.python, os.X_OK)
        ):
            try:
                result = self.run(
                    [self.python, "-I", self.worker, "--version"], self.root
                )
                if result["success"]:
                    info.update(json.loads(result["stdout"]))
            except (OSError, ValueError):
                pass
        self.cached, self.cached_at = info, time.time()
        return info

    def submit(self, user, source, samples, labels=None):
        import fcntl

        if not self.discover()["available"]:
            raise ValueError(
                "Engine unavailable; install the pinned classic YARA binding."
            )
        self.cleanup()
        slot = None
        for index in range(self.config["YARA_CONCURRENCY"]):
            candidate = (self.root / f".slot-{index}").open("a+b")
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                slot = candidate
                break
            except BlockingIOError:
                candidate.close()
        if slot is None:
            raise ValueError("YARA job capacity is busy. Retry after a job finishes.")
        directory = self.root / uuid.uuid4().hex
        directory.mkdir(mode=0o700)
        lease = (directory / "lease").open("a+b")
        fcntl.flock(lease, fcntl.LOCK_EX)
        try:
            work = directory / "work"
            work.mkdir(mode=0o700)
            (work / "source.yara").write_bytes(source.encode())
            for name, raw in samples:
                (work / (name + ".sample")).write_bytes(raw)
            state = dict(
                id=directory.name,
                user=user,
                status="queued",
                results=[],
                diagnostics=[],
                compiled=False,
                engine="classic YARA 4.5.4",
                sample_names=labels or {},
            )
            self.write(directory, state)
            queued = {k: v for k, v in state.items() if k != "user"}
            threading.Thread(
                target=self.execute, args=(directory, state, slot, lease), daemon=True
            ).start()
            return queued
        except BaseException:
            lease.close()
            slot.close()
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def execute(self, directory, state, slot, lease):
        try:
            state["status"] = "running"
            self.write(directory, state)
            cancelled = lambda: (directory / "cancel").exists()
            execution = self.run(
                [self.python, "-I", self.worker], directory / "work", cancelled
            )
            state["execution"] = execution
            if not execution["success"]:
                raise ValueError(
                    execution["reason"]
                    or "Compiler/scanner process failed; see bounded logs."
                )
            result = json.loads(execution["stdout"])
            if not isinstance(result.get("compiled"), bool):
                raise ValueError("Invalid compiler response.")
            state.update(result)
            state["status"] = (
                "completed"
                if result["compiled"]
                and not any(r["status"] == "error" for r in result["results"])
                else "failed"
            )
            if cancelled():
                state["status"] = "cancelled"
        except (ValueError, OSError) as error:
            state.update(
                status="cancelled" if (directory / "cancel").exists() else "failed",
                error=str(error),
            )
        finally:
            try:
                remove_work(directory / "work")
            except OSError:
                state.update(status="failed", error="Temporary sample cleanup failed.")
            try:
                self.write(directory, state)
            finally:
                lease.close()
                slot.close()
