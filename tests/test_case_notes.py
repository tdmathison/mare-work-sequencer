import io
import json
import uuid
import zipfile
from app import app, db, run
from test_tagging import fixture
from test_api import make_user
from sync_helpers import apply_preview, other_destination
from case_notes import initialize, listing, mutate


def post(client, cid, value, nid=None):
    return client.post(
        f"/case-notebook/{cid}" + (f"/{nid}" if nid else ""),
        data={"csrf": "tag-test", "payload": json.dumps(value)},
    )


def test_notebook_crud_search_ownership_and_closed():
    client, cid, uid = fixture()
    page = client.get(f"/cases/{cid}").text
    assert (
        page.index('id="tab-workbench"')
        < page.index('id="tab-notes"')
        < page.index('id="tab-tasks"')
    )
    assert "Reverse engineering notes</h2>" not in page
    assert page.index('id="panel-notes"') < page.index('id="panel-tasks"')
    assert post(client, cid, {"body": " \n "}).status_code == 400
    assert post(client, cid, {"body": "x", "note_type": "system"}).status_code == 400
    key = uuid.uuid4().hex
    value = {
        "body": "# Finding\n\n**Safe** <script>alert(1)</script> [x](javascript:alert(1))",
        "request_id": key,
    }
    created = post(client, cid, value)
    assert created.status_code == 200, created.text
    note = created.json["note"]
    nid = note["id"]
    assert "<script>" not in note["html"] and 'href="javascript:' not in note["html"]
    assert (
        note["author"] == "tag-user"
        and note["note_type"] == "user"
        and note["note_uuid"]
    )
    assert post(client, cid, value).json["note"]["id"] == nid
    assert post(client, cid, dict(value, body="changed")).status_code == 409
    result = client.get(
        f"/case-notebook/{cid}?q=finding&type=user&order=oldest&limit=1"
    ).json
    assert (
        result["total"] == 1
        and result["counts"]["user"] == 1
        and len(result["notes"]) == 1
    )
    assert post(client, cid, {"body": "Edited Markdown"}, nid).json["note"]["edited"]
    other, headers = make_user("other-note-editor", "User")
    api = app.test_client()
    assert (
        api.patch(
            f"/api/v1/cases/{cid}/notes/{nid}",
            json={"body": "impersonation"},
            headers=headers,
        ).status_code
        == 403
    )
    with app.app_context():
        run("UPDATE cases SET stage=3 WHERE id=?", (cid,))
    assert client.get(f"/case-notebook/{cid}").json["editable"] is False
    assert post(client, cid, {"body": "late composer"}).status_code == 409
    assert post(client, cid, {"operation": "delete"}, nid).status_code == 409
    with app.app_context():
        run("UPDATE cases SET stage=1 WHERE id=?", (cid,))
    assert post(client, cid, {"operation": "delete"}, nid).status_code == 200
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT count(*) FROM audit WHERE action LIKE ?", (f"%note {nid}%",)
            )
            .fetchone()[0]
            == 3
        )


def test_legacy_migration_preserves_text_and_is_idempotent():
    client, cid, uid = fixture()
    original = "  legacy **Markdown**\n\n```python\nx = 1\n```\n"
    with app.app_context():
        run(
            "INSERT INTO notes(case_id,body,author,created) VALUES(?,?,?,?)",
            (cid, original, "former-user", ""),
        )
        initialize(db())
        initialize(db())
        n = dict(db().execute("SELECT * FROM notes WHERE case_id=?", (cid,)).fetchone())
        assert (
            n["body"] == original
            and n["created"] == ""
            and n["author"] == "former-user"
            and n["author_uuid"] == ""
        )
        assert (
            n["source_id"] == "legacy-reverse-engineering" and n["note_type"] == "user"
        )
        assert (
            db()
            .execute("SELECT count(*) FROM notes WHERE case_id=?", (cid,))
            .fetchone()[0]
            == 1
        )


