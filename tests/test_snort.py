import io
import json
import os
from pathlib import Path
import struct
import sys
import time
import pytest
from app import app, db, run, ensure_package
from authorization import initialize_roles
from signature_files import analyze, document, persist, save_selected, version, Conflict
from snort_engine import Engine, capture_format

RULE = 'alert tcp any any -> any 80 (msg:"Harmless"; content:"/mare-example"; sid:1000001; rev:1;)'


@pytest.fixture
def client(monkeypatch, tmp_path):
    with app.app_context():
        initialize_roles(db())
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES('snort-test','unused','User',0)"
        ).lastrowid
        cid = run(
            "INSERT INTO cases(number,name,created,stage,owner,creator,owner_required) VALUES('SNORT-1','Snort case','2026',1,?,?,1)",
            (uid, uid),
        ).lastrowid
        ensure_package(cid)
    test = app.test_client()
    with test.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="snort-token")
    test.cid = cid
    test.uid = uid
    engine = app.extensions["snort_engine"]
    monkeypatch.setattr(engine, "root", tmp_path / "jobs")
    engine.root.mkdir()
    monkeypatch.setattr(engine, "cached", None)
    for k, v in dict(
        SNORT_EXECUTABLE="",
        SNORT_PROFILE="",
        SNORT_RUNNER="",
        SNORT_TIMEOUT=1,
        SNORT_CONCURRENCY=1,
        SNORT_UPLOAD_LIMIT=1024,
    ).items():
        monkeypatch.setitem(app.config, k, v)
    return test


def post(client, endpoint, **fields):
    return client.post(endpoint, data={"csrf": "snort-token", **fields})


def test_workspace_auth_missing_engine_draft(client):
    assert app.test_client().get("/tools/snort-rule-builder/app/").status_code == 302
    page = client.get("/tools/snort-rule-builder/app/")
    assert page.status_code == 200 and b"data-rule-editor" in page.data
    assert (
        client.get("/tools/snort-rule-builder/state").json["engine"]["status"]
        == "missing_engine"
    )
    assert (
        post(
            client,
            "/tools/snort-rule-builder/jobs",
            kind="validate",
            source_json=json.dumps(RULE),
        ).status_code
        == 503
    )
    raw = "# exact\r\n" + RULE + "\r\n"
    assert (
        post(
            client, "/tools/snort-rule-builder/draft", source_json=json.dumps(raw)
        ).status_code
        == 200
    )
    assert client.get("/tools/snort-rule-builder/state").json["draft"]["source"] == raw
    assert (
        post(
            client, "/tools/snort-rule-builder/download", source_json=json.dumps(raw)
        ).data
        == raw.encode()
    )
    assert client.post("/tools/snort-rule-builder/draft").status_code == 403


def test_capture_content_not_extension():
    raw = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    capture_format(raw)
    for invalid in (b"not a capture" * 4, raw + b"bad", raw[:10]):
        with pytest.raises(ValueError):
            capture_format(invalid)
    with pytest.raises(ValueError, match="PCAPNG"):
        capture_format(b"\x0a\x0d\x0d\x0a" + b"0" * 24)


def fake_engine(client, monkeypatch, tmp_path):
    exe = tmp_path / "engine"
    exe.write_text(
        "#!"
        + sys.executable
        + '\nimport sys\nif "-V" in sys.argv:print("Snort++ Version 3.1.99 fake")\nelif "--help-options" in sys.argv:print("-T -R -r -c --lua -A -l")\nelse:print("content http_uri alert_json")\n'
    )
    exe.chmod(0o700)
    profile = tmp_path / "snort.lua"
    profile.write_text("-- fake fixture only")
    runner = tmp_path / "runner"
    runner.write_text(
        "#!"
        + sys.executable
        + '\nimport sys,time,pathlib,json\nw=pathlib.Path(sys.argv[3]);r=(w/"current.rules").read_text()\nif "SLOW" in r:time.sleep(10)\nif "FAIL" in r:print("invalid option line 1");sys.exit(1)\nif "-r" in sys.argv:(w/"alert_json.txt").write_text(json.dumps({"rule":"1:1000001:1","msg":"fake"})+"\\n" if "target" in sys.argv[sys.argv.index("-r")+1] else "")\nprint("FAKE fixture only")\n'
    )
    runner.chmod(0o700)
    for k, v in dict(
        SNORT_EXECUTABLE=str(exe), SNORT_PROFILE=str(profile), SNORT_RUNNER=str(runner)
    ).items():
        monkeypatch.setitem(app.config, k, v)
    return app.extensions["snort_engine"]


