"""Automatic content disposition, applicability, register and existing storage."""

import io
import json
import pytest
from app import app, db, package, ROOT, readiness
from test_api import make_user, new_case, start_case


@pytest.fixture
def context():
    uid, headers = make_user("register-admin", role="Administrator")
    client = app.test_client()
    cid = new_case(client, headers)
    start_case(client, headers, cid, uid)
    with client.session_transaction() as s:
        s.update(uid=uid, version=1, csrf="register")
    return client, headers, cid, uid


def post(c, url, **values):
    return c.post(url, data={"csrf": "register", **values})


def state(c, cid, section):
    return next(
        r
        for r in c.get(f"/cases/{cid}/package-register").json["sections"]
        if r["category"] == section
    )


def applicable(c, cid, section, status="Not applicable"):
    return post(c, f"/cases/{cid}/readiness", category=section, status=status, ajax="1")


def test_presence_transitions_failure_and_single_activity(context):
    c, h, cid, _ = context
    assert all(
        r["status"] == "Empty"
        for r in c.get(f"/cases/{cid}/package-register").json["sections"]
    )
    assert applicable(c, cid, "scripts").status_code == 200
    assert state(c, cid, "scripts")["status"] == "Not applicable"
    assert (
        post(
            c,
            f"/cases/{cid}/upload",
            category="scripts",
            file=(io.BytesIO(b""), "empty.py"),
            ajax="1",
        ).status_code
        == 200
    )
    assert state(c, cid, "scripts")["status"] == "Not applicable"
    assert (
        post(
            c,
            f"/cases/{cid}/upload",
            category="scripts",
            file=(io.BytesIO(b"print(42)"), "work.py"),
            ajax="1",
        ).status_code
        == 200
    )
    assert state(c, cid, "scripts")["status"] == "Populated"
    assert applicable(c, cid, "scripts").status_code == 409
    conflict = post(
        c,
        f"/cases/{cid}/upload",
        category="scripts",
        file=(io.BytesIO(b"replace"), "work.py"),
        ajax="1",
    )
    assert conflict.status_code == 409
    assert (
        post(c, f"/cases/{cid}/assets/delete", path="scripts/work.py").status_code
        == 200
    )
    assert state(c, cid, "scripts")["status"] == "Empty"
    with app.app_context():
        assert (
            not db()
            .execute(
                "SELECT 1 FROM readiness WHERE case_id=? AND status!='Not applicable'",
                (cid,),
            )
            .fetchone()
        )
        assert (
            db()
            .execute(
                "SELECT count(*) FROM notes WHERE case_id=? AND event_type='package.applicability.cleared'",
                (cid,),
            )
            .fetchone()[0]
            == 1
        )
    for obsolete in ("Pending", "Populated"):
        response = c.put(
            f"/api/v1/cases/{cid}/readiness",
            headers=h,
            json={"category": "scripts", "status": obsolete},
        )
        assert response.status_code == 400 and "automatic" in response.json["error"]


def test_structured_generated_counts_ignore_stale_files_and_drafts(context):
    c, h, cid, uid = context
    with app.app_context():
        root = package(cid)
        (root / "iocs/indicators.stix.json").write_text('{"stale":true}')
        (root / "supporting/references.csv").write_text(
            "Link,Description\nhttps://stale.invalid,stale"
        )
        (root / "mappings/mitre-attack.md").write_text(
            "# MITRE ATT&CK\n\n| Technique ID | Technique | Evidence |\n|---|---|---|\n"
        )
    assert state(c, cid, "iocs")["status"] == "Empty"
    assert state(c, cid, "supporting")["status"] == "Empty"
    assert state(c, cid, "mappings")["status"] == "Empty"
    assert applicable(c, cid, "iocs").status_code == 200
    revision = c.get(f"/api/v1/cases/{cid}/indicators", headers=h).json["revision"]
    saved = c.put(
        f"/api/v1/cases/{cid}/indicators",
        headers=h,
        json={"revision": revision, "rows": [["domain", "example.com", "Observed"]]},
    )
    assert saved.status_code == 200, saved.text
    assert state(c, cid, "iocs")["status"] == "Populated"
    register = c.get(f"/cases/{cid}/package-register?section=iocs").json
    assert (
        register["rows"][0]["owner"] == "indicators"
        and not register["rows"][0]["editable"]
    )
    assert (
        c.delete(
            f"/api/v1/cases/{cid}/assets",
            headers=h,
            json={"path": "iocs/indicators.csv"},
        ).status_code
        == 409
    )
    assert c.get(
        f"/cases/{cid}/file?ajax=1&path=reports/sections/key_findings.md"
    ).status_code in (403, 404)


