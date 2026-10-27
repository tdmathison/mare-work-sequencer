"""Disposable Data Explorer browser fixture; no development records are used."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if not os.environ.get('MARE_EXPLORER_TEST') or not os.environ.get('MARE_DATA_DIR'):
    raise RuntimeError('Isolated data required')
from app import app,db,ensure_package,now
from werkzeug.security import generate_password_hash
from tagging import create
from threat_actors import save_associations
import json,uuid
with app.app_context():
    uid=db().execute('INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)',('explorer-browser',generate_password_hash('explorer-browser-password'),'Administrator')).lastrowid
    family=str(uuid.uuid4());actor=str(uuid.uuid4())
    for table,identity,name,prefix in [('malware_families',family,'Research family','MAL_EXPLORER'),('threat_actors',actor,'Research actor','TA_EXPLORER')]:
        tid=create(db(),prefix)[0]
        db().execute(f'INSERT INTO {table}(id,name,tag_id,aliases,created_at,updated_at) VALUES(?,?,?,?,?,?)',(identity,name,tid,'["Hidden search alias"]',now(),now()))
    save_associations(db(),actor,[family])
    ids=[]
    for i in range(3):
        cid=db().execute('INSERT INTO cases(number,name,created,stage,owner,creator) VALUES(?,?,?,1,?,?)',(f'MARE-EXPLORER-{i+1}','<img src=x onerror=alert(1)> Analysis' if i==0 else 'Investigation '+str(i),now(),uid,uid)).lastrowid;ids.append(cid)
        for tag in ['MAL_EXPLORER','TA_EXPLORER'] if i==0 else ['MAL_EXPLORER']:
            tid=db().execute('SELECT id FROM tags WHERE name=?',(tag,)).fetchone()[0]
            db().execute('INSERT INTO case_tags(case_id,tag_id,assigned_at) VALUES(?,?,?)',(cid,tid,now()))
        root=ensure_package(cid)
        if i==0:
            (root/'scripts'/'deliverable.py').write_text('print("Never executed")')
            (root/'reports'/'research.pdf').write_bytes(b'%PDF-1.4\nResearch report\n%%EOF')
            (root/'supporting'/'image.png').write_bytes(b'not displayed')
            (root/'iocs'/'indicators.csv').write_text('type,value,description\ndomain,example.test,Observed\n')
            (root/'supporting'/'references.csv').write_text('Link,Description\nhttps://example.com,Research\njavascript:alert(1),Unsafe link remains text\n')
    db().commit()
app.run(host='127.0.0.1',port=8806,use_reloader=False)
