"""API-only regression tests against disposable application fixtures."""
import io
import json
from pathlib import Path
import pytest
from app import app, db, ROOT
from test_api import make_user, new_case, start_case
from test_explorer_research import configuration

@pytest.fixture
def api_account():
    uid, headers=make_user('sdk-api-admin')
    with app.app_context():
        from malware_families import initialize
        initialize(db())
    client=app.test_client()
    cid=new_case(client,headers)
    start_case(client,headers,cid,uid)
    return client,uid,headers,cid


def test_coverage_graph_views_tags_and_registry(api_account):
    c,uid,h,cid=api_account
    for endpoint in ('/coverage?scope=all','/explorer/graph','/tools','/plugins','/search?q='):
        response=c.get('/api/v1'+endpoint,headers=h)
        assert response.status_code==200,response.text
        assert app.test_client().get('/api/v1'+endpoint).status_code==401
    assert c.get('/api/v1/coverage?scope=all',headers=h).json['rows'][0]['number']
    created=c.post('/api/v1/explorer/views',headers=h,json={'name':'Saved SDK view','configuration':configuration(cid)})
    assert created.status_code==201,created.text
    vid=created.json['id']
    assert c.get('/api/v1/explorer/views/'+vid,headers=h).json['name']=='Saved SDK view'
    _,other=make_user('sdk-other')
    assert c.get('/api/v1/explorer/views/'+vid,headers=other).status_code==404
    assert c.post('/api/v1/tags',headers=h,json={'name':'MAL_SDK'}).status_code==200
    tid=c.get('/api/v1/tags?q=MAL_SDK',headers=h).json['tags'][0]['id']
    assert c.post(f'/api/v1/cases/{cid}/tags/{tid}/assign',headers=h,json={}).status_code==200
    assert c.get(f'/api/v1/cases/{cid}/tags',headers=h).json['tags'][0]['name']=='MAL_SDK'
    assert c.post(f'/api/v1/cases/{cid}/tags/{tid}/remove',headers=h,json={}).status_code==200
    assert not c.get(f'/api/v1/cases/{cid}/tags',headers=h).json['tags']


def test_profiles_roundtrip_aliases_associations_versions_and_files(api_account):
    c,uid,h,cid=api_account
    r=c.post('/api/v1/families',headers=h,json={'name':'SDK family','tag':'MAL_SDK','aliases':['Other name']})
    assert r.status_code==200,r.text
    f=c.get('/api/v1/families',headers=h).json['profiles'][0]
    assert f['aliases']==['Other name']
    r=c.post('/api/v1/actors',headers=h,json={'name':'SDK actor','tag':'TA_SDK','known_families':[f['id']]})
    assert r.status_code==200,r.text
    actor=c.get('/api/v1/actors',headers=h).json['profiles'][0]
    assert actor['associations'][0]['family_id']==f['id']
    r=c.post('/api/v1/actors/'+actor['id']+'/edit',headers=h,json={'version':actor['version'],'aliases':['Alias']})
    assert r.status_code==200,r.text
    actor=c.get('/api/v1/actors/'+actor['id'],headers=h).json['profile']
    assert actor['name']=='SDK actor' and actor['associations']
    assert c.post('/api/v1/actors/'+actor['id']+'/edit',headers=h,json={'version':1,'name':'Conflict'}).status_code==409
    f=c.get('/api/v1/families/'+f['id'],headers=h).json['profile']
    assert c.post('/api/v1/families/'+f['id']+'/edit',headers=h,json={'version':f['version'],'known_actors':[],'aliases':[]}).status_code==200
    f=c.get('/api/v1/families/'+f['id'],headers=h).json['profile']
    assert not f['aliases'] and not f['associations']
    r=c.post('/api/v1/families/'+f['id']+'/osint',headers=h,json={'version':f['version'],'title':'Research','url':'https://example.test/research','position':1})
    assert r.status_code==200,r.text
    f=c.get('/api/v1/families/'+f['id'],headers=h).json['profile']
    assert f['osint'][0]['title']=='Research'
    assert 'storage_ref' not in json.dumps(f)
    assert c.post('/api/v1/families/'+f['id']+'/delete',headers=h,json={'version':f['version'],'confirm_name':f['name']}).status_code==200
    assert c.get('/api/v1/families/'+f['id'],headers=h).status_code==404


