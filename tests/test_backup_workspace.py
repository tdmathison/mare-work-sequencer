import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import zipfile
import pytest
from werkzeug.security import generate_password_hash
from app import app, db, ROOT, ensure_package
from authorization import initialize_roles
from malware_families import initialize as init_families
from tagging import initialize as init_tags, create as create_tag
from backup_areas import initialize, selection


def setup():
    with app.app_context():
        init_tags(db())
        init_families(db())
        initialize_roles(db())
        initialize(db())
        uid = (
            db()
            .execute(
                "INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",
                (
                    "recovery-admin",
                    generate_password_hash("recovery-admin-password"),
                    "Administrator",
                ),
            )
            .lastrowid
        )
        cid = (
            db()
            .execute(
                "INSERT INTO cases(number,name,stage,created,owner,creator) VALUES('MARE-2026-000050','Recovery research',1,'2026-10-01',?,?)",
                (uid, uid),
            )
            .lastrowid
        )
        tid = create_tag(db(), "MAL_RECOVERY")[0]
        db().execute("INSERT INTO case_tags VALUES(?,?,?,?)", (cid, tid, "2026", uid))
        db().commit()
        ensure_package(cid)
        (ROOT / f"cases/{cid}/mip/scripts/test.py").write_bytes(b'print("recovery")')
        app.extensions["case_sync"].reconcile(cid)
        db().commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="backup-workspace")
    return client, uid, cid, tid


def post(client, path, **values):
    return client.post(path, data={"csrf": "backup-workspace", **values})


def wait(client, jid, state=None):
    for _ in range(400):
        response = client.get("/backup-restore/jobs/" + jid)
        assert response.status_code == 200, response.status_code
        data = response.json
        if data["state"] not in ("queued", "running"):
            if state:
                assert data["state"] == state, data
            return data
        time.sleep(0.025)
    raise AssertionError("Backup job did not finish")


def export(client, areas=None, complete=False, password="a strong recovery passphrase"):
    response = post(
        client,
        "/backup-restore/jobs",
        kind="export",
        areas=areas or [],
        complete="1" if complete else "",
        passphrase=password,
    )
    assert response.status_code == 202, response.text
    data = wait(client, response.json["id"], "completed")
    archive = client.get("/backup-restore/jobs/" + data["id"] + "/download")
    assert archive.status_code == 200
    return archive.data, data


def inspect(client, archive, password="a strong recovery passphrase"):
    response = post(
        client,
        "/backup-restore/jobs",
        kind="inspect",
        passphrase=password,
        archive=(io.BytesIO(archive), "backup.zip"),
    )
    assert response.status_code == 202, response.text
    return wait(client, response.json["id"])


def test_registry_permissions_csrf_and_deprecated_plaintext_export():
    c, uid, *_ = setup()
    assert selection(["cases"]) == (["cases"], ["tags"])
    assert selection(["cases", "families", "tags"])[1] == ["actors"]
    assert selection([], True)[0] == ["actors", "cases", "families", "tags"]
    assert selection(["actors"]) == (["actors"], ["families", "tags"])
    assert c.get("/import-export", follow_redirects=True).status_code == 200
    assert "Complete application backup" in c.get("/backup-restore", follow_redirects=True).text
    assert c.post("/backup-restore/jobs", data={"kind": "export"}).status_code == 403
    assert post(c, "/account/database-backup").status_code == 302
    assert (
        post(
            c, "/backup-restore/jobs", kind="export", complete="1", passphrase="short"
        ).status_code
        == 400
    )
    assert post(c, "/backup-restore/jobs", kind="export").status_code == 400
    with app.app_context():
        db().execute("UPDATE users SET role='User' WHERE id=?", (uid,))
        db().commit()
    assert c.get("/backup-restore", follow_redirects=True).status_code == 403
    assert (
        post(c, "/backup-restore/jobs", kind="export", areas=["tags"]).status_code
        == 403
    )


