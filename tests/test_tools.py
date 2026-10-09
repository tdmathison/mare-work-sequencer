from dataclasses import replace
import pytest
from app import app, db, run
from analyst_tools import CYBERCHEF, AnalystTool


@pytest.fixture
def client():
    with app.app_context():
        uid = run("INSERT INTO users(username,password,role,forced) VALUES('tools-user','unused','User',0)").lastrowid
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf='tools-token')
    return client


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setitem(app.extensions, 'analyst_tools', {'cyberchef': CYBERCHEF})


@pytest.mark.parametrize('path', ['/tools', '/tools/cyberchef', '/tools/cyberchef/app/', '/tools/cyberchef/app/assets/main.js', '/tools/cyberchef/app/mare-theme.css'])
def test_requires_authentication(path):
    response = app.test_client().get(path)
    assert response.status_code == 302 and response.location.endswith('/login')


def test_workspace_and_navigation(client):
    page = client.get('/tools')
    assert page.status_code == 200
    html = page.data.decode()
    assert html.index('METRICS') < html.index('TOOLS') < html.index('SETTINGS')
    assert 'role="tab"' in html and 'tool-panel-cyberchef' in html
    assert 'data-src="/tools/cyberchef/app/"' in html
    assert 'allow-scripts allow-same-origin allow-downloads' in html
    assert client.get('/tools/cyberchef').status_code == 200
    assert client.get('/tools/unknown').status_code == 404
    with app.app_context():
        run("UPDATE users SET role='Administrator'")
    html = client.get('/tools').data.decode()
    assert html.index('METRICS') < html.index('TOOLS') < html.index('USERS')
    assert b'TOOLS' not in app.test_client().get('/login').data


def test_disabled_and_permission_routes(client):
    app.extensions['analyst_tools']['cyberchef'] = replace(CYBERCHEF, enabled=False)
    assert b'tool-panel-cyberchef' not in client.get('/tools').data
    assert client.get('/tools/cyberchef').status_code == 404
    assert client.get('/tools/cyberchef/app/assets/main.js').status_code == 404
    app.extensions['analyst_tools']['cyberchef'] = replace(CYBERCHEF, permission='users:manage')
    assert client.get('/tools/cyberchef').status_code == 403
    assert client.get('/tools/cyberchef/app/').status_code == 403
    assert b'tool-panel-cyberchef' not in client.get('/tools').data
    with app.app_context():
        run("UPDATE users SET role='Administrator'")
    assert client.get('/tools/cyberchef').status_code == 200


def test_missing_assets(client, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'CYBERCHEF_DIR', str(tmp_path))
    response = client.get('/tools/cyberchef/app/')
    assert response.status_code == 503 and b'Ask a MARE administrator' in response.data
    with app.app_context():
        run("UPDATE users SET role='Administrator'")
    assert b'python3 scripts/install_cyberchef.py' in client.get('/tools/cyberchef/app/').data


def test_local_assets_policy_and_no_database_changes(client, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, 'CYBERCHEF_DIR', str(tmp_path))
    (tmp_path/'index.html').write_text('<html><head></head><body>CyberChef</body></html>')
    (tmp_path/'assets').mkdir()
    (tmp_path/'assets/worker.js').write_text('self.onmessage = () => {};')
    with app.app_context():
        before = '\n'.join(db().iterdump())
    response = client.get('/tools/cyberchef/app/')
    assert b'mare-theme.css' in response.data
    assert response.headers['Cache-Control'] == 'no-store'
    assert "connect-src 'self' blob: data:" in response.headers['Content-Security-Policy']
    assert "frame-ancestors 'self'" in response.headers['Content-Security-Policy']
    assert client.get('/tools/cyberchef/app/assets/worker.js').status_code == 200
    assert client.get('/tools/cyberchef/app/mare-theme.css').mimetype == 'text/css'
    assert b'--accent: #d9ae58' in client.get('/tools/cyberchef/app/mare-palette.css').data
    assert client.get('/tools/cyberchef/app/assets/nope.js').status_code == 404
    assert client.get('/tools/cyberchef/app/../outside').status_code == 404
    client.get('/tools')
    with app.app_context():
        assert '\n'.join(db().iterdump()) == before


def test_existing_session_restrictions(client):
    with app.app_context():
        run('UPDATE users SET forced=1')
    assert client.get('/tools').location.endswith('/account')
    assert client.get('/tools/cyberchef/app/assets/main.js').location.endswith('/account')
    with app.app_context():
        run('UPDATE users SET forced=0,active=0')
    assert client.get('/tools').location.endswith('/login')


def test_registry_extension_and_validation(client):
    from analyst_tools import register_tool
    tool = AnalystTool('example', 'Example', 'Native utility', endpoint='tools_workspace', tool_type='native')
    register_tool(app, tool)
    page = client.get('/tools/example')
    assert page.status_code == 200
    assert b'tool-tab-example' in page.data and b'tool-panel-example' in page.data
    assert b'aria-selected="true" tabindex="0" data-tool="example"' in page.data
    with pytest.raises(ValueError):
        register_tool(app, tool)
    with pytest.raises(ValueError):
        register_tool(app, replace(tool, identifier='../bad'))
    with pytest.raises(ValueError):
        register_tool(app, replace(tool, identifier='invalid', tool_type='invalid'))


def test_installer_checksum_failure_preserves_assets(tmp_path):
    from scripts.install_cyberchef import install
    installed = tmp_path/'dist'
    installed.mkdir()
    (installed/'index.html').write_text('existing installation')
    bad_archive = tmp_path/'bad.zip'
    bad_archive.write_bytes(b'untrusted')
    with pytest.raises(ValueError, match='checksum'):
        install(bad_archive, installed)
    assert (installed/'index.html').read_text() == 'existing installation'
