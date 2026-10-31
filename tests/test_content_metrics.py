from pathlib import Path
from datetime import datetime, timezone
import io, json, uuid
import pytest
from app import app, db, ROOT, ensure_package
from test_tagging import fixture
from content_metrics import (
    collect_case,
    export_events,
    restore_events,
    initialize,
    validate_events,
)
from content_metrics_dashboard import aggregate

NOW = datetime(2026, 10, 30, 18, tzinfo=timezone.utc)


def event(kind, added, scope="case", scope_id="case", live=1):
    eid = uuid.uuid4().hex
    db().execute(
        "INSERT INTO content_events VALUES(?,?,?,?,?,?,?,?)",
        (eid, kind, scope, scope_id, eid, added, NOW.isoformat(), live),
    )
    return eid


def result(**filters):
    return aggregate(db(), lambda p: True, True, filters, "UTC", NOW)


def upload(client, cid, category, name, raw):
    response = client.post(
        f"/cases/{cid}/upload",
        data={
            "csrf": "tag-test",
            "category": category,
            "file": (io.BytesIO(raw), name),
            "ajax": "1",
        },
    )
    assert response.status_code == 200, response.text
    return response.json["path"]


def test_buckets_baseline_partial_coverage_and_timezone():
    with app.app_context():
        db().execute(
            "INSERT INTO content_metrics_state VALUES(1,?,0)",
            ("2026-07-01T00:00:00+00:00",),
        )
        for added in [
            "2026-04-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            "2026-10-29T23:30:00Z",
            None,
        ]:
            event("indicators", added)
        data = result(start="2026-05-01", end="2026-10-30", measure="cumulative")
        series = data["series"]["indicators"]
        assert (
            series["inventory"] == 4
            and series["unknown_dates"] == 1
            and series["total"] == 2
            and series["baseline"] == 1
        )
        assert series["values"] == [2, None, 2, 2, 2, 3]
        assert (
            data["buckets"][-1]["partial"]
            and data["buckets"][-1]["label"] == "2026-10-01"
        )
        monthly = aggregate(
            db(),
            lambda p: True,
            True,
            {"start": "2026-10-01", "end": "2026-10-30"},
            "Pacific/Auckland",
            NOW,
        )
        assert (
            monthly["series"]["indicators"]["total"] == 1
            and monthly["timezone"] == "Pacific/Auckland"
        )
        weekly = aggregate(
            db(),
            lambda p: True,
            True,
            {"start": "2026-10-25", "end": "2026-10-30", "granularity": "weekly"},
            "America/Los_Angeles",
            NOW,
        )
        assert [b["label"] for b in weekly["buckets"]] == ["2026-10-19", "2026-10-26"]
        assert weekly["series"]["indicators"]["total"] == 1
        # DST midnight and year/month boundaries are reporting-zone dates.
        event("samples", "2026-11-01T07:30:00Z")
        event("samples", "2026-11-01T09:30:00Z")
        after = datetime(2027, 1, 5, tzinfo=timezone.utc)
        dst = aggregate(
            db(),
            lambda p: True,
            True,
            {"start": "2026-10-31", "end": "2026-11-02", "granularity": "weekly"},
            "America/Los_Angeles",
            after,
        )
        assert dst["series"]["samples"]["total"] == 2
        year = aggregate(
            db(),
            lambda p: True,
            True,
            {"start": "2026-12-01", "end": "2027-01-05"},
            "UTC",
            after,
        )
        assert [b["label"] for b in year["buckets"]] == ["2026-12-01", "2027-01-01"]
        assert result()["start"] == "2026-05-01"
        for filters in (
            {"start": "nonsense"},
            {"start": "2020-01-01"},
            {"granularity": "daily"},
            {"measure": "inventory"},
            {"end": "2027-01-01"},
        ):
            with pytest.raises(ValueError):
                result(**filters)


