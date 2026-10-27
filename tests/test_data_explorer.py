import io
import json
import zipfile
import pytest
from app import app,db,ROOT,ensure_package,build_archive
from data_explorer import graph,permissions,LIMIT
from tagging import create as tag
from test_threat_actors import setup,create as actor_create,edit as actor_edit
from test_malware_families import create as family_create


def scenario():
    c,uid,cid,*_=setup()
    f=family_create(c,aliases=['Family alias'])
    a=actor_create(c,aliases=['Actor alias'],known_families=[f])
    with app.app_context():
        unconfigured=tag(db(),'TA_UNCONFIGURED')[0]
        db().execute('INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)',(cid,unconfigured,'2026'))
        db().commit()
    return c,uid,cid,f,a


def test_authorized_graph_real_edges_dedup_search_and_navigation():
    c,uid,cid,f,a=scenario()
    for path in ('/data-explorer','/data-explorer/data',f'/data-explorer/cases/{cid}/contents'):
        assert app.test_client().get(path).status_code==302
        assert c.get(path).status_code==200
    html=c.get('/data-explorer').text
    assert 'class="data-explorer-nav" href="/data-explorer" aria-current="page"' in html
    response=c.get('/data-explorer/data');data=response.json
    assert response.headers['Cache-Control']=='private, no-store'
    assert len(data['nodes'])==3 and len(data['edges'])==3
    case_node=next(n for n in data['nodes'] if n['kind']=='case')
    assert case_node['stage']==1 and case_node['status']=='Malware Analysis'
    assert all('stage' not in n for n in data['nodes'] if n['kind']!='case')
    assert len({e['id'] for e in data['edges']})==3
    assert {e['explanation'] for e in data['edges']}=={'Case carries MAL_EXISTING','Case carries TA_TEST','Configured profile association'}
    assert all('long_description' not in n for n in data['nodes'])
    assert c.get('/data-explorer/data?q=actor+alias').json['total']==3
    assert c.get('/data-explorer/data?q=TA_TEST').json['total']==3
    assert c.get('/data-explorer/data?type=family&type=actor').json['total']==2
    assert len(c.get('/data-explorer/data?type=family&type=actor').json['edges'])==1
    assert c.get('/data-explorer/data?q=absent').json['total']==0
    assert c.get('/data-explorer/data?type=invalid').status_code==400
    assert actor_edit(c,a,known_families=[]).status_code==302
    assert len(c.get('/data-explorer/data').json['edges'])==2
    with app.app_context():
        db().execute('DELETE FROM threat_actors WHERE id=?',(a,));db().commit()
    assert c.get('/data-explorer/data').json['total']==2


def test_permission_filtered_nodes_edges_counts_contents_and_downloads():
    c,uid,cid,f,a=scenario()
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('Explorer limited')")
        db().execute("INSERT INTO role_permissions VALUES('Explorer limited','tags:read')")
        db().execute("UPDATE users SET role='Explorer limited' WHERE id=?",(uid,));db().commit()
    assert {n['kind'] for n in c.get('/data-explorer/data').json['nodes']}=={'family','actor'}
    assert c.get(f'/data-explorer/cases/{cid}/contents').status_code==403
    assert c.get(f'/data-explorer/cases/{cid}/file?path=scripts/secret.py').status_code==403
    with app.app_context():
        db().execute("DELETE FROM role_permissions WHERE role_name='Explorer limited'")
        db().execute("INSERT INTO role_permissions VALUES('Explorer limited','cases:read')");db().commit()
    data=c.get('/data-explorer/data').json
    assert len(data['nodes'])==1 and data['edges']==[]
    assert c.get('/data-explorer/data?q=TA_TEST').json['total']==0
    summary=c.get(f'/data-explorer/cases/{cid}/contents').json
    assert summary['categories']==[] and set(summary['restricted'])=={'files','images','reports','indicators','references'}
    for category in summary['restricted']:
        assert c.get(f'/data-explorer/cases/{cid}/contents/{category}').status_code==403
    with app.app_context():
        db().execute("DELETE FROM role_permissions WHERE role_name='Explorer limited'");db().commit()
    assert c.get('/data-explorer').status_code==403
    assert 'DATA EXPLORER</a>' not in c.get('/dashboards').text


def save_contents(c,cid):
    # These endpoints publish the exact CSV carriers consumed by Standard export.
    r=c.post(f'/cases/{cid}/indicators',data={'csrf':'family-csrf','revision':'0','rows':json.dumps([['domain','one.example','First'],['ip-dst','192.0.2.1','Second']])})
    assert r.status_code==200,r.text
    r=c.post(f'/cases/{cid}/references',data={'csrf':'family-csrf','revision':'0','rows':json.dumps([['https://example.com','Source'],['javascript:alert(1)','Untrusted value']])})
    assert r.status_code==200,r.text
    with app.app_context():
        root=ensure_package(cid)
        for rel,body in {'reports/research.pdf':b'%PDF-1.4 saved', 'reports/extra.docx':b'extra doc',
            'reports/sections/private.md':b'RAW ONLY','reports/sections/assets/private.png':b'RAW SOURCE',
            'reports/malware-analysis-report.docx':b'current excluded by Standard rule',
            'scripts/one.py':b'print(1)','supporting/chart.png':b'image','samples/private.zip':b'sample',
            'scripts/backups/old.py':b'backup'}.items():
            path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
        (root/'scripts'/'link.py').symlink_to(root/'scripts'/'one.py')
    return root