def test_activity_success_noops_bulk_and_rollback():
    client, cid, uid = fixture()
    client.get(f"/cases/{cid}")

    def events():
        return client.get(f"/case-notebook/{cid}?type=system").json["notes"]

    assert events() == []
    # One entry for a successful bulk indicator operation, not one per row.
    r = client.post(
        f"/cases/{cid}/indicators",
        data={
            "csrf": "tag-test",
            "rows": json.dumps(
                [["domain", "a.example", ""], ["domain", "b.example", ""]]
            ),
            "revision": "0",
        },
    )
    assert r.status_code == 200
    e = events()
    assert (
        len(e) == 1
        and e[0]["event_type"] == "content.indicators.added"
        and e[0]["event_metadata"]["count"] == 2
    )
    assert post(client, cid, {"body": "not allowed"}, e[0]["id"]).status_code == 403
    assert (
        client.post(
            f"/cases/{cid}/indicators",
            data={"csrf": "tag-test", "rows": "[]", "revision": "0"},
        ).status_code
        == 409
    )
    assert len(events()) == 1
    # Revision-aware identical save has no additional activity.
    current = client.get(f"/cases/{cid}/indicators").json
    assert (
        client.post(
            f"/cases/{cid}/indicators",
            data={
                "csrf": "tag-test",
                "rows": json.dumps(current["rows"]),
                "revision": str(current["revision"]),
            },
        ).status_code
        == 200
    )
    assert len(events()) == 1
    asset = client.post(
        f"/cases/{cid}/upload",
        data={
            "csrf": "tag-test",
            "category": "supporting",
            "file": (io.BytesIO(b"content"), "evidence.txt"),
        },
    )
    assert asset.status_code in (200, 302)
    assert any(n["event_type"] == "asset.attached" for n in events())


def test_raw_notes_roundtrip_and_no_activity_replay():
    client, cid, uid = fixture("Administrator")
    client.get(f"/cases/{cid}")
    post(client, cid, {"body": "Private raw note"})
    exported = client.post(f"/cases/{cid}/backup", data={"csrf": "tag-test"})
    assert exported.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(exported.data))
    meta = json.loads(
        archive.read(
            next(n for n in archive.namelist() if n.endswith("/case-data.json"))
        )
    )
    expected = meta["records"]["notes"]
    assert expected[0]["body"] == "Private raw note"
    other_destination()
    response = client.post(
        "/import-export/import-raw",
        data={"csrf": "tag-test", "backup": (io.BytesIO(exported.data), "notes.zip")},
    )
    response = apply_preview(client, response, "tag-test")
    assert response.status_code == 302, response.text
    with app.app_context():
        target = db().execute("SELECT max(id) FROM cases").fetchone()[0]
        actual = [
            dict(r)
            for r in db().execute("SELECT * FROM notes WHERE case_id=?", (target,))
        ]
        assert [(n["body"], n["note_uuid"], n["created"]) for n in actual] == [
            (n["body"], n["note_uuid"], n["created"]) for n in expected
        ]
    assert client.get(f"/case-notebook/{target}?type=system").json["notes"] == []