def test_permissions_current_inventory_and_deleted_history():
    with app.app_context():
        event("indicators", "2026-10-01T00:00:00Z")
        event("indicators", "2026-10-01T00:00:00Z", live=0)
        event("references", "2026-10-01T00:00:00Z", "profile")
        event("references", "2026-10-01T00:00:00Z")
        event("families", "2026-10-01T00:00:00Z", "profile")
        event("tags", "2026-10-01T00:00:00Z", "global")
        read = {"tags:read", "metrics:read"}
        scoped = aggregate(db(), read.__contains__, False, {}, "UTC", NOW)
        assert (
            scoped["series"]["indicators"]["inventory"] is None
            and scoped["series"]["references"]["total"] == 1
        )
        assert (
            scoped["series"]["families"]["total"] == 1
            and scoped["series"]["tags"]["inventory"] == 1
        )
        basic = aggregate(db(), lambda p: True, False, {}, "UTC", NOW)
        assert (
            basic["series"]["indicators"]["inventory"] == 1
            and basic["series"]["indicators"]["total"] == 1
        )
        assert result()["series"]["indicators"]["total"] == 2
        assert "currently accessible records only" in basic["history_notice"]


def test_actual_asset_and_indicator_workflows_edits_deletes_and_exclusions(tmp_path):
    client, cid, uid = fixture("Administrator")
    first = client.post(
        f"/cases/{cid}/indicators",
        data={
            "csrf": "tag-test",
            "rows": json.dumps(
                [["domain", "repeat.example", "A"], ["domain", "repeat.example", "B"]]
            ),
            "revision": "0",
        },
    )
    assert first.status_code == 200, first.text
    assert (
        client.get("/content-metrics/data").json["series"]["indicators"]["inventory"]
        == 2
    )
    with app.app_context():
        before = (
            db()
            .execute("SELECT count(*) FROM content_events WHERE kind='indicators'")
            .fetchone()[0]
        )
    table = first.json
    table["sections"][0]["rows"][0][2] = "Edited description"
    changed = client.post(
        f"/cases/{cid}/indicators",
        data={
            "csrf": "tag-test",
            "sections": json.dumps(table["sections"]),
            "revision": str(table["revision"]),
        },
    )
    assert changed.status_code == 200
    with app.app_context():
        assert (
            db()
            .execute("SELECT count(*) FROM content_events WHERE kind='indicators'")
            .fetchone()[0]
            == before
        )
    sample = upload(client, cid, "samples", "sample.bin", b"not executable test bytes")
    upload(client, cid, "scripts", "rule.yar", b'print("a script, not a signature")')
    upload(client, cid, "supporting", "looks-like-sample.exe", b"arbitrary evidence")
    upload(client, cid, "supporting", "ambiguous.rules", b"not a signature")
    pdf = upload(client, cid, "reports", "research.pdf", b"%PDF-1.4\n%%EOF\n")
    upload(
        client,
        cid,
        "signatures",
        "x.rules",
        b'alert tcp any any -> any any (msg:"test"; sid:1;)\nalert udp any any -> any any (sid:2;)\n',
    )
    with app.app_context():
        from signature_files import persist

        persist(
            ensure_package(cid),
            "one.yar",
            b"rule First { condition: true }\nrule Second { condition: true }",
            db(),
            cid,
            suffix=".yar",
        )
        collect_case(db(), ROOT, cid)
        db().commit()
    upload(client, cid, "supporting", "attached.pdf", b"%PDF-1.4\n%%EOF\n")
    with app.app_context():
        from reporting import OUTPUT

        root = ensure_package(cid)
        generated = root / str(Path(OUTPUT).with_suffix(".pdf"))
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_bytes(b"%PDF-1.4\n%%EOF\n")
        db().execute(
            "INSERT INTO artifacts VALUES(?,?,?,?)",
            (cid, generated.relative_to(root).as_posix(), "Generated output", ""),
        )
        external = tmp_path / "outside.pdf"
        external.write_bytes(b"%PDF-1.4\n%%EOF\n")
        (root / "supporting/linked.pdf").symlink_to(external)
        db().execute(
            "INSERT INTO artifacts VALUES(?,?,?,?)",
            (cid, "supporting/linked.pdf", "Not an attachment", ""),
        )
        collect_case(db(), ROOT, cid)
        db().commit()
    data = client.get("/content-metrics/data").json["series"]
    assert {
        k: data[k]["inventory"]
        for k in ("samples", "scripts", "pdf", "snort", "yara", "indicators")
    } == {"samples": 1, "scripts": 1, "pdf": 2, "snort": 1, "yara": 1, "indicators": 2}
    assert (
        client.post(
            f"/cases/{cid}/artifact",
            data={"csrf": "tag-test", "path": pdf, "description": "Changed metadata"},
        ).status_code
        == 302
    )
    assert (
        client.post(
            f"/cases/{cid}/assets/delete", data={"csrf": "tag-test", "path": sample}
        ).status_code
        == 200
    )
    deleted = client.get("/content-metrics/data").json["series"]["samples"]
    assert deleted["inventory"] == 0 and deleted["total"] == 1
    upload(client, cid, "samples", "sample.bin", b"new sample record")
    assert client.get("/content-metrics/data").json["series"]["samples"]["total"] == 2


