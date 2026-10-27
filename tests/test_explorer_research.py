import io
import json
import sqlite3
import zipfile
import pytest
from app import app,db
from explorer_views import validate_config,initialize
from explorer_shared import normalize,shared_edges
from explorer_research import shortest_paths
from test_data_explorer import scenario


def configuration(cid):
    return dict(version=1,query='',types=['case','family','actor'],contents=True,layout=dict(mode='clusters',direction='tb',center='selected',spacing='balanced',emphasis=True),positions={f'case:{cid}':dict(x=123,y=456)},viewport=dict(zoom=1,pan=dict(x=0,y=0)),expanded=[],selected=[f'case:{cid}'],focus=None,shared=dict(enabled=False,types=['md5','domain'],minimum=1))

def test_views_owned_versioned_validated_configuration_only():
    c,uid,cid,*_=scenario();config=configuration(cid)
    def post(path,**values):return c.post(path,data={'csrf':'family-csrf',**values})
    response=post('/data-explorer/views',name='Research',description='Saved positions',configuration=json.dumps(config));assert response.status_code==201,response.text
    vid=response.json['id'];assert c.get('/data-explorer/views/'+vid).json['configuration']==config
    assert c.get('/data-explorer/views').json['views'][0]['id']==vid
    bad={**config,'case_contents':{'secret':'not configuration'}}
    assert post('/data-explorer/views',name='Bad',configuration=json.dumps(bad)).status_code==400
    assert post('/data-explorer/views',name='Bad',configuration=json.dumps({**config,'version':2})).status_code==400
    assert post('/data-explorer/views',name='Bad',configuration=json.dumps({**config,'viewport':{'zoom':float('nan'),'pan':{'x':0,'y':0}}})).status_code==400
    assert c.post('/data-explorer/views',data={}).status_code==403
    with app.app_context():
        other=db().execute("INSERT INTO users(username,password,role,forced) VALUES('other-view-owner','unused','Administrator',0)").lastrowid;db().commit()
    with c.session_transaction() as session:session['uid']=other
    assert c.get('/data-explorer/views').json['views']==[]
    for method,path in [('get',''),('post','/update'),('post','/delete')]:assert getattr(c,method)('/data-explorer/views/'+vid+path,data={'csrf':'family-csrf'}).status_code==404
    with c.session_transaction() as session:session['uid']=uid
    assert post('/data-explorer/views/'+vid+'/update',name='Renamed',description='',configuration=json.dumps(config)).status_code==200
    assert post('/data-explorer/views/'+vid+'/delete').status_code==200
    assert c.get('/data-explorer/views/'+vid).status_code==404
    with app.app_context():assert db().execute('SELECT 1 FROM cases WHERE id=?',(cid,)).fetchone()


@pytest.mark.parametrize('kind,value,expected',[
 ('md5','A'*32,('md5','a'*32)),('md5','bad',None),('sha256','F'*64,('sha256','f'*64)),
 ('domain','EXAMPLE.COM.',('domain','example.com')),('domain','bad..com',None),
 ('ip-dst','2001:0db8::1',('ip-dst','2001:db8::1')),('ip','999.1.2.3',None),
 ('ip','fe80::1%en0',None),('filename','payload.exe',None),('unknown','x',None),
 ('url','HTTPS://Example.COM:443/Path?a=X',('url','https://example.com/Path?a=X')),
 ('url','https://user:password@example.com/',None),('url','javascript:alert(1)',None)])
def test_indicator_normalization(kind,value,expected):assert normalize(kind,value)==expected


def test_shared_indicators_dedup_distinct_types_freshness_and_permissions():
    c,uid,cid,*_=scenario()
    with app.app_context():
        other=db().execute("INSERT INTO cases(number,name,created,stage) VALUES('SHARED-2','Shared second','2026',1)").lastrowid;db().commit()
    rows=[['md5','A'*32,''],['md5','a'*32,'duplicate'],['domain','EXAMPLE.COM',''],['filename','same.exe',''],['url','https://example.com/Path?q=1',''],['ip-src','192.0.2.1','']]
    for case,values in [(cid,rows),(other,[['md5','a'*32,''],['domain','example.com.',''],['filename','same.exe',''],['url','https://example.com/path?q=1',''],['ip-dst','192.0.2.1','']])]:
        assert c.post(f'/cases/{case}/indicators',data={'csrf':'family-csrf','revision':'0','rows':json.dumps(values)}).status_code==200
    url='/data-explorer/shared-indicators'
    data=c.get(url).json;assert len(data['edges'])==1
    edge=data['edges'][0];assert edge['count']==2 and edge['computed'] and 'indicators' not in edge
    assert c.get(url+'?minimum=3').json['edges']==[]
    graph=c.get('/data-explorer/data').json;assert all(not e.get('computed') for e in graph['edges'])
    evidence=c.get(f'/data-explorer/evidence?source=case:{cid}&target=case:{other}&shared=1').json
    assert evidence['computed'] and len(evidence['indicators'])==2
    assert c.get(f'/data-explorer/evidence?source=case:{cid}&target=case:{other}').status_code==404
    with app.app_context():
        db().execute('DELETE FROM indicator_tables WHERE case_id=?',(other,));db().execute('DELETE FROM indicator_sections WHERE case_id=?',(other,));db().commit()
    assert c.get(url).json['edges']==[]
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('No indicator explorer')");db().execute("INSERT INTO role_permissions VALUES('No indicator explorer','cases:read')");db().execute("UPDATE users SET role='No indicator explorer' WHERE id=?",(uid,));db().commit()
    assert c.get(url).status_code==403
    assert c.get(f'/data-explorer/connections?source=case:{cid}&target=case:{other}&shared=1').status_code==403


