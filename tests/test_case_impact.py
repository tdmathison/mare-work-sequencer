import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from app import app, db, run, ensure_package
import case_impact as impact
from performance_metrics import scorecard
from test_api import make_user
from test_performance_metrics import add_case, event, NOW
from test_backups import setup_backup_case
from sync_helpers import other_destination

VALUE = {
    "impact_confirmed": True,
    "impact_type": "both",
    "impact_summary": "  Confirmed enterprise discovery\nand a new detection.  ",
}
STAMP = "2024-02-05T12:00:00+00:00"


def record(cid):
    with app.app_context():
        return dict(db().execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())


def test_migration_is_repeatable_and_preserves_existing_cases():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE cases(id INTEGER PRIMARY KEY,name TEXT)")
    con.execute("INSERT INTO cases VALUES(1,'Existing')")
    impact.initialize(con)
    impact.initialize(con)
    row = con.execute(
        "SELECT name," + ",".join(impact.FIELDS) + " FROM cases"
    ).fetchone()
    assert row == ("Existing", 0, None, "", None)


@pytest.mark.parametrize("stage", [0, 1, 2, 3])
def test_web_impact_independent_of_stage_and_owner(stage):
    uid, _ = make_user("impact-web")
    with app.app_context():
        cid = add_case("2024-01-01", stage=stage)
        ensure_package(cid)
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="impact")
    url = f"/cases/{cid}"
    assert (
        c.post(url, data={"operation": "impact", "impact_confirmed": "1"}).status_code
        == 403
    )
    bad = c.post(
        url,
        data={
            "csrf": "impact",
            "operation": "impact",
            "impact_confirmed": "1",
            "ajax": "1",
        },
    )
    assert bad.status_code == 400
    enabled = c.post(
        url,
        data={
            "csrf": "impact",
            "operation": "impact",
            "impact_confirmed": "1",
            "impact_type": "both",
            "impact_summary": VALUE["impact_summary"],
            "ajax": "1",
        },
    )
    assert enabled.status_code == 200, enabled.data
    first = record(cid)
    assert first["stage"] == stage and first["owner"] is None
    assert first["impact_summary"] == VALUE["impact_summary"].strip()
    assert first["impact_confirmed_at"]
    assert 'id="case-impact" open' in c.get(url).text
    disabled = c.post(url, data={"csrf": "impact", "operation": "impact", "ajax": "1"})
    assert disabled.status_code == 200
    assert record(cid)["impact_confirmed"] == 0
    assert record(cid)["impact_summary"] == first["impact_summary"]
    c.post(
        url,
        data={
            "csrf": "impact",
            "operation": "impact",
            "impact_confirmed": "1",
            "impact_type": "detection",
            "impact_summary": "Edited",
            "ajax": "1",
        },
    )
    assert record(cid)["impact_confirmed_at"] == first["impact_confirmed_at"]


def test_api_create_patch_defaults_timestamp_and_unrelated_edits():
    uid, headers = make_user("impact-api")
    c = app.test_client()
    result = c.post("/api/v1/cases", headers=headers, json={"name": "API impact"})
    assert result.status_code == 201, result.data
    row = result.json["case"]
    cid = row["id"]
    assert row["impact_confirmed"] is False and row["impact_confirmed_at"] is None
    result = c.patch(f"/api/v1/cases/{cid}", headers=headers, json=VALUE)
    assert result.status_code == 200, result.data
    row = result.json["case"]
    stamp = row["impact_confirmed_at"]
    assert row["impact_confirmed"] is True and stamp
    c.patch(f"/api/v1/cases/{cid}", headers=headers, json={"name": "Renamed"})
    assert record(cid)["impact_confirmed_at"] == stamp
    c.patch(f"/api/v1/cases/{cid}", headers=headers, json={"impact_confirmed": False})
    assert record(cid)["impact_summary"] == VALUE["impact_summary"].strip()
    c.patch(f"/api/v1/cases/{cid}", headers=headers, json={"impact_confirmed": True})
    assert record(cid)["impact_confirmed_at"] == stamp
    assert (
        c.get(f"/api/v1/cases/{cid}", headers=headers).json["case"]["impact_type"]
        == "both"
    )
    created = c.post(
        "/api/v1/cases", headers=headers, json={"name": "Initially impactful", **VALUE}
    )
    assert created.status_code == 201 and created.json["case"]["impact_confirmed_at"]


