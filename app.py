from tagging import register_tags, assignments as tag_assignments, case_filter, prototype as tag_prototype
from indicators import register_indicators
from api import register_api
from backups import register_backups
from report_routes import register_reporting
from report_assets import register_assets
from analyst_tools import register_tools
from references import register_references
import shutil
import os
import sqlite3
import secrets
import functools
import json
import re
import io
import zipfile
import hashlib
import csv
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, session, redirect, render_template, abort, flash, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reporting import is_backup, OUTPUT, current_report
from mip import dated_title, title_date, create_mip, slugify, CATEGORIES, REPORT_TEMPLATE, GUIDANCE, OPTIONAL_TEMPLATES
from authorization import has_permission, initialize_roles

STAGES = ['Not started', 'Malware Analysis',
          'Packaging & Delivery', 'Completed']
APP_DIR = Path(__file__).resolve().parent
configured_data = Path(os.environ.get('MARE_DATA_DIR') or 'data').expanduser()
ROOT = (configured_data if configured_data.is_absolute()
        else APP_DIR/configured_data).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
secret = ROOT/'session.key'
if not secret.exists():
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(secrets.token_hex(32))
app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('MARE_SECRET_KEY') or secret.read_text(), MAX_CONTENT_LENGTH=100*1024*1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('MARE_SECURE_COOKIES') == '1', PERMANENT_SESSION_LIFETIME=28800)


def db():
    if 'db' not in g:
        g.db = sqlite3.connect(ROOT/'workflow.sqlite3')
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA busy_timeout=5000')
    return g.db


@app.teardown_appcontext
def close(_):
    if 'db' in g:
        g.db.close()
    if 'backup_lock_fd' in g:
        os.close(g.backup_lock_fd)


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run(sql, args=()):
    c = db().execute(sql, args)
    db().commit()
    return c