def wait(engine, job):
    for _ in range(max(200, int(app.config["SNORT_TIMEOUT"] * 160))):
        state = engine.read(engine.root / job)
        if state["status"] not in ("running", "queued"):
            return state
        time.sleep(0.02)
    raise AssertionError("Job stuck")


def test_fake_engine_success_zero_failure_timeout_cancel_and_cleanup(
    client, monkeypatch, tmp_path
):
    engine = fake_engine(client, monkeypatch, tmp_path)
    assert engine.discover()["available"]
    with app.app_context():
        user = (
            db()
            .execute("SELECT user_uuid FROM users WHERE id=?", (client.uid,))
            .fetchone()[0]
        )
    job = engine.submit(user, RULE, [("target", b""), ("baseline", b"")])
    state = wait(engine, job["id"])
    assert state["status"] == "completed"
    assert [r["alert_count"] for r in state["results"]] == [1, 0]
    assert not (engine.root / job["id"] / "work").exists()
    for name in ("FAIL", "SLOW"):
        job = engine.submit(user, RULE.replace("Harmless", name), [])
        state = wait(engine, job["id"])
        assert (
            state["status"] == "failed"
            and not (engine.root / job["id"] / "work").exists()
        )
    job = engine.submit(user, RULE.replace("Harmless", "SLOW"), [])
    with pytest.raises(ValueError, match="busy"):
        engine.submit(user, RULE, [])
    assert (
        post(client, f'/tools/snort-rule-builder/jobs/{job["id"]}/cancel').status_code
        == 200
    )
    assert wait(engine, job["id"])["status"] == "cancelled"
    assert (
        app.test_client().get(f'/tools/snort-rule-builder/jobs/{job["id"]}').status_code
        == 302
    )


def test_real_engine_if_configured():
    if not all(
        os.environ.get("MARE_SNORT_" + k) for k in ("EXECUTABLE", "PROFILE", "RUNNER")
    ):
        pytest.skip(
            "Real Snort 3/profile/isolated runner not configured; fake-engine tests do not establish compatibility."
        )
    engine = app.extensions["snort_engine"]
    assert engine.discover()["available"]
    fixtures = Path(__file__).parent / "fixtures" / "snort"
    state = wait(
        engine,
        engine.submit(
            "integration",
            RULE,
            [
                ("target", (fixtures / "target.pcap").read_bytes()),
                ("baseline", (fixtures / "baseline.pcap").read_bytes()),
            ],
        )["id"],
    )
    assert state["status"] == "completed", state
    assert state["results"][0]["alert_count"] >= 1
    assert state["results"][1]["alert_count"] == 0


def test_setup_states_and_upload_resource_limits(client, monkeypatch, tmp_path):
    engine = fake_engine(client, monkeypatch, tmp_path)
    monkeypatch.setitem(app.config, "SNORT_PROFILE", "")
    assert engine.discover()["status"] == "missing_configuration"
    engine.cached = None
    monkeypatch.setitem(app.config, "SNORT_PROFILE", str(tmp_path / "snort.lua"))
    monkeypatch.setitem(app.config, "SNORT_RUNNER", "")
    assert engine.discover()["status"] == "missing_isolation"
    assert (
        post(
            client,
            "/tools/snort-rule-builder/draft",
            source_json=json.dumps("x" * 100001),
        ).status_code
        == 400
    )
    with app.app_context():
        user = (
            db()
            .execute("SELECT user_uuid FROM users WHERE id=?", (client.uid,))
            .fetchone()[0]
        )
    for source in ("include /etc/passwd\n" + RULE, RULE + "\nips = { }"):
        with pytest.raises(ValueError):
            engine.submit(user, source, [])


