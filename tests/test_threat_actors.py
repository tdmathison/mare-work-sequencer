import copy
import hashlib
import io
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import app, db, ROOT
from family_reports import storage_path
from family_portable import export_library, validate_library, check_conflicts, restore_library
from profile_types import ACTOR
from tagging import create as create_tag
from test_malware_families import fixture, create as create_family, edit as edit_family, profile as family_profile
from test_family_reports import pdf
from threat_actors import associations, initialize


def post(client, path, **values):
    return client.post(path, data={'csrf':'family-csrf', **values})


def actor_record(aid):
    with app.app_context():
        return dict(db().execute('SELECT * FROM threat_actors WHERE id=?',(aid,)).fetchone())


def create(client, name='APT test', tag='TA_TEST', **extra):
    response = post(client, '/threat-actors/new', name=name, tag=tag, **extra)
    assert response.status_code == 302, response.text
    return response.location.split('/')[-1].split('?')[0]


def edit(client, aid, **extra):
    row=actor_record(aid)
    with app.app_context():
        tag=db().execute('SELECT name FROM tags WHERE id=?',(row['tag_id'],)).fetchone()[0]
        families=[r['family_uuid'] for r in associations(db(), aid)]
    values = dict(name=row['name'], tag=tag, version=row['version'], aliases=json.loads(row['aliases']), aliases_present='1', known_families=families)
    values.update(extra)
    return post(client, f'/threat-actors/{aid}/edit', **values)


def setup():
    client, uid, cid, tid=fixture()
    with app.app_context():
        initialize(db())
        actor_tag=create_tag(db(),'TA_TEST')[0]
        db().execute('INSERT INTO case_tags VALUES(?,?,?,?)',(cid, actor_tag,'2026',uid));db().commit()
    return client, uid, cid, actor_tag


def upload(client, aid, content=None):
    response=post(client,f'/threat-actors/{aid}/reports/upload',version=actor_record(aid)['version'],reports=(io.BytesIO(content or pdf()),'actor.pdf'))
    assert response.status_code==302,response.text
    with app.app_context():
        row=db().execute('SELECT * FROM actor_reports WHERE actor_id=?',(aid,)).fetchone()
        return dict(row) if row else None


def test_workspace_aliases_history_associations_and_safe_rendering():
    c, uid, cid, tid=setup()
    family=create_family(c)
    with app.app_context():
        before=[tuple(r) for r in db().execute('SELECT * FROM case_tags')]
    aid=create(c,name='<script>unsafe()</script>',aliases=[' First name ','Second Name'],known_families=[family])
    assert actor_record(aid)['tag_id']==tid
    assert json.loads(actor_record(aid)['aliases'])==['First name','Second Name']
    html=c.get('/threat-actors/'+aid).text
    assert '&lt;script&gt;unsafe()&lt;/script&gt;' in html and '<script>unsafe()' not in html
    assert 'Known Malware Families' in html and '/malware-families/'+family in html
    assert 'THREAT ACTORS' in html
    assert c.get('/threat-actors?q=second+NAME').text.count('class="family-choice"')==1
    history=c.get('/threat-actors/'+aid+'?tab=history').text
    assert 'MARE-FAMILY-1' in history and 'Cases currently using TA_TEST' in history
    assert '1 linked cases' in history
    assert edit(c,aid,aliases=['Second Name','Third alternative']).status_code==302
    assert json.loads(actor_record(aid)['aliases'])==['Second Name','Third alternative']
    assert edit(c,aid,known_families=[]).status_code==302
    assert 'No families associated.' in c.get('/threat-actors/'+aid).text
    with app.app_context():
        assert before==[tuple(r) for r in db().execute('SELECT * FROM case_tags')]
        assert db().execute("SELECT count(*) FROM tags WHERE name IN ('FIRST_NAME','SECOND_NAME','THIRD_ALTERNATIVE')").fetchone()[0]==0
    form=c.get('/threat-actors/'+aid+'/edit').text
    labels=['Threat actor name','>Aliases</label>','<label>Tag','Short description','Long description','Known Malware Families']
    assert [form.index(value) for value in labels]==sorted(form.index(value) for value in labels)
    assert '<label>Attribution notes' not in form


