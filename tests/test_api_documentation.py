"""Public specification drift, session/CSRF, and real isolated API contracts."""
import io
import json
import re
import subprocess
from pathlib import Path

import pytest
from app import app, db, run
from api_documentation import CONTRACTS, build_spec
from test_api import make_user, start_case


@pytest.fixture
def docs():
    app.config['TESTING'] = True
    uid, headers = make_user('documentation-admin')
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf='documentation-csrf')
    return client, uid, headers


def test_spec_is_protected_by_web_session(docs):
    client, _, headers = docs
    anonymous = app.test_client()
    for path in ('/api', '/api/openapi.json'):
        assert anonymous.get(path).status_code == 302
        assert anonymous.get(path, headers=headers).status_code == 302
        assert client.get(path).status_code == 200
    response = client.get('/api/openapi.json')
    assert response.headers['Cache-Control'] == 'no-store'
    assert headers['Authorization'].split(' ')[1] not in response.text
    with client.session_transaction() as session:
        session.clear()
    assert client.get('/api/openapi.json').status_code == 302
    # External bearer clients retain their existing authentication model.
    assert client.get('/api/v1/me', headers=headers).status_code == 200


def test_every_public_operation_and_permission_is_documented(docs):
    spec = docs[0].get('/api/openapi.json').json
    expected, actual, endpoints = set(), set(), set()
    ids = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/api/v1/'):
            continue
        path = re.sub(r'<(?:[^:>]+:)?([^>]+)>', r'{\1}', rule.rule[len('/api/v1'):])
        endpoint = rule.endpoint.split('.')[-1]
        for method in rule.methods - {'OPTIONS', 'HEAD'}:
            expected.add((path, method.lower()))
            endpoints.add((endpoint, method))
            op = spec['paths'][path][method.lower()]
            permission = getattr(app.view_functions[rule.endpoint], 'permission', None)
            permission = permission.get(method) if isinstance(permission, dict) else permission
            if endpoint.startswith('sync_api_'):
                permission = 'backups:manage'
            assert op['x-required-permission'] == permission
            assert {p['name'] for p in op['parameters'] if p['in'] == 'path'} == rule.arguments
            assert all('default' not in p['schema'] and 'example' not in p for p in op['parameters'] if p['in'] == 'path')
    for path, item in spec['paths'].items():
        for method, op in item.items():
            actual.add((path, method))
            ids.append(op['operationId'])
            assert op['summary'] and op['description'] and op['responses']
    assert expected == actual
    assert endpoints == set(CONTRACTS)
    assert len(ids) == len(set(ids))
    assert spec['security'] == [{'bearerAuth': []}]
    assert spec['components']['securitySchemes']['bearerAuth']['scheme'] == 'bearer'
    assert all(not path.startswith(('/account', '/import-export')) for path in spec['paths'])


def test_openapi_validates_with_pinned_local_validator(docs, tmp_path):
    if not Path('node_modules/@apidevtools/swagger-parser').exists():
        pytest.skip('Run npm ci for the pinned offline specification validator')
    target = tmp_path / 'openapi.json'
    target.write_text(json.dumps(docs[0].get('/api/openapi.json').json))
    outcome = subprocess.run(['node', 'frontend/validate-api-docs.cjs', str(target)], capture_output=True, text=True)
    assert outcome.returncode == 0, outcome.stderr


