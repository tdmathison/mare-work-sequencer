import io
import json
import os
from pathlib import Path
import sys
import time
import pytest
from app import app, db, run, ensure_package
from authorization import initialize_roles

SOURCE = 'import "pe"\nrule First { strings: $a = "MARE_TEST" condition: $a }\nrule Second { condition: First and filesize < 1MB }\n'


@pytest.fixture
def client(monkeypatch, tmp_path):
    with app.app_context():
        initialize_roles(db())
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES('yara-test','unused','User',0)"
        ).lastrowid
        cid = run(
            "INSERT INTO cases(number,name,created,stage,owner,creator,owner_required) VALUES('YARA-1','YARA case','2026',1,?,?,1)",
            (uid, uid),
        ).lastrowid
        ensure_package(cid)
    test = app.test_client()
    with test.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="yara-token")
    test.cid, test.uid = cid, uid
    engine = app.extensions["yara_engine"]
    monkeypatch.setattr(engine, "root", tmp_path / "jobs")
    engine.root.mkdir()
    monkeypatch.setattr(engine, "cached", None)
    monkeypatch.setattr(engine, "python", sys.executable)
    return test


def post(client, path, **fields):
    return client.post(path, data={"csrf": "yara-token", **fields})


def wait(client, job):
    for _ in range(300):
        result = client.get("/tools/yara-rule-editor/jobs/" + job).json
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(0.02)
    raise AssertionError("Job did not complete")


def compiler():
    if not app.extensions["yara_engine"].discover()["available"]:
        pytest.skip("Optional classic YARA 4.5.4 compiler unavailable")


def test_workspace_guard_missing_engine_and_draft(client, monkeypatch):
    assert app.test_client().get("/tools/yara-rule-editor/app/").status_code == 302
    assert (
        client.post(
            "/tools/yara-rule-editor/draft", data={"source_json": '"x"'}
        ).status_code
        == 403
    )
    engine = app.extensions["yara_engine"]
    monkeypatch.setattr(engine, "python", "/missing/python")
    engine.cached = None
    state = client.get("/tools/yara-rule-editor/state").json
    assert not state["engine"]["available"]
    assert b"YARA Rule Editor" in client.get("/tools/yara-rule-editor/app/").data
    assert (
        post(
            client,
            "/tools/yara-rule-editor/draft",
            source_json=json.dumps(SOURCE),
            context='{"caseId":"1"}',
        ).status_code
        == 200
    )
    assert client.get("/tools/yara-rule-editor/state").json["draft"]["source"] == SOURCE
    assert (
        post(
            client, "/tools/yara-rule-editor/download", source_json=json.dumps(SOURCE)
        ).data.decode()
        == SOURCE
    )
    assert (
        post(
            client,
            "/tools/yara-rule-editor/jobs",
            kind="validate",
            source_json=json.dumps(SOURCE),
        ).status_code
        == 503
    )
    app.extensions["analyst_tools"]["yara-rule-editor"]  # registry present
    from dataclasses import replace

    original = app.extensions["analyst_tools"]["yara-rule-editor"]
    monkeypatch.setitem(
        app.extensions["analyst_tools"],
        "yara-rule-editor",
        replace(original, enabled=False),
    )
    assert client.get("/tools/yara-rule-editor/app/").status_code == 404


