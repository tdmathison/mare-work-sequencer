"""Ownership is explicit: explain the start gate and unlock after saving an owner."""

import re

import pytest
from app import app, db, run
from test_api import make_user


@pytest.fixture
def analyst():
    uid, _ = make_user("start-analyst", "User")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="start-token")
    return client, uid


def create(client, **values):
    response = client.post(
        "/cases", data={"csrf": "start-token", "name": "Start regression", **values}
    )
    assert response.status_code == 302
    return response.location


def start_button(page):
    return re.search(r"<button([^>]*)>Start analysis</button>", page).group(1)


def test_unassigned_start_explains_requirement_and_saving_owner_unlocks(analyst):
    client, uid = analyst
    page = client.get("/cases/new").text
    assert "An active owner is required to start analysis." in page
    assert "Assigned owner (optional)" not in page
    base = create(client)
    page = client.get(base).text
    assert "disabled" in start_button(page)
    assert 'aria-describedby="stage-owner-required"' in start_button(page)
    assert "Select an owner and choose Save assigned owner." in page
    assert 'href="?tab=workbench#case-details"' in page
    assert (
        client.post(
            base + "/stage", data={"csrf": "start-token", "expected": "0"}
        ).status_code
        == 302
    )
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT stage FROM cases WHERE id=?", (int(base.rsplit("/", 1)[1]),)
            )
            .fetchone()[0]
            == 0
        )
    assert (
        client.post(
            base + "/owner", data={"csrf": "start-token", "owner_id": uid}
        ).status_code
        == 302
    )
    assert "disabled" not in start_button(client.get(base).text)
    response = client.post(
        base + "/stage", data={"csrf": "start-token", "expected": "0"}
    )
    assert response.status_code == 302
    with app.app_context():
        row = (
            db()
            .execute(
                "SELECT stage,owner FROM cases WHERE id=?",
                (int(base.rsplit("/", 1)[1]),),
            )
            .fetchone()
        )
        assert tuple(row) == (1, uid)


def test_owner_selected_during_creation_can_start_immediately(analyst):
    client, uid = analyst
    base = create(client, owner_id=uid)
    assert "disabled" not in start_button(client.get(base).text)
    assert (
        client.post(
            base + "/stage", data={"csrf": "start-token", "expected": "0"}
        ).status_code
        == 302
    )
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT stage FROM cases WHERE id=?", (int(base.rsplit("/", 1)[1]),)
            )
            .fetchone()[0]
            == 1
        )


def test_inactive_owner_does_not_unlock_start(analyst):
    client, _ = analyst
    owner, _ = make_user("inactive-owner", "User")
    base = create(client, owner_id=owner)
    with app.app_context():
        run("UPDATE users SET active=0 WHERE id=?", (owner,))
    assert "disabled" in start_button(client.get(base).text)
    client.post(base + "/stage", data={"csrf": "start-token", "expected": "0"})
    with app.app_context():
        assert (
            db()
            .execute(
                "SELECT stage FROM cases WHERE id=?", (int(base.rsplit("/", 1)[1]),)
            )
            .fetchone()[0]
            == 0
        )