def test_prefix_and_local_assets(docs):
    client = docs[0]
    spec = client.get('/api/openapi.json', environ_overrides={'SCRIPT_NAME': '/mare'}).json
    assert spec['servers'] == [{'url': '/mare/api/v1', 'description': 'This MARE deployment (same origin)'}]
    page = client.get('/api', environ_overrides={'SCRIPT_NAME': '/mare'}).text
    assert 'data-spec-url="/mare/api/openapi.json"' in page
    assert '/mare/static/vendor/swagger-ui/swagger-ui-bundle.js' in page
    assert re.search(r'<a href="/mare/api" aria-current="page">(?:<span[^>]*>[^<]*</span>)?API</a>', page)
    assert 'data-python-example' in page and 'data-markdown-editor' not in page
    assert 'os.environ["MARE_TOKEN"]' in page
    assert 'BASE = "http://localhost/mare/api/v1"' in page
    for name in ('swagger-ui-bundle.js', 'swagger-ui.css', 'LICENSE', 'NOTICE'):
        assert client.get('/static/vendor/swagger-ui/' + name).status_code == 200


def test_secret_is_revealed_once_through_csrf_protected_response(docs):
    client = docs[0]
    assert client.post('/account/api-tokens', data={'csrf': 'documentation-csrf', 'name': 'docs'}).status_code == 302
    with client.session_transaction() as session:
        secret = session['new_api_token']
    assert secret not in client.get('/api').text
    assert secret not in client.get('/api/openapi.json').text
    assert client.post('/account/api-tokens/reveal').status_code == 403
    reveal = client.post('/account/api-tokens/reveal', data={'csrf': 'documentation-csrf'})
    assert reveal.json == {'token': secret}
    assert reveal.headers['Cache-Control'] == 'no-store'
    assert client.post('/account/api-tokens/reveal', data={'csrf': 'documentation-csrf'}).status_code == 404


def test_user_documentation_does_not_grant_api_permissions():
    uid, headers = make_user('documentation-user', 'User')
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf='user-csrf')
    assert client.get('/api/openapi.json').status_code == 403
    with app.app_context():
        from authorization import initialize_roles
        initialize_roles(db())
        run("INSERT OR IGNORE INTO role_permissions VALUES('User','developer:api')")
    assert client.get('/api/openapi.json').status_code == 200
    assert client.get('/api/v1/me', headers=headers).status_code == 200
    assert client.get('/api/v1/users', headers=headers).status_code == 403
    assert client.get('/api/v1/backups/review/not-an-operation', headers=headers).status_code == 403
    with app.app_context():
        run('UPDATE users SET forced=1 WHERE id=?', (uid,))
    assert client.get('/api/openapi.json').headers['Location'].endswith('/settings/general')


def test_representative_contracts_with_isolated_write_upload_download_and_errors(docs):
    client, uid, headers = docs
    spec = client.get('/api/openapi.json').json
    create = client.post('/api/v1/cases', headers=headers, json={'name': 'Documentation fixture'})
    assert create.status_code == 201
    cid = create.json['case']['id']
    start_case(client, headers, cid, uid)
    assert client.get('/api/v1/me', headers=headers).json['user']['id'] == uid
    written = client.put(f'/api/v1/cases/{cid}/draft', headers=headers, json={'title': 'Example', 'body': 'Isolated test content'})
    assert written.json['draft']['body'] == 'Isolated test content'
    uploaded = client.post(f'/api/v1/cases/{cid}/assets', headers=headers,
                           data={'category': 'scripts', 'file': (io.BytesIO(b'example text\n'), 'example.txt')})
    assert uploaded.status_code == 201
    downloaded = client.get(f'/api/v1/cases/{cid}/assets/scripts/example.txt', headers=headers)
    assert downloaded.data == b'example text\n'
    assert 'attachment' in downloaded.headers['Content-Disposition']
    assert spec['paths']['/cases/{case_id}/assets']['post']['requestBody']['content']['multipart/form-data']['schema']['required'] == ['category', 'file']
    invalid = client.put(f'/api/v1/cases/{cid}/references', headers=headers, json={'revision': 0, 'rows': 'invalid'})
    assert invalid.status_code == 400 and 'error' in invalid.json
    assert spec['paths']['/cases/{case_id}/references']['put']['responses']['400']
    assert client.get(f'/api/v1/cases/{cid}/readiness', headers=headers).json['readiness'][0]['category'] == 'reports'
