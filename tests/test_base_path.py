"""Exercise the stripped-prefix proxy contract against actual application routes."""
import io
import pytest
from flask import url_for
from werkzeug.security import generate_password_hash
from app import app, run
from base_path import MountMiddleware, app_url, normalize_base_path


@pytest.mark.parametrize('value,expected', [('', ''), ('/', ''), ('/mws/', '/mws'), ('/team/tools', '/team/tools')])
def test_normalize(value, expected):
    assert normalize_base_path(value) == expected


@pytest.mark.parametrize('value', ['mws', '//evil', 'https://evil/mws', '/a?b', '/a#b', '/a/../b', '/.', '/a//b', '/a/%2e%2e', '/a\\b', '/a\nb', '/a b'])
def test_invalid_prefix(value):
    with pytest.raises(ValueError):
        normalize_base_path(value)


@pytest.fixture(params=['', '/mws', '/team/tools', '/cases'])
def mount(request, monkeypatch):
    prefix = request.param
    inner = app.wsgi_app
    while not isinstance(inner, MountMiddleware):
        inner = inner.app
    monkeypatch.setattr(inner, 'prefix', prefix)
    monkeypatch.setitem(app.config, 'APPLICATION_ROOT', prefix or '/')
    monkeypatch.setitem(app.config, 'SESSION_COOKIE_PATH', prefix or '/')
    return prefix


def test_workflows(mount):
    prefix = mount
    client = app.test_client()
    base = 'http://localhost' + prefix + '/'
    def get(path, **kwargs):
        return client.get(path, base_url=base, **kwargs)
    def post(path, **kwargs):
        return client.post(path, base_url=base, **kwargs)
    with app.app_context():
        run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)", ('mount-admin', generate_password_hash('mount-password'), 'Administrator'))
    assert post('/login', data={}).status_code == 403
    assert get('/').location == prefix + '/login'
    login = get('/login')
    assert login.status_code == 200
    cookie = login.headers['Set-Cookie']
    assert cookie.startswith('mws_session=') and 'Path=' + (prefix or '/') in cookie
    with client.session_transaction(base_url=base) as session:
        csrf = session['csrf']
    response = post('/login', data={'csrf': csrf, 'username': 'mount-admin', 'password': 'mount-password'})
    assert response.location == prefix + '/'
    assert get('/').status_code == 200
    assert get('/static/mws-url.js').status_code == 200
    assert get('/api/v1/cases').status_code == 401
    with client.session_transaction(base_url=base) as session:
        csrf = session['csrf']
    response = post('/cases', data={'csrf': csrf, 'name': 'Mounted case'})
    assert response.status_code == 302
    case_path = response.location.removeprefix(prefix)
    assert case_path.startswith('/cases/')
    page = get(case_path)
    assert page.status_code == 200
    for path in ('/static/', '/cases/', '/logout'):
        if prefix and path != prefix + '/':
            assert ('="' + path).encode() not in page.data
    with app.app_context():
        run('UPDATE cases SET owner=1 WHERE id=?', (int(case_path.split('/')[-1]),))
    assert post(case_path + '/stage', data={'csrf': csrf, 'expected': '0'}).status_code == 302
    upload = post(case_path + '/upload', data={'csrf': csrf, 'category': 'scripts', 'file': (io.BytesIO(b'print(42)'), 'mount.py')})
    assert upload.location == prefix + case_path
    download = get(case_path + '/file?path=scripts/mount.py&download=1')
    assert download.status_code == 200 and download.data == b'print(42)'
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, 'PNG')
    image.seek(0)
    response = post(case_path + '/report-images', data={'csrf': csrf, 'section': 'executive_summary', 'image': (image, 'figure.png')})
    assert response.status_code == 200, response.data
    assert response.json['url'].startswith(prefix + case_path + '/report-images/')
    assert get(response.json['url'].removeprefix(prefix)).status_code == 200
    assert get('/missing-route').status_code == 404
    response = get('/account?check=one%20two&check=three')
    assert response.location == prefix + '/settings/general?check=one%20two&check=three'
    assert post('/logout', data={'csrf': csrf}).location == prefix + '/login'
    assert get('/').status_code == 302


def test_proxy_trust_and_urls(mount):
    def capture(environ, start_response):
        with app.request_context(environ):
            assert url_for('login') == mount + '/login'
            assert app_url(mount + '/login') == mount + '/login'
            assert app_url('/cases?q=a%20b#part', internal=True) == mount + '/cases?q=a%20b#part'
            for external in ('https://elsewhere/x', '//elsewhere/x', 'data:image/png,x', 'blob:abc'):
                assert app_url(external) == external
            result.append((url_for('login', _external=True), request_query(environ)))
        start_response('200 OK', [])
        return [b'']
    def request_query(environ):
        return environ['QUERY_STRING']
    result = []
    from werkzeug.test import Client
    client = Client(MountMiddleware(capture, mount, ['127.0.0.1/32']))
    headers = {'X-Forwarded-Prefix': '/evil', 'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'evil.example'}
    client.get('/login?q=a%20b', headers=headers, environ_overrides={'REMOTE_ADDR': '203.0.113.4'})
    assert result[-1] == ('http://localhost' + mount + '/login', 'q=a%20b')
    client.get('/login?q=a%20b', headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert result[-1] == ('https://localhost' + mount + '/login', 'q=a%20b')


def test_api_json_and_documentation(mount):
    import hashlib
    client = app.test_client()
    base = 'http://localhost' + mount + '/'
    with app.app_context():
        uid = run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)", ('mount-api', generate_password_hash('mount-password'), 'Administrator')).lastrowid
        token = 'mount-api-token'
        run('INSERT INTO api_tokens(user_id,name,token_hash,token_prefix,created) VALUES(?,?,?,?,?)', (uid, 'mount', hashlib.sha256(token.encode()).hexdigest(), token[:14], '2026'))
    headers = {'Authorization': 'Bearer ' + token}
    response = client.post('/api/v1/cases', base_url=base, headers=headers, json={'name': 'Mounted JSON case', 'description': 'Query & body unchanged'})
    assert response.status_code == 201, response.data
    assert response.json['case']['name'] == 'Mounted JSON case'
    assert client.get('/api/v1/cases?q=Mounted%20JSON', base_url=base, headers=headers).status_code == 200
    with client.session_transaction(base_url=base) as session:
        session.update(uid=uid, version=1, csrf='mount-test')
    spec = client.get('/api/openapi.json', base_url=base).json
    assert spec['servers'][0]['url'] == mount + '/api/v1'
