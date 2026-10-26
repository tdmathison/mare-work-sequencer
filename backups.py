from tagging import portable as portable_tags, validate_portable as validate_tags, restore as restore_tags, prototype as tag_prototype
"""Portable case backups: nested RAW packages plus validated workbench metadata."""
import hashlib
from contextlib import closing
import io
import json
import re
import shutil
import stat
import tempfile
import zipfile
import sqlite3
from pathlib import Path, PurePosixPath
from flask import url_for, request, g, render_template, send_file, flash, redirect
from indicators import load_table, validate_sections, DEFAULT_COLUMNS
from references import load_references
from reporting import SECTIONS, is_backup
from mip import CATEGORIES
from zip_metadata import copied_info, generated_info, restore_mtime
SCHEMA = 'mare-case-backup/3'
MAX_TOTAL = 2*1024**3
MAX_FILE = 256*1024**2
MAX_METADATA = 64*1024**2


def json_bytes(value): return json.dumps(
    value, ensure_ascii=False, indent=2).encode('utf-8')


def safe_name(name):
    parts = name.rstrip('/').split('/')
    if not name or name.startswith('/') or '\\' in name or ':' in name or '\x00' in name or any(part in ('', '..', '.') for part in parts):
        raise ValueError('The archive contains an unsafe path.')
    return parts


def checked_members(archive):
    members = {}
    if len(archive.infolist()) > 100000:
        raise ValueError('Too many archive entries.')
    total = 0
    for info in archive.infolist():
        safe_name(info.filename)
        if info.filename in members or info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(
                'Duplicate, encrypted, or symbolic-link entries are not supported.')
        total += info.file_size
        if info.file_size > MAX_FILE or total > MAX_TOTAL:
            raise ValueError('Backup exceeds the import size limits.')
        members[info.filename] = info
    return members, total


def read_json(archive, name):
    if archive.getinfo(name).file_size > MAX_METADATA:
        raise ValueError('Backup metadata is too large.')
    result = json.loads(archive.read(name))
    if not isinstance(result, dict):
        raise ValueError('Invalid backup metadata.')
    return result


