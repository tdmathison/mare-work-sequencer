"""STIX mapping, draft safety, preview/import and stable revision regressions."""
import copy
import io
import json
import uuid
import pytest
from stix2 import parse
from stix2.v21 import Indicator, Bundle, IPv4Address, DomainName, NetworkTraffic
from app import app, db, package
from indicators import load_table
from indicator_types import CATALOG,analyze
from indicator_stix import import_document,from_pattern,MAX_BYTES,MAX_OBJECTS,MAX_PATTERN
from test_indicators import setup
from test_case_sync import head,preview,apply
from test_backups import setup_backup_case

VALUES={'software':"Example's \\ App",'mobile-application-id':'com.Example.application','domain':'evil[.]example.com','hostname':'host.example.com','url':'hxxps://evil[.]example.com/a',
        'ip-src':'2001:db8::1','ip-dst':'192.0.2.1','mac-address':'aa:bb:cc:dd:ee:ff','filename':"sample's\\path.exe",
        'md5':'a'*32,'sha1':'b'*40,'sha256':'c'*64,'sha512':'d'*128,'email-src':'sender@example.com','email-dst':'to@example.com',
        'email-subject':"Test ' subject",'email-attachment':'file.exe','mutex':"test\\' OR 'injection",
        'regkey':r'HKLM\Software\Test','regkey|value':r'HKLM\Software\Test|value',
        'x509-fingerprint-sha1':'a'*40,'x509-fingerprint-sha256':'b'*64}
for algorithm in ('md5','sha1','sha256'):VALUES['filename|'+algorithm]='file.exe|'+VALUES[algorithm]


def stix_file(pattern,**kwargs):
    return Indicator(pattern=pattern,pattern_type='stix',pattern_version='2.1',description='Original description',**kwargs).serialize().encode()


@pytest.mark.parametrize('item',[item for item in CATALOG if item['export']=='native'],ids=lambda item:item['name'])
def test_catalog_patterns_and_round_trip(item):
    kind=item['name'];row=[kind,VALUES[kind],'original description']
    result=analyze(row);assert not result.get('error'),result
    parsed=parse(stix_file(result['pattern']),version='2.1')
    assert parsed.pattern==result['pattern']
    extracted=from_pattern(result['pattern'],row[2],kind)
    assert analyze(extracted)['key']==result['key']
    assert extracted[2]==row[2]


def test_aliases_unknown_and_invalid_values_are_not_inferred():
    for alias in ('SHA256','SHA-256','sha256'):
        assert analyze([alias,'a'*64,''])['row'][0]=='sha256'
    assert analyze(['domain-name','evil.example',''])['row'][0]=='domain'
    for label in ('IP','ipv4','ipv6','ipv4-addr'):
        assert 'Direction' in analyze([label,'192.0.2.1',''])['error']
    assert analyze(['SHA256','unfinished',''])['row']==['SHA256','unfinished','']
    assert analyze(['regkey','not a key','']).get('error')
    assert analyze(['filename|sha256','part|with|'+('a'*64),'']).get('error')
    assert analyze(['','partial','']).get('error')
    assert analyze(['','',''])['blank']


@pytest.mark.parametrize('pattern',[
    "[domain-name:value = 'a.example' OR domain-name:value = 'b.example']",
    "[domain-name:value = 'a.example' AND url:value = 'https://example.com']",
    "[domain-name:value != 'a.example']",
    "[domain-name:value = 'a.example'] REPEATS 2 TIMES",
    "[domain-name:value = 'a.example'] WITHIN 60 SECONDS",
    "[domain-name:value = 'a.example'] AND [domain-name:value = 'b.example']",
    "[file:size > 20]",
    "[file:'hashes.MD5' = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']",
    "[email-message:to_refs[0].value = 'user@example.com']",
])
def test_complex_patterns_are_skipped_without_flattening(pattern):
    rows,skipped=import_document(stix_file(pattern))
    assert rows==[] and len(skipped)==1 and skipped[0]['reason']


