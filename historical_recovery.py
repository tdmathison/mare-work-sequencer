"""Explicit, metadata-only recovery from an original validated RAW/backup archive."""

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import click
from werkzeug.datastructures import FileStorage
from performance_metrics import timestamp
from case_sync import validate_graph, logical_snapshot, fingerprint


def recover(connection, plans, expected, apply=False):
    results = []
    seen = set()
    now = datetime.now(timezone.utc)
    for folder, validated, meta in plans:
        source = meta.get("sync")
        if not source:
            results.append(
                {"status": "unmatched", "reason": "Archive has no stable case UUID"}
            )
            continue
        validate_graph(source, fingerprint(logical_snapshot(validated, folder / "mip")))
        identity = source["case_uuid"]
        if identity in seen:
            raise ValueError("Duplicate case UUID in recovery archive")
        seen.add(identity)
        row = connection.execute(
            "SELECT c.id,c.created,s.origin_uuid FROM cases c JOIN sync_cases s ON s.case_id=c.id WHERE s.case_uuid=?",
            (identity,),
        ).fetchone()
        original = validated[0].get("created") or ""
        date = timestamp(original)
        result = {
            "case_uuid": identity,
            "original": original,
            "current": row["created"] if row else None,
        }
        if not row or row["origin_uuid"] != source["origin_uuid"]:
            result["status"] = "unmatched"
        elif not date or date > now:
            result["status"] = "unrecoverable"
        elif timestamp(row["created"]) == date:
            result["status"] = "unchanged"
        elif timestamp(row["created"]) and expected.get(identity) != row["created"]:
            result["status"] = "review-required"
        else:
            result["status"] = "repaired" if apply else "would-repair"
            if apply:
                connection.execute(
                    "UPDATE cases SET created=? WHERE id=? AND created IS ?",
                    (original, row["id"], row["created"]),
                )
                connection.execute(
                    "INSERT INTO audit(actor,action,created) VALUES(?,?,?)",
                    (
                        "CLI",
                        "Recovered case creation timestamp from original archive: "
                        + identity,
                        now.isoformat(),
                    ),
                )
        results.append(result)
    return results


def register(app, db, backups):
    @app.cli.command("recover-case-dates")
    @click.argument(
        "archive", type=click.Path(exists=True, dir_okay=False, path_type=Path)
    )
    @click.option(
        "--raw",
        is_flag=True,
        help="Archive is a single RAW MIP rather than an all-cases backup.",
    )
    @click.option(
        "--apply",
        is_flag=True,
        help="Apply eligible repairs; default is a read-only dry run.",
    )
    @click.option(
        "--expected-current",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Reviewed JSON object mapping UUIDs to exact erroneous current timestamps. Required to replace valid dates.",
    )
    def command(archive, raw, apply, expected_current):
        try:
            expected = (
                json.loads(expected_current.read_text()) if expected_current else {}
            )
        except (OSError, ValueError) as error:
            raise click.ClickException(
                "Cannot read reviewed timestamp mapping: " + str(error)
            ) from error
        if not isinstance(expected, dict) or any(
            not isinstance(k, str) or not isinstance(v, str)
            for k, v in expected.items()
        ):
            raise click.ClickException(
                "Expected-current must be a JSON object of UUID-to-timestamp strings"
            )
        with (
            app.test_request_context(),
            tempfile.TemporaryDirectory(prefix="mws-date-recovery-") as directory,
            archive.open("rb") as stream,
        ):
            try:
                app.extensions["case_sync"].acquire()
                plans, _ = backups["stage_upload"](
                    FileStorage(stream=stream, filename=archive.name), raw, directory
                )
                connection = db()
                connection.execute("SAVEPOINT historical_recovery")
                try:
                    results = recover(connection, plans, expected, apply)
                    connection.execute("RELEASE historical_recovery")
                    connection.commit()
                except Exception:
                    connection.execute("ROLLBACK TO historical_recovery")
                    connection.execute("RELEASE historical_recovery")
                    raise
            except (ValueError, KeyError) as error:
                raise click.ClickException(str(error)) from error
            counts = {
                status: sum(row["status"] == status for row in results)
                for status in sorted({row["status"] for row in results})
            }
            click.echo(
                json.dumps(
                    {"dry_run": not apply, "counts": counts, "cases": results}, indent=2
                )
            )
