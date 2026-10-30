import io
import json
import sqlite3
import uuid
from pathlib import Path
import pytest
from app import app,db,run,ensure_package
from test_api import make_user
from task_collections import initialize


def setup(role='User',name='collection-author'):
    uid,headers=make_user(name,role)
    with app.app_context():
        cid=run("INSERT INTO cases(number,name,stage,created,owner) VALUES(?,?,1,'2026',?)",('COLL-'+str(uid),'Collections case',uid)).lastrowid
        ensure_package(cid)
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='collection-token')
    return client,headers,cid,uid

def create(client,headers,name='Analysis guidance'):
    response=client.post('/api/v1/task-collections',headers=headers,json={'name':name,'description':'Reusable guidance','category':'Windows','tasks':[{'name':'Collect context','description':'Review context'},{'name':'Inspect content','description':'Inspect carefully'}]})
    assert response.status_code==201,response.data
    return response.json['collection']

def application(client,headers,cid,collection,**extra):
    return client.post(f'/api/v1/cases/{cid}/task-collections/{collection["id"]}/apply',headers=headers,json={'revision':collection['revision'],'template_ids':[t['id'] for t in collection['tasks']],'request_key':uuid.uuid4().hex,**extra})


def test_migration_preserves_all_legacy_fields_and_seeds_task_edit_roles():
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.executescript("CREATE TABLE schema_migrations(name TEXT PRIMARY KEY);CREATE TABLE cases(id INTEGER PRIMARY KEY);CREATE TABLE tasks(id INTEGER PRIMARY KEY,case_id INTEGER,title TEXT,body TEXT,state TEXT,priority TEXT,done INTEGER,created TEXT);CREATE TABLE role_permissions(role_name TEXT,permission TEXT,PRIMARY KEY(role_name,permission));INSERT INTO role_permissions VALUES('Analyst','cases:update');INSERT INTO tasks VALUES(7,1,'Legacy','Rich description','In Progress','High',0,'old date');")
    before=dict(con.execute('SELECT * FROM tasks').fetchone());initialize(con);initialize(con)
    after=dict(con.execute('SELECT * FROM tasks').fetchone())
    assert {k:after[k] for k in before}==before and after['group_id'] is None and after['position']==7
    assert con.execute("SELECT 1 FROM role_permissions WHERE role_name='Analyst' AND permission='task_collections:create'").fetchone()


def test_apply_order_status_atomic_replay_missing_and_revision_conflict():
    client,headers,cid,_=setup();collection=create(client,headers)
    request_key=uuid.uuid4().hex
    first=application(client,headers,cid,collection,request_key=request_key);assert first.status_code==201
    replay=application(client,headers,cid,collection,request_key=request_key);assert replay.json['replayed'] is True and replay.json['task_ids']==first.json['task_ids']
    state=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    assert [t['title'] for t in state['tasks']]==['Collect context','Inspect content']
    assert all(t['state']=='Not Started' and not t['done'] for t in state['tasks'])
    assert state['groups'][0]['name']==collection['name']
    assert application(client,headers,cid,collection).status_code==409
    assert application(client,headers,cid,collection,mode='copy').json['count']==2
    changed=client.patch('/api/v1/task-collections/'+collection['id'],headers=headers,json={**collection,'tasks':[*collection['tasks'],{'name':'New guidance','description':''}]}).json['collection']
    assert application(client,headers,cid,collection).status_code==409
    assert application(client,headers,cid,changed).json['count']==1
    assert application(client,headers,cid,changed,template_ids=['invalid']).status_code==400
    assert len(client.get(f'/api/v1/cases/{cid}/tasks',headers=headers).json['tasks'])==5


def test_templates_and_case_copies_are_independent_with_provenance_after_deletion():
    client,headers,cid,_=setup();collection=create(client,headers);result=application(client,headers,cid,collection).json;tid=result['task_ids'][0]
    assert client.patch(f'/api/v1/cases/{cid}/tasks/{tid}',headers=headers,json={'title':'Case-specific edit','state':'Completed'}).status_code==200
    updated=client.patch('/api/v1/task-collections/'+collection['id'],headers=headers,json={**collection,'name':'Revised library','tasks':[{'id':collection['tasks'][0]['id'],'name':'Revised template','description':''}]}).json['collection']
    assert client.delete('/api/v1/task-collections/'+collection['id'],headers=headers,json={'revision':updated['revision']}).status_code==204
    state=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    assert state['tasks'][0]['title']=='Case-specific edit' and state['tasks'][0]['state']=='Completed'
    assert state['groups'][0]['name']==collection['name'] and state['tasks'][0]['source_collection_id']==collection['id']
    assert state['groups'][0]['source_tasks'][0]['name']=='Collect context'
    assert len(state['groups'][0]['source_fingerprint'])==64
    assert client.delete(f'/api/v1/cases/{cid}/task-groups/{result["group_id"]}',headers=headers,json={'confirm':False}).status_code==400
    assert client.delete(f'/api/v1/cases/{cid}/task-groups/{result["group_id"]}',headers=headers,json={'confirm':True}).status_code==200


