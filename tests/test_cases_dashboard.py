from datetime import datetime, timezone
from app import app, db
from cases_dashboard import snapshot


def add(number, stage, completed=None, description='<script>private()</script>'):
    connection = db()
    cid = connection.execute('INSERT INTO cases(number,name,description,stage,created,external_number) VALUES(?,?,?,?,?,?)',
                             (number, '<img src=x onerror=alert(1)>', description, stage, '2026-01-01', 'SECRET')).lastrowid
    if completed:
        connection.execute("INSERT INTO history(case_id,stage,created,outcome,author) VALUES(?,2,?,'Done','SECRET')", (cid, completed))
    return cid


def test_public_access_and_private_boundary():
    client = app.test_client()
    assert client.get('/dashboards/cases').status_code == 200
    assert b'Cases dashboard' in client.get('/login').data
    assert client.get('/').status_code == 302
    assert client.get('/cases/1').status_code == 302
    assert client.get('/api/v1/cases').status_code == 401
    assert client.post('/dashboards/cases/data').status_code in (403, 405)
    with app.app_context():
        add('MARE-1', 3, '2026-10-02T12:00:00Z')
        db().commit()
    response = client.get('/dashboards/cases/data')
    data = response.json
    assert response.headers['Cache-Control'] == 'no-store'
    assert set(data['latest']) == {'number', 'title', 'description', 'state', 'completed_at'}
    assert 'SECRET' not in response.text
    assert data['latest']['title'].startswith('<img')  # JSON text, rendered via textContent.
    assert client.get('/dashboards/cases/data?page=bad').status_code == 400


def test_lifecycle_counts_timezone_reopen_missing_and_pagination():
    with app.app_context():
        add('DONE-OLD', 3, '2026-10-01T06:59:59Z')  # September in Los Angeles
        cid = add('DONE-NEW', 3, '2026-10-01T07:00:00Z')
        add('MISSING', 3, 'invalid')
        reopened = add('REOPENED', 1, '2026-10-02T00:00:00Z')
        db().execute("INSERT INTO history(case_id,stage,outcome,created) VALUES(?,3,'Reopened','2026-10-03T00:00:00Z')", (reopened,))
        # A completed legacy row whose only dated completion predates reopening.
        legacy = add('LEGACY', 3, '2026-09-01T00:00:00Z')
        db().execute("INSERT INTO history(case_id,stage,outcome,created) VALUES(?,3,'Reopened','2026-09-02T00:00:00Z')", (legacy,))
        for i in range(8): add(f'ACTIVE-{i}', 2 if i < 3 else 1)
        add('WAITING', 0)
        data = snapshot(db(), current=datetime(2026,10,15,tzinfo=timezone.utc), timezone_name='America/Los_Angeles')
        assert data['metrics'] == dict(in_progress=9, preparing=3, completed_month=1, not_started=1)
        assert data['latest']['number'] == 'DONE-NEW'
        assert len(data['recent']) == 3
        assert {c['number']:c['completed_at'] for c in data['recent']}['LEGACY'] is None
        assert data['pagination'] == dict(page=0, pages=3, page_size=4, total=9)
        assert all(c['state']=='Packaging & Delivery' for c in data['active'][:3])
        assert len(snapshot(db(), 2)['active']) == 1
        assert snapshot(db(), 999)['pagination']['page'] == 2


def test_empty_one_many_and_future_dates():
    with app.app_context():
        assert snapshot(db())['latest'] is None
        assert snapshot(db())['active'] == []
        add('ONE', 3)
        assert snapshot(db())['latest']['completed_at'] is None
        assert snapshot(db())['recent'] == []
        for i in range(30): add(f'DONE-{i:02}', 3, '2025-01-01T00:00:00Z')
        add('FUTURE', 3, '2999-01-01T00:00:00Z')
        data = snapshot(db())
        assert len(data['recent']) == 20
        assert data['latest']['number'] == 'DONE-29'


def test_only_terminal_exit_is_completion_evidence():
    with app.app_context():
        cid = add('MIGRATED', 3, '2026-10-10T00:00:00Z')
        # Merged legacy stages can produce adjacent stage=2 exits. The final
        # exit is authoritative even when its timestamp is missing.
        db().execute("INSERT INTO history(case_id,stage,outcome,created) VALUES(?,2,'Done','invalid')", (cid,))
        data = snapshot(db(), current=datetime(2026,10,15,tzinfo=timezone.utc))
        assert data['latest']['completed_at'] is None
        assert data['metrics']['completed_month'] == 0
        db().execute("INSERT INTO history(case_id,stage,outcome,created) VALUES(?,2,'Deferred','2026-10-12T00:00:00Z')", (cid,))
        assert snapshot(db(), current=datetime(2026,10,15,tzinfo=timezone.utc))['metrics']['completed_month'] == 1
