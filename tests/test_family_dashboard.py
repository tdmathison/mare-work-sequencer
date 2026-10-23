import json
import uuid
from app import app, db
from family_dashboard import snapshot, FIELDS, LIBRARY_SIZE
from tagging import create


def family(
    name="Family", tag="MAL_FAMILY", updated="2026-10-01T12:00:00Z", identity=None
):
    tid = create(db(), tag)[0]
    fid = identity or str(uuid.uuid4())
    db().execute(
        """INSERT INTO malware_families(id,name,tag_id,short_description,long_description,
      attribution_notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
        (
            fid,
            name,
            tid,
            "<img src=x onerror=alert(1)>",
            "PRIVATE LONG",
            "PRIVATE ATTRIBUTION",
            "2026",
            updated,
        ),
    )
    return fid, tid


def case(number, stage, tags):
    cid = (
        db()
        .execute(
            "INSERT INTO cases(number,name,stage,created) VALUES(?,?,?,?)",
            (number, "PRIVATE CASE", stage, "2026"),
        )
        .lastrowid
    )
    for tid in tags:
        db().execute(
            "INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)",
            (cid, tid, "2026"),
        )
    return cid


def test_anonymous_navigation_boundary_and_allowlist():
    c = app.test_client()
    assert c.get("/dashboards/malware-families").status_code == 200
    assert b"Malware families dashboard" in c.get("/login").data
    assert b'href="/dashboards/malware-families"' in c.get("/dashboards/cases").data
    assert (
        b'aria-current="page">Malware families'
        in c.get("/dashboards/malware-families").data
    )
    for route in [
        "/malware-families",
        "/malware-families/private",
        "/malware-families/private/reports/private/download",
        "/cases/1",
    ]:
        assert c.get(route).status_code == 302
    assert c.get("/api/v1/cases").status_code == 401
    assert c.post("/dashboards/malware-families/data").status_code in (403, 405)
    with app.app_context():
        fid, tid = family()
        case("PRIVATE NUMBER", 1, [tid])
        db().commit()
        before = db().total_changes
        data = snapshot(db())
        assert db().total_changes == before
    response = c.get("/dashboards/malware-families/data")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert set(data["featured"]) == set(FIELDS)
    assert all(
        set(row) == set(FIELDS) for row in data["tracked"] + data["investigations"]
    )
    assert data["featured"]["short_description"].startswith("<img")
    assert "PRIVATE" not in response.text and fid not in response.text
    for query in ["page=-1", "page=bad", "library_page=-2", "page=1000001"]:
        assert c.get("/dashboards/malware-families/data?" + query).status_code == 400


def test_distinct_counts_stable_relationships_stages_deletion_and_selection():
    with app.app_context():
        fid, a = family("Alpha", "MAL_ALPHA", "2026-10-02", identity="a")
        other, b = family("Beta", "MAL_BETA", "2026-10-03", identity="b")
        family("Newest idle", "MAL_IDLE", "2026-10-10", identity="c")
        create(db(), "MAL_NO_PROFILE")
        c1 = case("secret1", 1, [a, b])
        case("secret2", 2, [a])
        case("secret3", 0, [b])
        case("secret4", 3, [a])
        case("secret5", 8, [a])
        db().execute(
            "INSERT INTO family_osint VALUES(?,?,?,?,?)",
            ("osint", fid, "PRIVATE ARTICLE", "https://example.com/PRIVATE", 1),
        )
        db().execute(
            """INSERT INTO family_reports(id,family_id,title,original_filename,description,storage_ref,size,file_type,sha256,uploaded_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                "report",
                fid,
                "PRIVATE REPORT",
                "PRIVATE.pdf",
                "PRIVATE report description",
                "PRIVATE/storage",
                12,
                "application/pdf",
                "PRIVATE HASH",
                "2026",
            ),
        )
        data = snapshot(db())
        assert "PRIVATE" not in json.dumps(data)
        assert data["metrics"] == dict(
            tracked_families=3,
            families_in_progress=2,
            unique_linked_cases=4,
            reports_collected=1,
        )
        assert data["featured"]["name"] == "Beta"  # updated date, not active count
        assert [r["name"] for r in data["investigations"]] == ["Alpha", "Beta"]
        alpha = data["investigations"][0]
        assert (alpha["linked_cases"], alpha["in_progress"], alpha["osint_links"]) == (
            3,
            2,
            1,
        )
        db().execute("DELETE FROM cases WHERE id=?", (c1,))
        assert snapshot(db())["metrics"]["unique_linked_cases"] == 3
        db().execute("DELETE FROM malware_families WHERE id=?", (other,))
        assert snapshot(db())["metrics"]["tracked_families"] == 2
        db().execute("UPDATE cases SET stage=3 WHERE stage IN (1,2)")
        assert snapshot(db())["featured"]["name"] == "Newest idle"


def test_empty_single_missing_dates_ties_and_bounded_paging():
    with app.app_context():
        data = snapshot(db())
        assert data["featured"] is None and not data["tracked"]
        _, tid = family(updated="bad", identity="a")
        case("one", 2, [tid])
        assert snapshot(db())["featured"]["updated_at"] is None
        for index in range(1, 60):
            _, tid = family(
                f"Family {index:03}",
                f"MAL_F{index:03}",
                "2026-10-01",
                identity=f"id{index:03}",
            )
            case(str(index), 1, [tid])
        data = snapshot(db(), 999, 999)
        assert len(data["tracked"]) == 60 % LIBRARY_SIZE
        assert data["library_pagination"] == dict(
            page=2, pages=3, page_size=24, total=60
        )
        assert data["pagination"] == dict(page=19, pages=20, page_size=3, total=60)
        assert snapshot(db())["featured"]["name"] == "Family 001"
        names = []
        for page in range(3):
            names.extend(
                r["name"] for r in snapshot(db(), library_page=page)["tracked"]
            )
        assert len(set(names)) == 60
        assert len(json.dumps(data)) < 50000
