import hashlib,io,json,zipfile
from app import app,db,run,ensure_package,package,ROOT
from werkzeug.security import generate_password_hash
from reporting import OUTPUT
from docx import Document

def setup_backup_case():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('backup-user',generate_password_hash('password-long-123'),'User')).lastrowid
        cid=run("INSERT INTO cases(number,name,description,created,stage,owner,creator,creator_username) VALUES('SOURCE-01','Case one','Analysis case','2026',2,?,?,'backup-user')",(uid,uid)).lastrowid
        root=ensure_package(cid);(root/'reports/sections').mkdir(exist_ok=True)
        (root/'reports/sections/executive_summary.md').write_text('Saved executive summary.')
        (root/'scripts/decode.py').write_text('print(42)')
        (root/'reports/backups').mkdir();(root/'reports/backups/old.docx').write_bytes(b'old report')
        report=Document();report.add_paragraph('Final original content');report.save(root/OUTPUT)
        image='report-image-'+'a'*32+'.png';(root/'reports/sections/assets').mkdir();(root/'reports/sections/assets'/image).write_bytes(b'image bytes')
        run('INSERT INTO report_images(case_id,section,name,figure) VALUES(?,?,?,?)',(cid,'executive_summary',image,3));run('INSERT INTO figure_sequence VALUES(?,8)',(cid,))
        run("INSERT INTO notes(case_id,title,body,author,created,include_export) VALUES(?,'Private note','Saved internal finding','backup-user','2026',0)",(cid,))
        run("INSERT INTO tasks(case_id,title,body,state,priority,done,created) VALUES(?,'Decode','Investigate decoder','In Progress','High',0,'2026')",(cid,))
        run("INSERT INTO history(case_id,stage,author,created,outcome,reason) VALUES(?,1,'backup-user','2026','Done','Analysis work')",(cid,))
        second=run("INSERT INTO cases(number,name,created,stage) VALUES('SOURCE-02','Empty case','2026',0)").lastrowid;ensure_package(second)
    client=app.test_client()
    with client.session_transaction() as s:s.update(uid=uid,version=1,csrf='backup-token')
    def post(url,**data):return client.post(url,data={'csrf':'backup-token',**data})
    return client,cid,uid,post

def test_all_case_backup_round_trip_owners_ids_tables_and_files():
    client,cid,uid,post=setup_backup_case()
    sections=[{'id':'default','title':'Findings','description':'Primary analysis','rows':[['domain','evil.example.com','C2']]},{'id':'other','title':'Hashes','description':'Payloads','rows':[['sha256','b'*64,'File']]}]
    assert post(f'/cases/{cid}/indicators',sections=json.dumps(sections),revision='0').status_code==200
    assert post(f'/cases/{cid}/references',rows=json.dumps([['https://example.com/research','Background']]),revision='0').status_code==200
    assert b'IMPORT &amp; EXPORT' in client.get('/').data
    exported=post('/import-export/export');assert exported.status_code==200
    outer=zipfile.ZipFile(io.BytesIO(exported.data));index=json.loads(outer.read('backup.json'));assert len(index['cases'])==2
    raw=zipfile.ZipFile(io.BytesIO(outer.read(index['cases'][0]['path'])))
    assert any(p.endswith('/scripts/decode.py') for p in raw.namelist())
    assert any(p.endswith('/reports/sections/executive_summary.md') for p in raw.namelist())
    assert any(p.endswith('/case-data.json') for p in raw.namelist())
    assert not any('/backups/' in p for p in raw.namelist())
    with app.app_context():uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('importer',generate_password_hash('password-long-123'),'User')).lastrowid
    with client.session_transaction() as session:session['uid']=uid
    response=post('/import-export/import',backup=(io.BytesIO(exported.data),'backup.zip'));assert response.location=='/',client.get('/import-export').data.decode()
    with app.app_context():
        cases=db().execute('SELECT * FROM cases ORDER BY id').fetchall();assert len(cases)==4
        imported=cases[2];new=imported['id']
        assert imported['number'].startswith('MARE-') and imported['number'] not in ('SOURCE-01','SOURCE-02')
        assert imported['creator']==uid and imported['creator_username']=='importer' and imported['owner']==1 and imported['stage']==2
        assert db().execute('SELECT state FROM tasks WHERE case_id=?',(new,)).fetchone()[0]=='In Progress'
        assert db().execute('SELECT include_export FROM notes WHERE case_id=?',(new,)).fetchone()[0]==0
        assert db().execute('SELECT value FROM figure_sequence WHERE case_id=?',(new,)).fetchone()[0]==8
    assert package(new).joinpath('scripts/decode.py').read_text()=='print(42)'
    assert package(new).joinpath('reports/sections/executive_summary.md').read_text()=='Saved executive summary.'
    assert (package(new)/OUTPUT).read_bytes()==(package(cid)/OUTPUT).read_bytes()
    assert client.get(f'/cases/{new}/indicators').json['sections']==sections
    assert client.get(f'/cases/{new}/references').json['rows']==[['https://example.com/research','Background']]
    assert len(client.get(f'/cases/{new}/report-images').json['images'])==1
    post(f'/cases/{new}/stage',expected='0')
    with app.app_context():assert db().execute('SELECT stage FROM cases WHERE id=?',(new,)).fetchone()[0]==2
    post(f'/cases/{new}/owner',owner_id=str(uid))
    assert b'Saved executive summary.' in client.get(f'/cases/{new}').data
    post('/import-export/import',backup=(io.BytesIO(exported.data),'repeat.zip'))
    with app.app_context():
        numbers=[r[0] for r in db().execute('SELECT number FROM cases')];assert len(numbers)==6 and len(set(numbers))==6
    # Restore into an instance with no cases; source identities are not required.
    with app.app_context():
        connection=db();connection.execute('PRAGMA foreign_keys=OFF')
        for table in ('cases','notes','tasks','history','artifacts','readiness','report_images','figure_sequence','indicator_tables','indicator_sections','reference_tables'):connection.execute(f'DELETE FROM {table}')
        connection.commit();connection.execute('PRAGMA foreign_keys=ON')
    import shutil
    shutil.rmtree(ROOT/'cases')
    assert post('/import-export/import',backup=(io.BytesIO(exported.data),'new-instance.zip')).location=='/'
    with app.app_context():assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2

