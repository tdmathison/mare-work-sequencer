"""Historical reporting uses authoritative dates and actual portable events."""

import io
import json
from datetime import datetime, timezone
import pytest
from app import app, db, run, ensure_package
from performance_metrics import scorecard
from test_performance_metrics import add_case, event, NOW
from test_backups import setup_backup_case
from sync_helpers import other_destination


def test_all_time_includes_historical_current_and_zero_weeks():
    with app.app_context():
        for date in (
            "2025-12-31T23:30:00-01:00",
            "2026-01-04T23:59:59Z",
            "2026-10-14T09:00:00Z",
            "",
            "2099-01-01",
        ):
            add_case(date)
        data = scorecard(db(), "all", NOW)
        assert data["start"] == "2025-12-29"
        assert data["end"] == "2026-10-14"
        assert data["created"] == 3
        assert data["weekly"][0]["created"] == 2
        assert data["weekly"][-1]["created"] == 1
        assert any(w["created"] == 0 for w in data["weekly"])
        assert [w["start"] for w in data["weekly"]] == sorted(
            w["start"] for w in data["weekly"]
        )
        assert scorecard(db(), 4, NOW)["created"] == 0
        assert data["invalid_creation"] == 2


def test_24_imported_completed_cases_round_trip_without_duplicates():
    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        run("DELETE FROM cases WHERE id<>?", (cid,))
        run(
            "UPDATE cases SET created='2024-01-01T08:00:00Z',stage=3 WHERE id=?", (cid,)
        )
        run("DELETE FROM history WHERE case_id=?", (cid,))
        event(cid, "2024-01-02", 0)
        event(cid, "2024-01-04", 1)
        event(cid, "2024-01-06", 2)
        for index in range(1, 24):
            created = "2024-01-01" if index < 12 else "2024-03-04"
            new = add_case(created, stage=3, owner=uid, creator=uid)
            ensure_package(new)
            if index < 23:
                event(new, "2024-04-01")
        db().commit()
    exported = post("/import-export/export")
    assert exported.status_code == 200
    with app.app_context():
        # Simulate a fresh destination while keeping local accounts/configuration.
        db().commit()
        db().execute("PRAGMA foreign_keys=OFF")
        for row in (
            db().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ):
            if "case_id" in {
                column[1]
                for column in db().execute('PRAGMA table_info("' + row[0] + '")')
            }:
                db().execute('DELETE FROM "' + row[0] + '"')
        db().execute("DELETE FROM cases")
        db().execute("DELETE FROM sync_revisions")
        db().commit()
        db().execute("PRAGMA foreign_keys=ON")
        db().commit()
        import shutil
        from app import ROOT

        shutil.rmtree(ROOT / "cases")
    response = post(
        "/import-export/import", backup=(io.BytesIO(exported.data), "historical.zip")
    )
    assert response.status_code == 302, response.data
    with app.app_context():
        data = scorecard(db(), "all", NOW)
        assert data["total"] == data["completed_current"] == 24
        assert data["created"] == 24
        assert data["weekly"][0]["created"] == 12
        assert data["completed"] == 23
        assert data["missing_completion"] == 1
        assert data["workflow"]["durations"]["analysis"]["median"] == 2
        assert data["workflow"]["durations"]["packaging"]["median"] == 2
        rows = [
            tuple(row)
            for row in db().execute(
                "SELECT stage,author,created,outcome FROM history ORDER BY id"
            )
        ]
        assert len(rows) == 25
        assert min(
            row["created"] for row in db().execute("SELECT created FROM cases")
        ).startswith("2024")
    post("/import-export/import", backup=(io.BytesIO(exported.data), "again.zip"))
    with app.app_context():
        assert scorecard(db(), "all", NOW)["total"] == 24
        assert [
            tuple(row)
            for row in db().execute(
                "SELECT stage,author,created,outcome FROM history ORDER BY id"
            )
        ] == rows
    assert 'id="metrics-total">24' in client.get("/metrics").text
    assert "All time (default)</option>" in client.get("/metrics").text


def test_missing_creation_not_replaced_by_import_date():
    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        run("UPDATE cases SET created='',stage=3 WHERE id=?", (cid,))
        run("DELETE FROM history WHERE case_id=?", (cid,))
    blob = post(f"/cases/{cid}/backup").data
    other_destination()
    post("/import-export/import-raw", backup=(io.BytesIO(blob), "unknown.zip"))
    with app.app_context():
        imported = (
            db().execute("SELECT * FROM cases ORDER BY id DESC LIMIT 1").fetchone()
        )
        assert imported["created"] == "" and imported["stage"] == 3
        assert scorecard(db(), "all", NOW)["missing_completion"] == 2


def test_actual_workflow_intervals_and_missing_history():
    with app.app_context():
        cid = add_case("2026-09-01", stage=3)
        for stage, date in [(0, "2026-09-03"), (1, "2026-09-06"), (2, "2026-09-10")]:
            event(cid, date, stage)
        add_case("2026-09-01", stage=3)
        metrics = scorecard(db(), "all", NOW)
        assert metrics["median"] == 9
        durations = metrics["workflow"]["durations"]
        assert durations["waiting"] == {"median": 2, "records": 1}
        assert durations["analysis"]["median"] == 3
        assert durations["packaging"]["median"] == 4
        assert durations["analysis_to_completion"]["median"] == 7
        assert metrics["missing_completion"] == 1
        assert metrics["workflow"]["transitions"] == 3