def test_sdk_lifecycle_filters_pagination_and_permission_changes():
    import httpx
    from mws_sdk import MWSClient
    from mws_sdk.exceptions import MWSError
    from test_api import new_case, start_case

    uid, h = make_user("notebook-sdk")
    flask = app.test_client()

    def bridge(request):
        response = flask.open(
            request.url.raw_path.decode(),
            method=request.method,
            headers=dict(request.headers),
            data=request.content,
        )
        return httpx.Response(
            response.status_code, headers=dict(response.headers), content=response.data
        )

    with MWSClient(
        "https://mws.test",
        h["Authorization"].split()[1],
        transport=httpx.MockTransport(bridge),
    ) as sdk:
        cid = new_case(flask, h)
        start_case(flask, h, cid, uid)
        system = sdk.notes.list(
            cid, params={"type": "system", "order": "oldest", "limit": 1}
        )
        assert system.total == 3 and system.notes[0].event_type == "case.created"
        note = sdk.notes.create(
            cid, data={"body": "SDK private note", "request_id": uuid.uuid4().hex}
        ).note
        assert sdk.notes.get(cid, note.id).note.note_uuid == note.note_uuid
        assert sdk.notes.update(cid, note.id, data={"body": "SDK edited"}).note.edited
        assert (
            sdk.notes.list(cid, params={"q": "SDK edited", "type": "user"}).total == 1
        )
        with app.app_context():
            run("UPDATE cases SET stage=3 WHERE id=?", (cid,))
        import pytest

        with pytest.raises(MWSError):
            sdk.notes.create(cid, data={"body": "Closed SDK"})
        with pytest.raises(MWSError):
            sdk.notes.delete(cid, note.id)
        assert sdk.notes.get(cid, note.id).note.body == "SDK edited"
        assert flask.post(f"/api/v1/cases/{cid}/reopen", headers=h).status_code == 200
        assert (
            sdk.notes.list(cid, params={"type": "system"}).notes[0].event_type
            == "case.stage_changed"
        )
        sdk.notes.delete(cid, note.id)
    # Existing role permissions are checked on every request, not cached.
    other, headers = make_user("notebook-no-rights", "User")
    with app.app_context():
        run(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission IN ('cases:read','cases:update')"
        )
    assert flask.get(f"/api/v1/cases/{cid}/notes", headers=headers).status_code == 403
    assert (
        flask.post(
            f"/api/v1/cases/{cid}/notes", headers=headers, json={"body": "denied"}
        ).status_code
        == 403
    )


def test_collection_activity_replay_and_removed_history():
    client, cid, uid = fixture("Administrator")
    client.get(f"/cases/{cid}")
    with app.app_context():
        collection = (
            db()
            .execute("SELECT id,revision,tasks FROM task_collections LIMIT 1")
            .fetchone()
        )
        data = {
            "request_key": "case-note-collection-retry",
            "revision": collection["revision"],
            "template_ids": [json.loads(collection["tasks"])[0]["id"]],
        }
        collection_id = collection["id"]
    path = f"/task-workspace/cases/{cid}/collections/{collection_id}/apply"
    payload = {"csrf": "tag-test", "payload": json.dumps(data)}
    first = client.post(path, data=payload)
    assert first.status_code == 201, first.text
    assert client.post(path, data=payload).status_code in (200, 201)
    notes = client.get(f"/case-notebook/{cid}?type=system").json["notes"]
    assert len(notes) == 1 and notes[0]["event_type"] == "tasks.collection_added"
    removed = client.post(
        f"/task-workspace/cases/{cid}/groups/{first.json['group_id']}/delete",
        data={"csrf": "tag-test", "payload": json.dumps({"confirm": True})},
    )
    assert removed.status_code == 200
    notes = client.get(f"/case-notebook/{cid}?type=system").json["notes"]
    assert len(notes) == 2 and notes[0]["event_type"] == "tasks.collection_removed"


def test_system_history_merge_and_standard_export_privacy():
    from case_notes import activity
    from app import build_archive

    client, cid, uid = fixture("Administrator")
    client.get(f"/cases/{cid}")
    post(client, cid, {"body": "INTERNAL_NOTE_SECRET"})
    with app.app_context():
        activity(
            db(),
            cid,
            "asset.attached",
            "Historical activity",
            {"count": 1},
            "one-event",
        )
        activity(
            db(),
            cid,
            "asset.attached",
            "Historical activity",
            {"count": 1},
            "one-event",
        )
        db().commit()
        assert (
            db()
            .execute("SELECT count(*) FROM notes WHERE note_type='system'")
            .fetchone()[0]
            == 1
        )
        out, name = build_archive(cid, "standard")
        archive = zipfile.ZipFile(out)
        bodies = b"\n".join(archive.read(n) for n in archive.namelist())
        assert (
            b"INTERNAL_NOTE_SECRET" not in bodies
            and b"Historical activity" not in bodies
        )
        out.close()
    exported = client.post(f"/cases/{cid}/backup", data={"csrf": "tag-test"}).data
    with app.app_context():
        # Removing only supplemental history must not make Case content diverge.
        db().execute("DELETE FROM notes WHERE note_type='system'")
        db().commit()
    for _ in range(2):
        response = client.post(
            "/import-export/import-raw",
            data={"csrf": "tag-test", "backup": (io.BytesIO(exported), "history.zip")},
        )
        assert apply_preview(client, response, "tag-test").status_code == 302
    with app.app_context():
        assert (
            db()
            .execute("SELECT count(*) FROM notes WHERE note_type='system'")
            .fetchone()[0]
            == 1
        )
    assert (
        client.get(f"/case-notebook/{cid}?type=system")
        .json["notes"][0]["activity_link"]["href"]
        .endswith("tab=package")
    )


