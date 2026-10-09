import io
from werkzeug.security import generate_password_hash
from app import app,db,run,ensure_package,completion_items

def test_task_states_package_fields_and_markdown_preview():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('task-editor',generate_password_hash('password-long-123'),'User')).lastrowid
        cid=run("INSERT INTO cases(number,name,created,stage) VALUES('TASK-1','Task case','2026',1)").lastrowid
        ensure_package(cid)
    client=app.test_client()
    with client.session_transaction() as s:s.update(uid=uid,version=1,csrf='task-token')
    base=f'/cases/{cid}'
    def post(path,**data):return client.post(base+path,data={'csrf':'task-token',**data})
    response=post('/tasks',name='Decode configuration',description='Review strings',priority='High',state='Completed')
    assert response.status_code==302 and response.location.endswith('?tab=tasks')
    with app.app_context():
        task=db().execute('SELECT * FROM tasks WHERE case_id=?',(cid,)).fetchone();tid=task['id']
        assert task['state']=='Not Started' and task['priority']=='High' and task['done']==0
        item=next(item for item in completion_items(cid) if item['target']=='case-tasks')
        assert item['tab']=='tasks'
    assert post(f'/tasks/{tid}/edit',name='Decode configuration',description='In progress',priority='Critical',state='In Progress').status_code==302
    with app.app_context():assert db().execute('SELECT state FROM tasks WHERE id=?',(tid,)).fetchone()[0]=='In Progress'
    assert post(f'/tasks/{tid}/edit',name='Decode configuration',description='Finished',priority='Normal',state='Completed').status_code==302
    with app.app_context():
        assert db().execute('SELECT done FROM tasks WHERE id=?',(tid,)).fetchone()[0]==1
        assert not any(item['target']=='case-tasks' for item in completion_items(cid))
    assert post('/tasks',name='Invalid state',priority='Unknown').status_code==400
    assert post('/readiness',category='signatures',status='Not applicable').status_code==302
    assert post('/upload',category='scripts',file=(io.BytesIO(b'print(1)'),'decode.py'),description='Decode',usage='Do not track').status_code==302
    with app.app_context():assert db().execute('SELECT usage FROM artifacts WHERE case_id=?',(cid,)).fetchone()[0]==''
    page=client.get(base).data.decode()
    assert page.index('id="tab-tasks"')<page.index('id="tab-indicators"')<page.index('id="tab-references"')<page.index('id="tab-package"')<page.index('id="tab-report"')
    workbench=page.split('id="panel-workbench"')[1].split('id="panel-tasks"')[0]
    assert 'Add task' not in workbench and 'Save task' not in workbench
    package=page.split('id="panel-package"')[1].split('id="panel-indicators"')[0]
    assert 'name="reason"' not in package and 'scripts/decode.py' in package
    assert 'Usage (for scripts)' not in page and 'editor-preview-tab' in page
    result=post('/markdown-preview',text='# Heading\n\n**bold**\n\n|A|B|\n|---|---|\n|1|2|\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n![image](https://example.org/track.png)')
    assert result.status_code==200
    html=result.json['html']
    assert '<h1>Heading</h1>' in html and '<strong>bold</strong>' in html and '<table>' in html
    assert '<script>' not in html and 'href="javascript:' not in html and '<img' not in html

def test_task_markdown_images_full_dialogs_and_backup_restore():
    from PIL import Image
    from app import package
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('task-media-editor',generate_password_hash('password-long-123'),'User')).lastrowid
        cid=run("INSERT INTO cases(number,name,created,stage,owner) VALUES('TASK-MEDIA','Task media','2026',1,?)",(uid,)).lastrowid
        ensure_package(cid)
    client=app.test_client()
    with client.session_transaction() as s:s.update(uid=uid,version=1,csrf='task-media-token')
    base=f'/cases/{cid}'
    def post(path,**data):return client.post(base+path,data={'csrf':'task-media-token',**data})
    image=io.BytesIO();Image.new('RGB',(80,40),'blue').save(image,format='PNG')
    saved=post('/report-images',section='task-draft',image=(io.BytesIO(image.getvalue()),'task.png'))
    assert saved.status_code==200
    name=saved.json['name'];body='## Decoder task\n\n**Investigate** the script.\n\n![Image](assets/'+name+')'
    assert post('/tasks',name='Inspect decoder',description=body).status_code==302
    with app.app_context():
        tid=db().execute('SELECT id FROM tasks WHERE case_id=?',(cid,)).fetchone()[0]
        assert db().execute('SELECT section FROM report_images WHERE case_id=?',(cid,)).fetchone()[0]==f'task-{tid}'
    assert post('/report-images',section='task-999999',image=(io.BytesIO(image.getvalue()),'bad-task.png')).status_code==404
    page=client.get(base).data.decode()
    assert f'id="edit-task-dialog-{tid}"' in page and '<summary>Edit task</summary>' not in page
    assert 'data-task-preview' in page and 'data-image-section="task-draft"' in page
    assert 'class="markdown-toolbar"' in page and 'vendor/codemirror/markdown-editor.js' in page
    assert '<textarea class="markdown-source" data-markdown-editor name="description"' in page
    assert 'class="markdown-toolbar"' in page
    preview=post('/markdown-preview',text=body).json['html']
    assert '<h2>Decoder task</h2>' in preview and '<strong>Investigate</strong>' in preview and name in preview
    backup=post('/backup');assert backup.status_code==200
    response=client.post('/import-export/import-raw',data={'csrf':'task-media-token','backup':(io.BytesIO(backup.data),'task-backup.zip')})
    assert response.location=='/'
    with app.app_context():
        new=db().execute('SELECT id FROM cases ORDER BY id DESC LIMIT 1').fetchone()[0]
        new_task=db().execute('SELECT * FROM tasks WHERE case_id=?',(new,)).fetchone()
        assert new_task['body']==body
        assert db().execute('SELECT section FROM report_images WHERE case_id=?',(new,)).fetchone()[0]==f'task-{new_task["id"]}'
    assert (package(new)/'reports/sections/assets'/name).is_file()
    assert post('/report-images/'+name+'/delete').status_code==200
    with app.app_context():assert name not in db().execute('SELECT body FROM tasks WHERE id=?',(tid,)).fetchone()[0]