def test_job_upload_validation_output_safety_and_ownership(
    client, monkeypatch, tmp_path
):
    engine = fake_engine(client, monkeypatch, tmp_path)
    assert engine.discover()["available"]
    for raw in (b"not a capture" * 4, b"x" * 1025):
        result = post(
            client,
            "/tools/snort-rule-builder/jobs",
            kind="pcap",
            source_json=json.dumps(RULE),
            target=(io.BytesIO(raw), "looks-valid.pcap"),
        )
        assert result.status_code == 400
    with app.app_context():
        user = (
            db()
            .execute("SELECT user_uuid FROM users WHERE id=?", (client.uid,))
            .fetchone()[0]
        )
    job = engine.submit("another-user", RULE, [])
    wait(engine, job["id"])
    assert client.get("/tools/snort-rule-builder/jobs/" + job["id"]).status_code == 404
    runner = tmp_path / "runner"
    runner.write_text(
        "#!"
        + sys.executable
        + '\nimport sys,pathlib\nif "-r" in sys.argv:(pathlib.Path(sys.argv[3])/"alert_json.txt").symlink_to("/etc/passwd")\n'
    )
    runner.chmod(0o700)
    job = engine.submit(user, RULE, [("target", b"")])
    state = wait(engine, job["id"])
    assert (
        state["status"] == "failed" and not (engine.root / job["id"] / "work").exists()
    )
    runner.write_text("#!" + sys.executable + '\nprint("x"*200000)\n')
    runner.chmod(0o700)
    job = engine.submit(user, RULE, [])
    state = wait(engine, job["id"])
    assert state["status"] == "failed"
    assert "validation" in state, state.get("error")
    assert state["validation"]["reason"] == "output_limit"
    assert len(state["validation"]["stdout"].encode()) <= 65536


