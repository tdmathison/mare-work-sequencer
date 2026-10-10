import hashlib
import io
import json
import sqlite3
import zipfile
import pytest
from app import app, db, run, ensure_package
from authorization import initialize_roles
from tagging import initialize, create, assignments, portable, validate_portable, restore, migrate_prototype


def fixture(role='User'):
    with app.app_context():
        initialize(db()); initialize_roles(db())
        uid=run('INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)',('tag-user','unused',role)).lastrowid
        cid=run("INSERT INTO cases(number,name,created,stage,owner,creator) VALUES('TAG-1','Tag analysis','2026',1,?,?)",(uid,uid)).lastrowid
        ensure_package(cid)
    client=app.test_client()
    with client.session_transaction() as session: session.update(uid=uid,version=1,csrf='tag-test')
    return client,cid,uid


def test_schema_uniqueness_assignment_and_case_deletion():
    client,cid,uid=fixture()
    with app.app_context():
        before=[tuple(r) for r in db().execute('SELECT * FROM cases')]
        initialize(db());initialize(db())
        assert before==[tuple(r) for r in db().execute('SELECT * FROM cases')]
        tid,changed=create(db(),' MAL-AsyncRat ');assert changed
        assert create(db(),'mal-asyncrat')==(tid,False)
        assert db().execute('SELECT name FROM tags').fetchone()[0]=='MAL-AsyncRat'
        db().commit()
    for _ in range(2): assert client.post(f'/cases/{cid}/tags/{tid}/assign',data={'csrf':'tag-test'}).status_code==302
    with app.app_context():
        assert len(assignments(db(),cid))==1
        assert assignments(db(),cid)[0]['assigned_by']=='tag-user'
    client.post(f'/cases/{cid}/tags/{tid}/remove',data={'csrf':'tag-test'})
    with app.app_context():assert assignments(db(),cid)==[]
    client.post(f'/cases/{cid}/tags/{tid}/assign',data={'csrf':'tag-test'})
    with app.app_context():
        db().execute('DELETE FROM cases WHERE id=?',(cid,));db().commit()
        assert not assignments(db()) and len(db().execute('SELECT * FROM tags').fetchall())==1
        assert not db().execute('PRAGMA foreign_key_check').fetchall()


def test_search_create_exact_partial_and_permissions():
    assert app.test_client().get('/tags').status_code==302
    client,cid,_=fixture()
    client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'MAL-AsyncRat'})
    client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'MAL-Async'})
    client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'mal-asyncrat'})
    rows=client.get('/tags/search?q=ASYNC').json['tags'];assert len(rows)==2
    assert len(client.get(f'/cases/{cid}/tags').json['tags'])==2
    assert b'TAGS' in client.get('/').data
    assert client.post(f'/tags/{rows[0]["id"]}/rename',data={'csrf':'tag-test','name':'No'}).status_code==403
    assert client.post('/tags/create',data={'name':'No CSRF'}).status_code==403
    assert client.post(f'/cases/{cid}/tags/999/assign',data={'csrf':'tag-test'}).status_code==404
    with app.app_context():
        db().execute("UPDATE users SET role='Reader'");db().execute("INSERT INTO roles VALUES('Reader','',0)");db().execute("INSERT INTO role_permissions VALUES('Reader','tags:read')");db().commit()
    assert client.get('/tags').status_code==200
    assert client.post('/tags/create',data={'csrf':'tag-test','name':'No'}).status_code==403
    assert client.get(f'/cases/{cid}/tags').status_code==403


def test_or_and_search_rename_merge_delete_audit():
    client,cid,_=fixture('Administrator')
    with app.app_context():
        one=create(db(),'One')[0];two=create(db(),'Two')[0]
        other=db().execute("INSERT INTO cases(number,name,stage,created) VALUES('TAG-2','Another case',1,'2026')").lastrowid;db().commit();ensure_package(other)
    for c,t in [(cid,one),(cid,two),(other,two)]:client.post(f'/cases/{c}/tags/{t}/assign',data={'csrf':'tag-test'})
    assert client.get(f'/?tag={one}&tag={two}&match=any').data.count(b'class="panel case-card mip-card"')==2
    assert client.get(f'/?tag={one}&tag={two}&match=all').data.count(b'class="panel case-card mip-card"')==1
    assert client.get(f'/?tag={two}&q=Another').data.count(b'class="panel case-card mip-card"')==1
    assert client.get(f'/?tag={two}&q=absent').data.count(b'class="panel case-card mip-card"')==0
    client.post(f'/tags/{one}/rename',data={'csrf':'tag-test','name':'New name'})
    assert b'New name' in client.get(f'/cases/{cid}').data
    client.post(f'/tags/{one}/rename',data={'csrf':'tag-test','name':'TWO'})
    with app.app_context():assert db().execute('SELECT name FROM tags WHERE id=?',(one,)).fetchone()[0]=='New name'
    client.post(f'/tags/{one}/merge',data={'csrf':'tag-test','destination':two})
    with app.app_context():assert len(assignments(db(),cid))==2
    client.post(f'/tags/{one}/merge',data={'csrf':'tag-test','destination':two,'confirm':'1'})
    with app.app_context():assert len(assignments(db(),cid))==1
    client.post(f'/tags/{two}/delete',data={'csrf':'tag-test','confirm':'1'})
    with app.app_context():
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2
        assert not assignments(db())
        log=' '.join(r[0] for r in db().execute('SELECT action FROM audit'))
        for action in ['Tag assigned','Tag renamed','Tags merged','Tag deleted']:assert action in log


