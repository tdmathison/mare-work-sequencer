"""Full local catalog storage, explicit fallbacks and contextual STIX compatibility."""
import copy
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path

import pytest
from app import app, db, package
from indicator_types import CATALOG, BY_NAME, MISP_SOURCE, analyze, canonical_type, csv_row
from indicator_stix import build_bundle, import_document, reconcile_rows
from indicators import validate_sections
from test_indicators import setup
from test_backups import setup_backup_case
from test_case_sync import head, preview, apply

LITERAL="  Unicode 🦀\n\t punctuation !@#$% & <xml> 'quotes' \\ path\r\nhttps://evil.example [.] [@]  "


def test_bundled_catalog_is_complete_versioned_and_unique():
    root=Path('vendor/misp');source=json.loads((root/'SOURCE.json').read_text())
    assert source['version']=='2.5.34.4'
    assert hashlib.sha256((root/'describeTypes.json').read_bytes()).hexdigest()==source['sha256']
    assert len(MISP_SOURCE['types'])==194
    assert set(MISP_SOURCE['types']) <= set(BY_NAME)
    assert len(CATALOG)==len(BY_NAME)==195  # one retained MARE software-name extension
    for name in MISP_SOURCE['types']:
        assert canonical_type(name)==name
        assert BY_NAME[name]['export'] in ('native','contextual','unsupported')
        assert BY_NAME[name]['help']
    assert canonical_type('AS')=='AS' and canonical_type('named pipe')=='named pipe'
    assert canonical_type('URI')=='uri'  # exact official name wins over old URL alias
    assert canonical_type('free text')=='text'
    assert canonical_type('unknown') is None and 'unknown' in BY_NAME['text']['search_aliases']
    for alias in ('miscellaneous','catch all'):assert canonical_type(alias)=='other'


def test_every_official_type_can_be_saved_without_fabricating_an_export():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    rows=[[kind,LITERAL,'Exact description'] for kind in MISP_SOURCE['types']]
    saved=post(base,revision=0,rows=json.dumps(rows))
    assert saved.status_code==200 and saved.json['rows']==rows
    assert not saved.json['stix']['available']
    assert not (package(cid)/'iocs/indicators.stix.json').exists()
    assert client.get(base).json['rows']==rows


@pytest.mark.parametrize('kind',['text','comment','other','mobile-application-id','chrome-extension-id','edge-extension-id'])
def test_contextual_export_roundtrip_and_no_op_save(kind):
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    value=LITERAL if kind in ('text','comment','other') else 'com.Example.package'
    row=[kind,value,LITERAL]
    saved=post(base,revision=0,rows=json.dumps([row])).json
    assert saved['rows']==[row] and saved['stix']['available']
    assert csv_row(row)==row
    raw=(package(cid)/'iocs/indicators.stix.json').read_bytes()
    objects=json.loads(raw)['objects'];item=objects[0]
    assert item['type']=='x-misp-attribute' and 'pattern' not in item
    assert item['x_misp_type']==kind and item['x_misp_value']==value and item['x_misp_comment']==LITERAL
    assert item['x_misp_to_ids'] is False
    assert item['id'].split('--')[1]==saved['sections'][0]['row_meta'][0]['id'].split('--')[1]
    assert import_document(raw)[0]==[row]
    for automatic in ('0','1'):
        same=post(base,revision=saved['revision'],sections=json.dumps(saved['sections']),automatic=automatic).json
        assert same['sections']==saved['sections'] and same['revision']==saved['revision']
        assert (package(cid)/'iocs/indicators.stix.json').read_bytes()==raw
    previewed=post(base+'/import/preview',format='stix',section_id='default',stix=(io.BytesIO(raw),'context.stix')).json
    assert previewed['rows'][0]['duplicate']