def test_observable_references_and_ambiguous_ip_mapping():
    address=IPv4Address(value='192.0.2.1')
    traffic=NetworkTraffic(src_ref=address.id,protocols=['tcp'])
    rows,skipped=import_document(Bundle(objects=[address,traffic]).serialize().encode())
    assert ['IP','192.0.2.1',''] in rows
    assert ['ip-src','192.0.2.1',''] in rows
    assert not skipped
    rows,skipped=import_document(traffic.serialize().encode())
    assert rows==[] and 'missing from this uploaded document' in skipped[0]['reason']
    assert 'never fetched' in skipped[0]['reason']


def test_non_stix_and_resource_limits():
    obj=json.loads(stix_file("[domain-name:value = 'a.example']"));obj['pattern_type']='yara';obj['pattern']='rule x {condition:true}'
    rows,skipped=import_document(json.dumps(obj).encode());assert not rows and 'Non-STIX' in skipped[0]['reason']
    for raw in (b'invalid',b'[]',b'null',b'\xff',b' '* (MAX_BYTES+1)):
        with pytest.raises(ValueError):import_document(raw)
    with pytest.raises(ValueError,match='2,000'):
        import_document(json.dumps({'type':'bundle','objects':[{}]*(MAX_OBJECTS+1)}).encode())
    obj['pattern_type']='stix';obj['pattern']='['+'x'*MAX_PATTERN+']'
    rows,skipped=import_document(json.dumps(obj).encode());assert not rows and '4,096' in skipped[0]['reason']


def test_stable_save_download_drafts_and_no_revision_feedback():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    response=post(base,revision=0,rows=json.dumps([['SHA256','a'*64,"Apostrophe's \\ text"]]))
    assert response.status_code==200 and response.json['stix']['available']
    sections=response.json['sections'];meta=copy.deepcopy(sections[0]['row_meta'][0])
    first=client.get(base+'/stix');assert first.status_code==200
    assert first.mimetype=='application/stix+json' and 'attachment' in first.headers['Content-Disposition']
    bundle=parse(first.data,version='2.1');indicator=next(obj for obj in bundle.objects if obj.type=='indicator')
    assert indicator.id==meta['id'] and 'indicator_types' not in indicator
    assert not indicator.get('defanged')
    assert any(obj.type=='grouping' for obj in bundle.objects)
    revision=head(cid)
    unchanged=post(base,revision=response.json['revision'],sections=json.dumps(sections),automatic='1')
    assert unchanged.status_code==200 and unchanged.json['revision']==response.json['revision']
    assert unchanged.json['sections']==sections
    assert head(cid)==revision
    assert client.get(base+'/stix').data==first.data
    sections[0]['rows'][0][2]='New description'
    edited=post(base,revision=unchanged.json['revision'],sections=json.dumps(sections))
    assert edited.json['sections'][0]['row_meta'][0]['id']==meta['id']
    assert edited.json['sections'][0]['row_meta'][0]['created']==meta['created']
    assert edited.json['sections'][0]['row_meta'][0]['modified']>meta['modified']
    sections=edited.json['sections'];sections[0]['rows'].append(['IP','192.0.2.1','unfinished']);sections[0]['row_meta'].append(None)
    draft=post(base,revision=edited.json['revision'],sections=json.dumps(sections),automatic='1')
    assert draft.status_code==200 and not draft.json['stix']['available']
    assert draft.json['rows'][-1][0]=='IP'
    assert not (package(cid)/'iocs/indicators.stix.json').exists()
    assert client.get(base+'/stix').status_code==409
    assert '192[.]0[.]2[.]1' in (package(cid)/'iocs/indicators.csv').read_text()
    assert b'Indicator STIX unavailable' in client.get(f'/cases/{cid}').data


