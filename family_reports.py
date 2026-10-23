"""Durable family reports, bounded document validation and recoverable file writes."""

from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import uuid
import zipfile
from flask import (
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from reporting import validate_docx
from tagging import now

MIGRATION = "family-reports-v1"
MAX_FILE = 25 * 1024**2
MAX_BATCH = 75 * 1024**2
MAX_BATCH_COUNT = 10
MAX_REPORTS = 100
TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def initialize(connection):
    connection.executescript(
        """
    CREATE TABLE IF NOT EXISTS family_reports(
      id TEXT PRIMARY KEY, family_id TEXT NOT NULL REFERENCES malware_families(id) ON DELETE CASCADE,
      title TEXT NOT NULL, original_filename TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
      storage_ref TEXT NOT NULL UNIQUE, size INTEGER NOT NULL, file_type TEXT NOT NULL,
      sha256 TEXT NOT NULL, uploaded_at TEXT NOT NULL,
      uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
    CREATE TABLE IF NOT EXISTS family_import_state(
      family_id TEXT PRIMARY KEY REFERENCES malware_families(id) ON DELETE CASCADE,
      incoming_hash TEXT NOT NULL, local_hash TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS family_report_list ON family_reports(family_id,uploaded_at,id);
    INSERT OR IGNORE INTO schema_migrations VALUES('family-reports-v1');
    """
    )
    connection.commit()


def reference(aid):
    if not isinstance(aid, str) or str(uuid.UUID(aid)) != aid:
        raise ValueError("Invalid attachment identity.")
    return "family-reports/" + aid + ".bin"


def sync_directory(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def storage_path(root, aid):
    relative = reference(aid)
    root = Path(root).resolve()
    folder = root / "family-reports"
    if folder.is_symlink():
        raise ValueError("Report storage must not be a symbolic link.")
    path = root / relative
    if path.is_symlink():
        raise ValueError("Report files must not be symbolic links.")
    return path


def original_name(value):
    # Filename is display metadata, never a filesystem name. Strip client paths.
    value = (value or "").replace("\\", "/").split("/")[-1]
    if (
        not value
        or len(value) > 255
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError(
            "Report filenames must contain 1–255 characters without control characters."
        )
    if Path(value).suffix.lower() not in TYPES:
        raise ValueError("Upload PDF, DOC or DOCX research documents only.")
    return value


def validate_doc(path):
    """Recognize a Word binary document's CFB directory, without running Office.

    Read only bounded sector tables/directory entries; never interpret macros or
    render document content. Unlike an OLE magic-only check, reject XLS/PPT/OLE
    containers that do not contain a WordDocument stream.
    """
    with Path(path).open("rb") as source:
        header = source.read(512)
        if (
            len(header) != 512
            or header[:8] != bytes.fromhex("D0CF11E0A1B11AE1")
            or header[28:30] != b"\xfe\xff"
        ):
            raise ValueError("Upload a valid binary Word DOC document.")
        major, shift = (
            struct.unpack_from("<HH", header, 26)[0],
            struct.unpack_from("<H", header, 30)[0],
        )
        if (major, shift) not in ((3, 9), (4, 12)):
            raise ValueError("Unsupported binary Word document container.")
        sector_size = 1 << shift
        sectors = Path(path).stat().st_size // sector_size - 1

        def sector(sid):
            if not 0 <= sid < sectors:
                raise ValueError("Invalid DOC sector reference.")
            source.seek((sid + 1) * sector_size)
            data = source.read(sector_size)
            if len(data) != sector_size:
                raise ValueError("Truncated DOC container.")
            return data

        fat_count = struct.unpack_from("<I", header, 44)[0]
        difat = list(struct.unpack_from("<109I", header, 76))
        sid, count = struct.unpack_from("<II", header, 68)
        visited = set()
        if count > sectors or not 1 <= fat_count <= sectors:
            raise ValueError("Invalid DOC allocation table.")
        for _ in range(count):
            if sid in visited:
                raise ValueError("Cyclic DOC allocation table.")
            visited.add(sid)
            values = struct.unpack("<" + "I" * (sector_size // 4), sector(sid))
            difat.extend(values[:-1])
            sid = values[-1]
        fat_ids = [sid for sid in difat if sid != 0xFFFFFFFF]
        if len(fat_ids) != fat_count or len(set(fat_ids)) != fat_count:
            raise ValueError("Invalid DOC allocation table.")
        fat = []
        for sid in fat_ids:
            fat.extend(struct.unpack("<" + "I" * (sector_size // 4), sector(sid)))
        sid = struct.unpack_from("<I", header, 48)[0]
        visited = set()
        word = False
        root = False
        while sid != 0xFFFFFFFE:
            if sid in visited or len(visited) > sectors or sid >= len(fat):
                raise ValueError("Invalid DOC directory chain.")
            visited.add(sid)
            data = sector(sid)
            for offset in range(0, sector_size, 128):
                entry = data[offset : offset + 128]
                length = struct.unpack_from("<H", entry, 64)[0]
                if not entry[66]:
                    continue
                if not 2 <= length <= 64 or length % 2:
                    raise ValueError("Invalid DOC directory name.")
                name = entry[: length - 2].decode("utf-16-le")
                root |= entry[66] == 5
                size = struct.unpack_from("<Q", entry, 120)[0]
                word |= (
                    entry[66] == 2 and name == "WordDocument" and 0 < size <= MAX_FILE
                )
            sid = fat[sid]
        if not root or not word:
            raise ValueError(
                "The DOC container does not contain a Word document stream."
            )


def detected_type(path, filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in TYPES:
        raise ValueError("Upload PDF, DOC or DOCX reports only.")
    try:
        if suffix == ".pdf":
            with Path(path).open("rb") as source:
                if not source.read(8).startswith(b"%PDF-"):
                    raise ValueError("The file is not a PDF document.")
                source.seek(max(0, Path(path).stat().st_size - 2048))
                if b"%%EOF" not in source.read():
                    raise ValueError("The PDF document is truncated.")
        elif suffix == ".docx":
            validate_docx(path)  # Existing policy rejects macro-enabled OOXML.
            from backups import checked_members

            with zipfile.ZipFile(path) as archive:
                checked_members(archive)
                if len(archive.infolist()) > 10000 or archive.testzip() is not None:
                    raise ValueError("Invalid DOCX archive.")
        else:
            validate_doc(path)
    except (zipfile.BadZipFile, UnicodeError, struct.error) as exc:
        raise ValueError(
            "The document content does not match its file extension."
        ) from exc
    return TYPES[suffix]


def verify_report(root, row):
    if row["storage_ref"] != reference(row["id"]):
        raise ValueError("Invalid report storage reference.")
    original_name(row["original_filename"])
    if (
        type(row["size"]) is not int
        or not 0 < row["size"] <= MAX_FILE
        or not re.fullmatch("[a-f0-9]{64}", row["sha256"])
    ):
        raise ValueError("Invalid report size or hash.")
    path = storage_path(root, row["id"])
    if not path.is_file() or path.stat().st_size != row["size"]:
        raise ValueError(
            "An attached malware-family report is missing or has an incorrect size."
        )
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024**2):
            digest.update(chunk)
    if digest.hexdigest() != row["sha256"]:
        raise ValueError(
            "An attached malware-family report failed SHA-256 integrity validation."
        )
    if detected_type(path, row["original_filename"]) != row["file_type"]:
        raise ValueError("An attached report has an invalid detected file type.")
    return path


def recover_operation(connection, root, folder):
    """Called with a write reservation. Row existence resolves a crash/rollback."""
    if not folder.exists():
        return
    plan = folder / "plan.json"
    if plan.exists():
        if plan.stat().st_size > 100000:
            raise ValueError("Invalid report recovery journal.")
        for item in json.loads(plan.read_text()):
            aid = item["id"]
            final = storage_path(root, aid)
            saved = folder / (aid + ".bin")
            exists = (
                connection.execute(
                    "SELECT 1 FROM family_reports WHERE id=?", (aid,)
                ).fetchone()
                is not None
            )
            if item["action"] == "remove":
                if exists and saved.exists():
                    if final.exists():
                        raise ValueError(
                            "Report recovery encountered an unexpected filename collision."
                        )
                    final.parent.mkdir(mode=0o700, exist_ok=True)
                    saved.rename(final)
            elif item["action"] == "upload":
                if not exists:
                    final.unlink(missing_ok=True)
            else:
                raise ValueError("Invalid report recovery action.")
    shutil.rmtree(folder)


def recover_storage(connection, root):
    staging = Path(root) / "family-report-staging"
    if staging.is_symlink():
        raise ValueError("Unsafe report staging directory.")
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if staging.exists():
            for folder in staging.iterdir():
                if folder.is_symlink() or not folder.is_dir():
                    raise ValueError("Unsafe report recovery entry.")
                recover_operation(connection, root, folder)


class FileChanges:
    def __init__(self, root):
        self.root = Path(root)
        self.items = []
        staging = self.root / "family-report-staging"
        if staging.is_symlink():
            raise ValueError("Unsafe report staging directory.")
        staging.mkdir(mode=0o700, exist_ok=True)
        self.folder = staging / str(uuid.uuid4())
        self.folder.mkdir(mode=0o700)
        sync_directory(staging)
        sync_directory(self.root)

    def journal(self, aid, action):
        self.items.append({"id": aid, "action": action})
        temp = self.folder / "plan.tmp"
        with temp.open("w") as target:
            json.dump(self.items, target)
            target.flush()
            os.fsync(target.fileno())
        temp.replace(self.folder / "plan.json")
        sync_directory(self.folder)

    def publish(self, aid):
        final = storage_path(self.root, aid)
        final.parent.mkdir(mode=0o700, exist_ok=True)
        sync_directory(self.root)
        source = self.folder / (aid + ".bin")
        os.chmod(source, 0o600)
        with source.open("rb") as handle:
            os.fsync(handle.fileno())
        if final.exists():
            raise ValueError(
                "Report storage collision; no existing file was overwritten."
            )
        self.journal(aid, "upload")
        # Hard-link publication is exclusive, unlike replace/rename overwrites.
        os.link(self.folder / (aid + ".bin"), final)
        sync_directory(final.parent)

    def remove(self, rows):
        for row in rows:
            final = storage_path(self.root, row["id"])
            if row["storage_ref"] != reference(row["id"]):
                raise ValueError("Invalid report storage reference.")
            self.journal(row["id"], "remove")
            if final.exists():
                final.rename(self.folder / (row["id"] + ".bin"))
                sync_directory(final.parent)
                sync_directory(self.folder)


@contextmanager
def storage_transaction(connection, root):
    connection.execute("BEGIN IMMEDIATE")
    changes = None
    committed = False
    try:
        changes = FileChanges(root)
        yield changes
        # The application defers ordinary commit() calls until after_request.
        # File cleanup must wait for an actual durable commit, as in case import.
        sqlite3.Connection.commit(connection)
        committed = True
    except BaseException:
        connection.rollback()
        raise
    finally:
        if changes:
            # Recovery also finalizes successful operations. A crash before this
            # step is repaired on startup, without trusting temporary paths.
            try:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    recover_operation(connection, root, changes.folder)
                    sqlite3.Connection.commit(connection)
            except (OSError, ValueError):
                if not committed:
                    raise
                logging.getLogger(__name__).exception(
                    "Report change committed; cleanup journal retained for startup recovery"
                )


def register_reports(app, db, root, require, get_family, touch, event, finish, version):
    recover_storage(db(), root)

    def report(fid, aid):
        get_family(fid)
        row = (
            db()
            .execute(
                "SELECT * FROM family_reports WHERE id=? AND family_id=?", (aid, fid)
            )
            .fetchone()
        )
        if not row:
            abort(404)
        return row

    @app.post("/malware-families/<fid>/reports/upload")
    def families_reports_upload(fid):
        require(True)
        get_family(fid)
        try:
            uploads = request.files.getlist("reports")
            if not 1 <= len(uploads) <= MAX_BATCH_COUNT or any(
                not item.filename for item in uploads
            ):
                raise ValueError("Choose 1–10 PDF, DOC or DOCX reports.")
            with storage_transaction(db(), root) as changes:
                touch(fid, version())
                count = (
                    db()
                    .execute(
                        "SELECT count(*) FROM family_reports WHERE family_id=?", (fid,)
                    )
                    .fetchone()[0]
                )
                if count + len(uploads) > MAX_REPORTS:
                    raise ValueError("A family can have at most 100 reports.")
                total = 0
                for upload in uploads:
                    filename = original_name(upload.filename)
                    aid = str(uuid.uuid4())
                    path = changes.folder / (aid + ".bin")
                    digest = hashlib.sha256()
                    size = 0
                    with path.open("xb") as target:
                        os.chmod(path, 0o600)
                        while chunk := upload.stream.read(1024**2):
                            size += len(chunk)
                            total += len(chunk)
                            if size > MAX_FILE or total > MAX_BATCH:
                                raise ValueError(
                                    "Reports allow 25 MiB per file and 75 MiB per batch."
                                )
                            digest.update(chunk)
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    if not size:
                        raise ValueError("Empty reports are not accepted.")
                    mime = detected_type(path, filename)
                    changes.publish(aid)
                    db().execute(
                        "INSERT INTO family_reports VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            aid,
                            fid,
                            filename,
                            filename,
                            "",
                            reference(aid),
                            size,
                            mime,
                            digest.hexdigest(),
                            now(),
                            g.user["id"],
                        ),
                    )
                    event(
                        f"Malware family report uploaded: family={fid}, attachment={aid}, sha256={digest.hexdigest()}"
                    )
            flash(f"{len(uploads)} research report(s) uploaded.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            flash(f"Upload failed; existing reports were preserved. {exc}")
        return redirect(url_for("families_workspace", fid=fid, tab="osint"))

    @app.get("/malware-families/<fid>/reports/<aid>/download")
    def families_reports_download(fid, aid):
        require()
        # Keep removal/upload serialized until send_file opens its descriptor.
        # The descriptor remains usable if a later request removes the file.
        if "case_sync" in app.extensions:
            app.extensions["case_sync"].acquire()
        row = report(fid, aid)
        try:
            path = verify_report(root, row)
        except (ValueError, OSError):
            abort(
                409,
                "Report missing or damaged. Restore it from a verified installation backup.",
            )
        response = send_file(
            path,
            as_attachment=True,
            download_name=row["original_filename"],
            mimetype=row["file_type"],
            conditional=True,
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    @app.route("/malware-families/<fid>/reports/<aid>/edit", methods=["GET", "POST"])
    def families_reports_edit(fid, aid):
        require(True)
        family = get_family(fid)
        row = report(fid, aid)
        values = request.form if request.method == "POST" else dict(row)
        error = None
        status = 200
        if request.method == "POST":
            try:
                title = request.form.get("title", "").strip()
                description = request.form.get("description", "")
                if not title or len(title) > 300 or len(description) > 10000:
                    raise ValueError(
                        "Enter a title of 1–300 characters and a description up to 10,000 characters."
                    )
                with db():
                    touch(fid, version())
                    db().execute(
                        "UPDATE family_reports SET title=?,description=? WHERE id=? AND family_id=?",
                        (title, description, aid, fid),
                    )
                    event(
                        f"Malware family report metadata edited: family={fid}, attachment={aid}"
                    )
                return finish(fid, "osint")
            except ValueError as exc:
                error = str(exc)
                status = 409 if "another session" in str(exc) else 400
            except sqlite3.Error:
                error = "Unable to save report metadata right now. Your values are preserved; please retry."
                status = 503
        return (
            render_template(
                "malware_report_form.html",
                family=family,
                report=row,
                values=values,
                error=error,
            ),
            status,
        )

    @app.post("/malware-families/<fid>/reports/<aid>/delete")
    def families_reports_delete(fid, aid):
        require(True)
        row = report(fid, aid)
        try:
            if request.form.get("confirm") != "1":
                raise ValueError("Confirm removing the attached report.")
            with storage_transaction(db(), root) as changes:
                touch(fid, version())
                changes.remove([row])
                db().execute(
                    "DELETE FROM family_reports WHERE id=? AND family_id=?", (aid, fid)
                )
                event(f"Malware family report removed: family={fid}, attachment={aid}")
            flash("Attached report removed.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            flash(f"Report removal failed: {exc}")
        return redirect(url_for("families_workspace", fid=fid, tab="osint"))