@pytest.mark.parametrize('tag',['MAL_TEST','TA_','TA_BAD-NAME','TA_A B'])
def test_namespace_and_atomic_invalid_creation(tag):
    c,*_=setup()
    result=post(c,'/threat-actors/new',name='Invalid',tag=tag)
    assert result.status_code==400
    with app.app_context():
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==0


def test_validation_conflicts_aliases_and_failed_relationships():
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    for values in (['RedLine','redline'],[''],['a'*201],[str(n) for n in range(51)]):
        response=edit(c,aid,aliases=values)
        assert response.status_code==400
    failed=edit(c,aid,name='',aliases=['Retained alias'],known_families=[family])
    assert failed.status_code==400 and 'Retained alias' in failed.text and f'value="{family}"' in failed.text
    assert edit(c,aid,known_families=[family,family]).status_code==400
    unavailable=str(uuid.uuid4())
    response=edit(c,aid,known_families=[unavailable])
    assert response.status_code==409 and f'value="{unavailable}"' in response.text
    with app.app_context():
        assert [r['family_uuid'] for r in associations(db(),aid)]==[family]
    old=actor_record(aid)['version']
    assert edit(c,aid,name='New').status_code==302
    assert edit(c,aid,version=old,aliases=['Preserved']).status_code==409


def test_relink_protections_and_family_deleted_or_relinked():
    c,uid,cid,tid=setup();family=create_family(c);aid=create(c,known_families=[family])
    assert edit(c,aid,tag='TA_NEW').status_code==302
    assert 'MARE-FAMILY-1' not in c.get('/threat-actors/'+aid+'?tab=history').text
    with app.app_context():
        assert db().execute('SELECT 1 FROM case_tags WHERE case_id=? AND tag_id=?',(cid,tid)).fetchone()
        current=actor_record(aid)['tag_id']
        for sql in ("DELETE FROM tags WHERE id=?", "UPDATE tags SET name='MAL_WRONG',normalized_name='MAL_WRONG' WHERE id=?"):
            with pytest.raises(sqlite3.IntegrityError):
                db().execute(sql,(current,))
            db().rollback()
    assert edit_family(c,family,tag='MAL_RELINKED').status_code==302
    html=c.get('/threat-actors/'+aid).text
    assert 'MAL_RELINKED' in html and 'tag changed from MAL_EXISTING' in html
    version=actor_record(aid)['version']
    response=post(c,'/malware-families/'+family+'/delete',version=family_profile(family)['version'],confirm_name=family_profile(family)['name'])
    assert response.status_code==302
    assert 'Unavailable (profile deleted)' in c.get('/threat-actors/'+aid).text
    assert actor_record(aid)['version']>version
    assert edit(c,aid,known_families=[]).status_code==302


def test_tags_prefill_read_only_navigation_and_concurrent_creation():
    c,uid,cid,tid=setup()
    assert 'Create threat actor' in c.get('/tags').text
    with app.app_context():
        count=db().execute('SELECT count(*) FROM tags').fetchone()[0]
    page=c.get('/threat-actors/new?tag_id='+str(tid))
    assert page.status_code==200 and 'value="TA_TEST"' in page.text and 'will be reused' in page.text
    with app.app_context():
        assert db().execute('SELECT count(*) FROM tags').fetchone()[0]==count
    def creator(index):
        client=app.test_client()
        with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='family-csrf')
        return post(client,'/threat-actors/new',name='Concurrent '+str(index),tag='TA_TEST').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(creator,range(2)))==[302,409]
    with app.app_context():
        assert db().execute('SELECT count(*) FROM threat_actors WHERE tag_id=?',(tid,)).fetchone()[0]==1
        aid=db().execute('SELECT id FROM threat_actors WHERE tag_id=?',(tid,)).fetchone()[0]
    assert 'View threat actor' in c.get('/tags').text
    assert c.get('/threat-actors/new?tag_id='+str(tid)).location.endswith(aid+'?tab=overview')