with app.app_context():
    db().executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,forced INTEGER DEFAULT 1,version INTEGER DEFAULT 1,last_login TEXT);
    CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY,number TEXT UNIQUE NOT NULL,name TEXT NOT NULL,description TEXT,stage INTEGER DEFAULT 0,created TEXT NOT NULL,owner INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,case_id INTEGER REFERENCES cases(id),body TEXT NOT NULL,author TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,case_id INTEGER REFERENCES cases(id),title TEXT NOT NULL,done INTEGER DEFAULT 0,created TEXT);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,case_id INTEGER REFERENCES cases(id),stage INTEGER,author TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT,action TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS attempts(username TEXT PRIMARY KEY,count INTEGER,window INTEGER);
    CREATE TABLE IF NOT EXISTS site_settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
    INSERT OR IGNORE INTO site_settings VALUES('sample_archive_password','infected');
    ''')
# Additive migrations preserve existing accounts, cases, and notes.
with app.app_context():
    for table, column, definition in [('tasks', 'body', "TEXT DEFAULT ''"), ('cases', 'external_system', "TEXT DEFAULT ''"), ('cases', 'external_number', "TEXT DEFAULT ''"), ('cases', 'report_path', "TEXT DEFAULT ''"), ('notes', 'title', "TEXT DEFAULT ''"), ('notes', 'include_export', 'INTEGER DEFAULT 0'), ('history', 'outcome', "TEXT DEFAULT 'Done'"), ('history', 'reason', "TEXT DEFAULT ''")]:
        if column not in [r[1] for r in db().execute(f'PRAGMA table_info({table})')]:
            db().execute(
                f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    db().executescript("""
    CREATE TABLE IF NOT EXISTS case_sequence(id INTEGER PRIMARY KEY CHECK(id=1),value INTEGER NOT NULL);
    INSERT OR IGNORE INTO case_sequence VALUES(1,0);
    CREATE TABLE IF NOT EXISTS reserved_case_numbers(number TEXT PRIMARY KEY);
    INSERT OR IGNORE INTO reserved_case_numbers SELECT number FROM cases;
    CREATE TRIGGER IF NOT EXISTS reserve_case_number AFTER INSERT ON cases BEGIN
      INSERT OR IGNORE INTO reserved_case_numbers VALUES(NEW.number);
    END;
    CREATE TRIGGER IF NOT EXISTS immutable_case_number BEFORE UPDATE OF number ON cases
      WHEN NEW.number != OLD.number BEGIN SELECT RAISE(ABORT,'System case numbers are immutable'); END;
    CREATE TABLE IF NOT EXISTS readiness(case_id INTEGER REFERENCES cases(id),category TEXT,status TEXT DEFAULT 'Pending',reason TEXT DEFAULT '',PRIMARY KEY(case_id,category));
    CREATE TABLE IF NOT EXISTS artifacts(case_id INTEGER REFERENCES cases(id),path TEXT,description TEXT DEFAULT '',usage TEXT DEFAULT '',PRIMARY KEY(case_id,path));
    CREATE TABLE IF NOT EXISTS drafts(case_id INTEGER REFERENCES cases(id),user_id INTEGER REFERENCES users(id),title TEXT,body TEXT,updated TEXT,PRIMARY KEY(case_id,user_id));
    CREATE TABLE IF NOT EXISTS deferred(case_id INTEGER REFERENCES cases(id),stage INTEGER,reason TEXT,resolved INTEGER DEFAULT 0,PRIMARY KEY(case_id,stage));
    """)
    db().commit()


with app.app_context():
    columns = {row[1] for row in db().execute('PRAGMA table_info(tasks)')}
    if 'state' not in columns:
        db().execute("ALTER TABLE tasks ADD COLUMN state TEXT DEFAULT 'Not Started'")
        db().execute("UPDATE tasks SET state=CASE WHEN done=1 THEN 'Completed' ELSE 'Not Started' END")
    if 'priority' not in columns:
        db().execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'Normal'")
    if 'autosave_minutes' not in {row[1] for row in db().execute('PRAGMA table_info(users)')}:
        db().execute('ALTER TABLE users ADD COLUMN autosave_minutes INTEGER NOT NULL DEFAULT 5')
    if 'board_view' not in {row[1] for row in db().execute('PRAGMA table_info(users)')}:
        db().execute("ALTER TABLE users ADD COLUMN board_view TEXT NOT NULL DEFAULT 'cards'")
    if 'user_uuid' not in {row[1] for row in db().execute('PRAGMA table_info(users)')}:
        db().execute('ALTER TABLE users ADD COLUMN user_uuid TEXT')
    db().execute("UPDATE users SET user_uuid=lower(hex(randomblob(16))) WHERE user_uuid IS NULL")
    db().executescript('''CREATE UNIQUE INDEX IF NOT EXISTS user_uuid_unique ON users(user_uuid);
    CREATE TRIGGER IF NOT EXISTS user_identity_new AFTER INSERT ON users WHEN NEW.user_uuid IS NULL BEGIN
    UPDATE users SET user_uuid=lower(hex(randomblob(16))),autosave_minutes=5 WHERE id=NEW.id;
    END;
    CREATE TRIGGER IF NOT EXISTS user_identity_fixed BEFORE UPDATE OF user_uuid ON users WHEN OLD.user_uuid IS NOT NULL AND NEW.user_uuid IS NOT OLD.user_uuid BEGIN SELECT RAISE(ABORT,'User identifiers are immutable'); END;''')
    case_columns = {row[1] for row in db().execute('PRAGMA table_info(cases)')}
    if 'owner_required' not in case_columns:
        db().execute('ALTER TABLE cases ADD COLUMN owner_required INTEGER NOT NULL DEFAULT 0')
    if 'creator' not in case_columns:
        db().execute('ALTER TABLE cases ADD COLUMN creator INTEGER REFERENCES users(id)')
        db().execute('ALTER TABLE cases ADD COLUMN creator_username TEXT')
        db().execute('UPDATE cases SET creator=owner,creator_username=(SELECT username FROM users WHERE id=cases.owner)')
    db().execute("UPDATE artifacts SET usage=''")
    db().commit()


def migrate_analysis_stages(connection):
    """Merge legacy stages once, preserving history and all deferred reasons."""
    with connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY)')
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT 1 FROM schema_migrations WHERE name='merged-analysis-stages'").fetchone():
            return
        for table in ('cases', 'history'):
            connection.execute(
                f'UPDATE {table} SET stage=stage-1 WHERE stage>=3')
        rows = connection.execute(
            'SELECT * FROM deferred ORDER BY case_id,stage').fetchall()
        connection.execute('DELETE FROM deferred')
        merged = {}
        for row in rows:
            stage = row['stage']-1 if row['stage'] >= 3 else row['stage']
            key = (row['case_id'], stage)
            if key in merged:
                reason, resolved = merged[key]
                merged[key] = (reason+'\n'+row['reason'],
                               min(resolved, row['resolved']))
            else:
                merged[key] = (row['reason'], row['resolved'])
        for (cid, stage), (reason, resolved) in merged.items():
            connection.execute(
                'INSERT INTO deferred VALUES(?,?,?,?)', (cid, stage, reason, resolved))
        connection.execute(
            "INSERT INTO schema_migrations VALUES('merged-analysis-stages')")


def migrate_five_stages(connection):
    mapping = {0: 0, 1: 1, 2: 1, 3: 1, 4: 2, 5: 3, 6: 4}
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT 1 FROM schema_migrations WHERE name='five-stage-workflow'").fetchone():
            return
        for table in ('cases', 'history'):
            connection.execute(
                f'UPDATE {table} SET stage=CASE stage WHEN 0 THEN 0 WHEN 1 THEN 1 WHEN 2 THEN 1 WHEN 3 THEN 1 WHEN 4 THEN 2 WHEN 5 THEN 3 WHEN 6 THEN 4 ELSE stage END')
        rows = connection.execute(
            'SELECT * FROM deferred ORDER BY case_id,stage').fetchall()
        connection.execute('DELETE FROM deferred')
        merged = {}
        for row in rows:
            key = (row['case_id'], mapping[row['stage']])
            reason, resolved = merged.get(key, ('', 1))
            merged[key] = ((reason+'\n' if reason else '') +
                           row['reason'], min(resolved, row['resolved']))
        for (cid, stage), (reason, resolved) in merged.items():
            connection.execute(
                'INSERT INTO deferred VALUES(?,?,?,?)', (cid, stage, reason, resolved))
        connection.execute(
            "INSERT INTO schema_migrations VALUES('five-stage-workflow')")


def migrate_four_stages(connection):
    mapping = {0: 0, 1: 1, 2: 1, 3: 2, 4: 3}
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT 1 FROM schema_migrations WHERE name='four-stage-workflow'").fetchone():
            return
        for table in ('cases', 'history'):
            connection.execute(
                f'UPDATE {table} SET stage=CASE stage WHEN 0 THEN 0 WHEN 1 THEN 1 WHEN 2 THEN 1 WHEN 3 THEN 2 WHEN 4 THEN 3 ELSE stage END')
        rows = connection.execute(
            'SELECT * FROM deferred ORDER BY case_id,stage').fetchall()
        connection.execute('DELETE FROM deferred')
        merged = {}
        for row in rows:
            key = (row['case_id'], mapping[row['stage']])
            reason, resolved = merged.get(key, ('', 1))
            merged[key] = ((reason+'\n' if reason else '') +
                           row['reason'], min(resolved, row['resolved']))
        for (cid, stage), (reason, resolved) in merged.items():
            connection.execute(
                'INSERT INTO deferred VALUES(?,?,?,?)', (cid, stage, reason, resolved))
        connection.execute(
            "INSERT INTO schema_migrations VALUES('four-stage-workflow')")


with app.app_context():
    migrate_analysis_stages(db())
    migrate_five_stages(db())
    migrate_four_stages(db())
    initialize_roles(db())
    if not db().execute("SELECT 1 FROM schema_migrations WHERE name='one-minute-autosave'").fetchone():
        db().execute('UPDATE users SET autosave_minutes=1 WHERE autosave_minutes=5')
        db().execute("INSERT INTO schema_migrations VALUES('one-minute-autosave')")
        db().commit()
    if not db().execute("SELECT 1 FROM schema_migrations WHERE name='five-minute-autosave-default'").fetchone():
        db().execute('UPDATE users SET autosave_minutes=5 WHERE autosave_minutes=1')
        db().execute("INSERT INTO schema_migrations VALUES('five-minute-autosave-default')")
        db().commit()


def ensure_package(cid):
    root = package(cid)
    if not root.exists():
        create_mip(root.parent, 'mip', 'SAFE')
    # Existing assets are retained. New cases use only the simplified layout.
    for folder in CATEGORIES:
        (root/folder).mkdir(exist_ok=True)
    from mip import clean_mapping_placeholders
    clean_mapping_placeholders(root)
    marker = root/'.layout-v2'
    if not marker.exists():
        import shutil
        moves = {'indicators': 'iocs', 'decoders': 'scripts', 'configs': 'supporting/configs', 'network': 'supporting/network',
                 'artifacts': 'supporting/artifacts', 'references': 'supporting/references', 'detections': 'supporting/detections'}
        for old, new in moves.items():
            source = root/old
            if not source.exists():
                continue
            for original in source.rglob('*'):
                if original.is_file() and not original.is_symlink():
                    target = root/new/original.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        shutil.copy2(original, target)
        marker.write_text(
            'Simplified deliverable layout; original legacy folders retained.\n')
    return root


def package_files(cid):
    root = ensure_package(cid)
    return [{'path': p.relative_to(root).as_posix(), 'dir': p.is_dir(), 'size': p.stat().st_size if p.is_file() else 0} for p in sorted(root.rglob('*')) if not p.is_symlink() and not is_backup(p.relative_to(root))]


def raw_package_file(rel, include_samples=False):
    # RAW includes working content in the MIP structure, never backups or symlinks.
    is_sample = rel.startswith('samples/')
    return rel.split('/')[0] in CATEGORIES and not is_backup(rel) and (not is_sample or (include_samples and Path(rel).suffix.lower() == '.zip'))


def deliverable_file(cid, rel):
    if not raw_package_file(rel):
        return False
    if rel.startswith('samples/'):
        return False
    if rel.startswith('reports/') and Path(rel).suffix.lower() == '.docx' and rel == current_report(case(cid), package(cid)):
        return False
    if rel.startswith('reports/sections/'):
        return False
    if rel.startswith('reports/') and Path(rel).suffix.lower() == '.md':
        return False
    p = package(cid)/rel
    if rel in OPTIONAL_TEMPLATES and p.read_text(errors='replace').strip() == OPTIONAL_TEMPLATES[rel].strip():
        return False
    return True


def readiness(cid):
    root = ensure_package(cid)
    saved = {r['category']: dict(r) for r in db().execute(
        'SELECT * FROM readiness WHERE case_id=?', (cid,))}
    result = []
    for category, label in CATEGORIES.items():
        r = saved.get(category, {'status': 'Pending', 'reason': ''})
        count = sum(1 for p in (root/category).rglob('*') if p.is_file() and not p.is_symlink() and (p.suffix.lower()
                    == '.zip' if category == 'samples' else deliverable_file(cid, p.relative_to(root).as_posix())))
        if r['status'] == 'Populated' and not count:
            r['status'] = 'Pending'
        result.append(dict(category=category, label=label,
                      status=r['status'], reason=r['reason'], count=count))
    return result


def completion_items(cid):
    root = ensure_package(cid)
    c = case(cid)
    items = []
    for r in readiness(cid):
        if r['category'] == 'reports' and r['status'] != 'Populated':
            items.append({'message': 'Reports needs review. Mark Reports as Populated after reviewing the latest document.',
                         'action': 'Review Reports', 'target': 'readiness-reports', 'tab': 'package'})
        elif r['status'] == 'Pending':
            items.append({'message': r['label']+': Pending. Review its content and mark it Populated, or choose Not applicable with a reason.',
                         'action': 'Review '+r['label'], 'target': 'readiness-'+r['category'], 'tab': 'package'})
    report = root/'reports/malware-analysis-report.md'
    word = root/current_report(c, root)
    if not (word.is_file() and word.stat().st_size > 0) and (not report.exists() or not report.read_text(errors='replace').strip() or report.read_text(errors='replace').strip() == REPORT_TEMPLATE.strip()):
        items.append({'message': 'A completed analysis report is missing. Complete the Markdown report or generate/upload the Word report.',
                     'action': 'Open Report', 'target': 'panel-report', 'tab': 'report'})
    for t in db().execute('SELECT title FROM tasks WHERE case_id=? AND done=0', (cid,)):
        items.append({'message': 'Open task: '+t['title']+'. Complete or close this task.',
                     'action': 'Open Tasks', 'target': 'case-tasks', 'tab': 'tasks'})
    for d in db().execute('SELECT stage FROM deferred WHERE case_id=? AND resolved=0', (cid,)):
        items.append({'message': 'Deferred work remains for ' +
                     STAGES[d['stage']]+'. Resolve it in the stage history.', 'action': 'Open deferred work', 'target': 'stage-history', 'tab': 'workbench'})
    if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
        items.append({'message': 'Wait for report generation to finish.',
                     'action': 'Open report progress', 'target': 'panel-report', 'tab': 'report'})
    return items


def review_issues(cid): return [item['message']
                                for item in completion_items(cid)]


def audit(action): run('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',
                       (g.user['username'] if g.user else 'system', action, now()))


API_HITS = {}


@app.before_request
def protect():
    if request.method == 'POST' and os.name == 'posix':
        import fcntl
        fd = os.open(ROOT/'.backup.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if request.endpoint in (
                'database_backup', 'api.api_database_backup') else fcntl.LOCK_SH)
        except Exception:
            os.close(fd)
            raise
        g.backup_lock_fd = fd
    if request.endpoint in ('backup_import', 'api.api_import_backup'):
        request.max_content_length = 1024*1024*1024
    g.user = None
    if request.path.startswith('/api/v1/'):
        authorization = request.headers.get('Authorization', '')
        scheme, separator, token = authorization.partition(' ')
        if not separator or scheme.lower() != 'bearer' or not token:
            return {'error': 'A bearer token is required.'}, 401, {'WWW-Authenticate': 'Bearer'}
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        user = db().execute('SELECT api_tokens.id AS api_token_id,users.* FROM api_tokens JOIN users ON users.id=api_tokens.user_id WHERE api_tokens.token_hash=? AND api_tokens.revoked IS NULL AND (api_tokens.expires IS NULL OR api_tokens.expires>?)', (token_hash, now())).fetchone()
        if not user or not user['active']:
            return {'error': 'Invalid, expired, or revoked bearer token.'}, 401, {'WWW-Authenticate': 'Bearer'}
        if user['forced']:
            return {'error': 'Change the temporary password in the web account before using the API.'}, 403
        g.user = user
        g.api_token_id = user['api_token_id']
        import time
        limit = int(os.environ.get('MARE_API_RATE_LIMIT', '600'))
        minute = int(time.time()//60)
        window, count = API_HITS.get(g.api_token_id, (minute, 0))
        count = count+1 if window == minute else 1
        API_HITS[g.api_token_id] = (minute, count)
        if limit > 0 and count > limit:
            return {'error': 'Rate limit exceeded.'}, 429, {'Retry-After': '60'}
        run('UPDATE api_tokens SET last_used=? WHERE id=?', (now(), g.api_token_id))
        return
    if session.get('uid'):
        u = db().execute('SELECT * FROM users WHERE id=?',
                         (session['uid'],)).fetchone()
        if u and u['active'] and u['version'] == session.get('version'):
            g.user = u
        else:
            session.clear()
    if request.endpoint == 'static':
        return
    if request.method == 'POST' and (not session.get('csrf') or not secrets.compare_digest(session['csrf'], request.form.get('csrf', ''))):
        abort(403)
    if request.endpoint not in ('login', 'static'):
        if not g.user:
            return redirect('/login')
        if g.user['forced'] and request.endpoint not in ('account', 'logout'):
            return redirect('/account')


@app.before_request
def enforce_case_stage():
    if request.path.startswith('/api/v1/'):
        return
    cid = (request.view_args or {}).get('cid')
    if cid is None or request.method != 'POST' or not g.user:
        return
    c = case(cid)
    message = None
    if request.endpoint in ('assign_case_owner', 'backup_single_export', 'delete_case'):
        return
    if c['owner_required'] and not c['owner_active'] and request.endpoint != 'detail' and not (request.endpoint == 'progress' and c['stage'] == 0):
        return {'error': 'Assign an active owner in Case details to resume this case at its current stage.'}, 409
    if request.endpoint == 'archive':
        if c['stage'] not in (2, 3):
            message = 'MIP ZIP generation is available during Packaging & Delivery or Completed.'
    elif request.endpoint not in ('progress', 'reopen_case', 'delete_case'):
        if c['stage'] == 0 and request.endpoint != 'detail':
            message = 'Start analysis before adding or editing case content.'
        elif c['stage'] == 3:
            message = 'Reopen this case before editing its content.'
    if message:
        return {'error': message}, 409


@app.context_processor
def context():
    session.setdefault('csrf', secrets.token_urlsafe(32))
    return dict(user=g.user, csrf=session['csrf'], stages=STAGES, categories=CATEGORIES, guidance=GUIDANCE, active_users=db().execute("SELECT id,username FROM users WHERE active=1 ORDER BY username").fetchall())


def admin(f):
    @functools.wraps(f)
    def wrapped(*a, **kw):
        if not g.user or g.user['role'] != 'Administrator':
            abort(403)
        return f(*a, **kw)
    return wrapped


CASE_QUERY = "SELECT c.*,COALESCE(cr.username,c.creator_username,'Unknown') AS creator_name,ow.username AS owner_name,ow.active AS owner_active,CASE WHEN c.stage IN (0,3) OR (c.owner_required=1 AND COALESCE(ow.active,0)=0) THEN 1 ELSE 0 END AS workspace_locked FROM cases c LEFT JOIN users cr ON cr.id=c.creator LEFT JOIN users ow ON ow.id=c.owner"


def assigned_owner(form, current=None):
    value = form.get('owner_id', str(current or '')).strip()
    if not value:
        return None
    if not value.isdigit() or not db().execute('SELECT 1 FROM users WHERE id=? AND active=1', (value,)).fetchone():
        abort(400)
    return int(value)


def case(cid):
    c = db().execute(CASE_QUERY+' WHERE c.id=?', (cid,)).fetchone()
    if not c:
        abort(404)
    return c


def package(cid): return ROOT/'cases'/str(cid)/'mip'


def sample_archive_password():
    row = db().execute(
        "SELECT value FROM site_settings WHERE name='sample_archive_password'").fetchone()
    return row['value'] if row else 'infected'


def safe_path(cid, rel):
    if is_backup(rel):
        abort(404)
    root = package(cid).resolve()
    p = (root/rel).resolve()
    if p == root or root not in p.parents or any(x.is_symlink() for x in [p, *p.parents]):
        abort(400)
    return p


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        import time
        username = request.form.get('username', '').strip()
        stamp = int(time.time())
        a = db().execute('SELECT * FROM attempts WHERE username=?', (username,)).fetchone()
        if a and stamp-a['window'] < 900 and a['count'] >= 10:
            abort(429)
        u = db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if u and u['active'] and check_password_hash(u['password'], request.form.get('password', '')):
            session.clear()
            session.update(uid=u['id'], version=u['version'],
                           csrf=secrets.token_urlsafe(32))
            session.permanent = True
            run('DELETE FROM attempts WHERE username=?', (username,))
            run('UPDATE users SET last_login=? WHERE id=?', (now(), u['id']))
            return redirect('/account' if u['forced'] else '/')
        count = a['count']+1 if a and stamp-a['window'] < 900 else 1
        run('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',
            (username, count, a['window'] if count > 1 else stamp))
        flash('Invalid username or password.')
    return render_template('login.html')


@app.post('/logout')
def logout(): session.clear(); return redirect('/login')


@app.route('/account', methods=['GET', 'POST'])
def account():
    if request.method == 'POST':
        p = request.form.get('password', '')
        if not check_password_hash(g.user['password'], request.form.get('current', '')):
            flash('Current password is incorrect.')
        elif len(p) < 12 or p != request.form.get('confirm'):
            flash('Use at least 12 characters and matching passwords.')
        else:
            run('UPDATE users SET password=?,forced=0,version=version+1 WHERE id=?',
                (generate_password_hash(p), g.user['id']))
            session['version'] += 1
            audit('Changed own password')
            flash('Password changed.')
            return redirect('/')
    password = sample_archive_password(
    ) if g.user['role'] == 'Administrator' else None
    return render_template('account.html', sample_archive_password=password)


@app.post('/account/autosave')
def save_autosave_settings():
    raw = request.form.get('autosave_minutes', '').strip()
    try:
        minutes = int(raw)
        if minutes < 1 or minutes > 9223372036854775807:
            raise ValueError()
    except ValueError:
        flash('Enter a positive whole number of minutes.')
        return redirect('/account')
    run('UPDATE users SET autosave_minutes=? WHERE id=?',
        (minutes, g.user['id']))
    flash('Autosave interval saved. It applies when case pages are opened or refreshed.')
    return redirect('/account')


@app.post('/account/board-view')
def save_board_view():
    view = request.form.get('board_view')
    if view not in ('cards', 'table'):
        flash('Choose a valid board view.')
        return redirect('/account')
    run('UPDATE users SET board_view=? WHERE id=?', (view, g.user['id']))
    flash('Default board view saved.')
    return redirect('/account')


@app.post('/account/sample-password')
@admin
def save_sample_archive_password():
    password = request.form.get('sample_archive_password', '')
    if not password or len(password) > 256 or '\x00' in password:
        flash('Enter a sample archive password of 1–256 characters.')
        return redirect('/account')
    run("INSERT INTO site_settings(name,value) VALUES('sample_archive_password',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (password,))
    audit('Changed the sample archive password')
    flash('Sample archive password saved. It applies to future uploads only.')
    return redirect('/account')


@app.get('/')
def dashboard():
    selected = request.args.getlist('tag')
    if len(selected) > 100 or any(not v.isdigit() or len(v) > 10 for v in selected): abort(400)
    selected = sorted(set(map(int, selected)))
    match = request.args.get('match', 'any')
    if match not in ('any', 'all'): abort(400)
    can_read_tags = has_permission(g.user, 'tags:read', db())
    if selected and not can_read_tags: abort(403)
    if selected and tag_prototype(db()): abort(503, 'Prototype tag migration required.')
    query = request.args.get('q', '').strip()
    sql, args = case_filter(selected, match)
    cases = [dict(c) for c in db().execute(CASE_QUERY+" WHERE (instr(lower(c.name),?)>0 OR instr(lower(c.number),?)>0 OR instr(lower(coalesce(c.description,'')),?)>0)"+sql+' ORDER BY c.id DESC', [query.lower()]*3+args)]
    tag_map = {}
    if can_read_tags and not tag_prototype(db()):
        for tag in tag_assignments(db()): tag_map.setdefault(tag['case_id'], []).append(tag)
    for c in cases:
        c['readiness'] = readiness(c['id'])
    view = request.args.get('view')
    if view not in ('cards', 'table'):
        view = g.user['board_view']
    selected_labels = {t['id']: t['name'] for rows in tag_map.values() for t in rows if t['id'] in selected}
    if selected and not tag_prototype(db()):
        selected_labels.update({r['id']:r['name'] for r in db().execute('SELECT id,name FROM tags WHERE id IN ('+','.join('?' for _ in selected)+')', selected)})
    return render_template('dashboard.html', selected_tag_labels=selected_labels, cases=cases, view=view, board_query=query, selected_tags=selected, tag_match=match, board_tags=tag_map)


def metrics_data():
    users = db().execute('''SELECT u.id,u.username,u.active,
      (SELECT count(*) FROM cases WHERE creator=u.id) AS created_count,
      (SELECT count(*) FROM cases WHERE owner=u.id) AS assigned_count,
      (SELECT count(*) FROM cases WHERE owner=u.id AND stage IN (1,2)) AS progress_count,
      (SELECT count(*) FROM cases WHERE owner=u.id AND stage=3) AS completed_count
      FROM users u ORDER BY u.username''').fetchall()
    stage_counts = {row['stage']: row['count'] for row in db().execute(
        'SELECT stage,count(*) AS count FROM cases GROUP BY stage')}
    chart_data = {
        'completed': [{'label': user['username'], 'value': user['completed_count']} for user in users if user['completed_count']],
        'stages': [{'label': label, 'value': sum(stage_counts.get(stage, 0) for stage in stage_values)} for label, stage_values in [('Not started', (0,)), ('In progress', (1, 2)), ('Completed', (3,))]],
    }
    return users, chart_data


@app.get('/metrics')
def metrics():
    users, chart_data = metrics_data()
    return render_template('metrics.html', metrics_users=users, chart_data=chart_data)


def external_reference(form):
    system = form.get('external_system', '').strip()
    number = form.get('external_number', '').strip()
    if system not in ('', 'Vortex', 'XSIAM', 'JIRA') or len(number) > 200:
        return None
    if bool(system) != bool(number):
        return None
    return system, number


@app.get('/cases/new')
def create_case_page(): return render_template('create_case.html', values={
    'name': datetime.now().strftime('%Y%m%d')+': '})


def allocate_case_number(connection):
    sequence = connection.execute(
        'SELECT value FROM case_sequence WHERE id=1').fetchone()[0]
    while True:
        sequence += 1
        number = f'MARE-{datetime.now(timezone.utc).year}-{sequence:06d}'
        if not connection.execute('SELECT 1 FROM reserved_case_numbers WHERE number=?', (number,)).fetchone():
            break
    connection.execute(
        'UPDATE case_sequence SET value=? WHERE id=1', (sequence,))
    return number


@app.post('/cases')
def new_case():
    title = request.form.get('name', '').strip()
    reference = external_reference(request.form)
    if title:
        title = dated_title(title)
    if not title or len(title) > 200 or reference is None:
        flash('Enter a case name. For an external reference, provide both its system and number.')
        return render_template('create_case.html', values=request.form), 400
    system, external = reference
    owner = assigned_owner(request.form)
    connection = db()
    connection.execute('BEGIN IMMEDIATE')
    try:
        number = allocate_case_number(connection)
        cid = connection.execute('INSERT INTO cases(number,name,description,created,owner,external_system,external_number,creator,creator_username,owner_required) VALUES(?,?,?,?,?,?,?,?,?,1)',
                                 (number, title, request.form.get('description', ''), now(), owner, system, external, g.user['id'], g.user['username'])).lastrowid
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    ensure_package(cid)
    audit('Created case '+number)
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/owner')
def assign_case_owner(cid):
    c = case(cid)
    owner = assigned_owner(request.form)
    run('UPDATE cases SET owner=? WHERE id=?', (owner, cid))
    audit('Updated case owner '+c['number'])
    return redirect(f'/cases/{cid}?tab=workbench#case-details')


@app.route('/cases/<int:cid>', methods=['GET', 'POST'])
def detail(cid):
    c = case(cid)
    if request.method == 'POST':
        title = request.form.get('name', '').strip()
        reference = external_reference(request.form)
        if not title or len(title) > 200 or reference is None:
            flash('Enter a case name and a complete optional external reference.')
            return redirect(request.path)
        system, external = reference
        run('UPDATE cases SET name=?,description=?,external_system=?,external_number=?,owner=? WHERE id=?', (title,
            request.form.get('description', ''), system, external, assigned_owner(request.form, c['owner']), cid))
        audit('Updated case details '+c['number'])
        return redirect(request.path)
    draft = db().execute('SELECT * FROM drafts WHERE case_id=? AND user_id=?',
                         (cid, g.user['id'])).fetchone()
    root = package(cid)
    files = package_files(cid)
    report_path = current_report(c, root)
    export_files = [f for f in files if not f['dir']
                    and deliverable_file(cid, f['path'])]
    sample_archive_paths = [f['path'] for f in files if not f['dir'] and f['path'].startswith(
        'samples/') and f['path'].lower().endswith('.zip')]
    package_view_files = list(export_files)
    package_view_files.extend(f for f in files if not f['dir'] and f['path'].startswith(
        'samples/') and all(existing['path'] != f['path'] for existing in package_view_files))
    tracked_word = next(
        (f for f in files if f['path'] == report_path and not f['dir']), None)
    if tracked_word and all(f['path'] != report_path for f in package_view_files):
        package_view_files.append(tracked_word)
    report_output_paths = [report_path, Path(
        report_path).with_suffix('.pdf').as_posix()]
    return render_template('case.html', manual_sections=report_helpers['manual'](cid), word_report_exists=(root/report_path).exists(), word_report_path=report_path, report_output_paths=report_output_paths, package_view_files=package_view_files, sample_archive_paths=sample_archive_paths, c=c, files=files, ready=readiness(cid), export_files=export_files, raw_files=[f for f in files if not f['dir'] and raw_package_file(f['path'])], issues=review_issues(cid), completion=completion_items(cid), draft=draft, notes=db().execute('SELECT * FROM notes WHERE case_id=? ORDER BY id DESC', (cid,)).fetchall(), tasks=db().execute('SELECT * FROM tasks WHERE case_id=? ORDER BY id', (cid,)).fetchall(), history=db().execute('SELECT * FROM history WHERE case_id=? ORDER BY id DESC', (cid,)).fetchall(), artifacts={r['path']: r for r in db().execute('SELECT * FROM artifacts WHERE case_id=?', (cid,))}, deferred=db().execute('SELECT * FROM deferred WHERE case_id=? AND resolved=0', (cid,)).fetchall())


@app.post('/cases/<int:cid>/delete')
def delete_case(cid):
    c = case(cid)
    if request.form.get('confirm_number', '').strip() != c['number']:
        flash('Enter the exact system case number to confirm deletion.')
        return redirect(f'/cases/{cid}#destructive-commands')
    connection = db()
    connection.execute('BEGIN IMMEDIATE')
    folder = ROOT/'cases'/str(cid)
    staged = ROOT/'cases'/('.deleting-'+secrets.token_hex(16))
    moved = False
    try:
        if connection.execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
            connection.rollback()
            flash('Wait for report generation to finish before deleting this case.')
            return redirect(f'/cases/{cid}#destructive-commands')
        if folder.exists():
            folder.rename(staged)
            moved = True
        for table in ('notes', 'tasks', 'history', 'readiness', 'artifacts', 'drafts', 'deferred', 'report_jobs', 'report_images', 'figure_sequence', 'indicator_tables', 'indicator_sections', 'indicator_table_legacy', 'reference_tables'):
            connection.execute(f'DELETE FROM {table} WHERE case_id=?', (cid,))
        connection.execute('DELETE FROM cases WHERE id=?', (cid,))
        connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',
                           (g.user['username'], 'Deleted case '+c['number'], now()))
        connection.commit()
    except Exception:
        connection.rollback()
        if moved:
            staged.rename(folder)
        raise
    if moved:
        shutil.rmtree(staged)
    flash('Case '+c['number'] +
          ' deleted. Its system case number remains reserved.')
    return redirect('/')


@app.post('/cases/<int:cid>/stage')
def progress(cid):
    c = case(cid)
    try:
        expected = int(request.form['expected'])
    except (KeyError, ValueError):
        abort(400)
    outcome = request.form.get('outcome', 'Done')
    reason = request.form.get('reason', '').strip()
    if outcome not in ('Done', 'No applicable work', 'Deferred'):
        abort(400)
    if outcome != 'Done' and not reason:
        flash('Add a short reason for skipped or deferred work.')
        return redirect(f'/cases/{cid}')
    if c['stage'] != expected:
        flash('Stage changed. Refresh and retry.')
        return redirect(f'/cases/{cid}')
    if expected == 0 and (not c['owner'] or not c['owner_active']):
        flash('Assign an active owner in Case details before starting analysis.')
        return redirect(f'/cases/{cid}#case-details')
    if expected == 0:
        outcome = 'Started'
        reason = ''
    if expected == len(STAGES)-2:
        blockers = review_issues(cid)
        if blockers:
            flash(
                f'Completion blocked: {len(blockers)} outstanding actions. See the completion checklist below.')
            audit(f'Case {cid}: completion blocked — ' + '; '.join(blockers))
            return redirect(f'/cases/{cid}?tab=review#completion-review')
    if 0 <= expected < len(STAGES)-1:
        connection = db()
        cursor = connection.execute(
            'UPDATE cases SET stage=stage+1 WHERE id=? AND stage=?', (cid, expected))
        if cursor.rowcount:
            connection.execute('INSERT INTO history(case_id,stage,author,created,outcome,reason) VALUES(?,?,?,?,?,?)',
                               (cid, expected, g.user['username'], now(), outcome, reason))
            if outcome == 'Deferred':
                connection.execute(
                    'INSERT OR REPLACE INTO deferred VALUES(?,?,?,0)', (cid, expected, reason))
        connection.commit()
        audit(f'Case {cid}: {outcome} — {STAGES[expected]}')
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/reopen')
def reopen_case(cid):
    c = case(cid)
    if c['stage'] != 3:
        return {'error': 'Only completed cases can be reopened.'}, 409
    with db():
        db().execute('UPDATE cases SET stage=1 WHERE id=? AND stage=3', (cid,))
        db().execute('INSERT INTO history(case_id,stage,author,created,outcome,reason) VALUES(?,?,?,?,?,?)',
                     (cid, 3, g.user['username'], now(), 'Reopened', 'Returned to Malware Analysis'))
    audit(f'Reopened case {cid}')
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/deferred/<int:stage>')
def resolve_deferred(cid, stage):
    case(cid)
    run('UPDATE deferred SET resolved=1 WHERE case_id=? AND stage=?', (cid, stage))
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/readiness')
def set_readiness(cid):
    case(cid)
    category = request.form.get('category')
    status = request.form.get('status')
    reason = request.form.get('reason', '').strip()
    if category not in CATEGORIES or status not in ('Pending', 'Populated', 'Not applicable'):
        abort(400)
    if category == 'reports' and status == 'Not applicable':
        flash('A report is required for every MIP.')
        return redirect(f'/cases/{cid}')
    reason = ''
    root = ensure_package(cid)
    if status == 'Populated' and not any(p.is_file() for p in (root/category).rglob('*')):
        flash('Add content before marking this category populated.')
        return redirect(f'/cases/{cid}')
    run('INSERT OR REPLACE INTO readiness VALUES(?,?,?,?)',
        (cid, category, status, reason))
    audit(f'Case {cid}: {category} {status}')
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/draft')
def save_draft(cid):
    case(cid)
    title = request.form.get('title', '')
    body = request.form.get('body', '')
    run('INSERT OR REPLACE INTO drafts VALUES(?,?,?,?,?)',
        (cid, g.user['id'], title, body, now()))
    return {'saved': True, 'updated': now()}


@app.post('/cases/<int:cid>/notes')
def notes(cid):
    case(cid)
    body = request.form.get('body', '').strip()
    if body:
        run('INSERT INTO notes(case_id,body,author,created,title,include_export) VALUES(?,?,?,?,?,?)', (cid, body,
            g.user['username'], now(), request.form.get('title', '').strip(), int(request.form.get('include_export') == '1')))
        run('DELETE FROM drafts WHERE case_id=? AND user_id=?',
            (cid, g.user['id']))
        if request.form.get('include_export') == '1':
            mark_pending(cid, 'reports/reverse-engineering-notes.md')
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/notes/<int:nid>')
def edit_note(cid, nid):
    case(cid)
    previous = db().execute(
        'SELECT include_export FROM notes WHERE id=? AND case_id=?', (nid, cid)).fetchone()
    if previous and (previous['include_export'] or request.form.get('include_export') == '1'):
        mark_pending(cid, 'reports/reverse-engineering-notes.md')
    if request.form.get('body', '').strip():
        run('UPDATE notes SET title=?,body=?,include_export=? WHERE id=? AND case_id=?', (request.form.get(
            'title', ''), request.form['body'], int(request.form.get('include_export') == '1'), nid, cid))
    return redirect(f'/cases/{cid}')


def task_fields():
    name = request.form.get('name', request.form.get('title', '')).strip()
    description = request.form.get('description', request.form.get('body', ''))
    priority = request.form.get('priority', 'Normal')
    state = request.form.get('state', 'Not Started')
    if not name or len(name) > 200 or len(description) > 20000 or priority not in ('Low', 'Normal', 'High', 'Critical') or state not in ('Not Started', 'In Progress', 'Completed'):
        abort(400)
    return name, description, priority, state


@app.post('/cases/<int:cid>/tasks')
def tasks(cid):
    case(cid)
    name, description, priority, _ = task_fields()
    task = run("INSERT INTO tasks(case_id,title,body,priority,state,done,created) VALUES(?,?,?,?,'Not Started',0,?)",
               (cid, name, description, priority, now()))
    for image in re.findall(r'assets/(report-image-[a-f0-9]{32}\.png)', description):
        run("UPDATE report_images SET section=? WHERE case_id=? AND name=? AND section='task-draft'",
            (f'task-{task.lastrowid}', cid, image))
    return redirect(f'/cases/{cid}?tab=tasks')


@app.post('/cases/<int:cid>/tasks/<int:tid>/edit')
def edit_task(cid, tid):
    case(cid)
    name, description, priority, state = task_fields()
    run('UPDATE tasks SET title=?,body=?,priority=?,state=?,done=? WHERE id=? AND case_id=?',
        (name, description, priority, state, int(state == 'Completed'), tid, cid))
    return redirect(f'/cases/{cid}?tab=tasks')


@app.post('/cases/<int:cid>/tasks/<int:tid>')
def toggle(cid, tid):
    case(cid)
    run("UPDATE tasks SET state=CASE WHEN done=1 THEN 'Not Started' ELSE 'Completed' END,done=1-done WHERE id=? AND case_id=?", (tid, cid))
    return redirect(f'/cases/{cid}?tab=tasks')


@app.post('/cases/<int:cid>/markdown-preview')
def markdown_preview(cid):
    case(cid)
    text = request.form.get('text', '')
    if len(text) > 100000:
        abort(413)
    from markdown_support import markdown_parser
    import html
    renderer = markdown_parser()

    def image(tokens, index, *args):
        token = tokens[index]
        source = token.attrGet('src') or ''
        if re.fullmatch(r'assets/report-image-[a-f0-9]{32}\.png', source):
            return '<img src="/cases/'+str(cid)+'/report-images/'+source.split('/')[-1]+'" alt="'+html.escape(token.content, quote=True)+'">'
        return '<span>'+html.escape(token.content)+'</span>'
    renderer.renderer.rules['image'] = image
    return {'html': renderer.render(text)}


@app.post('/cases/<int:cid>/mip')
def scaffold(cid):
    case(cid)
    ensure_package(cid)
    return redirect(f'/cases/{cid}')


@app.route('/cases/<int:cid>/file', methods=['GET', 'POST'])
def file(cid):
    case(cid)
    rel = request.values.get('path', '')
    p = safe_path(cid, rel)
    if not p.is_file():
        abort(404)
    editable = p.suffix.lower() in ('.md', '.txt', '.json', '.csv', '.yml', '.yaml',
                                    '.yar', '.sigma', '.py', '.sh', '.ps1') and p.stat().st_size < 1024*1024
    if request.method == 'POST':
        if not editable:
            abort(400)
        content = request.form.get('content', '')
        if p.suffix == '.json':
            try:
                json.loads(content)
            except ValueError:
                flash('Invalid JSON; file was not saved.')
                return redirect(request.url)
        p.write_text(content, encoding='utf-8')
        mark_pending(cid, rel)
        audit(f'Edited case {cid}: {rel}')
        flash('Saved.')
        return redirect(f'/cases/{cid}')
    if request.args.get('download') or not editable:
        return send_file(p, as_attachment=True)
    return render_template('file.html', c=case(cid), cid=cid, path=rel, content=p.read_text(encoding='utf-8', errors='replace'))


@app.post('/cases/<int:cid>/upload')
def upload(cid):
    case(cid)
    folder = request.form.get('category') or request.form.get('folder', '')
    if folder not in CATEGORIES:
        abort(400)
    ensure_package(cid)
    f = request.files.get('file')
    name = secure_filename(f.filename if f else '')
    if not name:
        abort(400)
    relative_name = name
    if folder == 'samples':
        raw = f.read(100*1024*1024+1)
        if len(raw) > 100*1024*1024:
            abort(413)
        relative_name = name+'.zip'
        target = safe_path(cid, folder+'/'+relative_name)
        if target.exists():
            flash('A sample with that name already exists. Rename it before uploading.')
            return redirect(f'/cases/{cid}')
        import pyzipper
        out = tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
        try:
            with pyzipper.AESZipFile(out, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as archive:
                archive.setpassword(sample_archive_password().encode('utf-8'))
                archive.writestr(name, raw)
            out.seek(0)
            with target.open('xb') as destination:
                shutil.copyfileobj(out, destination)
        finally:
            out.close()
    else:
        target = safe_path(cid, folder+'/'+relative_name)
        if target.exists():
            flash('A file with that name already exists. Rename it before uploading.')
            return redirect(f'/cases/{cid}')
        with target.open('xb') as out:
            f.save(out)
    run('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)', (cid, folder +
        '/'+relative_name, request.form.get('description', '').strip(), ''))
    mark_pending(cid, folder+'/'+relative_name)
    audit(f'Uploaded case {cid}: {folder}/{relative_name}')
    if request.form.get('ajax') == '1':
        return {'saved': True, 'path': folder+'/'+relative_name}
    flash('Asset added to '+folder+'/')
    return redirect(f'/cases/{cid}')


def mark_pending(cid, rel):
    category = rel.split('/')[0]
    if category in CATEGORIES:
        run("INSERT OR REPLACE INTO readiness VALUES(?,?,'Pending','Content changed; review this category.')", (cid, category))


@app.post('/cases/<int:cid>/artifact')
def artifact_description(cid):
    case(cid)
    rel = request.form.get('path', '')
    p = safe_path(cid, rel)
    if not p.is_file():
        abort(404)
    run('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)',
        (cid, rel, request.form.get('description', ''), ''))
    return redirect(f'/cases/{cid}')


@app.post('/cases/<int:cid>/archive')
def archive(cid):
    c = case(cid)
    root = ensure_package(cid)
    issues = review_issues(cid)
    archive_type = request.form.get('archive_type', 'standard')
    if archive_type not in ('standard', 'raw'):
        abort(400)
    if issues and request.form.get('acknowledge') != '1':
        flash('Resolve pending items or acknowledge them before export.')
        return redirect(f'/cases/{cid}')
    report = root/'reports/malware-analysis-report.md'
    word = root/current_report(c, root)
    if not (word.is_file() and word.stat().st_size > 0) and (not report.exists() or not report.read_text(errors='replace').strip() or report.read_text(errors='replace').strip() == REPORT_TEMPLATE.strip()):
        flash('A completed analysis report is required.')
        return redirect(f'/cases/{cid}')
    if archive_type == 'standard' and not (word.is_file() and word.stat().st_size > 0):
        flash('Generate or upload the Word report before downloading the Standard archive.')
        return redirect(f'/cases/{cid}?tab=report')
    include_samples = request.form.get('include_samples') == '1'
    out, name = backup_helpers['case_backup'](cid, include_samples=include_samples) if archive_type == 'raw' else build_archive(
        cid, archive_type, include_samples=include_samples)
    audit(f'Exported MIP for case {cid}')
    response = send_file(out, as_attachment=True,
                         download_name=name+'.zip', mimetype='application/zip')
    response.call_on_close(out.close)
    return response


def build_archive(cid, archive_type, include_samples=False):
    c = case(cid)
    root = ensure_package(cid)
    issues = review_issues(cid)
    title = re.sub(r'^\d{8}:\s*', '', c['name'])
    name = title_date(c['name'])+'-MIP-'+slugify(title)+('-RAW' if archive_type ==
                                                         'raw' else '')+('-MAL' if include_samples else '')
    statuses = readiness(cid)
    metadata = [{k: a[k] for k in a.keys() if k != 'usage'} for a in db().execute(
        'SELECT * FROM artifacts WHERE case_id=?', (cid,))]
    manifest = {'archive_type': archive_type, 'include_samples': include_samples, 'schema': 'mare-mip/2.0', 'package_id': name, 'title': c['name'], 'case_number': c['number'], 'external_reference': {
        'system': c['external_system'], 'number': c['external_number']}, 'description': c['description'], 'created_at': c['created'], 'packaged_at': now(), 'readiness': statuses, 'acknowledged_issues': issues, 'artifacts': metadata, 'files': []}
    contents = {}
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root).as_posix()
        # Deliverable allowlist excludes legacy sample payload directories and obsolete scaffold files.
        if rel.split('/')[0] not in CATEGORIES or p.is_symlink() or is_backup(rel):
            continue
        if p.is_file() and (raw_package_file(rel, include_samples) if archive_type == 'raw' else deliverable_file(cid, rel) or (include_samples and rel.startswith('samples/') and p.suffix.lower() == '.zip')):
            contents[rel] = p
    selected = db().execute(
        'SELECT * FROM notes WHERE case_id=? AND include_export=1 ORDER BY id', (cid,)).fetchall()
    if selected and archive_type == 'raw':
        contents['reports/reverse-engineering-notes.md'] = ('# Reverse Engineering Notes\n\n'+'\n\n'.join('## '+(
            n['title'] or 'Note')+'\n'+n['author']+' · '+n['created']+'\n\n'+n['body'] for n in selected)).encode()
    text = '# Malware Intelligence Package: ' + \
        c['name']+'\n\nCase: '+c['number']+'\n\n' + \
        (c['description'] or '')+'\n\n## Deliverable readiness\n'
    if c['external_number']:
        text += 'External reference: ' + \
            c['external_system']+' '+c['external_number']+'\n\n'
    for r in statuses:
        text += '- '+r['label']+': '+r['status'] + \
            (' — '+r['reason'] if r['reason'] else '')+'\n'
    text += '\n## Artifacts\n'
    for a in metadata:
        if a['path'] in contents:
            text += '- `'+a['path']+'`: '+a['description']+'\n'
    if issues:
        text += '\n## Acknowledged outstanding items\n' + \
            '\n'.join('- '+i for i in issues)+'\n'
    contents['README.md'] = text.encode()
    manifest['artifacts'] = [a for a in metadata if a['path'] in contents]
    import tempfile
    out = tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder in CATEGORIES:
            z.writestr(name+'/'+folder+'/', b'')
        for rel, content in contents.items():
            digest = hashlib.sha256()
            size = 0
            with z.open(name+'/'+rel, 'w') as destination:
                if isinstance(content, Path):
                    with content.open('rb') as source:
                        while True:
                            chunk = source.read(1024*1024)
                            if not chunk:
                                break
                            destination.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                else:
                    destination.write(content)
                    digest.update(content)
                    size = len(content)
            manifest['files'].append(
                {'path': rel, 'sha256': digest.hexdigest(), 'size': size})
        z.writestr(name+'/manifest.json', json.dumps(manifest, indent=2))
    out.seek(0)
    return out, name


@app.route('/users', methods=['GET', 'POST'])
@admin
def users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        role = request.form.get('role')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username) or role not in ('User', 'Administrator'):
            abort(400)
        pw = temporary()
        try:
            run('INSERT INTO users(username,password,role) VALUES(?,?,?)',
                (username, generate_password_hash(pw), role))
            audit('Created user '+username)
            flash(f'Temporary password for {username}: {pw}')
        except sqlite3.IntegrityError:
            flash('Username already exists.')
        return redirect('/users')
    return render_template('users.html', users=db().execute('SELECT * FROM users ORDER BY username').fetchall())


def temporary(): return ''.join(secrets.choice(
    'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789') for _ in range(12))


@app.post('/users/<int:uid>/<action>')
@admin
def user_action(uid, action):
    u = db().execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not u:
        abort(404)
    if uid == g.user['id']:
        flash('Use Settings for your own account.')
        return redirect('/users')
    if u['role'] == 'Administrator' and u['active'] and action in ('toggle', 'delete') and db().execute("SELECT count(*) FROM users WHERE role='Administrator' AND active=1").fetchone()[0] <= 1:
        abort(400)
    if action == 'toggle':
        run('UPDATE users SET active=1-active,version=version+1 WHERE id=?', (uid,))
    elif action == 'reset':
        pw = temporary()
        run('UPDATE users SET password=?,forced=1,version=version+1 WHERE id=?',
            (generate_password_hash(pw), uid))
        flash(f'Temporary password for {u["username"]}: {pw}')
    elif action == 'delete':
        run('UPDATE cases SET owner=NULL WHERE owner=?', (uid,))
        run('DELETE FROM drafts WHERE user_id=?', (uid,))
        run('UPDATE cases SET creator=NULL WHERE creator=?', (uid,))
        run('DELETE FROM users WHERE id=?', (uid,))
    else:
        abort(404)
    audit(f'{action} user {u["username"]}')
    return redirect('/users')


@app.get('/audit')
@admin
def audit_view():
    actors = [row['actor'] for row in db().execute(
        "SELECT DISTINCT actor FROM audit WHERE actor IS NOT NULL AND actor!='' ORDER BY actor")]
    selected_actor = request.args.get('actor', '')
    query = 'SELECT * FROM audit'
    args = ()
    if selected_actor:
        query += ' WHERE actor=?'
        args = (selected_actor,)
    events = db().execute(query+' ORDER BY id DESC LIMIT 500', args).fetchall()
    grouped = {}
    for event in events:
        created = event['created'] or ''
        day = created[:10] if len(created) >= 10 else 'Unknown date'
        grouped.setdefault(day, []).append(event)
    days = [{'date': day, 'events': items} for day, items in grouped.items()]
    return render_template('audit.html', actors=actors, selected_actor=selected_actor, days=days)


@app.get('/audit/export.csv')
@admin
def audit_export_csv():
    actor = request.args.get('actor', '')
    query = 'SELECT created,actor,action FROM audit'
    args = ()
    if actor:
        query += ' WHERE actor=?'
        args = (actor,)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Time (UTC)', 'User', 'Action'])
    for event in db().execute(query+' ORDER BY id DESC', args):
        writer.writerow([event['created'], event['actor'], event['action']])
    data = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(data, as_attachment=True, download_name='audit-events.csv', mimetype='text/csv')


@app.get('/audit/export-all.zip')
@admin
def audit_export_all_zip():
    output = tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        with archive.open('audit-events.csv', 'w') as csv_bytes:
            text = io.TextIOWrapper(
                csv_bytes, encoding='utf-8-sig', newline='')
            try:
                writer = csv.writer(text)
                writer.writerow(['Time (UTC)', 'User', 'Action'])
                for event in db().execute('SELECT created,actor,action FROM audit ORDER BY id DESC'):
                    writer.writerow(
                        [event['created'], event['actor'], event['action']])
                text.flush()
            finally:
                text.detach()
    output.seek(0)
    response = send_file(output, as_attachment=True,
                         download_name='audit-events-all.zip', mimetype='application/zip')
    response.call_on_close(output.close)
    return response


@app.cli.command('create-admin')
def create_admin():
    import click
    username = click.prompt('Username')
    password = click.prompt('Password (12+ characters)',
                            hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        raise click.ClickException('Minimum 12 characters')
    try:
        run("INSERT INTO users(username,password,role,forced) VALUES(?,?,'Administrator',0)",
            (username, generate_password_hash(password)))
    except sqlite3.IntegrityError:
        raise click.ClickException('Username already exists')
    click.echo('Administrator created.')


register_indicators(app, ROOT, db, case, package,
                    ensure_package, mark_pending, audit)
register_references(app, db, case, ensure_package, mark_pending, audit)
asset_helpers = register_assets(
    app, db, case, package, ensure_package, safe_path, mark_pending, audit)
report_helpers = register_reporting(
    app, ROOT, db, run, case, package, ensure_package, mark_pending, audit, now)

backup_helpers = register_backups(
    app, ROOT, db, case, package, ensure_package, build_archive, allocate_case_number, audit, now)

register_api(app, db, run, case, package, ensure_package, now, audit, allocate_case_number, external_reference, sample_archive_password,
             mark_pending, readiness, review_issues, STAGES, safe_path, build_archive, report_helpers, asset_helpers, backup_helpers, metrics_data)

register_tools(app, db)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000)

register_tags(app, db, case)