def test_reference_edits_reorder_delete_and_new_additions():
    client, cid, _ = fixture("Administrator")
    rows = [["https://a.example", "A"], ["https://b.example", "B"]]

    def save(rows, revision):
        response = client.post(
            f"/cases/{cid}/references",
            data={
                "csrf": "tag-test",
                "rows": json.dumps(rows),
                "revision": str(revision),
            },
        )
        assert response.status_code == 200, response.text

    save(rows, 0)
    save(rows[::-1], 1)
    rows = [rows[1], ["https://a.example", "Edited"]]
    save(rows, 2)
    assert (
        client.get("/content-metrics/data").json["series"]["references"]["total"] == 2
    )
    save([rows[1]], 3)
    save([rows[1], ["https://c.example", "New"]], 4)
    counts = client.get("/content-metrics/data").json["series"]["references"]
    assert counts["inventory"] == 2 and counts["total"] == 3


def test_profile_records_shared_relationships_original_dates_and_delete():
    client, _, _ = fixture("Administrator")
    assert (
        client.post(
            "/malware-families/new",
            data={"csrf": "tag-test", "name": "Family", "tag": "MAL_METRICS"},
        ).status_code
        == 302
    )
    with app.app_context():
        fid = db().execute("SELECT id FROM malware_families").fetchone()[0]
    assert (
        client.post(
            "/threat-actors/new",
            data={
                "csrf": "tag-test",
                "name": "Actor",
                "tag": "TA_METRICS",
                "known_families": [fid],
            },
        ).status_code
        == 302
    )
    with app.app_context():
        con = db()
        con.execute(
            "INSERT INTO family_osint VALUES(?,?,?,?,0)",
            ("link", fid, "Research", "https://example.org"),
        )
        con.execute("UPDATE family_osint SET title=? WHERE id=?", ("Edited", "link"))
        con.commit()
    before = client.get("/content-metrics/data").json["series"]
    assert (
        before["families"]["inventory"] == 1
        and before["actors"]["inventory"] == 1
        and before["tags"]["inventory"] == 2
        and before["references"]["inventory"] == 1
    )
    with app.app_context():
        db().execute("DELETE FROM family_osint")
        db().commit()
    assert (
        client.get("/content-metrics/data").json["series"]["references"]["total"] == 1
    )