def test_selective_single_archive_inspection_no_data_change_and_stale_plan():
    c, uid, cid, tid = setup()
    archive, job = export(c, ["tags"], password="")
    assert job["manifest"]["complete"] is False
    assert job["manifest"]["counts"]["cases"] == 0
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert set(z.namelist()) == {"mare-backup.json", "payload.zip"}
        assert b"recovery-admin-password" not in archive
    with app.app_context():
        before = [tuple(r) for r in db().execute("SELECT * FROM cases")]
    plan = inspect(c, archive, password="")
    assert plan["state"] == "preview", plan
    assert not plan["preview"]["conflicts"]
    with app.app_context():
        assert before == [tuple(r) for r in db().execute("SELECT * FROM cases")]
    with app.app_context():
        db().execute("UPDATE cases SET name='Changed after review' WHERE id=?", (cid,))
        db().commit()
    response = post(c, "/backup-restore/jobs/" + plan["id"] + "/apply")
    assert response.status_code == 202
    failed = wait(c, plan["id"], "failed")
    assert "changed after preview" in failed["error"]


def test_encrypted_complete_export_and_actual_replacement(tmp_path):
    c, uid, cid, tid = setup()
    from test_family_reports import pdf

    result = post(
        c,
        "/malware-families/new",
        name="Recovered family",
        aliases=["Recovery Alias", "Other Name"],
        tag="MAL_RECOVERY",
        short_description="Recovered description",
    )
    assert result.status_code == 302
    fid = result.location.split("/")[-1].split("?")[0]
    assert (
        post(
            c,
            f"/malware-families/{fid}/osint/new",
            version=1,
            title="Recovery research",
            url="https://example.com/research",
            position=1,
        ).status_code
        == 302
    )
    with app.app_context():
        version = (
            db()
            .execute("SELECT version FROM malware_families WHERE id=?", (fid,))
            .fetchone()[0]
        )
    assert (
        post(
            c,
            f"/malware-families/{fid}/reports/upload",
            version=version,
            reports=(io.BytesIO(pdf()), "recovery-research.pdf"),
        ).status_code
        == 302
    )
    (ROOT / "recovery-template.bin").write_bytes(b"application customization")
    with app.app_context():
        db().execute("INSERT INTO site_settings VALUES('recovery-setting','preserved')")
        db().commit()
    from test_explorer_research import configuration
    saved = post(c, '/data-explorer/views', name='Recovery graph', description='Owner-scoped configuration', configuration=json.dumps(configuration(cid)))
    assert saved.status_code == 201, saved.text
    archive, job = export(c, complete=True)
    assert (
        job["manifest"]["complete"] and job["manifest"]["record_counts"]["users"] == 1
    )
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert all(i.flag_bits & 1 for i in z.infolist())
        with pytest.raises(RuntimeError):
            z.read("mare-backup.json")
    wrong = inspect(c, archive, password="wrong")
    assert wrong["state"] == "failed"
    plan = inspect(c, archive)
    assert plan["state"] == "preview", plan
    assert not plan["preview"]["blocking"], plan
    assert post(c, "/backup-restore/jobs/" + plan["id"] + "/apply").status_code == 400
    # Recovery is exercised in a separate clean compatible application process.
    source = tmp_path / "complete.zip"
    source.write_bytes(archive)
    destination = tmp_path / "fresh-instance"
    code = """
import io,time
from app import app,db,ROOT
from werkzeug.security import generate_password_hash
with app.app_context():
    uid=db().execute("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('bootstrap',generate_password_hash('bootstrap-password'),'Administrator')).lastrowid;db().commit()
client=app.test_client()
with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='dr')
r=client.post('/backup-restore/jobs',data={'csrf':'dr','kind':'inspect','passphrase':'a strong recovery passphrase','archive':(io.BytesIO(open('ARCHIVE','rb').read()),'complete.zip')},content_type='multipart/form-data')
assert r.status_code==202,r.text
jid=r.json['id']
for _ in range(500):
    state=client.get('/backup-restore/jobs/'+jid).json
    if state['state'] not in ('queued','running'):break
    time.sleep(.02)
assert state['state']=='preview' and not state['preview']['blocking'],state
r=client.post('/backup-restore/jobs/'+jid+'/apply',data={'csrf':'dr','ack':'REPLACE'});assert r.status_code==202,r.text
service=app.extensions['backup_workspace']
for _ in range(500):
    state=__import__('json').loads((service.directory/jid/'job.json').read_text())
    if state['state'] not in ('queued','running'):break
    time.sleep(.02)
assert state['state']=='completed',state
assert client.get('/').status_code==302
r=client.post('/login',data={'csrf':client.get('/login').text.split('name="csrf" value="')[1].split('"')[0],'username':'recovery-admin','password':'recovery-admin-password'})
assert r.status_code==302,r.text
with app.app_context():
    assert db().execute("SELECT value FROM site_settings WHERE name='recovery-setting'").fetchone()[0]=='preserved'
    view=db().execute("SELECT v.* FROM explorer_views v JOIN users u ON u.user_uuid=v.owner_uuid WHERE u.username='recovery-admin'").fetchone()
    assert view['name']=='Recovery graph' and __import__('json').loads(view['configuration'])['positions']
    assert len(client.get('/data-explorer/views').json['views'])==1

    case=db().execute('SELECT * FROM cases').fetchone();assert case['number']=='MARE-2026-000050' and case['stage']==1
    assert db().execute('SELECT count(*) FROM case_tags').fetchone()[0]==1
    assert db().execute("SELECT 1 FROM reserved_case_numbers WHERE number='MARE-2026-000050'").fetchone()
    assert (ROOT/('cases/'+str(case['id'])+'/mip/scripts/test.py')).read_bytes()==b'print("recovery")'
    family=db().execute('SELECT * FROM malware_families').fetchone()
    assert __import__('json').loads(family['aliases'])==['Recovery Alias','Other Name']
    assert family['name']=='Recovered family' and family['tag_id']==db().execute('SELECT tag_id FROM case_tags').fetchone()[0]
    assert family['created_by']==db().execute("SELECT id FROM users WHERE username='recovery-admin'").fetchone()[0]
    assert db().execute('SELECT title FROM family_osint WHERE family_id=? ORDER BY position',(family['id'],)).fetchone()[0]=='Recovery research'
    report=db().execute('SELECT * FROM family_reports').fetchone()
    downloaded=client.get('/malware-families/'+family['id']+'/reports/'+report['id']+'/download')
    assert downloaded.status_code==200 and __import__('hashlib').sha256(downloaded.data).hexdigest()==report['sha256']
    asset=client.get('/cases/'+str(case['id'])+'/file?path=scripts/test.py&download=1')
    assert asset.status_code==200 and __import__('hashlib').sha256(asset.data).hexdigest()==__import__('hashlib').sha256(b'print("recovery")').hexdigest()
    assert (ROOT/'recovery-template.bin').read_bytes()==b'application customization'
    from performance_metrics import scorecard
    inventory=scorecard(db());assert inventory['total']==db().execute('SELECT count(*) FROM cases').fetchone()[0]
    assert inventory['completed_current']==db().execute('SELECT count(*) FROM cases WHERE stage=3').fetchone()[0]
    from app import allocate_case_number
    next_number=allocate_case_number(db());assert next_number!='MARE-2026-000050';db().rollback()
""".replace(
        "ARCHIVE", str(source)
    )
    checked = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "MARE_DATA_DIR": str(destination)},
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert checked.returncode == 0, checked.stderr


