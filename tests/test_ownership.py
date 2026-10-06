from app import app,db,run
from werkzeug.security import generate_password_hash

def test_assignment_creator_metrics_and_settings():
    with app.app_context():
        creator=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('owner-creator',generate_password_hash('password-long-123'),'User')).lastrowid
        owner=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('owner-assignee',generate_password_hash('password-long-123'),'User')).lastrowid
    client=app.test_client()
    with client.session_transaction() as session:session.update(uid=creator,version=1,csrf='ownership')
    def post(url,**data):return client.post(url,data={'csrf':'ownership',**data})
    result=post('/cases',name='Ownership test');cid=int(result.location.rsplit('/',1)[1]);base=f'/cases/{cid}'
    with app.app_context():
        row=db().execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()
        assert row['creator']==creator and row['owner'] is None
    assert b'Assign an active owner' in client.get(base).data
    post(base+'/stage',expected='0')
    with app.app_context():assert db().execute('SELECT stage FROM cases WHERE id=?',(cid,)).fetchone()[0]==0
    assert post(base,name='Ownership test',owner_id='999999').status_code==400
    post(base,name='Ownership test',owner_id=str(owner));post(base+'/stage',expected='0')
    with app.app_context():
        row=db().execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()
        assert row['stage']==1 and row['creator']==creator and row['owner']==owner
    board=client.get('/').data
    assert b'Creator:' in board and b'owner-assignee' in board and b'owner-creator' in board
    metrics=client.get('/metrics').data
    assert b'In Progress' in metrics and b'owner-assignee' in metrics
    assert b'id="completed-cases-chart"' in metrics and b'id="case-stage-chart"' in metrics
    assert b'Completed cases by user' in metrics and b'Cases by stage' in metrics
    assert metrics.index(b'id="case-stage-chart"')<metrics.index(b'<h2>User metrics</h2>')
    settings=client.get('/account').data
    assert b'OpenAI configuration' not in settings and b'name="template_id"' not in settings
    assert post('/cases',name='Assigned on creation',owner_id=str(owner)).status_code==302
    assert post('/account/ai',model='new-model').status_code==404