def test_recovery_is_reviewed_idempotent_metadata_only(tmp_path):
    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        run("UPDATE cases SET created='2024-02-04T01:00:00Z' WHERE id=?", (cid,))
    blob = post(f"/cases/{cid}/backup").data
    archive = tmp_path / "original.zip"
    archive.write_bytes(blob)
    with app.app_context():
        uuid = (
            db()
            .execute("SELECT case_uuid FROM sync_cases WHERE case_id=?", (cid,))
            .fetchone()[0]
        )
        run("UPDATE cases SET created='2026-11-17T10:00:00Z' WHERE id=?", (cid,))
        before = dict(db().execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())
    runner = app.test_cli_runner()
    dry = runner.invoke(args=["recover-case-dates", str(archive), "--raw"])
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.output)["counts"] == {"review-required": 1}
    expected = tmp_path / "reviewed.json"
    expected.write_text(json.dumps({uuid: before["created"]}))
    dry = runner.invoke(
        args=[
            "recover-case-dates",
            str(archive),
            "--raw",
            "--expected-current",
            str(expected),
        ]
    )
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.output)["counts"] == {"would-repair": 1}
    with app.app_context():
        assert (
            dict(db().execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())
            == before
        )
    repaired = runner.invoke(
        args=[
            "recover-case-dates",
            str(archive),
            "--raw",
            "--expected-current",
            str(expected),
            "--apply",
        ]
    )
    assert repaired.exit_code == 0, repaired.output
    assert json.loads(repaired.output)["counts"] == {"repaired": 1}
    with app.app_context():
        after = dict(db().execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())
        assert after.pop("created") == "2024-02-04T01:00:00Z"
        before.pop("created")
        assert after == before
    again = runner.invoke(
        args=[
            "recover-case-dates",
            str(archive),
            "--raw",
            "--expected-current",
            str(expected),
            "--apply",
        ]
    )
    assert again.exit_code == 0, again.output
    assert json.loads(again.output)["counts"] == {"unchanged": 1}


def test_single_current_week_renders_without_division_by_zero():
    with app.app_context():
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES('metrics-viewer','unused','Administrator',0)"
        ).lastrowid
        add_case(datetime.now(timezone.utc).isoformat())
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="test")
    response = c.get("/metrics?weeks=all")
    assert response.status_code == 200
    assert "Current partial week excluded" not in response.text


def test_completion_without_creation_still_has_historical_week():
    with app.app_context():
        cid = add_case("", stage=3)
        event(cid, "2024-02-05")
        data = scorecard(db(), "all", NOW)
        assert data["created"] == 0 and data["completed"] == 1
        assert data["weekly"][0]["completed"] == 1
        assert data["median"] is None
        assert data["invalid_creation"] == 1


@pytest.mark.parametrize("prefix", ["", "/mws"])
def test_metrics_period_form_supports_production_mount(prefix, monkeypatch):
    monkeypatch.setattr(app.wsgi_app, "prefix", prefix)
    monkeypatch.setitem(app.config, "APPLICATION_ROOT", prefix or "/")
    monkeypatch.setitem(app.config, "SESSION_COOKIE_PATH", prefix or "/")
    with app.app_context():
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES('mounted-metrics','unused','Administrator',0)"
        ).lastrowid
        add_case("2023-03-01", stage=3)
    base = "http://localhost" + prefix + "/"
    client = app.test_client()
    with client.session_transaction(base_url=base) as session:
        session.update(uid=uid, version=1, csrf="test")
    response = client.get("/metrics", base_url=base)
    assert response.status_code == 200
    assert 'action="' + prefix + '/metrics"' in response.text
    assert 'id="metrics-total">1' in response.text
    assert "2023-02-27" in response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    assert client.get("/metrics?weeks=4", base_url=base).status_code == 200


def test_incomplete_and_reopened_histories_do_not_invent_durations():
    with app.app_context():
        cid = add_case("2024-01-01", stage=3)
        event(
            cid, "2024-01-03", stage=1
        )  # Missing analysis start: packaging can be timed.
        event(cid, "2024-01-04", stage=2)
        event(cid, "2024-01-05", stage=3, outcome="Reopened")
        event(cid, "2024-01-08", stage=1)
        event(
            cid, "2024-01-07", stage=2
        )  # Negative packaging interval must be excluded.
        data = scorecard(db(), "all", NOW)
        durations = data["workflow"]["durations"]
        assert durations["waiting"]["records"] == durations["analysis"]["records"] == 0
        assert durations["analysis_to_completion"]["records"] == 0
        assert durations["packaging"] == {"median": 1, "records": 1}


def test_unmatched_original_identities_survive_reexport():
    import zipfile

    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        original_uuid = (
            db().execute("SELECT user_uuid FROM users WHERE id=?", (uid,)).fetchone()[0]
        )
    archive = post(f"/cases/{cid}/backup").data
    with app.app_context():
        run("UPDATE users SET username='renamed-importer' WHERE id=?", (uid,))
    other_destination()
    post("/import-export/import-raw", backup=(io.BytesIO(archive), "identity.zip"))
    with app.app_context():
        new_id = db().execute("SELECT max(id) FROM cases").fetchone()[0]
    exported = post(f"/cases/{new_id}/backup")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.data)) as source:
        metadata = json.loads(
            source.read(
                next(
                    name
                    for name in source.namelist()
                    if name.endswith("/case-data.json")
                )
            )
        )
    assert metadata["source_creator"] == {
        "username": "backup-user",
        "user_uuid": original_uuid,
    }
    assert metadata["source_assignee"] == {
        "username": "backup-user",
        "user_uuid": original_uuid,
    }