def test_selective_cases_families_and_tags_round_trips(tmp_path):
    from test_family_reports import pdf
    import uuid

    c, uid, cid, tid = setup()
    fid = str(uuid.uuid4())
    with app.app_context():
        db().execute(
            "INSERT INTO malware_families(id,name,tag_id,created_at,updated_at,created_by,updated_by) VALUES(?,?,?,?,?,?,?)",
            (fid, "Isolated family", tid, "2026", "2026", uid, uid),
        )
        db().commit()
    assert (
        post(
            c,
            f"/malware-families/{fid}/reports/upload",
            version=1,
            reports=(io.BytesIO(pdf()), "research.pdf"),
        ).status_code
        == 302
    )
    with app.app_context():
        from family_aliases import save_aliases
        save_aliases(db(), fid, ['First Alias', 'Second name'])
        db().commit()
    for area in ("cases", "families", "tags"):
        archive, job = export(c, [area], password="")
        source = tmp_path / (area + ".zip")
        source.write_bytes(archive)
        destination = tmp_path / ("fresh-" + area)
        code = (
            """
import io,time,json,hashlib
from app import app,db,ROOT
from werkzeug.security import generate_password_hash
with app.app_context():
    uid=db().execute("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('dest-admin',generate_password_hash('a real destination password'),'Administrator')).lastrowid;db().commit()
c=app.test_client()
with c.session_transaction() as s:s.update(uid=uid,version=1,csrf='selective')
r=c.post('/backup-restore/jobs',data={'csrf':'selective','kind':'inspect','archive':(io.BytesIO(open('SOURCE','rb').read()),'selective.zip')},content_type='multipart/form-data');assert r.status_code==202,r.text
jid=r.json['id']
def wait():
    for _ in range(300):
        value=c.get('/backup-restore/jobs/'+jid).json
        if value['state'] not in ('running','queued'):return value
        time.sleep(.02)
    raise AssertionError('Timed out')
value=wait();assert value['state']=='preview' and not value['preview']['conflicts'],value
assert c.post('/backup-restore/jobs/'+jid+'/apply',data={'csrf':'selective'}).status_code==202
value=wait();assert value['state']=='completed',value
with app.app_context():
    assert db().execute('SELECT count(*) FROM users').fetchone()[0]==1
    tags=db().execute('SELECT name FROM tags').fetchall();assert len(tags)==1 and tags[0][0]=='MAL_RECOVERY'
    if 'AREA'=='cases':
        case=db().execute('SELECT * FROM cases').fetchone();assert case and case['owner'] is None
        assert (ROOT/('cases/'+str(case['id'])+'/mip/scripts/test.py')).read_bytes()==b'print("recovery")'
        assert db().execute("SELECT 1 FROM reserved_case_numbers WHERE number='MARE-2026-000050'").fetchone()
        assert db().execute('SELECT count(*) FROM malware_families').fetchone()[0]==0
    elif 'AREA'=='families':
        f=db().execute('SELECT * FROM malware_families').fetchone();assert f['id']=='FID' and f['created_by'] is None
        assert json.loads(f['aliases'])==['First Alias','Second name']
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==0
        report=db().execute('SELECT * FROM family_reports').fetchone()
        result=c.get('/malware-families/'+f['id']+'/reports/'+report['id']+'/download')
        assert result.status_code==200 and hashlib.sha256(result.data).hexdigest()==report['sha256']
    else:
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==0
        assert db().execute('SELECT count(*) FROM malware_families').fetchone()[0]==0
""".replace(
                "SOURCE", str(source)
            )
            .replace("AREA", area)
            .replace("FID", fid)
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "MARE_DATA_DIR": str(destination)},
            capture_output=True,
            text=True,
            timeout=35,
        )
        assert result.returncode == 0, result.stderr


