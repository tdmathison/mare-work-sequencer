import csv,io
import zipfile
from app import app,db,run
from werkzeug.security import generate_password_hash

def test_audit_filter_day_groups_and_csv_export():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('audit-admin',generate_password_hash('password-long-123'),'Administrator')).lastrowid
        run('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',('alice','Action, with comma','2026-10-06T12:00:00+00:00'))
        run('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',('bob','Other user action','2026-10-06T11:00:00+00:00'))
        run('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',('alice','Previous day action','2026-10-05T10:00:00+00:00'))
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='audit-token')
    page=client.get('/audit').data.decode()
    assert '<th>User</th>' in page and '<th>Actor</th>' not in page
    assert '<summary>2026-10-06' in page and '<summary>2026-10-05' in page
    filtered=client.get('/audit?actor=alice').data.decode()
    assert 'Action, with comma' in filtered and 'Previous day action' in filtered and 'Other user action' not in filtered
    response=client.get('/audit/export.csv?actor=alice')
    assert response.status_code==200 and response.mimetype=='text/csv'
    rows=list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
    assert rows==[['Time (UTC)','User','Action'],['2026-10-05T10:00:00+00:00','alice','Previous day action'],['2026-10-06T12:00:00+00:00','alice','Action, with comma']]

def test_audit_screen_limits_to_latest_500_and_zip_exports_all_events():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('audit-admin-all',generate_password_hash('password-long-123'),'Administrator')).lastrowid
        db().executemany('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',[(f'user-{index%3}',f'Event {index:04d}',f'2026-10-{(index%28)+1:02d}T12:00:00+00:00') for index in range(505)])
        db().commit()
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='audit-all-token')
    page=client.get('/audit').data.decode()
    assert 'Event 0504' in page and 'Event 0005' in page and 'Event 0004' not in page
    response=client.get('/audit/export-all.zip?actor=user-1')
    assert response.status_code==200 and response.mimetype=='application/zip'
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist()==['audit-events.csv']
        rows=list(csv.reader(io.StringIO(archive.read('audit-events.csv').decode('utf-8-sig'))))
    assert len(rows)==506 and rows[0]==['Time (UTC)','User','Action']
    assert rows[1][2]=='Event 0504' and rows[-1][2]=='Event 0000'