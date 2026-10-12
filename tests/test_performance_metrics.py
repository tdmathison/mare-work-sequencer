from datetime import datetime, timedelta, timezone

import pytest

from app import app, db, run
from performance_metrics import scorecard, comparison

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def add_case(created, stage=0, owner=None, creator=None, name="Saved creator"):
    return run(
        "INSERT INTO cases(number,name,created,stage,owner,creator,creator_username) VALUES(?,?,?,?,?,?,?)",
        (
            "MET-" + str(db().execute("SELECT count(*) FROM cases").fetchone()[0]),
            "Metrics case",
            created,
            stage,
            owner,
            creator,
            name,
        ),
    ).lastrowid


def event(cid, created, stage=2, outcome="Done"):
    run(
        "INSERT INTO history(case_id,stage,created,outcome) VALUES(?,?,?,?)",
        (cid, stage, created, outcome),
    )


def user(name, active=1):
    return run(
        "INSERT INTO users(username,password,role,active,forced) VALUES(?,'unused','User',?,0)",
        (name, active),
    ).lastrowid


def result(weeks=4):
    return scorecard(db(), weeks, NOW)


def test_full_weeks_boundaries_and_timezone():
    with app.app_context():
        for date in (
            "2026-09-14T00:00:00+00:00",
            "2026-10-11T23:59:59Z",
            "2026-10-12T00:00:00Z",
            "2026-09-13T23:59:59Z",
            "2026-09-13T23:30:00-01:00",
        ):
            add_case(date)
        data = result()
        assert (data["start"], data["end"]) == ("2026-09-14", "2026-10-11")
        assert data["created"] == 3
        assert [week["created"] for week in data["weekly"]] == [2, 0, 0, 1]
        assert data["created_comparison"] == "+200.0% vs prior period"
        assert data["previous_start"] == "2026-08-17"
        assert data["previous_end"] == "2026-09-13"
        assert data["timezone"] == "UTC"


@pytest.mark.parametrize("weeks", [4, 12, 26, 52])
def test_empty_installation_and_zero_weeks(weeks):
    with app.app_context():
        data = result(weeks)
        assert len(data["weekly"]) == weeks
        assert all(week["created"] == week["completed"] == 0 for week in data["weekly"])
        assert data["created_comparison"] == data["completed_comparison"] == "No change"
        assert data["median"] is None
        assert data["people"] == []
        assert data["total"] == data["unfinished"] == 0


@pytest.mark.parametrize(
    "current,prior,expected",
    [
        (0, 0, "No change"),
        (1, 0, "No prior-period baseline"),
        (0, 2, "-100.0% vs prior period"),
        (3, 2, "+50.0% vs prior period"),
        (2, 2, "No change"),
    ],
)
def test_comparison(current, prior, expected):
    assert comparison(current, prior) == expected


def test_current_pipeline_and_whole_day_age_boundaries():
    with app.app_context():
        for days in (0, 7.99, 8, 14.99, 15, 30.99, 31):
            add_case((NOW - timedelta(days=days)).isoformat())
        add_case("2026-10-10", stage=1)
        add_case("2026-10-10", stage=2)
        add_case("2026-10-10", stage=3)
        data = result()
        assert data["stages"] == [7, 1, 1, 1]
        assert data["progress"] == 2
        assert data["unfinished"] == 9
        assert data["ages"] == [4, 2, 2, 1]
        assert result(12)["ages"] == data["ages"]


def test_median_elapsed_time_and_prior_difference():
    with app.app_context():
        for created, done in [
            ("2026-09-14", "2026-09-16"),
            ("2026-09-20", "2026-09-26"),
            ("2026-08-20", "2026-08-23"),
        ]:
            cid = add_case(created, stage=3)
            event(cid, done)
        data = result()
        assert data["completed"] == 2
        assert data["median"] == 4
        assert data["median_comparison"] == "+1.0 days vs prior period"
        assert data["timed_cases"] == 2
        assert sum(week["completed"] for week in data["weekly"]) == data["completed"]


