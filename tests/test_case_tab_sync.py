"""Saved checklist content follows the same task state as completion/export gates."""

import pytest
from app import app, completion_items, db, review_issues
from test_task_collections import setup, create, application


def advisories(cid):
    with app.test_request_context():
        return [
            item["message"] for item in completion_items(cid) if item.get("advisory")
        ]


def test_saved_checklist_tracks_task_creation_status_and_last_deletion():
    client, headers, cid, _ = setup()
    base = f"/api/v1/cases/{cid}/tasks"
    with app.app_context():
        baseline = review_issues(cid)
    assert advisories(cid) == []
    ids = []
    for title in ("First saved task", "Second saved task"):
        response = client.post(base, headers=headers, json={"title": title})
        assert response.status_code == 201
        ids.append(response.json["task"]["id"])
    assert len(advisories(cid)) == 2
    assert (
        client.patch(
            f"{base}/{ids[0]}", headers=headers, json={"state": "Completed"}
        ).status_code
        == 200
    )
    assert len(advisories(cid)) == 1 and "Second saved task" in advisories(cid)[0]
    assert client.delete(f"{base}/{ids[1]}", headers=headers).status_code == 204
    assert advisories(cid) == []
    assert (
        client.patch(
            f"{base}/{ids[0]}", headers=headers, json={"state": "In Progress"}
        ).status_code
        == 200
    )
    assert "First saved task" in advisories(cid)[0]
    assert client.delete(f"{base}/{ids[0]}", headers=headers).status_code == 204
    assert advisories(cid) == []
    page = client.get(f"/cases/{cid}?tab=review").data.decode()
    assert "Open task:" not in page
    with app.app_context():
        # Tasks remain advisory; both completion and export use review_issues.
        assert review_issues(cid) == baseline


@pytest.mark.parametrize("keep_custom", [False, True])
def test_group_bulk_deletion_removes_only_affected_checklist_advisories(keep_custom):
    client, headers, cid, _ = setup()
    collection = create(client, headers)
    result = application(client, headers, cid, collection)
    assert result.status_code == 201
    gid = result.json["group_id"]
    if keep_custom:
        assert (
            client.post(
                f"/api/v1/cases/{cid}/tasks",
                headers=headers,
                json={"title": "Keep custom task"},
            ).status_code
            == 201
        )
    assert len(advisories(cid)) == 2 + keep_custom
    response = client.post(
        f"/task-workspace/cases/{cid}/groups/{gid}/delete",
        data={"csrf": "collection-token", "payload": '{"confirm":true}'},
    )
    assert response.status_code == 200
    remaining = advisories(cid)
    assert len(remaining) == int(keep_custom)
    if keep_custom:
        assert "Keep custom task" in remaining[0]
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT count(*) FROM tasks WHERE case_id=? AND group_id=?", (cid, gid)
            )
            .fetchone()[0]
            == 0
        )
    page = client.get(f"/cases/{cid}?tab=review").data.decode()
    assert (
        "Open task: Collect context" not in page
        and "Open task: Inspect content" not in page
    )
