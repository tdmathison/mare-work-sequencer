import base64
import json
import sqlite3
from pathlib import Path
import pytest
from app import app,db
from authorization import PERMISSIONS
import plugin_execution
import plugin_store as store
from plugin_fixtures import browser,metadata,package_entries,install,post


@pytest.fixture
def package(tmp_path,monkeypatch):
    monkeypatch.setitem(app.config,'PLUGINS_DIR',tmp_path)
    install(tmp_path)
    client,uid=browser()
    response=post(client,'/plugins/discovery')
    assert response.json=={'registered':['hello_plugin'],'invalid':[]}
    return client,uid,tmp_path


def test_navigation_and_removed_routes(package):
    client,_,_=package
    for path in ['/api','/developer/api','/developer/sdk','/developer/sdk?document=reference','/developer/sdk?document=plugins','/developer/sdk?document=runtime','/plugins']:
        response=client.get(path)
        assert response.status_code==200
        text=response.text
        assert 'developer-tab-editor' not in text
        positions=[text.index('id="developer-tab-'+name+'"') for name in ['api','sdk','plugins']]
        assert positions==sorted(positions)
        assert 'Edit in Editor' not in text and 'data-plugin-new' not in text
    for path in ['/developer/editor','/developer/workspace/plugins','/developer/workspace/plugins/hello_plugin/file']:
        assert client.get(path).status_code==404
    for action in ['develop','debug','language','validate','test','publish','files','import']:
        assert post(client,'/developer/workspace/plugins/hello_plugin/'+action).status_code==404
        assert post(client,'/plugins/registry/hello_plugin/'+action).status_code==404
    assert not set(PERMISSIONS)&{'plugins:create','plugins:edit','plugins:debug','plugins:test','plugins:validate','plugins:publish'}


def test_discovery_enable_configuration_reload_and_recoverable_delete(package):
    client,_,folder=package
    detail=client.get('/plugins/registry/hello_plugin').json
    assert detail['published_version']=='1.0.0' and detail['validation']['valid']
    assert post(client,'/plugins/registry/hello_plugin/enable',{'enabled':True}).json['enabled']
    changed=metadata();changed['version']='1.1.0';changed['configuration']={'label':dict(type='string',required=True)}
    install(folder,changed)
    assert post(client,'/plugins/discovery').json['registered']==['hello_plugin']
    assert client.get('/plugins/registry/hello_plugin').json['enabled']
    assert post(client,'/plugins/registry/hello_plugin/configuration',{'values':{'label':'Reviewed'}}).status_code==200
    assert client.get('/plugins/registry/hello_plugin/configuration').json['values']=={'label':'Reviewed'}
    detail=client.get('/plugins/registry/hello_plugin').json
    assert len(detail['versions'])==2
    assert post(client,'/plugins/registry/hello_plugin/rollback',{'version':'1.0.0'}).status_code==200
    assert post(client,'/plugins/discovery').json['registered']==[]
    assert client.get('/plugins/registry/hello_plugin').json['published_version']=='1.0.0'
    assert post(client,'/plugins/registry/hello_plugin/rollback',{'version':'1.1.0'}).status_code==200
    (folder/'hello_plugin'/'main.py').write_text('raise RuntimeError("must not execute on discovery")')
    assert post(client,'/plugins/discovery').json['invalid']
    assert client.get('/plugins/registry/hello_plugin').json['published_version']=='1.1.0'
    response=post(client,'/plugins/registry/hello_plugin/delete',{'revision':detail['revision']})
    assert response.status_code==200 and response.json['recoverable']
    assert not (folder/'hello_plugin').exists()
    assert client.get('/plugins/registry').json['plugins']==[]
    with app.app_context():
        assert db().execute('SELECT count(*) FROM developer_versions').fetchone()[0]==2


def test_unauthorized_protected_and_csrf(package,monkeypatch):
    client,_,_=package
    monkeypatch.setitem(app.config,'PROTECTED_PLUGIN_IDS',('hello_plugin',))
    assert post(client,'/plugins/registry/hello_plugin/delete',{'revision':1}).status_code==403
    assert client.post('/plugins/discovery').status_code==403
    other,_=browser('User')
    for path in ['/plugins/discovery','/plugins/registry/hello_plugin/enable','/plugins/registry/hello_plugin/run','/plugins/registry/hello_plugin/delete']:
        assert post(other,path,{'enabled':True,'revision':1}).status_code==403
    assert client.get('/plugins/registry/hello_plugin').status_code==200