def test_missing_imported_invalid_and_future_timestamps():
    with app.app_context():
        add_case("2026-09-20", stage=3)  # snapshot alone is not a date
        for created, done in [
            ("2026-10-01", "2026-09-20"),
            ("invalid", "2026-09-21"),
            ("2026-09-20", "invalid"),
            ("2026-09-20", "2099-01-01"),
        ]:
            cid = add_case(created, stage=3)
            event(cid, done)
        add_case("invalid")
        add_case("2099-01-01")
        data = result()
        assert data["completed"] == 2
        assert data["median"] is None
        assert data["timing_excluded"] == 2
        assert data["missing_completion"] == 3
        assert data["unknown_age"] == 2
        assert data["invalid_creation"] == 3


def test_reopening_recompletion_distinct_per_period_and_first_event():
    with app.app_context():
        cid = add_case("2026-08-20", stage=3)
        event(cid, "2026-08-25")
        event(cid, "2026-09-15", stage=3, outcome="Reopened")
        event(cid, "2026-09-20")
        event(cid, "2026-09-21", stage=3, outcome="Reopened")
        event(cid, "2026-10-01")
        reopened = add_case("2026-09-18", stage=1)
        event(reopened, "2026-09-22")
        event(reopened, "2026-09-23", stage=3, outcome="Reopened")
        data = result()
        assert data["completed"] == 2
        assert sum(week["completed"] for week in data["weekly"]) == 2
        assert data["completed_comparison"] == "+100.0% vs prior period"
        assert data["median"] == 17.5  # 31 days and 4 days; not the later recompletion


def test_merged_legacy_exits_use_final_completion_evidence():
    with app.app_context():
        cid = add_case("2026-09-20", stage=3)
        event(cid, "2026-09-21")
        event(cid, "2026-09-23")
        unfinished = add_case("2026-09-20", stage=2)
        event(unfinished, "2026-09-22")
        data = result()
        assert data["completed"] == 1
        assert data["median"] == 3


def test_creator_current_owner_unassigned_disabled_deleted_attribution():
    with app.app_context():
        creator = user("Creator")
        disabled = user("Disabled owner", active=0)
        cid = add_case("2026-09-20", stage=3, creator=creator, owner=disabled)
        event(cid, "2026-09-25")
        add_case("2026-09-20", stage=1, name="Deleted creator")
        add_case("2026-09-20", stage=2, creator=creator, owner=disabled)
        data = result()
        people = {p["username"]: p for p in data["people"]}
        assert people["Creator"]["created"] == 2
        assert people["Creator"]["completed"] == 0
        assert people["Disabled owner"]["completed"] == 1
        assert people["Disabled owner"]["assigned"] == 2
        assert people["Disabled owner"]["progress"] == 1
        assert people["Disabled owner"]["active"] == 0
        assert people["Unassigned"]["assigned"] == 1
        assert people["Deleted creator (deleted/unknown account)"]["created"] == 1
        assert sum(p["created"] for p in data["people"]) == data["created"]
        assert sum(p["completed"] for p in data["people"]) == data["completed"]
        assert sum(p["created_all"] for p in data["people"]) == 3


@pytest.mark.parametrize("role", ["User", "Administrator"])
def test_metrics_auth_period_validation_and_escaping(role):
    client = app.test_client()
    assert client.get("/metrics").status_code == 302
    with app.app_context():
        uid = run(
            "INSERT INTO users(username,password,role,forced) VALUES(?,'unused',?,0)",
            ("<script>label</script>", role),
        ).lastrowid
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf="metrics-token")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"MARE performance overview" in response.data
    assert b"Last 12 full weeks" in response.data
    assert b"&lt;script&gt;label&lt;/script&gt;" in response.data
    assert b"<script>label</script>" not in response.data
    assert b'href="/metrics" aria-current="page"' in response.data
    assert client.get("/metrics?weeks=4").status_code == 200
    assert client.get("/metrics?weeks=5").status_code == 400
    assert client.get("/metrics?weeks=garbage").status_code == 400
