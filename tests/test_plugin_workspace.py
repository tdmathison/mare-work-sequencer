import io
import json
import zipfile
import pytest
from app import app, db
from test_developer_shell import browser
import plugin_store as store


def metadata(pid="hello_plugin"):
    return dict(
        schema="mws-plugin/1",
        id=pid,
        name="Hello plugin",
        description="Example",
        version="1.0.0",
        author="Analyst",
        entrypoint="main.py:run",
        api_version="v1",
        sdk_version=">=1,<2",
        plugin_api="1",
        permissions=["cases:read"],
        dependencies=[],
    )


def post(client, path, payload=None, **extra):
    return client.post(
        "/developer/workspace/" + path,
        data={"csrf": "dev-csrf", "payload": json.dumps(payload or {}), **extra},
    )


def create(client, pid="hello_plugin"):
    response = post(client, "plugins", dict(manifest=metadata(pid), template="hello"))
    assert response.status_code == 201, response.text
    return client.get("/developer/workspace/plugins/" + pid).json


def test_draft_files_conflicts_binary_ownership_and_history():
    client, _ = browser()
    draft = create(client)
    assert (
        not draft["enabled"]
        and draft["development"] == "Draft"
        and draft["versions"] == []
    )

    def edit(data):
        return post(client, "plugins/hello_plugin/files", data)

    response = edit(
        dict(revision=1, path="main.py", text="def run(context):\n    return 42\n")
    )
    assert response.status_code == 200
    assert edit(dict(revision=1, path="main.py", text="lost")).status_code == 409
    assert (
        b"return 42"
        in client.get(
            "/developer/workspace/plugins/hello_plugin/file?path=main.py"
        ).data
    )
    assert (
        edit(
            dict(revision=2, path="docs/readme.md", operation="create", text="# Hi")
        ).status_code
        == 200
    )
    assert (
        edit(
            dict(
                revision=3,
                path="docs/readme.md",
                operation="rename",
                target="docs/guide.md",
            )
        ).status_code
        == 200
    )
    assert edit(dict(revision=4, path="docs", operation="directory")).status_code == 200
    assert edit(dict(revision=5, path="docs", operation="delete")).status_code == 200
    for path in ("../escape", "/tmp/escape", "a\\b", ".env", "logs/secret", "a/../b"):
        assert (
            edit(dict(revision=6, path=path, operation="create", text="")).status_code
            == 400
        )
    other, _ = browser()
    assert other.get("/developer/workspace/plugins/hello_plugin").status_code == 404
    assert (
        post(other, "plugins/hello_plugin/delete", dict(revision=6)).status_code == 404
    )
    assert (
        post(client, "plugins/hello_plugin/delete", dict(revision=6)).status_code == 200
    )
    assert client.get("/developer/workspace/plugins/hello_plugin").status_code == 404
    assert client.get("/developer/workspace/plugins/hello_plugin/history").json == {
        "executions": []
    }


def test_templates_validation_and_roundtrip_no_execution():
    client, _ = browser()
    for template in store.TEMPLATES:
        pid = "template_" + template
        assert (
            post(
                client, "plugins", dict(manifest=metadata(pid), template=template)
            ).status_code
            == 201
        )
        validation = post(client, "plugins/" + pid + "/static-validation").json
        assert validation["valid"], validation
        exported = client.get("/developer/workspace/plugins/" + pid + "/export")
        entries, value = store.inspect_archive(exported.data)
        assert value["id"] == pid and "tests/test_plugin.py" in entries
        assert all("secret" not in p for p in entries)
        for action in ("run", "test", "debug", "language"):
            assert post(client, "plugins/" + pid + "/" + action).status_code == 503
    # No submitted source is imported or run, even when its top level is hostile.
    assert (
        post(
            client,
            "plugins/template_hello/files",
            dict(
                revision=1,
                path="main.py",
                text='raise RuntimeError("must not run")\ndef run(context): pass',
            ),
        ).status_code
        == 200
    )
    assert post(client, "plugins/template_hello/static-validation").json["valid"]


def test_import_disabled_and_archive_rejections():
    client, _ = browser()
    entries = store.template_files(metadata(), "hello")
    raw = store.archive(entries)
    imported = post(client, "import", archive=(io.BytesIO(raw), "plugin.zip"))
    assert imported.status_code == 201
    detail = client.get("/developer/workspace/plugins/hello_plugin").json
    assert detail["enabled"] == 0 and detail["published_version"] is None
    assert (
        post(client, "import", archive=(io.BytesIO(raw), "plugin.zip")).status_code
        == 409
    )
    for path in (
        "../x",
        "a/../../x",
        "/etc/passwd",
        ".env",
        "resources/secret/../../escape",
    ):
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr(path, "unsafe")
        assert (
            post(
                client, "import", archive=(io.BytesIO(bad.getvalue()), "plugin.zip")
            ).status_code
            == 400
        )
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        symlink = zipfile.ZipInfo("link")
        symlink.create_system = 3
        symlink.external_attr = 0o120777 << 16
        archive.writestr(symlink, "/etc/passwd")
    with pytest.raises(ValueError):
        store.inspect_archive(bad.getvalue())
    with pytest.raises(ValueError):
        store.validate_tree(
            {"X": dict(body=b"", directory=False), "x": dict(body=b"", directory=False)}
        )
    with pytest.raises(ValueError):
        store.validate_tree(
            {
                "a": dict(body=b"", directory=False),
                "a/b": dict(body=b"", directory=False),
            }
        )


def test_permissions_csrf_and_manifest_types():
    client, uid = browser()
    create(client)
    assert (
        client.post("/developer/workspace/plugins/hello_plugin/validate").status_code
        == 403
    )
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('plugin-reader')")
        db().execute(
            "INSERT INTO role_permissions VALUES('plugin-reader','plugins:read')"
        )
        db().execute("UPDATE users SET role='plugin-reader' WHERE id=?", (uid,))
        db().commit()
    assert client.get("/developer/workspace/plugins/hello_plugin").status_code == 200
    for path in (
        "plugins",
        "import",
        "plugins/hello_plugin/files",
        "plugins/hello_plugin/delete",
        "plugins/hello_plugin/static-validation",
        "plugins/hello_plugin/run",
        "plugins/hello_plugin/debug",
    ):
        assert post(client, path).status_code == 403, path
    for field, value in [
        ("id", []),
        ("version", {}),
        ("entrypoint", None),
        ("permissions", [{}]),
        ("configuration", {"foo": None}),
    ]:
        invalid = metadata()
        invalid[field] = value
        with pytest.raises(ValueError):
            store.manifest(invalid)