def test_preview_stays_available_when_closed_and_rejects_unsafe_markdown():
    client, cid, uid = fixture()
    with app.app_context():
        run("UPDATE cases SET stage=3 WHERE id=?", (cid,))
    response = client.post(
        f"/case-notebook/{cid}/preview",
        data={
            "csrf": "tag-test",
            "text": '<script>x</script>\n\n![secret](file:///etc/passwd) [x](javascript:alert(1))\n\n```python\nprint("inert")\n```',
        },
    )
    assert response.status_code == 200
    html = response.json["html"]
    assert (
        "<script>" not in html
        and 'href="javascript:' not in html
        and "<img" not in html
        and "inert" in html
    )


def test_timestamp_offset_order_and_empty_legacy_records():
    client, cid, uid = fixture()
    first = post(client, cid, {"body": "Earlier instant"}).json["note"]["id"]
    later = post(client, cid, {"body": "Later instant"}).json["note"]["id"]
    with app.app_context():
        db().execute(
            "UPDATE notes SET created=? WHERE id=?",
            ("2026-11-01T01:00:00+02:00", first),
        )
        db().execute(
            "UPDATE notes SET created=? WHERE id=?", ("2026-10-31T23:30:00Z", later)
        )
        db().execute(
            "INSERT INTO notes(case_id,body,created) VALUES(?,?,?)", (cid, " \n\t", "")
        )
        db().commit()
    result = client.get(f"/case-notebook/{cid}?order=newest&limit=1").json
    assert result["total"] == 2 and result["notes"][0]["id"] == later
    assert (
        client.get(f"/case-notebook/{cid}?order=newest&limit=1&offset=1").json["notes"][
            0
        ]["id"]
        == first
    )


def test_signature_activity_removal_and_authorized_links():
    client, cid, uid = fixture()
    response = client.post(
        f"/cases/{cid}/upload",
        data={
            "csrf": "tag-test",
            "category": "signatures",
            "file": (
                io.BytesIO(b"alert tcp any any -> any any (sid:1;)"),
                "notebook.rules",
            ),
        },
    )
    assert response.status_code in (200, 302)
    notes = client.get(f"/case-notebook/{cid}?type=system").json["notes"]
    event = next(n for n in notes if n["event_type"] == "content.snort.added")
    assert event["event_metadata"]["count"] == 1 and event["activity_link"][
        "href"
    ].endswith("tab=package")
    with app.app_context():
        path = (
            db()
            .execute(
                "SELECT path FROM artifacts WHERE case_id=? AND path LIKE '%notebook.rules'",
                (cid,),
            )
            .fetchone()[0]
        )
    assert (
        client.post(
            f"/cases/{cid}/assets/delete", data={"csrf": "tag-test", "path": path}
        ).status_code
        == 200
    )
    notes = client.get(f"/case-notebook/{cid}?type=system").json["notes"]
    assert any(n["event_type"] == "content.snort.removed" for n in notes)
    with app.app_context():
        run(
            "DELETE FROM role_permissions WHERE role_name='User' AND permission='cases:assets'"
        )
    assert all(
        n["activity_link"] is None
        for n in client.get(f"/case-notebook/{cid}?type=system").json["notes"]
    )