def test_ledger_roundtrip_retries_copies_and_legacy_unknown_dates():
    client, cid, _ = fixture("Administrator")
    upload(client, cid, "scripts", "saved.py", b"print(1)")
    with app.app_context():
        con = db()
        sid = con.execute(
            "SELECT case_uuid FROM sync_cases WHERE case_id=?", (cid,)
        ).fetchone()[0]
        payload = export_events(con, "case", sid)
        before = con.execute("SELECT count(*) FROM content_events").fetchone()[0]
        for _ in range(3):
            restore_events(con, payload, "case", sid)
        collect_case(con, ROOT, cid, legacy=True)
        assert (
            con.execute("SELECT count(*) FROM content_events").fetchone()[0] == before
        )
        con.execute("UPDATE content_events SET live=0 WHERE scope_id=?", (sid,))
        restore_events(con, payload, "case", sid)
        collect_case(con, ROOT, cid, legacy=True)
        assert (
            con.execute("SELECT count(*) FROM content_events").fetchone()[0] == before
        )
        copied = str(uuid.uuid4())
        restore_events(con, payload, "case", copied)
        restore_events(con, payload, "case", copied)
        assert (
            con.execute("SELECT count(*) FROM content_events").fetchone()[0]
            == before + 1
        )
        assert con.execute(
            "SELECT added_at FROM content_events WHERE scope_id=?", (copied,)
        ).fetchone()[0]
        # A legacy attachment has no date: neither mtime nor Case creation is used.
        root = ensure_package(cid)
        (root / "scripts/legacy.py").write_text("old")
        con.execute(
            "INSERT INTO artifacts VALUES(?,?,?,?)", (cid, "scripts/legacy.py", "", "")
        )
        collect_case(con, ROOT, cid, legacy=True)
        assert (
            con.execute(
                "SELECT count(*) FROM content_events WHERE kind='scripts' AND added_at IS NULL"
            ).fetchone()[0]
            == 1
        )
        initialize(con, ROOT)
        initialize(con, ROOT)
        assert (
            con.execute(
                "SELECT count(*) FROM content_events WHERE kind='scripts' AND added_at IS NULL"
            ).fetchone()[0]
            == 1
        )
        invalid = {
            **payload,
            "events": [{**payload["events"][0], "kind": "not-a-type"}],
        }
        with pytest.raises(ValueError):
            validate_events(invalid)


def test_private_routes_directory_rename_and_api_auth():
    anonymous = app.test_client()
    assert anonymous.get("/content-metrics").status_code == 302
    assert anonymous.get("/content-metrics/data").status_code == 302
    assert anonymous.get("/api/v1/content-metrics").status_code == 401
    assert b"Content Metrics" not in anonymous.get("/login").data
    for path in (
        "/dashboards/cases",
        "/dashboards/malware-families",
        "/dashboards/threat-actors",
    ):
        assert b"Content Metrics" not in anonymous.get(path).data
    client, _, _ = fixture("User")
    assert client.get("/content-metrics").status_code == 200
    assert (
        client.get("/content-metrics/data").headers["Cache-Control"]
        == "private, no-store"
    )
    assert client.get("/content-metrics/data?granularity=bad").status_code == 400
    assert "Case Metrics" in client.get("/metrics").text
    directory = client.get("/dashboards").text
    assert directory.index("Open dashboard: Case Metrics") < directory.index(
        "Open dashboard: Content Metrics"
    )
    with app.app_context():
        db().execute(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission='metrics:read'"
        )
        db().commit()
    assert (
        client.get("/content-metrics").status_code == 403
        and client.get("/content-metrics/data").status_code == 403
    )


def test_actual_raw_backup_restores_event_dates_without_replay():
    import zipfile
    from test_case_sync import preview, apply
    from test_backups import setup_backup_case

    client, cid, _, post = setup_backup_case()
    assert (
        post(
            f"/cases/{cid}/upload",
            category="scripts",
            file=(io.BytesIO(b"print(7)"), "known.py"),
            ajax="1",
        ).status_code
        == 200
    )
    response = post(f"/cases/{cid}/archive", archive_type="raw", acknowledge="1")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        meta = json.loads(
            archive.read(
                next(p for p in archive.namelist() if p.endswith("/case-data.json"))
            )
        )
    assert meta["content_metrics"]["events"]
    expected = {e["event_id"]: e["added_at"] for e in meta["content_metrics"]["events"]}
    for _ in range(2):
        operation, plan = preview(client, response.data)
        outcome = apply(client, operation)
        assert outcome[0]["action"] == "Unchanged", outcome
    assert post(f"/cases/{cid}/delete", confirm_number="SOURCE-01").status_code == 302
    operation, plan = preview(client, response.data)
    apply(client, operation)
    with app.app_context():
        actual = {
            r["event_id"]: r["added_at"]
            for r in db().execute(
                "SELECT * FROM content_events WHERE scope_id=?",
                (meta["sync"]["case_uuid"],),
            )
        }
        assert actual == expected


