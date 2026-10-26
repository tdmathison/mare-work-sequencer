"""Versioned full-installation recovery. Never merges unrelated database IDs.

Offline recovery only publishes a fully validated staged data directory into an
absent destination. The web application's existing administrator backup is the
producer; portable case imports remain independent merges of case work.
"""

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile
import uuid
from backups import checked_members, read_json, MAX_TOTAL, MAX_FILE
from zip_metadata import restore_mtime

SCHEMA = "mare-installation-backup/3"
ACTOR_MIGRATION = "threat-actors-v1"
ACTOR_TABLES = {"threat_actors", "actor_osint", "actor_reports", "actor_families"}
FAMILY_MIGRATION = "family-reports-v1"
BASE_FAMILY_MIGRATION = "malware-families-v1"
COUNT_TABLES = (
    "users",
    "cases",
    "tags",
    "case_tags",
    "malware_families",
    "family_osint",
    "family_reports",
    "threat_actors", "actor_osint", "actor_reports", "actor_families",
)
FAMILY_COLUMNS = {
    "malware_families": {
        "id",
        "name",
        "tag_id",
        "short_description",
        "long_description",
        "attribution_notes",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "version",
    },
    "family_osint": {"id", "family_id", "title", "url", "position"},
}


def record_counts(connection):
    tables = {
        r[0]
        for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    return {
        table: (
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if table in tables
            else 0
        )
        for table in COUNT_TABLES
    }


def add_file(archive, source, name, entries, *, expanded=0):
    """Hash exactly the bytes written and preserve the existing ZIP timestamps."""
    source = Path(source)
    if (
        source.stat().st_size > MAX_FILE
        or expanded + source.stat().st_size > MAX_TOTAL
        or len(entries) >= 99998
    ):
        raise ValueError(
            "Installation backup exceeds recovery size limits (256 MiB per file, 2 GiB expanded, 100,000 entries)."
        )
    info = zipfile.ZipInfo.from_file(source, name, strict_timestamps=False)
    info.compress_type = zipfile.ZIP_DEFLATED
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as src, archive.open(info, "w", force_zip64=True) as dst:
        while chunk := src.read(1024**2):
            size += len(chunk)
            if size > MAX_FILE or expanded + size > MAX_TOTAL:
                raise ValueError(
                    "An installation file exceeds the 256 MiB recovery limit."
                )
            digest.update(chunk)
            dst.write(chunk)
    entries[name] = {"size": size, "sha256": digest.hexdigest()}
    return expanded + size


def validate_database(path, modern):
    # Untrusted snapshots are inspected read-only; no application startup/migration
    # happens until the entire archive has been validated and published.
    connection = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("The installation database failed integrity validation.")
        tables = {
            r[0]
            for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"users", "cases", "history", "schema_migrations"} <= tables or (
            ("tags" in tables) != ("case_tags" in tables)
        ):
            raise ValueError(
                "The archive does not contain a compatible MARE installation database."
            )
        if (
            "case_tags" in tables
            and connection.execute(
                "SELECT 1 FROM case_tags ct LEFT JOIN cases c ON c.id=ct.case_id LEFT JOIN tags t ON t.id=ct.tag_id WHERE c.id IS NULL OR t.id IS NULL LIMIT 1"
            ).fetchone()
        ):
            raise ValueError("A case tag assignment references a missing case or tag.")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(
                "The installation database has broken record relationships."
            )
        has_families = "malware_families" in tables
        if modern or has_families:
            if not set(FAMILY_COLUMNS) <= tables:
                raise ValueError("Incomplete malware-family database tables.")
            for table, fields in FAMILY_COLUMNS.items():
                if not fields <= {
                    r[1] for r in connection.execute(f"PRAGMA table_info({table})")
                }:
                    raise ValueError("Unsupported malware-family schema.")
            if not connection.execute(
                "SELECT 1 FROM schema_migrations WHERE name=?", (BASE_FAMILY_MIGRATION,)
            ).fetchone():
                raise ValueError("Missing malware-family migration marker.")
            from malware_families import family_tag, safe_url

            profiles = connection.execute(
                """SELECT f.*,t.name AS tag FROM malware_families f
                LEFT JOIN tags t ON t.id=f.tag_id"""
            )
            ids, tag_ids = set(), set()
            for row in profiles:
                if 'aliases' in row.keys():
                    from family_aliases import load_aliases
                    if load_aliases(row['aliases']) != json.loads(row['aliases']):
                        raise ValueError('Invalid untrimmed malware-family aliases.')
                for field, limit in (
                    ("name", 200),
                    ("short_description", 1000),
                    ("long_description", 100000),
                    ("attribution_notes", 100000),
                ):
                    if not isinstance(row[field], str) or len(row[field]) > limit:
                        raise ValueError("Invalid malware-family text fields.")
                if (
                    str(uuid.UUID(row["id"])) != row["id"]
                    or row["id"] in ids
                    or row["tag_id"] in tag_ids
                    or not row["name"].strip()
                    or type(row["version"]) is not int
                    or row["version"] < 1
                ):
                    raise ValueError(
                        "Invalid or duplicate malware-family identity or tag relationship."
                    )
                if family_tag(row["tag"]) != row["tag"]:
                    raise ValueError("A family references a noncanonical tag.")
                for reference in ("created_by", "updated_by"):
                    if (
                        row[reference] is not None
                        and not connection.execute(
                            "SELECT 1 FROM users WHERE id=?", (row[reference],)
                        ).fetchone()
                    ):
                        raise ValueError("A family references an unknown user.")
                ids.add(row["id"])
                tag_ids.add(row["tag_id"])
            seen, positions = set(), set()
            for entry in connection.execute("SELECT * FROM family_osint"):
                if (
                    str(uuid.UUID(entry["id"])) != entry["id"]
                    or entry["id"] in seen
                    or entry["family_id"] not in ids
                    or type(entry["position"]) is not int
                    or entry["position"] < 1
                    or (entry["family_id"], entry["position"]) in positions
                    or not isinstance(entry["title"], str)
                    or not entry["title"].strip()
                    or len(entry["title"]) > 300
                ):
                    raise ValueError(
                        "Invalid OSINT identity, order or profile relationship."
                    )
                safe_url(entry["url"])
                seen.add(entry["id"])
                positions.add((entry["family_id"], entry["position"]))
        if 'threat_actors' in tables:
            if not ACTOR_TABLES <= tables or not {'actor_import_state'} <= tables:
                raise ValueError('Incomplete Threat Actors schema.')
            if not connection.execute("SELECT 1 FROM schema_migrations WHERE name=?", (ACTOR_MIGRATION,)).fetchone():
                raise ValueError('Missing Threat Actors migration marker.')
            from family_portable import export_profiles, validate_profiles
            from profile_types import ACTOR
            from threat_actors import check_dependencies
            data = export_profiles(connection, Path(path).parent, spec=ACTOR)
            validate_profiles(data, Path(path).parent, spec=ACTOR)
            check_dependencies(connection, data['actors'])
        if "family_reports" in tables:
            from family_reports import verify_report, MAX_REPORTS

            fields = {
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
                "uploaded_by",
            }
            if not fields <= {
                r[1] for r in connection.execute("PRAGMA table_info(family_reports)")
            }:
                raise ValueError("Unsupported family report metadata schema.")
            if not connection.execute(
                "SELECT 1 FROM schema_migrations WHERE name=?", (FAMILY_MIGRATION,)
            ).fetchone():
                raise ValueError("Missing attached-report migration marker.")
            for row in connection.execute("SELECT * FROM family_reports"):
                if not connection.execute(
                    "SELECT 1 FROM malware_families WHERE id=?", (row["family_id"],)
                ).fetchone():
                    raise ValueError("An attached report references a missing family.")
                if (
                    not isinstance(row["title"], str)
                    or not row["title"].strip()
                    or len(row["title"]) > 300
                    or not isinstance(row["description"], str)
                    or len(row["description"]) > 10000
                ):
                    raise ValueError("Invalid attached report title or description.")
                if (
                    row["uploaded_by"] is not None
                    and not connection.execute(
                        "SELECT 1 FROM users WHERE id=?", (row["uploaded_by"],)
                    ).fetchone()
                ):
                    raise ValueError(
                        "An attached report references a missing uploader."
                    )
                verify_report(Path(path).parent, row)
            if connection.execute(
                "SELECT 1 FROM family_reports GROUP BY family_id HAVING count(*)>?",
                (MAX_REPORTS,),
            ).fetchone():
                raise ValueError("Too many reports for one family.")
        return record_counts(connection), has_families
    except sqlite3.DatabaseError as exc:
        raise ValueError("Invalid installation database.") from exc
    finally:
        connection.close()


def restore_installation(archive_path, destination):
    """Validate all records/files, then atomically rename a staged directory.

    The service must be stopped. Destination must not exist, so ID/name collisions,
    partial merges and repeat-import overwrites fail before touching a live tree.
    Legacy installation ZIPs are supported; case-export ZIPs are never accepted.
    """
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(
            "Destination already exists. Stop MARE and retain/move its data directory before restoring to an absent path. Installation recovery replaces an entire instance; it never merges profiles, tags or users."
        )
    if not destination.parent.is_dir():
        raise ValueError("The destination parent directory must already exist.")
    with tempfile.TemporaryDirectory(
        prefix=".mare-recovery-", dir=destination.parent
    ) as temporary:
        stage = Path(temporary) / "data"
        stage.mkdir(mode=0o700)
        with zipfile.ZipFile(archive_path) as archive:
            members, _ = checked_members(archive)
            manifest = (
                read_json(archive, "installation.json")
                if "installation.json" in members
                else None
            )
            if "data/workflow.sqlite3" not in members:
                raise ValueError(
                    "Use the database & installation backup, not a portable case export."
                )
            if any(
                name != "installation.json" and not name.startswith("data/")
                for name in members
            ):
                raise ValueError("Unexpected installation archive content.")
            if manifest is not None:
                modern_actors = manifest.get("schema") == SCHEMA
                modern_reports = manifest.get("schema") in (SCHEMA, "mare-installation-backup/2")
                compatible = (
                    modern_actors
                    and manifest.get("required_migration") == ACTOR_MIGRATION
                ) or (
                    manifest.get("schema") == "mare-installation-backup/2"
                    and manifest.get("required_migration") == FAMILY_MIGRATION
                ) or (
                    manifest.get("schema") == "mare-installation-backup/1"
                    and manifest.get("required_migration") == BASE_FAMILY_MIGRATION
                )
                if (
                    not compatible
                    or not isinstance(manifest.get("files"), dict)
                    or not isinstance(manifest.get("counts"), dict)
                ):
                    raise ValueError(
                        "Unsupported installation backup format or required schema version."
                    )
                expected_counts = (
                    set(COUNT_TABLES) if modern_actors else
                    set(COUNT_TABLES) - ACTOR_TABLES if modern_reports else
                    set(COUNT_TABLES) - ACTOR_TABLES - {"family_reports"}
                )
                if set(manifest["counts"]) != expected_counts or any(
                    type(value) is not int or value < 0
                    for value in manifest["counts"].values()
                ):
                    raise ValueError("Invalid installation record counts.")
                files = {
                    name
                    for name, info in members.items()
                    if name != "installation.json" and not info.is_dir()
                }
                if files != set(manifest["files"]):
                    raise ValueError(
                        "Installation manifest file list does not match the archive."
                    )
            for name, info in members.items():
                if name == "installation.json" or info.is_dir():
                    continue
                relative = Path(*name.split("/")[1:])
                target = stage / relative
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with archive.open(info) as src, target.open("xb") as dst:
                    os.chmod(target, 0o600)
                    while chunk := src.read(1024**2):
                        digest.update(chunk)
                        size += len(chunk)
                        dst.write(chunk)
                restore_mtime(target, info)
                if manifest is not None:
                    expected = manifest["files"][name]
                    if (
                        not isinstance(expected, dict)
                        or type(expected.get("size")) is not int
                        or expected != {"size": size, "sha256": digest.hexdigest()}
                    ):
                        raise ValueError(
                            "Installation file checksum validation failed."
                        )
            counts, has_families = validate_database(
                stage / "workflow.sqlite3", manifest is not None
            )
            if manifest is not None:
                if modern_reports and not (stage / "workflow.sqlite3").is_file():
                    raise ValueError("Missing installation database.")
                if modern_reports:
                    with sqlite3.connect(stage / "workflow.sqlite3") as con:
                        if not con.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_reports'"
                        ).fetchone():
                            raise ValueError(
                                "Missing attached-report schema in modern backup."
                            )
                expected = {key: counts[key] for key in expected_counts}
                if modern_actors:
                    with closing(sqlite3.connect(stage / "workflow.sqlite3")) as actor_connection:
                        present = {r[0] for r in actor_connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        if not ACTOR_TABLES <= present:
                            raise ValueError("Missing Threat Actors tables in modern backup.")
                if manifest["counts"] != expected:
                    raise ValueError(
                        "Installation record counts do not match the snapshot."
                    )
        if has_families:
            # Additive upgrade only after the original snapshot's hashes/counts
            # have been verified. This also permits pre-alias complete recovery.
            from family_aliases import initialize as initialize_aliases
            with closing(sqlite3.connect(stage / 'workflow.sqlite3')) as connection:
                initialize_aliases(connection)
                from threat_actors import initialize as initialize_actors
                initialize_actors(connection)
        # No running connection or partially copied tree is ever exposed. Keep all
        # integer and UUID identities together by replacing the complete database.
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared during recovery; restore cancelled.")
        stage.rename(destination)
    return {
        "counts": counts,
        "legacy": manifest is None,
        "message": (
            "Backup predates malware-family support; profiles will be initialized empty on startup."
            if not has_families
            else "Profiles, OSINT links, attached reports and tag relationships restored with their original identities."
        ),
    }