def test_tag_conflict_resolution_exact_plan_and_repeated_merge():
    c, uid, cid, tid = setup()
    archive, job = export(c, ["tags"], password="")
    # Same canonical name with a different permanent identity must be reviewed.
    with app.app_context():
        db().execute(
            "UPDATE family_tag_identities SET identity=? WHERE tag_id=?",
            ("a" * 32, tid),
        )
        db().commit()
    plan = inspect(c, archive, password="")
    assert plan["state"] == "preview" and plan["preview"]["conflicts"]
    assert post(c, "/backup-restore/jobs/" + plan["id"] + "/apply").status_code == 409
    choices = {item["key"]: "reuse" for item in plan["preview"]["conflicts"]}
    assert (
        post(
            c,
            "/backup-restore/jobs/" + plan["id"] + "/preview",
            choices=json.dumps(choices),
        ).status_code
        == 202
    )
    updated = wait(c, plan["id"], "preview")
    assert not updated["preview"]["conflicts"]
    assert post(c, "/backup-restore/jobs/" + plan["id"] + "/apply").status_code == 202
    applied = wait(c, plan["id"], "completed")
    assert applied["result"]["failed"] == 0
    repeated = inspect(c, archive, password="")
    assert not repeated["preview"]["conflicts"]
    assert (
        post(c, "/backup-restore/jobs/" + repeated["id"] + "/apply").status_code == 202
    )
    wait(c, repeated["id"], "completed")
    with app.app_context():
        assert db().execute("SELECT count(*) FROM tags").fetchone()[0] == 1
        assert (
            db().execute("SELECT count(*) FROM backup_tag_aliases").fetchone()[0] == 1
        )