def test_complete_file_save_paths_permissions_and_conflict(client):
    path = f"/cases/{client.cid}/yara-file"
    raw = "\ufeff// untouched\r\n" + SOURCE.replace("\n", "\r\n")
    saved = post(
        client, path, filename="nested/multiple.yara", source_json=json.dumps(raw)
    )
    assert saved.status_code == 200, saved.data
    opened = client.get(path + "?path=nested/multiple.yara").json
    assert opened["source"] == raw
    preview = client.get(
        f"/cases/{client.cid}/file?path=signatures/nested/multiple.yara"
    )
    assert preview.status_code == 200 and b"YARA Rule Editor" in preview.data
    assert (
        client.post(
            f"/cases/{client.cid}/file",
            data={
                "csrf": "yara-token",
                "path": "signatures/nested/multiple.yara",
                "content": "lost",
            },
        ).status_code
        == 405
    )
    assert (
        post(
            client,
            path,
            filename="nested/multiple.yara",
            source_json=json.dumps("other"),
        ).status_code
        == 409
    )
    assert (
        post(
            client, path, filename="../outside.yara", source_json=json.dumps(SOURCE)
        ).status_code
        == 400
    )
    assert (
        post(
            client, path, filename="bad.rules", source_json=json.dumps(SOURCE)
        ).status_code
        == 400
    )
    newer = SOURCE + "// complete document stays intact\n"
    assert (
        post(
            client,
            path,
            filename="nested/multiple.yara",
            source_json=json.dumps(newer),
            version=opened["version"],
        ).status_code
        == 200
    )
    assert (
        post(
            client,
            path,
            filename="nested/multiple.yara",
            source_json=json.dumps(raw),
            version=opened["version"],
        ).status_code
        == 409
    )
    with app.app_context():
        p = ensure_package(client.cid) / "signatures/nested/multiple.yara"
        assert p.read_text() == newer
        assert (
            db()
            .execute(
                "SELECT 1 FROM artifacts WHERE case_id=? AND path='signatures/nested/multiple.yara'",
                (client.cid,),
            )
            .fetchone()
        )
        run("UPDATE cases SET stage=3 WHERE id=?", (client.cid,))
    assert (
        post(
            client, path, filename="completed.yara", source_json=json.dumps(SOURCE)
        ).status_code
        == 409
    )
    assert client.get(f"/cases/{client.cid}/yara-files").json["editable"] is False
    with app.app_context():
        run("UPDATE cases SET stage=1 WHERE id=?", (client.cid,))
        run("UPDATE users SET role='Read-Only' WHERE id=?", (client.uid,))
    assert (
        post(
            client, path, filename="denied.yara", source_json=json.dumps(SOURCE)
        ).status_code
        == 403
    )
    assert client.get(path + "?path=nested/multiple.yara").status_code == 403


def test_real_compile_scan_dependencies_and_include_restriction(client):
    compiler()
    response = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="scan",
        source_json=json.dumps(SOURCE),
        positive=(io.BytesIO(b"prefix MARE_TEST suffix"), "positive.bin"),
        baseline=(io.BytesIO(b"benign"), "baseline.bin"),
    )
    assert response.status_code == 202, response.data
    result = wait(client, response.json["id"])
    assert result["compiled"] and result["status"] == "completed", result
    assert [r["status"] for r in result["results"]] == ["match", "no match"]
    first = result["results"][0]["matches"][0]
    assert first["rule"] == "First" and first["strings"][0]["identifier"] == "$a"
    assert first["strings"][0]["offset"] == 7 and first["strings"][0]["length"] == 9
    assert not (app.extensions["yara_engine"].root / result["id"] / "work").exists()
    bad = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="validate",
        source_json=json.dumps('include "/etc/passwd"\n' + SOURCE),
    )
    result = wait(client, bad.json["id"])
    assert result["status"] == "failed" and not result["compiled"]
    assert (
        result["diagnostics"][0]["line"] == 1
        and "include" in result["diagnostics"][0]["message"].lower()
    )
    malformed = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="validate",
        source_json=json.dumps("rule A {\n condition: invalid_symbol\n}"),
    )
    result = wait(client, malformed.json["id"])
    assert result["diagnostics"][0]["line"] == 2
    assert result["diagnostics"][0]["column"] is None


def test_sample_access_and_upload_limits(client, monkeypatch):
    compiler()
    with app.app_context():
        samples = ensure_package(client.cid) / "samples"
        samples.mkdir(exist_ok=True)
        (samples / "safe.bin").write_bytes(b"MARE_TEST")
    result = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="scan",
        case_id=str(client.cid),
        positive_path="samples/safe.bin",
        source_json=json.dumps(SOURCE),
    )
    assert result.status_code == 202
    assert wait(client, result.json["id"])["results"][0]["status"] == "match"
    assert post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="scan",
        case_id=str(client.cid),
        positive_path="samples/../../../../session.key",
        source_json=json.dumps(SOURCE),
    ).status_code in (400, 404)
    monkeypatch.setitem(app.config, "YARA_UPLOAD_LIMIT", 1024)
    assert (
        post(
            client,
            "/tools/yara-rule-editor/jobs",
            kind="scan",
            source_json=json.dumps(SOURCE),
            positive=(io.BytesIO(b"x" * 1025), "big.bin"),
        ).status_code
        == 400
    )
    assert (
        post(
            client,
            "/tools/yara-rule-editor/draft",
            source_json=json.dumps("x" * 100001),
        ).status_code
        == 400
    )