def test_normal_execution_contract_and_revocation(package,monkeypatch):
    client,_,_=package;captured=[]
    def worker(method,path,value=None):
        if path=='/health':return {'ready':True}
        if path=='/jobs':
            captured.append(value)
            return dict(id='job1',status='Running')
        return dict(id='job1',status='Canceled' if path.endswith('/cancel') else 'Succeeded',stdout='Hello World\n',stderr='Hello diagnostic\n',exit_code=0,duration=.1)
    monkeypatch.setattr(plugin_execution,'call',worker)
    assert post(client,'/plugins/registry/hello_plugin/run').status_code==409
    post(client,'/plugins/registry/hello_plugin/enable',{'enabled':True})
    started=post(client,'/plugins/registry/hello_plugin/run')
    assert started.status_code==202,started.text
    assert captured[0]['mode']=='run' and captured[0]['token']==''
    assert store.inspect_archive(base64.b64decode(captured[0]['archive']))[0]==package_entries()
    result=client.get('/plugins/executions/'+started.json['id'])
    assert result.json['stdout']=='Hello World\n' and result.json['stderr']=='Hello diagnostic\n'
    assert result.json['status']=='Succeeded'
    with app.app_context():
        assert db().execute('SELECT revoked FROM api_tokens WHERE id=(SELECT grant_id FROM developer_executions)').fetchone()[0]
    started=post(client,'/plugins/registry/hello_plugin/run')
    assert post(client,'/plugins/executions/'+started.json['id']+'/cancel').json['status']=='Canceled'


def test_forward_migration_preserves_packages_configuration_and_is_idempotent(package):
    _,_,_=package
    with app.app_context():
        connection=db()
        connection.execute('CREATE TABLE developer_files(plugin_id TEXT,path TEXT,body BLOB,directory INTEGER)')
        connection.execute('DELETE FROM plugin_packages')
        connection.executemany('INSERT INTO developer_files VALUES(?,?,?,?)',[("hello_plugin",name,item['body'],0) for name,item in package_entries().items()])
        connection.execute("UPDATE developer_plugins SET configuration='{\"saved\":true}'")
        connection.execute("INSERT INTO role_permissions VALUES('User','plugins:edit')")
        connection.execute("INSERT INTO role_permissions VALUES('User','plugins:create')")
        connection.commit()
        store.retire_editor_schema(connection);store.retire_editor_schema(connection)
        assert store.files(connection,'hello_plugin')==package_entries()
        assert connection.execute('SELECT configuration FROM developer_plugins').fetchone()[0]=='{"saved":true}'
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='developer_files'").fetchone()
        assert connection.execute("SELECT 1 FROM role_permissions WHERE role_name='User' AND permission='plugins:install'").fetchone()
        assert not connection.execute("SELECT 1 FROM role_permissions WHERE permission='plugins:edit'").fetchone()


def test_invalid_and_symlink_packages_are_not_imported(package):
    client,_,folder=package
    bad=folder/'invalid';bad.mkdir();(bad/'plugin.json').write_text('{}')
    linked=install(folder,metadata('linked_plugin'))
    (linked/'main.py').unlink();(linked/'main.py').symlink_to(Path(__file__))
    result=post(client,'/plugins/discovery').json
    assert len(result['invalid'])==2
    assert len(client.get('/plugins/registry').json['plugins'])==1


def test_legacy_complete_backup_migrates_source_and_preserves_supported_data(package,tmp_path):
    from malware_families import initialize as initialize_families
    from test_malware_families import make_backup
    from installation_backup import restore_installation
    client,uid,_=package
    with app.app_context():
        connection=db()
        initialize_families(connection)
        connection.execute('CREATE TABLE developer_files(plugin_id TEXT,path TEXT,body BLOB,directory INTEGER)')
        connection.execute('DELETE FROM plugin_packages')
        connection.execute('DROP TABLE plugin_packages')
        connection.executemany('INSERT INTO developer_files VALUES(?,?,?,?)',[("hello_plugin",name,item['body'],0) for name,item in package_entries().items()])
        connection.execute("UPDATE developer_plugins SET configuration='{\"preserved\":true}'")
        connection.commit()
    try:
        archive=tmp_path/'old-installation.zip';archive.write_bytes(make_backup(client))
        destination=tmp_path/'restored';restore_installation(archive,destination)
        with sqlite3.connect(destination/'workflow.sqlite3') as connection:
            from backup_workspace import schema
            assert schema(connection)==app.extensions['backup_workspace'].expected_schema
            connection.row_factory=sqlite3.Row
            assert store.files(connection,'hello_plugin')==package_entries()
            assert connection.execute('SELECT configuration FROM developer_plugins').fetchone()[0]=='{"preserved":true}'
            assert connection.execute('SELECT count(*) FROM developer_versions').fetchone()[0]==1
            assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='developer_files'").fetchone()
            assert connection.execute('SELECT count(*) FROM users WHERE id=?',(uid,)).fetchone()[0]==1
    finally:
        # Keep the process's live test schema current for subsequent fixtures.
        with app.app_context():store.retire_editor_schema(db())


