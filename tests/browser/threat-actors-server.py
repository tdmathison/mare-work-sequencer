"""Isolated authenticated actor workflow fixture; never use an existing instance."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if not os.environ.get('MARE_ACTOR_BROWSER_TEST') or not os.environ.get('MARE_DATA_DIR'):
    raise RuntimeError('An isolated test data directory is required')
from app import app,db,ensure_package,now
from werkzeug.security import generate_password_hash
from tagging import create
with app.app_context():
    uid=db().execute('INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)',('actor-browser',generate_password_hash('actor-browser-password'),'Administrator')).lastrowid
    ta=create(db(),'TA_APT_BROWSER')[0];mal=create(db(),'MAL_BROWSER')[0]
    for i,title in [(1,'Actor-tagged investigation'),(2,'Family-only investigation')]:
        cid=db().execute('INSERT INTO cases(number,name,stage,created,owner,creator) VALUES(?,?,?,?,?,?)',(f'MARE-ACTOR-{i}',title,1,now(),uid,uid)).lastrowid
        db().execute('INSERT INTO case_tags VALUES(?,?,?,?)',(cid,mal,now(),uid))
        if i==1:db().execute('INSERT INTO case_tags VALUES(?,?,?,?)',(cid,ta,now(),uid))
        ensure_package(cid)
    db().commit()
app.run(host='127.0.0.1',port=int(os.environ.get('MARE_ACTOR_TEST_PORT','8804')),use_reloader=False)