def test_lossless_source_model_regressions():
    import subprocess
    import shutil

    if not shutil.which("node"):
        pytest.skip("Node.js is required for source-model tests.")
    subprocess.run(
        ["node", "tests/browser/snort-model.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )


def upload(client, name, raw):
    return client.post(
        f"/cases/{client.cid}/upload",
        data={
            "csrf": "snort-token",
            "ajax": "1",
            "category": "signatures",
            "file": (io.BytesIO(raw), name),
        },
    )


def open_document(client, name):
    result = client.get(
        f"/cases/{client.cid}/snort-signature", query_string={"path": name}
    )
    assert result.status_code == 200, result.data
    return result.json["document"]


def replace_rule(client, name, info, rule, text):
    return post(
        client,
        f"/cases/{client.cid}/snort-rule",
        operation="replace",
        filename=name,
        version=info["version"],
        start=str(rule["start"]),
        end=str(rule["end"]),
        source_json=json.dumps(text),
    )


@pytest.mark.parametrize(
    "separator", ["\n\n", " ", "\r\n# between\ninclude local.rules\r\n"]
)
def test_multirule_byte_exact_selected_replacement_and_repeated_saves(
    client, separator
):
    first = RULE.replace("Harmless", "first").replace("; ", ";\r\n ")
    middle = RULE.replace("Harmless", "middle")  # duplicate SID is intentional
    last = 'alert http (content:"last|3B|";)'
    raw = (
        "\ufeff# shared\r\n# "
        + RULE
        + "\n"
        + first
        + separator
        + middle
        + separator
        + last
        + "\r\n# final\n"
    ).encode()
    assert upload(client, "many.RULES", raw).status_code == 200
    info = open_document(client, "many.RULES")
    assert info["count"] == 3 and info["disabled"] == 1
    assert (
        info["rules"][0]["sid"] == info["rules"][1]["sid"]
        and not info["rules"][2]["sid"]
    )
    rule = info["rules"][1]
    old_start, old_end = rule["start"], rule["end"]
    new = (
        rule["source"]
        .replace("Harmless", "unused")
        .replace("middle", "a much longer title")
        .replace("sid:1000001", "sid:999")
    )
    result = replace_rule(client, "many.RULES", info, rule, new)
    assert result.status_code == 200, result.data
    with app.app_context():
        file = ensure_package(client.cid) / "signatures/many.RULES"
        saved = file.read_bytes()
    assert saved == raw[:old_start] + new.encode() + raw[old_end:]
    updated = result.json["document"]
    selection = result.json["selected"]
    assert selection["position"] == 2 and selection["sid"] == "999"
    shorter = new.replace("a much longer title", "x")
    again = replace_rule(client, "many.RULES", updated, selection, shorter)
    assert again.status_code == 200
    assert file.read_bytes() == raw[:old_start] + shorter.encode() + raw[old_end:]
    assert len(list(file.parent.glob("many*"))) == 1


def test_multiline_quotes_comments_directives_and_disabled_blocks():
    a = 'alert tcp any any -> any 80 (\nmsg:"semi; paren( escaped\\")"; content:"|41 42|";\nsid:1;)'
    raw = ("#begin\n" + RULE + "\n#end\n" + a + " include other.rules\n" + a).encode()
    info = document(raw)
    assert info["count"] == 2 and info["disabled"] == 1 and len(info["directives"]) == 1
    assert info["rules"][0]["source"] == a
    assert document(b"config multiline {\n" + RULE.encode() + b"\n}")["reason"]
    assert document(("# " + RULE).encode())["count"] == 0


def test_selected_save_rejects_stale_ranges_invalid_and_multirule_editor(client):
    raw = (RULE + "\n" + RULE).encode()
    upload(client, "file.rules", raw)
    info = open_document(client, "file.rules")
    selected = info["rules"][1]
    for text in (
        RULE[:-1],
        RULE + RULE,
        "include x.rules\n" + RULE,
        "# adjacent\n" + RULE,
    ):
        assert (
            replace_rule(client, "file.rules", info, selected, text).status_code == 400
        )
    tampered = {**selected, "start": 0}
    assert replace_rule(client, "file.rules", info, tampered, RULE).status_code == 400
    with app.app_context():
        file = ensure_package(client.cid) / "signatures/file.rules"
        assert file.read_bytes() == raw
        file.write_bytes(raw + b"\n# changed")
    stale = replace_rule(client, "file.rules", info, selected, RULE)
    assert stale.status_code == 409 and stale.json["conflict"]
    assert file.read_bytes() == raw + b"\n# changed"
    assert (
        post(
            client, f"/cases/{client.cid}/snort-signatures/normalize", path="file.rules"
        ).status_code
        == 410
    )
    assert file.read_bytes() == raw + b"\n# changed"


def test_uploads_preserve_file_and_save_as_selected_only(client):
    import hashlib

    raw = ("include config.rules\r\n" + RULE + RULE).encode()
    r = upload(client, "original.rules", raw)
    assert r.json["paths"] == ["signatures/original.rules"]
    with app.app_context():
        file = ensure_package(client.cid) / "signatures/original.rules"
        assert file.read_bytes() == raw
        run(
            "INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created) VALUES(?,?,?,?,?)",
            (
                client.uid,
                "test",
                hashlib.sha256(b"snort-api").hexdigest(),
                "snort",
                "2026",
            ),
        )
    response = client.post(
        f"/api/v1/cases/{client.cid}/assets",
        headers={"Authorization": "Bearer snort-api"},
        data={"category": "signatures", "file": (io.BytesIO(raw), "api.rules")},
    )
    assert response.status_code == 201 and response.json["files"] == [
        "signatures/api.rules"
    ]
    info = open_document(client, "original.rules")
    selected = info["rules"][1]
    copied = post(
        client,
        f"/cases/{client.cid}/snort-rule",
        filename="copy.rules",
        source_json=json.dumps(selected["source"]),
    )
    assert copied.status_code == 200
    assert file.read_bytes() == raw
    assert upload(client, "original.rules", b"other").status_code == 409
    with app.app_context():
        assert (file.parent / "copy.rules").read_text() == RULE and (
            file.parent / "api.rules"
        ).read_bytes() == raw


def test_case_permissions_paths_and_metadata_rollback(client):
    import sqlite3

    upload(client, "nested/original.rules".replace("/", "-"), RULE.encode())
    with app.app_context():
        package = ensure_package(client.cid)
        persist(package, "nested/file.rules", RULE.encode(), db(), client.cid)
        file = package / "signatures/nested/file.rules"
        (file.parent / "link.rules").symlink_to(file)
        db().execute(
            "CREATE TEMP TRIGGER fail_metadata BEFORE INSERT ON artifacts BEGIN SELECT RAISE(ABORT,'metadata failed'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            persist(
                package,
                "nested/file.rules",
                b"changed",
                db(),
                client.cid,
                expected=version(RULE.encode()),
            )
        assert file.read_bytes() == RULE.encode()
        db().execute("DROP TRIGGER fail_metadata")
    for path in (
        "../outside.rules",
        "/tmp/x.rules",
        "nested/../../x.rules",
        "nested/link.rules",
    ):
        assert (
            client.get(
                f"/cases/{client.cid}/snort-signature", query_string={"path": path}
            ).status_code
            == 400
        )
    info = open_document(client, "nested/file.rules")
    with app.app_context():
        run("UPDATE cases SET stage=3 WHERE id=?", (client.cid,))
    assert (
        replace_rule(
            client, "nested/file.rules", info, info["rules"][0], RULE
        ).status_code
        == 409
    )
    with app.app_context():
        run(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission='cases:assets'"
        )
    assert client.get(f"/cases/{client.cid}/snort-signatures").status_code == 403


def test_save_as_cannot_replace_original_selected_file(client):
    raw = (RULE + "\n" + RULE).encode()
    upload(client, "original.rules", raw)
    response = post(
        client,
        f"/cases/{client.cid}/snort-rule",
        filename="original.rules",
        origin_cid=str(client.cid),
        origin_path="original.rules",
        version=version(raw),
        source_json=json.dumps(RULE),
    )
    assert (
        response.status_code == 400 and "separate destination" in response.json["error"]
    )
    with app.app_context():
        assert (
            ensure_package(client.cid) / "signatures/original.rules"
        ).read_bytes() == raw


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_comment_aware_multiline_boundaries_and_metadata(newline):
    text = (Path(__file__).parent / "fixtures/snort/lexical-multiple.rules").read_text()
    raw = ("\ufeff" + text.replace("\n", newline)).encode()
    info = document(raw, "lexical.rules")
    assert not info["reason"], info
    assert info["count"] == 3
    assert len(info["directives"]) == 1
    assert [r["sid"] for r in info["rules"]] == ["7", "7", ""]
    assert info["rules"][1]["message"] == "second"
    for rule in info["rules"]:
        assert raw[rule["start"]:rule["end"]].decode() == rule["source"]
        assert rule["line_end"] >= rule["line_start"]


def test_reported_file_is_malformed_not_a_multirule_split_failure():
    raw = (Path(__file__).parent / "fixtures/snort/reported-malformed-multiple.rules").read_bytes()
    info = document(raw, "multiple.rules")
    error = info["diagnostics"][0]
    assert info["count"] == 0
    assert error["filename"] == "multiple.rules" and error["line"] == 1
    assert "Typographic quote" in error["reason"] and "msg:”" in error["excerpt"]
    # Isolate the second supplied rule: pcre has a closing quote but no opening quote.
    second = raw.decode().split('\nalert http ', 1)[1]
    second = 'alert http ' + second
    error = document(second.encode())["diagnostics"][0]
    assert "missing ASCII opening quote" in error["reason"]
    assert error["line"] == 4
    # Explicit test-only repair proves the report is not caused by rule count.
    # Production code and the original uploaded file never perform this rewrite.
    repaired = raw.decode().translate(str.maketrans({'“':'"', '”':'"'})).replace('pcre:/', 'pcre:"/')
    repaired_info = document(repaired.encode())
    assert repaired_info['count'] == 2 and not repaired_info['reason']


@pytest.mark.parametrize("suffix,reason", [
    ('alert tcp any any -> any 80 (msg:"unterminated)', "Unterminated quoted"),
    ('alert tcp any any -> any 80 (content:(oops);)', "Unexpected opening"),
    ('alert tcp any any -> any 80 (sid:2)', "Missing option semicolon"),
    ('/* unclosed (', "Unterminated block comment"),
    ('var NAME value /* comment\n' + RULE + '\n*/', 'Block comment crossing a directive'),
    ('include "unclosed\n' + RULE, 'Unterminated quoted directive'),
    ('config lua {\n' + RULE + '\n}', "Unsupported or multiline directive"),
])
def test_safe_prefix_survives_uncertain_suffix(suffix, reason):
    info = document((RULE + '\n' + suffix).encode(), 'broken.rules')
    assert info["count"] == 1 and info["rules"][0]["source"] == RULE
    assert reason in info["diagnostics"][0]["reason"]
    assert '1 safely recognized' in info["reason"]
    assert info["diagnostics"][0]["line"] >= 2


def test_partial_file_selected_save_preserves_unverified_suffix(client):
    raw = (RULE + '\n/* (fake rule) */\n' + RULE + '\nalert tcp any any -> any 80 (msg:"broken').encode()
    upload(client, 'partial.rules', raw)
    info = open_document(client, 'partial.rules')
    assert info['count'] == 2 and info['reason']
    original = info['rules'][1]
    replacement = original['source']
    for title in ['a longer title 🦀', 'x', 'another title']:
        replacement = RULE.replace('Harmless', title)
        result = replace_rule(client, 'partial.rules', info, info['rules'][1], replacement)
        assert result.status_code == 200, result.data
        with app.app_context():
            saved = (ensure_package(client.cid) / 'signatures/partial.rules').read_bytes()
        assert saved == raw[:original['start']] + replacement.encode() + raw[original['end']:]
        info = result.json['document']
        assert info['count'] == 2 and info['diagnostics'][0]['reason'].startswith('Unterminated quoted')
