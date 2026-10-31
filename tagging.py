"""Simple shared tags, case assignments, and portable backup metadata."""
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from flask import abort, flash, g, redirect, render_template, request, url_for
from authorization import has_permission


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


NAMING_HELP = 'Tags are saved in uppercase. Use only ASCII letters, numbers, and underscores (1–120 characters).'
INVALID_NAME = 'Tags may contain only letters, numbers, and underscores.'


def name(value):
    if not isinstance(value, str):
        raise ValueError('Tag names must contain 1–120 characters.')
    value = value.strip()
    if not value or len(value) > 120:
        raise ValueError('Tag names must contain 1–120 characters.')
    # Validate before uppercasing: ß, dotless i and Unicode lookalikes stay invalid.
    if not re.fullmatch(r'[A-Za-z0-9_]+', value, flags=re.ASCII):
        raise ValueError(INVALID_NAME)
    return value.upper()


def normalized(value):
    return name(value)


def invalid_legacy(connection):
    invalid = []
    for row in connection.execute('SELECT id,name FROM tags ORDER BY id'):
        try:
            name(row['name'])
        except ValueError as error:
            invalid.append(dict(id=row['id'], name=row['name'], error=str(error)))
    return invalid


def migrate_names(connection):
    """One atomic upgrade; keep lowest IDs and all assignments, flag invalid rows."""
    marker = 'uppercase-ascii-tags-v1'
    if connection.execute('SELECT 1 FROM schema_migrations WHERE name=?', (marker,)).fetchone():
        return
    connection.execute('SAVEPOINT uppercase_tags')
    try:
        groups = {}
        for row in connection.execute('SELECT id,name FROM tags ORDER BY id').fetchall():
            try:
                canonical = name(row['name'])
            except ValueError:
                continue  # Never rewrite or discard invalid legacy records.
            groups.setdefault(canonical, []).append(row['id'])
        # Free old normalized keys before canonicalizing (including swapped keys).
        temporary_prefix = 'tag-migration:'+secrets.token_hex(16)+':'
        for ids in groups.values():
            for tid in ids:
                connection.execute('UPDATE tags SET normalized_name=? WHERE id=?', (temporary_prefix+str(tid), tid))
        for canonical, ids in groups.items():
            winner = ids[0]
            for tid in ids[1:]:
                connection.execute('INSERT OR IGNORE INTO case_tags SELECT case_id,?,assigned_at,assigned_by FROM case_tags WHERE tag_id=?', (winner, tid))
                connection.execute('DELETE FROM case_tags WHERE tag_id=?', (tid,))
                connection.execute('DELETE FROM tags WHERE id=?', (tid,))
                connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)', ('migration', f'Tag casing consolidated: source={tid}, canonical={winner} ({canonical})', now()))
            connection.execute('UPDATE tags SET name=?,normalized_name=? WHERE id=?', (canonical, canonical, winner))
        for tag in invalid_legacy(connection):
            connection.execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)', ('migration', f'Invalid legacy tag retained: id={tag["id"]}; rename in Tag Manager', now()))
        connection.execute('INSERT INTO schema_migrations VALUES(?)', (marker,))
        connection.execute('RELEASE uppercase_tags')
    except Exception:
        connection.execute('ROLLBACK TO uppercase_tags')
        connection.execute('RELEASE uppercase_tags')
        raise


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
    migrate_names(connection)
    # Existing invalid rows remain editable; all new/renamed names are canonical.
    for operation in ('INSERT', 'UPDATE OF name,normalized_name'):
        suffix = 'insert' if operation == 'INSERT' else 'update'
        connection.execute(f"""CREATE TRIGGER IF NOT EXISTS tags_canonical_{suffix}
        BEFORE {operation} ON tags WHEN length(NEW.name) NOT BETWEEN 1 AND 120
        OR NEW.name GLOB '*[^A-Z0-9_]*' OR instr(NEW.name,char(0))>0 OR NEW.name<>upper(NEW.name)
        OR NEW.normalized_name<>NEW.name
        BEGIN SELECT RAISE(ABORT, 'Tags must use canonical uppercase ASCII names.'); END""")
    connection.commit()
    return True