def test_profile_pdf_scope_and_portable_history(tmp_path):
    from test_family_reports import pdf
    from family_portable import export_profiles, restore_profiles

    client, _, _ = fixture("Administrator")
    response = client.post(
        "/malware-families/new",
        data={"csrf": "tag-test", "name": "Attached research", "tag": "MAL_PDF"},
    )
    fid = response.location.split("/")[-1].split("?")[0]
    response = client.post(
        f"/malware-families/{fid}/reports/upload",
        data={
            "csrf": "tag-test",
            "version": "1",
            "reports": (io.BytesIO(pdf()), "research.pdf"),
        },
    )
    assert response.status_code == 302, response.text
    assert (
        client.post(
            "/threat-actors/new",
            data={
                "csrf": "tag-test",
                "name": "Linked one",
                "tag": "TA_ONE",
                "known_families": [fid],
            },
        ).status_code
        == 302
    )
    assert (
        client.post(
            "/threat-actors/new",
            data={
                "csrf": "tag-test",
                "name": "Linked two",
                "tag": "TA_TWO",
                "known_families": [fid],
            },
        ).status_code
        == 302
    )
    counts = client.get("/content-metrics/data").json["series"]["pdf"]
    assert (
        counts["inventory"] == 1 and counts["total"] == 1 and counts["case_total"] == 0
    )
    with app.app_context():
        payload = export_profiles(db(), ROOT)
        expected = {
            e["event_id"]: e["added_at"]
            for e in payload["families"][0]["content_metrics"]["events"]
        }
        for _ in range(2):
            restore_profiles(db(), ROOT, ROOT, payload)
        assert {
            r["event_id"]: r["added_at"]
            for r in db().execute(
                "SELECT * FROM content_events WHERE scope='profile' AND scope_id=?",
                (fid,),
            )
        } == expected
        # Old profile archives remain compatible and do not differ solely by metrics.
        old = json.loads(json.dumps(payload))
        old["families"][0].pop("content_metrics")
        restore_profiles(db(), ROOT, ROOT, old)
        assert (
            db()
            .execute("SELECT count(*) FROM content_events WHERE kind='pdf'")
            .fetchone()[0]
            == 1
        )


def test_bearer_data_scope_and_no_permission_cache():
    import hashlib

    client, _, uid = fixture("User")
    secret = "metrics-token"
    with app.app_context():
        db().execute(
            "INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created) VALUES(?,?,?,?,?)",
            (
                uid,
                "content",
                hashlib.sha256(secret.encode()).hexdigest(),
                "metrics",
                "2026",
            ),
        )
        event("references", NOW.isoformat(), "profile")
        event("references", NOW.isoformat(), "case")
        db().commit()
    headers = {"Authorization": "Bearer " + secret}
    first = client.get("/api/v1/content-metrics", headers=headers)
    assert (
        first.status_code == 200
        and first.json["series"]["references"]["inventory"] == 2
    )
    with app.app_context():
        db().execute(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission='references:read'"
        )
        db().commit()
    second = client.get("/api/v1/content-metrics", headers=headers)
    assert (
        second.status_code == 200
        and second.json["series"]["references"]["inventory"] == 1
    )
    with app.app_context():
        db().execute(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission='metrics:read'"
        )
        db().commit()
    assert client.get("/api/v1/content-metrics", headers=headers).status_code == 403


def test_legacy_indicator_identity_initialization_retains_unknown_dates():
    from indicators import DEFAULT_COLUMNS

    client, cid, _ = fixture("Administrator")
    old = [["domain", "one.example", "one"], ["domain", "two.example", "two"]]
    with app.app_context():
        db().execute(
            "INSERT INTO indicator_tables VALUES(?,?,?,0)",
            (cid, json.dumps(DEFAULT_COLUMNS), json.dumps(old)),
        )
        collect_case(db(), ROOT, cid, legacy=True)
        db().commit()
    # Inserting before existing rows must not date all legacy rows at this save.
    response = client.post(
        f"/cases/{cid}/indicators",
        data={
            "csrf": "tag-test",
            "rows": json.dumps([["domain", "new.example", "new"], *old]),
            "revision": "0",
        },
    )
    assert response.status_code == 200, response.text
    counts = client.get("/content-metrics/data").json["series"]["indicators"]
    assert (
        counts["inventory"] == 3
        and counts["unknown_dates"] == 2
        and counts["total"] == 1
    )
    with app.app_context():
        assert (
            db()
            .execute("SELECT count(*) FROM content_events WHERE kind='indicators'")
            .fetchone()[0]
            == 3
        )