def test_evidence_and_paths_use_authorized_records_and_limits():
    c,uid,cid,f,a=scenario();source=f'case:{cid}';target='actor:'+a
    response=c.get('/data-explorer/evidence',query_string={'source':source,'target':target});assert response.status_code==200
    assert response.json['relationship_type']=='Case tag assignment' and not response.json['computed']
    assert 'TA_TEST' in response.json['reason']
    path=c.get('/data-explorer/connections',query_string={'source':source,'target':target}).json;assert path['paths']==[[source,target]]
    assert c.get('/data-explorer/connections',query_string={'source':source,'target':target,'type':'family'}).status_code==400
    assert c.get('/data-explorer/connections',query_string={'source':source,'target':target,'type':'family','scope':'all'}).json['paths']==[[source,target]]
    assert c.get('/data-explorer/connections',query_string={'source':source,'target':source}).status_code==400
    with app.app_context():db().execute('DELETE FROM case_tags WHERE case_id=?',(cid,));db().commit()
    assert c.get('/data-explorer/evidence',query_string={'source':source,'target':target}).status_code==404
    assert c.get('/data-explorer/connections',query_string={'source':source,'target':target}).json['paths']==[]
    nodes=[{'id':x} for x in 'abcdef'];edges=[dict(source=x,target=y) for x,y in [('a','b'),('a','c'),('b','d'),('c','d'),('d','a'),('d','e')]]
    result=shortest_paths(nodes,edges,'b','c');assert len(result['paths'])==2
    assert shortest_paths(nodes,edges,'a','e',1)['limited']
    assert shortest_paths(nodes,edges,'a','f')['paths']==[]


def test_saved_view_migration_and_unmapped_owner_rejected_by_existing_restore_rules(tmp_path):
    from installation_backup import validate_database
    c,uid,cid,*_=scenario()
    response=c.post('/data-explorer/views',data={'csrf':'family-csrf','name':'Owner identity','configuration':json.dumps(configuration(cid))})
    assert response.status_code==201
    snapshot=tmp_path/'snapshot.sqlite3'
    with app.app_context():
        initialize(db());initialize(db())
        assert db().execute("SELECT count(*) FROM schema_migrations WHERE name='explorer-views-v1'").fetchone()[0]==1
        with sqlite3.connect(snapshot) as target:db().backup(target)
    with sqlite3.connect(snapshot) as connection:connection.execute("UPDATE explorer_views SET owner_uuid='unmapped-owner'")
    with pytest.raises(ValueError,match='broken record relationships'):validate_database(snapshot,True)


def test_common_indicator_limit_and_recorded_evidence_permissions():
    c,uid,cid,f,a=scenario()
    with app.app_context():
        nodes=[]
        for i in range(101):
            case=db().execute("INSERT INTO cases(number,name,created,stage) VALUES(?,?,?,1)",(f'COMMON-{i}',f'Common {i}','2026')).lastrowid
            db().execute('INSERT INTO indicator_tables(case_id,columns,rows,revision) VALUES(?,?,?,0)',(case,json.dumps(['type','value','description']),json.dumps([['md5','a'*32,''],['md5','A'*32,'duplicate']])))
            nodes.append({'id':f'case:{case}','uid':case,'kind':'case'})
        edges,limited=shared_edges(db(),{'cases:read':True,'indicators:read':True},nodes,{'md5'},1)
        assert limited and edges==[]
        db().execute("INSERT INTO roles(name) VALUES('Profile research only')");db().execute("INSERT INTO role_permissions VALUES('Profile research only','tags:read')");db().execute("UPDATE users SET role='Profile research only' WHERE id=?",(uid,));db().commit()
    hidden=c.get('/data-explorer/evidence',query_string={'source':f'case:{cid}','target':'family:'+f})
    assert hidden.status_code==404 and 'MAL_EXISTING' not in hidden.text
    allowed=c.get('/data-explorer/evidence',query_string={'source':'family:'+f,'target':'actor:'+a})
    assert allowed.status_code==200 and allowed.json['relationship_type']=='Configured profile association'
    assert c.get('/data-explorer/connection-objects?scope=all').json['nodes']
    assert all(n['kind']!='case' for n in c.get('/data-explorer/connection-objects?scope=all').json['nodes'])