def test_summary_matches_real_standard_archive_without_archive_generation(monkeypatch):
    c,uid,cid,*_=scenario();root=save_contents(c,cid)
    with app.app_context():
        before=db().total_changes
        snapshot={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    monkeypatch.setattr('app.ensure_package',lambda *a:pytest.fail('Explorer scaffolded files'))
    monkeypatch.setattr('app.build_archive',lambda *a,**k:pytest.fail('Explorer generated archive'))
    summary=c.get(f'/data-explorer/cases/{cid}/contents')
    assert summary.status_code==200,summary.text
    counts={x['kind']:x['count'] for x in summary.json['categories']}
    assert counts=={'indicators':2,'references':2,'reports':2,'images':1,'files':3}
    assert snapshot=={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    refs=c.get(f'/data-explorer/cases/{cid}/contents/references').json
    assert refs['items'][1]['cells'][0]=='javascript:alert(1)'
    report=c.get(f'/data-explorer/cases/{cid}/contents/reports').json['items'][0]
    response=c.get(report['download'])
    assert response.status_code==200 and response.headers['X-Content-Type-Options']=='nosniff'
    assert 'sandbox' in response.headers['Content-Security-Policy']
    for rel in ('reports/sections/private.md','samples/private.zip','scripts/link.py','../workflow.sqlite3'):
        assert c.get(f'/data-explorer/cases/{cid}/file',query_string={'path':rel}).status_code==404
    monkeypatch.undo()
    with app.app_context():
        output,name=build_archive(cid,'standard')
    with output,zipfile.ZipFile(output) as archive:
        manifest=json.loads(archive.read(name+'/manifest.json'))
        paths={item['path'] for item in manifest['files']}|{'manifest.json'}
    categorized=set()
    for category in ('reports','images','files'):
        for item in c.get(f'/data-explorer/cases/{cid}/contents/{category}').json['items']:
            assert item['filename'] not in categorized;categorized.add(item['filename'])
    assert categorized|{'iocs/indicators.csv','iocs/indicators.stix.json','supporting/references.csv'}==paths


def test_zero_counts_read_only_missing_package_and_paging():
    c,uid,cid,*_=scenario()
    summary=c.get(f'/data-explorer/cases/{cid}/contents').json
    assert {x['kind']:x['count'] for x in summary['categories']}=={'files':2}
    with app.app_context():
        root=ROOT/'cases'/str(cid)/'mip'
        (root/'supporting'/'references.csv').write_text('Link,Description\n'+'https://example.com,source\n'*201)
    data=c.get(f'/data-explorer/cases/{cid}/contents/references?page=1').json
    assert data['count']==201 and data['pages']==2 and len(data['items'])==1
    assert c.get(f'/data-explorer/cases/{cid}/contents/references?page=-1').status_code==400
    assert c.get('/data-explorer/cases/99999/contents').status_code==404
    with app.app_context():
        new=db().execute("INSERT INTO cases(number,name,created) VALUES('UNSCAFFOLDED','No package','2026')").lastrowid;db().commit()
    assert c.get(f'/data-explorer/cases/{new}/contents').status_code==200
    assert not (ROOT/'cases'/str(new)).exists()


def test_large_graph_explicit_limit_focused_search_and_constant_queries():
    c,uid,cid,*_=scenario()
    with app.app_context():
        db().executemany("INSERT INTO cases(number,name,created) VALUES(?,?,'2026')",[(f'LIMIT-{i}',f'Unrelated {i}') for i in range(LIMIT)])
        db().commit()
    response=c.get('/data-explorer/data')
    assert response.status_code==413 and response.json['total']==LIMIT+3
    assert 'nodes' not in response.json
    assert c.get('/data-explorer/data?q=Family+alias').json['total']==3


def test_stix_only_counts_predict_export_refresh_without_writes_and_queries_are_batched():
    from flask import g
    c,uid,cid,*_=scenario();root=save_contents(c,cid)
    (root/'iocs'/'indicators.csv').unlink()
    (root/'iocs'/'indicators.stix.json').unlink()
    response=c.get(f'/data-explorer/cases/{cid}/contents')
    assert next(x for x in response.json['categories'] if x['kind']=='indicators')['count']==2
    assert not (root/'iocs'/'indicators.stix.json').exists()
    with app.test_request_context('/data-explorer/data'):
        g.user=db().execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        statements=[];db().set_trace_callback(statements.append)
        try:
            allowed=permissions(db());result,status=graph(db(),allowed)
        finally:db().set_trace_callback(None)
        assert status==200 and result['total']==3
        assert len([s for s in statements if s.startswith('WITH nodes')])==3
        before=db().total_changes
        from data_explorer import package_categories
        record=db().execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()
        package_categories(db(),record,root,allowed)
        assert db().total_changes==before
