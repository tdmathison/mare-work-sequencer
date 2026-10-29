"""Deterministic names from explicit selections, with no archive-format changes."""
from datetime import datetime, timezone
from itertools import combinations
import io
import json
import re
import zipfile

import pytest
from app import app, db
import backup_filenames as names
from backup_areas import KEYS
from test_backup_workspace import setup, post, export, wait

MAPPING = (("cases", "C"), ("tags", "T"), ("actors", "TA"), ("families", "MF"))
SELECTIONS = [list(items) for size in range(1, 5) for items in combinations(dict(MAPPING), size)]


class Clock(datetime):
    instant = datetime(2026, 1, 2, 23, 4, 5, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.astimezone().replace(tzinfo=None)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(names, "datetime", Clock)
    monkeypatch.setitem(app.config, "DISPLAY_TIMEZONE", "America/Los_Angeles")


@pytest.mark.parametrize("areas", SELECTIONS)
def test_all_category_combinations_use_explicit_order_and_local_24_hour_time(clock, areas):
    suffix = "_".join(code for key, code in MAPPING if key in areas)
    # Reverse input order to prove that selection order never affects filenames.
    filename = names.archive_filename(list(reversed(areas)), "America/Los_Angeles")
    assert filename == "MWS_20260102-150405_" + suffix + ".zip"
    assert re.fullmatch(r"MWS_\d{8}-\d{6}_(?:C|T|TA|MF)(?:_(?:C|T|TA|MF))*\.zip", filename)


def test_no_categories_rejected_and_server_local_fallback(clock):
    with pytest.raises(ValueError, match="Select at least one"):
        names.archive_filename([], "UTC")
    with pytest.raises(ValueError, match="implemented"):
        names.archive_filename(["unknown"], "UTC")
    expected = Clock.instant.astimezone().strftime("%Y%m%d-%H%M%S")
    assert names.archive_filename(["tags"]) == f"MWS_{expected}_T.zip"
    assert names.archive_filename(["tags"], "UTC") == "MWS_20260102-230405_T.zip"


@pytest.mark.parametrize("areas", [["tags"], ["actors"], ["families"], ["cases", "actors", "families"], list(KEYS)])
def test_download_matches_persisted_name_and_explicit_empty_categories(clock, areas):
    client, *_ = setup()
    archive, job = export(client, areas, password="")
    suffix = "_".join(code for key, code in MAPPING if key in areas)
    expected = f"MWS_20260102-150405_{suffix}.zip"
    assert job["archive_name"] == expected
    response = client.get("/backup-restore/jobs/" + job["id"] + "/download")
    assert response.headers["Content-Disposition"] == f"attachment; filename={expected}"
    assert response.mimetype == "application/zip"
    service = app.extensions["backup_workspace"]
    assert response.data == archive == (service.job_path(job["id"]) / "backup.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        assert set(source.namelist()) == {"mare-backup.json", "payload.zip"}
        manifest = json.loads(source.read("mare-backup.json"))
        assert manifest["areas"] == sorted(areas)
        assert "archive_name" not in manifest
    if areas == ["actors"]:
        assert job["manifest"]["counts"]["threat_actors"] == 0
    if areas == ["families"]:
        assert job["manifest"]["counts"]["malware_families"] == 0
    with app.app_context():
        assert any(expected in row[0] for row in db().execute("SELECT action FROM audit"))


def test_name_is_fixed_at_job_creation_before_worker_starts(clock, monkeypatch):
    client, *_ = setup()
    service = app.extensions["backup_workspace"]
    with monkeypatch.context() as paused:
        paused.setattr(service, "submit", lambda *args: None)
        response = post(client, "/backup-restore/jobs", kind="export", areas=["tags"])
        assert response.status_code == 202
    jid = response.json["id"]
    stored = json.loads((service.job_path(jid) / "job.json").read_text())
    assert stored["archive_name"] == "MWS_20260102-150405_T.zip"
    monkeypatch.setattr(Clock, "instant", datetime(2030, 12, 31, 1, 2, 3, tzinfo=timezone.utc))
    service.submit(stored, "export", "")
    completed = wait(client, jid, "completed")
    assert completed["archive_name"] == stored["archive_name"]
    response = client.get("/backup-restore/jobs/" + jid + "/download")
    assert stored["archive_name"] in response.headers["Content-Disposition"]


def test_complete_backup_and_legacy_job_download_names(clock):
    client, *_ = setup()
    archive, job = export(client, complete=True)
    assert job["archive_name"] == "MWS_20260102-150405_C_T_TA_MF.zip"
    service = app.extensions["backup_workspace"]
    # Older durable jobs have no archive_name. Resolve using their original start.
    job.pop("archive_name")
    job["created_at"] = "2026-01-02T23:04:05+00:00"
    service.save(job)
    response = client.get("/backup-restore/jobs/" + job["id"] + "/download")
    assert "MWS_20260102-150405_C_T_TA_MF.zip" in response.headers["Content-Disposition"]
    assert response.data == archive


def test_empty_selection_rejected_and_old_filename_import_still_works(clock):
    client, *_ = setup()
    response = post(client, "/backup-restore/jobs", kind="export", areas=[])
    assert response.status_code == 400 and "Select at least one" in response.json["error"]
    archive, _ = export(client, ["tags"], password="")
    response = post(client, "/backup-restore/jobs", kind="inspect", archive=(io.BytesIO(archive), "MARE-backup-old-name.zip"))
    assert response.status_code == 202
    assert wait(client, response.json["id"])["state"] == "preview"


def test_legacy_portable_endpoint_uses_same_name(clock):
    client, *_ = setup()
    response = post(client, "/import-export/export")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == "attachment; filename=MWS_20260102-150405_C_T_TA_MF.zip"
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as source:
        assert "backup.json" in source.namelist()


def test_timezone_date_boundary_and_midnight_zero_padding():
    instant = datetime(2026, 1, 2, 3, 2, 3, tzinfo=timezone.utc)
    assert names.archive_filename(["cases"], "America/Los_Angeles", started_at=instant) == "MWS_20260101-190203_C.zip"
    midnight = datetime(2026, 1, 2, 8, 2, 3, tzinfo=timezone.utc)
    assert names.archive_filename(["cases"], "America/Los_Angeles", started_at=midnight) == "MWS_20260102-000203_C.zip"
