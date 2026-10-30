"""The sidebar hierarchy changes without changing destination permissions/routes."""

import pytest
from flask import template_rendered
from app import app, db
from authorization import initialize_roles
from test_developer_shell import browser

ORDER = [
    "MIP Board",
    "Workbench",
    "Search",
    "Malware Families",
    "Threat Actors",
    "Tags",
    "Dashboards",
    "Tools",
    "Data Explorer",
    "Settings",
    "Developer",
]


def navigation(client, path="/"):
    contexts = []

    def capture(sender, template, context, **extra):
        contexts.append(context["sidebar_items"])

    with template_rendered.connected_to(capture, app):
        response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response, contexts[-1]


def test_exact_hierarchy_and_existing_destinations():
    client, _ = browser()
    response, items = navigation(client)
    assert [i["label"] for i in items] == ORDER
    by_name = {i["label"]: i for i in items}
    settings = by_name["Settings"]["children"]
    assert [i["label"] for i in settings] == [
        "General",
        "Users",
        "Audit",
        "Import & Export",
    ]
    assert [i["url"] for i in settings] == [
        "/settings/general",
        "/settings/users",
        "/settings/audit",
        "/settings/import-export",
    ]
    assert {i["label"]: i.get("icon") for i in settings} == {
        "General": "⚙",
        "Users": "♙",
        "Import & Export": "⇄",
        "Audit": "▤",
    }
    developer = by_name["Developer"]["children"]
    assert [i["label"] for i in developer] == ["API", "SDK", "Editor", "Plugins"]
    assert [i["url"] for i in developer] == [
        "/api",
        "/developer/sdk",
        "/developer/editor",
        "/plugins",
    ]
    assert developer[2]["url"] != developer[3]["url"]
    assert developer[3]["icon"] == "◇"
    assert all(child.get("icon") for item in items for child in item["children"])
    tools = by_name["Tools"]["children"]
    assert [child["icon"] for child in tools] == [tool.icon for tool in app.extensions["analyst_tools"].values() if tool.enabled]
    assert "Metrics" not in by_name and "Plugins" not in by_name
    assert "Users" not in by_name and "Import & Export" not in by_name
    assert response.text.count('href="/plugins"') == 1
    for item in items:
        assert client.get(item["url"]).status_code == 200, item
        for child in item["children"]:
            assert client.get(child["url"]).status_code == 200, child
    assert 'href="/metrics"' in client.get("/dashboards").text
    assert client.get("/metrics").status_code == 200


@pytest.mark.parametrize(
    "path,parent,child",
    [
        ("/tools", "Tools", "CyberChef"),
        ("/tools/cyberchef", "Tools", "CyberChef"),
        ("/tools/text-manipulation", "Tools", "Text Manipulation"),
        ("/tools/snort-rule-builder", "Tools", "Snort Rule Builder"),
        ("/tools/yara-rule-editor", "Tools", "YARA Rule Editor"),
        ("/settings/users", "Settings", "Users"),
        ("/settings/import-export", "Settings", "Import & Export"),
        ("/settings/general", "Settings", "General"),
        ("/settings/audit", "Settings", "Audit"),
        ("/plugins", "Developer", "Plugins"),
        ("/developer/editor", "Developer", "Editor"),
        ("/api", "Developer", "API"),
        ("/developer/api", "Developer", "API"),
        ("/developer/sdk", "Developer", "SDK"),
        ("/metrics", "Dashboards", None),
    ],
)
def test_direct_links_highlight_and_expand_the_right_parent(path, parent, child):
    client, _ = browser()
    response, items = navigation(client, path)
    active = [i for i in items if i["active"]]
    assert [i["label"] for i in active] == [parent]
    if child:
        assert [i["label"] for i in active[0]["children"] if i["active"]] == [child]
        assert f'aria-expanded="true" data-group="{parent}"' in response.text
    else:
        assert 'title="Dashboards" aria-current="page"' in response.text


def test_default_user_and_explicit_developer_access():
    client, uid = browser()
    with app.app_context():
        initialize_roles(db())
        db().execute("UPDATE users SET role='User' WHERE id=?", (uid,))
        db().commit()
    _, items = navigation(client)
    assert [i["label"] for i in items] == ORDER[:-1]
    settings = next(i for i in items if i["label"] == "Settings")
    assert [i["label"] for i in settings["children"]] == ["General"]
    for path in (
        "/settings/users",
        "/settings/import-export",
        "/plugins",
        "/developer/editor",
        "/api",
    ):
        assert client.get(path).status_code == 403, path
    assert client.get("/metrics").status_code == 200
    with app.app_context():
        db().execute("INSERT INTO role_permissions VALUES('User','plugins:read')")
        db().commit()
    _, items = navigation(client, "/plugins")
    assert [i["label"] for i in items[-1]["children"]] == ["Editor", "Plugins"]
    assert items[-1]["active"] and client.get("/developer/editor").status_code == 200
    assert client.get("/api").status_code == 403


def test_restricted_role_does_not_gain_moved_permissions():
    client, uid = browser()
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('sidebar-restricted')")
        db().execute("UPDATE users SET role='sidebar-restricted' WHERE id=?", (uid,))
        db().commit()
    _, items = navigation(client)
    assert [i["label"] for i in items] == ["Dashboards", "Tools", "Settings"]
    assert [i["label"] for i in items[-1]["children"]] == ["General"]
    assert 'href="/metrics"' not in client.get("/dashboards").text
    for path in ("/metrics", "/plugins", "/settings/users", "/settings/import-export"):
        assert client.get(path).status_code == 403, path