def test_selected_tasks_create_and_append_definitions_without_case_mutation():
    client,headers,cid,_=setup()
    task_ids=[]
    for name in ['Original one','Original two']:
        task_ids.append(client.post(f'/api/v1/cases/{cid}/tasks',headers=headers,json={'title':name,'body':'Detailed '+name}).json['task']['id'])
    client.patch(f'/api/v1/cases/{cid}/tasks/{task_ids[0]}',headers=headers,json={'state':'Completed'})
    before=client.get(f'/api/v1/cases/{cid}/tasks',headers=headers).json
    created=client.post(f'/api/v1/cases/{cid}/task-collections',headers=headers,json={'task_ids':list(reversed(task_ids)),'name':'From case','category':'General'}).json['collection']
    assert [t['name'] for t in created['tasks']]==['Original two','Original one']
    assert all(set(t)=={'id','name','description'} for t in created['tasks'])
    appended=client.post(f'/api/v1/cases/{cid}/task-collections',headers=headers,json={'task_ids':[task_ids[0]],'collection_id':created['id'],'revision':created['revision']})
    assert appended.status_code==201 and len(appended.json['collection']['tasks'])==3
    assert client.get(f'/api/v1/cases/{cid}/tasks',headers=headers).json==before


@pytest.mark.parametrize('stage',[0,3])
def test_closed_case_blocks_every_mutation_but_library_is_readable(stage):
    client,headers,cid,_=setup();collection=create(client,headers);result=application(client,headers,cid,collection).json
    with app.app_context():run('UPDATE cases SET stage=? WHERE id=?',(stage,cid))
    assert application(client,headers,cid,collection,mode='copy').status_code==409
    tid=result['task_ids'][0]
    assert client.patch(f'/api/v1/cases/{cid}/tasks/{tid}',headers=headers,json={'state':'Completed'}).status_code==409
    assert client.delete(f'/api/v1/cases/{cid}/tasks/{tid}',headers=headers).status_code==409
    assert client.put(f'/api/v1/cases/{cid}/task-order',headers=headers,json={'group_id':result['group_id'],'task_ids':result['task_ids']}).status_code==409
    assert client.delete(f'/api/v1/cases/{cid}/task-groups/{result["group_id"]}',headers=headers,json={'confirm':True}).status_code==409
    assert client.post(f'/cases/{cid}/tasks',data={'csrf':'collection-token','name':'Forbidden'}).status_code==409
    assert client.get('/api/v1/task-collections',headers=headers).status_code==200
    assert client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json['editable'] is False


def test_creator_permissions_bulk_ids_and_web_csrf():
    client,headers,cid,_=setup();collection=create(client,headers)
    other,other_headers,other_cid,other_uid=setup(name='other-author')
    assert other.patch('/api/v1/task-collections/'+collection['id'],headers=other_headers,json=collection).status_code==403
    assert other.delete('/api/v1/task-collections/'+collection['id'],headers=other_headers,json={'revision':1}).status_code==403
    assert other.post('/task-workspace/collections',data={'payload':'{}'}).status_code==403
    with app.app_context():
        run("INSERT INTO roles VALUES('reader','',0)")
        run("INSERT INTO role_permissions VALUES('reader','cases:read')")
        run("UPDATE users SET role='reader' WHERE id=?",(other_uid,))
    assert other.get('/api/v1/task-collections',headers=other_headers).status_code==200
    assert other.post('/api/v1/task-collections',headers=other_headers,json=collection).status_code==403
    assert application(other,other_headers,other_cid,collection).status_code==403
    assert other.post(f'/cases/{other_cid}/tasks',data={'csrf':'collection-token','name':'Forbidden'}).status_code==403
    assert client.post(f'/api/v1/cases/{cid}/task-collections',headers=headers,json={'task_ids':[99999],'name':'No'}).status_code==404
    assert client.get('/api/v1/task-collections').status_code==401


