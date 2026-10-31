"""Permission-scoped content overview; charts consume counts, never content bodies."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, abort, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from authorization import has_permission
from content_metrics import KINDS, COLORS, initialize, coverage_start, ready


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError, AttributeError):
        return None


def period_start(value, granularity):
    return (
        value.replace(day=1)
        if granularity == "monthly"
        else value - timedelta(days=value.weekday())
    )


def next_period(value, granularity):
    return (
        (
            value.replace(year=value.year + 1, month=1)
            if value.month == 12
            else value.replace(month=value.month + 1)
        )
        if granularity == "monthly"
        else value + timedelta(days=7)
    )


def aggregate(con, can, admin=False, filters=None, timezone_name="UTC", instant=None):
    filters = filters or {}
    instant = instant or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"
    today = instant.astimezone(zone).date()
    default = today.replace(day=1)
    for _ in range(5):
        default = (default - timedelta(days=1)).replace(day=1)
    try:
        start = date.fromisoformat(filters.get("start") or default.isoformat())
        end = date.fromisoformat(filters.get("end") or today.isoformat())
    except (ValueError, TypeError):
        raise ValueError("Use ISO dates (YYYY-MM-DD).")
    granularity = filters.get("granularity", "monthly")
    measure = filters.get("measure", "added")
    if (
        granularity not in ("monthly", "weekly")
        or measure not in ("added", "cumulative")
        or start > end
        or end > today
        or (end - start).days > 1096
    ):
        raise ValueError(
            "Choose a valid date range of at most three years, ending no later than today."
        )
    permissions = {
        "global": {"tags": can("tags:read")},
        "profile": {
            kind: can("tags:read")
            for kind in ("families", "actors", "pdf", "references")
        },
        "case": {
            kind: can("cases:read")
            and can(
                "indicators:read"
                if kind == "indicators"
                else "references:read" if kind == "references" else "cases:assets"
            )
            for kind in (
                "indicators",
                "references",
                "samples",
                "snort",
                "yara",
                "scripts",
                "pdf",
            )
        },
    }
    authorized = {
        (scope, kind)
        for scope, values in permissions.items()
        for kind, allowed in values.items()
        if allowed
    }
    buckets = []
    cursor = period_start(start, granularity)
    while cursor <= end:
        following = next_period(cursor, granularity)
        buckets.append(
            {
                "start": max(cursor, start).isoformat(),
                "end": min(following - timedelta(days=1), end).isoformat(),
                "label": cursor.isoformat(),
                "partial": cursor < start
                or following - timedelta(days=1) > end
                or cursor <= today < following,
            }
        )
        cursor = following
    coverage = timestamp(coverage_start(con)) or instant
    covered_day = coverage.astimezone(zone).date()
    series = {
        kind: dict(
            label=label,
            color=COLORS[kind],
            available=any(k == kind for _, k in authorized),
            inventory=0,
            unknown_dates=0,
            total=0,
            case_total=0,
            baseline=0,
            counts=[0] * len(buckets),
        )
        for kind, label in KINDS.items()
    }
    con.create_function(
        "content_reporting_day",
        1,
        lambda value: (
            parsed.astimezone(zone).date().isoformat()
            if (parsed := timestamp(value)) and parsed <= instant
            else None
        ),
    )
    # One grouped, content-free query; no cache can cross a permission boundary.
    clauses = " OR ".join("(scope=? AND kind=?)" for _ in authorized) or "0"
    arguments = [value for pair in sorted(authorized) for value in pair]
    grouped = con.execute(
        "SELECT kind,scope,live,content_reporting_day(added_at) AS day,count(*) AS n FROM content_events WHERE "
        + clauses
        + " GROUP BY kind,scope,live,day",
        arguments,
    )
    for row in grouped:
        kind, scope, live, day, n = tuple(row)
        if (scope, kind) not in authorized or kind not in series:
            continue
        target = series[kind]
        if live:
            target["inventory"] += n
        if day is None:
            if live:
                target["unknown_dates"] += n
            continue
        if not live and not admin:
            continue
        value = date.fromisoformat(day)
        if value < start:
            target["baseline"] += n
        elif value <= end:
            target["total"] += n
            if scope == "case":
                target["case_total"] += n
            for index, bucket in enumerate(buckets):
                if bucket["start"] <= day <= bucket["end"]:
                    target["counts"][index] += n
                    break
    for target in series.values():
        running = target["baseline"]
        target["values"] = []
        target["partial_history"] = []
        for index, bucket in enumerate(buckets):
            count = target["counts"][index]
            running += count
            incomplete = (
                datetime.combine(date.fromisoformat(bucket["start"]), time.min, zone)
                < coverage
            )
            target["partial_history"].append(incomplete)
            target["values"].append(
                None
                if incomplete and count == 0
                else running if measure == "cumulative" else count
            )
        if not target["available"]:
            for key in (
                "inventory",
                "unknown_dates",
                "total",
                "case_total",
                "baseline",
            ):
                target[key] = None
            target["values"] = [None] * len(buckets)
            target["counts"] = [None] * len(buckets)
    return dict(
        today=today.isoformat(),
        start=start.isoformat(),
        end=end.isoformat(),
        timezone=timezone_name,
        granularity=granularity,
        measure=measure,
        buckets=buckets,
        series=series,
        last_updated=instant.astimezone(zone).isoformat(),
        coverage_start=coverage.astimezone(zone).isoformat(),
        coverage_date=covered_day.isoformat(),
        unknown_dates=sum(s["unknown_dates"] or 0 for s in series.values()),
        deleted_history=admin,
        history_notice="Earlier additions are a lower bound; empty pre-coverage periods are unavailable. Unknown dates are excluded from trends. Cumulative additions are not historical inventory."
        + (
            ""
            if admin
            else " Deleted records are excluded for this account; addition history covers currently accessible records only."
        ),
    )


def register(app, db, root):
    with app.app_context():
        initialize(db(), root)

    @app.get("/content-metrics")
    def content_metrics():
        if not has_permission(g.user, "metrics:read", db()):
            abort(403)
        if not ready(db()):
            abort(
                503,
                description="Complete the existing tag migration before enabling Content Metrics.",
            )
        response = app.make_response(render_template("content_metrics.html"))
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/content-metrics/data")
    def content_metrics_data():
        if not has_permission(g.user, "metrics:read", db()):
            return (
                jsonify(error="Permission denied."),
                403,
                {"Cache-Control": "private, no-store"},
            )
        if not ready(db()):
            return (
                jsonify(
                    error="Complete the existing tag migration before enabling Content Metrics."
                ),
                503,
            )
        try:
            result = aggregate(
                db(),
                lambda p: has_permission(g.user, p, db()),
                g.user["role"] == "Administrator",
                request.args,
                app.config.get("DISPLAY_TIMEZONE", "UTC"),
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400, {"Cache-Control": "private, no-store"}
        response = jsonify(result)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    content_metrics_data.permission = "metrics:read"

    api = Blueprint("content_metrics_api", __name__, url_prefix="/api/v1")
    api.add_url_rule(
        "/content-metrics",
        endpoint="api_content_metrics",
        view_func=content_metrics_data,
        methods=["GET"],
    )

    @api.errorhandler(HTTPException)
    def api_error(error):
        return jsonify(error=error.description), error.code

    @api.errorhandler(Exception)
    def api_failure(error):
        app.logger.exception("Content metrics API failed")
        return jsonify(error="Internal server error."), 500

    @api.after_request
    def private_data(response):
        response.headers["Cache-Control"] = "private, no-store"
        return response

    app.register_blueprint(api)