def test_osint_reports_permissions_delete_and_cleanup():
    c,uid,cid,tid=setup();family=create_family(c);aid=create(c,known_families=[family])
    assert post(c,f'/threat-actors/{aid}/osint/new',version=actor_record(aid)['version'],title='Unsafe',url='javascript:alert(1)',position=1).status_code==400
    for position,title in [(1,'Second'),(1,'First')]:
        assert post(c,f'/threat-actors/{aid}/osint/new',version=actor_record(aid)['version'],title=title,url='https://example.com/'+title,position=position).status_code==302
    with app.app_context():
        rows=db().execute('SELECT * FROM actor_osint WHERE actor_id=? ORDER BY position',(aid,)).fetchall()
        assert [r['title'] for r in rows]==['First','Second']
        eid=rows[0]['id']
    assert post(c,f'/threat-actors/{aid}/osint/{eid}/edit',version=actor_record(aid)['version'],title='Edited',url='https://example.com/edited',position=2).status_code==302
    report=upload(c,aid)
    downloaded=c.get(f'/threat-actors/{aid}/reports/{report["id"]}/download')
    assert downloaded.data==pdf() and downloaded.headers['X-Content-Type-Options']=='nosniff'
    assert post(c,f'/threat-actors/{aid}/reports/{report["id"]}/edit',version=actor_record(aid)['version'],title='Actor research',description='Private').status_code==302
    anonymous=app.test_client()
    for url in ('/threat-actors',f'/threat-actors/{aid}',f'/threat-actors/{aid}/reports/{report["id"]}/download','/threat-actors/families/search'):
        assert anonymous.get(url).status_code==302
    assert c.post(f'/threat-actors/{aid}/delete',data={'confirm_name':'APT test'}).status_code==403
    with app.app_context():
        db().execute("UPDATE users SET role='User' WHERE id=?",(uid,));db().commit()
    assert c.get('/threat-actors/'+aid).status_code==200
    assert c.get('/threat-actors/'+aid+'/edit').status_code==403
    assert c.get(f'/threat-actors/{aid}/reports/{report["id"]}/download').status_code==200
    with app.app_context():
        db().execute("UPDATE users SET role='Restricted' WHERE id=?",(uid,));db().commit()
    assert c.get('/threat-actors/'+aid).status_code==403
    assert c.get(f'/threat-actors/{aid}/reports/{report["id"]}/download').status_code==403
    with app.app_context():
        db().execute("UPDATE users SET role='Administrator' WHERE id=?",(uid,));db().commit()
    response=post(c,'/threat-actors/'+aid+'/delete',version=actor_record(aid)['version'],confirm_name='APT test')
    assert response.status_code==302
    assert not storage_path(ROOT,report['id'],spec=ACTOR).exists()
    with app.app_context():
        assert db().execute('SELECT count(*) FROM actor_osint').fetchone()[0]==0
        assert db().execute('SELECT count(*) FROM actor_reports').fetchone()[0]==0
        assert db().execute('SELECT count(*) FROM actor_families').fetchone()[0]==0
        assert db().execute('SELECT 1 FROM tags WHERE id=?',(tid,)).fetchone()
        assert db().execute('SELECT 1 FROM case_tags WHERE case_id=? AND tag_id=?',(cid,tid)).fetchone()
        assert db().execute('SELECT 1 FROM malware_families WHERE id=?',(family,)).fetchone()
        assert db().execute("SELECT 1 FROM audit WHERE action LIKE 'Threat actor%'").fetchone()