@pytest.mark.parametrize(
    "changes",
    [
        {"impact_confirmed": True},
        {"impact_confirmed": True, "impact_type": "invalid", "impact_summary": "x"},
        {"impact_confirmed": True, "impact_type": "detection", "impact_summary": "   "},
        {"impact_summary": "x" * 4001},
        {"impact_confirmed": "true"},
        {"impact_confirmed": 1},
        {"impact_type": ["detection"]},
        {"impact_summary": None},
        {"impact_confirmed_at": STAMP},
    ],
)
def test_api_validation_is_atomic(changes):
    uid, headers = make_user("impact-validation")
    c = app.test_client()
    cid = c.post("/api/v1/cases", headers=headers, json={"name": "Unchanged"}).json[
        "case"
    ]["id"]
    response = c.patch(
        f"/api/v1/cases/{cid}", headers=headers, json={"name": "Do not save", **changes}
    )
    assert response.status_code == 400, response.data
    assert record(cid)["name"] == "Unchanged" and not record(cid)["impact_confirmed"]


def test_existing_permissions_apply_to_impact():
    uid, headers = make_user("impact-reader", "reader")
    with app.app_context():
        run(
            "INSERT INTO roles(name,description,builtin) VALUES('reader','Read only',0)"
        )
        run("INSERT INTO role_permissions VALUES('reader','cases:read')")
        cid = add_case("2024-01-01")
        ensure_package(cid)
    c = app.test_client()
    assert (
        c.patch(f"/api/v1/cases/{cid}", headers=headers, json=VALUE).status_code == 403
    )
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="reader")
    assert (
        c.post(
            f"/cases/{cid}",
            data={
                "csrf": "reader",
                "operation": "impact",
                "impact_confirmed": "1",
                "impact_type": "both",
                "impact_summary": "No",
            },
        ).status_code
        == 403
    )
    assert not record(cid)["impact_confirmed"]


def test_board_badges_filters_and_workflow_colors():
    uid, _ = make_user("impact-board")
    with app.app_context():
        first = add_case("2024-01-01", stage=3)
        ensure_package(first)
        second = add_case("2024-02-01", stage=1)
        ensure_package(second)
        impact.write(db(), first, impact.patch({}, VALUE, STAMP))
        db().commit()
        from tagging import create

        tag = create(db(), "IMPACT_CASE")[0]
        run(
            "INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)",
            (first, tag, "2024"),
        )
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="impact")
    page = c.get("/?view=cards").text
    assert page.count('class="impact-preview"') == 1 and "state-populated" in page
    assert "Confirmed enterprise discovery" in page
    from flask import template_rendered

    contexts = []

    def capture(sender, template, context, **extra):
        if template.name == "dashboard.html":
            contexts.append(context)

    with template_rendered.connected_to(capture, app):
        response = c.get(f"/?impact=yes&stage=3&tag={tag}&q=Metrics&view=table")
        assert response.status_code == 200
        assert [row["id"] for row in contexts[-1]["cases"]] == [first]
        assert "is-completed" in response.text and "★ Impact" in response.text
        c.get("/?impact=no")
        assert [row["id"] for row in contexts[-1]["cases"]] == [second]
    assert c.get("/?impact=invalid").status_code == 400
    sorted_page = c.post(
        "/account/board-sort",
        data={"csrf": "impact", "column": "title", "direction": "asc", "impact": "yes"},
    )
    assert "impact=yes" in sorted_page.location


