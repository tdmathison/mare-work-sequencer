import copy
import json
import sqlite3
import pytest
from app import app, db, ROOT
from family_aliases import initialize, load_aliases, save_aliases, validate_aliases
from family_portable import export_library, validate_library, restore_library, check_conflicts
from test_malware_families import fixture, create, edit, profile, post


def aliases(fid):
    return load_aliases(profile(fid)['aliases'])


def test_create_edit_search_and_tag_independence():
    client, uid, cid, tid = fixture()
    fid = create(client, aliases=[' RedLine ', 'Multiple Word Name', 'MAL_NOT_A_TAG', '<script>alert(1)</script>'])
    assert aliases(fid) == ['RedLine', 'Multiple Word Name', 'MAL_NOT_A_TAG', '<script>alert(1)</script>']
    with app.app_context():
        assert db().execute('SELECT count(*) FROM tags').fetchone()[0] == 1
        before = [tuple(row) for row in db().execute('SELECT * FROM case_tags')]
        assert db().execute('SELECT count(*) FROM history').fetchone()[0] == 0
    html = client.get('/malware-families/' + fid).text
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert html.index('Existing family</h2>') < html.index('RedLine</span>') < html.index('MAL_EXISTING</span>')
    form = client.get('/malware-families/' + fid + '/edit').text
    assert form.index('Malware family name') < form.index('>Aliases</label>') < form.index('<label>Tag')
    assert 'Remove alias Multiple Word Name' in form
    assert edit(client, fid, aliases=['Multiple Word Name','New alias']).status_code == 302
    assert aliases(fid) == ['Multiple Word Name','New alias']
    assert client.get('/malware-families?q=new+ALIAS').text.count('class="family-choice"') == 1
    assert client.get('/malware-families?q=redline').text.count('class="family-choice"') == 0
    assert edit(client, fid, aliases=[]).status_code == 302
    assert aliases(fid) == []
    with app.app_context():
        assert before == [tuple(row) for row in db().execute('SELECT * FROM case_tags')]
        assert db().execute('SELECT count(*) FROM tags').fetchone()[0] == 1
        assert db().execute('SELECT count(*) FROM history').fetchone()[0] == 0
    assert profile(fid)['tag_id'] == tid


@pytest.mark.parametrize('values', [[''], ['   '], ['RedLine','redline'], ['Straße','STRASSE'], ['a'*201], ['a\nb'], [str(i) for i in range(51)]])
def test_server_rejects_invalid_aliases_and_preserves_inputs(values):
    client, *_ = fixture()
    result = post(client, '/malware-families/new', name='Family', tag='MAL_EXISTING', aliases=values)
    assert result.status_code == 400
    assert 'name="aliases"' in result.text
    with app.app_context():
        assert db().execute('SELECT count(*) FROM malware_families').fetchone()[0] == 0


def test_failed_saves_conflicts_and_drafts_preserve_aliases(monkeypatch):
    client, *_ = fixture()
    fid = create(client, aliases=['Original'])
    version = profile(fid)['version']
    assert edit(client, fid, aliases=['Current']).status_code == 302
    failed = edit(client, fid, version=version, aliases=['Unsaved alternative', 'Second Name'])
    assert failed.status_code == 409
    assert 'value="Unsaved alternative"' in failed.text and 'value="Second Name"' in failed.text
    assert aliases(fid) == ['Current']
    failed = edit(client, fid, name='', aliases=['Draft'], alias_draft='Pending name')
    assert failed.status_code == 400
    assert 'value="Draft"' in failed.text and 'value="Pending name"' in failed.text
    assert edit(client, fid, aliases=['Draft'], alias_draft='Pending name').status_code == 302
    assert aliases(fid) == ['Draft','Pending name']
    import malware_families
    def unavailable(*args):
        raise sqlite3.OperationalError('busy')
    monkeypatch.setattr(malware_families, 'save_aliases', unavailable)
    failed = edit(client, fid, aliases=['Retry later'])
    assert failed.status_code == 503 and 'value="Retry later"' in failed.text
    assert aliases(fid) == ['Draft','Pending name']


def test_empty_profiles_and_legacy_form_posts():
    client, *_ = fixture()
    fid = create(client)
    assert aliases(fid) == []
    assert edit(client, fid, aliases=['Preserved']).status_code == 302
    response = post(client, '/malware-families/'+fid+'/edit', version=profile(fid)['version'], name='Renamed', tag='MAL_EXISTING')
    assert response.status_code == 302 and aliases(fid) == ['Preserved']
    for path in ('/dashboards/malware-families/data', '/dashboards/cases/data'):
        payload = client.get(path).text
        assert 'Preserved' not in payload and 'aliases' not in payload