def test_portable_roundtrip_dependencies_identity_and_report_bytes(tmp_path):
    c,*_=setup();family=create_family(c);aid=create(c,aliases=['First','Second'],known_families=[family]);report=upload(c,aid)
    staged=tmp_path/'staged';(staged/'actor-reports').mkdir(parents=True)
    (staged/report['storage_ref']).write_bytes(pdf())
    with app.app_context():
        data=export_library(db(),ROOT)
        validate_library(data,ROOT)
        assert data['actors'][0]['known_families'][0]['family_uuid']==family
        assert check_conflicts(db(),ROOT,data)=={family}
        # Simulate a clean shared catalog with different numeric tag IDs.
        db().execute('DELETE FROM threat_actors');db().execute('DELETE FROM malware_families');db().execute('DELETE FROM case_tags');db().execute('DELETE FROM tags');db().commit()
        storage_path(ROOT,report['id'],spec=ACTOR).unlink()
        create_tag(db(),'UNRELATED');db().commit()
        restore_library(db(),ROOT,staged,data)
        assert [r['family_id'] for r in associations(db(),aid)]==[family]
        restored=db().execute('SELECT * FROM actor_reports').fetchone()
        assert hashlib.sha256(storage_path(ROOT,restored['id'],spec=ACTOR).read_bytes()).hexdigest()==report['sha256']
        assert json.loads(db().execute('SELECT aliases FROM threat_actors WHERE id=?',(aid,)).fetchone()[0])==['First','Second']
        restore_library(db(),ROOT,staged,data)  # Idempotent reports and relationships.
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==1
        bad=copy.deepcopy(data);bad['actors'][0]['known_families'][0]['family_uuid']=str(uuid.uuid4())
        with pytest.raises(ValueError):check_conflicts(db(),ROOT,bad)
        legacy={key:value for key,value in data.items() if key!='actors'}
        restore_library(db(),ROOT,staged,legacy)
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==1


def test_dependency_errors_do_not_match_names_or_reused_tags():
    from threat_actors import check_dependencies
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    with app.app_context():
        data=export_library(db(),ROOT)
        actor=copy.deepcopy(data['actors'][0])
        actor['known_families'][0]['family_uuid']=str(uuid.uuid4())
        with pytest.raises(ValueError,match='dependency unavailable or changed'):
            check_dependencies(db(),[actor],[])
        actor=copy.deepcopy(data['actors'][0])
        actor['known_families'][0]['target_tag_identity']='f'*32
        with pytest.raises(ValueError,match='dependency unavailable or changed'):
            check_dependencies(db(),[actor],data['families'])


def test_cross_profile_restore_rolls_back_records_and_file_publication(tmp_path,monkeypatch):
    from family_reports import FileChanges
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family]);actor_report=upload(c,aid)
    assert post(c,f'/malware-families/{family}/reports/upload',version=family_profile(family)['version'],reports=(io.BytesIO(pdf()),'family.pdf')).status_code==302
    staged=tmp_path/'staged'
    with app.app_context():
        data=export_library(db(),ROOT)
        for profile in data['families']+data['actors']:
            for report in profile['reports']:
                target=staged/report['storage_ref'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/report['storage_ref']).read_bytes())
        db().execute('DELETE FROM threat_actors');db().execute('DELETE FROM malware_families');db().commit()
        for profile in data['families']+data['actors']:
            for report in profile['reports']:(ROOT/report['storage_ref']).unlink()
        publish=FileChanges.publish
        def fail(self,aid):
            if self.spec.actor:raise OSError('Injected actor publication failure')
            return publish(self,aid)
        monkeypatch.setattr(FileChanges,'publish',fail)
        with pytest.raises(OSError,match='Injected'):
            restore_library(db(),ROOT,staged,data)
        assert db().execute('SELECT count(*) FROM malware_families').fetchone()[0]==0
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==0
        for profile in data['families']+data['actors']:
            for report in profile['reports']:assert not (ROOT/report['storage_ref']).exists()