def catalog(connection, search='', sort='name', limit=None, *, case_access=None):
    order = {'name': 't.normalized_name', 'most': 'uses DESC,t.normalized_name', 'least': 'uses,t.normalized_name'}.get(sort, 't.normalized_name')
    # Optional view scope leaves existing API/export callers unchanged while sharing
    # normalization, matching and ordering with the profile workspace.
    from case_queries import CASE_ELIGIBILITY
    scoped = case_access is not None
    prefix = ('WITH accessible_cases AS (SELECT c.id FROM cases c WHERE ('+CASE_ELIGIBILITY+') AND ?) ') if scoped else ''
    usage = 'count(DISTINCT visible.id)' if scoped else 'count(ct.case_id)'
    joins = ' LEFT JOIN accessible_cases visible ON visible.id=ct.case_id' if scoped else ''
    sql = prefix+'SELECT t.*,'+usage+' AS uses FROM tags t LEFT JOIN case_tags ct ON ct.tag_id=t.id'+joins+' WHERE (instr(t.normalized_name,?)>0 OR instr(t.normalized_name,?)>0) GROUP BY t.id ORDER BY '+order
    args = ([bool(case_access)] if scoped else [])+[search.strip().upper(), search.strip().casefold()]
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


def validate_portable(data, *, allow_legacy=False):
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) != {'schema_version', 'tags'} or type(data['schema_version']) is not int or data['schema_version'] != 1 or not isinstance(data['tags'], list) or len(data['tags']) > 10000:
        raise ValueError('Unsupported or malformed tag metadata.')
    seen = set()
    for value in data['tags']:
        if allow_legacy:
            # Only trusted local snapshots use this escape hatch, never imports.
            continue
        try:
            key = normalized(value)
        except ValueError as error:
            raise ValueError(f'Invalid incoming tag {value!r}: {error}') from error
        if key in seen:
            raise ValueError('Duplicate names in tag metadata.')
        seen.add(key)
    return data


def restore(connection, data, cid=None):
    if data is None:
        return
    validate_portable(data)
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
        return dict(can_tags_read=allowed('tags:read'), can_tags_create=allowed('tags:create'), can_tags_manage=allowed('tags:manage'), can_tags_assign=allowed('tags:assign') and allowed('cases:update'), tags_ready=not prototype(db()), tag_naming_help=NAMING_HELP, case_tags=lambda cid: assignments(db(), cid))


    from tag_workspace import register_workspace
    register_workspace(app,db,allowed,require)

    @app.get('/tags/search')
    def tags_search():
        require('tags:read')
        query = request.args.get('q','').strip()
        try:
            key = name(query)
        except ValueError:
            key = None
        exact = db().execute('SELECT id FROM tags WHERE normalized_name=?',(key,)).fetchone()
        return {'tags': catalog(db(), query, limit=100), 'exact_id': exact[0] if exact else None}

    @app.get('/cases/<int:cid>/tags')
    def case_tags_list(cid):
        require('tags:read'); require('cases:read'); case(cid)
        return {'tags': assignments(db(), cid)}


    def workspace_redirect(tid=None):
        values={key:request.form.get(key,'') for key in ('q','namespace','sort','tab') if request.form.get(key)}
        return redirect(url_for('tag_detail',tid=tid,**values) if tid is not None else url_for('tags_manager',**values))

    @app.post('/tags/create')
    @app.post('/cases/<int:cid>/tags/create')
    def tags_create(cid=None):
        require('tags:create')
        if cid is not None:
            require('tags:assign'); require('cases:update'); case(cid)
        tid=None
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
        if cid is None and request.form.get('workspace')=='1':return workspace_redirect(tid)
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
                    db().execute('UPDATE malware_families SET updated_by=? WHERE tag_id=?', (g.user['id'],tid))
                    event(f'Tag renamed: id={tid}, previous={source["name"]}, new={display}')
                elif operation == 'merge':
                    destination = request.form.get('destination','')
                    target = db().execute('SELECT * FROM tags WHERE id=?',(destination,)).fetchone()
                    if not target or target['id'] == tid: raise ValueError('Choose a different destination tag.')
                    name(target['name'])
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
        except sqlite3.IntegrityError as exc:
            flash(str(exc) if 'malware family' in str(exc) or 'threat actor' in str(exc) or 'MAL_' in str(exc) else 'That tag name already exists. Merge the tags instead.')
        except ValueError as exc: flash(str(exc))
        if request.form.get('workspace')=='1':
            remaining=db().execute('SELECT id FROM tags WHERE id=?',(tid,)).fetchone()
            return workspace_redirect(tid if remaining else int(request.form['destination']) if operation=='merge' else None)
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
