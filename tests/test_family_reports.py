import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import os
import uuid
import zipfile
from html.parser import HTMLParser
import pytest
from docx import Document
from app import app, db, ROOT
from family_reports import storage_path, reference, recover_storage, MAX_FILE
from installation_backup import restore_installation
from test_malware_families import fixture, create, post, profile, make_backup


def pdf():
    from pypdf import PdfWriter

    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(out)
    return out.getvalue()


def docx():
    out = io.BytesIO()
    document = Document()
    document.add_paragraph("Research report")
    document.save(out)
    return out.getvalue()


def doc():
    # A bounded CFB v3 Word container with directory/FAT and a WordDocument stream.
    header = bytearray(512)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into(
        "<IIIIIIIII", header, 40, 0, 1, 0, 0, 4096, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0
    )
    struct.pack_into("<109I", header, 76, 9, *([0xFFFFFFFF] * 108))
    directory = bytearray(512)

    def entry(offset, name, kind, start, size):
        encoded = (name + "\0").encode("utf-16-le")
        directory[offset : offset + len(encoded)] = encoded
        struct.pack_into("<H", directory, offset + 64, len(encoded))
        directory[offset + 66] = kind
        struct.pack_into("<I", directory, offset + 116, start)
        struct.pack_into("<Q", directory, offset + 120, size)

    entry(0, "Root Entry", 5, 0xFFFFFFFE, 0)
    entry(128, "WordDocument", 2, 1, 4096)
    fat = (
        [0xFFFFFFFE] + list(range(2, 9)) + [0xFFFFFFFE, 0xFFFFFFFD] + [0xFFFFFFFF] * 118
    )
    content = bytearray(4096)
    struct.pack_into("<H", content, 0, 0xA5EC)
    return bytes(header + directory + content + struct.pack("<128I", *fat))


def upload(client, fid, files):
    return client.post(
        f"/malware-families/{fid}/reports/upload",
        data={
            "csrf": "family-csrf",
            "version": profile(fid)["version"],
            "reports": [(io.BytesIO(content), name) for name, content in files],
        },
        content_type="multipart/form-data",
    )


def reports(fid):
    with app.app_context():
        return [
            dict(row)
            for row in db().execute(
                "SELECT * FROM family_reports WHERE family_id=? ORDER BY uploaded_at,id",
                (fid,),
            )
        ]