def test_encrypted_selective_and_complete_actor_backup(tmp_path):
    import os,subprocess,sys
    from test_backup_workspace import export,inspect,post as backup_post,wait
    c,uid,cid,tid=setup();family=create_family(c);aid=create(c,aliases=['Ordered first','Second name'],known_families=[family]);report=upload(c,aid)
    create_family(c,name='Unrelated family',tag='MAL_UNRELATED')
    from werkzeug.security import generate_password_hash
    with app.app_context():
        db().execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash('source-actor-password'),uid));db().commit()
    # Unified backup helper's session token; actor CRUD data is already saved.
    with c.session_transaction() as session:session['csrf']='backup-workspace'
    selective,job=export(c,['actors'],password='')
    assert job['manifest']['areas']==['actors']
    assert job['manifest']['dependencies']==['families','tags']
    assert job['manifest']['counts']['cases']==0
    assert job['manifest']['counts']['threat_actors']==1
    assert job['manifest']['counts']['malware_families']==1
    complete,_=export(c,complete=True)
    for kind,archive in [('selective',selective),('complete',complete)]:
        source=tmp_path/(kind+'.zip');source.write_bytes(archive)
        destination=tmp_path/('dest-'+kind)
        code=r'''
import io,time,json,hashlib
from app import app,db,ROOT
from authorization import initialize_roles
from werkzeug.security import generate_password_hash
from tagging import create
with app.app_context():
    uid=db().execute("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('destination',generate_password_hash('destination-password'),'Administrator')).lastrowid
    create(db(),'UNRELATED_TAG');db().commit()
c=app.test_client()
with c.session_transaction() as s:s.update(uid=uid,version=1,csrf='roundtrip')
r=c.post('/backup-restore/jobs',data={'csrf':'roundtrip','kind':'inspect','passphrase':'PASSPHRASE','archive':(io.BytesIO(open('SOURCE','rb').read()),'backup.zip')},content_type='multipart/form-data');assert r.status_code==202,r.text
jid=r.json['id']
def wait():
    for _ in range(600):
        value=c.get('/backup-restore/jobs/'+jid).json
        if value['state'] not in ('running','queued'):return value
        time.sleep(.02)
    raise AssertionError('Timed out')
value=wait();assert value['state']=='preview' and not value['preview']['conflicts'] and not value['preview']['blocking'],value
r=c.post('/backup-restore/jobs/'+jid+'/apply',data={'csrf':'roundtrip','ack':'REPLACE'});assert r.status_code==202,r.text
service=app.extensions['backup_workspace']
for _ in range(600):
    value=json.loads((service.directory/jid/'job.json').read_text())
    if value['state'] not in ('running','queued'):break
    time.sleep(.02)
assert value['state']=='completed',value
with app.app_context():
    actor=db().execute('SELECT * FROM threat_actors').fetchone();assert actor['id']=='ACTOR_ID'
    assert json.loads(actor['aliases'])==['Ordered first','Second name']
    link=db().execute('SELECT * FROM actor_families').fetchone();assert link['family_id']=='FAMILY_ID' and link['family_uuid']=='FAMILY_ID'
    family=db().execute('SELECT * FROM malware_families WHERE id=?',(link['family_id'],)).fetchone();assert family['id']==link['family_id']
    report=db().execute('SELECT * FROM actor_reports').fetchone();assert report['actor_id']==actor['id']
    assert hashlib.sha256((ROOT/report['storage_ref']).read_bytes()).hexdigest()=='REPORT_HASH'
    if 'KIND'=='selective':
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==0
        assert db().execute('SELECT name FROM tags WHERE id=?',(actor['tag_id'],)).fetchone()[0]=='TA_TEST'
        assert actor['tag_id']!=int('ORIGINAL_TAG_ID')
'''.replace('SOURCE',str(source)).replace('PASSPHRASE','' if kind=='selective' else 'a strong recovery passphrase').replace('ACTOR_ID',aid).replace('FAMILY_ID',family).replace('REPORT_HASH',report['sha256']).replace('KIND',kind).replace('ORIGINAL_TAG_ID',str(tid))
        result=__import__('subprocess').run([sys.executable,'-c',code],env={**os.environ,'MARE_DATA_DIR':str(destination)},capture_output=True,text=True,timeout=45)
        assert result.returncode==0,result.stdout+result.stderr


def test_missing_dependency_is_a_resolvable_actor_skip(tmp_path):
    from backup_areas import resolve
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    with app.app_context():
        data=export_library(db(),ROOT)
        data['actors'][0]['known_families'][0]['family_uuid']=str(uuid.uuid4())
        db().execute('DELETE FROM threat_actors');db().commit()
        (tmp_path/'family-library.json').write_text(json.dumps(data))
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{})
        assert any(row['key']=='actor:'+aid and 'dependency unavailable' in row['label'] for row in conflicts)
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{'actor:'+aid:'keep'})
        assert not conflicts and planned['actors']==[]
        assert db().execute('SELECT count(*) FROM threat_actors').fetchone()[0]==0