def test_stage_locks_and_validation():
    client,cid,_=fixture()
    for stage in [0,3]:
        with app.app_context():db().execute('UPDATE cases SET stage=? WHERE id=?',(stage,cid));db().commit()
        assert client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'Locked'}).status_code==409
    for value in ['', 'x'*121, None, '\nBad']:
        with pytest.raises(ValueError):validate_portable({'schema_version':1,'tags':[value]})
    for value in [{'schema_version':True,'tags':[]},{'schema_version':2,'tags':[]},{'schema_version':1,'tags':['A','a']},{'schema_version':1,'tags':[],'extra':1}]:
        with pytest.raises(ValueError):validate_portable(value)
    assert validate_portable(None) is None


def rewrite_metadata(raw,change):
    with zipfile.ZipFile(io.BytesIO(raw)) as source:contents={n:source.read(n) for n in source.namelist()}
    path=next(n for n in contents if n.endswith('/case-data.json'));meta=json.loads(contents[path]);change(meta);contents[path]=json.dumps(meta).encode()
    manifest_path=next(n for n in contents if n.endswith('/manifest.json'));manifest=json.loads(contents[manifest_path]);entry=next(e for e in manifest['files'] if e['path']=='case-data.json');entry.update(size=len(contents[path]),sha256=hashlib.sha256(contents[path]).hexdigest());contents[manifest_path]=json.dumps(manifest).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for n,v in contents.items():archive.writestr(n,v)
    return out.getvalue()


def test_raw_full_and_legacy_restore():
    client,cid,_=fixture('Administrator')
    client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'Saved'})
    client.post('/tags/create',data={'csrf':'tag-test','name':'Unused'})
    raw=client.post(f'/cases/{cid}/backup',data={'csrf':'tag-test'}).data
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        meta=json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/case-data.json'))));assert meta['tagging']=={'schema_version':1,'tags':['Saved']}
    client.post('/import-export/import-raw',data={'csrf':'tag-test','backup':(io.BytesIO(raw),'raw.zip')})
    with app.app_context():assert len(assignments(db()))==2
    bad=rewrite_metadata(raw,lambda m:m.update(tagging={'schema_version':2,'tags':[]}))
    response=client.post('/import-export/import-raw',data={'csrf':'tag-test','backup':(io.BytesIO(bad),'bad.zip')},follow_redirects=True)
    assert b'Unsupported or malformed tag metadata' in response.data
    legacy=rewrite_metadata(raw,lambda m:m.pop('tagging'))
    client.post('/import-export/import-raw',data={'csrf':'tag-test','backup':(io.BytesIO(legacy),'old.zip')})
    with app.app_context():assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==3
    full=client.post('/import-export/export',data={'csrf':'tag-test'}).data
    with app.app_context():
        db().execute('DELETE FROM tags');db().commit()
    client.post('/import-export/import',data={'csrf':'tag-test','backup':(io.BytesIO(full),'full.zip')})
    with app.app_context():
        assert portable(db())['tags']==['Saved','Unused']
        assert len(assignments(db()))==2


def test_prototype_requires_explicit_preserving_migration(tmp_path):
    path=tmp_path/'prototype.db';connection=sqlite3.connect(path)
    connection.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT);CREATE TABLE cases(id INTEGER PRIMARY KEY,name TEXT);CREATE TABLE schema_migrations(name TEXT PRIMARY KEY);CREATE TABLE audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,created TEXT);CREATE TABLE tag_categories(id INTEGER PRIMARY KEY,name TEXT);CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT,category_id INTEGER,created TEXT);CREATE TABLE case_tags(case_id INTEGER,tag_id INTEGER,assigned TEXT,assigned_by INTEGER);INSERT INTO cases VALUES(1,'Preserved');INSERT INTO users VALUES(1,'actor');INSERT INTO tags VALUES(1,'Same',1,'2026');INSERT INTO tags VALUES(2,'SAME',2,'2026');INSERT INTO case_tags VALUES(1,1,'2026',1);INSERT INTO case_tags VALUES(1,2,'2026',1);''');connection.commit()
    assert not initialize(connection)
    assert connection.execute('SELECT count(*) FROM tags').fetchone()[0]==2
    connection.close();backup=migrate_prototype(path);assert backup.is_file()
    connection=sqlite3.connect(path);connection.row_factory=sqlite3.Row
    assert initialize(connection)
    assert connection.execute('SELECT name FROM cases').fetchone()[0]=='Preserved'
    assert len(assignments(connection))==1
    assert connection.execute('SELECT count(*) FROM prototype_tags').fetchone()[0]==2
    assert not connection.execute('PRAGMA foreign_key_check').fetchall()
    connection.close()


def test_async_case_tags_confirmed_without_redirect_or_flash():
    client,cid,_=fixture()
    headers={'Accept':'application/json'}
    response=client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':'Async'},headers=headers)
    assert response.status_code==200 and not response.headers.get('Location')
    tid=response.json['tags'][0]['id']
    assert response.json['tags'][0]['name']=='Async'
    response=client.post(f'/cases/{cid}/tags/{tid}/assign',data={'csrf':'tag-test'},headers=headers)
    assert len(response.json['tags'])==1
    response=client.post(f'/cases/{cid}/tags/create',data={'csrf':'tag-test','name':''},headers=headers)
    assert response.status_code==400 and response.json['error']
    response=client.post(f'/cases/{cid}/tags/{tid}/remove',data={'csrf':'tag-test'},headers=headers)
    assert response.status_code==200 and response.json['tags']==[]
    with client.session_transaction() as session:assert not session.get('_flashes')
    assert client.get(f'/cases/{cid}/tags').json['tags']==[]