def test_open_collection_and_custom_tasks_do_not_gate_case_completion():
    from mip import CATEGORIES
    from app import completion_items,review_issues,package
    client,headers,cid,_=setup();collection=create(client,headers);application(client,headers,cid,collection)
    client.post(f'/api/v1/cases/{cid}/tasks',headers=headers,json={'title':'Optional custom guidance'})
    with app.app_context():
        run('UPDATE cases SET stage=2 WHERE id=?',(cid,))
        (package(cid)/'reports/malware-analysis-report.md').write_text('# Finished analysis\nReviewed findings.')
        from docx import Document
        report=Document();report.add_paragraph('Reviewed findings.');report.save(package(cid)/'reports/reviewed-findings.docx')
        for category in CATEGORIES:run('INSERT OR REPLACE INTO readiness VALUES(?,?,?,?)',(cid,category,'Populated' if category=='reports' else 'Not applicable','No applicable content'))
        assert len([i for i in completion_items(cid) if i.get('advisory')])==3
        assert not review_issues(cid)
    result=client.post(f'/api/v1/cases/{cid}/stage',headers=headers,json={'expected':2})
    assert result.status_code==200,result.data
    with app.app_context():
        assert db().execute('SELECT stage FROM cases WHERE id=?',(cid,)).fetchone()[0]==3
        assert db().execute('SELECT count(*) FROM tasks WHERE case_id=? AND done=0',(cid,)).fetchone()[0]==3


def test_case_only_backup_restores_independent_groups_without_global_collection():
    from sync_helpers import apply_preview,other_destination
    client,headers,cid,_=setup(role='Administrator');collection=create(client,headers);applied=application(client,headers,cid,collection).json
    tid=applied['task_ids'][0]
    client.patch(f'/api/v1/cases/{cid}/tasks/{tid}',headers=headers,json={'title':'Independent case title','state':'In Progress','body':'**Case description**'})
    backup=client.post(f'/cases/{cid}/backup',data={'csrf':'collection-token'});assert backup.status_code==200
    client.delete('/api/v1/task-collections/'+collection['id'],headers=headers,json={'revision':1})
    other_destination()
    response=client.post('/import-export/import-raw',data={'csrf':'collection-token','backup':(io.BytesIO(backup.data),'case.zip')})
    response=apply_preview(client,response,'collection-token');assert response.status_code==302
    with app.app_context():
        assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==2
        restored=db().execute('SELECT max(id) FROM cases').fetchone()[0]
        group=db().execute('SELECT * FROM task_groups WHERE case_id=?',(restored,)).fetchone()
        tasks=db().execute('SELECT * FROM tasks WHERE case_id=? ORDER BY position,id',(restored,)).fetchall()
        assert group['name']==collection['name'] and group['source_collection_id']==collection['id'] and group['source_revision']==1
        assert tasks[0]['title']=='Independent case title' and tasks[0]['state']=='In Progress' and tasks[0]['body']=='**Case description**'
        assert not db().execute('SELECT 1 FROM task_collections').fetchone()
        assert db().execute('SELECT template_ids FROM task_collection_applications WHERE case_id=?',(restored,)).fetchone()[0]


