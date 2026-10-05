import sqlite3
import pytest
from app import app,db,run,ROOT,package
from werkzeug.security import generate_password_hash

def test_delete_case_contents_confirmation_and_reserved_number():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('delete-user',generate_password_hash('password-long-123'),'User')).lastrowid
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='delete-token')
    def post(url,**data):return client.post(url,data={'csrf':'delete-token',**data})
    created=post('/cases',name='Accidental case');cid=int(created.location.rsplit('/',1)[1]);url=f'/cases/{cid}'
    with app.app_context():
        number=db().execute('SELECT number FROM cases WHERE id=?',(cid,)).fetchone()[0]
        run("INSERT INTO notes(case_id,body) VALUES(?,'test note')",(cid,))
        run("INSERT INTO indicator_tables VALUES(?, ?, ?, 1)",(cid,'["type","value","description"]','[]'))
        run("INSERT INTO reference_tables VALUES(?, '[]', 1)",(cid,))
        with pytest.raises(sqlite3.IntegrityError):run("UPDATE cases SET number='tampered' WHERE id=?",(cid,))
        db().rollback()
    (package(cid)/'supporting/evidence.txt').write_text('evidence')
    page=client.get(url).data
    assert b'Destructive commands' in page and b'<input value=' not in page
    assert client.get(url+'/delete').status_code==405
    assert client.post(url+'/delete',data={'confirm_number':number}).status_code==403
    post(url+'/delete',confirm_number='incorrect')
    assert client.get(url).status_code==200 and package(cid).exists()
    with app.app_context():run("INSERT INTO report_jobs(id,case_id,status) VALUES('delete-job',?,'running')",(cid,))
    post(url+'/delete',confirm_number=number)
    assert client.get(url).status_code==200
    with app.app_context():run("UPDATE report_jobs SET status='completed' WHERE id='delete-job'")
    assert post(url+'/delete',confirm_number=number).location=='/'
    assert client.get(url).status_code==404 and not (ROOT/'cases'/str(cid)).exists()
    with app.app_context():
        for table in ('notes','indicator_tables','reference_tables','report_jobs'):
            assert db().execute(f'SELECT count(*) FROM {table} WHERE case_id=?',(cid,)).fetchone()[0]==0
        assert db().execute('SELECT 1 FROM reserved_case_numbers WHERE number=?',(number,)).fetchone()
        run('UPDATE case_sequence SET value=0 WHERE id=1')
    next_case=post('/cases',name='New case');next_id=int(next_case.location.rsplit('/',1)[1])
    with app.app_context():assert db().execute('SELECT number FROM cases WHERE id=?',(next_id,)).fetchone()[0]!=number
    with app.app_context():run('UPDATE cases SET stage=3 WHERE id=?',(next_id,));next_number=db().execute('SELECT number FROM cases WHERE id=?',(next_id,)).fetchone()[0]
    assert post(f'/cases/{next_id}/delete',confirm_number=next_number).location=='/'