def test_report_remove_reject_invalid_upload_and_case_permission_boundary():
    c,uid,*_=setup();aid=create(c)
    first=upload(c,aid)
    assert post(c,f'/threat-actors/{aid}/reports/upload',version=actor_record(aid)['version'],reports=(io.BytesIO(b'not PDF'),'bad.pdf')).status_code==302
    with app.app_context():
        assert db().execute('SELECT count(*) FROM actor_reports').fetchone()[0]==1
    assert post(c,f'/threat-actors/{aid}/reports/{first["id"]}/delete',version=actor_record(aid)['version'],confirm='1').status_code==302
    assert not storage_path(ROOT,first['id'],spec=ACTOR).exists()
    assert c.get(f'/threat-actors/{aid}/reports/{first["id"]}/download').status_code==404
    assert post(c,f'/threat-actors/{aid}/osint/new',version=actor_record(aid)['version'],title='Delete me',url='https://example.com',position=1).status_code==302
    with app.app_context():
        eid=db().execute('SELECT id FROM actor_osint').fetchone()[0]
    assert post(c,f'/threat-actors/{aid}/osint/{eid}/delete',version=actor_record(aid)['version']).status_code==302
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('Profile Reader')")
        db().execute("INSERT INTO role_permissions VALUES('Profile Reader','tags:read')")
        db().execute("UPDATE users SET role='Profile Reader' WHERE id=?",(uid,));db().commit()
    html=c.get('/threat-actors/'+aid+'?tab=history').text
    assert 'Case history requires case read permission.' in html and 'MARE-FAMILY-1' not in html


def test_v2_complete_backup_without_actors_upgrades_safely(tmp_path):
    import zipfile
    from test_malware_families import make_backup
    from installation_backup import restore_installation, ACTOR_TABLES
    from backup_workspace import schema
    c,*_=setup();create_family(c)
    data=make_backup(c)
    snapshot=tmp_path/'legacy.sqlite3'
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        snapshot.write_bytes(source.read('data/workflow.sqlite3'))
        with sqlite3.connect(snapshot) as connection:
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'actor_%'").fetchall():
                connection.execute('DROP TRIGGER "'+row[0]+'"')
            for table in ('actor_families','actor_osint','actor_reports','actor_import_state','threat_actors'):
                connection.execute('DROP TABLE '+table)
            connection.execute("DELETE FROM schema_migrations WHERE name IN ('threat-actors-v1','actor-reports-v1')")
        old=tmp_path/'legacy-v2.zip';content=snapshot.read_bytes()
        with zipfile.ZipFile(old,'w') as target:
            for entry in source.infolist():
                payload=source.read(entry)
                if entry.filename=='data/workflow.sqlite3':payload=content
                if entry.filename=='installation.json':
                    manifest=json.loads(payload);manifest['schema']='mare-installation-backup/2';manifest['required_migration']='family-reports-v1'
                    manifest['counts']={key:value for key,value in manifest['counts'].items() if key not in ACTOR_TABLES}
                    manifest['files']['data/workflow.sqlite3']={'size':len(content),'sha256':hashlib.sha256(content).hexdigest()}
                    payload=json.dumps(manifest).encode()
                target.writestr(entry,payload)
    destination=tmp_path/'recovered';restore_installation(old,destination)
    with sqlite3.connect(destination/'workflow.sqlite3') as connection:
        assert connection.execute('SELECT count(*) FROM threat_actors').fetchone()[0]==0
        assert connection.execute('SELECT count(*) FROM malware_families').fetchone()[0]==1
        assert schema(connection)==app.extensions['backup_workspace'].expected_schema


def test_deleted_association_requires_explicit_unavailable_import_choice(tmp_path):
    from backup_areas import resolve
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    assert post(c,'/malware-families/'+family+'/delete',version=family_profile(family)['version'],confirm_name=family_profile(family)['name']).status_code==302
    with app.app_context():
        data=export_library(db(),ROOT)
        assert data['actors'][0]['known_families'][0]['available'] is False
        db().execute('DELETE FROM threat_actors');db().commit()
        (tmp_path/'family-library.json').write_text(json.dumps(data))
        key='actor-unavailable:'+aid+':'+family
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{})
        assert any(conflict['key']==key for conflict in conflicts)
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{key:'retain'})
        assert not conflicts
        restore_library(db(),ROOT,tmp_path,planned)
        assert associations(db(),aid)[0]['family_id'] is None
        # A reused identifier/name must not silently make an unavailable link live.
        tid=create_tag(db(),'MAL_IMPOSTOR')[0]
        db().execute("INSERT INTO malware_families(id,name,tag_id,created_at,updated_at) VALUES(?,?,?,'2026','2026')",(family,'Impostor',tid));db().commit()
    assert edit(c,aid).status_code==302
    with app.app_context():
        assert associations(db(),aid)[0]['family_id'] is None