def test_collection_only_archive_preview_conflicts_restore_and_repeat(tmp_path):
    from test_backup_workspace import setup as backup_setup,export,inspect,post,wait
    client,uid,_,_=backup_setup()
    value={'name':'Same name is not identity','description':'Reusable','category':'General','tasks':[{'name':'Guidance','description':'Reusable definition'}]}
    response=client.post('/task-workspace/collections',data={'csrf':'backup-workspace','payload':json.dumps(value)})
    assert response.status_code==201
    source=response.json['collection']
    archive,job=export(client,['task_collections'],password='')
    assert job['manifest']['counts']['task_collections']==1 and job['manifest']['counts']['task_templates']==1 and job['manifest']['counts']['cases']==0
    assert job['archive_name'].endswith('_TC.zip')
    # Replace the source with a distinct same-name record to prove no title merge.
    client.post('/task-workspace/collections/'+source['id'],data={'csrf':'backup-workspace','payload':json.dumps({'operation':'delete','revision':1})})
    client.post('/task-workspace/collections',data={'csrf':'backup-workspace','payload':json.dumps(value)})
    for iteration in range(2):
        preview=inspect(client,archive,password='');assert preview['state']=='preview',preview
        assert preview['preview']['counts']['task_collections']==1 and not preview['preview']['conflicts']
        assert any(r['category']=='task_collections' for r in preview['preview']['records'])
        result=post(client,'/backup-restore/jobs/'+preview['id']+'/apply');assert result.status_code==202,result.data
        outcome=wait(client,preview['id'],'completed')
        assert outcome['result']['records'][0]['action']==('added' if iteration==0 else 'unchanged')
    with app.app_context():
        assert db().execute('SELECT count(*) FROM task_collections').fetchone()[0]==2
        from task_collection_portable import export as portable_export,validate
        validate(portable_export(db()))
    changed={**source,'description':'Conflicting destination edit'}
    client.post('/task-workspace/collections/'+source['id'],data={'csrf':'backup-workspace','payload':json.dumps(changed)})
    preview=inspect(client,archive,password='');assert preview['preview']['conflicts'][0]['key']=='task_collection:'+source['id']
    for choice in ('keep','replace'):
        if choice=='replace':preview=inspect(client,archive,password='')
        key='task_collection:'+source['id']
        assert post(client,'/backup-restore/jobs/'+preview['id']+'/preview',choices=json.dumps({key:choice})).status_code==202
        refreshed=wait(client,preview['id'],'preview');assert not refreshed['preview']['conflicts']
        assert post(client,'/backup-restore/jobs/'+preview['id']+'/apply').status_code==202
        completed=wait(client,preview['id'],'completed')
        assert completed['result']['records'][0]['action']==('skipped' if choice=='keep' else 'updated')
        with app.app_context():assert db().execute('SELECT description FROM task_collections WHERE id=?',(source['id'],)).fetchone()[0]==('Conflicting destination edit' if choice=='keep' else 'Reusable')


def test_complete_backup_preserves_collections_revisions_groups_and_states(tmp_path):
    from test_backup_workspace import setup as backup_setup,export
    from installation_backup import restore_installation
    import zipfile
    client,uid,cid,_=backup_setup()
    payload={'name':'Complete backup guidance','tasks':[{'name':'One','description':'Before edit'}]}
    created=client.post('/task-workspace/collections',data={'csrf':'backup-workspace','payload':json.dumps(payload)}).json['collection']
    applied=client.post(f'/task-workspace/cases/{cid}/collections/{created["id"]}/apply',data={'csrf':'backup-workspace','payload':json.dumps({'revision':1,'request_key':uuid.uuid4().hex,'template_ids':[created['tasks'][0]['id']]})});assert applied.status_code==201
    tid=applied.json['task_ids'][0]
    client.post(f'/task-workspace/cases/{cid}/tasks/{tid}',data={'csrf':'backup-workspace','payload':json.dumps({'state':'Completed'})})
    client.post('/task-workspace/collections/'+created['id'],data={'csrf':'backup-workspace','payload':json.dumps({**created,'description':'Revised'})})
    archive,_=export(client,complete=True)
    source=tmp_path/'outer.zip';source.write_bytes(archive)
    # Unwrap using the same reviewed decryption path as the current Import workflow.
    import pyzipper
    with pyzipper.AESZipFile(source) as outer:
        outer.setpassword(b'a strong recovery passphrase');payload_path=tmp_path/'payload.zip';payload_path.write_bytes(outer.read('payload.zip'))
    destination=tmp_path/'restored';restore_installation(payload_path,destination)
    con=sqlite3.connect(destination/'workflow.sqlite3')
    assert con.execute('SELECT revision FROM task_collections WHERE id=?',(created['id'],)).fetchone()[0]==2
    assert con.execute('SELECT count(*) FROM task_collection_revisions WHERE collection_id=?',(created['id'],)).fetchone()[0]==2
    assert con.execute('SELECT source_revision,name FROM task_groups WHERE case_id=?',(cid,)).fetchone()==(1,'Complete backup guidance')
    assert con.execute('SELECT state FROM tasks WHERE id=?',(tid,)).fetchone()[0]=='Completed'