def test_unified_preview_apply_duplicates_and_section_target():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    first=post(base,revision=0,sections=json.dumps([
        {'id':'default','title':'Default','description':'','rows':[['domain','evil[.]example.com','Existing']]},
        {'id':'other','title':'Other','description':'Original section description','rows':[]},
    ]))
    file=client.get(base+'/stix').data
    preview=post(base+'/import/preview',format='stix',section_id='default',stix=(io.BytesIO(file),'example.stix'))
    assert preview.status_code==200 and preview.json['rows'][0]['duplicate']
    assert preview.json['rows'][0]['row']==['domain','evil.example.com','Existing']
    applied=post(base+'/import',revision=first.json['revision'],section_id='default',accepted_rows=json.dumps([preview.json['rows'][0]['row']]))
    assert applied.json['added']==0 and applied.json['skipped_duplicates']==1
    assert len(applied.json['rows'])==1
    target=post(base+'/import/preview',format='csv',section_id='other',csv='TYPE,Value,Description\nSHA256,'+'a'*64+',Payload')
    assert target.json['rows'][0]['row'][0]=='sha256' and target.json['rows'][0]['normalized']
    imported=post(base+'/import',revision=applied.json['revision'],section_id='other',accepted_rows=json.dumps([target.json['rows'][0]['row']]))
    assert imported.json['added']==1 and len(imported.json['sections'][0]['rows'])==1
    assert imported.json['sections'][1]['description']=='Original section description'
    assert imported.json['sections'][1]['row_meta'][0]['id']!=first.json['sections'][0]['row_meta'][0]['id']
    unresolved=post(base+'/import/preview',format='csv',section_id='other',csv='IP,192.0.2.1,observed')
    assert unresolved.json['rows'][0]['reason'] and unresolved.json['rows'][0]['row'][0]=='IP'
    assert post(base+'/import',revision=0,section_id='default',accepted_rows='[]').status_code==400
    assert post(base+'/import/preview',format='stix',section_id='missing',stix=(io.BytesIO(file),'test.json')).status_code==400


def test_authorization_stages_and_preview_does_not_mutate():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    assert app.test_client().get(base+'/stix').status_code==302
    assert client.post(base+'/import/preview',data={'format':'csv','csv':'domain,a.example,','section_id':'default'}).status_code==403
    before=client.get(base).json
    assert post(base+'/import/preview',format='csv',csv='domain,a.example,',section_id='default').status_code==200
    assert client.get(base).json==before
    with app.app_context():db().execute('UPDATE cases SET stage=3 WHERE id=?',(cid,));db().commit()
    assert post(base+'/import/preview',format='csv',csv='domain,a.example,',section_id='default').status_code==409
    assert post(base,revision=0,rows='[]').status_code==409


def test_raw_identity_roundtrip_and_derived_stix_is_not_a_revision_input():
    client,cid,uid,post=setup_backup_case();base=f'/cases/{cid}/indicators'
    initial=post(base,revision=0,rows=json.dumps([['domain','example.com','']])).json
    before=head(cid)
    (package(cid)/'iocs/indicators.stix.json').write_text('invalid derived output')
    assert head(cid)==before
    assert client.get(base+'/stix').status_code==409
    post(base,revision=initial['revision'],sections=json.dumps(initial['sections']))
    blob=post(f'/cases/{cid}/backup').data
    operation,plan=preview(client,blob)
    assert plan['items'][0]['preview']['classification']=='unchanged'
    assert apply(client,operation)[0]['action']=='Unchanged'
    assert client.get(base).json['sections'][0]['row_meta']==initial['sections'][0]['row_meta']


def test_official_misp_attribute_conversion_when_available(tmp_path):
    import os
    import subprocess
    from indicator_stix import reconcile_rows,build_bundle
    python=os.environ.get('MARE_MISP_PYTHON')
    if not python:pytest.skip('Set MARE_MISP_PYTHON to an isolated official misp-stix environment')
    rows=[[kind,VALUES[kind],'Description '+kind] for kind in VALUES if kind not in ('software','mobile-application-id')]
    sections=reconcile_rows([dict(id='default',title='MISP compatibility fixture',description='Section context',rows=rows)],[])
    raw,_=build_bundle(sections);path=tmp_path/'misp-test.json';path.write_text(raw)
    result=subprocess.run([python,'tests/verify_indicator_misp.py',str(path)],capture_output=True,text=True,check=True)
    converted=json.loads(result.stdout)
    assert not converted['errors'] and not converted['warnings']
    assert converted['events']==['MISP compatibility fixture']
    attributes={item['type']:item for item in converted['attributes']}
    for row in rows:
        checked=analyze(row);values=checked['key'][1]
        expected=values[1] if row[0].startswith('ip-') else '|'.join(values)
        assert attributes[row[0]]['value']==expected
        assert attributes[row[0]]['comment']=='Description '+row[0]


