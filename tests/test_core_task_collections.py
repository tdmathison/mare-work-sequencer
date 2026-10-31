import copy
import json
import sqlite3
import uuid
import httpx
import pytest
from app import app,db,run
import core_task_collections as core
import task_collections as service
import task_collection_portable as portable
from test_task_collections import setup,create,application
from mws_sdk import MWSClient


def core_items(client,headers):
    return client.get('/api/v1/task-collections?origin=core',headers=headers).json['collections']


def test_exact_core_library_filter_and_same_name_custom():
    client,headers,cid,_=setup()
    items=core_items(client,headers)
    assert len(items)==10
    assert {i['name'] for i in items}=={i['name'] for i in core.definitions()}
    assert sum(i['task_count'] for i in items)==60
    assert all(i['origin']=='core' and i['read_only'] and not i['can_edit'] and not i['can_delete'] for i in items)
    assert len({t['id'] for i in items for t in i['tasks']})==60
    custom=create(client,headers,name=items[0]['name'])
    assert custom['origin']=='custom' and not custom['read_only']
    assert client.get('/api/v1/task-collections?origin=custom',headers=headers).json['total']==1
    assert client.get('/api/v1/task-collections?origin=all',headers=headers).json['total']==11
    assert client.get('/api/v1/task-collections?origin=other',headers=headers).status_code==400
    assert client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json['tasks']==[]


