"""Shared authenticated research profile workspace and optimistic edit guards."""
import sqlite3
import uuid
from flask import abort, flash, g, redirect, render_template, request, url_for
from authorization import has_permission
from tagging import create as create_tag, now, prototype
from family_aliases import load_aliases, save_aliases, validate_aliases
from malware_families import PAGE_SIZE, STATES, Conflict, safe_url
from tagging import name as tag_name

def profile_tag(value, spec):
    value = tag_name(value)
    if not value.startswith(spec.tag_prefix) or len(value) <= len(spec.tag_prefix):
        raise ValueError(f'Choose a tag beginning with {spec.tag_prefix} and a nonempty suffix.')
    return value

def register_profiles(app, db, ROOT, spec):

    def render_profile(template, **context):
        family = context.get('family')
        from threat_actors import associations, choices, family_associations, actor_choices
        if spec.actor:
            if template == 'malware_family_form.html' and request.method == 'POST':
                selected = request.form.getlist('known_families')
                context['known_families'] = choices(db(), list(dict.fromkeys(selected))[:100], family['id'] if family else None)
            else:
                context['known_families'] = associations(db(), family['id']) if family else []
        else:
            if template == 'malware_family_form.html' and request.method == 'POST' and ('known_actors_present' in request.form or 'known_actors' in request.form):
                context['known_actors'] = actor_choices(db(), list(dict.fromkeys(request.form.getlist('known_actors')))[:100])
            else:
                context['known_actors'] = family_associations(db(), family['id']) if family else []
        return render_template(template, profile_type=spec, **context)

    def allowed(permission):
        return has_permission(g.user, permission, db())

    def require(write=False):
        if not allowed('tags:read') or (write and (not allowed('tags:manage'))):
            abort(403)
        if prototype(db()):
            abort(503, f'Migrate prototype tags before using {spec.title}.')

    def event(message):
        db().execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)', (g.user['username'], message, now()))

    def get_family(fid):
        row = db().execute(f'SELECT f.*,t.name AS tag FROM {spec.table} f JOIN tags t ON t.id=f.tag_id WHERE f.id=?', (fid,)).fetchone()
        if not row:
            abort(404)
        result = dict(row)
        result['aliases'] = load_aliases(row['aliases'])
        return result

    def version():
        try:
            return int(request.form.get('version', ''))
        except ValueError:
            raise ValueError('Missing edit version. Reload this profile before saving.')

    def touch(fid, expected):
        changed = db().execute(f'UPDATE {spec.table} SET version=version+1,updated_at=?,updated_by=? WHERE id=? AND version=?', (now(), g.user['id'], fid, expected)).rowcount
        if not changed:
            raise Conflict('This profile changed in another session. Your entered values are preserved. Open the current profile in another tab, compare changes, then reload before saving.')

    def finish(fid, tab='overview'):
        target = request.form.get('next', '')
        if target.startswith('/') and (not target.startswith('//')) and ('\\' not in target) and (not any((ord(c) < 32 for c in target))):
            return redirect(target)
        return redirect(url_for(f'{spec.key}_workspace', fid=fid, tab=tab))

    def page_number(key):
        try:
            return max(1, min(1000000, int(request.args.get(key, '1'))))
        except ValueError:
            abort(400)

    @app.context_processor
    def family_permissions():
        return {('can_actors_read' if spec.actor else 'can_families_read'): bool(getattr(g, 'user', None)) and has_permission(g.user, 'tags:read', db())}

    @app.get(f'{spec.path}', endpoint=f'{spec.key}_workspace')
    @app.get(f'{spec.path}/<fid>', endpoint=f'{spec.key}_workspace')
    def families_workspace(fid=None):
        require()
        page = page_number('page')
        query = request.args.get('q', '').strip()[:200]
        predicate = "(?='' OR instr(lower(f.name),lower(?))>0\n            OR instr(lower(t.name),lower(?))>0 OR EXISTS\n            (SELECT 1 FROM json_each(f.aliases) a WHERE instr(lower(a.value),lower(?))>0))"
        query_args = (query,) * 4
        selected = get_family(fid) if fid else None
        if selected and (not query) and ('page' not in request.args):
            rank = db().execute(f'SELECT count(*) FROM {spec.table} WHERE name COLLATE NOCASE < ? COLLATE NOCASE OR (name COLLATE NOCASE = ? COLLATE NOCASE AND id < ?)', (selected['name'], selected['name'], fid)).fetchone()[0]
            page = rank // PAGE_SIZE + 1
        total = db().execute(f'SELECT count(*) FROM {spec.table} f JOIN tags t ON t.id=f.tag_id WHERE ' + predicate, query_args).fetchone()[0]
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        can_cases = allowed('cases:read')
        families = db().execute(f'SELECT f.id,f.name,\n          (SELECT count(*) FROM {spec.osint_table} o WHERE o.{spec.foreign_key}=f.id) AS osint_count,\n          (SELECT count(*) FROM {spec.reports_table} r WHERE r.{spec.foreign_key}=f.id) AS report_count,\n          CASE WHEN ? THEN (SELECT count(DISTINCT ct.case_id) FROM case_tags ct JOIN cases c ON c.id=ct.case_id WHERE ct.tag_id=f.tag_id) ELSE 0 END AS case_count\n          FROM {spec.table} f JOIN tags t ON t.id=f.tag_id WHERE ' + predicate + ' ORDER BY f.name COLLATE NOCASE,f.id LIMIT ? OFFSET ?', (can_cases, *query_args, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
        if fid is None and families:
            fid = families[0]['id']
        family = selected or (get_family(fid) if fid else None)
        tab = request.args.get('tab', 'overview')
        if tab not in ('overview', 'osint', 'history'):
            abort(400)
        case_page = page_number('case_page')
        case_count = 0
        history = []
        osint = []
        reports = []
        if family:
            if can_cases:
                case_count = db().execute('SELECT count(DISTINCT ct.case_id) FROM case_tags ct JOIN cases c ON c.id=ct.case_id WHERE ct.tag_id=?', (family['tag_id'],)).fetchone()[0]
                case_page = min(case_page, max(1, (case_count + PAGE_SIZE - 1) // PAGE_SIZE))
                if tab == 'history':
                    history = db().execute('SELECT c.id,c.number,c.name,c.stage FROM cases c JOIN case_tags ct ON ct.case_id=c.id WHERE ct.tag_id=? ORDER BY c.number DESC LIMIT ? OFFSET ?', (family['tag_id'], PAGE_SIZE, (case_page - 1) * PAGE_SIZE)).fetchall()
            if tab == 'osint':
                osint = db().execute(f'SELECT * FROM {spec.osint_table} WHERE {spec.foreign_key}=? ORDER BY position,id', (fid,)).fetchall()
                reports = db().execute(f'SELECT * FROM {spec.reports_table} WHERE {spec.foreign_key}=? ORDER BY uploaded_at,id LIMIT 100', (fid,)).fetchall()
        return render_profile('malware_families.html', families=families, query=query, family=family, tab=tab, osint=osint, reports=reports, history=history, states=STATES, page=page, pages=pages, total=total, case_count=case_count, case_page=case_page, case_pages=max(1, (case_count + PAGE_SIZE - 1) // PAGE_SIZE), can_cases=can_cases, can_manage=allowed('tags:manage'))

    @app.route(f'{spec.path}/new', methods=['GET', 'POST'], endpoint=f'{spec.key}_edit')
    @app.route(f'{spec.path}/<fid>/edit', methods=['GET', 'POST'], endpoint=f'{spec.key}_edit')
    def families_edit(fid=None):
        require(True)
        family = get_family(fid) if fid else None
        values = request.form if request.method == 'POST' else dict(family) if family else {}
        aliases = request.form.getlist('aliases') if request.method == 'POST' and ('aliases_present' in request.form or 'aliases' in request.form) else family['aliases'] if family else []
        alias_draft = request.form.get('alias_draft', '') if request.method == 'POST' else ''
        error, status = (None, 200)
        conflict = None
        origin_id = request.form.get('source_tag_id', '') if request.method == 'POST' else request.args.get('tag_id', '')
        origin_name = request.form.get('source_tag_name', '')
        origin_identity = request.form.get('source_tag_identity', '')
        origin = None
        if not family and origin_id:
            if not origin_id.isascii() or not origin_id.isdigit() or len(origin_id) > 18:
                error, status = (f'Invalid tag selection. Return to Tags and choose an existing {spec.tag_prefix} tag.', 400)
            else:
                origin = db().execute('SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE t.id=?', (int(origin_id),)).fetchone()
                if not origin or not origin['name'].startswith(f'{spec.tag_prefix}') or len(origin['name']) <= len(spec.tag_prefix):
                    error, status = (f'The selected tag was deleted or is no longer a valid {spec.tag_prefix} tag. Return to Tags and select an accessible tag.', 409)
                elif request.method == 'GET':
                    existing_profile = db().execute(f'SELECT id FROM {spec.table} WHERE tag_id=?', (origin['id'],)).fetchone()
                    if existing_profile:
                        flash(f'This tag already has a {spec.lower} profile.')
                        return redirect(url_for(f'{spec.key}_workspace', fid=existing_profile['id'], tab='overview'))
                    origin_name = origin['name']
                    origin_identity = origin['identity']
                    values = {'tag': origin_name}
        if request.method == 'POST' and (not error):
            try:
                saved_aliases = validate_aliases([*aliases, alias_draft] if alias_draft.strip() else aliases)
                title = request.form.get('name', '').strip()
                if not title or len(title) > 200:
                    raise ValueError(f'Enter a {spec.lower} name of 1–200 characters.')
                tag = profile_tag(request.form.get('tag'), spec)
                descriptions = [request.form.get(key, '') for key in ('short_description', 'long_description', 'attribution_notes')]
                if spec.actor:
                    descriptions[2] = ''
                if any((len(value) > limit for value, limit in zip(descriptions, (1000, 100000, 100000)))):
                    raise ValueError('Short descriptions allow 1,000 characters; long descriptions and attribution notes allow 100,000 each.')
                with db():
                    db().execute('BEGIN IMMEDIATE')
                    if not family and origin_id:
                        current_origin = db().execute('SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE t.id=?', (int(origin_id),)).fetchone()
                        if not current_origin or current_origin['identity'] != origin_identity or current_origin['name'] != origin_name or (not current_origin['name'].startswith(f'{spec.tag_prefix}')):
                            raise Conflict('The original tag changed or was deleted. Your content is preserved; return to Tags and select the current tag before saving.')
                    existing = db().execute('SELECT id FROM tags WHERE normalized_name=?', (tag,)).fetchone()
                    if not family and origin_id and (tag == origin_name) and (not existing or existing['id'] != int(origin_id)):
                        raise Conflict('The original tag identity is no longer available. Return to Tags; no replacement tag was created.')
                    if not existing and (not allowed('tags:create')):
                        abort(403)
                    if family:
                        touch(fid, version())
                    tid, created = create_tag(db(), tag)
                    conflict = db().execute(f'SELECT id,name FROM {spec.table} WHERE tag_id=? AND id<>?', (tid, fid or '')).fetchone()
                    if conflict:
                        raise Conflict(f"This tag is already linked to {conflict['name']}. Edit that profile or choose a different {spec.tag_prefix} tag.")
                    stamp = now()
                    if family:
                        db().execute(f'UPDATE {spec.table} SET name=?,tag_id=?,short_description=?,long_description=?,attribution_notes=? WHERE id=?', [title, tid, *descriptions, fid])
                        event(f'{spec.singular} edited: {fid} ({title})')
                        if family['tag_id'] != tid:
                            event(f"{spec.singular} relinked: {fid}, previous={family['tag_id']}, new={tid}; case assignments preserved")
                    else:
                        fid = str(uuid.uuid4())
                        db().execute(f'INSERT INTO {spec.table}(id,name,tag_id,short_description,long_description,attribution_notes,created_at,updated_at,created_by,updated_by) VALUES(?,?,?,?,?,?,?,?,?,?)', [fid, title, tid, *descriptions, stamp, stamp, g.user['id'], g.user['id']])
                        event(f'{spec.singular} created: {fid} ({title})')
                    save_aliases(db(), fid, saved_aliases, table=spec.table)
                    if spec.actor:
                        from threat_actors import save_associations
                        if save_associations(db(), fid, request.form.getlist('known_families'), g.user['id']):
                            event(f'Threat actor Malware Family associations changed: {fid}')
                    elif 'known_actors_present' in request.form or 'known_actors' in request.form:
                        from threat_actors import save_family_associations
                        if save_family_associations(db(), fid, request.form.getlist('known_actors'), g.user['id']):
                            event(f'Malware Family Threat Actor associations changed: {fid}')
                    if created:
                        event(f'Tag created: id={tid}, name={tag}')
                flash(f'{spec.singular} saved. You can now attach research reports in OSINT & Reports.')
                if request.form.get('upload_after') == '1':
                    return redirect(url_for(f'{spec.key}_workspace', fid=fid, tab='osint') + '#attached-reports')
                return finish(fid)
            except (ValueError, sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                error = str(exc) if not isinstance(exc, sqlite3.IntegrityError) else 'This tag is already linked to a profile. Choose a different tag.'
                if isinstance(exc, sqlite3.OperationalError):
                    error = 'Unable to save right now. Your entered values are preserved; retry when the database is available.'
                status = 503 if isinstance(exc, sqlite3.OperationalError) else 409 if isinstance(exc, (Conflict, sqlite3.IntegrityError)) else 400
        tags = db().execute(f"SELECT name FROM tags WHERE substr(name,1,{len(spec.tag_prefix)})='{spec.tag_prefix}' AND length(name)>{len(spec.tag_prefix)} ORDER BY name LIMIT 1000").fetchall()
        return (render_profile('malware_family_form.html', family=family, values=values, error=error, tags=tags, origin=origin, origin_id=origin_id, origin_name=origin_name, origin_identity=origin_identity, conflict=conflict, aliases=aliases, alias_draft=alias_draft), status)

    @app.route(f'{spec.path}/<fid>/delete', methods=['GET', 'POST'], endpoint=f'{spec.key}_delete')
    def families_delete(fid):
        require(True)
        family = get_family(fid)
        error, status = (None, 200)
        if request.method == 'POST':
            try:
                if request.form.get('confirm_name') != family['name']:
                    raise ValueError('Enter the exact profile name to confirm deletion.')
                from family_reports import storage_transaction
                with storage_transaction(db(), ROOT, spec=spec) as files:
                    touch(fid, version())
                    files.remove(db().execute(f'SELECT * FROM {spec.reports_table} WHERE {spec.foreign_key}=?', (fid,)).fetchall())
                    affected = db().execute('SELECT actor_id FROM actor_families WHERE family_id=?', (fid,)).fetchall() if not spec.actor else []
                    db().execute(f'DELETE FROM {spec.table} WHERE id=?', (fid,))
                    for row in affected:
                        event(f'Threat actor association removed: actor={row[0]}, deleted Malware Family={fid}')
                    event(f"{spec.singular} deleted: {fid} ({family['name']}); shared tag and case assignments preserved")
                flash('Profile deleted. Its shared tag, case assignments, cases and assets were preserved.')
                return redirect(url_for(f'{spec.key}_workspace'))
            except (ValueError, OSError, sqlite3.Error) as exc:
                error, status = (str(exc), 409 if isinstance(exc, Conflict) else 400)
        return (render_profile('malware_family_delete.html', family=family, error=error), status)

    @app.route(f'{spec.path}/<fid>/osint/new', methods=['GET', 'POST'], endpoint=f'{spec.key}_osint_edit')
    @app.route(f'{spec.path}/<fid>/osint/<eid>/edit', methods=['GET', 'POST'], endpoint=f'{spec.key}_osint_edit')
    def families_osint_edit(fid, eid=None):
        require(True)
        family = get_family(fid)
        entry = db().execute(f'SELECT * FROM {spec.osint_table} WHERE id=? AND {spec.foreign_key}=?', (eid, fid)).fetchone() if eid else None
        if eid and (not entry):
            abort(404)
        count = db().execute(f'SELECT count(*) FROM {spec.osint_table} WHERE {spec.foreign_key}=?', (fid,)).fetchone()[0]
        values = request.form if request.method == 'POST' else dict(entry) if entry else {'position': count + 1}
        error, status = (None, 200)
        if request.method == 'POST':
            try:
                title = request.form.get('title', '').strip()
                if not title or len(title) > 300:
                    raise ValueError('Enter an article title of 1–300 characters.')
                url = safe_url(request.form.get('url', '').strip())
                try:
                    position = int(request.form.get('position', ''))
                except ValueError:
                    raise ValueError('Enter a valid display position.')
                if not 1 <= position <= count + (0 if eid else 1) or (not eid and count >= 1000):
                    raise ValueError('Choose a display position within this list (up to 1,000 entries).')
                with db():
                    touch(fid, version())
                    ordered = [r[0] for r in db().execute(f'SELECT id FROM {spec.osint_table} WHERE {spec.foreign_key}=? AND id<>? ORDER BY position,id', (fid, eid or ''))]
                    saved_id = eid or str(uuid.uuid4())
                    db().execute(f'UPDATE {spec.osint_table} SET position=-position WHERE {spec.foreign_key}=?', (fid,))
                    if eid:
                        db().execute(f'UPDATE {spec.osint_table} SET title=?,url=? WHERE id=?', (title, url, eid))
                    else:
                        db().execute(f'INSERT INTO {spec.osint_table} VALUES(?,?,?,?,0)', (saved_id, fid, title, url))
                    ordered.insert(position - 1, saved_id)
                    for index, entry_id in enumerate(ordered, 1):
                        db().execute(f'UPDATE {spec.osint_table} SET position=? WHERE id=?', (index, entry_id))
                    event(f"{spec.singular} OSINT {('edited' if eid else 'added')}: family={fid}, entry={saved_id}")
                flash('OSINT link saved.')
                return finish(fid, 'osint')
            except (ValueError, sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                error = 'Unable to save right now. Your entered values are preserved; please retry.' if isinstance(exc, sqlite3.OperationalError) else str(exc)
                status = 503 if isinstance(exc, sqlite3.OperationalError) else 409 if isinstance(exc, (Conflict, sqlite3.IntegrityError)) else 400
        return (render_profile('malware_osint_form.html', family=family, values=values, entry=entry, count=count, error=error), status)

    @app.post(f'{spec.path}/<fid>/osint/<eid>/delete', endpoint=f'{spec.key}_osint_delete')
    def families_osint_delete(fid, eid):
        require(True)
        get_family(fid)
        if not db().execute(f'SELECT 1 FROM {spec.osint_table} WHERE {spec.foreign_key}=? AND id=?', (fid, eid)).fetchone():
            abort(404)
        try:
            with db():
                touch(fid, version())
                db().execute(f'DELETE FROM {spec.osint_table} WHERE {spec.foreign_key}=? AND id=?', (fid, eid))
                ids = [r[0] for r in db().execute(f'SELECT id FROM {spec.osint_table} WHERE {spec.foreign_key}=? ORDER BY position,id', (fid,))]
                for index, entry_id in enumerate(ids, 1):
                    db().execute(f'UPDATE {spec.osint_table} SET position=? WHERE id=?', (index, entry_id))
                event(f'{spec.singular} OSINT removed: family={fid}, entry={eid}')
            flash('OSINT link removed.')
        except ValueError as exc:
            flash(str(exc))
        return redirect(url_for(f'{spec.key}_workspace', fid=fid, tab='osint'))
    from family_reports import register_reports
    with app.app_context():
        if not prototype(db()):
            register_reports(app, db, ROOT, require, get_family, touch, event, finish, version, spec=spec)
