"""Actual official-converter round trips for the complete non-binary catalog."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime

import pytest
from app import app,package
from indicator_types import analyze,BY_NAME,MISP_SOURCE,OFFICIAL_NATIVE
from indicator_stix import build_bundle,import_document,reconcile_rows
from test_indicators import setup

ROWS=json.loads(Path('tests/fixtures/misp_indicator_attributes.json').read_text())['rows']


def converted(tmp_path,raw):
    path=tmp_path/'bundle.stix';path.write_text(raw)
    result=json.loads(subprocess.run([sys.executable,'tests/verify_indicator_misp.py',str(path)],check=True,capture_output=True,text=True).stdout)
    assert not result['errors'] and not result['warnings']
    return result


def expected_value(row):
    result=analyze(row)
    values=result['key'][1]
    return values[-1] if row[0].startswith('ip-') and result['export']=='native' else '|'.join(values)


def test_all_192_nonbinary_types_roundtrip_without_missing_attributes(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket,'connect',lambda *args,**kwargs:pytest.fail('Converter attempted a network request'))
    assert {row[0] for row in ROWS}==set(MISP_SOURCE['types'])-{'attachment','malware-sample'}
    assert len(ROWS)==192
    assert all(not analyze(row).get('error') for row in ROWS)
    sections=reconcile_rows([dict(id='default',title='Primary section',description='Primary context',rows=copy.deepcopy(ROWS[:96])),dict(id='other',title='Other section',description='Other context',rows=copy.deepcopy(ROWS[96:]))],[])
    raw,report=build_bundle(sections)
    assert report['available'] and not report['issues']
    assert build_bundle(sections)[0]==raw
    assert reconcile_rows(copy.deepcopy(sections),sections)==sections
    objects=json.loads(raw)['objects']
    assert len([item for item in objects if item['type']!='grouping'])==192
    assert set(item['type'] for item in objects)<={'indicator','x-misp-attribute','grouping'}
    result=converted(tmp_path,raw)
    assert result['events']==['Primary section','Other section']
    assert len(result['attributes'])==192 and not result['objects']
    attributes={item['type']:item for item in result['attributes']}
    identities={row[0]:meta['id'].split('--')[1] for section in sections for row,meta in zip(section['rows'],section['row_meta'])}
    assert set(attributes)=={row[0] for row in ROWS}
    for row in ROWS:
        attribute=attributes[row[0]];expected=expected_value(row)
        if row[0]=='datetime':
            # PyMISP serializes UTC as +00:00 instead of Z (same instant).
            assert datetime.fromisoformat(attribute['value'])==datetime.fromisoformat(expected.replace('Z','+00:00'))
        else:assert attribute['value']==expected,row[0]
        assert attribute['uuid']==identities[row[0]]
        assert attribute['comment']==row[2]
        assert attribute['to_ids']==analyze(row)['to_ids']
    restored,skipped=import_document(raw.encode())
    assert len(restored)==192 and all(item['type']=='grouping' for item in skipped)


def test_all_68_official_native_patterns_preserve_type_value_description_and_intent(tmp_path):
    rows=[copy.deepcopy(row) for row in ROWS if row[0] in OFFICIAL_NATIVE]
    assert len(rows)==68
    sections=reconcile_rows([dict(id='default',title='Native mappings',description='',rows=rows,row_meta=[{'to_ids':True} for row in rows])],[])
    raw,report=build_bundle(sections)
    assert report['available'],report
    result=converted(tmp_path,raw);attributes={item['type']:item for item in result['attributes']}
    assert len(attributes)==68
    for row in rows:
        assert attributes[row[0]]['value']==expected_value(row),row[0]
        assert attributes[row[0]]['comment']==row[2]
        assert attributes[row[0]]['to_ids'] is True
    imported,skipped,origins,intents=import_document(raw.encode(),with_intent=True)
    assert len(imported)==68 and intents==[True]*68
    assert all(item['type']=='grouping' for item in skipped)
    for row,source in zip(imported,rows):assert analyze(row)['key']==analyze(source)['key']


def test_previously_blocked_rows_save_autosave_download_and_package(tmp_path):
    from app import build_archive
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    kinds={'text','comment','other','mobile-application-id','port','ip-src|port','yara','pdb','email-body','uri'}
    rows=[copy.deepcopy(row) for row in ROWS if row[0] in kinds]
    saved=post(base,revision=0,rows=json.dumps(rows))
    assert saved.status_code==200 and saved.json['stix']['available']
    assert not saved.json['stix']['issues']
    assert len(saved.json['stix']['notices'])==len(rows)
    raw=client.get(base+'/stix').data
    assert len(converted(tmp_path,raw.decode())['attributes'])==len(rows)
    same=post(base,revision=saved.json['revision'],sections=json.dumps(saved.json['sections']),automatic='1').json
    assert same['revision']==saved.json['revision'] and same['sections']==saved.json['sections']
    for kind in ('standard','raw'):
        with app.app_context():output,name=build_archive(cid,kind)
        with output,zipfile.ZipFile(output) as archive:
            assert archive.read(name+'/iocs/indicators.stix.json')==raw
            csv=archive.read(name+'/iocs/indicators.csv').decode()
            assert 'https[:]//' not in csv  # URL scheme remains defanged hxxps
            assert 'com.Example.app' in csv
            assert 'https://example.com' in csv  # contextual prose was not defanged


@pytest.mark.parametrize('row',[
    ['port','70000',''],['port','not-a-number',''],['ip-src|port','192.0.2.1|70000',''],
    ['sha224','a'*55,''],['ssdeep','not-a-fuzzy-hash',''],['datetime','not-a-date',''],
    ['attachment','sample.bin',''],['malware-sample','sample.exe|'+'a'*32,''],
])
def test_genuinely_invalid_or_binary_missing_values_keep_draft_but_remove_stale_output(row):
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    good=post(base,revision=0,rows=json.dumps([['domain','evil.example','']])).json
    saved=post(base,revision=good['revision'],rows=json.dumps([row]))
    assert saved.status_code==200 and saved.json['rows']==[row]
    assert not saved.json['stix']['available'] and saved.json['stix']['issues'][0]['reason']
    assert not (package(cid)/'iocs/indicators.stix.json').exists()
    assert client.get(base+'/stix').status_code==409
    assert (package(cid)/'iocs/indicators.csv').exists()


def test_detection_intent_is_preserved_and_contextual_rows_default_false(tmp_path):
    rows=[['sha224','a'*56,'New native, initially non-detection'],['domain','evil[.]example','Existing native, explicitly non-detection'],['text','Actual analyst text','Non-detection']]
    sections=reconcile_rows([dict(id='default',title='Intent',description='',rows=rows,row_meta=[{'to_ids':True},{'to_ids':False},None])],[])
    raw,report=build_bundle(sections);assert report['available']
    attributes={item['type']:item for item in converted(tmp_path,raw)['attributes']}
    assert attributes['sha224']['to_ids'] is True
    assert attributes['domain']['to_ids'] is False and attributes['text']['to_ids'] is False
    objects=json.loads(raw)['objects']
    assert len([item for item in objects if item['type']=='indicator'])==1
    restored,skipped,originals,intents=import_document(raw.encode(),with_intent=True)
    assert intents==[True,False,False]
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    result=post(base+'/import',revision=0,section_id='default',accepted_rows=json.dumps(restored),accepted_intents=json.dumps(intents)).json
    assert [meta['to_ids'] for meta in result['sections'][0]['row_meta']]==intents
    initial=result['sections'];same=post(base,revision=result['revision'],sections=json.dumps(initial)).json
    assert same['revision']==result['revision'] and same['sections']==initial


def test_converter_failure_is_explicit_and_never_publishes_a_partial_bundle(monkeypatch):
    import indicator_stix
    client,cid,post=setup();base=f'/cases/{cid}/indicators'
    saved=post(base,revision=0,rows=json.dumps([['text','Valid text','']])).json
    def fail(*args,**kwargs):raise ValueError('Pinned converter contract changed: review required.')
    monkeypatch.setattr(indicator_stix,'convert_attribute',fail)
    response=post(base,revision=saved['revision'],rows=json.dumps([['text','Still saved','']]))
    assert response.status_code==200 and response.json['rows'][0][1]=='Still saved'
    assert not response.json['stix']['available']
    assert 'contract changed' in response.json['stix']['issues'][0]['reason']
    assert not (package(cid)/'iocs/indicators.stix.json').exists()


def test_native_literal_escaping_and_cidr_networks(tmp_path):
    rows=[['filename|imphash'," sample's\\path.exe|"+'a'*32,'Description'],['ip-src','192[.]0[.]2[.]0/24','CIDR']]
    sections=reconcile_rows([dict(id='default',title='Literals',description='',rows=rows,row_meta=[{'to_ids':True},{'to_ids':True}])],[])
    raw,report=build_bundle(sections);assert report['available'],report
    assert import_document(raw.encode())[0]==[analyze(row)['row'] if row[0]=='filename|imphash' else ['ip-src','192.0.2.0/24','CIDR'] for row in rows]
    result=converted(tmp_path,raw);attributes={item['type']:item for item in result['attributes']}
    assert attributes['filename|imphash']['value']==rows[0][1].strip()  # documented PyMISP boundary trimming
    assert attributes['ip-src']['value']=='192.0.2.0/24'


def test_capability_upgrade_does_not_revise_unchanged_source_metadata():
    sections=reconcile_rows([dict(id='default',title='Existing table',description='',rows=[['port','443','']])],[])
    # Model a digest computed by the previous, storage-only capability profile.
    sections[0]['stix_meta']['digest']='0'*64
    import hashlib
    for row,meta in zip(sections[0]['rows'],sections[0]['row_meta']):
        meta.pop('to_ids',None)
        meta['digest']=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    assert reconcile_rows(copy.deepcopy(sections),sections)==sections
    assert build_bundle(sections)[1]['available']


def test_native_descriptive_objects_do_not_change_default_detection_intent(tmp_path):
    rows=[['campaign-name','Example campaign','Campaign description'],['vulnerability','CVE-2024-1234','Vulnerability description']]
    for intent in (False,True):
        sections=reconcile_rows([dict(id='default',title='Descriptors',description='',rows=copy.deepcopy(rows),row_meta=[{'to_ids':intent} for row in rows])],[])
        raw,report=build_bundle(sections);assert report['available']
        objects=[item for item in json.loads(raw)['objects'] if item['type']!='grouping']
        assert [item['type'] for item in objects]==(['campaign','vulnerability'] if intent else ['x-misp-attribute']*2)
        attributes=converted(tmp_path,raw)['attributes']
        assert len(attributes)==2 and all(attribute['to_ids'] is intent for attribute in attributes)
        assert [attribute['comment'] for attribute in attributes]==[row[2] for row in rows]
        assert import_document(raw.encode(),with_intent=True)[3]==[intent,intent]


def test_api_exports_complete_catalog_and_preserves_explicit_intent():
    from app import db
    from test_api import make_user,new_case,start_case
    uid,headers=make_user('complete-catalog-api');client=app.test_client();cid=new_case(client,headers);start_case(client,headers,cid,uid)
    route=f'/api/v1/cases/{cid}/indicators'
    saved=client.put(route,headers=headers,json={'revision':0,'rows':copy.deepcopy(ROWS)})
    assert saved.status_code==200 and saved.json['stix']['available']
    asset=client.get(f'/api/v1/cases/{cid}/assets/iocs/indicators.stix.json',headers=headers)
    assert asset.status_code==200
    assert len([item for item in asset.json['objects'] if item['type']!='grouping'])==192
    metadata=saved.json['sections'][0]['row_meta']
    assert all(isinstance(meta['to_ids'],bool) for meta in metadata)
    same=client.put(route,headers=headers,json={'revision':saved.json['revision'],'sections':saved.json['sections']})
    assert same.status_code==200 and same.json['revision']==saved.json['revision']


def test_import_preserves_explicit_false_indicator_intent_and_flags_conflicts():
    from test_indicator_stix import stix_file
    raw=stix_file("[domain-name:value = 'evil.example']",labels=['misp:type="domain"','misp:to_ids="False"'])
    rows,skipped,originals,intents=import_document(raw,with_intent=True)
    assert len(rows)==1 and not skipped and intents==[False]
    obj=json.loads(raw);obj['labels'].append('misp:to_ids="True"')
    rows,skipped=import_document(json.dumps(obj).encode())
    assert not rows and 'Conflicting detection-intent' in skipped[0]['reason']


def test_boundary_whitespace_is_preserved_with_an_informational_compatibility_notice():
    rows=[['text',' \n\t ','Literal whitespace']]
    sections=reconcile_rows([dict(id='default',title='Literal',description='',rows=rows)],[])
    raw,report=build_bundle(sections)
    assert report['available'] and not report['issues']
    assert 'trims boundary whitespace' in report['notices'][0]['message']
    assert json.loads(raw)['objects'][0]['x_misp_value']==rows[0][1]


def test_pinned_converter_profile_and_extended_native_text(tmp_path):
    from importlib.metadata import version
    from indicator_types import CONVERSION_PROFILE
    assert CONVERSION_PROFILE['version']==version('misp-stix')=='2026.10.12'
    assert version('pymisp')=='2.5.34.4'
    rows=[['email-body',"Unicode 🦀\n'quoted' \\ body",'Exact body'],['port','443','Explicit detection flag']]
    sections=reconcile_rows([dict(id='default',title='Extended',description='',rows=rows,row_meta=[{'to_ids':True},{'to_ids':True}])],[])
    raw,report=build_bundle(sections);assert report['available'],report
    attributes={item['type']:item for item in converted(tmp_path,raw)['attributes']}
    for row in rows:
        assert attributes[row[0]]['value']==row[1]
        assert attributes[row[0]]['to_ids'] is True
    assert import_document(raw.encode(),with_intent=True)[3]==[True,True]
    assert not analyze(['filename|impfuzzy','|3:abc:abc','']).get('key')
