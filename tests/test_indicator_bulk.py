"""Bulk entry uses the existing preview, append, revisions and permission gates."""

import csv
import io
import json

from app import app, db
from test_indicators import setup


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["type", "value", "description"])
    writer.writerows(rows)
    return stream.getvalue()


def test_preview_reports_batch_duplicates_and_uses_shared_validation():
    client, cid, post = setup()
    base = f"/cases/{cid}/indicators"
    rows = [
        ["SHA-256", "a" * 64, "Shared"],
        ["sha256", "A" * 64, "Shared"],
        ["sha256", "invalid hash", "Shared"],
    ]
    preview = post(
        base + "/import/preview", format="csv", section_id="default", csv=csv_text(rows)
    )
    assert preview.status_code == 200
    items = preview.json["rows"]
    assert not items[0]["reason"] and not items[0]["duplicate_in_import"]
    assert items[1]["duplicate_in_import"] and not items[1]["duplicate"]
    assert items[2]["reason"] and not items[2]["duplicate_in_import"]
    assert client.get(base).json["sections"][0]["rows"] == []
    result = post(
        base + "/import",
        revision=preview.json["revision"],
        section_id="default",
        accepted_rows=json.dumps([item["row"] for item in items[:2]]),
        skip_duplicates="1",
    )
    assert result.status_code == 200
    assert result.json["added"] == 1 and result.json["skipped_duplicates"] == 1
    repeat = post(
        base + "/import/preview",
        format="csv",
        section_id="default",
        csv=csv_text(rows[:1]),
    )
    assert repeat.json["rows"][0]["duplicate"]
    kept = post(
        base + "/import",
        revision=repeat.json["revision"],
        section_id="default",
        accepted_rows=json.dumps(rows[:2]),
        skip_duplicates="0",
    )
    assert kept.status_code == 200 and kept.json["added"] == 2


def test_import_preserves_literal_text_and_existing_invalid_draft_model():
    client, cid, post = setup()
    base = f"/cases/{cid}/indicators"
    rows = [
        ["text", 'hello, "world"  with spaces', ""],
        ["sha256", "invalid", "Needs correction"],
    ]
    preview = post(
        base + "/import/preview", format="csv", section_id="default", csv=csv_text(rows)
    )
    assert preview.status_code == 200 and preview.json["rows"][1]["reason"]
    result = post(
        base + "/import",
        revision=preview.json["revision"],
        section_id="default",
        accepted_rows=json.dumps(rows),
    )
    assert result.status_code == 200 and result.json["added"] == 2
    assert result.json["sections"][0]["rows"] == rows
    assert not result.json["stix"]["available"]
    stale = post(
        base + "/import",
        revision=preview.json["revision"],
        section_id="default",
        accepted_rows=json.dumps([rows[0]]),
    )
    assert stale.status_code == 400
    assert "changed in another session" in stale.json["error"]
    assert len(client.get(base).json["sections"][0]["rows"]) == 2


def test_bulk_persistence_cannot_bypass_closed_case_or_csrf():
    client, cid, post = setup()
    base = f"/cases/{cid}/indicators"
    fields = {
        "section_id": "default",
        "revision": 0,
        "accepted_rows": json.dumps([["domain", "bulk.example", ""]]),
    }
    assert client.post(base + "/import", data=fields).status_code == 403
    with app.app_context():
        db().execute("UPDATE cases SET stage=3 WHERE id=?", (cid,))
        db().commit()
    assert post(base + "/import", **fields).status_code == 409
    assert (
        post(
            base + "/import/preview",
            format="csv",
            section_id="default",
            csv="domain,bulk.example,",
        ).status_code
        == 409
    )
    assert client.get(base).json["sections"][0]["rows"] == []


def test_readonly_role_sees_disabled_controls_and_cannot_import():
    client, cid, post = setup()
    with app.app_context():
        db().execute(
            "INSERT INTO roles(name,description) VALUES('IOC Reader','Read only')"
        )
        db().execute("INSERT INTO role_permissions VALUES('IOC Reader','cases:read')")
        db().execute("UPDATE users SET role='IOC Reader' WHERE username='ioc-user'")
        db().commit()
    page = client.get(f"/cases/{cid}?tab=indicators")
    assert page.status_code == 200
    root = page.text.split('id="indicator-workspace"', 1)[1].split("</section>", 1)[0]
    assert 'data-locked="true"' in root
    assert (
        post(
            f"/cases/{cid}/indicators/import",
            section_id="default",
            revision=0,
            accepted_rows=json.dumps([["text", "value", ""]]),
        ).status_code
        == 403
    )
    assert (
        post(
            f"/cases/{cid}/indicators/import/preview",
            format="csv",
            section_id="default",
            csv="text,value,",
        ).status_code
        == 403
    )