def text(value, limit=1000000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Invalid text in backup metadata.')
    return value


def records(meta, name, fields):
    values = meta.get('records', {}).get(name, [])
    if not isinstance(values, list) or len(values) > 100000:
        raise ValueError('Invalid case records.')
    result = []
    for row in values:
        if not isinstance(row, dict):
            raise ValueError('Invalid case record.')
        out = {}
        for field, default in fields.items():
            value = row.get(field, default)
            if isinstance(default, int):
                if not isinstance(value, int):
                    raise ValueError('Invalid numeric case record.')
            else:
                value = text(value if value is not None else '')
            out[field] = value
        result.append(out)
    return result


def validate_metadata(meta, *, allow_legacy_tags=False):
    if meta.get('schema') not in ('mare-case-state/1', 'mare-case-state/2'):
        raise ValueError('Unsupported case metadata version.')
    if meta.get('schema') == 'mare-case-state/2' and (not {'notes','tasks','history','deferred','readiness','artifacts'}.issubset(meta.get('records',{})) or not {'images','figure_sequence','indicators','references','tagging','source_creator'}.issubset(meta)):
        raise ValueError('Incomplete modern case snapshot.')
    c = meta['case']
    text(c['name'], 200)
    text(c.get('description', ''))
    text(c.get('number', ''), 200)
    if not c['name'].strip() or c.get('stage') not in range(4):
        raise ValueError('Invalid source case.')
    if c.get('external_system', '') not in ('', 'Vortex', 'XSIAM', 'JIRA'):
        raise ValueError('Invalid external case system.')
    text(c.get('external_number', ''), 200)
    if bool(c.get('external_system')) != bool(c.get('external_number')):
        raise ValueError('Invalid external case reference.')
    from reporting import valid_report_path
    if c.get('report_path') and not valid_report_path(c['report_path']):
        raise ValueError('Invalid current report path.')
    sections = validate_sections(meta['indicators']['sections'])
    refs = meta['references']['rows']
    if not isinstance(refs, list) or len(refs) > 10000 or any(not isinstance(r, list) or len(r) != 2 or any(not isinstance(v, str) or len(v) > 4000 for v in r) for r in refs):
        raise ValueError('Invalid references table.')
    clean = {
        'notes': records(meta, 'notes', {'title': '', 'body': '', 'author': '', 'created': '', 'include_export': 0}),
        'tasks': records(meta, 'tasks', {'title': '', 'body': '', 'state': 'Not Started', 'priority': 'Normal', 'created': ''}),
        'history': records(meta, 'history', {'stage': 0, 'author': '', 'created': '', 'outcome': 'Done', 'reason': ''}),
        'deferred': records(meta, 'deferred', {'stage': 0, 'reason': '', 'resolved': 0}),
        'readiness': records(meta, 'readiness', {'category': '', 'status': 'Pending', 'reason': ''}),
        'artifacts': records(meta, 'artifacts', {'path': '', 'description': ''})}
    for row in clean['notes']:
        if row['include_export'] not in (0, 1):
            raise ValueError('Invalid note state.')
    for row in clean['tasks']:
        if row['state'] not in ('Not Started', 'In Progress', 'Completed') or row['priority'] not in ('Low', 'Normal', 'High', 'Critical'):
            raise ValueError('Invalid task state.')
        text(row['title'], 200)
    for row in clean['history']+clean['deferred']:
        if row['stage'] not in range(4):
            raise ValueError('Invalid history stage.')
    for row in clean['deferred']:
        if row['resolved'] not in (0, 1):
            raise ValueError('Invalid deferred state.')
    if len({r['category'] for r in clean['readiness']}) != len(clean['readiness']) or len({r['stage'] for r in clean['deferred']}) != len(clean['deferred']):
        raise ValueError('Duplicate case records.')
    for row in clean['readiness']:
        if row['category'] not in CATEGORIES or row['status'] not in ('Pending', 'Populated', 'Not applicable'):
            raise ValueError('Invalid readiness category.')
    if len({r['path'] for r in clean['artifacts']}) != len(clean['artifacts']):
        raise ValueError('Duplicate artifact paths.')
    images = meta.get('images', [])
    if not isinstance(images, list) or len(images) > 10000:
        raise ValueError('Invalid report image metadata.')
    names = set()
    for image in images:
        if (image['section'] not in SECTIONS and image['section'] != 'task-draft' and not re.fullmatch(r'task-[0-9]+', image['section'])) or not re.fullmatch(r'report-image-[a-f0-9]{32}\.png', image['name']) or image['name'] in names or not isinstance(image['figure'], int) or image['figure'] < 1:
            raise ValueError('Invalid report image metadata.')
        names.add(image['name'])
    sequence = meta.get('figure_sequence', 0)
    if not isinstance(sequence, int) or not 0 <= sequence < 9223372036854775807:
        raise ValueError('Invalid figure sequence.')
    return c, sections, refs, clean, images, max([sequence]+[i['figure'] for i in images]), validate_tags(meta.get('tagging'), allow_legacy=allow_legacy_tags)


def register_backups(app, ROOT, db, case, package, ensure_package, build_archive, allocate, audit, now):
    def case_metadata(cid):
        c = case(cid)
        data = {'schema': 'mare-case-state/2', 'case': {key: c[key] for key in ('number', 'name', 'description', 'stage', 'external_system', 'external_number', 'created', 'report_path')}, 'records': {
        }, 'indicators': load_table(db, cid), 'references': load_references(db, cid)}
        owner = db().execute('SELECT username,user_uuid FROM users WHERE id=?',
                             (c['owner'],)).fetchone()
        data['case']['assigned_user'] = dict(owner) if owner else None
        for key in ('description', 'external_system', 'external_number'):
            data['case'][key] = data['case'][key] or ''
        for table in ('notes', 'tasks', 'history', 'deferred', 'readiness', 'artifacts'):
            data['records'][table] = [{k: row[k] for k in row.keys() if k not in (
                'id', 'case_id', 'usage')} for row in db().execute(f'SELECT * FROM {table} WHERE case_id=?', (cid,))]
        data['records']['artifacts'] = [r for r in data['records']['artifacts'] if (package(
            cid)/r['path']).is_file() and r['path'].split('/')[0] in CATEGORIES and not is_backup(r['path'])]
        data['images'] = [dict(row) for row in db().execute('SELECT section,name,figure FROM report_images WHERE case_id=?', (cid,)) if (
            package(cid)/'reports/sections/assets'/row['name']).is_file()]
        seq = db().execute('SELECT value FROM figure_sequence WHERE case_id=?', (cid,)).fetchone()
        data['figure_sequence'] = seq[0] if seq else 0
        if tag_prototype(db()): raise ValueError('Migrate prototype tags before exporting RAW backups.')
        data['tagging'] = portable_tags(db(), cid)
        creator = db().execute('SELECT username,user_uuid FROM users WHERE id=?', (c['creator'],)).fetchone()
        data['source_creator'] = dict(creator) if creator else {'username': c['creator_username'] or 'Unknown', 'user_uuid': None}
        return data

    def case_backup(cid, email_safe=False, include_samples=False):
        raw, name = build_archive(cid, 'raw', include_samples=include_samples)
        out = tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            meta = case_metadata(cid)
            meta['sync'] = app.extensions['case_sync'].export(cid)
            renamed = {}
            with zipfile.ZipFile(raw) as source:
                manifest = read_json(source, name+'/manifest.json')
                if email_safe:
                    for item in manifest['files']:
                        if item['path'].lower().endswith('.py'):
                            renamed[item['path']] = item['path'][:-3]+'_py.txt'
                    paths = [renamed.get(item['path'], item['path'])
                             for item in manifest['files']]
                    if len(paths) != len(set(paths)):
                        raise ValueError(
                            'Python filename conversion would overwrite another file. Rename the conflicting asset first.')
                    for record in meta['records']['artifacts']:
                        record['path'] = renamed.get(
                            record['path'], record['path'])
                    meta['file_name_encoding'] = 'python-email-v1'
                data = json_bytes(meta)
                if len(data) > MAX_METADATA:
                    raise ValueError('Case metadata exceeds the backup limit.')
                with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
                    for info in source.infolist():
                        if info.filename == name+'/manifest.json':
                            continue
                        rel = info.filename[len(name)+1:]
                        destination = name+'/'+renamed.get(rel, rel)
                        with source.open(info) as src, target.open(copied_info(info, destination), 'w') as dst:
                            shutil.copyfileobj(src, dst)
                    for item in manifest['files']:
                        item['path'] = renamed.get(item['path'], item['path'])
                    target.writestr(generated_info(name+'/case-data.json'), data)
                    manifest['files'].append(
                        {'path': 'case-data.json', 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)})
                    target.writestr(generated_info(name+'/manifest.json'),
                                    json_bytes(manifest))
            if out.tell() > MAX_FILE:
                raise ValueError(
                    'The case ZIP exceeds the 256 MiB import limit.')
            out.seek(0)
            with zipfile.ZipFile(out) as archive:
                checked_members(archive)
            out.seek(0)
            return out, name
        except Exception:
            out.close()
            raise
        finally:
            raw.close()

    @app.post('/cases/<int:cid>/backup')
    def backup_single_export(cid):
        case(cid)
        if db().execute("SELECT 1 FROM report_jobs WHERE case_id=? AND status IN ('queued','running')", (cid,)).fetchone():
            flash('Wait for report generation to finish before backing up this case.')
            return redirect('/')
        try:
            out, name = case_backup(cid, True)
        except ValueError as exc:
            flash(str(exc))
            return redirect('/')
        audit(
            f'Backed up RAW case {cid} with Python filenames converted for email')
        response = send_file(out, as_attachment=True, download_name=name +
                             '-backup.zip', mimetype='application/zip')
        response.call_on_close(out.close)
        return response

    @app.post('/account/database-backup')
    def database_backup():
        from authorization import has_permission
        if g.user['role'] != 'Administrator' or not has_permission(g.user, 'backups:manage', db()):
            from flask import abort
            abort(403)
        if request.endpoint in ('database_backup','api.api_database_backup') and not getattr(g,'backup_worker',False):
            return redirect(url_for('import_export_page'))
        connection = db()
        connection.execute('BEGIN IMMEDIATE')
        out = tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            if connection.execute("SELECT 1 FROM report_jobs WHERE status IN ('queued','running')").fetchone():
                connection.rollback()
                out.close()
                flash(
                    'Wait for report generation to finish before creating the database backup.')
                return redirect(url_for('account'))
            with tempfile.TemporaryDirectory(prefix='mare-database-') as directory:
                snapshot = Path(directory)/'workflow.sqlite3'
                # Read through a second connection while the write reservation prevents database changes.
                source = sqlite3.connect(ROOT/'workflow.sqlite3')
                destination = sqlite3.connect(snapshot)
                try:
                    source.backup(destination)
                finally:
                    source.close()
                    destination.close()
                from installation_backup import add_file, record_counts, SCHEMA as INSTALLATION_SCHEMA, FAMILY_MIGRATION, ACTOR_MIGRATION
                files = {}
                with closing(sqlite3.connect(snapshot)) as snapshot_connection:
                    snapshot_connection.row_factory = sqlite3.Row
                    from family_reports import verify_report
                    if snapshot_connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_reports'").fetchone():
                        for report in snapshot_connection.execute('SELECT * FROM family_reports'):
                            verify_report(ROOT, report)
                    from profile_types import ACTOR
                    if snapshot_connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='actor_reports'").fetchone():
                        for report in snapshot_connection.execute('SELECT * FROM actor_reports'):
                            verify_report(ROOT, report, spec=ACTOR)
                    counts = record_counts(snapshot_connection)
                    family_schema = snapshot_connection.execute("SELECT 1 FROM schema_migrations WHERE name=?", (FAMILY_MIGRATION,)).fetchone() is not None
                with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
                    expanded = add_file(archive, snapshot, 'data/workflow.sqlite3', files)
                    for file in sorted(ROOT.rglob('*')):
                        rel = file.relative_to(ROOT)
                        if file.is_symlink() or not file.is_file() or rel.parts[0].startswith(('case-import-', 'report-jobs')) or rel.parts[0] in ('search-index', 'snort-jobs', 'yara-jobs', 'family-report-staging','actor-report-staging') or file.name in ('.backup.lock', '.case-sync.lock', '.maintenance.lock', 'workflow.sqlite3', 'workflow.sqlite3-wal', 'workflow.sqlite3-shm', 'workflow.sqlite3-journal'):
                            continue
                        expanded = add_file(archive, file, (Path('data')/rel).as_posix(), files, expanded=expanded)
                    # Keep the pre-feature installation format usable for an
                    # instance awaiting the explicit prototype-tag migration.
                    if family_schema:
                        metadata = json_bytes({
                            'schema': INSTALLATION_SCHEMA, 'required_migration': ACTOR_MIGRATION,
                            'created': now(), 'counts': counts, 'files': files})
                        if len(metadata) > MAX_METADATA:
                            raise ValueError('Installation metadata exceeds the recovery limit.')
                        archive.writestr(generated_info('installation.json'), metadata)
                out.seek(0)
                with zipfile.ZipFile(out) as archive:
                    checked_members(archive)
            connection.commit()
            out.seek(0)
            summary = ', '.join(f'{value} {key}' for key,value in counts.items())
            audit('Created full database and MIP content backup: '+summary)
            flash('Installation backup includes '+summary+'.')
            response = send_file(out, as_attachment=True, download_name='MARE-installation-backup-'+now()[
                                 :19].replace(':', '-')+'.zip', mimetype='application/zip')
            response.headers['X-MARE-Backup-Counts'] = json.dumps(counts, separators=(',', ':'))
            response.call_on_close(out.close)
            return response
        except ValueError as exc:
            connection.rollback()
            out.close()
            flash(str(exc))
            return redirect(url_for('account'))
        except Exception:
            connection.rollback()
            out.close()
            raise

    @app.get('/import-export')
    @app.get('/settings/import-export')
    def import_export_page():
        workspace=app.extensions['backup_workspace'];workspace.require()
        if request.path == '/import-export':
            from settings_navigation import legacy_redirect
            return legacy_redirect('import_export_page')
        return workspace.page()

    @app.post('/import-export/export')
    def backup_export():
        areas = set(getattr(g, "backup_areas", ("cases","families","tags","actors")))
        if db().execute("SELECT 1 FROM report_jobs WHERE status IN ('queued','running')").fetchone():
            flash('Wait for report generation to finish before exporting the backup.')
            return redirect(url_for('import_export_page'))
        out = tempfile.SpooledTemporaryFile(max_size=8*1024**2)
        try:
            index = {'schema': SCHEMA, 'exporter_uuid': app.extensions['case_sync'].installation(), 'created': now(), 'cases': [], 'tagging': portable_tags(db())}
            from family_portable import export_library
            from authorization import has_permission
            library = export_library(db(), ROOT, include_families="families" in areas, include_actors="actors" in areas)
            if (library['families'] or library.get('actors')) and not has_permission(g.user,'tags:read',db()):
                from flask import abort
                abort(403)
            index['family_library'] = library
            needed={f['tag'] for f in library['families'] + library.get('actors',[])}
            if 'cases' in areas:needed.update(r[0] for r in db().execute('SELECT DISTINCT t.name FROM tags t JOIN case_tags ct ON ct.tag_id=t.id'))
            registry=[dict(r) for r in db().execute('SELECT t.name,i.identity,t.created_at FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id ORDER BY t.name') if 'tags' in areas or r['name'] in needed]
            index['tag_registry']=registry
            index['tagging']['tags']=[r['name'] for r in registry]
            index['included_areas']=sorted(areas)
            if 'cases' in areas:
                index['case_numbers']={'sequence':db().execute('SELECT value FROM case_sequence WHERE id=1').fetchone()[0], 'reserved':[r[0] for r in db().execute('SELECT number FROM reserved_case_numbers ORDER BY number')]}

            total = 0
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as outer:
                from family_reports import storage_path
                from profile_types import FAMILY, ACTOR
                for report_spec, family in [(FAMILY,f) for f in library['families']] + [(ACTOR,a) for a in library.get('actors',[])]:
                    for report in family['reports']:
                        outer.write(storage_path(ROOT,report['id'],spec=report_spec), 'library/'+report['storage_ref'])
                        total += report['size']
                        if total>MAX_TOTAL:raise ValueError('Backup exceeds the 2 GiB expanded limit.')
                for row in (db().execute('SELECT id FROM cases ORDER BY id').fetchall() if 'cases' in areas else []):
                    cid = row['id']
                    inner, name = case_backup(cid, include_samples=getattr(g,"backup_include_samples",False))
                    try:
                        inner.seek(0)
                        with zipfile.ZipFile(inner) as check:
                            _, size = checked_members(check)
                        total += size
                        if total > MAX_TOTAL or len(index['cases']) >= 1000:
                            raise ValueError(
                                'Backup exceeds the import limits (1,000 cases or 2 GiB expanded).')
                        inner.seek(0)
                        path = f'cases/{cid}.zip'
                        digest = hashlib.sha256()
                        length = 0
                        with outer.open(generated_info(path, zipfile.ZIP_STORED), 'w') as destination:
                            while chunk := inner.read(1024**2):
                                destination.write(chunk)
                                digest.update(chunk)
                                length += len(chunk)
                        if length > MAX_FILE:
                            raise ValueError(
                                'A case package exceeds 256 MiB compressed.')
                        index['cases'].append(
                            {'path': path, 'size': length, 'sha256': digest.hexdigest()})
                    finally:
                        inner.close()
                metadata=json_bytes(index)
                if len(metadata)>MAX_METADATA:raise ValueError('Shared backup metadata exceeds the import limit.')
                outer.writestr(generated_info('backup.json', zipfile.ZIP_STORED), metadata)
            if out.tell() > 1024**3:
                raise ValueError('Backup exceeds the 1 GiB upload limit.')
            out.seek(0)
            audit('Exported full RAW case backup: ' +
                  str(len(index['cases']))+' cases; '+str(len(library['families']))+' malware families; '+str(sum(len(f['reports']) for f in library['families']))+' attached reports')
            response = send_file(out, as_attachment=True, download_name='MARE-case-backup-'+now()[
                                 :19].replace(':', '-')+'.zip', mimetype='application/zip')
            response.call_on_close(out.close)
            return response
        except ValueError as exc:
            out.close()
            flash(str(exc))
            return redirect(url_for('import_export_page'))
        except Exception:
            out.close()
            raise

    def stage_upload(upload, single, temporary):
        temporary = Path(temporary)
        incoming = temporary/'backup.zip'
        upload.save(incoming)
        plans = []
        total = 0
        if single:
            raw_upload = temporary/'single.zip'
            incoming.rename(raw_upload)
            digest = hashlib.sha256()
            size = 0
            with raw_upload.open('rb') as source:
                while chunk := source.read(1024**2):
                    digest.update(chunk)
                    size += len(chunk)
            with zipfile.ZipFile(incoming, 'w', zipfile.ZIP_STORED) as wrapper:
                wrapper.write(raw_upload, 'cases/1.zip')
                wrapper.writestr('backup.json', json_bytes({'schema': SCHEMA, 'cases': [
                                 {'path': 'cases/1.zip', 'sha256': digest.hexdigest(), 'size': size}]}))
        with zipfile.ZipFile(incoming) as outer:
            members, _ = checked_members(outer)
            index = read_json(outer, 'backup.json')
            tag_catalog = validate_tags(index.get('tagging'))
            if 'case_numbers' in index:
                numbers=index['case_numbers']
                if not isinstance(numbers,dict) or set(numbers)!={'sequence','reserved'} or type(numbers['sequence']) is not int or not 0<=numbers['sequence']<2**63 or not isinstance(numbers['reserved'],list) or len(numbers['reserved'])>100000 or any(not isinstance(n,str) or not n or len(n)>200 for n in numbers['reserved']):raise ValueError('Invalid case allocation metadata.')
                (temporary/'case-numbers.json').write_bytes(json_bytes(numbers))
            if 'tag_registry' in index:
                from backup_areas import validate_tags as validate_registry
                registry=validate_registry(index['tag_registry'])
                (temporary/'tag-registry.json').write_bytes(json_bytes(registry))
            entries = index.get('cases')
            if index.get('schema') not in (SCHEMA, 'mare-case-backup/2', 'mare-case-backup/1') or not isinstance(entries, list) or len(entries) > 1000:
                raise ValueError(
                    'Use an archive created by Export all cases.')
            paths = [e['path'] for e in entries]
            shared = index.get('family_library')
            library_files=[]
            shared_seen=set()
            if shared is not None:
                if not isinstance(shared,dict) or not isinstance(shared.get('families'),list):raise ValueError('Invalid shared family section.')
                from family_reports import reference, MAX_FILE as REPORT_FILE_LIMIT, MAX_REPORTS
                if len(shared['families'])>10000:raise ValueError('Too many shared families.')
                from profile_types import FAMILY, ACTOR
                if not isinstance(shared.get('actors',[]),list) or len(shared.get('actors',[]))>10000:raise ValueError('Invalid shared actor section.')
                for report_spec, family in [(FAMILY,f) for f in shared['families']] + [(ACTOR,a) for a in shared.get('actors',[])]:
                    if not isinstance(family,dict) or not isinstance(family.get('reports'),list):raise ValueError('Invalid shared report section.')
                    if len(family['reports'])>MAX_REPORTS:raise ValueError('Too many reports in one family.')
                    for report in family['reports']:
                        # Derive every destination from a validated UUID; never use
                        # an incoming storage path for extraction.
                        rel=reference(report['id'],spec=report_spec)
                        archive_path='library/'+rel
                        if archive_path in shared_seen:raise ValueError('Duplicate report in shared archive.')
                        library_files.append(archive_path);shared_seen.add(archive_path)
                        info=members.get(archive_path)
                        if info is None or info.file_size!=report['size'] or not 0<info.file_size<=REPORT_FILE_LIMIT:raise ValueError('Shared report bytes are missing or have the wrong size.')
                        total+=info.file_size
                        if total>MAX_TOTAL:raise ValueError('Backup exceeds the 2 GiB expanded limit.')
                        target=temporary/'library'/rel;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        with outer.open(info) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
                from family_portable import validate_library
                validate_library(shared,temporary/'library')
                (temporary/'family-library.json').write_bytes(json_bytes(shared))
            elif index.get('schema')==SCHEMA and not single:
                raise ValueError('Modern Export All backup is missing its shared family library.')
            if len(paths) != len(set(paths)) or set(members) != set(paths+library_files+['backup.json']):
                raise ValueError(
                    'Unexpected or duplicate files in backup archive.')
            for n, entry in enumerate(entries):
                path = entry['path']
                if not re.fullmatch(r'cases/[0-9]+\.zip', path):
                    raise ValueError('Invalid case package path.')
                raw = temporary/f'{n}.zip'
                digest = hashlib.sha256()
                size = 0
                with outer.open(path) as src, raw.open('wb') as dst:
                    while chunk := src.read(1024**2):
                        dst.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if digest.hexdigest() != entry['sha256'] or size != entry['size']:
                    raise ValueError('Case package checksum failed.')
                with zipfile.ZipFile(raw) as archive:
                    files, expanded = checked_members(archive)
                    total += expanded
                    if total > MAX_TOTAL:
                        raise ValueError(
                            'Backup exceeds the 2 GiB expanded limit.')
                    manifests = [p for p in files if p.endswith(
                        '/manifest.json') and len(safe_name(p)) == 2]
                    if len(manifests) != 1:
                        raise ValueError(
                            'A RAW case manifest is missing.')
                    manifest = read_json(archive, manifests[0])
                    prefix = manifests[0].split('/')[0]
                    if manifest.get('schema') != 'mare-mip/2.0' or manifest.get('archive_type') != 'raw' or manifest.get('package_id') != prefix:
                        raise ValueError(
                            'Only RAW case packages are supported.')
                    declared = {}
                    actual = set()
                    for item in manifest['files']:
                        rel = item['path']
                        safe_name(rel)
                        if rel in declared:
                            raise ValueError(
                                'Duplicate manifest paths.')
                        declared[rel] = item
                    folder = temporary/f'case-{n}'/'mip'
                    folder.mkdir(parents=True)
                    directories = []
                    for filename, info in files.items():
                        parts = safe_name(filename)
                        if parts[0] != prefix or len(parts) < 2:
                            raise ValueError(
                                'Unexpected RAW package root.')
                        rel = '/'.join(parts[1:])
                        if rel not in ('README.md', 'manifest.json', 'case-data.json') and (parts[1] not in CATEGORIES or is_backup(rel)):
                            raise ValueError(
                                'Unsupported RAW package content.')
                        if parts[1] in CATEGORIES and len(parts) == 2 and not info.is_dir():
                            raise ValueError(
                                'Package categories must be directories.')
                        if info.is_dir():
                            (folder/rel).mkdir(parents=True, exist_ok=True)
                            directories.append((folder/rel, info))
                            continue
                        if rel == 'manifest.json':
                            continue
                        actual.add(rel)
                        if rel not in declared:
                            raise ValueError('Unlisted package file.')
                        digest = hashlib.sha256()
                        size = 0
                        destination = folder/rel
                        destination.parent.mkdir(
                            parents=True, exist_ok=True)
                        with archive.open(info) as src, destination.open('wb') as dst:
                            while chunk := src.read(1024**2):
                                dst.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                        if digest.hexdigest() != declared[rel]['sha256'] or size != declared[rel]['size']:
                            raise ValueError(
                                'RAW package file checksum failed.')
                        restore_mtime(destination, info)
                    if actual != set(declared):
                        raise ValueError('Missing RAW package file.')
                    meta = read_json(archive, prefix+'/case-data.json')
                    validated = validate_metadata(meta)
                    for image in validated[4]:
                        if not (folder/'reports/sections/assets'/image['name']).is_file():
                            raise ValueError(
                                'A registered report image is missing.')
                    for artifact in validated[3]['artifacts']:
                        safe_name(artifact['path'])
                        if artifact['path'] not in actual:
                            raise ValueError(
                                'Artifact metadata references a missing file.')
                    if (single and meta.get('schema') == 'mare-case-state/1') or meta.get('file_name_encoding') == 'python-email-v1':
                        renames = {
                            rel: rel[:-7]+'.py' for rel in actual if rel.endswith('_py.txt')}
                        if len({renames.get(rel, rel) for rel in actual}) != len(actual):
                            raise ValueError(
                                'Python filename restoration would overwrite another file.')
                        for original, replacement in renames.items():
                            (folder/original).rename(folder/replacement)
                        for artifact in validated[3]['artifacts']:
                            artifact['path'] = renames.get(
                                artifact['path'], artifact['path'])
                    for generated in ('README.md', 'case-data.json'):
                        (folder/generated).unlink(missing_ok=True)
                    for category in CATEGORIES:
                        (folder/category).mkdir(exist_ok=True)
                    for directory, info in sorted(directories, key=lambda item: len(item[0].parts), reverse=True):
                        restore_mtime(directory, info)
                    # Store logical restored record paths; the uploaded ZIP remains unchanged.
                    meta['records'] = validated[3]
                    plans.append((folder.parent, validated, meta))
        if getattr(g,'backup_workspace',False) and not (temporary/'tag-registry.json').exists():
            # Legacy archives have no permanent tag identity. Use an archive-bound
            # transfer identity and require explicit verification of name reuse.
            names=set((tag_catalog or {}).get('tags',[]))
            for _,validated,meta in plans:names.update((meta.get('tagging') or {}).get('tags',[]))
            shared_file=temporary/'family-library.json'
            shared=json.loads(shared_file.read_text()) if shared_file.exists() else {'families':[]}
            known={f['tag']:f['tag_identity'] for f in shared['families']}
            names.update(known)
            source=temporary/('single.zip' if single else 'backup.zip')
            h=hashlib.sha256()
            with source.open('rb') as file:
                while chunk:=file.read(1024**2):h.update(chunk)
            registry=[{'name':name,'identity':known.get(name) or hashlib.sha256((h.hexdigest()+':'+name).encode()).hexdigest()[:32],'created_at':''} for name in sorted(names)]
            (temporary/'tag-registry.json').write_bytes(json_bytes(registry))
        return plans, tag_catalog

    def shared_preview(directory):
        if getattr(g,'backup_workspace',False):
            from backup_areas import resolve
            conflicts,mappings,library=resolve(db(),ROOT,directory,getattr(g,'backup_choices',{}))
            if conflicts:raise ValueError('Resolve shared data conflicts in Backup & Restore.')
            (Path(directory)/'family-library.json').write_bytes(json_bytes(library))
            (Path(directory)/'resolved-tags.json').write_bytes(json_bytes(mappings))
        path=Path(directory)/'family-library.json'
        if not path.exists():return {'legacy':True,'profiles':0,'osint':0,'reports':0}
        from family_portable import validate_library,check_conflicts
        from authorization import has_permission
        data=json.loads(path.read_text())
        if (data['families'] or data.get('actors')) and not (has_permission(g.user,'tags:manage',db()) and has_permission(g.user,'tags:read',db())):
            from flask import abort
            abort(403,'Shared malware-family import requires profile management permission.')
        counts=validate_library(data,Path(directory)/'library')
        check_conflicts(db(),ROOT,data)
        if any(not db().execute('SELECT 1 FROM tags WHERE normalized_name=?',(f['tag'],)).fetchone() for f in data['families']+data.get('actors',[])) and not has_permission(g.user,'tags:create',db()):
            from flask import abort
            abort(403)
        return counts

    def shared_restore(directory):
        path=Path(directory)/'family-library.json'
        if not path.exists():return {'legacy':True,'profiles':0,'osint':0,'reports':0}
        shared_preview(directory)  # Recheck permissions/conflicts at apply time.
        from family_portable import restore_library
        registry_path=Path(directory)/'resolved-tags.json'
        registry=json.loads(registry_path.read_text()) if getattr(g,'backup_workspace',False) and registry_path.exists() else []
        result=restore_library(db(),ROOT,Path(directory)/'library',json.loads(path.read_text()),registry=registry)
        db().execute('INSERT INTO audit(actor,action,created) VALUES(?,?,?)',(g.user['username'],'Shared research profile library restored: '+json.dumps(result),now()))
        db().commit()
        return result

    def restore_records(connection, cid, validated):
        c, sections, refs, rows, images, sequence, tags = validated
        for table in ('notes','tasks','history','deferred','readiness','artifacts','indicator_tables','indicator_sections','reference_tables','report_images','figure_sequence'):
            connection.execute(f'DELETE FROM {table} WHERE case_id=?', (cid,))
        connection.execute('DELETE FROM case_tags WHERE case_id=?', (cid,))
        restore_tags(connection, tags, cid)
        for table, values in rows.items():
            for record in values:
                if table == 'tasks':
                    record['done'] = int(
                        record['state'] == 'Completed')
                if table == 'artifacts':
                    record['usage'] = ''
                keys = list(record)
                sql = f'INSERT INTO {table}(case_id,'+','.join(
                    keys)+') VALUES('+','.join('?' for _ in range(len(keys)+1))+')'
                connection.execute(
                    sql, [cid]+[record[key] for key in keys])
        flat = [row for section in sections for row in section['rows']]
        connection.execute('INSERT INTO indicator_tables VALUES(?,?,?,0)', (cid, json.dumps(
            DEFAULT_COLUMNS), json.dumps(flat)))
        connection.execute(
            'INSERT INTO indicator_sections VALUES(?,?)', (cid, json.dumps(sections)))
        connection.execute(
            'INSERT INTO reference_tables VALUES(?,?,0)', (cid, json.dumps(refs)))
        for image in images:
            if image['section'].startswith('task-'):
                task = connection.execute(
                    'SELECT id FROM tasks WHERE case_id=? AND instr(body,?)>0 ORDER BY id LIMIT 1', (cid, image['name'])).fetchone()
                image['section'] = f'task-{task[0]}' if task else 'task-draft'
            connection.execute('INSERT INTO report_images(case_id,section,name,figure) VALUES(?,?,?,?)', (
                cid, image['section'], image['name'], image['figure']))
        connection.execute(
            'INSERT INTO figure_sequence VALUES(?,?)', (cid, sequence))

    @app.post('/import-export/import-raw')
    @app.post('/import-export/import')
    def backup_import():
        return app.extensions['case_import_sync'].preview(request.files.get('backup'), request.path.endswith('/import-raw'))

    return {'shared_preview':shared_preview,'shared_restore':shared_restore,'case_backup': case_backup, 'case_metadata': case_metadata, 'stage_upload': stage_upload, 'restore_records': restore_records, 'single': backup_single_export, 'export': backup_export, 'import': backup_import, 'database': database_backup}
