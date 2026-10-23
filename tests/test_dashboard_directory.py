import pytest
from werkzeug.security import generate_password_hash
from app import app, db, run
from authorization import initialize_roles
from dashboard_directory import DASHBOARDS
from test_navigation import NavigationParser


def login_client(role='User'):
    with app.app_context():
        initialize_roles(db())
        uid = run("INSERT INTO users(username,password,role,forced) VALUES('directory',?,?,0)",
                  (generate_password_hash('directory-password'), role)).lastrowid
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid, version=1, csrf='directory-token')
    return client


def test_anonymous_directory_and_shared_registry(monkeypatch):
    # Directory rendering must not invoke either public dashboard dataset.
    for endpoint in ('cases_dashboard_data', 'family_dashboard_data'):
        monkeypatch.setitem(app.view_functions, endpoint, lambda: pytest.fail('dataset fetched'))
    monkeypatch.setattr('app.scorecard', lambda *args, **kwargs: pytest.fail('Metrics dataset fetched'))
    client = app.test_client()
    response = client.get('/dashboards')
    assert response.status_code == 200
    assert client.get('/metrics').headers['Location'] == '/login?next=/metrics'
    html = response.text
    for entry in DASHBOARDS:
        assert entry.name in html and entry.description in html
    assert 'admin-nav' not in html
    assert 'Sign in to open' in html and '/login?next=/metrics' in html
    assert html.count('class="directory-row"') == len(DASHBOARDS)
    assert 'href="None"' not in html
    assert 'Coming later' in html and 'Threat Actors' in html
    for path in ('/dashboards/cases', '/dashboards/malware-families'):
        wall = client.get(path)
        assert wall.status_code == 200
        assert b'admin-nav' not in wall.data
        assert 'class="wall-login" href="/login">Login</a>' in wall.text
        for entry in DASHBOARDS:
            if entry.visibility == 'public':
                assert entry.name in wall.text


def test_authorized_menu_and_active_section():
    client = login_client()
    html = client.get('/dashboards').text
    links = NavigationParser(html).links
    assert [link['href'] for link in links if link.get('aria-current') == 'page'] == ['/dashboards']
    assert 'METRICS</a>' not in html
    assert 'Metrics — Private' in html
    assert 'Threat Actors — Coming later</span>' in html
    assert 'aria-label="Open dashboard: Metrics"' in html
    assert client.get('/metrics').status_code == 200
    for path in ('/dashboards/cases', '/dashboards/malware-families'):
        wall = client.get(path)
        assert 'class="wall-login" href="/">Return</a>' in wall.text
        assert 'class="wall-login" href="/login"' not in wall.text
    assert 'href="/dashboards" aria-current="page"' in client.get('/metrics').text
    assert 'aria-current="true">Metrics — Private' in client.get('/metrics').text
    top = [link['href'] for link in links]
    assert top.index('/api') + 1 == top.index('/tools/cyberchef')


def test_restricted_metrics_is_enforced_server_side():
    client = login_client('Restricted')
    html = client.get('/dashboards').text
    assert 'Access restricted' in html
    assert 'href="/metrics"' not in html
    assert client.get('/metrics').status_code == 403
    assert client.get('/metrics?weeks=4').status_code == 403


@pytest.mark.parametrize('destination,expected', [
    ('/metrics','/metrics'), ('https://evil.example','/'), ('//evil.example','/'),
    ('/\\evil.example','/'), ('/%2f%2fevil.example','/'), ('/metrics?next=//evil.example','/'),
    ('javascript:alert(1)','/'), ('/settings/users','/'),
])
def test_login_validates_return_on_get_and_post(destination, expected):
    login_client()
    client = app.test_client()
    response = client.get('/login', query_string={'next': destination})
    assert response.status_code == 200
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post('/login', data={'username':'directory', 'password':'directory-password', 'csrf':csrf, 'next':destination})
    assert response.status_code == 302
    assert response.headers['Location'] == expected
    if expected == '/metrics':
        assert client.get(expected).status_code == 200