def test_legacy_upgrade_and_idempotent_initialization_preserve_custom(monkeypatch):
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
    con.executescript("""CREATE TABLE schema_migrations(name TEXT PRIMARY KEY);
    CREATE TABLE tasks(id INTEGER PRIMARY KEY,case_id INTEGER,title TEXT,body TEXT,state TEXT,priority TEXT,done INTEGER,created TEXT);
    CREATE TABLE cases(id INTEGER PRIMARY KEY);CREATE TABLE role_permissions(role_name TEXT,permission TEXT,PRIMARY KEY(role_name,permission));
    CREATE TABLE task_collections(id TEXT PRIMARY KEY,name TEXT,description TEXT,category TEXT,tasks TEXT,revision INTEGER,creator_uuid TEXT,creator_name TEXT,created TEXT,updated TEXT);
    CREATE TABLE task_collection_revisions(collection_id TEXT,revision INTEGER,snapshot TEXT,PRIMARY KEY(collection_id,revision));""")
    cid=uuid.uuid4().hex
    con.execute('INSERT INTO task_collections VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,core.definitions()[0]['name'],'Custom preserved','General','[]',1,None,'Owner','before','before'));con.commit()
    service.initialize(con)
    before=[tuple(r) for r in con.execute('SELECT * FROM task_collections ORDER BY id')]
    versions=[tuple(r) for r in con.execute('SELECT * FROM task_collection_revisions ORDER BY collection_id,revision')]
    monkeypatch.setattr(service,'now',lambda:'2100-01-01T00:00:00+00:00')
    service.initialize(con);service.initialize(con)
    assert [tuple(r) for r in con.execute('SELECT * FROM task_collections ORDER BY id')]==before
    assert [tuple(r) for r in con.execute('SELECT * FROM task_collection_revisions ORDER BY collection_id,revision')]==versions
    assert con.execute("SELECT count(*) FROM task_collections WHERE origin='core'").fetchone()[0]==10
    assert con.execute('SELECT description FROM task_collections WHERE id=?',(cid,)).fetchone()[0]=='Custom preserved'
    assert con.execute('SELECT count(*) FROM tasks').fetchone()[0]==0


@pytest.mark.parametrize('role',['User','Administrator'])
def test_core_is_protected_in_crud_and_append_workflows(role):
    client,headers,cid,_=setup(role=role)
    item=core_items(client,headers)[0]
    applied=application(client,headers,cid,item).json
    for method,payload in [('patch',{**item,'name':'Overwritten','origin':'custom','read_only':False}),('delete',{'revision':1})]:
        assert getattr(client,method)('/api/v1/task-collections/'+item['id'],headers=headers,json=payload).status_code==403
    assert client.post('/task-workspace/collections/'+item['id'],data={'csrf':'collection-token','payload':json.dumps({'operation':'delete','revision':1})}).status_code==403
    assert client.post(f'/api/v1/cases/{cid}/task-collections',headers=headers,json={'collection_id':item['id'],'revision':1,'task_ids':applied['task_ids']}).status_code==403
    assert client.post('/api/v1/task-collections',headers=headers,json={**item,'id':item['id']}).status_code==403
    assert client.get('/api/v1/task-collections/'+item['id'],headers=headers).json['collection']['name']==item['name']


def test_duplicate_sdk_permissions_and_independent_case_copy():
    client,headers,cid,_=setup()
    item=core_items(client,headers)[0]
    with MWSClient('http://isolated.test',headers['Authorization'][7:],transport=httpx.WSGITransport(app=app),retries=0) as sdk:
        listed=sdk.task_collections.list(params={'origin':'core'})
        assert len(listed.collections)==10 and listed.collections[0].read_only
        duplicate=sdk.task_collections.duplicate(item['id'],data={'name':'My custom guidance'}).collection
        assert duplicate.origin=='custom' and not duplicate.read_only and duplicate.id!=item['id']
        assert {t.id for t in duplicate.tasks}.isdisjoint({t['id'] for t in item['tasks']})
        assert sdk.task_collections.update(duplicate.id,data={'revision':1,'name':'Editable copy','tasks':[{'id':t.id,'name':t.name,'description':t.description} for t in duplicate.tasks]}).collection.name=='Editable copy'
    chosen=[item['tasks'][4]['id'],item['tasks'][1]['id']]
    applied=application(client,headers,cid,item,template_ids=chosen).json
    state=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    assert [t['source_template_id'] for t in state['tasks']]==[item['tasks'][1]['id'],item['tasks'][4]['id']]
    assert all(t['state']=='Not Started' for t in state['tasks'])
    assert client.patch(f'/api/v1/cases/{cid}/tasks/{applied["task_ids"][0]}',headers=headers,json={'state':'Completed','title':'Independent copy'}).status_code==200
    with app.app_context():run('UPDATE cases SET stage=3 WHERE id=?',(cid,))
    assert application(client,headers,cid,item,mode='copy').status_code==409
    assert client.post('/api/v1/task-collections/'+item['id']+'/duplicate',headers=headers,json={}).status_code==201
    with app.app_context():run("DELETE FROM role_permissions WHERE role_name='User' AND permission='task_collections:create'")
    assert client.post('/api/v1/task-collections/'+item['id']+'/duplicate',headers=headers,json={}).status_code==403
    with app.app_context():run('UPDATE cases SET stage=1 WHERE id=?',(cid,))
    assert application(client,headers,cid,item,mode='copy').status_code==201


def test_new_bundle_revision_does_not_change_case_progress_or_allow_downgrade(monkeypatch):
    client,headers,cid,_=setup();item=core_items(client,headers)[0]
    applied=application(client,headers,cid,item).json
    client.patch(f'/api/v1/cases/{cid}/tasks/{applied["task_ids"][0]}',headers=headers,json={'state':'Completed'})
    before=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    bundled=copy.deepcopy(core.definitions());changed=next(i for i in bundled if i['id']==item['id']);changed['revision']=2;changed['name']='Updated title with stable identity';changed['tasks'].reverse();changed['tasks'][0]['description']='Updated bundled guidance'
    with monkeypatch.context() as patch:
        patch.setattr(core,'definitions',lambda:bundled)
        with app.app_context():service.initialize(db())
    after=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    assert before==after and after['groups'][0]['source_revision']==1
    with app.app_context():
        stamp=db().execute('SELECT updated FROM task_collections WHERE id=?',(item['id'],)).fetchone()[0]
        service.initialize(db())
        assert service.get(db(),item['id'])['revision']==2
        assert db().execute('SELECT updated FROM task_collections WHERE id=?',(item['id'],)).fetchone()[0]==stamp


def test_portable_import_cannot_replace_or_forge_core_and_supports_legacy(tmp_path):
    client,headers,_,uid=setup(role='Administrator')
    custom=create(client,headers,name='Custom archive')
    with app.app_context():
        rows=portable.export(db());saved=copy.deepcopy(rows)
        item=next(i for i in rows if i['origin']=='core')
        item['name']='Forged';item['revisions'][-1]['name']='Forged'
        item['origin']='custom';item['revisions'][-1]['origin']='custom'
        unknown=copy.deepcopy(next(i for i in rows if i['origin']=='core'));unknown['id']=uuid.uuid4().hex
        for rev in unknown['revisions']:rev['id']=unknown['id']
        rows.append(unknown)
        legacy=next(i for i in rows if i['id']==custom['id']);legacy.pop('origin')
        for rev in legacy['revisions']:rev.pop('origin')
        conflicts,records=portable.plan(db(),rows,{'task_collection:'+item['id']:'replace'})
        assert not conflicts
        assert next(r for r in records if r['identifier']==item['id'])['predicted_action']=='skipped'
        (tmp_path/'task-collections.json').write_text(json.dumps(rows))
        user=db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        portable.restore(db(),user,tmp_path,{'task_collection:'+item['id']:'replace'})
        assert portable.export(db())==saved
        assert db().execute("SELECT count(*) FROM task_collections WHERE origin='core'").fetchone()[0]==10


def test_complete_backup_retains_newer_core_and_original_case_provenance(tmp_path,monkeypatch):
    from test_malware_families import make_backup
    from malware_families import initialize as initialize_families
    from installation_backup import restore_installation
    client,headers,cid,_=setup(role='Administrator')
    item=core_items(client,headers)[0];applied=application(client,headers,cid,item).json
    client.patch(f'/api/v1/cases/{cid}/tasks/{applied["task_ids"][0]}',headers=headers,json={'state':'Completed'})
    before=client.get(f'/api/v1/cases/{cid}/task-groups',headers=headers).json
    bundled=copy.deepcopy(core.definitions());next(i for i in bundled if i['id']==item['id'])['revision']=2
    with monkeypatch.context() as patch:
        patch.setattr(core,'definitions',lambda:bundled)
        with app.app_context():
            initialize_families(db());service.initialize(db())
        raw=make_backup(client)
    archive=tmp_path/'complete.zip';archive.write_bytes(raw)
    destination=tmp_path/'restored';restore_installation(archive,destination)
    with sqlite3.connect(destination/'workflow.sqlite3') as connection:
        connection.row_factory=sqlite3.Row
        assert connection.execute("SELECT count(*) FROM task_collections WHERE origin='core'").fetchone()[0]==10
        assert service.get(connection,item['id'])['revision']==2
        group=connection.execute('SELECT * FROM task_groups WHERE case_id=?',(cid,)).fetchone()
        assert group['source_revision']==1
        assert connection.execute('SELECT state FROM tasks WHERE id=?',(applied['task_ids'][0],)).fetchone()[0]=='Completed'
        response=json.loads(connection.execute('SELECT response FROM task_collection_applications WHERE case_id=?',(cid,)).fetchone()[0])
        assert response['source_tasks']==before['groups'][0]['source_tasks']
        from backup_workspace import schema
        assert schema(connection)==app.extensions['backup_workspace'].expected_schema


def test_concurrent_installation_and_core_only_import_do_not_require_library_management(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path=tmp_path/'concurrent.sqlite3'
    with app.app_context():
        ddl=[db().execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()[0] for name in ('schema_migrations','task_collections','task_collection_revisions')]
    with sqlite3.connect(path) as connection:
        for sql in ddl:connection.execute(sql)
    def install(_):
        with sqlite3.connect(path,timeout=10) as connection:core.install(connection)
    with ThreadPoolExecutor(max_workers=3) as workers:list(workers.map(install,range(3)))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM task_collections').fetchone()[0]==10
        assert connection.execute('SELECT count(*) FROM task_collection_revisions').fetchone()[0]==10
    client,headers,_,uid=setup()
    with app.app_context():
        before=portable.export(db());(tmp_path/'task-collections.json').write_text(json.dumps(before))
        user=db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        result=portable.restore(db(),user,tmp_path,{})
        assert len(result)==10 and all(r['action']=='skipped' for r in result)
        assert portable.export(db())==before
