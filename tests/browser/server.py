"""Isolated browser-test fixture server. Never imported by the production app."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if not os.environ.get('MARE_EDITOR_BROWSER_TEST') or not os.environ.get('MARE_DATA_DIR'):
    raise RuntimeError('Browser tests require an explicitly isolated data directory')
from app import app, run, db, ROOT, ensure_package, package, case
from reporting import TOKENS, current_report
from werkzeug.security import generate_password_hash
from docx import Document

with app.app_context():
    uid = run("INSERT INTO users(username,password,role,forced) VALUES(?,?,?,0)",
              ('editor-test', generate_password_hash('temporary-editor-test-123'), 'Administrator')).lastrowid
    cid = run("INSERT INTO cases(number,name,created,stage,owner,creator) VALUES('CM-TEST','Editor regression','2026',1,?,?)", (uid, uid)).lastrowid
    root = ensure_package(cid)
    initial = '# Saved report\n\nExisting **Markdown** and `code`.\n\n::: align-center\nPreserved alignment\n:::\n'
    (root/'reports/sections').mkdir(parents=True, exist_ok=True)
    (root/'reports/sections/executive_summary.md').write_text(initial)
    task_id = run("INSERT INTO tasks(case_id,title,body,created) VALUES(?,?,?,?)", (cid, 'Existing task', 'Saved task **body**', '2026')).lastrowid
    template = Document()
    for key, label in TOKENS.items():
        template.add_heading(label, 1)
        template.add_paragraph('{{ '+key+' }}')
    template_path = ROOT/'editor-test-template.docx'
    template.save(template_path)

@app.get('/__editor_test__')
def editor_fixture():
    with app.app_context():
        connection = db()
        report = package(cid)/current_report(case(cid), package(cid))
        document = Document(report) if report.exists() else None
        paragraphs = [p.text for p in document.paragraphs] if document else []
        inline_shapes = len(document.inline_shapes) if document else 0
    return dict(cid=cid, task_id=task_id, initial=initial, template=str(template_path), paragraphs=paragraphs, inline_shapes=inline_shapes)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ['MARE_EDITOR_TEST_PORT']), use_reloader=False)