def test_additive_migration_is_idempotent():
    con = sqlite3.connect(':memory:')
    con.executescript("CREATE TABLE schema_migrations(name TEXT PRIMARY KEY);CREATE TABLE malware_families(id TEXT PRIMARY KEY,name TEXT);INSERT INTO malware_families VALUES('old','Legacy');")
    initialize(con); initialize(con)
    assert con.execute('SELECT aliases FROM malware_families').fetchone()[0] == '[]'
    assert con.execute("SELECT count(*) FROM schema_migrations WHERE name='family-aliases-v1'").fetchone()[0] == 1
    assert con.execute('SELECT name FROM malware_families').fetchone()[0] == 'Legacy'
    con.close()


def test_portable_alias_order_conflicts_and_legacy_absence(tmp_path):
    client, *_ = fixture()
    fid = create(client, aliases=['First name','Second','RedLine'])
    with app.app_context():
        data = export_library(db(), ROOT)
        assert data['families'][0]['aliases'] == ['First name','Second','RedLine']
        validate_library(data, ROOT)
        db().execute('DELETE FROM malware_families WHERE id=?', (fid,)); db().commit()
        restore_library(db(), ROOT, tmp_path, data)
        assert load_aliases(db().execute('SELECT aliases FROM malware_families').fetchone()[0]) == ['First name','Second','RedLine']
        legacy = copy.deepcopy(data)
        del legacy['families'][0]['aliases']
        assert check_conflicts(db(), ROOT, legacy) == {fid}
        restore_library(db(), ROOT, tmp_path, legacy)
        assert load_aliases(db().execute('SELECT aliases FROM malware_families').fetchone()[0]) == ['First name','Second','RedLine']
        explicit = copy.deepcopy(data); explicit['families'][0]['aliases'] = []
        with pytest.raises(ValueError, match='conflict'):
            restore_library(db(), ROOT, tmp_path, explicit)
        assert load_aliases(db().execute('SELECT aliases FROM malware_families').fetchone()[0]) == ['First name','Second','RedLine']
        db().execute('DELETE FROM malware_families WHERE id=?', (fid,)); db().commit()
        restore_library(db(), ROOT, tmp_path, legacy)
        assert load_aliases(db().execute('SELECT aliases FROM malware_families').fetchone()[0]) == []


@pytest.mark.parametrize('value', [None, 'one', [''], ['Dupe','DUPE'], [' a '], [1], ['a'*201]])
def test_portable_validation_rejects_invalid_alias_collections(value):
    client, *_ = fixture()
    create(client)
    with app.app_context():
        data = export_library(db(), ROOT)
        data['families'][0]['aliases'] = value
        with pytest.raises(ValueError):
            validate_library(data, ROOT)


def test_pre_alias_complete_backup_recovers_with_empty_aliases(tmp_path):
    import io
    import zipfile
    from test_malware_families import make_backup
    from installation_backup import restore_installation
    client, *_ = fixture()
    fid = create(client)
    raw = make_backup(client)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        snapshot = tmp_path / 'old.sqlite3'
        snapshot.write_bytes(archive.read('data/workflow.sqlite3'))
        with sqlite3.connect(snapshot) as con:
            con.execute('ALTER TABLE malware_families DROP COLUMN aliases')
            con.execute("DELETE FROM schema_migrations WHERE name='family-aliases-v1'")
        old = tmp_path / 'legacy.zip'
        with zipfile.ZipFile(old, 'w') as target:
            for entry in archive.infolist():
                if entry.filename == 'installation.json':
                    continue
                target.writestr(entry, snapshot.read_bytes() if entry.filename == 'data/workflow.sqlite3' else archive.read(entry))
    destination = tmp_path / 'recovered'
    restore_installation(old, destination)
    with sqlite3.connect(destination / 'workflow.sqlite3') as con:
        assert con.execute('SELECT aliases FROM malware_families WHERE id=?', (fid,)).fetchone()[0] == '[]'
        assert con.execute("SELECT 1 FROM schema_migrations WHERE name='family-aliases-v1'").fetchone()
        from backup_workspace import schema
        assert schema(con) == app.extensions['backup_workspace'].expected_schema