def test_metrics_rates_outcomes_history_unknown_dates_and_refresh():
    with app.app_context():
        ids = []
        for kind in ("detection", "discovery", "both"):
            cid = add_case("2024-01-01", stage=3)
            ids.append(cid)
            impact.write(
                db(),
                cid,
                impact.patch(
                    {}, {**VALUE, "impact_type": kind}, "2026-10-14T10:00:00Z"
                ),
            )
            event(cid, "2024-03-04")
        add_case("2024-01-01")
        data = scorecard(db(), "all", NOW)
        assert data["impact"]["total"] == 3 and data["impact"]["denominator"] == 4
        assert data["impact"]["rate"] == 75
        assert data["impact"]["detection"] == data["impact"]["discovery"] == 2
        assert data["impact"]["breakdown"] == {
            "detection": 1,
            "discovery": 1,
            "both": 1,
        }
        assert (
            next(w for w in data["impact"]["weekly"] if w["start"] == "2024-03-04")[
                "impact"
            ]
            == 3
        )
        assert (
            scorecard(db(), 4, NOW)["impact"]["total"] == 0
        )  # completion, not recent confirmation
        run("UPDATE cases SET impact_confirmed=0 WHERE id=?", (ids[0],))
        assert scorecard(db(), "all", NOW)["impact"]["total"] == 2
        unknown = add_case("", stage=3)
        impact.write(
            db(),
            unknown,
            {
                **impact.DEFAULTS,
                "impact_confirmed": 1,
                "impact_type": "both",
                "impact_summary": "Legacy unknown",
            },
        )
        alltime = scorecard(db(), "all", NOW)["impact"]
        assert alltime["total"] == 3 and alltime["undated"] == 1
        assert sum(w["impact"] for w in alltime["weekly"]) == 2


def test_reporting_date_fallbacks_and_recent_denominator():
    with app.app_context():
        old = add_case("2020-01-01", stage=1)
        impact.write(db(), old, impact.patch({}, VALUE, "2026-09-20T10:00:00Z"))
        fallback = add_case("2026-09-21", stage=1)
        impact.write(
            db(),
            fallback,
            {
                **impact.DEFAULTS,
                "impact_confirmed": 1,
                "impact_type": "detection",
                "impact_summary": "Imported without confirmation date",
            },
        )
        add_case("2026-09-22")
        data = scorecard(db(), 4, NOW)["impact"]
        assert data["total"] == 2 and data["denominator"] == 3 and data["rate"] == 66.7
        assert {row["date_source"] for row in data["rows"]} == {
            "First confirmation",
            "Creation fallback",
        }
        assert sum(w["impact"] for w in data["weekly"]) == 2


@pytest.mark.parametrize("full", [False, True])
def test_portable_impact_round_trip_original_dates_and_deduplication(full):
    client, cid, uid, post = setup_backup_case()
    with app.app_context():
        run("UPDATE cases SET created='2024-01-01' WHERE id=?", (cid,))
        impact.write(db(), cid, impact.patch({}, VALUE, STAMP))
        db().commit()
    archive = post("/import-export/export" if full else f"/cases/{cid}/backup")
    assert archive.status_code == 200
    other_destination()
    endpoint = "/import-export/import" if full else "/import-export/import-raw"
    response = post(endpoint, backup=(io.BytesIO(archive.data), "impact.zip"))
    assert response.status_code == 302
    with app.app_context():
        imported = (
            db()
            .execute("SELECT * FROM cases WHERE impact_confirmed=1 AND id<>?", (cid,))
            .fetchone()
        )
        assert imported and imported["impact_confirmed_at"] == STAMP
        assert imported["impact_summary"] == VALUE["impact_summary"].strip()
        assert imported["created"] == "2024-01-01"
        before = db().execute("SELECT count(*) FROM cases").fetchone()[0]
    post(endpoint, backup=(io.BytesIO(archive.data), "again.zip"))
    with app.app_context():
        assert db().execute("SELECT count(*) FROM cases").fetchone()[0] == before


