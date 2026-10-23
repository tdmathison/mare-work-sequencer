"""Inventory and explicitly dated executive scorecard; read-only, batched queries over existing records."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo
from case_queries import inventory

PERIODS = (4, 12, 26, 52)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Legacy naive timestamps are interpreted as UTC, never server local time.
        return (
            result.replace(tzinfo=timezone.utc)
            if result.tzinfo is None
            else result.astimezone(timezone.utc)
        )
    except (ValueError, TypeError, AttributeError):
        return None


def comparison(current, prior):
    if not current and not prior:
        return "No change"
    if not prior:
        return "No prior-period baseline"
    change = 100 * (current - prior) / prior
    return "No change" if change == 0 else f"{change:+.1f}% vs prior period"


def scorecard(connection, weeks=12, current_time=None, timezone_name="UTC"):
    # All inventory/history/user reads belong to one consistent request snapshot.
    connection.execute("SAVEPOINT metrics_snapshot")
    try:
        return _scorecard(connection, weeks, current_time, timezone_name)
    finally:
        connection.execute("RELEASE metrics_snapshot")


def _scorecard(connection, weeks, current_time, timezone_name):
    if weeks not in PERIODS:
        raise ValueError("Unsupported reporting period")
    now = (current_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local = now.astimezone(ZoneInfo(timezone_name))
    end = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start, previous_start = end - timedelta(weeks=weeks), end - timedelta(
        weeks=2 * weeks
    )
    cases = inventory(connection)
    users = [
        dict(row)
        for row in connection.execute(
            "SELECT id,username,active FROM users ORDER BY username"
        )
    ]
    # Window functions select only terminal exits, keeping irrelevant history out
    # of Python and avoiding per-case queries. Migrations can merge adjacent
    # stage-exit records into stage 2; the final exit is the completion evidence.
    history = connection.execute(
        """
        WITH exits AS (
            SELECT case_id, stage, outcome, created,
                   LEAD(id) OVER sequence AS next_id,
                   LEAD(stage) OVER sequence AS next_stage,
                   LEAD(outcome) OVER sequence AS next_outcome
            FROM history
            WINDOW sequence AS (PARTITION BY case_id ORDER BY id)
        )
        SELECT DISTINCT exits.case_id, exits.created,
               (next_id IS NULL AND cases.stage = 3) AS current_completion
        FROM exits JOIN cases ON cases.id = exits.case_id
        WHERE exits.stage = 2 AND exits.outcome IN ('Done','No applicable work','Deferred')
          AND ((next_stage = 3 AND next_outcome = 'Reopened')
               OR (next_id IS NULL AND cases.stage = 3))
    """
    )
    completions = defaultdict(list)
    current_completions = {}
    for event in history:
        date = timestamp(event["created"])
        completions[event["case_id"]].append(date)
        if event["current_completion"]:
            current_completions[event["case_id"]] = date

    weekly = []
    for index in range(weeks):
        week_start = start + timedelta(weeks=index)
        weekly.append(
            {
                "start": week_start.date().isoformat(),
                "end": (week_start + timedelta(days=6)).date().isoformat(),
                "created": 0,
                "completed": 0,
            }
        )
    people = {
        user["id"]: {
            **user,
            "created": 0,
            "assigned": 0,
            "progress": 0,
            "completed": 0,
            "completed_snapshot": 0,
        }
        for user in users
    }

    def person(case, field):
        key = case[field]
        if key not in people:
            if field == "creator":
                label = case["creator_username"] or (
                    f"Deleted user #{key}" if key else "Unknown creator"
                )
                key = ("creator", key, label)
                label += " (deleted/unknown account)"
            else:
                label = "Unassigned" if key is None else f"Deleted owner #{key}"
                key = ("owner", key)
            people.setdefault(
                key,
                {
                    "id": key,
                    "username": label,
                    "active": None,
                    "created": 0,
                    "assigned": 0,
                    "progress": 0,
                    "completed": 0,
                    "completed_snapshot": 0,
                },
            )
        return people[key]

    created_counts, completed_counts = [0, 0], [0, 0]
    durations = [[], []]
    stage_counts = [0, 0, 0, 0]
    ages = [0, 0, 0, 0]
    unknown_age = invalid_creation = timing_excluded = missing_completion = 0
    for case in cases:
        stage = case["stage"]
        if stage in range(4):
            stage_counts[stage] += 1
        creator = person(case, "creator")
        creator.setdefault("created_all", 0)
        creator["created_all"] += 1
        owner = person(case, "owner")
        owner["assigned"] += 1
        owner["progress"] += int(stage in (1, 2))
        owner["completed_snapshot"] += int(stage == 3)
        created = timestamp(case["created"])
        if created is None or created > now:
            invalid_creation += 1
        if stage in (0, 1, 2):
            if created is None or created > now:
                unknown_age += 1
            else:
                days = (now - created).days
                ages[
                    0 if days <= 7 else 1 if days <= 14 else 2 if days <= 30 else 3
                ] += 1
        events = sorted(
            {date for date in completions[case["id"]] if date and date <= now}
        )
        current_completion = current_completions.get(case["id"])
        if stage == 3 and (current_completion is None or current_completion > now):
            missing_completion += 1
        for index, (left, right) in enumerate(((start, end), (previous_start, start))):
            if created and left <= created < right:
                created_counts[index] += 1
                if index == 0:
                    person(case, "creator")["created"] += 1
                    weekly[
                        (created.astimezone(local.tzinfo).date() - start.date()).days
                        // 7
                    ]["created"] += 1
            event = next((date for date in events if left <= date < right), None)
            if event:
                completed_counts[index] += 1
                if index == 0:
                    owner["completed"] += 1
                    weekly[
                        (event.astimezone(local.tzinfo).date() - start.date()).days // 7
                    ]["completed"] += 1
                if created and created <= event:
                    durations[index].append((event - created).total_seconds() / 86400)
                elif index == 0:
                    timing_excluded += 1
    medians = [median(values) if values else None for values in durations]
    delta = "Prior-period cycle time unavailable"
    if medians[0] is not None and medians[1] is not None:
        difference = medians[0] - medians[1]
        delta = (
            "No change"
            if abs(difference) < 0.05
            else f"{difference:+.1f} days vs prior period"
        )
    return {
        "weeks": weeks,
        "start": start.date().isoformat(),
        "end": (end - timedelta(days=1)).date().isoformat(),
        "previous_start": previous_start.date().isoformat(),
        "previous_end": (start - timedelta(days=1)).date().isoformat(),
        "timezone": timezone_name,
        "as_of": now.isoformat(timespec="seconds"),
        "created": created_counts[0],
        "created_comparison": comparison(*created_counts),
        "completed": completed_counts[0],
        "completed_comparison": comparison(*completed_counts),
        "median": medians[0],
        "median_comparison": delta,
        "timed_cases": len(durations[0]),
        "stages": stage_counts,
        "total": len(cases),
        "completed_current": stage_counts[3],
        "unknown_state": sum(case["stage"] not in range(4) for case in cases),
        "unfinished": sum(stage_counts[:3]),
        "progress": sum(stage_counts[1:3]),
        "weekly": weekly,
        "chart_max": max(1, max(week["created"] for week in weekly)),
        "ages": ages,
        "age_max": max(1, *ages),
        "unknown_age": unknown_age,
        "people": [{"created_all": 0, **person} for person in people.values()],
        "missing_completion": missing_completion,
        "timing_excluded": timing_excluded,
        "invalid_creation": invalid_creation,
    }
