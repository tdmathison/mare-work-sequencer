from html.parser import HTMLParser
import pytest
from app import app, db
from test_developer_shell import browser


class TabLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'a' and attributes.get('id', '').startswith('developer-tab-'):
            self.links.append(attributes)


@pytest.mark.parametrize('path,active', [('/api','api'),('/developer/api','api'),('/developer/sdk','sdk'),('/developer/sdk?document=reference','sdk'),('/developer/editor','editor'),('/plugins','plugins')])
def test_developer_tabs_reuse_sidebar_routes_and_active_state(path, active):
    client, _ = browser()
    response = client.get(path)
    assert response.status_code == 200
    links = TabLinks()
    links.feed(response.text)
    assert [link['id'] for link in links.links] == ['developer-tab-api','developer-tab-sdk','developer-tab-editor','developer-tab-plugins']
    assert [link['href'] for link in links.links] == ['/api','/developer/sdk','/developer/editor','/plugins']
    assert [link['id'] for link in links.links if link.get('aria-current') == 'page'] == ['developer-tab-'+active]
    assert 'aria-label="Developer sections"' in response.text
    assert 'class="mws-tabs developer-navigation"' in response.text


def test_developer_tab_visibility_preserves_existing_permissions():
    client, uid = browser()
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('sdk-navigation-reader')")
        db().execute("INSERT INTO role_permissions VALUES('sdk-navigation-reader','developer:sdk')")
        db().execute("UPDATE users SET role='sdk-navigation-reader' WHERE id=?", (uid,))
        db().commit()
    response = client.get('/developer/sdk')
    assert response.status_code == 200
    links = TabLinks();links.feed(response.text)
    assert [link['id'] for link in links.links] == ['developer-tab-sdk']
    for path in ('/api','/developer/editor','/plugins'):
        assert client.get(path).status_code == 403