def test_unsafe_archives_scope_and_job_ownership():
    c, uid, *_ = setup()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("../escape", "bad")
    bad = inspect(c, out.getvalue(), password="")
    assert bad["state"] == "failed"
    assert post(c, "/backup-restore/jobs/" + bad["id"] + "/apply").status_code == 409
    assert not (ROOT.parent / "escape").exists()
    archive, job = export(c, ["tags"], password="")
    with app.app_context():
        other = (
            db()
            .execute(
                "INSERT INTO users(username,password,role,forced) VALUES('other-backup-admin','unused','Administrator',0)"
            )
            .lastrowid
        )
        db().commit()
    different = app.test_client()
    with different.session_transaction() as s:
        s.update(uid=other, version=1, csrf="backup-workspace")
    assert different.get("/backup-restore/jobs/" + job["id"]).status_code == 404
    assert (
        different.get("/backup-restore/jobs/" + job["id"] + "/download").status_code
        == 404
    )
    assert app.test_client().get("/backup-restore/jobs/" + job["id"]).status_code == 302


def test_restart_rolls_back_before_database_bootstrap(tmp_path):
    from backup_workspace import bootstrap_guard, durable

    root = tmp_path / "app-data"
    root.mkdir()
    directory = root.parent / (
        ".mare-backup-work-" + hashlib.sha256(str(root).encode()).hexdigest()[:16]
    )
    old = directory / "replacement-recovery" / "old"
    old.mkdir(parents=True)
    (old / "workflow.sqlite3").write_bytes(b"original database")
    (old / "session.key").write_bytes(b"original key")
    (root / "workflow.sqlite3").write_bytes(b"incoming database")
    durable(
        directory / "replacement-recovery" / "journal.json",
        dict(
            phase="prepared",
            moved_new=["workflow.sqlite3"],
            moved_old=["workflow.sqlite3", "session.key"],
        ),
    )
    handle = bootstrap_guard(root)
    try:
        assert (root / "workflow.sqlite3").read_bytes() == b"original database"
        assert (root / "session.key").read_bytes() == b"original key"
        assert not (directory / "replacement-recovery").exists()
    finally:
        os.close(handle)


