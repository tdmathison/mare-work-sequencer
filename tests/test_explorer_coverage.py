import io
import json
import uuid
import pytest
from app import app, db, ensure_package, ROOT
from explorer_coverage import meaningful_markdown
from mip import OPTIONAL_TEMPLATES, REPORT_TEMPLATE
from test_threat_actors import setup, create as actor_create, upload as actor_upload
from test_malware_families import create as family_create
from test_data_explorer import save_contents
from tagging import create as tag


def fetch(client, scope='all', **params):
    response = client.get('/data-explorer/coverage', query_string={'scope':scope, **params})
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'private, no-store'
    return response.json


@pytest.mark.parametrize('value', ['', '  \n', '# Executive Summary\n', 'Executive Summary', '<!-- analyst prompt -->', '[Add the key findings and stakeholder impact.]', REPORT_TEMPLATE, *OPTIONAL_TEMPLATES.values(), '## Heading\n\nTODO', '| ID | Technique |\n|---|---|'])
def test_default_scaffolds_are_not_content(value):
    assert not meaningful_markdown(value)


@pytest.mark.parametrize('value', ['No malicious network behavior was observed.', '## Findings\nThe sample decrypts its configuration.', '| T1059 | Command execution | Observed process |', '![Evidence](assets/screen.png)', '```\nCreateProcessW(payload)\n```'])
def test_saved_analysis_is_meaningful(value):
    assert meaningful_markdown(value)


def test_empty_separate_catalogs_report_and_standard_package():
    c, uid, cid, _ = setup()
    row = fetch(c)['rows'][0]
    assert {row[k]['state'] for k in ('indicators', 'attack', 'mbc', 'report', 'package')} == {'missing'}
    assert row['missing'] == 4
    root = ROOT / 'cases' / str(cid) / 'mip'
    (root / 'mappings' / 'mitre-attack.md').write_text(OPTIONAL_TEMPLATES['mappings/mitre-attack.md'])
    (root / 'reports' / 'sections').mkdir(exist_ok=True)
    (root / 'reports' / 'sections' / 'executive_summary.md').write_text('# Executive Summary\n\n[Add a summary.]')
    assert fetch(c)['rows'][0]['report']['state'] == 'missing'
    (root / 'mappings' / 'mitre-mbc.md').write_text('# MBC\n\n| Behavior ID | Behavior | Evidence |\n|---|---|---|\n| B0001 | Sample behavior | Observed |')
    (root / 'reports' / 'sections' / 'key_findings.md').write_text('The sample persists using a scheduled task.')
    row = fetch(c)['rows'][0]
    assert row['attack']['state'] == 'missing' and row['mbc']['state'] == 'present'
    assert 'count' not in row['mbc'] and row['report']['state'] == 'present'
    assert row['package']['state'] == 'present' and row['package']['count'] == 1
    assert row['missing'] == 2
    assert row['mbc']['url'].endswith('?tab=report')
    # Report source, current report, samples, backups and symlinks do not qualify.
    (root / 'mappings' / 'mitre-mbc.md').unlink()
    (root / 'reports' / 'malware-analysis-report.docx').write_bytes(b'current report')
    (root / 'samples' / 'sample.zip').write_bytes(b'sample')
    (root / 'scripts' / 'backups').mkdir()
    (root / 'scripts' / 'backups' / 'old.py').write_text('old')
    (root / 'scripts' / 'link').symlink_to(root / 'reports' / 'malware-analysis-report.docx')
    assert fetch(c)['rows'][0]['package']['state'] == 'missing'
    (root / 'scripts' / 'real.py').write_text('print(1)')
    assert fetch(c)['rows'][0]['package']['state'] == 'present'


def test_indicator_validation_sections_and_current_saved_data():
    c, uid, cid, _ = setup()
    sections = [dict(id='default', title='First', description='', rows=[['md5','a'*32,''], ['md5','bad',''], ['filename','payload.exe',''], ['domain',' ','']]), dict(id='two', title='Second', description='', rows=[['domain','example.test',''], ['', '', 'description only']])]
    with app.app_context():
        db().execute('INSERT INTO indicator_sections(case_id,sections) VALUES(?,?)', (cid, json.dumps(sections)));db().commit()
    row = fetch(c)['rows'][0]
    assert row['indicators']['state'] == 'present' and row['indicators']['count'] == 3
    sections[0]['rows'] = [];sections[1]['rows'] = []
    with app.app_context():
        db().execute('UPDATE indicator_sections SET sections=? WHERE case_id=?', (json.dumps(sections), cid));db().commit()
    assert fetch(c)['rows'][0]['indicators']['state'] == 'missing'
    # Oversized/malformed saved content is unavailable rather than fabricated missing.
    with app.app_context():
        db().execute("UPDATE indicator_sections SET sections='not json' WHERE case_id=?", (cid,));db().commit()
    row = fetch(c)['rows'][0]
    assert row['indicators']['state'] == 'unavailable' and row['package']['state'] == 'unavailable'
    assert row['missing'] == 2


