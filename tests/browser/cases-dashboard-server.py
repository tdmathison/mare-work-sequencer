"""Disposable data for the anonymous wall browser regression."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if not os.environ.get('MARE_DASHBOARD_BROWSER_TEST') or not os.environ.get('MARE_DATA_DIR'):
    raise RuntimeError('An isolated data directory is required')
from app import app, db, now
with app.app_context():
    for i in range(23):
        stage = 3 if i < 12 else (1 if i % 2 else 2)
        cid = db().execute('INSERT INTO cases(number,name,description,stage,created) VALUES(?,?,?,?,?)',
            (f'MARE-2026-{i:06}', '<img src=x onerror=alert(1)> '+('Long investigation title ' * (8 if i == 11 else 1)),
             'Research description. ' * 80, stage, now())).lastrowid
        if stage == 3:
            db().execute("INSERT INTO history(case_id,stage,created,outcome) VALUES(?,2,?,'Done')", (cid, now()))
    db().commit()
app.run(host='127.0.0.1', port=int(os.environ.get('MARE_DASHBOARD_TEST_PORT', '8794')), use_reloader=False)