def test_atomic_publication_failure_restores_prior_outputs(monkeypatch):
    import indicators
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    original=post(base,revision=0,rows=json.dumps([['domain','old.example','']])).json
    root=package(cid)/'iocs'
    before={filename:(root/filename).read_bytes() for filename in ('indicators.csv','indicators.stix.json')}
    actual=indicators.os.replace;failed=False
    def fail_once(source,target):
        nonlocal failed
        if str(target).endswith('indicators.stix.json') and not failed:
            failed=True;raise OSError('Simulated publication failure')
        return actual(source,target)
    monkeypatch.setattr(indicators.os,'replace',fail_once)
    app.config['TESTING']=True
    with pytest.raises(OSError,match='Simulated publication failure'):
        post(base,revision=original['revision'],rows=json.dumps([['domain','new.example','']]))
    for filename,content in before.items():assert (root/filename).read_bytes()==content
    assert client.get(base).json['rows']==original['rows']
    assert not (root.parent.parent/'.indicator-output-recovery').exists()


def test_startup_recovery_uses_committed_table_state():
    from indicators import journal_outputs,publish_outputs,recover_output
    from indicator_stix import reconcile_rows
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    old=post(base,revision=0,rows=json.dumps([['domain','old.example','']])).json
    root=package(cid)/'iocs';before=(root/'indicators.stix.json').read_bytes()
    intended=copy.deepcopy(old);intended['sections'][0]['rows'][0][1]='new.example'
    reconcile_rows(intended['sections'],old['sections']);intended['rows']=[row for section in intended['sections'] for row in section['rows']]
    journal_outputs(root,intended);publish_outputs(root,intended)
    assert (root/'indicators.stix.json').read_bytes()!=before
    recover_output(root,old)
    assert (root/'indicators.stix.json').read_bytes()==before
    journal_outputs(root,intended);publish_outputs(root,intended);recover_output(root,intended)
    assert (root/'indicators.stix.json').read_bytes()!=before
    assert not (root.parent.parent/'.indicator-output-recovery').exists()


def test_empty_table_and_literal_filename_are_explicit():
    from indicator_stix import reconcile_rows,build_bundle
    sections=reconcile_rows([dict(id='default',title='Empty',description='',rows=[])],[])
    raw,report=build_bundle(sections)
    assert report['available'] and report['count']==0
    rows,skipped=import_document(raw.encode());assert rows==[] and skipped==[]
    assert analyze(['filename',' hxxps[.]literal.exe ',''])['key'][1]==[' hxxps[.]literal.exe ']
    assert analyze(['url','HTTPS://EXAMPLE.COM/a',''])['key'][1]==['https://example.com/a']



def test_import_time_budget_and_network_isolation(monkeypatch):
    import socket
    import indicator_stix
    raw=stix_file("[domain-name:value = 'a.example']")
    def forbidden(*args,**kwargs):raise AssertionError('External network access is forbidden')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    assert import_document(raw)[0][0][0]=='domain'
    ticks=iter([0,6])
    monkeypatch.setattr(indicator_stix.time,'monotonic',lambda:next(ticks))
    with pytest.raises(ValueError,match='processing limit'):import_document(raw)


def test_api_save_uses_shared_catalog_and_stale_asset_guard():
    from test_api import make_user,new_case,start_case
    uid,headers=make_user('stix-api-admin');client=app.test_client();cid=new_case(client,headers);start_case(client,headers,cid,uid)
    route=f'/api/v1/cases/{cid}/indicators'
    result=client.put(route,headers=headers,json={'revision':0,'rows':[['SHA-1','a'*40,'Evidence']]})
    assert result.status_code==200 and result.json['rows'][0][0]=='sha1' and result.json['stix']['available']
    stale=package(cid)/'iocs/indicators.stix.json';stale.write_text('{}')
    assert client.get(f'/api/v1/cases/{cid}/assets/iocs/indicators.stix.json',headers=headers).status_code==409
    other,limited=make_user('stix-api-user',role='stix-reader')
    with app.app_context():
        db().execute("INSERT INTO roles VALUES('stix-reader','',0)");db().execute("INSERT INTO role_permissions VALUES('stix-reader','indicators:read')");db().commit()
    assert client.get(route,headers=limited).status_code==200
    assert client.put(route,headers=limited,json={'revision':1,'rows':[]}).status_code==403


