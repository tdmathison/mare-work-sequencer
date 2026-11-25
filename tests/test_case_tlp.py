"""Case TLP validation, privacy, portability and generated-document markings."""
import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path
import pytest
from docx import Document
from app import app, db, run, ROOT, backup_helpers
import case_tlp
from test_api import make_user
from test_backups import setup_backup_case
from test_case_sync import preview, apply


def session_client(role='Administrator', name='tlp-analyst'):
    uid, headers = make_user(name, role)
    client = app.test_client()
    with client.session_transaction() as s: s.update(uid=uid,version=1,csrf='tlp-token')
    return client, uid, headers


def test_migration_is_idempotent_preserves_valid_values_and_enforces_storage():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE cases(id INTEGER PRIMARY KEY,tlp TEXT)')
    for value in [None, '', *case_tlp.METADATA]: con.execute('INSERT INTO cases(tlp) VALUES(?)',(value,))
    case_tlp.initialize(con); case_tlp.initialize(con)
    assert [r[0] for r in con.execute('SELECT tlp FROM cases')] == [case_tlp.DEFAULT,case_tlp.DEFAULT,*case_tlp.METADATA]
    for value in [None,'','AMBER','TLP:WHITE','TLP-AMBER',42]:
        with pytest.raises(sqlite3.IntegrityError): con.execute('INSERT INTO cases(tlp) VALUES(?)',(value,))
    fresh = sqlite3.connect(':memory:');fresh.execute('CREATE TABLE cases(id INTEGER PRIMARY KEY)')
    fresh.execute('INSERT INTO cases DEFAULT VALUES');case_tlp.initialize(fresh);case_tlp.initialize(fresh)
    assert fresh.execute('SELECT tlp FROM cases').fetchone()[0] == 'TLP:AMBER'


def test_system_default_is_admin_only_applies_only_to_new_cases_and_validates():
    client,uid,h = session_client()
    old=client.post('/api/v1/cases',headers=h,json={'name':'Saved default'}).json['case']
    assert old['tlp']=='TLP:AMBER'
    for value in case_tlp.METADATA:
        assert client.post('/settings/default-case-tlp',data={'csrf':'tlp-token','tlp':value}).status_code==302
        made=client.post('/api/v1/cases',headers=h,json={'name':value})
        assert made.status_code==201 and made.json['case']['tlp']==value
        assert client.get(f"/api/v1/cases/{old['id']}",headers=h).json['case']['tlp']=='TLP:AMBER'
    for value in [None,'','TLP:WHITE','TLP-AMBER',[],42]:
        assert client.post('/api/v1/cases',headers=h,json={'name':'Bad','tlp':value}).status_code==400
        assert client.patch(f"/api/v1/cases/{old['id']}",headers=h,json={'tlp':value}).status_code==400
    assert client.post('/settings/default-case-tlp',data={'csrf':'tlp-token','tlp':'bad'}).status_code==400
    assert client.post('/settings/default-case-tlp',data={'tlp':'TLP:RED'}).status_code==403
    user,_,_=session_client('User','tlp-user')
    assert user.post('/settings/default-case-tlp',data={'csrf':'tlp-token','tlp':'TLP:RED'}).status_code==403
    assert 'Save Default Case TLP' not in user.get('/settings/general').text
    form=client.get('/cases/new').text
    assert 'value="TLP:CLEAR"' in form and 'data-tlp-select' in form
    invalid=client.post('/cases',data={'csrf':'tlp-token','name':'','tlp':'TLP:GREEN'})
    assert invalid.status_code==400 and 'value="TLP:GREEN" data-color="#33FF00"' in invalid.text


