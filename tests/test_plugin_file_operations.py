import json
import pytest
from app import app, db
from test_developer_shell import browser
from test_plugin_workspace import create, post
from plugin_file_operations import organize, directory_exists


def setup_tree():
    client, uid = browser()
    create(client)
    for path, operation in [('src','directory'),('src/nested','directory'),('src/a.py','create'),('src/nested/b.py','create'),('dest','directory')]:
        assert change(client, operation, path=path).status_code == 200
    return client, uid


def detail(client):
    return client.get('/developer/workspace/plugins/hello_plugin').json


def change(client, operation, **data):
    data.setdefault('revision',detail(client)['revision'])
    return post(client, 'plugins/hello_plugin/files', {'operation':operation,**data})


def test_atomic_folder_move_copy_root_and_collision_safe_duplicates():
    client, _ = setup_tree()
    moved=change(client,'move',paths=['src','src/a.py'],destination='dest')
    assert moved.status_code == 200
    assert moved.json['changes']['roots'] == [{'source':'src','target':'dest/src'}]
    names={f['path'] for f in detail(client)['files']}
    assert 'dest/src/nested/b.py' in names and 'src/a.py' not in names
    copied=change(client,'copy',paths=['dest/src'],destination='dest')
    assert copied.status_code == 200
    assert copied.json['changes']['roots'][0]['target'] == 'dest/src copy'
    copied_again=change(client,'copy',paths=['dest/src'],destination='dest')
    assert copied_again.json['changes']['roots'][0]['target'] == 'dest/src copy 2'
    result=change(client,'move',paths=['dest/src/a.py','dest/src/nested/b.py'],destination='')
    assert result.status_code == 200
    assert {'a.py','b.py'}.issubset({f['path'] for f in detail(client)['files']})
    assert change(client,'rename',path='a.py',target='A.py').status_code == 200
    assert change(client,'delete',paths=['dest/src copy','dest/src copy 2']).status_code == 200
    assert not any(f['path'].startswith('dest/src copy') for f in detail(client)['files'])


@pytest.mark.parametrize('operation,data',[
    ('move',{'paths':['src'],'destination':'src/nested'}),
    ('move',{'paths':['src'],'destination':'src'}),
    ('rename',{'path':'src','target':'src/nested/new'}),
    ('copy',{'paths':['src'],'destination':'src/nested'}),
    ('move',{'paths':['src/a.py'],'destination':'src/nested/b.py'}),
    ('move',{'paths':['src/a.py'],'destination':'absent'}),
    ('move',{'paths':['../outside'],'destination':''}),
    ('move',{'paths':['/etc/passwd'],'destination':''}),
    ('move',{'paths':['src/a.py'],'destination':'../../outside'}),
    ('rename',{'path':'src/a.py','target':'dest/bad?.py'}),
    ('move',{'paths':['plugin.json'],'destination':'dest'}),
    ('delete',{'paths':['src','plugin.json']}),
    ('rename',{'path':'plugin.json','target':'metadata.json'}),
    ('create',{'path':'bad|name.txt'}),
    ('create',{'path':'SRC/another.py'}),
])
def test_invalid_operations_leave_entire_snapshot_and_revision_unchanged(operation,data):
    client, _ = setup_tree()
    before=detail(client)
    result=change(client,operation,**data)
    assert result.status_code == 400
    after=detail(client)
    assert (after['revision'],after['files']) == (before['revision'],before['files'])


def test_collisions_stale_revisions_and_ownership_are_enforced():
    client, uid = setup_tree()
    assert change(client,'create',path='dest/a.py').status_code == 200
    before=detail(client)
    assert change(client,'move',paths=['src/a.py','src/nested/b.py'],destination='dest').status_code == 400
    assert detail(client)['files'] == before['files']
    assert change(client,'move',paths=['src'],destination='dest',revision=1).status_code == 409
    assert detail(client)['files'] == before['files']
    other, _ = browser()
    assert post(other,'plugins/hello_plugin/files',{'operation':'move','paths':['src'],'destination':'dest','revision':before['revision']}).status_code == 404
    with app.app_context():
        db().execute("INSERT INTO roles(name) VALUES('explorer-reader')")
        db().execute("INSERT INTO role_permissions VALUES('explorer-reader','plugins:read')")
        db().execute("UPDATE users SET role='explorer-reader' WHERE id=?",(uid,))
        db().commit()
    assert change(client,'copy',paths=['src'],destination='dest').status_code == 403


def test_implicit_folders_and_package_budget_are_bounded():
    entries={'src/a.py':{'body':b'content','directory':False},'dest':{'body':b'','directory':True}}
    moved, changes=organize(entries,'move',['src'],'dest')
    assert moved['dest/src/a.py']['body'] == b'content'
    assert directory_exists(moved,'dest/src')
    assert changes['roots'] == [{'source':'src','target':'dest/src'}]
    crowded={str(i)+'.txt':{'body':b'', 'directory':False} for i in range(200)}
    with pytest.raises(ValueError,match='size limits'):
        organize(crowded,'copy',['0.txt'],'')
