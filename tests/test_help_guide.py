"""Global Help permissions, atomic edits, rendering and recovery compatibility."""
import json
import sqlite3
import uuid
import pytest
from werkzeug.security import generate_password_hash
from app import app, db
from help_guide import DEFAULT_INTRO, read, recover, render


@pytest.fixture
def clients():
    with app.app_context():
        ids = []
        for role in ('Administrator', 'User'):
            ids.append(db().execute('INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)', (role, generate_password_hash('help-password-123'), role)).lastrowid)
        db().commit()
    result = []
    for uid in ids:
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(uid=uid, version=1, csrf='help-csrf')
        result.append(client)
    return result


def post(client, doc):
    return client.post('/help/content', data={'csrf':'help-csrf','document':json.dumps(doc)})


def example(doc):
    return dict(doc, introduction='A short guide.', sops=[dict(id=uuid.uuid4().hex,title='Investigation SOP',url='https://example.sharepoint.com/sites/sop?web=1&x=2#section')], faqs=[dict(id=uuid.uuid4().hex,question='Where to start?',answer='Use **Notes** and `code`.\n\n- First\n- Second\n\n```python\nprint(42)\n```')])


def test_access_navigation_empty_and_csrf(clients):
    admin, user = clients
    assert app.test_client().get('/help').status_code == 302
    assert app.test_client().get('/help/content').status_code == 302
    login = app.test_client().get('/login').text
    assert 'href="/help"' not in login
    for client in clients:
        response = client.get('/help')
        assert response.status_code == 200
        assert 'No SOP documents configured.' in response.text
        assert 'No FAQs configured.' in response.text
        from test_sidebar_hierarchy import navigation
        _, entries = navigation(client, '/help')
        assert entries[-1]['label'] == 'Help'
        assert entries[-1]['active']
    assert 'Manage help' not in user.get('/help').text
    assert post(user, example(user.get('/help/content').json)).status_code == 403
    assert user.post('/help/preview', data={'csrf':'help-csrf','text':'Hi'}).status_code == 403
    assert admin.post('/help/content',data={'document':'{}'}).status_code == 403


def test_crud_metadata_order_conflicts_and_persistence(clients):
    admin, _ = clients
    original = admin.get('/help/content').json
    doc = example(original)
    response = post(admin, doc)
    assert response.status_code == 200, response.text
    saved = response.json
    assert saved['revision'] == 1
    assert saved['sops'][0]['url'] == doc['sops'][0]['url']
    assert saved['faqs'][0]['created_by']
    assert '<strong>Notes</strong>' in saved['faqs'][0]['html']
    assert '<ul>' in saved['faqs'][0]['html'] and '<pre' in saved['faqs'][0]['html']
    assert admin.get('/help/content').json == saved
    assert post(admin, doc).status_code == 409
    assert admin.get('/help/content').json == saved
    saved['faqs'].append(dict(id=uuid.uuid4().hex,question='Second?',answer='Answer content'))
    saved['sops'].append(dict(id=uuid.uuid4().hex,title='Other',url='https://tenant.sharepoint.com/other'))
    saved['faqs'].reverse(); saved['sops'].reverse()
    updated = post(admin,saved).json
    assert updated['faqs'][0]['question'] == 'Second?'
    assert updated['sops'][0]['position'] == 0
    assert updated['faqs'][1]['created_at'] == response.json['faqs'][0]['created_at']
    updated['faqs'] = updated['faqs'][:1]; updated['sops'] = []
    assert post(admin,updated).status_code == 200
    with app.app_context():
        assert db().execute("SELECT count(*) FROM audit WHERE action LIKE 'Updated global Help%'").fetchone()[0] == 3


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,test','http://example.com','//example.com','https://user:pass@example.com','https://host:bad/path','https://host/a\npath','https://host\\evil/path'])
def test_bad_sop_urls_do_not_replace_saved_content(clients,url):
    admin, _ = clients
    doc = example(admin.get('/help/content').json)
    doc['sops'][0]['url'] = url
    assert post(admin,doc).status_code == 400
    assert admin.get('/help/content').json['revision'] == 0


def test_limits_plain_questions_and_sanitized_markdown(clients):
    admin, _ = clients
    doc = example(admin.get('/help/content').json)
    doc['faqs'][0]['question'] = '<script>alert(1)</script>'
    doc['faqs'][0]['answer'] = '<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n![pixel](https://example.com/pixel)'
    response = post(admin,doc)
    assert response.status_code == 200
    html = response.json['faqs'][0]['html']
    assert '<script>' not in html and 'href="javascript:' not in html and '<img' not in html
    page = admin.get('/help').text
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert admin.post('/help/preview',data={'csrf':'help-csrf','text':doc['faqs'][0]['answer']}).json['html'] == html
    doc = response.json; doc['introduction'] = 'First\nSecond'
    assert post(admin,doc).status_code == 400
    doc['introduction'] = 'Guide'; doc['faqs'][0]['answer'] = 'x'*20001
    assert post(admin,doc).status_code == 400


def test_additive_recovery_retains_missing_help_and_modern_content(clients):
    admin, _ = clients
    configured = post(admin,example(admin.get('/help/content').json)).json
    configured['faqs'][0].pop('html')
    with sqlite3.connect(':memory:') as old:
        assert recover(old,configured)
        assert read(old) == configured
        assert not recover(old,dict(configured,introduction='Do not replace modern content'))
        assert read(old) == configured
    with sqlite3.connect(':memory:') as fresh:
        assert recover(fresh)
        assert read(fresh)['introduction'] == DEFAULT_INTRO


def test_complete_archive_recovers_guide_and_older_archive_retains_destination(clients,tmp_path):
    import io
    import hashlib
    import zipfile
    from test_malware_families import make_backup
    from installation_backup import restore_installation
    admin, _ = clients
    saved = post(admin,example(admin.get('/help/content').json)).json
    saved['faqs'][0].pop('html')
    with app.app_context():
        from malware_families import initialize as initialize_families
        initialize_families(db())
    archive = make_backup(admin)
    path = tmp_path/'complete.zip'; path.write_bytes(archive)
    destination = tmp_path/'fresh'
    restore_installation(path,destination)
    with sqlite3.connect(destination/'workflow.sqlite3') as con:
        assert read(con) == saved
    # Represent a genuine pre-feature snapshot, with correct original hashes.
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        files = {name:z.read(name) for name in z.namelist()}
    snapshot = tmp_path/'old.sqlite3'; snapshot.write_bytes(files['data/workflow.sqlite3'])
    with sqlite3.connect(snapshot) as con:
        con.execute('DROP TABLE help_guide'); con.commit()
    files['data/workflow.sqlite3'] = snapshot.read_bytes()
    manifest = json.loads(files['installation.json'])
    manifest['files']['data/workflow.sqlite3']['size'] = len(files['data/workflow.sqlite3'])
    manifest['files']['data/workflow.sqlite3']['sha256'] = hashlib.sha256(files['data/workflow.sqlite3']).hexdigest()
    files['installation.json'] = json.dumps(manifest).encode()
    older = tmp_path/'older.zip'
    with zipfile.ZipFile(older,'w') as z:
        for name,value in files.items(): z.writestr(name,value)
    result = restore_installation(older,tmp_path/'upgraded',help_content=saved)
    assert result['help_missing']
    with sqlite3.connect(tmp_path/'upgraded'/'workflow.sqlite3') as con:
        assert read(con) == saved