def test_section_context_changes_only_grouping_modified_time():
    client,cid,post=setup();route=f'/cases/{cid}/indicators'
    initial=post(route,revision=0,rows=json.dumps([['domain','example.com','Original']])).json
    row=copy.deepcopy(initial['sections'][0]['row_meta'][0]);group=copy.deepcopy(initial['sections'][0]['stix_meta'])
    sections=initial['sections'];sections[0]['title']='Changed section title'
    changed=post(route,revision=initial['revision'],sections=json.dumps(sections)).json
    assert changed['sections'][0]['row_meta'][0]==row
    assert changed['sections'][0]['stix_meta']['id']==group['id']
    assert changed['sections'][0]['stix_meta']['created']==group['created']
    assert changed['sections'][0]['stix_meta']['modified']>group['modified']


def test_standard_and_raw_include_current_csv_and_stix():
    import zipfile
    from app import build_archive
    client,cid,post=setup();route=f'/cases/{cid}/indicators'
    saved=post(route,revision=0,rows=json.dumps([['domain','example.com','']])).json
    (package(cid)/'iocs/indicators.stix.json').write_text('stale')
    with app.app_context():
        for kind in ('standard','raw'):
            output,name=build_archive(cid,kind)
            with output,zipfile.ZipFile(output) as archive:
                assert name+'/iocs/indicators.csv' in archive.namelist()
                content=archive.read(name+'/iocs/indicators.stix.json')
                bundle=parse(content,version='2.1')
                assert next(obj for obj in bundle.objects if obj.type=='indicator').id==saved['sections'][0]['row_meta'][0]['id']


@pytest.mark.parametrize('alias,kind', [('application','software'),('Software name','software'),('Android','mobile-application-id'),('package-name','mobile-application-id'),('application-id','mobile-application-id'),('bundle identifier','mobile-application-id')])
def test_software_aliases(alias,kind):
    assert analyze([alias,VALUES[kind],''])['row'][0]==kind


def test_software_context_and_roundtrip():
    from stix2.v21 import Software
    from indicator_stix import reconcile_rows,build_bundle
    sections=reconcile_rows([dict(id='default',title='Software',description='',rows=[['software','com.example.app','Generic name'],['mobile-application-id','com.example.app','Package']])],[])
    raw,_=build_bundle(sections)
    rows,skipped=import_document(raw.encode())
    assert rows==sections[0]['rows']
    assert all(item['type']=='grouping' for item in skipped)
    assert from_pattern("[software:name = 'com.example.app']")[0]=='software'
    assert import_document(Software(name='com.example.app').serialize().encode())[0]==[['software','com.example.app','']]
    android=Software(name='com.example.app',x_mare_indicator_type='mobile-application-id',allow_custom=True)
    assert import_document(android.serialize().encode())[0]==[['mobile-application-id','com.example.app','']]
    assert analyze(['mobile-application-id','com.example.app',''])['key'][1]==['com.example.app']
    assert analyze(['mobile-application-id','com[.]example[.]app',''])['key'][1]==['com[.]example[.]app']


@pytest.mark.parametrize('kind,value,expected',[
    ('domain','evil[.]example[.]com','evil.example.com'),
    ('hostname','host[.]example','host.example'),
    ('ip-dst','192[.]0[.]2[.]1','192.0.2.1'),
    ('ip-src','2001[:]db8[:][:]1','2001:db8::1'),
    ('url','hxxps://evil[.]example[.]com/CaseSensitive','https://evil.example.com/CaseSensitive'),
    ('url','https[:]//evil[.]example[.]com/a','https://evil.example.com/a'),
    ('url','hxxps[:]//192[.]0[.]2[.]1/Case','https://192.0.2.1/Case'),
    ('url','https://[2001:db8::1]/Case','https://[2001:db8::1]/Case'),
    ('email-src','analyst[@]evil[.]example','analyst@evil.example'),
    ('email-dst','Analyst[@]evil[.]example','Analyst@evil.example'),
])
def test_network_csv_and_stix_share_pipeline(kind,value,expected):
    from indicator_types import csv_row
    row=[kind,value,'Literal https://description.example, analyst@example.com']
    original=copy.deepcopy(row)
    checked=analyze(row);assert checked.get('pattern'),checked
    assert checked['key'][1][-1]==expected
    exported=csv_row(row)
    assert exported[1]!=expected
    assert analyze(exported)['key']==checked['key']
    assert exported[2]==row[2] and row==original
    assert analyze(from_pattern(checked['pattern'],'',kind))['key']==checked['key']