def test_unknown_fallback_is_explicit_and_provenance_survives_roundtrip():
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    csv='type,value,description\nUnexpectedArtifact,"arbitrary, value",Evidence\n'
    draft=post(base+'/import/preview',format='csv',csv=csv,section_id='default').json
    assert draft['rows'][0]['unknown'] and draft['rows'][0]['row'][0]=='UnexpectedArtifact'
    assert draft['rows'][0]['reason']
    original=draft['rows'][0]['row'][0];converted=['other',draft['rows'][0]['row'][1],draft['rows'][0]['row'][2]]
    saved=post(base+'/import',revision=0,section_id='default',accepted_rows=json.dumps([converted]),accepted_original_types=json.dumps([original])).json
    assert saved['sections'][0]['row_meta'][0]['original_type']==original
    raw=(package(cid)/'iocs/indicators.stix.json').read_bytes()
    reimport=post(base+'/import/preview',format='stix',section_id='default',stix=(io.BytesIO(raw),'context.json')).json
    assert reimport['rows'][0]['original_type']==original and reimport['rows'][0]['duplicate']
    invalid=post(base+'/import',revision=saved['revision'],section_id='default',accepted_rows=json.dumps([converted]),accepted_original_types=json.dumps([123]))
    assert invalid.status_code==400


def test_legacy_android_alias_migrates_on_save_preserving_identity_and_provenance():
    current=reconcile_rows([dict(id='default',title='Apps',description='',rows=[['mobile-application-id','com.Example.app','Description']])],[])
    current[0]['rows'][0][0]='android-package'
    legacy=copy.deepcopy(current[0]['row_meta'][0])
    updated=reconcile_rows(copy.deepcopy(current),current)
    meta=updated[0]['row_meta'][0]
    assert updated[0]['rows'][0]==['mobile-application-id','com.Example.app','Description']
    assert meta['id']==legacy['id'] and meta['created']==legacy['created']
    assert meta['original_type']=='android-package'
    assert reconcile_rows(copy.deepcopy(updated),updated)==updated
    stale_alias=copy.deepcopy(updated);stale_alias[0].pop('row_meta');stale_alias[0]['rows'][0][0]='android-package'
    assert reconcile_rows(stale_alias,updated)==updated
    assert validate_sections(updated)==updated
    raw,_=build_bundle(updated)
    assert import_document(raw.encode(),with_provenance=True)[2]==['android-package']
    # Legacy detection patterns remain importable with explicit package context.
    from test_indicator_stix import stix_file
    raw=stix_file("[software:name = 'com.Example.app']",labels=['mare:type="android-package"'])
    assert import_document(raw,with_provenance=True)[0][0][0]=='mobile-application-id'
    assert import_document(raw,with_provenance=True)[2]==['android-package']


@pytest.mark.parametrize('kind',['attachment','malware-sample','yara','stix2-pattern','ip-src|port'])
def test_missing_binary_or_unverified_mapping_keeps_data_but_blocks_whole_stix(kind):
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    good=post(base,revision=0,rows=json.dumps([['domain','example.com','']])).json
    assert (package(cid)/'iocs/indicators.stix.json').exists()
    saved=post(base,revision=good['revision'],rows=json.dumps([['domain','example.com',''],[kind,'literal sample','Keep']])).json
    assert saved['rows'][1]==[kind,'literal sample','Keep'] and not saved['stix']['available']
    assert saved['stix']['issues'][0]['storage_valid']
    assert 'STIX export' in saved['stix']['issues'][0]['reason']
    assert not (package(cid)/'iocs/indicators.stix.json').exists()
    assert client.get(base+'/stix').status_code==409
    assert 'literal sample' in (package(cid)/'iocs/indicators.csv').read_text()


def test_contextual_rows_and_provenance_survive_raw_sync():
    client,cid,uid,post=setup_backup_case();base=f'/cases/{cid}/indicators'
    rows=[['text',LITERAL,'Notes'],['android-package','com.example.app','Package']]
    saved=post(base,revision=0,rows=json.dumps(rows)).json
    before=head(cid);blob=post(f'/cases/{cid}/backup').data
    operation,plan=preview(client,blob)
    assert plan['items'][0]['preview']['classification']=='unchanged'
    assert apply(client,operation)[0]['action']=='Unchanged'
    assert head(cid)==before and client.get(base).json['sections']==saved['sections']
    from sync_helpers import other_destination
    other_destination()
    imported=post('/import-export/import-raw',backup=(io.BytesIO(blob),'raw.zip'))
    assert imported.status_code==302
    with app.app_context():new_cid=db().execute('SELECT max(id) FROM cases').fetchone()[0]
    assert new_cid!=cid and client.get(f'/cases/{new_cid}/indicators').json['sections']==saved['sections']