def test_closed_workflow_and_permissions_for_extended_mutations(api_account):
    c,uid,h,cid=api_account
    source={'source_json':json.dumps('rule example { condition: true }'),'filename':'example.yara'}
    assert c.post(f'/api/v1/cases/{cid}/yara/file',headers=h,json=source).status_code==200
    with app.app_context():
        db().execute('UPDATE cases SET stage=3 WHERE id=?',(cid,));db().commit()
    for endpoint,data in [(f'/cases/{cid}/yara/file',source),(f'/cases/{cid}/indicators/import',{'csv':'domain,example.test,Observed'})]:
        assert c.post('/api/v1'+endpoint,headers=h,json=data).status_code==409
    assert c.post(f'/api/v1/cases/{cid}/reopen',headers=h).status_code==200
    assert c.post(f'/api/v1/cases/{cid}/indicators/import/preview',headers=h,json={'section_id':'default','format':'csv','csv':'domain,example.test,Observed'}).status_code==200
    r=c.post(f'/api/v1/cases/{cid}/indicators/import',headers=h,json={'section_id':'default','accepted_rows':[['domain','example.test','Observed']],'revision':0})
    assert r.status_code==200,r.text
    assert c.get(f'/api/v1/cases/{cid}/indicators/stix',headers=h).status_code==200
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('sdk-limited')")
        db().execute("INSERT INTO role_permissions VALUES('sdk-limited','cases:read')")
        db().execute("UPDATE users SET role='sdk-limited' WHERE id=?",(uid,));db().commit()
    coverage=c.get('/api/v1/coverage?scope=all',headers=h).json
    assert coverage['gap_total']==0 and coverage['rows'][0]['indicators']['state']=='unavailable'
    assert c.get('/api/v1/families',headers=h).status_code==403
    assert c.post(f'/api/v1/cases/{cid}/yara/file',headers=h,json=source).status_code==403
    assert c.post('/api/v1/backup-jobs',headers=h,json={'kind':'export'}).status_code==403


def test_tools_drafts_backup_job_ownership_and_filters(api_account,monkeypatch):
    c,uid,h,cid=api_account
    r=c.post('/api/v1/tools/text/process',headers=h,json={'operation':'domains','text':'EXAMPLE.TEST'})
    assert r.status_code==200 and r.json['text']=='example.test'
    r=c.post('/api/v1/tools/yara/draft',headers=h,json={'source_json':json.dumps('rule one { condition: true }'),'context':{'case_id':cid}})
    assert r.status_code==200,r.text
    assert c.get('/api/v1/tools/yara/state',headers=h).json
    # Inspect rejects missing uploads; no job is queued or production data contacted.
    assert c.post('/api/v1/backup-jobs',headers=h,json={'kind':'inspect'}).status_code==400
    r=c.get('/api/v1/cases?q=API&stage=1&sort=number&limit=1',headers=h)
    assert r.status_code==200 and r.json['total']==1
    assert c.get('/api/v1/cases?stage=99',headers=h).status_code==400
    assert c.get('/api/v1/cases?sort=unknown',headers=h).status_code==400


def test_profile_attachment_upload_download_and_failure_not_success(api_account):
    from test_family_reports import pdf
    c,uid,h,cid=api_account
    c.post('/api/v1/families',headers=h,json={'name':'Research','tag':'MAL_RESEARCH'})
    f=c.get('/api/v1/families',headers=h).json['profiles'][0]
    base='/api/v1/families/'+f['id']
    uploaded=c.post(base+'/reports',headers=h,data={'version':str(f['version']),'reports':(io.BytesIO(pdf()),'research.pdf')})
    assert uploaded.status_code==200,uploaded.text
    f=c.get(base,headers=h).json['profile'];attachment=f['reports'][0]
    assert c.get(base+'/reports/'+attachment['id']+'/download',headers=h).data==pdf()
    failed=c.post(base+'/reports/'+attachment['id']+'/delete',headers=h,json={'version':f['version'],'confirm':False})
    assert failed.status_code>=400,failed.text
    assert c.post(base+'/reports/'+attachment['id']+'/delete',headers=h,json={'version':f['version'],'confirm':True}).status_code==200
    assert not c.get(base,headers=h).json['profile']['reports']
    assert c.post('/api/v1/tags',headers=h,json={'name':'bad invalid tag!'}).status_code>=400