def test_secret_configuration_stays_encrypted_and_outside_plugin_context(package,monkeypatch):
    from developer_configuration import unseal
    client,_,folder=package
    value=metadata();value['version']='1.1.0'
    value['configuration']={'label':dict(type='string',required=True),'service_key':dict(type='string',secret=True,required=True)}
    install(folder,value);assert post(client,'/plugins/discovery').status_code==200
    assert post(client,'/plugins/registry/hello_plugin/configuration',{'values':{'label':'safe'},'secrets':{'service_key':'fixture-secret'}}).status_code==200
    visible=client.get('/plugins/registry/hello_plugin/configuration')
    assert 'fixture-secret' not in visible.text and visible.json['configured_secrets']==['service_key']
    with app.app_context():
        row=db().execute('SELECT * FROM developer_plugins').fetchone()
        assert b'fixture-secret' not in row['secret_box']
        assert unseal(row['secret_box'],app.config['SECRET_KEY'])=={'service_key':'fixture-secret'}
    jobs=[]
    def worker(method,path,payload=None):
        if path=='/health':return {'ready':True}
        jobs.append(payload);return dict(id='job',status='Running')
    monkeypatch.setattr(plugin_execution,'call',worker)
    assert post(client,'/plugins/registry/hello_plugin/enable',{'enabled':True}).status_code==200
    assert post(client,'/plugins/registry/hello_plugin/run').status_code==202
    assert jobs[0]['context']['configuration']=={'label':'safe'}
    assert jobs[0]['secrets']=={'service_key':'fixture-secret'}


def test_operational_sdk_grant_is_case_scoped_and_revoked(package,monkeypatch):
    import httpx
    from mws_sdk import MWSClient
    from test_api import new_case
    client,uid,folder=package
    with app.app_context():
        username=db().execute('SELECT username FROM users WHERE id=?',(uid,)).fetchone()[0]
    headers={'Authorization':'Bearer mare_test_'+username}
    cid=new_case(client,headers);other=new_case(client,headers)
    value=metadata();value['version']='1.1.0';value['permissions']=['cases:read']
    install(folder,value);post(client,'/plugins/discovery')
    token=[]
    def worker(method,path,payload=None):
        if path=='/health':return {'ready':True}
        if path=='/jobs':token.append(payload['token']);return dict(id='job',status='Running')
        return dict(status='Canceled',stdout='',stderr='',duration=.1,exit_code=143)
    monkeypatch.setattr(plugin_execution,'call',worker)
    post(client,'/plugins/registry/hello_plugin/enable',{'enabled':True})
    assert post(client,'/plugins/registry/hello_plugin/run',{'archive':'arbitrary source'}).status_code==400
    started=post(client,'/plugins/registry/hello_plugin/run',{'case_id':cid})
    assert started.status_code==202
    scoped={'Authorization':'Bearer '+token[-1]}
    with MWSClient('http://isolated.test',token[-1],transport=httpx.WSGITransport(app=app),retries=0) as sdk:
        assert sdk.cases.get(cid).case.id==cid
    assert client.get('/api/v1/cases/'+str(other),headers=scoped).status_code==403
    assert client.get('/api/v1/cases',headers=scoped).status_code==403
    assert client.patch('/api/v1/cases/'+str(cid),json={'name':'blocked'},headers=scoped).status_code==403
    assert post(client,'/plugins/executions/'+started.json['id']+'/cancel').status_code==200
    assert client.get('/api/v1/cases/'+str(cid),headers=scoped).status_code==401
    # An upgraded instance revokes old language/debug capabilities, while retaining audit records.
    started=post(client,'/plugins/registry/hello_plugin/run',{'case_id':cid})
    with app.app_context():
        db().execute("UPDATE developer_executions SET mode='language' WHERE id=?",(started.json['id'],));db().commit()
        store.retire_editor_schema(db())
        assert db().execute('SELECT status FROM developer_executions WHERE id=?',(started.json['id'],)).fetchone()[0]=='Canceled'
    assert client.get('/api/v1/cases/'+str(cid),headers={'Authorization':'Bearer '+token[-1]}).status_code==401
