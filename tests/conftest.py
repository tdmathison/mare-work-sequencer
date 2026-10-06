import os,tempfile,shutil
from pathlib import Path
os.environ['MARE_DATA_DIR']=tempfile.mkdtemp(prefix='mare-tests-')
import pytest
from app import app,db,ROOT
import report_routes
@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    def fake_pdf(source,destination):Path(destination).write_bytes(b'%PDF-1.4\n%%EOF\n')
    monkeypatch.setattr(report_routes,'convert_docx_to_pdf',fake_pdf)
    with app.app_context():
        connection=db();connection.commit();connection.execute('PRAGMA foreign_keys=OFF')
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():connection.execute('DELETE FROM "'+row[0]+'"')
        connection.execute('INSERT INTO case_sequence VALUES(1,0)');connection.commit();connection.execute('PRAGMA foreign_keys=ON')
    for directory in ('cases','users','report-jobs'):shutil.rmtree(ROOT/directory,ignore_errors=True)
    yield