class Fields(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.values = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "input" and data.get("name", "").startswith("source_tag_"):
            self.values[data["name"]] = data.get("value", "")


def selected(client, tid):
    response = client.get(f"/malware-families/new?tag_id={tid}")
    assert response.status_code == 200, response.text
    return Fields(response.text).values


def test_multiple_document_types_duplicate_names_and_metadata():
    client, uid, _, _ = fixture()
    fid = create(client)
    assert (
        upload(
            client,
            fid,
            [
                ("../../research.pdf", pdf()),
                ("research.pdf", pdf()),
                ("word.doc", doc()),
                ("word.docx", docx()),
            ],
        ).status_code
        == 302
    )
    rows = reports(fid)
    assert len(rows) == 4 and len({r["storage_ref"] for r in rows}) == 4
    assert sorted(r["original_filename"] for r in rows) == [
        "research.pdf",
        "research.pdf",
        "word.doc",
        "word.docx",
    ]
    for row in rows:
        path = storage_path(ROOT, row["id"])
        assert path.is_file()
        response = client.get(f'/malware-families/{fid}/reports/{row["id"]}/download')
        assert response.status_code == 200
        assert response.headers["Content-Disposition"].startswith("attachment;")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert hashlib.sha256(response.data).hexdigest() == row["sha256"]
        assert row["uploaded_by"] == uid and row["size"] == len(response.data)
    row = rows[0]
    response = post(
        client,
        f'/malware-families/{fid}/reports/{row["id"]}/edit',
        version=profile(fid)["version"],
        title="<script>Title</script>",
        description="<img src=x>\nNotes",
    )
    assert response.status_code == 302
    page = client.get(f"/malware-families/{fid}?tab=osint").text
    assert (
        "OSINT &amp; Reports" in page
        and "4 reports" in page
        and "&lt;script&gt;Title" in page
        and "<img src=x>" not in page
    )


def test_failed_upload_is_atomic_and_limits_keep_existing(tmp_path, monkeypatch):
    client, *_ = fixture()
    fid = create(client)
    upload(client, fid, [("existing.pdf", pdf())])
    original = reports(fid)[0]
    original_bytes = storage_path(ROOT, original["id"]).read_bytes()
    for files in [
        [("good.pdf", pdf()), ("bad.docx", b"not a document")],
        [("bad.pdf", b"fake")],
        [("bad.exe", b"MZ")],
        [("empty.pdf", b"")],
        [("a.pdf", pdf())] * 11,
    ]:
        upload(client, fid, files)
        assert len(reports(fid)) == 1
        assert len(list((ROOT / "family-reports").iterdir())) == 1
        assert not list((ROOT / "family-report-staging").iterdir())
    monkeypatch.setattr("family_reports.MAX_FILE", 1)
    upload(client, fid, [("oversized.pdf", pdf())])
    assert len(reports(fid)) == 1
    monkeypatch.setattr("family_reports.MAX_FILE", MAX_FILE)
    monkeypatch.setattr("family_reports.MAX_REPORTS", 1)
    upload(client, fid, [("too-many.pdf", pdf())])
    assert len(reports(fid)) == 1
    assert storage_path(ROOT, original["id"]).read_bytes() == original_bytes


def test_insert_failure_and_storage_crash_recovery_preserve_records():
    client, *_ = fixture()
    fid = create(client)
    with app.app_context():
        db().execute(
            "CREATE TRIGGER report_injected_failure BEFORE INSERT ON family_reports BEGIN SELECT RAISE(ABORT,'injected upload failure'); END"
        )
        db().commit()
    try:
        upload(client, fid, [("research.pdf", pdf())])
        assert reports(fid) == []
        assert not list((ROOT / "family-reports").iterdir())
    finally:
        with app.app_context():
            db().execute("DROP TRIGGER report_injected_failure")
            db().commit()
    upload(client, fid, [("research.pdf", pdf())])
    row = reports(fid)[0]
    folder = ROOT / "family-report-staging" / str(uuid.uuid4())
    folder.mkdir()
    storage_path(ROOT, row["id"]).rename(folder / (row["id"] + ".bin"))
    (folder / "plan.json").write_text(
        json.dumps([{"id": row["id"], "action": "remove"}])
    )
    orphan = str(uuid.uuid4())
    storage_path(ROOT, orphan).write_bytes(b"orphan")
    other = ROOT / "family-report-staging" / str(uuid.uuid4())
    other.mkdir()
    (other / "plan.json").write_text(json.dumps([{"id": orphan, "action": "upload"}]))
    with app.app_context():
        recover_storage(db(), ROOT)
    assert (
        storage_path(ROOT, row["id"]).exists()
        and not storage_path(ROOT, orphan).exists()
    )
    assert not list((ROOT / "family-report-staging").iterdir())


def test_permissions_csrf_metadata_removal_and_profile_cleanup():
    client, uid, cid, tid = fixture()
    fid = create(client)
    upload(client, fid, [("research.pdf", pdf())])
    row = reports(fid)[0]
    download = f'/malware-families/{fid}/reports/{row["id"]}/download'
    assert app.test_client().get(download).status_code == 302
    assert client.post(f"/malware-families/{fid}/reports/upload").status_code == 403
    other = create(client, name="Other family", tag="MAL_OTHER")
    assert (
        client.get(
            f'/malware-families/{other}/reports/{row["id"]}/download'
        ).status_code
        == 404
    )
    with app.app_context():
        db().execute("UPDATE users SET role='User' WHERE id=?", (uid,))
        db().commit()
    assert client.get(download).status_code == 200
    assert (
        client.get(f'/malware-families/{fid}/reports/{row["id"]}/edit').status_code
        == 403
    )
    assert upload(client, fid, [("x.pdf", pdf())]).status_code == 403
    with app.app_context():
        db().execute("INSERT INTO roles VALUES('NoFamily','',0)")
        db().execute("UPDATE users SET role='NoFamily' WHERE id=?", (uid,))
        db().commit()
    assert client.get(download).status_code == 403
    with app.app_context():
        db().execute("UPDATE users SET role='Administrator' WHERE id=?", (uid,))
        db().commit()
    remove = f'/malware-families/{fid}/reports/{row["id"]}/delete'
    post(client, remove, version=profile(fid)["version"])
    assert len(reports(fid)) == 1
    post(client, remove, confirm="1", version=profile(fid)["version"])
    assert reports(fid) == []
    assert not storage_path(ROOT, row["id"]).exists()
    upload(client, fid, [("word.docx", docx())])
    path = storage_path(ROOT, reports(fid)[0]["id"])
    post(
        client,
        f"/malware-families/{fid}/delete",
        confirm_name="Existing family",
        version=profile(fid)["version"],
    )
    assert not path.exists()
    with app.app_context():
        assert (
            db()
            .execute("SELECT tag_id FROM case_tags WHERE case_id=?", (cid,))
            .fetchone()[0]
            == tid
        )
        actions = " ".join(r[0] for r in db().execute("SELECT action FROM audit"))
        assert "report uploaded" in actions and "report removed" in actions


def test_tags_prefill_no_get_mutations_and_live_navigation():
    client, _, _, tid = fixture()
    with app.app_context():
        from tagging import create as tag_create

        nonmal = tag_create(db(), "OTHER_TAG")[0]
        db().commit()
    page = client.get("/tags").text
    assert f"tag_id={tid}" in page and f"tag_id={nonmal}" not in page
    values = selected(client, tid)
    assert values["source_tag_name"] == "MAL_EXISTING"
    page = client.get(f"/malware-families/new?tag_id={tid}").text
    assert (
        "will be reused" in page
        and 'name="name" required maxlength="200" value=""' in page
    )
    with app.app_context():
        assert db().execute("SELECT count(*) FROM malware_families").fetchone()[0] == 0
    error = post(client, "/malware-families/new", name="", tag="MAL_EXISTING", **values)
    assert error.status_code == 400 and "MAL_EXISTING" in error.text
    response = post(
        client, "/malware-families/new", name="From tag", tag="MAL_EXISTING", **values
    )
    assert response.status_code == 302
    fid = response.location.split("/")[-1].split("?")[0]
    assert (
        profile(fid)["tag_id"] == tid
        and "MARE-FAMILY-1" in client.get(f"/malware-families/{fid}?tab=history").text
    )
    page = client.get("/tags").text
    assert (
        f"/malware-families/{fid}?tab=overview" in page
        and "View malware family" in page
    )
    assert client.get(f"/malware-families/new?tag_id={tid}").location.endswith(
        f"{fid}?tab=overview"
    )
    post(
        client,
        f"/malware-families/{fid}/delete",
        confirm_name="From tag",
        version=profile(fid)["version"],
    )
    assert f"tag_id={tid}" in client.get("/tags").text


def test_stale_tag_identity_rename_deleted_invalid_and_concurrent_creation():
    client, *_, tid = fixture()
    values = selected(client, tid)
    for parameter in ("bad", "-1", "99999999999999999999999", "999999"):
        assert client.get("/malware-families/new?tag_id=" + parameter).status_code in (
            400,
            409,
        )
    post(client, f"/tags/{tid}/rename", name="OUTSIDE")
    assert (
        post(
            client,
            "/malware-families/new",
            name="Preserved content",
            tag="MAL_EXISTING",
            **values,
        ).status_code
        == 409
    )
    assert client.get(f"/malware-families/new?tag_id={tid}").status_code == 409
    post(client, f"/tags/{tid}/rename", name="MAL_EXISTING")
    values = selected(client, tid)
    post(client, f"/tags/{tid}/delete", confirm="1")
    # Deliberate ID reuse plus identical canonical name still has a different nonce.
    with app.app_context():
        db().execute(
            "INSERT INTO tags(id,name,normalized_name,created_at) VALUES(?,?,?,?)",
            (tid, "MAL_EXISTING", "MAL_EXISTING", "2026"),
        )
        db().commit()
    response = post(
        client,
        "/malware-families/new",
        name="Keep my research",
        tag="MAL_EXISTING",
        **values,
    )
    assert response.status_code == 409 and "Keep my research" in response.text
    values = selected(client, tid)
    fid = create(client)
    conflict = post(
        client,
        "/malware-families/new",
        name="Concurrent content",
        tag="MAL_EXISTING",
        **values,
    )
    assert (
        conflict.status_code == 409
        and "Concurrent content" in conflict.text
        and "Open existing profile" in conflict.text
    )
    assert fid in conflict.text


def test_report_bytes_recovery_real_clean_instance_and_tags(tmp_path):
    client, uid, _, tid = fixture()
    values = selected(client, tid)
    created = post(
        client,
        "/malware-families/new",
        name="Recovered family",
        tag="MAL_EXISTING",
        **values,
    )
    fid = created.location.split("/")[-1].split("?")[0]
    sources = [
        ("research.pdf", pdf()),
        ("research.docx", docx()),
        ("research.doc", doc()),
    ]
    upload(client, fid, sources)
    orphan = create(client, name="No linked cases", tag="MAL_REPORT_ONLY")
    upload(client, orphan, [sources[0]])
    rows = reports(fid)
    original = {row["id"]: storage_path(ROOT, row["id"]).read_bytes() for row in rows}
    archive = tmp_path / "full.zip"
    archive.write_bytes(make_backup(client))
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("installation.json"))
        assert manifest["schema"] == "mare-installation-backup/3"
        assert manifest["counts"]["family_reports"] == 4
        for row in rows:
            assert z.read("data/" + row["storage_ref"]) == original[row["id"]]
    dest = tmp_path / "different-storage-root"
    restore_installation(archive, dest)
    # A separate app boots against only recovered data; fetch authenticated links
    # and every restored report through real Flask download endpoints.
    code = """
import hashlib,json
from app import app,db
with app.app_context():
    u=db().execute('SELECT * FROM users').fetchone()
    c=app.test_client()
    with c.session_transaction() as session:session.update(uid=u['id'],version=u['version'])
    assert b'View malware family' in c.get('/tags').data
    assert b'MARE-FAMILY-1' in c.get('/malware-families/FAMILY_TOKEN?tab=history').data
    for row in db().execute('SELECT * FROM family_reports'):
        r=c.get('/malware-families/'+row['family_id']+'/reports/'+row['id']+'/download')
        assert r.status_code==200 and hashlib.sha256(r.data).hexdigest()==row['sha256']
    print('Restored downloads, Tags navigation, profile IDs, uploader IDs and case History verified')
""".replace(
        "FAMILY_TOKEN", fid
    )
    check = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "MARE_DATA_DIR": str(dest)},
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr
    for row in rows:
        assert storage_path(dest, row["id"]).read_bytes() == original[row["id"]]
    # A missing file cannot pass backup or restore, even with forged manifest hashes.
    broken = tmp_path / "missing.zip"
    missing = "data/" + rows[0]["storage_ref"]
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(broken, "w") as out:
        for info in src.infolist():
            if info.filename == missing:
                continue
            data = src.read(info)
            if info.filename == "installation.json":
                m = json.loads(data)
                del m["files"][missing]
                data = json.dumps(m).encode()
            out.writestr(info, data)
    with pytest.raises(ValueError, match="missing"):
        restore_installation(broken, tmp_path / "bad-target")
    assert not (tmp_path / "bad-target").exists()
    storage_path(ROOT, rows[0]["id"]).write_bytes(b"corrupt")
    assert (
        client.get(
            f'/malware-families/{fid}/reports/{rows[0]["id"]}/download'
        ).status_code
        == 409
    )
    assert post(client, "/account/database-backup").status_code == 302