@pytest.mark.parametrize('kind', ['software','mobile-application-id','filename','mutex','regkey','regkey|value','filename|sha256','sha256'])
def test_csv_leaves_non_network_values_and_other_cells_untouched(kind):
    from indicator_types import csv_row
    value=VALUES[kind]
    if kind=='filename':value="com.example's\\sample.exe"
    row=[kind,value,'Keep evil.example and https://example.com exactly']
    assert csv_row(row)==row
    assert not analyze(row).get('error')


def test_network_serializers_across_save_download_and_packages():
    import zipfile
    from app import build_archive
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    rows=[['url','hxxps[:]//evil[.]example/Case','Description'],['mobile-application-id','com.example.app','Package']]
    saved=post(base,revision=0,rows=json.dumps(rows)).json
    assert saved['rows']==rows
    ids=copy.deepcopy(saved['sections'][0]['row_meta'])
    assert 'com.example.app' in (package(cid)/'iocs/indicators.csv').read_text()
    assert 'hxxps[:]' in (package(cid)/'iocs/indicators.csv').read_text()
    for autosave in ('0','1'):
        unchanged=post(base,revision=saved['revision'],sections=json.dumps(saved['sections']),automatic=autosave).json
        assert unchanged['revision']==saved['revision'] and unchanged['sections'][0]['row_meta']==ids
    downloaded=client.get(base+'/stix');assert downloaded.status_code==200
    indicators=[obj for obj in json.loads(downloaded.data)['objects'] if obj['type']=='indicator']
    assert indicators[0]['pattern']=="[url:value = 'https://evil.example/Case']"
    contextual=[obj for obj in json.loads(downloaded.data)['objects'] if obj['type']=='x-misp-attribute']
    assert contextual[0]['x_misp_type']=='mobile-application-id' and contextual[0]['x_misp_value']=='com.example.app'
    for kind in ('standard','raw'):
        with app.app_context(): archive,name=build_archive(cid,kind)
        with archive,zipfile.ZipFile(archive) as zipped:
            names=zipped.namelist()
            stix=next(name for name in names if name.endswith('iocs/indicators.stix.json'))
            assert json.loads(zipped.read(stix))==json.loads(downloaded.data)


def test_official_misp_software_conversion_when_available(tmp_path):
    import os,subprocess
    from indicator_stix import reconcile_rows,build_bundle
    python=os.environ.get('MARE_MISP_PYTHON')
    if not python:pytest.skip('Set MARE_MISP_PYTHON to an isolated official misp-stix environment')
    sections=reconcile_rows([dict(id='default',title='Software',description='',rows=[['software','Example App','']])],[])
    raw,_=build_bundle(sections);path=tmp_path/'software.json';path.write_text(raw)
    result=json.loads(subprocess.run([python,'tests/verify_indicator_misp.py',str(path),'--external'],capture_output=True,text=True,check=True).stdout)
    assert not result['errors'] and not result['warnings']
    assert [obj['name'] for obj in result['objects']]==['software']
    assert [obj['Attribute'][0]['value'] for obj in result['objects']]==['Example App']


def test_software_csv_aliases_and_import_regeneration():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    imported=post(base+'/import',revision=0,csv='type,value,description\napplication,Example App,Name\npackage-name,com.example.app,Package\n')
    assert imported.status_code==200
    assert imported.json['rows']==[['software','Example App','Name'],['mobile-application-id','com.example.app','Package']]
    csv=(package(cid)/'iocs/indicators.csv').read_text()
    assert 'com.example.app' in csv and 'com[.]example' not in csv
    raw=(package(cid)/'iocs/indicators.stix.json').read_bytes()
    rows,skipped=import_document(raw)
    assert rows==imported.json['rows']
    assert all(item['type']=='grouping' for item in skipped)


def test_structured_software_and_android_context_require_review():
    from stix2.v21 import Software
    rows,skipped=import_document(Software(name='Example',version='1.0').serialize().encode())
    assert not rows and 'Structured software' in skipped[0]['reason']
    obj=json.loads(stix_file("[software:name = 'com.example.app']"))
    obj['labels']=['misp:name="android-app"']
    assert import_document(json.dumps(obj).encode())[0]==[['mobile-application-id','com.example.app','Original description']]