def test_history_complete_counts_pagination_and_current_states():
    from flask import template_rendered
    c,uid,cid,tid=setup();aid=create(c)
    with app.app_context():
        for index in range(30):
            case=db().execute("INSERT INTO cases(number,name,stage,created) VALUES(?,?,1,'2026')",(f'PAGE-{index:03}',f'Case {index}')).lastrowid
            db().execute("INSERT INTO case_tags VALUES(?,?,'2026',?)",(case,tid,uid))
        db().commit()
    captured={}
    def capture(sender,template,context,**extra):captured.update(context)
    with template_rendered.connected_to(capture,app):
        assert c.get('/threat-actors/'+aid+'?tab=history&case_page=2').status_code==200
    assert captured['case_count']==31 and captured['case_pages']==2 and len(captured['history'])==6
    with app.app_context():
        db().execute('UPDATE cases SET stage=3 WHERE id=?',(cid,));db().commit()
    assert 'Completed' in c.get('/threat-actors/'+aid+'?tab=history&case_page=2').text
    assert c.get('/threat-actors/'+aid+'?case_page=bad').status_code==400
    with app.app_context():
        create_tag(db(),'MAL_UNCONFIGURED');db().commit()
    assert c.get('/threat-actors/families/search?q=UNCONFIGURED').json=={'families':[]}


def test_http_unavailable_dependency_choice_and_repeat_import():
    from test_backup_workspace import export,inspect,post as backup_post,wait
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    assert post(c,'/malware-families/'+family+'/delete',version=family_profile(family)['version'],confirm_name=family_profile(family)['name']).status_code==302
    with c.session_transaction() as session:session['csrf']='backup-workspace'
    archive,_=export(c,['actors'],password='')
    with app.app_context():
        db().execute('DELETE FROM threat_actors');db().commit()
    plan=inspect(c,archive,password='')
    key='actor-unavailable:'+aid+':'+family
    assert plan['state']=='preview' and any(row['key']==key for row in plan['preview']['conflicts'])
    assert backup_post(c,'/backup-restore/jobs/'+plan['id']+'/apply').status_code==409
    assert backup_post(c,'/backup-restore/jobs/'+plan['id']+'/preview',choices=json.dumps({key:'retain'})).status_code==202
    refreshed=wait(c,plan['id'],'preview')
    assert not refreshed['preview']['conflicts']
    assert backup_post(c,'/backup-restore/jobs/'+plan['id']+'/apply').status_code==202
    wait(c,plan['id'],'completed')
    with app.app_context():
        assert associations(db(),aid)[0]['family_id'] is None
    repeated=inspect(c,archive,password='')
    assert repeated['state']=='preview' and not repeated['preview']['conflicts']


def test_skip_actor_clears_all_its_unavailable_dependency_conflicts(tmp_path):
    from backup_areas import resolve
    c,*_=setup();family=create_family(c);aid=create(c,known_families=[family])
    assert post(c,'/malware-families/'+family+'/delete',version=family_profile(family)['version'],confirm_name=family_profile(family)['name']).status_code==302
    with app.app_context():
        data=export_library(db(),ROOT);db().execute('DELETE FROM threat_actors');db().commit()
        second=copy.deepcopy(data['actors'][0]['known_families'][0]);second.update(family_uuid=str(uuid.uuid4()),position=2)
        data['actors'][0]['known_families'].append(second)
        (tmp_path/'family-library.json').write_text(json.dumps(data))
        key='actor-unavailable:'+aid+':'+second['family_uuid']
        conflicts,_,planned=resolve(db(),ROOT,tmp_path,{key:'skip'})
        assert not conflicts and planned['actors']==[]