def test_queued_submission_is_deduplicated_and_payload_hash_is_verified(monkeypatch):
    c, *_ = setup()
    service = app.extensions["backup_workspace"]
    archive, _ = export(c, ["tags"], password="")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        manifest = z.read("mare-backup.json")
        payload = z.read("payload.zip")
    damaged = io.BytesIO()
    with zipfile.ZipFile(damaged, "w") as z:
        z.writestr("mare-backup.json", manifest)
        z.writestr("payload.zip", payload + b"changed")
    failed = inspect(c, damaged.getvalue(), password="")
    assert failed["state"] == "failed" and "integrity" in failed["error"]
    assert not (service.job_path(failed["id"]) / "payload.zip").exists()
    with monkeypatch.context() as patch:
        patch.setattr(service, "submit", lambda *args: None)
        first = post(c, "/backup-restore/jobs", kind="export", areas=["tags"])
        assert first.status_code == 202
        duplicate = post(c, "/backup-restore/jobs", kind="export", areas=["tags"])
        assert duplicate.status_code == 409 and duplicate.json["id"] == first.json["id"]
    data = json.loads((service.job_path(first.json["id"]) / "job.json").read_text())
    data["state"] = "failed"
    service.save(data)


def test_legacy_complete_archive_uses_unified_inspection():
    from test_malware_families import make_backup

    c, *_ = setup()
    result = inspect(c, make_backup(c), password="")
    assert result["state"] == "preview", result
    assert result["preview"]["complete"] and result["preview"]["warnings"]


def test_publication_failure_restores_original_files(tmp_path, monkeypatch):
    from backup_workspace import BackupWorkspace
    from flask import g

    service = object.__new__(BackupWorkspace)
    service.root = tmp_path / "destination"
    service.root.mkdir()
    service.directory = tmp_path / "workspace"
    service.directory.mkdir()
    service.update = lambda *args, **kwargs: None
    restored = tmp_path / "incoming"
    restored.mkdir()
    for name in ("workflow.sqlite3", "session.key"):
        (service.root / name).write_bytes(("original " + name).encode())
        (restored / name).write_bytes(("incoming " + name).encode())
    original = Path.rename

    def failing_rename(path, target):
        if path == restored / "session.key":
            raise OSError("injected publication failure")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", failing_rename)
    with app.test_request_context("/"):
        g.backup_exclusive = True
        with pytest.raises(OSError, match="injected"):
            service.publish_replace({}, restored)
    for name in ("workflow.sqlite3", "session.key"):
        assert (service.root / name).read_bytes() == ("original " + name).encode()
    assert not (service.directory / "replacement-recovery").exists()


def test_snapshot_blocks_http_edits_until_files_and_database_captured(monkeypatch):
    import threading

    c, uid, cid, _ = setup()
    service = app.extensions["backup_workspace"]
    writer = app.test_client()
    with writer.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="backup-workspace")
    started = threading.Event()
    finished = threading.Event()
    responses = []

    def edit():
        started.set()
        responses.append(post(writer, f"/cases/{cid}", name="After snapshot"))
        finished.set()

    original = service.helpers["database"]
    threads = []

    def snapshot():
        thread = threading.Thread(target=edit)
        threads.append(thread)
        thread.start()
        assert started.wait(2)
        assert not finished.wait(0.1), "HTTP edit entered the snapshot boundary"
        response = original()
        assert not finished.is_set(), "HTTP edit changed snapshot files"
        return response

    monkeypatch.setitem(service.helpers, "database", snapshot)
    archive, job = export(c, complete=True)
    for thread in threads:
        thread.join(5)
    assert finished.is_set() and responses[0].status_code == 302
    import pyzipper

    with pyzipper.AESZipFile(io.BytesIO(archive)) as outer:
        outer.setpassword(b"a strong recovery passphrase")
        with zipfile.ZipFile(io.BytesIO(outer.read("payload.zip"))) as payload:
            database = service.job_path(job["id"]) / "snapshot-check.sqlite3"
            database.write_bytes(payload.read("data/workflow.sqlite3"))
            try:
                with sqlite3.connect(database) as con:
                    assert (
                        con.execute("SELECT name FROM cases").fetchone()[0]
                        == "Recovery research"
                    )
            finally:
                database.unlink()
    with app.app_context():
        assert (
            db().execute("SELECT name FROM cases WHERE id=?", (cid,)).fetchone()[0]
            == "After snapshot"
        )
