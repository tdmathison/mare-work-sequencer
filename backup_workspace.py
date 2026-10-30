"""Focused, durable backup jobs over the existing installation and RAW services."""
from backup_filenames import archive_filename

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing, nullcontext
from datetime import datetime, timezone
import hashlib
from functools import wraps
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import time
import uuid
import zipfile
import fcntl
import pyzipper
from flask import (
    abort,
    g,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from itsdangerous import URLSafeTimedSerializer
from werkzeug.datastructures import FileStorage, MultiDict
from authorization import has_permission
from backups import (
    checked_members,
    read_json,
    MAX_METADATA,
)
from installation_backup import restore_installation
from backup_areas import AREAS, KEYS, initialize, selection, resolve

FORMAT = "mare-backup/1"
UPLOAD_LIMIT = 1024**3
TTL = 24 * 3600
TRANSIENT = {
    "search-index",
    "report-jobs",
    "snort-jobs",
    "yara-jobs",
    "family-report-staging",
    "actor-report-staging",
}
LOCKS = {".backup.lock", ".case-sync.lock", ".maintenance.lock"}
OPERATIONAL = {"audit", "attempts", "sync_imports", "sync_dirty", "report_jobs"}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024**2):
            result.update(chunk)
    return result.hexdigest()


def durable(path, value):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    with temp.open("w") as output:
        os.chmod(temp, 0o600)
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock(path, exclusive):
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(fd)


def persistent(root):
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root)
        if (
            rel.parts[0] in TRANSIENT
            or rel.parts[0].startswith("case-import-")
            or path.name in LOCKS
            or path.name
            in {
                "workflow.sqlite3-wal",
                "workflow.sqlite3-shm",
                "workflow.sqlite3-journal",
            }
        ):
            continue
        if path.is_symlink():
            raise ValueError(
                "Persistent symbolic links cannot be recovered portably. Replace them with managed files before exporting."
            )
        if path.is_file():
            yield path, rel.as_posix()


def schema(con):
    return {
        r[0] + " " + r[1]: " ".join(r[2].split())
        for r in con.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    }


def destination_state(con, root):
    result = hashlib.sha256()
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        if r[0] not in OPERATIONAL
    ]
    for table in tables:
        rows = [
            list(r)
            for r in con.execute('SELECT * FROM "' + table.replace('"', '""') + '"')
        ]
        if table == "users":
            columns = [r[1] for r in con.execute("PRAGMA table_info(users)")]
            if "last_login" in columns:
                for row in rows:
                    row[columns.index("last_login")] = None
        result.update(
            json.dumps(
                [table, sorted(rows, key=repr)], sort_keys=True, default=str
            ).encode()
        )
    for path, rel in persistent(root):
        if rel == "workflow.sqlite3" or rel.startswith(
            ("sync-staging/", "sync-recovery/")
        ):
            continue
        result.update(rel.encode())
        result.update(digest(path).encode())
    return result.hexdigest()


def recover_replacement(root, directory):
    directory = Path(directory) / "replacement-recovery"
    file = directory / "journal.json"
    if not file.exists():
        return
    journal = json.loads(file.read_text())
    if journal["phase"] == "committed":
        return
    for name in reversed(journal["moved_new"]):
        path = Path(root) / name
        if path.exists():
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    for name in reversed(journal["moved_old"]):
        source = directory / "old" / name
        if source.exists():
            target = Path(root) / name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            source.rename(target)
    shutil.rmtree(directory)


def bootstrap_guard(root):
    token = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    directory = Path(root).parent / (".mare-backup-work-" + token)
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory / "maintenance.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    recover_replacement(root, directory)
    fcntl.flock(fd, fcntl.LOCK_SH)
    return fd


class MaintenanceWSGI:
    """All HTTP readers drain before publication; writers pause during snapshots."""

    def __init__(self, application, service):
        self.application = application
        self.service = service

    def __call__(self, environ, start_response):
        # Hold through the request, including session deserialization/serialization.
        with lock(self.service.maintenance, False):
            writing = environ.get("REQUEST_METHOD") not in (
                "GET",
                "HEAD",
                "OPTIONS",
            ) or environ.get("PATH_INFO", "").startswith("/api/v1/")
            if writing:
                with lock(self.service.writes, False):
                    return self.application(environ, start_response)
            return self.application(environ, start_response)


class DataKeySessions(SecureCookieSessionInterface):
    def __init__(self, root):
        self.root = root

    def get_signing_serializer(self, app):
        key = (
            os.environ.get("MARE_SECRET_KEY") or (self.root / "session.key").read_text()
        )
        return URLSafeTimedSerializer(
            key,
            salt=self.salt,
            serializer=self.serializer,
            signer_kwargs={
                "key_derivation": self.key_derivation,
                "digest_method": self.digest_method,
            },
        )