def test_invalid_backup_rejected_without_partial_import():
    client,cid,uid,post=setup_backup_case();exported=post('/import-export/export').data
    def rewrite(mutate):
        source=zipfile.ZipFile(io.BytesIO(exported));data={p:source.read(p) for p in source.namelist()};mutate(data);out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for p,value in data.items():archive.writestr(p,value)
        return out.getvalue()
    def malicious_path(data):data['../escape.txt']=b'escape'
    def bad_hash(data):index=json.loads(data['backup.json']);index['cases'][1]['sha256']='0'*64;data['backup.json']=json.dumps(index).encode()
    def traversal_inner(data):
        index=json.loads(data['backup.json']);entry=index['cases'][0];raw=zipfile.ZipFile(io.BytesIO(data[entry['path']]));out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as archive:
            for p in raw.namelist():archive.writestr(p,raw.read(p))
            archive.writestr(raw.namelist()[0].split('/')[0]+'/scripts/../../escape.txt',b'bad')
        data[entry['path']]=out.getvalue();entry['size']=len(out.getvalue());entry['sha256']=hashlib.sha256(out.getvalue()).hexdigest();data['backup.json']=json.dumps(index).encode()
    for value in [b'not zip',rewrite(malicious_path),rewrite(bad_hash),rewrite(traversal_inner)]:
        assert post('/import-export/import',backup=(io.BytesIO(value),'invalid.zip')).location=='/import-export'
        with app.app_context():assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2
    # A late filesystem conflict rolls back database rows, numbering, and earlier moves.
    orphan=ROOT/'cases'/'3';orphan.mkdir();(orphan/'keep.txt').write_text('Existing orphan')
    with app.app_context():before=db().execute('SELECT value FROM case_sequence').fetchone()[0]
    assert post('/import-export/import',backup=(io.BytesIO(exported),'conflict.zip')).location=='/import-export'
    assert (orphan/'keep.txt').read_text()=='Existing orphan'
    with app.app_context():
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2
        assert db().execute('SELECT value FROM case_sequence').fetchone()[0]==before
    import shutil
    shutil.rmtree(orphan)
    assert not (ROOT/'escape.txt').exists()
    assert not list(ROOT.glob('case-import-*'))
    assert client.post('/import-export/export',data={}).status_code==403
    with app.app_context():run("INSERT INTO report_jobs(id,case_id,status) VALUES('busy-backup',?,'running')",(cid,))
    assert post('/import-export/export').location=='/import-export'

