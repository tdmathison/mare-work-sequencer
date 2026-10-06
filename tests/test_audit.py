import csv,io
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