def test_api_stores_literal_contextual_and_unmapped_types():
    from test_api import make_user,new_case,start_case
    uid,headers=make_user('catalog-api');client=app.test_client();cid=new_case(client,headers);start_case(client,headers,cid,uid)
    route=f'/api/v1/cases/{cid}/indicators'
    rows=[['text',LITERAL,'Context'],['attachment','file.bin','Binary not supplied']]
    response=client.put(route,headers=headers,json={'revision':0,'rows':rows})
    assert response.status_code==200 and response.json['rows']==rows
    assert not response.json['stix']['available']
    assert client.get(route,headers=headers).json['rows']==rows


def test_official_misp_contextual_conversion_when_available(tmp_path):
    python=os.environ.get('MARE_MISP_PYTHON')
    if not python:pytest.skip('Set MARE_MISP_PYTHON to official converter environment')
    rows=[[kind,LITERAL if kind in ('text','comment','other') else 'com.example.app','Description '+kind] for kind in ('text','comment','other','mobile-application-id','chrome-extension-id','edge-extension-id')]
    sections=reconcile_rows([dict(id='default',title='Context section',description='Context',rows=rows)],[])
    raw,_=build_bundle(sections);path=tmp_path/'context.json';path.write_text(raw)
    result=json.loads(subprocess.run([python,'tests/verify_indicator_misp.py',str(path)],capture_output=True,text=True,check=True).stdout)
    assert not result['errors'] and not result['warnings']
    assert result['events']==['Context section']
    attributes={item['type']:item for item in result['attributes']}
    for kind,value,description in rows:
        assert attributes[kind]['value']==value.strip()  # PyMISP's documented boundary trimming
        assert attributes[kind]['comment']==description and attributes[kind]['to_ids'] is False


def test_catalog_update_reads_only_the_pinned_local_wheel(tmp_path):
    import zipfile
    wheel=tmp_path/'pymisp.whl';root=Path('vendor/misp')
    with zipfile.ZipFile(wheel,'w') as archive:
        archive.writestr('pymisp/data/describeTypes.json',(root/'describeTypes.json').read_bytes())
        archive.writestr('pymisp-2.5.34.4.dist-info/METADATA','Name: pymisp\nVersion: 2.5.34.4\n')
        archive.writestr('pymisp-2.5.34.4.dist-info/licenses/LICENSE',(root/'LICENSE').read_bytes())
    import sys
    output=tmp_path/'output'
    command=[sys.executable,'scripts/update_indicator_catalog.py',str(wheel),'--expected-version','2.5.34.4','--destination',str(output)]
    subprocess.run(command,capture_output=True,text=True,check=True)
    assert (output/'describeTypes.json').read_bytes()==(root/'describeTypes.json').read_bytes()
    assert json.loads((output/'SOURCE.json').read_text())==json.loads((root/'SOURCE.json').read_text())
    command[command.index('2.5.34.4')]='0.0.0'
    before=(output/'SOURCE.json').read_bytes()
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert (output/'SOURCE.json').read_bytes()==before


def test_custom_import_rejects_lost_detection_or_binary_semantics():
    sections=reconcile_rows([dict(id='default',title='Context',description='',rows=[['text','literal','']])],[])
    raw,_=build_bundle(sections);obj=json.loads(raw)['objects'][0]
    for change in ({'x_misp_to_ids':True},{'x_misp_type':'domain'},{'x_misp_data':'ZmFrZQ=='}):
        data={**obj,**change};rows,skipped=import_document(json.dumps(data).encode())
        assert not rows and skipped[0]['reason']
    del obj['created']
    rows,skipped=import_document(json.dumps(obj).encode())
    assert not rows and 'Malformed contextual' in skipped[0]['reason']


@pytest.mark.parametrize('kind,value,expected',[
    ('domain|ip','evil.example|192.0.2.1','evil[.]example|192[.]0[.]2[.]1'),
    ('ip-src|port','192.0.2.1|443','192[.]0[.]2[.]1|443'),
    ('ip-dst|port','2001:db8::1|443','2001[:]db8[:][:]1|443'),
    ('hostname|port','Host.Example|0443','host[.]example|0443'),
    ('email','a@evil.example','a[@]evil[.]example'),
    ('uri','https://evil.example/Path','hxxps[:]//evil[.]example/Path'),
])
def test_additional_network_csv_components_do_not_claim_stix_support(kind,value,expected):
    original=[kind,value,'Literal https://description.example']
    assert csv_row(original)==[kind,expected,original[2]]
    assert original[1]==value
    assert analyze(original)['storage_valid'] and analyze(original).get('error')