def test_edits_permissions_closed_cases_board_markers_and_activity():
    c,uid,h=session_client()
    made=c.post('/api/v1/cases',headers=h,json={'name':'Designated','owner_id':uid,'tlp':'TLP:GREEN'}).json['case']
    cid=made['id']
    assert c.patch(f'/api/v1/cases/{cid}',headers=h,json={'tlp':'TLP:AMBER+STRICT'}).status_code==200
    page=c.get(f'/cases/{cid}').text
    assert 'edit-case-tlp' in page and 'TLP:AMBER+STRICT' in page
    for view in ('cards','table'):
        html=c.get('/?view='+view).text
        assert f'data-tlp-case="{cid}"' in html
        assert 'aria-label="TLP:AMBER+STRICT" title="TLP:AMBER+STRICT"' in html
        assert 'data-tlp-symbol aria-hidden="true">+</span>' in html
    with app.app_context():
        assert db().execute("SELECT count(*) FROM audit WHERE action LIKE '%TLP%AMBER+STRICT%'").fetchone()[0]
        assert db().execute("SELECT count(*) FROM notes WHERE case_id=? AND event_type='case.tlp_changed'",(cid,)).fetchone()[0]
        run('UPDATE cases SET stage=3 WHERE id=?',(cid,))
    assert c.patch(f'/api/v1/cases/{cid}',headers=h,json={'tlp':'TLP:CLEAR'}).status_code==409
    assert c.post(f'/cases/{cid}',data={'csrf':'tlp-token','name':'Designated','tlp':'TLP:CLEAR'}).status_code==409
    assert c.get(f'/api/v1/cases/{cid}',headers=h).json['case']['tlp']=='TLP:AMBER+STRICT'


def test_anonymous_counts_and_rows_filter_before_serialization_and_change_immediately():
    c,uid,h=session_client()
    ids={}
    for designation in case_tlp.METADATA:
        ids[designation]=c.post('/api/v1/cases',headers=h,json={'name':'Secret '+designation,'tlp':designation}).json['case']['id']
    public=app.test_client()
    data=public.get('/dashboards/cases/data')
    assert data.headers['Cache-Control']=='no-store'
    assert data.json['metrics']['not_started']==1
    with app.app_context():
        run('UPDATE cases SET stage=1 WHERE id=?',(ids['TLP:CLEAR'],))
    assert [row['title'] for row in public.get('/dashboards/cases/data').json['active']]==['Secret TLP:CLEAR']
    assert c.patch(f"/api/v1/cases/{ids['TLP:CLEAR']}",headers=h,json={'tlp':'TLP:RED'}).status_code==200
    assert public.get('/dashboards/cases/data').json['active']==[]
    assert public.get('/dashboards/cases/data').json['pagination']['total']==0
    # Authentication retains the existing inventory visibility for every designation.
    assert c.get('/api/v1/cases',headers=h).json['total']==5


def rewrite_legacy(blob, value='missing'):
    with zipfile.ZipFile(io.BytesIO(blob)) as source: files={n:source.read(n) for n in source.namelist()}
    key=next(n for n in files if n.endswith('/case-data.json'));mk=next(n for n in files if n.endswith('/manifest.json'))
    meta=json.loads(files[key]);manifest=json.loads(files[mk]);meta.pop('sync',None)
    if value=='missing': meta['case'].pop('tlp',None);manifest.pop('tlp',None)
    else: meta['case']['tlp']=value;manifest['tlp']=value
    files[key]=json.dumps(meta).encode()
    item=next(item for item in manifest['files'] if item['path']=='case-data.json')
    item.update(size=len(files[key]),sha256=hashlib.sha256(files[key]).hexdigest());files[mk]=json.dumps(manifest).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as target:
        for name,data in files.items(): target.writestr(name,data)
    return out.getvalue()


