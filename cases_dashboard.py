"""Anonymous display projection. No internal case serializer is used here."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import abort, jsonify, render_template, request

PAGE_SIZE = 4
RECENT_LIMIT = 20
# History.stage is the stage LEFT, not the stage entered. A reopening invalidates
# prior completions. Only terminal stage exits qualify, matching the executive
# scorecard and avoiding legacy merged-stage duplicates. SQLite rejects malformed
# timestamps through julianday().
PUBLIC_CTE = '''WITH public_cases AS (
 SELECT c.number, substr(c.name,1,200) AS title,
 substr(coalesce(c.description,''),1,1200) AS description, c.stage,
 (SELECT max(julianday(h.created)) FROM history h WHERE h.case_id=c.id
  AND h.stage=2 AND h.outcome IN ('Done','No applicable work','Deferred')
  AND h.id = (SELECT max(r.id) FROM history r WHERE r.case_id=c.id)
  AND julianday(h.created)<=julianday(:now)) AS completed_jd,
 (SELECT max(julianday(h.created)) FROM history h WHERE h.case_id=c.id
  AND julianday(h.created)<=julianday(:now)) AS changed_jd
 FROM cases c WHERE c.stage BETWEEN 0 AND 3
) '''
STATES = ('Not Started', 'Malware Analysis', 'Packaging & Delivery', 'Completed')


def public_case(row):
    """Explicit allowlist, including bounded text. Never return model dictionaries."""
    return dict(number=row['number'], title=row['title'], description=row['description'],
                state=STATES[row['stage']], completed_at=row['completed_at'])


def snapshot(connection, page=0, current=None, timezone_name='UTC'):
    zone = ZoneInfo(timezone_name)
    current = current or datetime.now(timezone.utc)
    local = current.astimezone(zone)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(year=start.year+1, month=1) if start.month == 12
           else start.replace(month=start.month+1))
    params = dict(now=current.isoformat(), start=start.astimezone(timezone.utc).isoformat(),
                  end=end.astimezone(timezone.utc).isoformat())
    # One read transaction keeps counts, spotlight and the active page consistent.
    connection.execute('SAVEPOINT public_dashboard')
    try:
        counts = connection.execute(PUBLIC_CTE + '''SELECT
          count(CASE WHEN stage IN (1,2) THEN 1 END) AS in_progress,
          count(CASE WHEN stage=2 THEN 1 END) AS preparing,
          count(CASE WHEN stage=0 THEN 1 END) AS not_started,
          count(CASE WHEN stage=3 AND completed_jd>=julianday(:start)
            AND completed_jd<julianday(:end) THEN 1 END) AS completed_month
          FROM public_cases''', params).fetchone()
        pages = max(1, (counts['in_progress']+PAGE_SIZE-1)//PAGE_SIZE)
        page = min(max(page, 0), pages-1)
        projection = "SELECT *, strftime('%Y-%m-%dT%H:%M:%SZ',completed_jd) AS completed_at FROM public_cases "
        completed = connection.execute(PUBLIC_CTE + projection +
            'WHERE stage=3 ORDER BY completed_jd DESC,number DESC LIMIT 21', params).fetchall()
        active = connection.execute(PUBLIC_CTE + projection +
            'WHERE stage IN (1,2) ORDER BY stage DESC,changed_jd DESC,number DESC LIMIT 4 OFFSET :offset',
            dict(params, offset=page*PAGE_SIZE)).fetchall()
    finally:
        connection.execute('RELEASE public_dashboard')
    return dict(updated_at=current.isoformat(), timezone=timezone_name, metrics=dict(counts),
                latest=public_case(completed[0]) if completed else None,
                recent=[public_case(row) for row in completed[1:RECENT_LIMIT+1]],
                active=[public_case(row) for row in active],
                pagination=dict(page=page, pages=pages, page_size=PAGE_SIZE, total=counts['in_progress']))


def register_dashboard(app, db):
    @app.get('/dashboards/cases')
    def cases_dashboard():
        return render_template('cases_dashboard.html')

    @app.get('/dashboards/cases/data')
    def cases_dashboard_data():
        try:
            page = int(request.args.get('page', '0'))
        except ValueError:
            abort(400)
        if page < 0 or page > 1000000:
            abort(400)
        response = jsonify(snapshot(db(), page, timezone_name=app.config.get('DISPLAY_TIMEZONE', 'UTC')))
        response.headers['Cache-Control'] = 'no-store'
        return response
