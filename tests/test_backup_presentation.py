import json
from collections import Counter
import pytest
from app import app, db
from backup_presentation import record, outcomes, case_action
from test_backup_workspace import setup, post, export, inspect, wait


def test_preview_and_committed_shared_outcomes_across_all_categories():
    client, *_ = setup()
    ids = {}
    for category, path, prefix in (("families", "/malware-families/new", "MAL_"), ("actors", "/threat-actors/new", "TA_")):
        ids[category] = []
        for n in range(2):
            response = post(client, path, name=f"{category} record {n}", tag=prefix+f"PRESENTATION_{n}", aliases_present="1", aliases=[f"Alias {n}"], short_description="Readable research description")
            assert response.status_code == 302, response.text
            ids[category].append(response.location.rsplit("/", 1)[-1].split("?")[0])
    archive, _ = export(client, ["cases", "tags", "actors", "families"], password="")
    with app.app_context():
        for category, table in (("families", "malware_families"), ("actors", "threat_actors")):
            db().execute(f"DELETE FROM {table} WHERE id=?", (ids[category][0],))
        db().commit()
    plan = inspect(client, archive, password="")
    p = plan["preview"]
    assert {r["category"] for r in p["records"]} == {"cases", "tags", "actors", "families"}
    for category, key in (("cases", "cases"), ("tags", "tags"), ("actors", "threat_actors"), ("families", "malware_families")):
        assert sum(r["category"] == category for r in p["records"]) == p["counts"][key]
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    # A second submission cannot duplicate this reviewed operation.
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 409
    completed = wait(client, plan["id"], "completed")
    results = completed["result"]["records"]
    for category in ("families", "actors"):
        assert Counter(r["action"] for r in results if r["category"] == category) == {"added": 1, "unchanged": 1}
    assert all(r["action"] == "unchanged" for r in results if r["category"] in ("tags", "cases"))
    assert completed["result"]["duration"] >= 0
    assert completed["result"]["started_at"] and completed["result"]["completed_at"]
    assert all("predicted_action" not in r for r in results)


@pytest.mark.parametrize("action,expected", [("Imported new", "added"), ("Updated existing", "updated"), ("Replaced by explicit decision", "replaced"), ("Unchanged", "unchanged"), ("Kept local", "skipped"), ("Skipped older", "skipped"), ("Conflict unresolved", "conflict"), ("Failed and rolled back", "error")])
def test_explicit_action_mapping(action, expected):
    assert case_action(action) == expected


def test_unknown_outcomes_are_never_success_and_updated_is_not_added():
    preview = {"records": [record("cases", "CASE-1", "Updated case", index=0), record("tags", "tag-1", "Unknown tag")]}
    records = outcomes(preview, [{"index": 0, "action": "Updated existing", "reason": "Newer revision applied"}], None)
    assert [r["action"] for r in records] == ["updated", "not_processed"]


def test_partial_failure_preserves_successful_shared_outcomes_and_hides_internal_errors(monkeypatch):
    client, *_ = setup()
    archive, _ = export(client, ["cases", "tags"], password="")
    plan = inspect(client, archive, password="")
    importer = app.extensions["case_import_sync"]
    monkeypatch.setattr(importer, "apply_one", lambda *args: dict(index=0, action="Failed and rolled back", reason="/private/secret/database.sqlite3: internal traceback"))
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    completed = wait(client, plan["id"], "failed")
    records = completed["result"]["records"]
    assert any(r["category"] == "tags" and r["action"] == "unchanged" for r in records)
    assert any(r["category"] == "cases" and r["action"] == "error" for r in records)
    assert "/private/secret" not in json.dumps(records)


def test_late_failure_keeps_journaled_successes(monkeypatch):
    client, *_ = setup()
    archive, _ = export(client, ["tags"], password="")
    plan = inspect(client, archive, password="")
    importer = app.extensions["case_import_sync"]
    apply = importer.apply
    def fail_after_commit(operation):
        apply(operation)
        raise ValueError("Completion interrupted after committed records")
    monkeypatch.setattr(importer, "apply", fail_after_commit)
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    completed = wait(client, plan["id"], "failed")
    assert completed["result"]["records"]
    assert all(r["action"] == "unchanged" for r in completed["result"]["records"])


def test_complete_preview_whitelists_display_fields_only():
    client, *_ = setup()
    archive, _ = export(client, complete=True)
    plan = inspect(client, archive)
    records = plan["preview"]["records"]
    assert records and all(r["predicted_action"] == "replaced" for r in records)
    assert not any(key in json.dumps(records).lower() for key in ("password", "session.key", "token_hash"))


def test_empty_selected_category_is_reviewable_without_invented_records():
    client, *_ = setup()
    with app.app_context():
        db().execute("DELETE FROM case_tags")
        db().execute("DELETE FROM tags")
        db().commit()
    archive, _ = export(client, ["tags"], password="")
    plan = inspect(client, archive, password="")
    assert plan["preview"]["areas"] == ["tags"]
    assert plan["preview"]["counts"]["tags"] == 0
    assert plan["preview"]["records"] == []
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    completed = wait(client, plan["id"], "completed")
    assert completed["result"]["records"] == []


def test_explicit_kept_profile_has_a_skipped_outcome():
    client, *_ = setup()
    created = post(client, "/malware-families/new", name="Keep local family", tag="MAL_KEEP_LOCAL")
    fid = created.location.rsplit("/", 1)[-1].split("?")[0]
    archive, _ = export(client, ["families"], password="")
    with app.app_context():
        db().execute("UPDATE malware_families SET short_description='Destination research changed',version=version+1 WHERE id=?", (fid,))
        db().commit()
    plan = inspect(client, archive, password="")
    assert any(c["key"] == "family:" + fid for c in plan["preview"]["conflicts"])
    response = post(client, "/backup-restore/jobs/"+plan["id"]+"/preview", choices=json.dumps({"family:"+fid:"keep"}))
    assert response.status_code == 202
    plan = wait(client, plan["id"], "preview")
    assert any(r["category"] == "families" and r["predicted_action"] == "skipped" for r in plan["preview"]["records"])
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    completed = wait(client, plan["id"], "completed")
    assert any(r["category"] == "families" and r["action"] == "skipped" for r in completed["result"]["records"])


def test_legacy_tag_catalog_has_confirmed_record_outcomes():
    import io
    import zipfile
    client, *_ = setup()
    raw = post(client, "/import-export/export")
    with zipfile.ZipFile(io.BytesIO(raw.data)) as source:
        index = json.loads(source.read("backup.json"))
    # A legacy tag-only archive predates shared library/identity sections.
    for key in ("family_library", "tag_registry", "included_areas", "case_numbers", "task_collections"):
        index.pop(key, None)
    index["cases"] = []
    index["schema"] = "mare-case-backup/2"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("backup.json", json.dumps(index))
    plan = inspect(client, stream.getvalue(), password="")
    choices = {item["key"]: "reuse" for item in plan["preview"]["conflicts"]}
    if choices:
        assert post(client, "/backup-restore/jobs/"+plan["id"]+"/preview", choices=json.dumps(choices)).status_code == 202
        plan = wait(client, plan["id"], "preview")
    assert post(client, "/backup-restore/jobs/"+plan["id"]+"/apply").status_code == 202
    completed = wait(client, plan["id"], "completed")
    assert completed["result"]["records"]
    assert all(r["category"] == "tags" and r["action"] == "unchanged" for r in completed["result"]["records"])