def test_export_all_import_all_maps_different_ids_and_is_idempotent(tmp_path):
    client, *_, tid = fixture()
    values = selected(client, tid)
    response = post(
        client,
        "/malware-families/new",
        name="Portable research",
        tag="MAL_EXISTING",
        **values,
    )
    fid = response.location.split("/")[-1].split("?")[0]
    upload(client, fid, [("portable.pdf", pdf()), ("portable.docx", docx())])
    orphan = create(client, name="Research without cases", tag="MAL_ORPHAN_REPORT")
    upload(client, orphan, [("orphan.pdf", pdf())])
    exported = post(client, "/import-export/export")
    assert exported.status_code == 200
    archive = tmp_path / "all.zip"
    archive.write_bytes(exported.data)
    with zipfile.ZipFile(archive) as z:
        index = json.loads(z.read("backup.json"))
        assert index["schema"] == "mare-case-backup/3"
        assert len(index["family_library"]["families"]) == 2
        assert sum(len(f["reports"]) for f in index["family_library"]["families"]) == 3
    destination = tmp_path / "clean-other-instance"
    code = """
import hashlib,io,sys
sys.path.insert(0,'tests')
from app import app,db,now
from tagging import create
from sync_helpers import apply_preview
with app.app_context():
    db().execute("INSERT INTO users(id,username,password,role,forced) VALUES(1,'unrelated-user','unused','User',0)")
    uid=db().execute("INSERT INTO users(username,password,role,forced) VALUES('families-test','unused','Administrator',0)").lastrowid
    unrelated=create(db(),'UNRELATED')[0]
    db().execute("INSERT INTO cases(number,name,stage,created) VALUES('DEST-ONLY','Unrelated destination',0,?)",(now(),));db().commit()
    c=app.test_client()
    with c.session_transaction() as session:session.update(uid=uid,version=1,csrf='portable-test')
    for _ in range(2):
        data=open('ARCHIVE','rb').read()
        preview=c.post('/import-export/import',data={'csrf':'portable-test','backup':(io.BytesIO(data),'all.zip')},content_type='multipart/form-data')
        assert '/review/' in preview.location,preview.location
        outcome=apply_preview(c,preview,csrf='portable-test');assert outcome.status_code==302
        assert db().execute('SELECT count(*) FROM malware_families').fetchone()[0]==2
        assert db().execute('SELECT count(*) FROM family_reports').fetchone()[0]==3
    assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2
    assert db().execute('SELECT name FROM tags WHERE id=?',(unrelated,)).fetchone()[0]=='UNRELATED'
    f=db().execute("SELECT * FROM malware_families WHERE id='PROFILE'").fetchone()
    assert f['created_by']==uid and uid!=1 and f['tag_id']!=unrelated
    assert b'View malware family' in c.get('/tags').data
    page=c.get('/malware-families/PROFILE?tab=history').data
    assert b'Existing case' in page and b'Unrelated destination' not in page
    for r in db().execute('SELECT * FROM family_reports'):
        result=c.get('/malware-families/'+r['family_id']+'/reports/'+r['id']+'/download')
        assert result.status_code==200 and hashlib.sha256(result.data).hexdigest()==r['sha256']
        assert r['uploaded_by']==uid
    assert not db().execute('PRAGMA foreign_key_check').fetchall()
""".replace(
        "ARCHIVE", str(archive)
    ).replace(
        "PROFILE", fid
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "MARE_DATA_DIR": str(destination)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_shared_merge_rollback_conflicts_and_legacy_preservation(tmp_path, monkeypatch):
    from family_portable import export_library, restore_library, check_conflicts
    from sync_helpers import apply_preview

    client, *_ = fixture()
    fid = create(client)
    upload(client, fid, [("report.pdf", pdf())])
    with app.app_context():
        data = export_library(db(), ROOT)
        # A different profile ID using the same linked tag is an explicit conflict.
        conflict = json.loads(json.dumps(data))
        conflict["families"][0]["id"] = str(uuid.uuid4())
        for r in conflict["families"][0]["reports"]:
            r["family_id"] = conflict["families"][0]["id"]
        with pytest.raises(ValueError, match="already uses"):
            check_conflicts(db(), ROOT, conflict)
        # Simulate a clean destination shared library while retaining staged bytes.
        staged = tmp_path / "staged"
        (staged / "family-reports").mkdir(parents=True)
        import shutil

        for row in reports(fid):
            shutil.copyfile(storage_path(ROOT, row["id"]), staged / row["storage_ref"])
        db().execute("DELETE FROM malware_families")
        db().execute("DELETE FROM tags")
        db().commit()
        for path in (ROOT / "family-reports").iterdir():
            path.unlink()
        db().execute(
            "CREATE TRIGGER inject_shared_failure BEFORE INSERT ON family_reports BEGIN SELECT RAISE(ABORT,'injected shared import failure'); END"
        )
        db().commit()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                restore_library(db(), ROOT, staged, data)
            assert (
                db().execute("SELECT count(*) FROM malware_families").fetchone()[0] == 0
            )
            assert db().execute("SELECT count(*) FROM tags").fetchone()[0] == 0
            assert not list((ROOT / "family-reports").iterdir())
        finally:
            db().execute("DROP TRIGGER inject_shared_failure")
            db().commit()
        restore_library(db(), ROOT, staged, data)
    # A legacy archive missing the library section must preserve the restored files.
    exported = post(client, "/import-export/export")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exported.data)) as src, zipfile.ZipFile(
        out, "w"
    ) as dst:
        for info in src.infolist():
            if info.filename.startswith("library/"):
                continue
            content = src.read(info)
            if info.filename == "backup.json":
                index = json.loads(content)
                index["schema"] = "mare-case-backup/2"
                index.pop("family_library")
                content = json.dumps(index).encode()
            dst.writestr(info, content)
    preview = client.post(
        "/import-export/import",
        data={
            "csrf": "family-csrf",
            "backup": (io.BytesIO(out.getvalue()), "legacy.zip"),
        },
        content_type="multipart/form-data",
    )
    assert apply_preview(client, preview, csrf="family-csrf").status_code == 302
    assert len(reports(fid)) == 1 and storage_path(ROOT, reports(fid)[0]["id"]).exists()