def test_raw_backup_tlp_round_trip_legacy_warning_and_no_silent_downgrade():
    client,cid,uid,post=setup_backup_case()
    with app.app_context(): run('UPDATE cases SET tlp=? WHERE id=?',('TLP:RED',cid))
    blob=post(f'/cases/{cid}/backup').data
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        manifest=json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/manifest.json'))))
        meta=json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('/case-data.json'))))
        assert manifest['tlp']==meta['case']['tlp']=='TLP:RED'
    # A new destination retains the explicit designation.
    from sync_helpers import other_destination
    other_destination();operation,plan=preview(client,blob)
    result=apply(client,operation)[0]
    with app.app_context(): assert db().execute('SELECT tlp FROM cases WHERE number=?',(result['destination_number'],)).fetchone()[0]=='TLP:RED'
    legacy=rewrite_legacy(blob)
    operation,plan=preview(client,legacy)
    assert 'TLP:AMBER' in plan['items'][0]['preview']['tlp_assumption']
    apply(client,operation,{'decision-0':'new'})
    with app.app_context(): assert db().execute('SELECT tlp FROM cases ORDER BY id DESC LIMIT 1').fetchone()[0]=='TLP:AMBER'
    # Explicitly linking an old archive must retain the existing destination TLP.
    operation,plan=preview(client,legacy)
    apply(client,operation,{'decision-0':'link','target-0':str(cid)})
    with app.app_context(): assert db().execute('SELECT tlp FROM cases WHERE id=?',(cid,)).fetchone()[0]=='TLP:RED'
    for value in [None,'','TLP:WHITE']:
        invalid=client.post('/import-export/import-raw',data={'csrf':'backup-token','backup':(io.BytesIO(rewrite_legacy(blob,value)),'invalid.zip')})
        assert invalid.status_code==302 and '/review/' not in (invalid.location or '')


def test_differing_imported_tlp_requires_conflict_resolution():
    client,cid,uid,post=setup_backup_case()
    blob=post(f'/cases/{cid}/backup').data
    with app.app_context(): run('UPDATE cases SET tlp=? WHERE id=?',('TLP:GREEN',cid))
    newer=post(f'/cases/{cid}/backup').data
    with app.app_context(): run('UPDATE cases SET tlp=? WHERE id=?',('TLP:RED',cid))
    operation,plan=preview(client,newer)
    info=plan['items'][0]['preview']
    assert info['classification']=='conflict' and info['tlp_conflict']=={'local':'TLP:RED','incoming':'TLP:GREEN'}
    assert apply(client,operation)[0]['action']=='Conflict unresolved'
    apply(client,operation,{'decision-0':'replace'})
    with app.app_context(): assert db().execute('SELECT tlp FROM cases WHERE id=?',(cid,)).fetchone()[0]=='TLP:GREEN'


def test_complete_backup_preserves_case_tlp_and_system_default(tmp_path):
    from test_backup_workspace import setup,export,inspect
    client,uid,cid,tid=setup()
    with app.app_context():
        run("INSERT INTO site_settings(name,value) VALUES('default_case_tlp','TLP:GREEN')")
        run("UPDATE cases SET tlp='TLP:AMBER+STRICT' WHERE id=?",(cid,))
    archive,_=export(client,complete=True)
    with app.app_context(): run("UPDATE cases SET tlp='TLP:RED' WHERE id=?",(cid,))
    inspected=inspect(client,archive)
    assert inspected['state']=='preview',inspected
    assert any('matching Case identities' in warning for warning in inspected['preview']['warnings'])
    folder=app.extensions['backup_workspace'].job_path(inspected['id'])/'restored'
    con=sqlite3.connect(folder/'workflow.sqlite3')
    assert con.execute('SELECT tlp FROM cases WHERE id=?',(cid,)).fetchone()[0]=='TLP:AMBER+STRICT'
    assert case_tlp.default(con)=='TLP:GREEN'
    con.close()


def test_official_colors_shared_markup_and_word_header_footer_markings(tmp_path):
    from reporting import fill_template, TOKENS
    expected=['#FF2B2B','#FFC000','#FFC000','#33FF00','#FFFFFF']
    assert [m['color'] for m in case_tlp.METADATA.values()]==expected
    template=tmp_path/'template.docx';doc=Document();
    for key in TOKENS: doc.add_paragraph('{{ '+key+' }}')
    doc.sections[0].header.paragraphs[0].text='Preserved header';doc.save(template)
    for value in case_tlp.METADATA:
        out=tmp_path/'report.docx'
        fill_template(template,out,{key:'Analysis' for key in TOKENS},'MARE-1','Title',tlp=value)
        rendered=Document(out)
        for section in rendered.sections:
            for story in [section.header,section.footer,section.first_page_header,section.first_page_footer,section.even_page_header,section.even_page_footer]:
                assert value in [p.text for p in story.paragraphs]
                run=next(p for p in story.paragraphs if p.text==value).runs[0]
                assert str(run.font.color.rgb)==case_tlp.METADATA[value]['color'][1:]
                assert run.font.size.pt==12
        assert rendered.sections[0].header.paragraphs[0].text=='Preserved header'