def strip_impact(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    path = next(name for name in files if name.endswith("/case-data.json"))
    meta = json.loads(files[path])
    for key in impact.FIELDS:
        meta["case"].pop(key, None)
    files[path] = json.dumps(meta).encode()
    manifest_path = next(name for name in files if name.endswith("/manifest.json"))
    manifest = json.loads(files[manifest_path])
    item = next(item for item in manifest["files"] if item["path"] == "case-data.json")
    item.update(sha256=hashlib.sha256(files[path]).hexdigest(), size=len(files[path]))
    files[manifest_path] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return out.getvalue()


def test_older_archives_default_disabled_and_do_not_erase_local_impact():
    from test_case_sync import incoming, preview, apply

    c, cid, uid, post = setup_backup_case()
    old = strip_impact(post(f"/cases/{cid}/backup").data)
    with app.app_context():
        impact.write(db(), cid, impact.patch({}, VALUE, STAMP))
        db().commit()
    branch, _ = incoming(old, "Old client metadata edit")
    operation, plan = preview(c, branch)
    outcomes = apply(c, operation, {"decision-0": "replace"})
    assert outcomes[0]["action"] not in ("Failed and rolled back", "Failed"), outcomes
    assert (
        record(cid)["impact_confirmed"] == 1
        and record(cid)["impact_confirmed_at"] == STAMP
    )
    foreign, _ = incoming(old, "Imported legacy", foreign=True)
    operation, _ = preview(c, foreign)
    apply(c, operation, {"decision-0": "new"})
    with app.app_context():
        restored = (
            db().execute("SELECT * FROM cases WHERE name='Imported legacy'").fetchone()
        )
        assert restored and restored["impact_confirmed"] == 0


def test_complete_installation_backup_contains_impact(tmp_path):
    from test_malware_families import make_backup

    c, cid, uid, post = setup_backup_case()
    with app.app_context():
        run("UPDATE users SET role='Administrator' WHERE id=?", (uid,))
        from malware_families import initialize
        from family_reports import initialize as initialize_reports

        initialize(db())
        initialize_reports(db())
        impact.write(db(), cid, impact.patch({}, VALUE, STAMP))
        db().commit()
    archive = make_backup(c)
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        snapshot = tmp_path / "snapshot.sqlite3"
        snapshot.write_bytes(source.read("data/workflow.sqlite3"))
    from installation_backup import restore_installation

    source_path = tmp_path / "installation.zip"
    source_path.write_bytes(archive)
    restored_path = tmp_path / "restored"
    restore_installation(source_path, restored_path)
    with sqlite3.connect(restored_path / "workflow.sqlite3") as con:
        row = con.execute(
            "SELECT " + ",".join(impact.FIELDS) + " FROM cases WHERE id=?", (cid,)
        ).fetchone()
        assert row == (1, "both", VALUE["impact_summary"].strip(), STAMP)


def test_sdk_case_impact_round_trip():
    import httpx
    from mws_sdk import MWSClient
    from mws_sdk.models import CasesUpdateRequest

    uid, headers = make_user("impact-sdk")
    with MWSClient(
        "http://isolated.test",
        headers["Authorization"][7:],
        transport=httpx.WSGITransport(app=app),
        retries=0,
    ) as sdk:
        cid = sdk.cases.create(data={"name": "SDK impact"}).case.id
        result = sdk.cases.update(cid, data=CasesUpdateRequest(**VALUE)).case
        assert (
            result.impact_confirmed
            and result.impact_type == "both"
            and result.impact_confirmed_at
        )
        assert sdk.cases.get(cid).case.impact_summary == VALUE["impact_summary"].strip()
        sdk.cases.update(cid, data={"description": "Unrelated"})
        assert sdk.cases.get(cid).case.impact_confirmed_at == result.impact_confirmed_at


def test_disabled_owner_does_not_block_impact_only_api_update():
    uid, headers = make_user("impact-inactive-owner")
    with app.app_context():
        owner = run(
            "INSERT INTO users(username,password,role,active,forced) VALUES('disabled','unused','User',0,0)"
        ).lastrowid
        cid = add_case("2024-01-01", stage=3, owner=owner)
    response = app.test_client().patch(
        f"/api/v1/cases/{cid}", headers=headers, json=VALUE
    )
    assert response.status_code == 200, response.data
    assert record(cid)["owner"] == owner and record(cid)["stage"] == 3


def test_missing_imported_confirmation_timestamp_is_not_fabricated_on_edit():
    value = {
        **impact.DEFAULTS,
        "impact_confirmed": 1,
        "impact_type": "detection",
        "impact_summary": "Imported legacy impact",
    }
    updated = impact.patch(value, {"impact_summary": "Edited details"}, STAMP)
    assert updated["impact_confirmed_at"] is None
    assert (
        impact.patch(
            {**value, "impact_confirmed": 0}, {"impact_confirmed": True}, STAMP
        )["impact_confirmed_at"]
        == STAMP
    )


def test_enabled_impact_sync_revision_changes_and_defaults_stay_compatible():
    from test_case_sync import head

    c, cid, uid, post = setup_backup_case()
    post(f"/cases/{cid}/backup")
    before = head(cid)
    post(f"/cases/{cid}/backup")
    assert head(cid) == before
    post(
        f"/cases/{cid}",
        operation="impact",
        impact_confirmed="1",
        impact_type="both",
        impact_summary="Security outcome",
    )
    assert head(cid) != before
    with app.app_context():
        state = app.extensions["case_sync"].snapshot(cid)
        assert state["case"]["impact_confirmed"] == 1


def test_metrics_search_sort_and_safe_plain_text():
    uid, _ = make_user("impact-metrics-ui")
    with app.app_context():
        cid = add_case("2024-01-01", stage=3, owner=uid)
        ensure_package(cid)
        impact.write(
            db(),
            cid,
            impact.patch(
                {},
                {**VALUE, "impact_summary": "<script>bad()</script>\nEnterprise block"},
                STAMP,
            ),
        )
        db().commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="impact")
    response = c.get("/metrics?weeks=all&impact_q=enterprise&impact_sort=number")
    assert response.status_code == 200
    assert 'id="metrics-impactful">1' in response.text
    assert "&lt;script&gt;bad()&lt;/script&gt;" in response.text
    assert "<script>bad()</script>" not in response.text
    empty = c.get("/metrics?impact_q=unmatched-text")
    assert "No impactful cases match" in empty.text
    assert 'id="metrics-impactful">1' in empty.text  # Search filters only the table.
    assert c.get("/metrics?impact_sort=invalid").status_code == 400


def test_api_raw_exports_include_impact_and_standard_structure_is_unchanged():
    c, cid, uid, post = setup_backup_case()
    _, headers = make_user("impact-export-api")
    with app.app_context():
        impact.write(db(), cid, impact.patch({}, VALUE, STAMP))
        db().commit()
    for kind in ("raw", "standard"):
        response = c.post(
            f"/api/v1/cases/{cid}/archive",
            headers=headers,
            json={"archive_type": kind, "acknowledge": True},
        )
        assert response.status_code == 200, response.data
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            paths = [
                path for path in archive.namelist() if path.endswith("/case-data.json")
            ]
            if kind == "raw":
                metadata = json.loads(archive.read(paths[0]))
                assert metadata["case"]["impact_type"] == "both"
                assert metadata["case"]["impact_confirmed_at"] == STAMP
                assert metadata["case"]["created"] == "2026"
            else:
                assert paths == []
                assert not any(
                    "impact" in name.casefold() for name in archive.namelist()
                )
