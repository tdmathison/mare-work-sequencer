import json,subprocess
from pathlib import Path
from werkzeug.security import generate_password_hash
from app import app,db,run,ensure_package,migrate_four_stages,STAGES

def test_user_autosave_interval_is_private_and_validated():
    with app.app_context():
        uid=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('autosave-user',generate_password_hash('password-long-123'),'User')).lastrowid
        other=run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",('autosave-other',generate_password_hash('password-long-123'),'User')).lastrowid
        cid=run("INSERT INTO cases(number,name,created,stage) VALUES('AUTOSAVE','Autosave','2026',1)").lastrowid;ensure_package(cid)
    client=app.test_client()
    with client.session_transaction() as s:s.update(uid=uid,version=1,csrf='autosave-token')
    def post(value):return client.post('/account/autosave',data={'csrf':'autosave-token','autosave_minutes':value})
    assert b'value="1"' in client.get('/account').data
    for value in ['1','7','60','1440']:
        assert post(value).status_code==302
        with app.app_context():
            assert db().execute('SELECT autosave_minutes FROM users WHERE id=?',(uid,)).fetchone()[0]==int(value)
            assert db().execute('SELECT autosave_minutes FROM users WHERE id=?',(other,)).fetchone()[0]==1
    for value in ['0','-2','2.5','invalid','']:
        post(value)
        with app.app_context():assert db().execute('SELECT autosave_minutes FROM users WHERE id=?',(uid,)).fetchone()[0]==1440
    page=client.get(f'/cases/{cid}').data
    assert b'data-autosave-minutes="1440"' in page and b'filename' not in page
    assert b'/static/autosave.js' in page
    for filename in ['report-workspace.js','indicators.js','references.js']:
        assert 'MareAutosave.register' in (Path('static')/filename).read_text()

def test_four_stage_migration_preserves_completion_and_deferred_reasons():
    with app.app_context():
        ids=[]
        for stage in range(5):
            cid=run('INSERT INTO cases(number,name,created,stage) VALUES(?,?,?,?)',(f'FOUR-{stage}','Migration','2026',stage)).lastrowid;ids.append(cid)
            run('INSERT INTO history(case_id,stage) VALUES(?,?)',(cid,stage))
        run("INSERT INTO deferred VALUES(?,1,'Analysis follow-up',1)",(ids[2],))
        run("INSERT INTO deferred VALUES(?,2,'Report follow-up',0)",(ids[2],))
        migrate_four_stages(db())
        assert [db().execute('SELECT stage FROM cases WHERE id=?',(cid,)).fetchone()[0] for cid in ids]==[0,1,1,2,3]
        assert [row[0] for row in db().execute('SELECT stage FROM history ORDER BY id')]==[0,1,1,2,3]
        row=db().execute('SELECT * FROM deferred').fetchone()
        assert row['stage']==1 and row['resolved']==0 and 'Analysis follow-up' in row['reason'] and 'Report follow-up' in row['reason']
        migrate_four_stages(db())
        assert db().execute('SELECT stage FROM cases WHERE id=?',(ids[3],)).fetchone()[0]==2
    assert STAGES==['Not started','Malware Analysis','Packaging & Delivery','Completed']

def test_autosave_scheduler_interval_dirty_check_and_failure_feedback():
    source=Path('static/autosave.js').read_text()
    script='''const vm=require('vm'),assert=require('assert');
    let now=0,tick,visibility,dirty=true,saves=0,errors=0;
    const context={window:{},document:{body:{dataset:{autosaveMinutes:'5'}},hidden:false,addEventListener:(name,fn)=>visibility=fn},Date:{now:()=>now},setInterval:fn=>tick=fn};
    vm.runInNewContext(SOURCE,context);
    context.window.MareAutosave.register({canSave:()=>dirty,save:async()=>{saves++;dirty=false;},onError:()=>errors++});
    (async()=>{now=299999;await tick();assert.equal(saves,0);now=300000;await tick();assert.equal(saves,1);now=600000;await tick();assert.equal(saves,1);dirty=true;now=900000;await tick();assert.equal(saves,2);
    context.window.MareAutosave.register({canSave:()=>true,save:async()=>{throw Error('offline')},onError:()=>errors++});now=1200000;await tick();assert.equal(errors,1);now=1500000;await tick();assert.equal(errors,2);console.log('Scheduler checks passed');})().catch(error=>{console.error(error);process.exitCode=1});'''.replace('SOURCE',json.dumps(source))
    subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)

def test_countdown_and_manual_reset():
    source=Path('static/autosave.js').read_text()
    script='''const vm=require('vm'),assert=require('assert');let now=0,tick,last,saves=0;
    const context={window:{},document:{body:{dataset:{}},hidden:false,addEventListener:()=>{}},Date:{now:()=>now},setInterval:fn=>tick=fn};vm.runInNewContext(SOURCE,context);
    const timer=context.window.MareAutosave.register({canSave:()=>true,onCountdown:seconds=>last=seconds,save:async()=>saves++,onError:()=>{}});
    (async()=>{assert.equal(last,60);now=30000;await tick();assert.equal(last,30);timer.reset();assert.equal(last,60);now=60000;await tick();assert.equal(saves,0);assert.equal(last,30);now=90000;await tick();assert.equal(saves,1);assert.equal(last,60);now=150000;await tick();assert.equal(saves,2);assert.equal(last,60)})().catch(e=>{console.error(e);process.exitCode=1});'''.replace('SOURCE',json.dumps(source))
    subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)
