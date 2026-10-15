import copy
import hashlib
import io
import json
import tempfile
import uuid
import zipfile

import pytest
from werkzeug.datastructures import FileStorage
from app import app, db, run, ROOT, package, backup_helpers
from case_sync import fingerprint, logical_snapshot, validate_graph
from test_backups import setup_backup_case


def preview(client, blob, full=False):
    response = client.post(
        "/import-export/import" if full else "/import-export/import-raw",
        data={"csrf": "backup-token", "backup": (io.BytesIO(blob), "exchange.zip")},
    )
    assert response.status_code == 302, response.data
    operation = response.location.rsplit("/", 1)[-1]
    with app.app_context():
        row = (
            db()
            .execute("SELECT * FROM sync_imports WHERE id=?", (operation,))
            .fetchone()
        )
        return operation, json.loads(row["plan"])


def apply(client, operation, decisions=None):
    response = client.post(
        "/import-export/apply/" + operation,
        data={"csrf": "backup-token", **(decisions or {})},
    )
    assert response.status_code == 302, response.data
    with app.app_context():
        return json.loads(
            db()
            .execute("SELECT outcomes FROM sync_imports WHERE id=?", (operation,))
            .fetchone()[0]
        )


def head(cid):
    with app.app_context():
        return app.extensions["case_sync"].reconcile(cid)["revision_uuid"]


def incoming(blob, title, foreign=False, parents=None):
    with zipfile.ZipFile(io.BytesIO(blob)) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    meta_path = next(name for name in contents if name.endswith("/case-data.json"))
    manifest_path = next(name for name in contents if name.endswith("/manifest.json"))
    meta = json.loads(contents[meta_path])
    meta["case"]["name"] = title
    if foreign:
        meta["sync"]["case_uuid"] = str(uuid.uuid4())
        meta["sync"]["revisions"] = []

    def write():
        contents[meta_path] = json.dumps(meta).encode()
        manifest = json.loads(contents[manifest_path])
        item = next(row for row in manifest["files"] if row["path"] == "case-data.json")
        item.update(
            sha256=hashlib.sha256(contents[meta_path]).hexdigest(),
            size=len(contents[meta_path]),
        )
        contents[manifest_path] = json.dumps(manifest).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for name, data in contents.items():
                target.writestr(name, data)
        return output.getvalue()

    # Validation stages physical filenames before computing the authoritative hash.
    with app.app_context(), tempfile.TemporaryDirectory(dir=ROOT) as directory:
        plans, _ = backup_helpers["stage_upload"](
            FileStorage(io.BytesIO(write()), filename="x.zip"), True, directory
        )
        folder, validated, _ = plans[0]
        content_hash = fingerprint(logical_snapshot(validated, folder / "mip"))
    key = str(uuid.uuid4())
    old = meta["sync"]["revision_uuid"]
    node = {
        "uuid": key,
        "parents": [] if foreign else (parents if parents is not None else [old]),
        "fingerprint": content_hash,
        "created": "2026-01-01T00:00:00+00:00",
        "installation": meta["sync"]["exporter_uuid"],
    }
    meta["sync"]["revisions"].append(node)
    meta["sync"]["revision_uuid"] = key
    return write(), key


def test_same_backup_and_full_reimport_do_not_duplicate():
    client, cid, uid, post = setup_backup_case()
    blob = post(f"/cases/{cid}/backup").data
    revision = head(cid)
    for _ in range(2):
        operation, plan = preview(client, blob)
        assert plan["items"][0]["preview"]["classification"] == "unchanged"
        assert apply(client, operation)[0]["action"] == "Unchanged"
    full = post("/import-export/export").data
    operation, plan = preview(client, full, True)
    assert all(
        item["preview"]["classification"] == "unchanged" for item in plan["items"]
    )
    apply(client, operation)
    with app.app_context():
        assert db().execute("SELECT count(*) FROM cases").fetchone()[0] == 2
    assert head(cid) == revision


def test_descendant_update_then_ancestor_skip_and_recovery():
    client, cid, uid, post = setup_backup_case()
    base = post(f"/cases/{cid}/backup").data
    newer, revision = incoming(base, "Incoming descendant")
    operation, plan = preview(client, newer)
    assert plan["items"][0]["preview"]["classification"] == "update"
    outcome = apply(client, operation)[0]
    assert outcome["action"] == "Updated existing", outcome
    assert outcome["recovery"]
    assert head(cid) == revision
    with app.app_context():
        current = db().execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        assert (
            current["name"] == "Incoming descendant"
            and current["number"] == "SOURCE-01"
            and current["creator"] == uid
        )
        assert (
            ROOT / "sync-recovery" / outcome["recovery"] / "case/mip/scripts/decode.py"
        ).read_text() == "print(42)"
    operation, plan = preview(client, base)
    assert plan["items"][0]["preview"]["classification"] == "older"
    assert apply(client, operation)[0]["action"] == "Skipped older"