def test_synced_old_archive_replacement_preserves_destination_tlp():
    from test_case_sync import incoming
    client,cid,uid,post=setup_backup_case()
    blob=post(f'/cases/{cid}/backup').data
    # AMBER's implicit snapshot encoding preserves genuinely pre-TLP ancestry.
    with zipfile.ZipFile(io.BytesIO(blob)) as archive: files={n:archive.read(n) for n in archive.namelist()}
    key=next(n for n in files if n.endswith('/case-data.json'));mk=next(n for n in files if n.endswith('/manifest.json'))
    meta=json.loads(files[key]);meta['case'].pop('tlp');files[key]=json.dumps(meta).encode()
    manifest=json.loads(files[mk]);manifest.pop('tlp');item=next(r for r in manifest['files'] if r['path']=='case-data.json');item.update(size=len(files[key]),sha256=hashlib.sha256(files[key]).hexdigest());files[mk]=json.dumps(manifest).encode()
    old=io.BytesIO()
    with zipfile.ZipFile(old,'w') as archive:
        for name,value in files.items(): archive.writestr(name,value)
    descendant,_=incoming(old.getvalue(),'Legacy remote metadata update')
    with app.app_context(): run("UPDATE cases SET tlp='TLP:RED' WHERE id=?",(cid,))
    operation,plan=preview(client,descendant)
    assert plan['items'][0]['preview']['classification']=='conflict'
    result=apply(client,operation,{'decision-0':'replace'})[0]
    assert result['action']=='Replaced by explicit decision'
    with app.app_context():
        row=db().execute('SELECT name,tlp FROM cases WHERE id=?',(cid,)).fetchone()
        assert tuple(row)==('Legacy remote metadata update','TLP:RED')


def test_old_complete_preview_assigns_amber_and_malformed_explicit_values_fail(tmp_path):
    from test_backup_workspace import setup,inspect
    from test_malware_families import make_backup
    client,uid,cid,tid=setup()
    archive=make_backup(client)
    with zipfile.ZipFile(io.BytesIO(archive)) as source: original={n:source.read(n) for n in source.namelist()}
    def changed(old):
        files=dict(original);path=tmp_path/('old.sqlite3' if old else 'bad.sqlite3');path.write_bytes(files['data/workflow.sqlite3'])
        con=sqlite3.connect(path)
        names=con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND sql LIKE '%tlp%'").fetchall()
        for (name,) in names: con.execute('DROP TRIGGER "'+name+'"')
        if old: con.execute('ALTER TABLE cases DROP COLUMN tlp')
        else: con.execute("UPDATE cases SET tlp='TLP:WHITE'")
        con.commit();con.close();files['data/workflow.sqlite3']=path.read_bytes()
        if 'installation.json' in files:
            manifest=json.loads(files['installation.json']);manifest['files']['data/workflow.sqlite3']={'size':len(files['data/workflow.sqlite3']),'sha256':hashlib.sha256(files['data/workflow.sqlite3']).hexdigest()};files['installation.json']=json.dumps(manifest).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as target:
            for name,value in files.items(): target.writestr(name,value)
        return out.getvalue()
    result=inspect(client,changed(True),password='')
    assert result['state']=='preview',result
    assert any('TLP:AMBER' in warning for warning in result['preview']['warnings'])
    folder=app.extensions['backup_workspace'].job_path(result['id'])/'restored'
    con=sqlite3.connect(folder/'workflow.sqlite3');assert con.execute('SELECT DISTINCT tlp FROM cases').fetchall()==[('TLP:AMBER',)];con.close()
    invalid=inspect(client,changed(False),password='')
    assert invalid['state']=='failed' and 'TLP' in invalid['error'],invalid