def test_real_encrypted_backup_jobs_over_rest(api_account,monkeypatch):
    import time
    c,uid,h,cid=api_account
    response=c.post('/api/v1/backup-jobs',headers=h,json={'kind':'export','complete':True,'passphrase':'SDK isolated backup passphrase'})
    assert response.status_code==202,response.text
    jid=response.json['id']
    def wait(jid):
        for _ in range(400):
            response=c.get('/api/v1/backup-jobs/'+jid,headers=h)
            assert response.status_code==200,response.text
            data=response.json
            if data['state'] not in ('queued','running'):return data
            time.sleep(.025)
        pytest.fail('Disposable backup job timed out')
    result=wait(jid)
    assert result['state']=='completed',json.dumps(result,indent=2)
    assert 'SDK isolated backup passphrase' not in json.dumps(result)
    archive=c.get('/api/v1/backup-jobs/'+jid+'/download',headers=h)
    assert archive.status_code==200
    _,other=make_user('sdk-backup-other')
    assert c.get('/api/v1/backup-jobs/'+jid,headers=other).status_code==404
    inspection=c.post('/api/v1/backup-jobs',headers=h,data={'kind':'inspect','passphrase':'SDK isolated backup passphrase','archive':(io.BytesIO(archive.data),'encrypted.zip')})
    assert inspection.status_code==202,inspection.text
    preview=wait(inspection.json['id'])
    assert preview['state']=='preview',preview
    # Applying is intentionally explicit: a complete preview cannot be applied without acknowledgement.
    assert c.post('/api/v1/backup-jobs/'+preview['id']+'/apply',headers=h,json={}).status_code in (400,409)


def test_request_identifiers_and_token_scoped_audit(api_account):
    c,uid,h,cid=api_account
    response=c.post(f'/api/v1/cases/{cid}/notes',headers=h,json={'body':'Traceable finding'})
    rid=response.headers['X-Request-ID']
    assert rid and response.headers['Cache-Control']=='private, no-store'
    with app.app_context():
        messages=[r[0] for r in db().execute('SELECT action FROM audit')]
    assert any('API token id=' in m and rid in m for m in messages)
    assert all(h['Authorization'][7:] not in m for m in messages)


def test_item_read_endpoints_on_closed_cases_and_admin_models(api_account):
    c,uid,h,cid=api_account
    task=c.post(f'/api/v1/cases/{cid}/tasks',headers=h,json={'title':'Task'}).json['task']['id']
    note=c.post(f'/api/v1/cases/{cid}/notes',headers=h,json={'body':'Finding'}).json['note']['id']
    c.post('/api/v1/tags',headers=h,json={'name':'MAL_ITEM'})
    tid=c.get('/api/v1/tags?q=MAL_ITEM',headers=h).json['tags'][0]['id']
    with app.app_context():
        from authorization import initialize_roles
        initialize_roles(db())
        db().execute('UPDATE cases SET stage=3 WHERE id=?',(cid,));db().commit()
    assert c.get(f'/api/v1/cases/{cid}/tasks/{task}',headers=h).json['task']['title']=='Task'
    assert c.get(f'/api/v1/cases/{cid}/notes/{note}',headers=h).json['note']['body']=='Finding'
    assert c.get(f'/api/v1/users/{uid}',headers=h).json['user']['id']==uid
    assert c.get('/api/v1/roles/Administrator',headers=h).json['name']=='Administrator'
    assert c.get(f'/api/v1/tags/{tid}',headers=h).json['tag']['name']=='MAL_ITEM'
    assert c.get(f'/api/v1/cases/999999/tasks/{task}',headers=h).status_code==404