class BackupWorkspace:
    def __init__(self, app, root, db, helpers):
        self.app, self.root, self.db, self.helpers = app, Path(root), db, helpers
        token = hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        self.directory = self.root.parent / (".mare-backup-work-" + token)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.maintenance = self.directory / "maintenance.lock"
        self.writes = self.directory / "writers.lock"
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mare-backup")
        with app.app_context():
            initialize(db())
            self.expected_schema = schema(db())
        with lock(self.maintenance, True), lock(self.writes, True):
            self.recover_replace()
        self.cleanup(recover=True)
        app.extensions["backup_workspace"] = self
        app.session_interface = DataKeySessions(self.root)
        app.wsgi_app = MaintenanceWSGI(app.wsgi_app, self)
        self.routes()

        @app.context_processor
        def backup_permissions():
            return dict(
                can_backups_manage=bool(getattr(g, "user", None))
                and has_permission(g.user, "backups:manage", self.db())
            )

    def require(self):
        if not has_permission(g.user, "backups:manage", self.db()):
            abort(403)

    def job_path(self, jid):
        try:
            if str(uuid.UUID(jid)) != jid:
                raise ValueError()
        except ValueError:
            abort(404)
        return self.directory / jid

    def load(self, jid):
        path = self.job_path(jid) / "job.json"
        if not path.is_file():
            abort(404)
        data = json.loads(path.read_text())
        if data["owner"] != g.user["user_uuid"]:
            abort(404)
        if time.time() - data["created_epoch"] > TTL:
            abort(410)
        if data["kind"] == "export" and not data.get("archive_name"):
            data["archive_name"] = archive_filename(
                data["areas"], self.app.config.get("DISPLAY_TIMEZONE"),
                started_at=datetime.fromisoformat(data["created_at"]),
            )
            self.save(data)
        return data

    def save(self, data):
        durable(self.job_path(data["id"]) / "job.json", data)

    def update(self, data, **fields):
        data.update(fields)
        data["updated_at"] = stamp()
        self.save(data)

    def audit(self, action, jid, archive_name=None):
        self.db().execute(
            "INSERT INTO audit(actor,action,created) VALUES(?,?,?)",
            (g.user["username"], f"Backup workspace {action}: job={jid}" + ("; archive=" + archive_name if archive_name else ""), stamp()),
        )
        sqlite3.Connection.commit(self.db())

    def cleanup(self, recover=False):
        for path in self.directory.iterdir():
            if not path.is_dir():
                continue
            if path.name == "replacement-recovery" or path.name.startswith(
                "previous-destination-"
            ):
                journal = path / "journal.json"
                if journal.exists():
                    entry = json.loads(journal.read_text())
                    if (
                        entry["phase"] == "committed"
                        and time.time() - entry.get("committed_at", time.time()) > TTL
                    ):
                        shutil.rmtree(path)
                continue
            file = path / "job.json"
            if file.exists():
                data = json.loads(file.read_text())
                if time.time() - data["created_epoch"] > TTL:
                    shutil.rmtree(path)
                elif (
                    recover
                    and data["state"] in ("queued", "running")
                    and not self.alive(data.get("pid"))
                ):
                    # A process restart cannot safely replay an in-memory passphrase.
                    data.update(
                        state="failed",
                        phase="Interrupted by restart; upload or export again.",
                        error="The operation was interrupted. Existing data or the recovery journal was preserved.",
                    )
                    durable(file, data)

    def alive(self, pid):
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def submit(self, data, operation, *args):
        self.pool.submit(self.run, data["id"], operation, args)

    def run(self, jid, operation, args):
        with self.app.app_context():
            data = json.loads((self.job_path(jid) / "job.json").read_text())
            try:
                exclusive = operation == "apply" and bool(
                    (data.get("preview") or {}).get("complete")
                )
                with lock(self.maintenance, exclusive), lock(self.writes, True):
                    with self.app.test_request_context(
                        "/backup-restore/worker", method="POST"
                    ):
                        g.backup_exclusive = exclusive
                        user = (
                            self.db()
                            .execute(
                                "SELECT * FROM users WHERE user_uuid=? AND active=1",
                                (data["owner"],),
                            )
                            .fetchone()
                        )
                        if not user or not has_permission(
                            user, "backups:manage", self.db()
                        ):
                            raise ValueError(
                                "Backup permission is no longer available."
                            )
                        # backups:manage delegates the existing shared-data helpers
                        # inside this authorized job, without changing account roles.
                        g.user = dict(user)
                        g.user["role"] = "Administrator"
                        g.backup_worker = True
                        self.app.extensions["case_sync"].acquire()
                        self.update(
                            data,
                            state="running",
                            phase="Checking active jobs and snapshot consistency",
                        )
                        self.ensure_idle()
                        if operation == "export":
                            self.export(data, *args)
                        elif operation == "inspect":
                            self.inspect(data, *args)
                        else:
                            self.apply(data, *args)
            except Exception as exc:
                self.db().rollback() if "db" in g else None
                error = (
                    str(exc)[:700]
                    if isinstance(exc, ValueError)
                    else "Operation failed safely. Review server availability and retry; no archive content is logged."
                )
                if isinstance(exc, zipfile.BadZipFile):
                    error = "The selected file is not a valid ZIP backup. Choose a supported MWS archive."
                if operation == "apply" and data.get("preview"):
                    from backup_presentation import outcomes as display_outcomes
                    reviewed = data["preview"]
                    journal = self.db().execute("SELECT plan,outcomes FROM sync_imports WHERE id=?", (reviewed.get("operation"),)).fetchone()
                    shared = json.loads(journal["plan"]).get("shared", {}).get("records", []) if journal and json.loads(journal["plan"]).get("shared_applied") else None
                    case_results = json.loads(journal["outcomes"]) if journal else []
                    ended = stamp()
                    data["result"] = dict(message=error, failed=1,
                        records=display_outcomes(reviewed, case_results, shared),
                        started_at=data.get("execution_started_at"), completed_at=ended,
                        duration=max(0, (datetime.fromisoformat(ended)-datetime.fromisoformat(data["execution_started_at"])).total_seconds()))
                self.update(data, state="failed", phase="Failed", error=error)
                if getattr(g, "user", None):
                    try:
                        self.audit(operation + " failed", jid)
                    except (sqlite3.Error, OSError):
                        pass
                for name in ("probe", "restored", "verified"):
                    shutil.rmtree(self.job_path(jid) / name, ignore_errors=True)
                for name in ("payload.zip", "counts.sqlite3"):
                    (self.job_path(jid) / name).unlink(missing_ok=True)
            finally:
                for name in ("passphrase", "password"):
                    data.pop(name, None)

    def ensure_idle(self):
        if (
            self.db()
            .execute("SELECT 1 FROM report_jobs WHERE status IN ('queued','running')")
            .fetchone()
        ):
            raise ValueError("Wait for active report generation jobs to finish.")
        for name in ("snort-jobs", "yara-jobs"):
            for status in (self.root / name).glob("*/status.json"):
                value = json.loads(status.read_text())
                if value.get("status") in ("queued", "running"):
                    raise ValueError("Wait for active analysis jobs to finish.")
        for table in ("snort_jobs", "yara_jobs"):
            if (
                self.db()
                .execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                .fetchone()
                and self.db()
                .execute(f"SELECT 1 FROM {table} WHERE status IN ('queued','running')")
                .fetchone()
            ):
                raise ValueError("Wait for active analysis jobs to finish.")

    def capture_response(self, response, path):
        if response.status_code != 200:
            raise ValueError(
                "Backup could not be prepared. Check active jobs and storage integrity."
            )
        try:
            with Path(path).open("wb") as target:
                os.chmod(path, 0o600)
                for chunk in response.response:
                    target.write(chunk)
        finally:
            response.close()

    def export(self, data, passphrase):
        folder = self.job_path(data["id"])
        g.backup_archive_name = data["archive_name"]
        payload = folder / "payload.zip"
        self.update(data, phase="Snapshotting database and durable files")
        if data["complete"]:
            list(
                persistent(self.root)
            )  # Reject unportable links instead of silently omitting them.
            self.capture_response(self.helpers["database"](), payload)
        else:
            g.backup_areas = data["areas"]
            g.backup_include_samples = True
            self.capture_response(self.helpers["export"](), payload)
        with zipfile.ZipFile(payload) as z:
            if data["complete"]:
                details = read_json(z, "installation.json")
                counts = details["counts"]
                files = details["files"]
                snapshot = folder / "counts.sqlite3"
                with z.open("data/workflow.sqlite3") as source, snapshot.open(
                    "wb"
                ) as target:
                    shutil.copyfileobj(source, target)
                with closing(sqlite3.connect(snapshot)) as con:
                    all_counts = {
                        r[0]: con.execute(
                            'SELECT count(*) FROM "' + r[0].replace('"', '""') + '"'
                        ).fetchone()[0]
                        for r in con.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                        ).fetchall()
                    }
                snapshot.unlink()
            else:
                index = read_json(z, "backup.json")
                library = index["family_library"]
                counts = {
                    "cases": len(index["cases"]),
                    "malware_families": len(library["families"]),
                    "threat_actors": len(library.get("actors", [])),
                    "actor_reports": sum(len(a["reports"]) for a in library.get("actors", [])),
                    "tags": len(index["tag_registry"]),
                    "family_reports": sum(
                        len(f["reports"]) for f in library["families"]
                    ),
                }
                files = {}
                for entry in z.infolist():
                    if entry.is_dir():
                        continue
                    checksum = hashlib.sha256()
                    with z.open(entry) as source:
                        while chunk := source.read(1024**2):
                            checksum.update(chunk)
                    files[entry.filename] = {
                        "size": entry.file_size,
                        "sha256": checksum.hexdigest(),
                    }
                all_counts = counts
        manifest = dict(
            schema=FORMAT,
            id=data["id"],
            created=stamp(),
            application_version=os.environ.get(
                "MARE_APP_VERSION", "MARE backup-workspace-v1"
            ),
            complete=data["complete"],
            areas=data["areas"],
            dependencies=data["dependencies"],
            counts=counts,
            record_counts=all_counts,
            content_files=files,
            file_count=len(files),
            payload={"size": payload.stat().st_size, "sha256": digest(payload)},
            compatibility={
                "schema": self.expected_schema if data["complete"] else {},
                "mode": "replace" if data["complete"] else "merge",
            },
            exclusions=[
                "Application source/dependencies, host services, TLS and environment configuration",
                "Search caches, transient report/YARA/Snort jobs, temporary report staging",
                "Browser sessions end after full replacement; restore environment-provided secrets separately",
            ],
        )
        self.update(data, phase="Encrypting and sealing archive")
        archive = folder / "backup.zip"
        if passphrase:
            with pyzipper.AESZipFile(
                archive, "w", compression=zipfile.ZIP_STORED, encryption=pyzipper.WZ_AES
            ) as z:
                z.setpassword(passphrase.encode())
                z.setencryption(pyzipper.WZ_AES, nbits=256)
                z.writestr("mare-backup.json", json.dumps(manifest).encode())
                z.write(payload, "payload.zip")
        else:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:
                z.writestr("mare-backup.json", json.dumps(manifest))
                z.write(payload, "payload.zip")
        os.chmod(archive, 0o600)
        payload.unlink()
        self.audit("export completed", data["id"], data["archive_name"])
        self.update(
            data,
            state="completed",
            phase="Archive ready",
            manifest=manifest,
            archive_size=archive.stat().st_size,
            error=None,
        )

    def unwrap(self, folder, passphrase):
        incoming = folder / "upload.zip"
        with zipfile.ZipFile(incoming) as probe:
            if "mare-backup.json" not in probe.namelist():
                return incoming, None
            entries = probe.infolist()
            if len(entries) != 2 or {i.filename for i in entries} != {
                "mare-backup.json",
                "payload.zip",
            }:
                raise ValueError("Unexpected backup envelope entries.")
            for i in entries:
                if i.file_size > (
                    MAX_METADATA if i.filename == "mare-backup.json" else UPLOAD_LIMIT
                ):
                    raise ValueError("Backup envelope exceeds size limits.")
            encrypted = any(i.flag_bits & 1 for i in entries)
        try:
            with pyzipper.AESZipFile(incoming) as z:
                if encrypted:
                    z.setpassword(passphrase.encode())
                with z.open("mare-backup.json") as source:
                    manifest = json.loads(source.read(MAX_METADATA + 1))
                if (
                    manifest.get("schema") != FORMAT
                    or type(manifest.get("complete")) is not bool
                ):
                    raise ValueError("Unsupported backup manifest version.")
                if manifest["complete"] and not encrypted:
                    raise ValueError("New complete archives must be encrypted.")
                selection(manifest.get("areas"), manifest["complete"])
                target = folder / "payload.zip"
                with z.open("payload.zip") as source, target.open("wb") as out:
                    os.chmod(target, 0o600)
                    size = 0
                    while chunk := source.read(1024**2):
                        size += len(chunk)
                        if size > UPLOAD_LIMIT:
                            raise ValueError("Backup payload exceeds size limits.")
                        out.write(chunk)
                if manifest.get("payload") != {
                    "size": target.stat().st_size,
                    "sha256": digest(target),
                }:
                    raise ValueError("Payload integrity verification failed.")
                return target, manifest
        except (
            RuntimeError,
            NotImplementedError,
            zipfile.BadZipFile,
            pyzipper.BadZipFile,
        ) as exc:
            raise ValueError(
                "Passphrase is incorrect or the encrypted archive is damaged."
            ) from exc

    def inspect(self, data, passphrase):
        folder = self.job_path(data["id"])
        self.update(data, phase="Validating archive format, paths, sizes and hashes")
        payload, manifest = self.unwrap(folder, passphrase)
        with zipfile.ZipFile(payload) as z:
            members, _ = checked_members(z)
            complete = "data/workflow.sqlite3" in members
            single = "backup.json" not in members and not complete
            legacy = manifest is None
        findings = []
        conflicts = []
        mapping = []
        case_choices = []
        shared_actions = {}
        handoff = None
        display_records = []
        for old in ("restored", "probe"):
            shutil.rmtree(folder / old, ignore_errors=True)
        if complete:
            restored = folder / "restored"
            restore_installation(payload, restored)
            if (
                not (restored / "session.key").is_file()
                or not (restored / "session.key").read_bytes()
            ):
                findings.append("The archive is missing its application session key.")
            with closing(sqlite3.connect(restored / "workflow.sqlite3")) as source:
                source.row_factory = sqlite3.Row
                contract = schema(source)
                if contract != self.expected_schema:
                    findings.append(
                        "The database schema differs from this application version. Upgrade a copy with a compatible release before replacing this instance."
                    )
                admins = source.execute(
                    "SELECT username,user_uuid FROM users WHERE active=1 AND role='Administrator' AND (password LIKE 'scrypt:%$%' OR password LIKE 'pbkdf2:%$%')"
                ).fetchall()
                if not admins:
                    findings.append(
                        "The archive has no active administrator with a usable password hash."
                    )
                else:
                    handoff = dict(admins[0])
                if source.execute(
                    "SELECT 1 FROM cases WHERE number NOT IN (SELECT number FROM reserved_case_numbers)"
                ).fetchone():
                    findings.append("Case number reservations are incomplete.")
                counts = {
                    r[0]: source.execute(
                        'SELECT count(*) FROM "' + r[0].replace('"', '""') + '"'
                    ).fetchone()[0]
                    for r in source.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
            from backup_presentation import database_records
            with closing(sqlite3.connect(restored / "workflow.sqlite3")) as source:
                display_records = database_records(source)
            areas = sorted(KEYS)
            mode = "replace"
            operation = None
            file_count = sum(1 for _ in persistent(restored))
        else:
            g.backup_workspace = True
            g.backup_choices = data.get("choices", {})
            probe = folder / "probe"
            probe.mkdir(mode=0o700)
            with payload.open("rb") as file:
                plans, catalog = self.helpers["stage_upload"](
                    FileStorage(file, filename=data["filename"]), single, probe
                )
            source_library = (
                json.loads((probe / "family-library.json").read_text())
                if (probe / "family-library.json").exists()
                else {"families": []}
            )
            conflicts, mapping, library = resolve(
                self.db(), self.root, probe, data.get("choices", {})
            )
            shared_actions = {
                'incoming_actors': len(source_library.get('actors', [])),
                'kept_destination_actors': len(source_library.get('actors', [])) - len(library.get('actors', [])),
                'actor_additions': sum(not bool(self.db().execute('SELECT 1 FROM threat_actors WHERE id=?', (a['id'],)).fetchone()) for a in library.get('actors', [])),
                "incoming_families": len(source_library["families"]),
                "kept_destination": len(source_library["families"])
                - len(library["families"]),
                "additions": sum(
                    not bool(
                        self.db()
                        .execute(
                            "SELECT 1 FROM malware_families WHERE id=?", (f["id"],)
                        )
                        .fetchone()
                    )
                    for f in library["families"]
                ),
                "report_additions": sum(
                    len(f["reports"])
                    for f in library["families"]
                    if not self.db()
                    .execute("SELECT 1 FROM malware_families WHERE id=?", (f["id"],))
                    .fetchone()
                ),
            }
            cases = [
                self.app.extensions["case_import_sync"].classify(
                    validated, meta, p / "mip"
                )
                for p, validated, meta in plans
            ]
            for index, item in enumerate(cases):
                if item["classification"] == "invalid":
                    findings.append(
                        "Case "
                        + str(index + 1)
                        + " is invalid: "
                        + item.get("reason", "Validation failed.")
                    )
                if item["classification"] in ("conflict", "review"):
                    key = "case:" + str(index)
                    options = (
                        [
                            ["keep", "Keep destination"],
                            ["replace", "Replace destination case"],
                        ]
                        if item["classification"] == "conflict"
                        else [["new", "Import as a new case"]]
                    )
                    if data.get("choices", {}).get(key) not in {o[0] for o in options}:
                        conflicts.append(
                            dict(
                                key=key,
                                label="Case "
                                + item.get("incoming_number", "")
                                + ": "
                                + item["classification"],
                                options=options,
                            )
                        )
                case_choices.append(
                    {
                        "index": index,
                        "action": item["classification"],
                        "number": item.get("incoming_number"),
                        "destination": item.get("destination_number"),
                        "unmapped_owner": not bool(
                            self.app.extensions["case_import_sync"].owner(
                                plans[index][1][0]
                            )
                        ),
                        "creator_maps": bool(
                            self.app.extensions["case_import_sync"].matching_user(
                                plans[index][2].get("source_creator")
                            )
                        ),
                        "file_count": sum(
                            1
                            for p in (plans[index][0] / "mip").rglob("*")
                            if p.is_file()
                        ),
                    }
                )
            from backup_presentation import record, profile
            for index, (path, validated, meta) in enumerate(plans):
                case = validated[0]
                display_records.append(record("cases", case.get("number"), case["name"], index=index,
                    stage=case.get("stage"), created=case.get("created"),
                    predicted_action=cases[index]["classification"], details=cases[index].get("reason", "")))
            for category, key, table in (("families", "families", "malware_families"), ("actors", "actors", "threat_actors")):
                retained = {value["id"] for value in library.get(key, [])}
                for value in source_library.get(key, []):
                    exists = self.db().execute(f"SELECT 1 FROM {table} WHERE id=?", (value["id"],)).fetchone()
                    action = "skipped" if value["id"] not in retained else "unchanged" if exists else "new"
                    display_records.append({**profile(category, value), "predicted_action": action,
                        "details": "Reviewed profile import; conflicts require explicit resolution."})
            registry = json.loads((probe / "tag-registry.json").read_text()) if (probe / "tag-registry.json").exists() else []
            for value in registry:
                resolved = next((row for row in mapping if row["identity"] == value["identity"]), None)
                display_records.append(record("tags", value["identity"], value["name"],
                    predicted_action="conflict" if not resolved else "new" if resolved["outcome"] == "Add tag" else "unchanged",
                    details=resolved["outcome"] if resolved else "Resolve tag identity conflict."))
            counts = {
                "cases": len(plans),
                "malware_families": len(library["families"]),
                "threat_actors": len(library.get("actors", [])),
                "actor_reports": sum(len(a["reports"]) for a in library.get("actors", [])),
                "tags": (
                    len(mapping) if mapping else len((catalog or {}).get("tags", []))
                ),
                "family_reports": sum(len(f["reports"]) for f in library["families"]),
            }
            file_count = sum(item["file_count"] for item in case_choices) + sum(
                len(f["reports"]) for f in library["families"] + library.get("actors",[])
            )
            areas = (manifest or {}).get("areas") or [
                key
                for key, n in [
                    ("cases", len(plans)),
                    ("families", len(library["families"])),
                    ("actors", len(library.get("actors",[]))),
                    ("tags", len((catalog or {}).get("tags", []))),
                ]
                if n
            ]
            mode = "merge"
            operation = None
            if not conflicts:
                g.backup_workspace = True
                g.backup_choices = data.get("choices", {})
                with payload.open("rb") as file:
                    response = self.app.extensions["case_import_sync"].preview(
                        FileStorage(file, filename=data["filename"]), single
                    )
                if "/review/" not in (response.location or ""):
                    raise ValueError(
                        "Archive could not be staged for import. Check shared relationships and case content."
                    )
                operation = response.location.rsplit("/", 1)[-1]
        if manifest and manifest["complete"] != complete:
            raise ValueError("Manifest scope does not match archive content.")
        self.db().commit()
        sqlite3.Connection.commit(self.db())
        preview = dict(
            records=display_records,
            archive_size=(folder / "upload.zip").stat().st_size,
            filename=data["filename"],
            format=(manifest or {}).get(
                "schema",
                "Legacy installation" if complete else "Legacy RAW / case backup",
            ),
            created=(manifest or {}).get("created", "Unknown in legacy archive"),
            application_version=(manifest or {}).get(
                "application_version", "Not recorded"
            ),
            complete=complete,
            mode=mode,
            areas=areas,
            dependencies=(manifest or {}).get(
                "dependencies", ["Referenced tags"] if not complete else []
            ),
            counts=counts,
            file_count=file_count,
            conflicts=conflicts,
            blocking=findings,
            mapping=mapping,
            cases=case_choices,
            shared_actions=shared_actions,
            handoff=handoff,
            legacy=legacy,
            warnings=(
                [
                    "Legacy archive: newer data areas may be absent; missing sections never delete destination data."
                ]
                if legacy
                else []
            ),
            destination=destination_state(self.db(), self.root),
            archive_hash=digest(folder / "upload.zip"),
            payload_hash=digest(payload),
            operation=operation,
        )
        durable(folder / "preview.json", preview)
        self.audit("inspection completed", data["id"])
        self.update(
            data,
            state="preview",
            phase=(
                "Resolve conflicts"
                if conflicts
                else (
                    "Blocked by compatibility findings"
                    if findings
                    else "Ready for review"
                )
            ),
            preview=preview,
            error=None,
        )

    def apply(self, data, ack):
        folder = self.job_path(data["id"])
        self.update(data, execution_started_at=stamp())
        preview = json.loads((folder / "preview.json").read_text())
        if preview["blocking"] or preview["conflicts"]:
            raise ValueError("Resolve blocking findings and generate a new preview.")
        if (
            digest(folder / "upload.zip") != preview["archive_hash"]
            or destination_state(self.db(), self.root) != preview["destination"]
        ):
            raise ValueError(
                "Destination or archive changed after preview. Refresh the plan before importing."
            )
        self.update(data, phase="Applying reviewed " + preview["mode"] + " plan")
        # Legacy archives may import tag names through the case catalog rather
        # than the shared identity registry. Keep before/after evidence for them.
        prior_tags = {r["name"]: self.db().execute("SELECT id FROM tags WHERE name=?", (r["name"],)).fetchone()
                      for r in preview.get("records", []) if r["category"] == "tags"}
        if preview["complete"]:
            if ack != "REPLACE":
                raise ValueError("Acknowledge complete replacement in the preview.")
            payload = (
                folder / "payload.zip"
                if (folder / "payload.zip").exists()
                else folder / "upload.zip"
            )
            if digest(payload) != preview["payload_hash"]:
                raise ValueError("Staged payload changed; inspect the archive again.")
            verified = folder / "verified"
            shutil.rmtree(verified, ignore_errors=True)
            restore_installation(payload, verified)
            self.publish_replace(data, verified)
            data["owner"] = preview["handoff"]["user_uuid"]
            shutil.rmtree(verified, ignore_errors=True)
            result = {
                "replaced": sum(preview["counts"].values()),
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "files": preview["file_count"],
                "failed": 0,
                "message": "Application data replaced. Sign in using an active restored administrator. All previous sessions ended.",
            }
        else:
            g.backup_workspace = True
            g.backup_choices = data.get("choices", {})
            operation = preview["operation"]
            values = MultiDict()
            for item in preview["cases"]:
                choice = data.get("choices", {}).get("case:" + str(item["index"]))
                if choice:
                    values.add("decision-" + str(item["index"]), choice)
            # Existing service performs per-case rechecks, journals and outcomes.
            with self.app.test_request_context(
                "/import-export/apply/" + operation, method="POST", data=values
            ):
                g.user = dict(
                    self.db()
                    .execute("SELECT * FROM users WHERE user_uuid=?", (data["owner"],))
                    .fetchone()
                )
                g.user["role"] = "Administrator"
                g.backup_workspace = True
                g.backup_choices = data.get("choices", {})
                allocations = (
                    self.root / "sync-staging" / operation / "case-numbers.json"
                )
                numbers = (
                    json.loads(allocations.read_text())
                    if allocations.exists()
                    else None
                )
                self.app.extensions["case_import_sync"].apply(operation)
                row = (
                    self.db()
                    .execute(
                        "SELECT status,outcomes,plan FROM sync_imports WHERE id=?",
                        (operation,),
                    )
                    .fetchone()
                )
                outcomes = json.loads(row["outcomes"])
                if numbers:
                    for number in numbers["reserved"]:
                        self.db().execute(
                            "INSERT OR IGNORE INTO reserved_case_numbers VALUES(?)",
                            (number,),
                        )
                    self.db().execute(
                        "UPDATE case_sequence SET value=max(value,?) WHERE id=1",
                        (numbers["sequence"],),
                    )
                    sqlite3.Connection.commit(self.db())
                if row["status"] != "complete":
                    raise ValueError("Import remains unresolved; refresh the preview.")
            result = {
                "added": sum(o["action"].startswith("Imported") for o in outcomes),
                "updated": sum(
                    "Updated" in o["action"] or "Replaced" in o["action"]
                    for o in outcomes
                ),
                "skipped": sum(
                    o["action"] in ("Unchanged", "Kept local", "Skipped older")
                    for o in outcomes
                ),
                "failed": sum(
                    "failed" in o["action"].lower()
                    or "rolled back" in o["action"].lower()
                    for o in outcomes
                ),
                "files": sum(
                    preview["cases"][o["index"]]["file_count"]
                    for o in outcomes
                    if o["action"].startswith(("Imported", "Updated", "Replaced"))
                )
                + preview["shared_actions"].get("report_additions", 0),
                "case_outcomes": outcomes,
                "shared": preview["counts"],
                "shared_actions": preview["shared_actions"],
                "message": "Reviewed merge finished. Case outcomes and shared counts are shown separately.",
            }
        from backup_presentation import outcomes as display_outcomes
        shared = [] if preview["complete"] else json.loads(row["plan"]).get("shared", {}).get("records", [])
        if not preview["complete"]:
            known = {(r["category"], r["identifier"]) for r in shared}
            for item in preview.get("records", []):
                if item["category"] != "tags" or ("tags", item["identifier"]) in known:
                    continue
                actual = self.db().execute("SELECT id FROM tags WHERE name=?", (item["name"],)).fetchone()
                before = prior_tags[item["name"]]
                if actual and (before is None or actual[0] == before[0]):
                    shared.append({**item, "action": "added" if before is None else "unchanged",
                        "details": "Tag added by the completed catalog import." if before is None else "Verified existing tag retained by the completed catalog import."})
        result["records"] = display_outcomes(preview, [] if preview["complete"] else outcomes, shared, replaced=preview["complete"])
        result["started_at"] = data["execution_started_at"]
        result["completed_at"] = stamp()
        result["duration"] = max(0, (datetime.fromisoformat(result["completed_at"]) - datetime.fromisoformat(result["started_at"])).total_seconds())
        result["warnings"] = preview["warnings"]
        self.audit(
            "import partially failed" if result["failed"] else "import completed",
            data["id"],
        )
        self.app.extensions["mip_search"].invalidate()
        for name in ("probe", "restored", "verified"):
            shutil.rmtree(folder / name, ignore_errors=True)
        (folder / "payload.zip").unlink(missing_ok=True)
        self.update(
            data,
            state="completed" if not result["failed"] else "failed",
            phase=(
                "Import completed"
                if not result["failed"]
                else "Partial import: inspect failed counts"
            ),
            result=result,
            error=None,
        )

    def publish_replace(self, data, restored):
        recovery = self.directory / "replacement-recovery"
        if recovery.exists():
            prior = json.loads((recovery / "journal.json").read_text())
            if prior["phase"] != "committed":
                raise ValueError(
                    "A previous replacement recovery directory needs attention."
                )
            recovery.rename(
                self.directory / ("previous-destination-" + str(uuid.uuid4()))
            )
        recovery.mkdir(mode=0o700)
        old = recovery / "old"
        old.mkdir(mode=0o700)
        names = [p.name for p in self.root.iterdir() if p.name not in LOCKS]
        incoming = [p.name for p in restored.iterdir() if p.name not in LOCKS]
        journal = {
            "phase": "prepared",
            "old": names,
            "incoming": incoming,
            "moved_old": [],
            "moved_new": [],
        }
        durable(recovery / "journal.json", journal)
        # Release this worker's SQLite handle before the maintenance publication.
        if "db" in g:
            g.pop("db").close()
        # The outer read lock is upgraded temporarily; writers are already excluded.
        with (
            nullcontext()
            if getattr(g, "backup_exclusive", False)
            else lock(self.maintenance, True)
        ):
            try:
                for name in names:
                    journal["moved_old"].append(name)
                    durable(recovery / "journal.json", journal)
                    (self.root / name).rename(old / name)
                for name in incoming:
                    journal["moved_new"].append(name)
                    durable(recovery / "journal.json", journal)
                    (restored / name).rename(self.root / name)
                with closing(sqlite3.connect(self.root / "workflow.sqlite3")) as con:
                    con.execute(
                        "UPDATE users SET version=version+?",
                        (secrets.randbelow(2**30) + 1000,),
                    )
                    con.commit()
                for name in TRANSIENT | {
                    "cases",
                    "users",
                    "snort-drafts",
                    "yara-drafts",
                    "sync-staging",
                    "sync-recovery",
                }:
                    (self.root / name).mkdir(mode=0o700, exist_ok=True)
                journal["phase"] = "committed"
                journal["committed_at"] = time.time()
                durable(recovery / "journal.json", journal)
            except BaseException:
                self.recover_replace()
                raise
        # Keep the old destination privately until the next explicit cleanup/TTL.
        self.update(
            data,
            recovery="replacement-recovery",
            phase="Replacement committed; ending old sessions",
        )

    def recover_replace(self):
        recover_replacement(self.root, self.directory)

    def page(self):
        self.require()
        rows = [
            dict(
                key=a.key,
                label=a.label,
                count=a.count(self.db()),
                description=a.description,
                dependencies=a.dependencies,
                available=a.available,
            )
            for a in AREAS
        ]
        recent = []
        for file in self.directory.glob("*/job.json"):
            value = json.loads(file.read_text())
            if (
                value["owner"] == g.user["user_uuid"]
                and value["kind"] == "inspect"
                and value["state"] == "completed"
                and time.time() - value["created_epoch"] < TTL
            ):
                recent.append(value)
        recent.sort(key=lambda value: value["created_epoch"], reverse=True)
        return render_template(
            "backup_workspace.html",
            areas=rows,
            resume_import=recent[0]["id"] if recent else "",
        )

    def routes(self):
        app = self.app

        def serialized(handler):
            @wraps(handler)
            def guarded(*args, **kwargs):
                with lock(self.directory / "submission.lock", True):
                    return handler(*args, **kwargs)

            return guarded

        @app.get("/backup-restore")
        def backup_workspace_page():
            self.require()
            from settings_navigation import legacy_redirect
            return legacy_redirect('import_export_page')

        @app.post("/backup-restore/jobs")
        @serialized
        def backup_jobs_create():
            self.require()
            self.cleanup()
            kind = request.form.get("kind")
            if kind not in ("export", "inspect"):
                abort(400)
            complete = request.form.get("complete") == "1"
            try:
                areas, deps = (
                    selection(request.form.getlist("areas"), complete)
                    if kind == "export"
                    else ([], [])
                )
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            password = request.form.get("passphrase", "")
            if kind == "export" and (complete or password) and len(password) < 16:
                return (
                    jsonify(
                        error="Use a backup passphrase of at least 16 characters. Keep it separately; it cannot be recovered."
                    ),
                    400,
                )
            # Owner-scoped, active-operation deduplication survives page reloads.
            for path in self.directory.glob("*/job.json"):
                current = json.loads(path.read_text())
                if current["owner"] == g.user["user_uuid"] and current["state"] in (
                    "queued",
                    "running",
                ):
                    return (
                        jsonify(
                            error="An operation is already running.", id=current["id"]
                        ),
                        409,
                    )
            jid = str(uuid.uuid4())
            folder = self.job_path(jid)
            folder.mkdir(mode=0o700)
            data = dict(
                id=jid,
                kind=kind,
                owner=g.user["user_uuid"],
                created_epoch=time.time(),
                created_at=stamp(),
                state="queued",
                phase="Queued",
                pid=os.getpid(),
                complete=complete,
                areas=areas,
                dependencies=deps,
                choices={},
            )
            if kind == "export":
                data["archive_name"] = archive_filename(areas, app.config.get("DISPLAY_TIMEZONE"))
            if kind == "inspect":
                upload = request.files.get("archive")
                if not upload or not upload.filename:
                    shutil.rmtree(folder)
                    return jsonify(error="Choose one backup archive."), 400
                data["filename"] = Path(upload.filename.replace("\\", "/")).name[:255]
                target = folder / "upload.zip"
                size = 0
                with target.open("wb") as output:
                    os.chmod(target, 0o600)
                    while chunk := upload.stream.read(1024**2):
                        size += len(chunk)
                        if size > UPLOAD_LIMIT:
                            shutil.rmtree(folder)
                            abort(413)
                        output.write(chunk)
            self.save(data)
            self.audit(kind + " queued", jid, data.get("archive_name"))
            self.submit(data, "export" if kind == "export" else "inspect", password)
            return jsonify(id=jid), 202

        @app.get("/backup-restore/jobs/<jid>")
        def backup_jobs_status(jid):
            self.require()
            response = jsonify(self.load(jid))
            response.headers["Cache-Control"] = "private, no-store"
            return response

        @app.get("/backup-restore/jobs/<jid>/download")
        def backup_jobs_download(jid):
            self.require()
            data = self.load(jid)
            if data["kind"] != "export" or data["state"] != "completed":
                abort(409)
            response = send_file(
                self.job_path(jid) / "backup.zip",
                as_attachment=True,
                download_name=data["archive_name"],
                mimetype="application/zip",
            )
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        @app.post("/backup-restore/jobs/<jid>/preview")
        @serialized
        def backup_jobs_preview(jid):
            self.require()
            data = self.load(jid)
            if data["kind"] != "inspect" or data["state"] in (
                "queued",
                "running",
                "completed",
            ):
                abort(409)
            choices = request.form.get("choices", "{}")
            try:
                choices = json.loads(choices)
            except ValueError:
                abort(400)
            if (
                not isinstance(choices, dict)
                or len(choices) > 11000
                or any(
                    not isinstance(k, str)
                    or v not in ("keep", "replace", "new", "reuse", "retain", "skip")
                    for k, v in choices.items()
                )
            ):
                abort(400)
            data["choices"] = choices
            self.update(
                data, state="queued", phase="Revalidating preview", preview=None, result=None, execution_started_at=None
            )
            self.submit(data, "inspect", request.form.get("passphrase", ""))
            return jsonify(id=jid), 202

        @app.post("/backup-restore/jobs/<jid>/apply")
        @serialized
        def backup_jobs_apply(jid):
            self.require()
            data = self.load(jid)
            if (
                data["state"] != "preview"
                or not data.get("preview")
                or data["preview"]["blocking"]
                or data["preview"]["conflicts"]
            ):
                abort(409)
            if data["preview"]["complete"] and request.form.get("ack") != "REPLACE":
                return (
                    jsonify(
                        error="Acknowledge Replace application data in the reviewed preview."
                    ),
                    400,
                )
            self.update(data, state="queued", phase="Import queued")
            self.submit(data, "apply", request.form.get("ack", ""))
            return jsonify(id=jid), 202