def test_public_profile_case_counts_exclude_restricted_designations():
    from test_family_dashboard import family
    from test_actor_dashboard import actor
    with app.app_context():
        _,ft=family();_,at=actor()
        for value in case_tlp.METADATA:
            cid=run('INSERT INTO cases(number,name,stage,created,tlp) VALUES(?,?,1,?,?)',(value,'Linked research','2026',value)).lastrowid
            for tid in [ft,at]: run("INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,'2026')",(cid,tid))
    client=app.test_client()
    for endpoint in ['/dashboards/malware-families/data','/dashboards/threat-actors/data']:
        response=client.get(endpoint)
        assert response.headers['Cache-Control']=='no-store'
        assert response.json['metrics']['unique_linked_cases']==1


def test_report_pipeline_marks_saved_tlp_and_preserves_report_if_tlp_changes_mid_job(monkeypatch,tmp_path):
    import report_routes
    from reporting import TOKENS
    client,uid,h=session_client()
    cid=client.post('/api/v1/cases',headers=h,json={'name':'Marked report','owner_id':uid,'tlp':'TLP:RED'}).json['case']['id']
    assert client.post(f'/api/v1/cases/{cid}/stage',headers=h,json={'expected':0}).status_code==200
    document=Document()
    for key in TOKENS: document.add_paragraph('{{ '+key+' }}')
    template=io.BytesIO();document.save(template)
    assert client.post('/account/templates',data={'csrf':'tlp-token','template':(io.BytesIO(template.getvalue()),'TLP template.docx')}).status_code==302
    class InlineThread:
        def __init__(self,target,args,**kwargs): self.target,self.args=target,args
        def start(self): self.target(*self.args)
    monkeypatch.setattr(report_routes.threading,'Thread',InlineThread)
    endpoint=f'/cases/{cid}/generate-report'
    assert client.post(endpoint,data={'csrf':'tlp-token','executive_summary':'Initial report'}).status_code==202
    status=client.get(f'/cases/{cid}/report-job').json
    assert status['job']['status']=='completed',status
    report=ROOT/'cases'/str(cid)/'mip'/status['report_path'];original=report.read_bytes()
    assert 'TLP:RED' in [p.text for p in Document(report).sections[0].header.paragraphs]
    render=report_routes.fill_template
    def concurrent_change(*args,**kwargs):
        render(*args,**kwargs)
        run("UPDATE cases SET tlp='TLP:GREEN' WHERE id=?",(cid,))
    monkeypatch.setattr(report_routes,'fill_template',concurrent_change)
    assert client.post(endpoint,data={'csrf':'tlp-token','executive_summary':'Changed report','previous':'backup'}).status_code==202
    status=client.get(f'/cases/{cid}/report-job').json
    assert status['job']['status']=='failed',status
    assert 'TLP changed' in str(status['job'])
    assert report.read_bytes()==original


def test_omitted_tlp_on_metadata_save_does_not_write_a_stale_designation(monkeypatch):
    import app as application
    client,uid,h=session_client()
    cid=client.post('/api/v1/cases',headers=h,json={'name':'Concurrent metadata','tlp':'TLP:RED'}).json['case']['id']
    original=application.run
    def intervening_write(sql,args=()):
        if sql.startswith('UPDATE cases SET name='):
            original("UPDATE cases SET tlp='TLP:GREEN' WHERE id=?",(cid,))
        return original(sql,args)
    monkeypatch.setattr(application,'run',intervening_write)
    response=client.post(f'/cases/{cid}',data={'csrf':'tlp-token','name':'Updated unrelated field'})
    assert response.status_code==302
    with app.app_context(): assert db().execute('SELECT tlp FROM cases WHERE id=?',(cid,)).fetchone()[0]=='TLP:GREEN'