def test_divergence_explicit_replacement_and_two_parent_resolution():
    client, cid, uid, post = setup_backup_case()
    base = post(f"/cases/{cid}/backup").data
    branch, remote = incoming(base, "Remote branch")
    assert (
        post(
            f"/cases/{cid}",
            name="Local branch",
            description="local edit",
            owner_id=str(uid),
        ).status_code
        == 302
    )
    local = head(cid)
    operation, plan = preview(client, branch)
    assert plan["items"][0]["preview"]["classification"] == "conflict"
    assert apply(client, operation)[0]["action"] == "Conflict unresolved"
    outcome = apply(client, operation, {"decision-0": "replace"})[0]
    assert outcome["action"] == "Replaced by explicit decision", outcome
    with app.app_context():
        state = app.extensions["case_sync"].reconcile(cid)
        nodes = app.extensions["case_sync"].graph(state["case_uuid"])
        assert set(nodes[state["revision_uuid"]]["parents"]) == {local, remote}
    operation, plan = preview(client, branch)
    assert plan["items"][0]["preview"]["classification"] == "unchanged"


def test_new_identity_numbering_and_stale_preview():
    client, cid, uid, post = setup_backup_case()
    base = post(f"/cases/{cid}/backup").data
    foreign, revision = incoming(base, "Different case", foreign=True)
    operation, plan = preview(client, foreign)
    assert plan["items"][0]["preview"]["classification"] == "new"
    outcome = apply(client, operation)[0]
    assert outcome["action"] == "Imported new", outcome
    with app.app_context():
        restored = (
            db()
            .execute(
                "SELECT * FROM cases WHERE number=?", (outcome["destination_number"],)
            )
            .fetchone()
        )
        assert restored["number"].startswith("MARE-") and restored["creator"] == uid
    operation, plan = preview(client, foreign)
    assert plan["items"][0]["preview"]["classification"] == "unchanged"
    branch, _ = incoming(base, "Pending remote")
    operation, plan = preview(client, branch)
    post(
        f"/cases/{cid}",
        name="Edited after preview",
        description="changed",
        owner_id=str(uid),
    )
    outcome = apply(client, operation)[0]
    assert outcome["action"] == "Failed and rolled back"
    assert "changed after preview" in outcome["reason"]


def test_no_op_exports_autosaves_and_external_file_detection():
    client, cid, uid, post = setup_backup_case()
    post(f"/cases/{cid}/backup")
    original = head(cid)
    post(f"/cases/{cid}/backup")
    assert head(cid) == original
    # Existing file editor uses the same centralized transaction/revision boundary.
    post(f"/cases/{cid}/file", path="scripts/decode.py", content="print(42)")
    assert head(cid) == original
    post(f"/cases/{cid}/file", path="scripts/decode.py", content="print(43)")
    changed = head(cid)
    assert changed != original
    with app.app_context():
        (package(cid) / "scripts/decode.py").write_text("print(44)")
    post(f"/cases/{cid}/backup")
    assert head(cid) != changed


def test_recompute_fingerprint_and_expiration_access():
    client, cid, uid, post = setup_backup_case()
    base = post(f"/cases/{cid}/backup").data
    branch, _ = incoming(base, "Foreign", foreign=True)
    operation, plan = preview(client, branch)
    with app.app_context():
        db().execute("UPDATE sync_imports SET created=0 WHERE id=?", (operation,))
        db().commit()
    assert client.get("/import-export/review/" + operation).status_code == 410
    assert client.post("/import-export/apply/" + operation, data={}).status_code == 403
    other = app.test_client()
    assert other.get("/import-export/review/" + operation).status_code == 302
    with zipfile.ZipFile(io.BytesIO(base)) as archive:
        meta = json.loads(
            archive.read(
                next(
                    name
                    for name in archive.namelist()
                    if name.endswith("/case-data.json")
                )
            )
        )
    sync = meta["sync"]
    computed = sync["revisions"][-1]["fingerprint"]
    bad = copy.deepcopy(sync)
    bad["revisions"][-1]["parents"] = [bad["revision_uuid"]]
    with pytest.raises(ValueError, match="Cyclic"):
        validate_graph(bad, computed)
    with pytest.raises(ValueError, match="fingerprint"):
        validate_graph(sync, "0" * 64)