def test_timeout_cancel_failure_cleanup_and_job_ownership(client, monkeypatch):
    engine = app.extensions["yara_engine"]
    monkeypatch.setitem(engine.app.config, "SNORT_TIMEOUT", 0.1)
    timed = engine.run([sys.executable, "-c", "import time;time.sleep(2)"], engine.root)
    assert not timed["success"] and timed["reason"] == "timeout"
    engine.cached = dict(available=True, version="4.5.4")
    engine.cached_at = time.time()

    def blocked(args, work, cancel=lambda: False):
        while not cancel():
            time.sleep(0.01)
        return dict(success=False, reason="cancelled", code=-9, stdout="", stderr="")

    monkeypatch.setattr(engine, "run", blocked)
    response = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="validate",
        source_json=json.dumps(SOURCE),
    )
    assert response.status_code == 202
    job = response.json["id"]
    assert (
        post(client, "/tools/yara-rule-editor/jobs/" + job + "/cancel").status_code
        == 200
    )
    assert wait(client, job)["status"] == "cancelled"
    assert not (engine.root / job / "work").exists()
    with client.session_transaction() as session:
        session["uid"] = 9999
    assert client.get("/tools/yara-rule-editor/jobs/" + job).status_code == 302


def test_snippet_catalog_compiles_with_declared_prerequisites():
    import subprocess

    compiler()
    node = subprocess.run(
        [
            "node",
            "-e",
            "const e=require('esbuild'),b={exports:{}};new Function('module','exports',e.buildSync({entryPoints:['frontend/yara-language.js'],bundle:true,write:false,format:'cjs'}).outputFiles[0].text)(b,b.exports);process.stdout.write(JSON.stringify(b.exports.SNIPPETS));",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import yara

    for name, expression, prerequisites in json.loads(node.stdout):
        source = (
            'import "pe"\nrule Example { strings: $sample="x" $group1="a" $group2="b" condition: ('
            + expression
            + ") and all of them }"
        )
        try:
            yara.compile(source=source, includes=False)
        except yara.Error as error:
            pytest.fail(f"{name}: {error} ({prerequisites})")


def test_other_user_job_access_and_abandoned_cleanup(client, monkeypatch):
    compiler()
    response = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="validate",
        source_json=json.dumps(SOURCE),
    )
    result = wait(client, response.json["id"])
    with app.app_context():
        other = run(
            "INSERT INTO users(username,password,role,forced) VALUES('other-yara','unused','User',0)"
        ).lastrowid
    outsider = app.test_client()
    with outsider.session_transaction() as session:
        session.update(uid=other, version=1, csrf="other-token")
    assert (
        outsider.get("/tools/yara-rule-editor/jobs/" + result["id"]).status_code == 404
    )
    engine = app.extensions["yara_engine"]
    directory = engine.root / result["id"]
    old = engine.read(directory)
    old["updated"] = 0
    (directory / "status.json").write_text(json.dumps(old))
    engine.cleanup()
    assert not directory.exists()
    abandoned = engine.root / ("a" * 32)
    abandoned.mkdir()
    (abandoned / "work").mkdir()
    (abandoned / "work/positive.sample").write_bytes(b"temporary")
    engine.write(abandoned, dict(status="running", user="stopped", updated=0))
    engine.cleanup()
    assert not (abandoned / "work").exists()
    assert engine.read(abandoned)["status"] == "failed"


def test_scan_failure_is_not_successful_no_match(client, monkeypatch):
    engine = app.extensions["yara_engine"]
    engine.cached = dict(available=True, version="4.5.4")
    engine.cached_at = time.time()
    output = dict(
        compiled=True,
        diagnostics=[],
        results=[
            dict(sample="positive", status="error", matches=[], error="scan timeout")
        ],
    )
    monkeypatch.setattr(
        engine,
        "run",
        lambda *args, **kw: dict(
            success=True, code=0, reason="", stdout=json.dumps(output), stderr=""
        ),
    )
    response = post(
        client,
        "/tools/yara-rule-editor/jobs",
        kind="scan",
        source_json=json.dumps(SOURCE),
        positive=(io.BytesIO(b"data"), "positive.bin"),
    )
    result = wait(client, response.json["id"])
    assert result["status"] == "failed" and result["compiled"]
    assert result["results"][0]["status"] == "error"
    assert not (engine.root / result["id"] / "work").exists()


def test_yara_asset_search_and_archive_integration(client):
    from app import build_archive
    import zipfile

    result = post(
        client,
        f"/cases/{client.cid}/yara-file",
        filename="nested/searchable.yara",
        source_json=json.dumps(SOURCE + "// unique_yara_case_marker\n"),
    )
    assert result.status_code == 200
    index = app.extensions["mip_search"]
    with app.app_context():
        index.refresh()
        archive, name = build_archive(client.cid, "raw")
        with zipfile.ZipFile(archive) as zipped:
            assert (
                zipped.read(name + "/signatures/nested/searchable.yara").decode()
                == SOURCE + "// unique_yara_case_marker\n"
            )
        archive.close()
    results = client.get("/search/results?q=unique_yara_case_marker")
    assert results.status_code == 200
    assert "searchable.yara" in results.get_data(as_text=True)
