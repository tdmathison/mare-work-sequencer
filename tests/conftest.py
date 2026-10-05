import os,tempfile,shutil
os.environ['MARE_DATA_DIR']=tempfile.mkdtemp(prefix='mare-tests-')
import pytest
from app import app,db,ROOT
@pytest.fixture(autouse=True)
def isolated_state():
    with app.app_context():
        connection=db();connection.commit();connection.execute('PRAGMA foreign_keys=OFF')
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():connection.execute('DELETE FROM "'+row[0]+'"')
        connection.execute('INSERT INTO case_sequence VALUES(1,0)');connection.commit();connection.execute('PRAGMA foreign_keys=ON')
    for directory in ('cases','users','report-jobs'):shutil.rmtree(ROOT/directory,ignore_errors=True)
    yield
