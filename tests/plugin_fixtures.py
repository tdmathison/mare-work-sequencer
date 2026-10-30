"""Installed package fixtures shared by plugin lifecycle tests."""
import json
import uuid
from app import app
from test_api import make_user


def browser(role='Administrator'):
    uid, token = make_user('plugins-'+uuid.uuid4().hex[:8],role=role)
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(uid=uid,version=1,csrf='plugin-csrf')
    return client,uid


def metadata(pid='hello_plugin'):
    return dict(schema='mws-plugin/1',id=pid,name='Hello plugin',description='External example',
                version='1.0.0',author='Analyst',entrypoint='main.py:run',api_version='v1',
                sdk_version='>=1,<2',plugin_api='1',permissions=[],dependencies=[])


def package_entries(value=None):
    return {'plugin.json':dict(body=json.dumps(value or metadata()).encode(),directory=False),
            'main.py':dict(body=b'def run(context):\n print("Hello World")\n context.log("Hello diagnostic")\n',directory=False)}


def install(folder,value=None):
    value=value or metadata()
    package=folder/value['id'];package.mkdir(parents=True,exist_ok=True)
    for name,item in package_entries(value).items():(package/name).write_bytes(item['body'])
    return package


def post(client,path,payload=None):
    return client.post(path,data={'csrf':'plugin-csrf','payload':json.dumps(payload or {})})
