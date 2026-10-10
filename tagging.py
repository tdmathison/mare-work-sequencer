"""Simple shared tags, case assignments, and portable backup metadata."""
import sqlite3
from datetime import datetime, timezone
from flask import abort, flash, g, redirect, render_template, request
from authorization import has_permission


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError('Tag names must contain 1–120 characters without control characters.')
    return value.strip()


def normalized(value):
    return name(value).casefold()


def prototype(connection):
    columns = {r[1] for r in connection.execute('PRAGMA table_info(tags)')}
    relationships = {r[1] for r in connection.execute('PRAGMA table_info(case_tags)')}
    return bool((columns and columns != {'id', 'name', 'normalized_name', 'created_at'}) or (relationships and relationships != {'case_id', 'tag_id', 'assigned_at', 'assigned_by'}) or (not columns and connection.execute("SELECT 1 FROM sqlite_master WHERE name='tag_categories'").fetchone()))


def initialize(connection):
    if prototype(connection):
        return False
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS case_tags(case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,assigned_at TEXT NOT NULL,assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,PRIMARY KEY(case_id,tag_id));
    CREATE INDEX IF NOT EXISTS case_tags_tag ON case_tags(tag_id,case_id);
    ''')
    connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES('simple-case-tags-v1')")
    connection.commit()
    return True


def catalog(connection, search='', sort='name', limit=None):
    order = {'name': 't.normalized_name', 'most': 'uses DESC,t.normalized_name', 'least': 'uses,t.normalized_name'}.get(sort, 't.normalized_name')
    sql = 'SELECT t.*,count(ct.case_id) AS uses FROM tags t LEFT JOIN case_tags ct ON ct.tag_id=t.id WHERE instr(t.normalized_name,?)>0 GROUP BY t.id ORDER BY '+order
    args = [search.strip().casefold()]
    if limit is not None:
        sql += ' LIMIT ?'; args.append(limit)
    return [dict(r) for r in connection.execute(sql, args)]


def create(connection, value):
    display = name(value)
    changed = connection.execute('INSERT INTO tags(name,normalized_name,created_at) VALUES(?,?,?) ON CONFLICT(normalized_name) DO NOTHING', (display, normalized(display), now())).rowcount
    tid = connection.execute('SELECT id FROM tags WHERE normalized_name=?', (normalized(display),)).fetchone()[0]
    return tid, bool(changed)


def assignments(connection, cid=None):
    sql = 'SELECT t.id,t.name,ct.case_id,ct.assigned_at,u.username AS assigned_by FROM case_tags ct JOIN tags t ON t.id=ct.tag_id LEFT JOIN users u ON u.id=ct.assigned_by'
    args = []
    if cid is not None:
        sql += ' WHERE ct.case_id=?'; args.append(cid)
    return [dict(r) for r in connection.execute(sql+' ORDER BY t.normalized_name', args)]


def portable(connection, cid=None):
    if prototype(connection): raise ValueError('Migrate prototype tags before exporting RAW backups.')
    rows = assignments(connection, cid) if cid is not None else catalog(connection)
    return {'schema_version': 1, 'tags': [r['name'] for r in rows]}


def validate_portable(data):
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) != {'schema_version', 'tags'} or type(data['schema_version']) is not int or data['schema_version'] != 1 or not isinstance(data['tags'], list) or len(data['tags']) > 10000:
        raise ValueError('Unsupported or malformed tag metadata.')
    seen = set()
    for value in data['tags']:
        key = normalized(value)
        if key in seen:
            raise ValueError('Duplicate names in tag metadata.')
        seen.add(key)
    return data


def restore(connection, data, cid=None):
    if data is None:
        return
    if prototype(connection):
        raise ValueError('Prototype tag tables require explicit migration before restoring tags.')
    for value in data['tags']:
        tid, _ = create(connection, value)
        if cid is not None:
            connection.execute('INSERT OR IGNORE INTO case_tags VALUES(?,?,?,NULL)', (cid, tid, now()))


def case_filter(selected, match):
    if not selected:
        return '', []
    sql = ' AND c.id IN (SELECT case_id FROM case_tags WHERE tag_id IN ('+','.join('?' for _ in selected)+') GROUP BY case_id'
    if match == 'all':
        sql += ' HAVING count(DISTINCT tag_id)=?'
    return sql+')', list(selected)+([len(selected)] if match == 'all' else [])


def register_tags(app, db, case):
    with app.app_context():
        initialize(db())

    def allowed(permission):
        return has_permission(g.user, permission, db())

    def require(permission):
        if not allowed(permission): abort(403)
        if prototype(db()): abort(503, 'Prototype tag tables detected. Run the documented explicit migration before using tags.')

    def event(action):
        db().execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)', (g.user['username'], action, now()))

    @app.context_processor
    def context():
        if not getattr(g, 'user', None): return {}
        return dict(can_tags_read=allowed('tags:read'), can_tags_create=allowed('tags:create'), can_tags_manage=allowed('tags:manage'), can_tags_assign=allowed('tags:assign') and allowed('cases:update'), tags_ready=not prototype(db()), case_tags=lambda cid: assignments(db(), cid))

    @app.get('/tags')
    def tags_manager():
        require('tags:read')
        return render_template('tags.html', tags=catalog(db(), request.args.get('q',''), request.args.get('sort','name')))

    @app.get('/tags/search')
    def tags_search():
        require('tags:read')
        query = request.args.get('q','').strip()
        exact = db().execute('SELECT id FROM tags WHERE normalized_name=?',(query.casefold(),)).fetchone()
        return {'tags': catalog(db(), query, limit=100), 'exact_id': exact[0] if exact else None}

    @app.get('/cases/<int:cid>/tags')
    def case_tags_list(cid):
        require('tags:read'); require('cases:read'); case(cid)
        return {'tags': assignments(db(), cid)}

    @app.get('/tags/<int:tid>')
    def tag_detail(tid):
        require('tags:read')
        tag = db().execute('SELECT t.*,count(ct.case_id) AS uses FROM tags t LEFT JOIN case_tags ct ON ct.tag_id=t.id WHERE t.id=? GROUP BY t.id', (tid,)).fetchone()
        if not tag: abort(404)
        rows = db().execute('SELECT c.id,c.number,c.name,c.stage,u.username AS owner FROM cases c JOIN case_tags ct ON ct.case_id=c.id LEFT JOIN users u ON u.id=c.owner WHERE ct.tag_id=? ORDER BY c.id DESC', (tid,)).fetchall() if allowed('cases:read') else []
        return render_template('tag_detail.html', tag=tag, cases=rows, all_tags=catalog(db()))

    @app.post('/tags/create')
    @app.post('/cases/<int:cid>/tags/create')
    def tags_create(cid=None):
        require('tags:create')
        if cid is not None:
            require('tags:assign'); require('cases:update'); case(cid)
        try:
            with db():
                tid, created = create(db(), request.form.get('name'))
                if created: event(f'Tag created: id={tid}, name={name(request.form.get("name"))}')
                if cid is not None:
                    changed = db().execute('INSERT OR IGNORE INTO case_tags VALUES(?,?,?,?)', (cid, tid, now(), g.user['id'])).rowcount
                    if changed: event(f'Tag assigned: case={cid}, tag={tid}')
            if cid is not None and request.accept_mimetypes.best == 'application/json':
                return {'tags': assignments(db(), cid)}
            flash('Tag saved.')
        except ValueError as exc:
            if cid is not None and request.accept_mimetypes.best == 'application/json':
                return {'error': str(exc)}, 400
            flash(str(exc))
        return redirect(f'/cases/{cid}#case-tags' if cid is not None else '/tags')

    @app.post('/cases/<int:cid>/tags/<int:tid>/<operation>')
    def case_tag_change(cid, tid, operation):
        require('tags:assign'); require('cases:update'); case(cid)
        if operation not in ('assign','remove') or not db().execute('SELECT 1 FROM tags WHERE id=?',(tid,)).fetchone(): abort(404)
        with db():
            changed = db().execute('INSERT OR IGNORE INTO case_tags VALUES(?,?,?,?)',(cid,tid,now(),g.user['id'])).rowcount if operation == 'assign' else db().execute('DELETE FROM case_tags WHERE case_id=? AND tag_id=?',(cid,tid)).rowcount
            if changed: event(f'Tag {"assigned" if operation == "assign" else "removed"}: case={cid}, tag={tid}')
        if request.accept_mimetypes.best == 'application/json':
            return {'tags': assignments(db(), cid)}
        flash('Case tags updated.')
        return redirect(f'/cases/{cid}#case-tags')

    @app.post('/tags/<int:tid>/<operation>')
    def tag_manage(tid, operation):
        require('tags:manage')
        source = db().execute('SELECT * FROM tags WHERE id=?',(tid,)).fetchone()
        if not source: abort(404)
        try:
            with db():
                if operation == 'rename':
                    display = name(request.form.get('name'))
                    db().execute('UPDATE tags SET name=?,normalized_name=? WHERE id=?',(display,normalized(display),tid))
                    event(f'Tag renamed: id={tid}, previous={source["name"]}, new={display}')
                elif operation == 'merge':
                    destination = request.form.get('destination','')
                    target = db().execute('SELECT * FROM tags WHERE id=?',(destination,)).fetchone()
                    if not target or target['id'] == tid: raise ValueError('Choose a different destination tag.')
                    if request.form.get('confirm') != '1': raise ValueError('Confirm the merge before proceeding.')
                    db().execute('INSERT OR IGNORE INTO case_tags SELECT case_id,?,assigned_at,assigned_by FROM case_tags WHERE tag_id=?',(target['id'],tid))
                    db().execute('DELETE FROM tags WHERE id=?',(tid,))
                    event(f'Tags merged: source={tid} ({source["name"]}), destination={target["id"]} ({target["name"]})')
                elif operation == 'delete':
                    if request.form.get('confirm') != '1': raise ValueError('Confirm deleting this tag and its assignments.')
                    db().execute('DELETE FROM tags WHERE id=?',(tid,))
                    event(f'Tag deleted: id={tid}, name={source["name"]}')
                else: abort(404)
            flash('Tag catalog updated.')
        except sqlite3.IntegrityError: flash('That tag name already exists. Merge the tags instead.')
        except ValueError as exc: flash(str(exc))
        return redirect(f'/tags/{tid}' if operation == 'rename' else '/tags')


def migrate_prototype(path):
    """Explicit conversion: retain original tables and back up the entire database."""
    from pathlib import Path
    path = Path(path)
    if not path.is_file(): raise ValueError('Database path does not exist.')
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if not prototype(connection): raise ValueError('No prototype tag schema detected.')
    required = {'id','name','created','category_id'}
    if not required <= {r[1] for r in connection.execute('PRAGMA table_info(tags)')}:
        raise ValueError('Unknown prototype schema; migration refused.')
    backup = path.with_name(path.name+'.before-simple-tags-'+datetime.now().strftime('%Y%m%d%H%M%S')+'.sqlite')
    with sqlite3.connect(backup) as destination: connection.backup(destination)
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('ALTER TABLE case_tags RENAME TO prototype_case_tags')
        connection.execute('ALTER TABLE tags RENAME TO prototype_tags')
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='tag_categories'").fetchone():
            connection.execute('ALTER TABLE tag_categories RENAME TO prototype_tag_categories')
        connection.execute('DROP INDEX IF EXISTS case_tags_tag')
        connection.execute('CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL)')
        connection.execute('CREATE TABLE case_tags(case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,assigned_at TEXT NOT NULL,assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,PRIMARY KEY(case_id,tag_id))')
        connection.execute('CREATE INDEX case_tags_tag ON case_tags(tag_id,case_id)')
        mapping = {}
        for row in connection.execute('SELECT * FROM prototype_tags ORDER BY id').fetchall():
            tid, added = create(connection,row['name']); mapping[row['id']] = tid
            if added: connection.execute('UPDATE tags SET created_at=? WHERE id=?',(row['created'],tid))
        for row in connection.execute('SELECT * FROM prototype_case_tags ORDER BY assigned').fetchall():
            connection.execute('INSERT OR IGNORE INTO case_tags VALUES(?,?,?,?)',(row['case_id'],mapping[row['tag_id']],row['assigned'],row['assigned_by']))
        connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES('simple-case-tags-v1')")
        connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',('migration','Explicit prototype tag flattening; original tables retained',now()))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()
    return backup


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Back up and explicitly flatten prototype tags. Stop MARE before running.')
    parser.add_argument('--migrate-prototype', required=True)
    parser.add_argument('--confirm-flatten', action='store_true', help='Confirm merging identical names across former categories; lowest original ID wins display name.')
    args = parser.parse_args()
    if not args.confirm_flatten: parser.error('--confirm-flatten is required')
    print('Database backup:', migrate_prototype(args.migrate_prototype))
