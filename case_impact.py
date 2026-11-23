"""Independent case impact metadata, validation, portability and reporting."""

from datetime import datetime, timezone

TYPES = {
    "detection": "New or Improved Detection",
    "discovery": "Confirmed Discovery",
    "both": "Detection and Discovery",
}
FIELDS = ("impact_confirmed", "impact_type", "impact_summary", "impact_confirmed_at")
DEFAULTS = dict(zip(FIELDS, (0, None, "", None)))
MAX_SUMMARY = 4000


def initialize(connection):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(cases)")}
    for name, definition in zip(
        FIELDS,
        ("INTEGER NOT NULL DEFAULT 0", "TEXT", "TEXT NOT NULL DEFAULT ''", "TEXT"),
    ):
        if name not in columns:
            connection.execute(f"ALTER TABLE cases ADD COLUMN {name} {definition}")


def track_sync(connection):
    """Install after CaseSync creates its dirty-record table."""
    connection.executescript(
        """CREATE TRIGGER IF NOT EXISTS sync_dirty_case_impact_update
        AFTER UPDATE OF impact_confirmed,impact_type,impact_summary,impact_confirmed_at ON cases
        BEGIN INSERT OR IGNORE INTO sync_dirty VALUES(NEW.id); END;"""
    )


def fields(record):
    record = dict(record)
    return {name: record.get(name, default) for name, default in DEFAULTS.items()}


def validate(value):
    if type(value["impact_confirmed"]) not in (bool, int) or value[
        "impact_confirmed"
    ] not in (0, 1):
        raise ValueError("Enterprise Impact Confirmed must be a boolean.")
    if value["impact_type"] not in (None, "", *TYPES):
        raise ValueError("Select a supported impact outcome type.")
    summary = value["impact_summary"]
    if not isinstance(summary, str) or len(summary) > MAX_SUMMARY:
        raise ValueError("Impact Summary must be at most 4,000 characters.")
    summary = summary.strip()
    if value["impact_confirmed"] and (value["impact_type"] not in TYPES or not summary):
        raise ValueError(
            "Confirmed impact requires an outcome type and a nonempty Impact Summary."
        )
    stamp = value["impact_confirmed_at"]
    if stamp is not None:
        try:
            if not isinstance(stamp, str):
                raise ValueError()
            datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid impact confirmation timestamp.") from None
    return {
        **value,
        "impact_confirmed": int(value["impact_confirmed"]),
        "impact_type": value["impact_type"] or None,
        "impact_summary": summary,
    }


def patch(current, incoming, now):
    if "impact_confirmed_at" in incoming:
        raise ValueError(
            "impact_confirmed_at is recorded by the server and is read-only."
        )
    before = fields(current)
    value = {**before, **{key: incoming[key] for key in FIELDS[:-1] if key in incoming}}
    if (
        "impact_confirmed" in incoming
        and type(incoming["impact_confirmed"]) is not bool
    ):
        raise ValueError("Enterprise Impact Confirmed must be a boolean.")
    if (
        value["impact_confirmed"]
        and not before["impact_confirmed"]
        and not before["impact_confirmed_at"]
    ):
        value["impact_confirmed_at"] = now
    return validate(value)


def archived(record):
    return validate(fields(record))


def snapshot_fields(record):
    value = archived(record)
    return value if value != DEFAULTS else {}


def write(connection, cid, value):
    connection.execute(
        "UPDATE cases SET " + ",".join(name + "=?" for name in FIELDS) + " WHERE id=?",
        [value[name] for name in FIELDS] + [cid],
    )


def report(connection, cases, weekly, start, end, now):
    from performance_metrics import timestamp

    rows = [
        dict(row)
        for row in connection.execute(
            "SELECT c.*,u.username AS owner_name FROM cases c LEFT JOIN users u ON u.id=c.owner"
        )
    ]
    ids = {case["id"] for case in cases}
    histories = {}
    for row in connection.execute(
        "SELECT case_id,stage,outcome,created FROM history ORDER BY case_id,id"
    ):
        histories.setdefault(row["case_id"], []).append(dict(row))
    selected, undated, active = [], 0, 0
    # Every case in a recent scope uses the same reporting-date rule.
    scope = set(ids) if start is None else set()
    for row in rows:
        if row["id"] not in ids:
            continue
        confirmed = bool(row["impact_confirmed"])
        active += int(confirmed)
        history = histories.get(row["id"], [])
        completed = None
        for index, event in enumerate(history):
            if (
                event["stage"] == 2
                and event["outcome"] in ("Done", "No applicable work", "Deferred")
                and (
                    (index == len(history) - 1 and row["stage"] == 3)
                    or (
                        index + 1 < len(history)
                        and history[index + 1]["stage"] == 3
                        and history[index + 1]["outcome"] == "Reopened"
                    )
                )
            ):
                date = timestamp(event["created"])
                if date and date <= now:
                    completed = date
        date = completed
        source = "Completion"
        if date is None:
            date = timestamp(row["impact_confirmed_at"]) if confirmed else None
            source = "First confirmation"
        if date is None or date > now:
            date = timestamp(row["created"])
            source = "Creation fallback"
        if date is None or date > now:
            undated += int(confirmed)
            if start is not None:
                continue
            date = None
            source = "Unavailable"
        if start is not None and not (start <= date < end):
            continue
        scope.add(row["id"])
        if confirmed:
            selected.append(
                {
                    **row,
                    "date": date,
                    "display_date": (
                        date.astimezone(end.tzinfo).date().isoformat()
                        if date
                        else "Unavailable"
                    ),
                    "date_source": source,
                }
            )
    selected.sort(
        key=lambda row: (
            row["date"] or datetime.min.replace(tzinfo=timezone.utc),
            row["number"],
        ),
        reverse=True,
    )
    counts = {
        kind: sum(row["impact_type"] == kind for row in selected) for kind in TYPES
    }
    trend = [{**week, "impact": 0} for week in weekly]
    for row in selected:
        if row["date"]:
            local_date = row["date"].astimezone(end.tzinfo).date().isoformat()
            for week in trend:
                if week["start"] <= local_date <= week["end"]:
                    week["impact"] += 1
                    break
    return {
        "total": len(selected),
        "denominator": len(scope),
        "rate": round(100 * len(selected) / len(scope), 1) if scope else 0.0,
        "detection": counts["detection"] + counts["both"],
        "discovery": counts["discovery"] + counts["both"],
        "breakdown": counts,
        "rows": selected,
        "weekly": trend,
        "max": max(1, *(week["impact"] for week in trend)),
        "undated": undated,
        "active_all": active,
    }
