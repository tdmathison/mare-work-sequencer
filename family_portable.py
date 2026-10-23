"""One shared family section in Export All, never in individual case archives."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
from family_reports import verify_report, storage_transaction, MAX_REPORTS
from malware_families import family_tag, safe_url
from tagging import create as create_tag, now

SCHEMA = "mare-family-library/1"
FIELDS = (
    "id",
    "name",
    "short_description",
    "long_description",
    "attribution_notes",
    "created_at",
    "updated_at",
    "version",
)
REPORT_FIELDS = (
    "id",
    "family_id",
    "title",
    "original_filename",
    "description",
    "storage_ref",
    "size",
    "file_type",
    "sha256",
    "uploaded_at",
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def export_library(connection, root):
    users = {
        row["id"]: {"username": row["username"], "user_uuid": row["user_uuid"]}
        for row in connection.execute("SELECT id,username,user_uuid FROM users")
    }
    families = []
    for row in connection.execute(
        "SELECT f.*,t.name AS tag,i.identity FROM malware_families f JOIN tags t ON t.id=f.tag_id JOIN family_tag_identities i ON i.tag_id=t.id ORDER BY f.id"
    ):
        record = {key: row[key] for key in FIELDS}
        record.update(
            tag=row["tag"],
            tag_identity=row["identity"],
            created_by=users.get(row["created_by"]),
            updated_by=users.get(row["updated_by"]),
        )
        record["osint"] = [
            dict(entry)
            for entry in connection.execute(
                "SELECT * FROM family_osint WHERE family_id=? ORDER BY position,id",
                (row["id"],),
            )
        ]
        record["reports"] = []
        for report in connection.execute(
            "SELECT * FROM family_reports WHERE family_id=? ORDER BY uploaded_at,id",
            (row["id"],),
        ):
            verify_report(root, report)
            record["reports"].append(
                {
                    **{key: report[key] for key in REPORT_FIELDS},
                    "uploaded_by": users.get(report["uploaded_by"]),
                }
            )
        families.append(record)
    if (
        len(families)
        != connection.execute("SELECT count(*) FROM malware_families").fetchone()[0]
    ):
        raise ValueError(
            "A malware family has a missing tag identity; repair it before exporting."
        )
    if (
        sum(len(f["reports"]) for f in families)
        != connection.execute("SELECT count(*) FROM family_reports").fetchone()[0]
    ):
        raise ValueError("An attached report has a missing parent family.")
    return {"schema": SCHEMA, "families": families}


def validate_library(data, root):
    if (
        not isinstance(data, dict)
        or set(data) != {"schema", "families"}
        or data["schema"] != SCHEMA
        or not isinstance(data["families"], list)
        or len(data["families"]) > 10000
    ):
        raise ValueError("Unsupported shared malware-family library.")
    profiles = set()
    tags = set()
    identities = set()
    entries = set()
    attachments = set()

    def identity(value):
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError("Invalid shared library identity.")

    def user(value):
        if value is not None and (
            not isinstance(value, dict)
            or set(value) != {"username", "user_uuid"}
            or not isinstance(value["username"], str)
            or len(value["username"]) > 200
            or not isinstance(value["user_uuid"], str)
            or len(value["user_uuid"]) > 100
        ):
            raise ValueError("Invalid shared library user reference.")

    for record in data["families"]:
        if not isinstance(record, dict) or set(record) != set(FIELDS) | {
            "tag",
            "tag_identity",
            "created_by",
            "updated_by",
            "osint",
            "reports",
        }:
            raise ValueError("Invalid family library record.")
        identity(record["id"])
        if (
            record["id"] in profiles
            or record["tag"] in tags
            or record["tag_identity"] in identities
            or family_tag(record["tag"]) != record["tag"]
            or not re.fullmatch("[a-f0-9]{32}", record["tag_identity"])
        ):
            raise ValueError("Duplicate or invalid family/tag identity.")
        profiles.add(record["id"])
        tags.add(record["tag"])
        identities.add(record["tag_identity"])
        for field, limit in (
            ("name", 200),
            ("short_description", 1000),
            ("long_description", 100000),
            ("attribution_notes", 100000),
            ("created_at", 100),
            ("updated_at", 100),
        ):
            if not isinstance(record[field], str) or len(record[field]) > limit:
                raise ValueError("Invalid family library text.")
        if (
            not record["name"].strip()
            or type(record["version"]) is not int
            or record["version"] < 1
        ):
            raise ValueError("Invalid family name or version.")
        user(record["created_by"])
        user(record["updated_by"])
        if (
            not isinstance(record["osint"], list)
            or len(record["osint"]) > 1000
            or not isinstance(record["reports"], list)
            or len(record["reports"]) > MAX_REPORTS
        ):
            raise ValueError("Shared family record limits exceeded.")
        positions = set()
        for entry in record["osint"]:
            if not isinstance(entry, dict) or set(entry) != {
                "id",
                "family_id",
                "title",
                "url",
                "position",
            }:
                raise ValueError("Invalid shared OSINT entry.")
            identity(entry["id"])
            if (
                entry["id"] in entries
                or entry["family_id"] != record["id"]
                or type(entry["position"]) is not int
                or entry["position"] < 1
                or entry["position"] in positions
                or not isinstance(entry["title"], str)
                or not entry["title"].strip()
                or len(entry["title"]) > 300
            ):
                raise ValueError("Invalid shared OSINT relationship/order.")
            safe_url(entry["url"])
            entries.add(entry["id"])
            positions.add(entry["position"])
        for report in record["reports"]:
            if not isinstance(report, dict) or set(report) != set(REPORT_FIELDS) | {
                "uploaded_by"
            }:
                raise ValueError("Invalid shared report record.")
            identity(report["id"])
            if (
                report["id"] in attachments
                or report["family_id"] != record["id"]
                or not isinstance(report["title"], str)
                or not report["title"].strip()
                or len(report["title"]) > 300
                or not isinstance(report["description"], str)
                or len(report["description"]) > 10000
                or not isinstance(report["uploaded_at"], str)
                or len(report["uploaded_at"]) > 100
            ):
                raise ValueError("Invalid shared report relationship or metadata.")
            user(report["uploaded_by"])
            verify_report(root, report)
            attachments.add(report["id"])
    return {
        "profiles": len(profiles),
        "osint": len(entries),
        "reports": len(attachments),
    }


def check_conflicts(connection, root, data):
    """Never silently overwrite destination research; exact repeats are skipped."""
    current = {
        record["id"]: record for record in export_library(connection, root)["families"]
    }
    skip = set()
    for record in data["families"]:
        fid = record["id"]
        if fid in current:
            incoming = fingerprint(record)
            local = fingerprint(current[fid])
            state = connection.execute(
                "SELECT * FROM family_import_state WHERE family_id=?", (fid,)
            ).fetchone()
            if incoming == local or (
                state
                and state["incoming_hash"] == incoming
                and state["local_hash"] == local
            ):
                skip.add(fid)
                continue
            raise ValueError(
                f'Shared family conflict: {record["name"]}. Keep the destination research, or explicitly delete/relink the conflicting profile after retaining a backup, then preview again. No shared records were overwritten.'
            )
        tag = connection.execute(
            "SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE t.normalized_name=? OR i.identity=?",
            (record["tag"], record["tag_identity"]),
        ).fetchall()
        if tag and (
            len(tag) != 1
            or tag[0]["name"] != record["tag"]
            or tag[0]["identity"] != record["tag_identity"]
        ):
            raise ValueError(
                "Shared tag identity/name conflict for "
                + record["tag"]
                + ". Resolve it explicitly in Tags before retrying; unrelated IDs are never reused."
            )
        if (
            tag
            and connection.execute(
                "SELECT 1 FROM malware_families WHERE tag_id=?", (tag[0]["id"],)
            ).fetchone()
        ):
            raise ValueError(
                "A destination profile already uses "
                + record["tag"]
                + ". Resolve its profile-to-tag conflict before retrying."
            )
        for entry in record["osint"]:
            if connection.execute(
                "SELECT 1 FROM family_osint WHERE id=?", (entry["id"],)
            ).fetchone():
                raise ValueError("OSINT entry identity collision.")
        for report in record["reports"]:
            if (
                connection.execute(
                    "SELECT 1 FROM family_reports WHERE id=?", (report["id"],)
                ).fetchone()
                or (Path(root) / report["storage_ref"]).exists()
            ):
                raise ValueError("Attached report identity or storage collision.")
    return skip


def restore_library(connection, root, staged, data, registry=None):
    validate_library(data, staged)

    def user(source):
        if source is None:
            return None
        # Follow existing portable import attribution: exact username mapping,
        # never numeric IDs; missing destination users remain NULL.
        row = connection.execute(
            "SELECT id FROM users WHERE username=?", (source["username"],)
        ).fetchone()
        return row[0] if row else None

    with storage_transaction(connection, root) as changes:
        if registry:
            from backup_areas import merge_registry
            merge_registry(connection,registry)
        skip = check_conflicts(connection, root, data)
        for record in data["families"]:
            if record["id"] in skip:
                continue
            tid, _ = create_tag(connection, record["tag"])
            connection.execute(
                "UPDATE family_tag_identities SET identity=? WHERE tag_id=?",
                (record["tag_identity"], tid),
            )
            connection.execute(
                "INSERT INTO malware_families(id,name,short_description,long_description,attribution_notes,created_at,updated_at,version,tag_id,created_by,updated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    *[record[key] for key in FIELDS],
                    tid,
                    user(record["created_by"]),
                    user(record["updated_by"]),
                ],
            )
            for entry in record["osint"]:
                connection.execute(
                    "INSERT INTO family_osint VALUES(?,?,?,?,?)",
                    [
                        entry[key]
                        for key in ("id", "family_id", "title", "url", "position")
                    ],
                )
            for report in record["reports"]:
                shutil.copyfile(
                    Path(staged) / report["storage_ref"],
                    changes.folder / (report["id"] + ".bin"),
                )
                changes.publish(report["id"])
                connection.execute(
                    "INSERT INTO family_reports VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        *[report[key] for key in REPORT_FIELDS],
                        user(report["uploaded_by"]),
                    ],
                )
        local = {r["id"]: r for r in export_library(connection, root)["families"]}
        for record in data["families"]:
            connection.execute(
                "INSERT OR REPLACE INTO family_import_state VALUES(?,?,?)",
                (record["id"], fingerprint(record), fingerprint(local[record["id"]])),
            )
    return {**validate_library(data, staged), "unchanged": len(skip)}
