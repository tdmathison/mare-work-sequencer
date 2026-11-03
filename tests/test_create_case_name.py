"""Only a fresh Create Case form supplies a date; submission preserves names."""

from datetime import datetime, timezone
from html.parser import HTMLParser
import pytest
import app as application
from app import app, db
from test_api import make_user


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return (
            cls(2026, 11, 3, 12)
            if tz is None
            else cls(2026, 11, 3, 20, tzinfo=timezone.utc).astimezone(tz)
        )


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and "name" in values:
            self.values[values["name"]] = values.get("value", "")


@pytest.fixture
def creator(monkeypatch):
    monkeypatch.setattr(application, "datetime", Clock)
    uid, headers = make_user("case-name-analyst")
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="case-name")
    return client, headers


def test_new_form_has_one_local_date_prefix_and_focus_only(creator):
    client, _ = creator
    response = client.get("/cases/new")
    assert response.status_code == 200
    assert Inputs(response.text).values["name"] == "20261103: "
    assert (
        "name.setSelectionRange(name.value.length, name.value.length)" in response.text
    )
    assert "name.value =" not in response.text


@pytest.mark.parametrize(
    "name",
    [
        "20261103: ",
        "20261103: My case",
        "My custom case",
        "  Intentional spaces  ",
        "20261103: 20261103: intentional text",
        'Case <special> & "quoted"',
    ],
)
def test_web_and_api_create_preserve_exact_supplied_names(creator, name):
    client, headers = creator
    response = client.post("/cases", data={"csrf": "case-name", "name": name})
    assert response.status_code == 302
    cid = int(response.location.rsplit("/", 1)[-1])
    with app.app_context():
        assert (
            db().execute("SELECT name FROM cases WHERE id=?", (cid,)).fetchone()[0]
            == name
        )
    response = client.post("/api/v1/cases", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    assert response.json["case"]["name"] == name


def test_repeated_validation_preserves_returned_name_without_initialization(creator):
    client, _ = creator
    name = "20261103: My case "
    for _ in range(2):
        response = client.post(
            "/cases",
            data={"csrf": "case-name", "name": name, "external_system": "JIRA"},
        )
        assert response.status_code == 400
        assert Inputs(response.text).values["name"] == name
        assert "name.setSelectionRange" not in response.text
        with app.app_context():
            assert db().execute("SELECT count(*) FROM cases").fetchone()[0] == 0
    response = client.post("/cases", data={"csrf": "case-name", "name": name})
    assert response.status_code == 302
    with app.app_context():
        assert db().execute("SELECT name FROM cases").fetchone()[0] == name


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_invalid_names_remain_invalid_and_unmodified_in_form(creator, name):
    client, headers = creator
    response = client.post("/cases", data={"csrf": "case-name", "name": name})
    assert response.status_code == 400 and Inputs(response.text).values["name"] == name
    assert (
        client.post("/api/v1/cases", headers=headers, json={"name": name}).status_code
        == 400
    )