def test_idempotent_upgrade_preserves_content_and_empty_na(context):
    c, h, cid, _ = context
    with app.app_context():
        root = package(cid)
        (root / "scripts/legacy.py").write_text("saved analyst content")
        db().execute(
            "INSERT OR REPLACE INTO readiness VALUES(?, 'scripts','Not applicable','old contradiction')",
            (cid,),
        )
        db().execute(
            "INSERT OR REPLACE INTO readiness VALUES(?, 'signatures','Populated','old manual flag')",
            (cid,),
        )
        db().execute(
            "INSERT OR REPLACE INTO readiness VALUES(?, 'supporting','Not applicable','No evidence expected')",
            (cid,),
        )
        db().execute(
            "DELETE FROM schema_migrations WHERE name='automatic-package-status-v1'"
        )
        db().commit()
        from package_status import initialize

        initialize(db(), ROOT)
        initialize(db(), ROOT)
        assert (root / "scripts/legacy.py").read_text() == "saved analyst content"
        assert (
            db()
            .execute("SELECT count(*) FROM readiness WHERE case_id=?", (cid,))
            .fetchone()[0]
            == 1
        )
    assert state(c, cid, "scripts")["status"] == "Populated"
    assert state(c, cid, "signatures")["status"] == "Empty"
    assert state(c, cid, "supporting")["status"] == "Not applicable"


def test_optimistic_edits_bulk_download_and_closed_case(context):
    c, h, cid, _ = context
    assert (
        post(
            c,
            f"/cases/{cid}/upload",
            category="scripts",
            file=(io.BytesIO(b"print(1)"), "work.py"),
            ajax="1",
        ).status_code
        == 200
    )
    value = c.get(f"/cases/{cid}/file?ajax=1&path=scripts/work.py").json
    changed = post(
        c,
        f"/cases/{cid}/file",
        path="scripts/work.py",
        content="print(2)",
        revision=value["revision"],
        ajax="1",
    )
    assert changed.status_code == 200
    assert (
        post(
            c,
            f"/cases/{cid}/file",
            path="scripts/work.py",
            content="lost update",
            revision=value["revision"],
            ajax="1",
        ).status_code
        == 409
    )
    with app.app_context():
        db().execute("UPDATE cases SET stage=3 WHERE id=?", (cid,))
        db().commit()
    assert c.get(f"/cases/{cid}/package-register").json["locked"]
    assert (
        post(
            c,
            f"/cases/{cid}/file",
            path="scripts/work.py",
            content="blocked",
            revision=changed.json["revision"],
            ajax="1",
        ).status_code
        == 409
    )
    assert applicable(c, cid, "supporting").status_code == 409
    assert (
        post(c, f"/cases/{cid}/assets/delete", path="scripts/work.py").status_code
        == 409
    )
    download = post(
        c,
        f"/cases/{cid}/package-register/download",
        paths=json.dumps(["scripts/work.py"]),
    )
    assert download.status_code == 200, download.text
    assert state(c, cid, "scripts")["status"] == "Populated"
    assert not c.get(f"/cases/{cid}/package-register").json["rows"][0]["remove"]


def test_permissions_and_pagination(context):
    c, h, cid, uid = context
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('register-reader')")
        db().execute(
            "INSERT INTO role_permissions VALUES('register-reader','cases:read')"
        )
        db().execute("UPDATE users SET role='register-reader' WHERE id=?", (uid,))
        db().commit()
    assert not c.get(f"/cases/{cid}/package-register").json["can_upload"]
    assert applicable(c, cid, "supporting").status_code == 403
    assert (
        post(
            c,
            f"/cases/{cid}/upload",
            category="scripts",
            file=(io.BytesIO(b"x"), "blocked.py"),
            ajax="1",
        ).status_code
        == 403
    )