def test_single_raw_backup_restores_stage_owner_and_python_files():
    client,cid,uid,post=setup_backup_case()
    with app.app_context():
        run("INSERT INTO artifacts VALUES(?,'scripts/decode.py','Decoder','')",(cid,))
        identity=dict(db().execute('SELECT username,user_uuid FROM users WHERE id=?',(uid,)).fetchone())
    exported=post(f'/cases/{cid}/backup');assert exported.status_code==200
    archive=zipfile.ZipFile(io.BytesIO(exported.data));names=archive.namelist()
    assert any(p.endswith('/scripts/decode_py.txt') for p in names) and not any(p.endswith('.py') for p in names)
    metadata=json.loads(archive.read(next(p for p in names if p.endswith('/case-data.json'))))
    assert metadata['case']['stage']==2 and metadata['case']['assigned_user']==identity
    assert post('/import-export/import-raw',backup=(io.BytesIO(exported.data),'single.zip')).location=='/'
    with app.app_context():
        imported=db().execute('SELECT * FROM cases ORDER BY id DESC LIMIT 1').fetchone();new=imported['id']
        assert imported['stage']==2 and imported['owner']==uid
        assert db().execute('SELECT description FROM artifacts WHERE case_id=? AND path=?',(new,'scripts/decode.py')).fetchone()[0]=='Decoder'
    assert (package(new)/'scripts/decode.py').read_text()=='print(42)'
    assert not (package(new)/'scripts/decode_py.txt').exists()
    assert post(f'/cases/{new}/notes',body='Resumed analysis').status_code==302
    # Regular RAW export now also carries the import metadata.
    raw=post(f'/cases/{cid}/archive',archive_type='raw',acknowledge='1');assert raw.status_code==200
    assert post('/import-export/import-raw',backup=(io.BytesIO(raw.data),'raw.zip')).location=='/'


def test_same_username_different_identifier_stays_unassigned_preserving_stage():
    client,cid,uid,post=setup_backup_case();exported=post(f'/cases/{cid}/backup').data
    with app.app_context():
        old_uuid=db().execute('SELECT user_uuid FROM users WHERE id=?',(uid,)).fetchone()[0]
        run('UPDATE cases SET owner=NULL WHERE owner=?',(uid,))
        run('UPDATE cases SET creator=NULL WHERE creator=?',(uid,))
        run('DELETE FROM users WHERE id=?',(uid,))
        replacement=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('backup-user',generate_password_hash('password-long-123'),'User')).lastrowid
        assert db().execute('SELECT user_uuid FROM users WHERE id=?',(replacement,)).fetchone()[0]!=old_uuid
    with client.session_transaction() as session:session['uid']=replacement
    assert post('/import-export/import-raw',backup=(io.BytesIO(exported),'single.zip')).location=='/'
    with app.app_context():
        imported=db().execute('SELECT * FROM cases ORDER BY id DESC LIMIT 1').fetchone();new=imported['id']
        assert imported['stage']==2 and imported['owner'] is None
    assert post(f'/cases/{new}/notes',body='Blocked').status_code==409
    assert b'Assign an active owner' in client.get(f'/cases/{new}').data
    post(f'/cases/{new}/owner',owner_id=str(replacement))
    assert post(f'/cases/{new}/notes',body='Resumed').status_code==302
    with app.app_context():assert db().execute('SELECT stage FROM cases WHERE id=?',(new,)).fetchone()[0]==2


def test_completed_import_can_assign_owner_without_reopening():
    client,cid,uid,post=setup_backup_case()
    with app.app_context():run('UPDATE cases SET stage=3,owner=NULL WHERE id=?',(cid,))
    exported=post(f'/cases/{cid}/backup').data
    post('/import-export/import-raw',backup=(io.BytesIO(exported),'completed.zip'))
    with app.app_context():
        imported=db().execute('SELECT * FROM cases ORDER BY id DESC LIMIT 1').fetchone();new=imported['id']
        assert imported['stage']==3 and imported['owner'] is None
    assert post(f'/cases/{new}/owner',owner_id=str(uid)).status_code==302
    with app.app_context():assert db().execute('SELECT stage FROM cases WHERE id=?',(new,)).fetchone()[0]==3
    assert post(f'/cases/{new}/archive',acknowledge='1').status_code==200
    assert post(f'/cases/{new}/notes',body='Read-only').status_code==409


def test_installation_database_backup_restores_accounts_keys_and_content(tmp_path):
    import sqlite3
    client,cid,uid,post=setup_backup_case()
    assert post('/account/database-backup').status_code==403
    with app.app_context():
        run("UPDATE users SET role='Administrator' WHERE id=?",(uid,))
        original=dict(db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    template_dir=ROOT/'users'/str(uid)/'templates';template_dir.mkdir(parents=True);(template_dir/'saved.docx').write_bytes(b'template')
    backup=post('/account/database-backup');assert backup.status_code==200
    archive=zipfile.ZipFile(io.BytesIO(backup.data));names=archive.namelist()
    assert 'data/workflow.sqlite3' in names and 'data/session.key' in names and 'data/api-keys.key' not in names
    assert f'data/cases/{cid}/mip/scripts/decode.py' in names
    assert f'data/users/{uid}/templates/saved.docx' in names
    assert f'data/cases/{cid}/mip/reports/backups/old.docx' in names
    snapshot=tmp_path/'restored.sqlite3';snapshot.write_bytes(archive.read('data/workflow.sqlite3'))
    connection=sqlite3.connect(snapshot);connection.row_factory=sqlite3.Row
    restored=dict(connection.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone());connection.close()
    assert restored['password']==original['password'] and restored['user_uuid']==original['user_uuid']