def test_corrupt_attachment_restore_and_v1_installation_compatibility(tmp_path):
    client, *_ = fixture()
    fid = create(client)
    upload(client, fid, [("report.pdf", pdf())])
    data = make_backup(client)
    row = reports(fid)[0]
    key = "data/" + row["storage_ref"]
    bad = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(bad, "w") as dst:
        payload = bytearray(src.read(key))
        payload[10] ^= 1
        payload = bytes(payload)
        for info in src.infolist():
            content = src.read(info)
            if info.filename == key:
                content = payload
            if info.filename == "installation.json":
                m = json.loads(content)
                m["files"][key] = {
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                content = json.dumps(m).encode()
            dst.writestr(info, content)
    with pytest.raises(ValueError, match="SHA-256"):
        restore_installation(bad, tmp_path / "refused-corrupt")
    assert not (tmp_path / "refused-corrupt").exists()
    # Make a real prior-version database/manifest without attachments.
    database = tmp_path / "v1.sqlite3"
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        database.write_bytes(src.read("data/workflow.sqlite3"))
    con = sqlite3.connect(database)
    con.execute("DROP TABLE family_reports")
    con.execute("DELETE FROM schema_migrations WHERE name='family-reports-v1'")
    con.commit()
    con.close()
    content = database.read_bytes()
    old = tmp_path / "v1.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(old, "w") as dst:
        for info in src.infolist():
            if info.filename.startswith("data/family-reports/"):
                continue
            payload = src.read(info)
            if info.filename == "data/workflow.sqlite3":
                payload = content
            if info.filename == "installation.json":
                m = json.loads(payload)
                m["schema"] = "mare-installation-backup/1"
                m["required_migration"] = "malware-families-v1"
                m["counts"].pop("family_reports")
                for key in ("threat_actors","actor_osint","actor_reports","actor_families"):
                    m["counts"].pop(key, None)
                m["files"] = {
                    k: v
                    for k, v in m["files"].items()
                    if not k.startswith("data/family-reports/")
                }
                m["files"]["data/workflow.sqlite3"] = {
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                payload = json.dumps(m).encode()
            dst.writestr(info, payload)
    result = restore_installation(old, tmp_path / "old-recovered")
    assert (
        result["counts"]["family_reports"] == 0
        and result["counts"]["malware_families"] == 1
    )


def test_profile_delete_failure_restores_files_and_single_case_scope():
    client, _, cid, _ = fixture()
    fid = create(client)
    upload(client, fid, [("family.pdf", pdf())])
    row = reports(fid)[0]
    path = storage_path(ROOT, row["id"])
    before = path.read_bytes()
    response = post(client, f"/cases/{cid}/backup")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert not any(
            "family-reports" in name or name.startswith("library/")
            for name in archive.namelist()
        )
    with app.app_context():
        db().execute(
            "CREATE TRIGGER inject_delete_failure BEFORE DELETE ON malware_families BEGIN SELECT RAISE(ABORT,'injected profile delete failure'); END"
        )
        db().commit()
    try:
        response = post(
            client,
            f"/malware-families/{fid}/delete",
            confirm_name="Existing family",
            version=profile(fid)["version"],
        )
        assert response.status_code == 400
        assert path.read_bytes() == before and len(reports(fid)) == 1
        assert not list((ROOT / "family-report-staging").iterdir())
    finally:
        with app.app_context():
            db().execute("DROP TRIGGER inject_delete_failure")
            db().commit()


def test_tags_actions_follow_relink_rename_and_permissions():
    from test_malware_families import edit

    client, uid, _, tid = fixture()
    fid = create(client)
    assert edit(client, fid, tag="MAL_NEW_LINK").status_code == 302
    text = client.get("/tags").text
    assert f"tag_id={tid}" in text and f"{fid}?tab=overview" in text
    new_tag = profile(fid)["tag_id"]
    post(client, f"/tags/{new_tag}/rename", name="MAL_RENAMED_LINK")
    assert f"{fid}?tab=overview" in client.get("/tags?q=MAL_RENAMED_LINK").text
    with app.app_context():
        db().execute("UPDATE users SET role='User' WHERE id=?", (uid,))
        db().commit()
    text = client.get("/tags").text
    assert "View malware family" in text and "Create malware family" not in text
    assert client.get(f"/malware-families/new?tag_id={tid}").status_code == 403