def test_scopes_filters_sorting_pagination_and_authorized_case_inventory():
    c, uid, cid, _ = setup()
    with app.app_context():
        for i in range(55):
            db().execute('INSERT INTO cases(number,name,stage,created) VALUES(?,?,3,?)', (f'CASE-{i:03}', 'Needle' if i == 54 else 'Other case', '2026'))
        db().commit()
    data = fetch(c)
    assert data['scope_total'] == 56 and data['total'] == 56 and len(data['rows']) == 50 and data['pages'] == 2
    assert len(fetch(c, page=1)['rows']) == 6
    data = fetch(c, scope='graph', ids=json.dumps([f'case:{cid}', 'case:999999']))
    assert data['total'] == 1 and data['rows'][0]['id'] == f'case:{cid}'
    assert fetch(c, scope='graph')['total'] == 0
    assert fetch(c, q='needle')['total'] == 1
    root = ROOT / 'cases' / str(cid) / 'mip'
    (root/'scripts'/'real.py').write_text('print(1)')
    ordered = fetch(c, sort='missing')['rows']
    assert ordered[0]['missing'] == 4 and fetch(c, q='MARE-FAMILY')['rows'][0]['missing'] == 3
    assert fetch(c, missing='1')['total'] == 56
    with app.app_context():
        db().execute('DELETE FROM case_tags WHERE case_id=?', (cid,))
        db().execute('DELETE FROM cases WHERE id=?', (cid,));db().commit()
    assert fetch(c, scope='graph', ids=json.dumps([f'case:{cid}']))['total'] == 0
    assert c.get('/data-explorer/coverage?sort=bad').status_code == 400
    assert c.get('/data-explorer/coverage?ids={broken').status_code == 400
    assert app.test_client().get('/data-explorer/coverage').status_code == 302


def test_gap_dedup_prefill_references_and_scope():
    c, uid, cid, tid = setup()
    family = family_create(c)
    actor = actor_create(c)
    with app.app_context():
        missing = tag(db(), 'MAL_NO_PROFILE')[0]
        for i in range(2):
            other = db().execute('INSERT INTO cases(number,name,stage,created) VALUES(?,?,1,?)', (f'OTHER-{i}', 'Second case', '2026')).lastrowid
            db().execute('INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)', (other, missing, '2026'))
        db().commit()
    gaps = fetch(c)['gaps']
    missing_gap = next(g for g in gaps if g['name'] == 'MAL_NO_PROFILE')
    assert missing_gap['case_count'] == 2 and len(missing_gap['supports']) == 2
    assert sum(g['name'] == 'MAL_NO_PROFILE' for g in gaps) == 1
    assert missing_gap['action']['url'] == f'/malware-families/new?tag_id={missing}'
    html = c.get(missing_gap['action']['url']).text
    assert 'MAL_NO_PROFILE' in html and 'source_tag_identity' in html
    assert len([g for g in gaps if 'without references' in g['suggestion']]) == 2
    current = fetch(c, scope='graph', ids=json.dumps([f'case:{cid}', f'family:{family}']))
    assert {g['name'] for g in current['gaps']} == {'Existing family'}
    # A profile represented in the graph may be reviewed even with no scoped case.
    assert fetch(c, scope='graph', ids=json.dumps([f'actor:{actor}']))['gap_total'] == 1
    with app.app_context():
        db().execute('INSERT INTO family_osint VALUES(?,?,?,?,?)', (str(uuid.uuid4()), family, 'Research', 'https://example.test', 0));db().commit()
    assert not any(g['name'] == 'Existing family' for g in fetch(c)['gaps'])
    actor_upload(c, actor)
    assert not any('without references' in g['suggestion'] for g in fetch(c)['gaps'])
    with app.app_context():
        db().execute('INSERT INTO actor_osint VALUES(?,?,?,?,?)', (str(uuid.uuid4()), actor, 'Research', 'https://example.test', 0));db().commit()
    assert not any('without references' in g['suggestion'] for g in fetch(c)['gaps'])
    # Removing a profile preserves its tag: a distinct actor missing-profile suggestion.
    with app.app_context():
        db().execute('DELETE FROM threat_actors WHERE id=?', (actor,));db().commit()
    assert any(g['action']['url'].startswith('/threat-actors/new?tag_id=') for g in fetch(c)['gaps'])