def test_concurrent_applicability_and_saved_content_are_serialized(context):
    from concurrent.futures import ThreadPoolExecutor

    c, h, cid, _ = context

    def choose():
        client = app.test_client()
        return client.put(
            f"/api/v1/cases/{cid}/readiness",
            headers=h,
            json={"category": "scripts", "status": "Not applicable"},
        ).status_code

    def upload():
        client = app.test_client()
        return client.post(
            f"/api/v1/cases/{cid}/assets",
            headers=h,
            data={"category": "scripts", "file": (io.BytesIO(b"print(42)"), "race.py")},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(choose)
        b = pool.submit(upload)
        assert a.result() in (200, 409)
        assert b.result() == 201
    assert state(c, cid, "scripts")["status"] == "Populated"
    with app.app_context():
        assert (
            not db()
            .execute(
                "SELECT 1 FROM readiness WHERE case_id=? AND category=?",
                (cid, "scripts"),
            )
            .fetchone()
        )


def test_raw_roundtrip_preserves_applicability_content_and_metadata():
    from test_backups import setup_backup_case
    from sync_helpers import other_destination

    c, cid, uid, submit = setup_backup_case()
    assert (
        submit(
            f"/cases/{cid}/readiness", category="signatures", status="Not applicable"
        ).status_code
        == 302
    )
    raw = submit(f"/cases/{cid}/backup")
    assert raw.status_code == 200
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(raw.data))
    metadata = json.loads(
        archive.read(
            next(n for n in archive.namelist() if n.endswith("/case-data.json"))
        )
    )
    assert any(
        r["category"] == "signatures" and r["status"] == "Not applicable"
        for r in metadata["records"]["readiness"]
    )
    assert any(
        n.get("event_type") == "package.applicability"
        for n in metadata["records"]["notes"]
    )
    other_destination()
    result = submit(
        "/import-export/import-raw", backup=(io.BytesIO(raw.data), "package.zip")
    )
    assert result.status_code == 302, result.text
    with app.app_context():
        imported = (
            db()
            .execute(
                "SELECT id FROM cases WHERE id!=? AND name=? ORDER BY id DESC",
                (cid, "Case one"),
            )
            .fetchone()[0]
        )
        assert (package(imported) / "scripts/decode.py").read_text() == "print(42)"
    assert state(c, imported, "signatures")["status"] == "Not applicable"
    assert state(c, imported, "scripts")["status"] == "Populated"


def test_empty_word_and_json_templates_do_not_populate(context):
    from docx import Document

    c, h, cid, _ = context
    with app.app_context():
        root = package(cid)
        Document().save(root / "reports/blank-template.docx")
        (root / "scripts/empty.json").write_text("{}")
    assert state(c, cid, "reports")["status"] == "Empty"
    assert state(c, cid, "scripts")["status"] == "Empty"
    entries = c.get(f"/cases/{cid}/package-register").json["rows"]
    assert any(r["name"] == "blank-template.docx" and r["count"] == 0 for r in entries)


def test_derived_downloads_and_standard_export_use_current_records():
    from test_backups import setup_backup_case

    c, cid, uid, submit = setup_backup_case()
    assert (
        submit(
            f"/cases/{cid}/indicators",
            rows=json.dumps([["domain", "current.example", "saved"]]),
            revision="0",
        ).status_code
        == 200
    )
    with app.app_context():
        (package(cid) / "iocs/indicators.csv").write_text(
            "Type,Value,Description\ndomain,stale.example,old\n"
        )
    direct = c.get(f"/cases/{cid}/file?download=1&path=iocs/indicators.csv")
    assert (
        direct.status_code == 200
        and b"current[.]example" in direct.data
        and b"stale.example" not in direct.data
    )
    register = c.get(f"/cases/{cid}/package-register?section=iocs").json
    assert register["rows"][0]["download"] and not register["rows"][0]["remove"]
    archive = submit(f"/cases/{cid}/archive", acknowledge="1")
    assert archive.status_code == 200
    import zipfile

    with zipfile.ZipFile(io.BytesIO(archive.data)) as z:
        content = z.read(
            next(n for n in z.namelist() if n.endswith("/iocs/indicators.csv"))
        )
        assert b"current[.]example" in content and b"stale.example" not in content
