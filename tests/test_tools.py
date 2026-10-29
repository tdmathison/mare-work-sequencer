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
    assert html.index('title="Dashboards"') < html.index('title="Tools"') < html.index('title="Settings"')
    assert 'role="tab"' in html and 'tool-panel-cyberchef' in html
    assert 'data-src="/tools/cyberchef/app/"' in html
    assert 'allow-scripts allow-same-origin allow-downloads' in html
    assert client.get('/tools/cyberchef').status_code == 200
    assert client.get('/tools/unknown').status_code == 404
    with app.app_context():
        run("UPDATE users SET role='Administrator'")
    html = client.get('/tools').data.decode()
    assert html.index('title="Dashboards"') < html.index('title="Tools"') < html.index('title="Settings"')
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
    assert client.get('/tools').location.endswith('/settings/general')
    assert client.get('/tools/cyberchef/app/assets/main.js').location.endswith('/settings/general')
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


def test_dropdown_uses_available_registry_order_and_direct_tabs(client):
    import html
    import re
    from analyst_tools import register_tool
    tools=[AnalystTool('text-manipulation','Text Manipulation','Text utilities',endpoint='tools_text_manipulation',tool_type='native'),
           AnalystTool('snort-rule-builder','Snort Rule Builder','Snort rules',endpoint='tools_snort',tool_type='native'),
           AnalystTool('yara-rule-editor','YARA Rule Editor','YARA rules',endpoint='tools_yara',tool_type='native')]
    for tool in tools:register_tool(app,tool)
    def entries(page):
        menu=page.split('data-group="Tools"',1)[1].split('class="sidebar-group"',1)[1].split('</div>',1)[0]
        return [(path,html.unescape(label)) for path,label in re.findall(r'<a href="([^"]+)"[^>]*>(?:<span[^>]*>[^<]*</span>)?([^<]+)</a>',menu)]
    page=client.get('/tools').text
    assert entries(page)==[('/tools/'+tool.identifier,tool.name) for tool in [CYBERCHEF]+tools]
    assert page.index('title="Tools"')<page.index('title="Settings"')
    assert 'title="Developer"' not in page  # Default User has no Developer permissions.
    for tool in [CYBERCHEF]+tools:
        response=client.get('/tools/'+tool.identifier)
        assert response.status_code==200
        assert 'href="/tools/'+tool.identifier+'" aria-current="page"' in response.text
        assert 'id="tool-tab-'+tool.identifier+'"' in response.text
        assert 'data-url="/tools/'+tool.identifier+'"' in response.text
    app.extensions['analyst_tools']['cyberchef']=replace(CYBERCHEF,enabled=False)
    app.extensions['analyst_tools']['snort-rule-builder']=replace(tools[1],permission='users:manage')
    page=client.get('/tools').text
    assert entries(page)==[('/tools/text-manipulation','Text Manipulation'),('/tools/yara-rule-editor','YARA Rule Editor')]
    assert 'href="/tools/text-manipulation" aria-current="page" data-navigation-tool="text-manipulation"' in page
    assert client.get('/tools/snort-rule-builder').status_code==403
    assert client.get('/tools/snort-rule-builder/app/').status_code == 403