def test_permissions_do_not_leak_counts_content_or_actions():
    c, uid, cid, _ = setup()
    family = family_create(c)
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('Coverage reader')")
        db().execute("INSERT INTO role_permissions VALUES('Coverage reader','cases:read')")
        db().execute("UPDATE users SET role='Coverage reader' WHERE id=?", (uid,));db().commit()
    data = fetch(c)
    assert data['gap_total'] == 0
    row = data['rows'][0]
    assert row['missing'] == 0
    assert all(row[k]['state'] == 'unavailable' and 'url' not in row[k] for k in ('indicators','attack','mbc','report','package'))
    with app.app_context():
        db().execute("INSERT INTO role_permissions VALUES('Coverage reader','tags:read')");db().commit()
    data = fetch(c)
    assert any(g['action'] is None for g in data['gaps'] if 'without a profile' in g['suggestion'])
    assert any(g['action']['label'] == 'Review profile' for g in data['gaps'] if g['name'] == 'Existing family')
    with app.app_context():
        db().execute("DELETE FROM role_permissions WHERE role_name='Coverage reader' AND permission='cases:read'");db().commit()
    assert fetch(c)['scope_total'] == 0 and fetch(c)['gap_total'] == 0
    graph = fetch(c, scope='graph', ids=json.dumps([f'case:{cid}',f'family:{family}']))
    assert graph['total'] == 0 and graph['gap_total'] == 1 and graph['gaps'][0]['supports'] == []
    with app.app_context():
        db().execute("DELETE FROM role_permissions WHERE role_name='Coverage reader'");db().commit()
    assert c.get('/data-explorer/coverage').status_code == 403


def test_package_matches_existing_standard_selection_and_read_only(monkeypatch):
    c, uid, cid, _ = setup();root = save_contents(c, cid)
    with app.app_context():
        before = db().total_changes
        snapshot = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    monkeypatch.setattr('app.ensure_package', lambda *a: pytest.fail('Coverage must not scaffold'))
    row = fetch(c)['rows'][0]
    assert row['package']['state'] == 'present' and row['package']['count'] == 7
    with app.app_context():
        assert db().total_changes == before
    assert snapshot == {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def test_explicit_applicability_is_not_inferred_and_does_not_hide_content():
    c, uid, cid, _ = setup()
    with app.app_context():
        db().execute("INSERT INTO readiness VALUES(?,'iocs','Not applicable','')", (cid,))
        db().execute("INSERT INTO readiness VALUES(?,'mappings','Not applicable','')", (cid,));db().commit()
    row = fetch(c)['rows'][0]
    assert all(row[k]['state'] == 'not-applicable' for k in ('indicators','attack','mbc'))
    assert row['missing'] == 2 and row['report']['state'] == 'missing' and row['package']['state'] == 'missing'
    root = ROOT/'cases'/str(cid)/'mip'
    (root/'mappings'/'mitre-attack.md').write_text('Observed T1059 command execution.')
    row = fetch(c)['rows'][0]
    assert row['attack']['state'] == 'present' and row['mbc']['state'] == 'not-applicable'
    assert row['missing'] == 1


def test_complete_content_missing_filter_and_partial_inventory(monkeypatch):
    c, uid, cid, _ = setup()
    save_contents(c, cid)
    root = ROOT/'cases'/str(cid)/'mip'
    (root/'reports'/'sections'/'executive_summary.md').write_text('Sample analysis identifies an information stealer.')
    (root/'mappings'/'mitre-attack.md').write_text('Observed T1059 command execution.')
    (root/'mappings'/'mitre-mbc.md').write_text('Observed execution behavior.')
    assert fetch(c)['rows'][0]['missing'] == 0
    assert fetch(c, missing='1')['total'] == 0
    with app.app_context():
        db().execute("INSERT INTO cases(number,name,stage,created) VALUES('ZZ-LATER','Later',1,'2026')");db().commit()
    monkeypatch.setattr('explorer_coverage.MAX_CASES', 1)
    data = fetch(c)
    assert data['limited'] and data['scope_total'] == 2 and data['total'] == 1
    assert '1 of 2 cases' in data['note']