def test_sdk_new_collections_and_existing_tasks_use_real_rest_contract():
    httpx=pytest.importorskip('httpx')
    from mws_sdk import MWSClient
    client,headers,cid,_=setup(role='Administrator')
    with MWSClient('http://isolated.test',headers['Authorization'].removeprefix('Bearer '),transport=httpx.WSGITransport(app=app),retries=0) as sdk:
        collection=sdk.task_collections.create(data={'name':'SDK guidance','tasks':[{'name':'Read context','description':'Details'}]}).collection
        assert sdk.task_collections.list().collections[0].id==collection.id
        assert list(sdk.task_collections.iter_all())[0].id==collection.id
        applied=sdk.task_collections.apply(cid,collection.id,data={'revision':collection.revision,'template_ids':[t.id for t in collection.tasks],'request_key':uuid.uuid4().hex})
        task=sdk.tasks.get(cid,applied.task_ids[0]).task
        assert task.state=='Not Started' and task.source_collection_id==collection.id
        sdk.tasks.update(cid,task.id,data={'state':'Completed'})
        assert sdk.tasks.list(cid).tasks[0].state=='Completed'
        assert sdk.task_collections.case_groups(cid).groups[0].source_revision==1


def test_old_complete_archive_without_collections_gets_additive_upgrade(tmp_path):
    import hashlib,zipfile,pyzipper
    from test_backup_workspace import setup as backup_setup,export
    from installation_backup import restore_installation,record_counts
    client,_,_,_=backup_setup();archive,_=export(client,complete=True)
    with pyzipper.AESZipFile(io.BytesIO(archive)) as outer:
        outer.setpassword(b'a strong recovery passphrase');raw=outer.read('payload.zip')
    with zipfile.ZipFile(io.BytesIO(raw)) as source:members={name:source.read(name) for name in source.namelist()}
    old_db=tmp_path/'old.sqlite3';old_db.write_bytes(members['data/workflow.sqlite3'])
    with sqlite3.connect(old_db) as con:
        for table in ('task_collections','task_collection_revisions','task_groups','task_collection_applications'):con.execute('DROP TABLE '+table)
        for column in ('group_id','source_template_id','source_collection_id','source_revision','position'):con.execute('ALTER TABLE tasks DROP COLUMN '+column)
        con.execute('DELETE FROM schema_migrations WHERE name=?',('task-collections-v1',))
        con.commit();counts=record_counts(con)
    body=old_db.read_bytes();members['data/workflow.sqlite3']=body
    manifest=json.loads(members['installation.json']);manifest['counts']=counts
    manifest['files']['data/workflow.sqlite3']={'size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    members['installation.json']=json.dumps(manifest).encode()
    legacy=tmp_path/'old.zip'
    with zipfile.ZipFile(legacy,'w') as target:
        for name,content in members.items():target.writestr(name,content)
    restored=tmp_path/'upgraded';restore_installation(legacy,restored)
    with sqlite3.connect(restored/'workflow.sqlite3') as con:
        assert con.execute('SELECT count(*) FROM task_collections').fetchone()[0]==0
        assert 'group_id' in {r[1] for r in con.execute('PRAGMA table_info(tasks)')}
        assert con.execute("SELECT 1 FROM schema_migrations WHERE name='task-collections-v1'").fetchone()
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='sync_dirty_task_groups_INSERT'").fetchone()
        from backup_workspace import schema
        assert schema(con)==app.extensions['backup_workspace'].expected_schema


def test_concurrent_request_retries_add_exactly_one_group():
    from concurrent.futures import ThreadPoolExecutor
    client,headers,cid,_=setup();collection=create(client,headers);key=uuid.uuid4().hex
    def submit(_):
        separate=app.test_client();return application(separate,headers,cid,collection,request_key=key)
    with ThreadPoolExecutor(max_workers=2) as executor:responses=list(executor.map(submit,range(2)))
    assert [r.status_code for r in responses]==[201,201]
    assert sum(bool(r.json.get('replayed')) for r in responses)==1
    with app.app_context():
        assert db().execute('SELECT count(*) FROM tasks WHERE case_id=?',(cid,)).fetchone()[0]==2
        assert db().execute('SELECT count(*) FROM task_groups WHERE case_id=?',(cid,)).fetchone()[0]==1


def test_application_rolls_back_every_task_group_and_retry_record(monkeypatch):
    client,headers,cid,_=setup();collection=create(client,headers)
    with app.app_context():
        db().execute("CREATE TRIGGER task_apply_failure BEFORE INSERT ON tasks WHEN NEW.title='Inspect content' BEGIN SELECT RAISE(ABORT,'test failure'); END");db().commit()
    monkeypatch.setitem(app.config,'TESTING',True)
    try:
        with pytest.raises(sqlite3.IntegrityError):application(client,headers,cid,collection)
        with app.app_context():
            for table in ('tasks','task_groups','task_collection_applications'):assert db().execute(f'SELECT count(*) FROM {table} WHERE case_id=?',(cid,)).fetchone()[0]==0
    finally:
        with app.app_context():db().execute('DROP TRIGGER task_apply_failure');db().commit()


def test_pre_collection_case_archive_keeps_valid_sync_identity():
    import zipfile
    from sync_helpers import apply_preview
    client,headers,cid,_=setup(role='Administrator')
    client.post(f'/api/v1/cases/{cid}/tasks',headers=headers,json={'title':'Legacy task','body':'Preserved guidance'})
    blob=client.post(f'/cases/{cid}/backup',data={'csrf':'collection-token'}).data
    with zipfile.ZipFile(io.BytesIO(blob)) as source:members={name:source.read(name) for name in source.namelist()}
    metadata=next(name for name in members if name.endswith('/case-data.json'))
    value=json.loads(members[metadata]);value['records'].pop('task_groups');value['records'].pop('task_application_history')
    for task in value['records']['tasks']:
        for key in ('group_id','source_template_id','source_collection_id','source_revision','position'):task.pop(key,None)
    members[metadata]=json.dumps(value).encode()
    import hashlib
    manifest_path=next(name for name in members if name.endswith('/manifest.json'))
    manifest=json.loads(members[manifest_path]);entry=next(row for row in manifest['files'] if row['path']=='case-data.json');entry.update(size=len(members[metadata]),sha256=hashlib.sha256(members[metadata]).hexdigest());members[manifest_path]=json.dumps(manifest).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as target:
        for name,content in members.items():target.writestr(name,content)
    response=client.post('/import-export/import-raw',data={'csrf':'collection-token','backup':(io.BytesIO(out.getvalue()),'older-case.zip')})
    assert response.status_code==302 and '/review/' in response.location
    with app.app_context():
        plan=json.loads(db().execute('SELECT plan FROM sync_imports WHERE id=?',(response.location.rsplit('/',1)[-1],)).fetchone()[0])
        assert plan['items'][0]['preview']['classification']=='unchanged'
    apply_preview(client,response,'collection-token')
    with app.app_context():assert db().execute('SELECT count(*) FROM cases').fetchone()[0]==1


def test_case_backup_retains_prior_application_ids_after_group_removal():
    from sync_helpers import apply_preview,other_destination
    client,headers,cid,_=setup(role='Administrator');collection=create(client,headers);result=application(client,headers,cid,collection).json
    client.delete(f'/api/v1/cases/{cid}/task-groups/{result["group_id"]}',headers=headers,json={'confirm':True})
    backup=client.post(f'/cases/{cid}/backup',data={'csrf':'collection-token'}).data
    other_destination()
    response=client.post('/import-export/import-raw',data={'csrf':'collection-token','backup':(io.BytesIO(backup),'removed-group.zip')})
    apply_preview(client,response,'collection-token')
    with app.app_context():restored=db().execute('SELECT max(id) FROM cases').fetchone()[0]
    assert restored!=cid
    state=client.get(f'/api/v1/cases/{restored}/task-groups',headers=headers).json
    assert not state['groups'] and not state['tasks'] and len(state['applications'])==1
    assert application(client,headers,restored,collection).status_code==409
    assert application(client,headers,restored,collection,mode='copy').json['count']==2


def test_task_reordering_preserves_image_association_in_case_snapshots():
    from PIL import Image
    from app import package
    client,headers,cid,_=setup(role='Administrator');collection=create(client,headers);result=application(client,headers,cid,collection).json
    name='report-image-'+uuid.uuid4().hex+'.png';tid=result['task_ids'][0]
    with app.app_context():
        assets=package(cid)/'reports/sections/assets';assets.mkdir(parents=True,exist_ok=True);Image.new('RGB',(10,10),'blue').save(assets/name)
        run('INSERT INTO report_images(case_id,section,name,figure) VALUES(?,?,?,1)',(cid,'task-'+str(tid),name))
    client.patch(f'/api/v1/cases/{cid}/tasks/{tid}',headers=headers,json={'body':'![Finding](assets/'+name+')'})
    ordered=list(reversed(result['task_ids']))
    assert client.put(f'/api/v1/cases/{cid}/task-order',headers=headers,json={'group_id':result['group_id'],'task_ids':ordered}).status_code==200
    with app.app_context():
        snapshot=app.extensions['case_sync'].snapshot(cid)
        assert snapshot['records']['tasks'][1]['body']=='![Finding](assets/'+name+')'
        assert snapshot['images'][0]['section']=='task-index-1'
