"""Case IOC table storage and CSV import."""
import csv
import io
import json
import re
import copy
import os
import tempfile
import uuid
import hashlib
import shutil
from datetime import datetime
from flask import request, abort, g, send_file, after_this_request
from indicator_types import CATALOG, analyze, inspect_sections, canonical_type, duplicate_key
from indicator_stix import reconcile_rows, build_bundle, import_document
DEFAULT_COLUMNS = ['type', 'value', 'description']
DEFAULT_SECTION_TITLE = 'Indicators extracted during analysis'
DEFAULT_SECTION_DESCRIPTION = 'The following table contains indicators extracted during analysis of the malicious artifact.'


def validate_table(columns, rows):
    if columns != DEFAULT_COLUMNS:
        raise ValueError('Columns are fixed: type, value, description.')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('A table can contain at most 10,000 indicators.')
    if any(not isinstance(row, list) or len(row) != len(columns) or any(not isinstance(v, str) or len(v) > 4000 for v in row) for row in rows):
        raise ValueError(
            'Every row must match the columns; cells are limited to 4,000 characters.')
    return columns, rows


def parse_csv(raw, has_file_header):
    parsed = list(csv.reader(io.StringIO(
        raw.decode('utf-8-sig'), newline=''), strict=True))
    parsed = [row for row in parsed if any(v.strip() for v in row)]
    if not parsed:
        raise ValueError('CSV contains no rows.')
    headers = [v.strip().casefold() for v in parsed[0]]
    is_header = all(name in headers for name in DEFAULT_COLUMNS)
    if has_file_header and not is_header:
        raise ValueError(
            'CSV files require type, value, and description headers (case insensitive).')
    if is_header:
        if any(headers.count(name) != 1 for name in DEFAULT_COLUMNS):
            raise ValueError('Each required CSV header must appear once.')
        positions = [headers.index(name) for name in DEFAULT_COLUMNS]
        if any(len(row) != len(headers) for row in parsed[1:]):
            raise ValueError('CSV rows must match the header width.')
        return [[row[i] for i in positions] for row in parsed[1:]]
    if any(len(row) != 3 for row in parsed):
        raise ValueError(
            'Headerless pasted CSV must have three fields: type, value, description.')
    return parsed


def migrate_fixed_columns(connection):
    # Preserve original custom tables before switching to the fixed schema.
    with connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS indicator_table_legacy(case_id INTEGER PRIMARY KEY,columns TEXT,rows TEXT,revision INTEGER)')
        connection.execute('BEGIN IMMEDIATE')
        migrated = []
        for row in connection.execute('SELECT * FROM indicator_tables').fetchall():
            columns = json.loads(row['columns'])
            if columns == DEFAULT_COLUMNS:
                continue
            rows = json.loads(row['rows'])
            names = [c.strip().casefold() for c in columns]
            aliases = [('type', 'kind'), ('value', 'observable'),
                       ('description', 'context')]
            indices = [next((i for i, c in enumerate(names) if c in keys), index if index < len(
                columns) else None) for index, keys in enumerate(aliases)]
            normalized = [
                [values[i] if i is not None else '' for i in indices] for values in rows]
            connection.execute('INSERT OR IGNORE INTO indicator_table_legacy VALUES(?,?,?,?)',
                               (row['case_id'], row['columns'], row['rows'], row['revision']))
            connection.execute('UPDATE indicator_tables SET columns=?,rows=?,revision=revision+1 WHERE case_id=?',
                               (json.dumps(DEFAULT_COLUMNS), json.dumps(normalized), row['case_id']))
            migrated.append(row['case_id'])
        return migrated


def validate_sections(sections, *, allow_new_meta=False):
    if not isinstance(sections, list) or not 1 <= len(sections) <= 100:
        raise ValueError('Use between 1 and 100 indicator sections.')
    ids = set()
    total = 0
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError('Invalid indicator section.')
        sid = section.get('id')
        title = section.get('title')
        description = section.get('description')
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', sid) or sid in ids:
            raise ValueError('Sections require unique identifiers.')
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('Section titles must contain 1–200 characters.')
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError(
                'Section descriptions are limited to 4,000 characters.')
        validate_table(DEFAULT_COLUMNS, section.get('rows'))
        metadata=section.get('row_meta')
        if metadata is not None:
            if not isinstance(metadata,list) or len(metadata)!=len(section['rows']):raise ValueError('Row identity metadata must match the rows.')
            for meta in metadata:
                if meta is None:
                    if allow_new_meta:continue
                    raise ValueError('Saved indicator row identities cannot be null.')
                if not isinstance(meta,dict):raise ValueError('Malformed indicator row identity metadata.')
                if 'original_type' in meta and (not isinstance(meta['original_type'],str) or len(meta['original_type'])>4000):raise ValueError('Original type provenance is limited to 4,000 characters.')
                if 'to_ids' in meta and not isinstance(meta['to_ids'],bool):raise ValueError('Detection intent to_ids must be a boolean.')
                if allow_new_meta and set(meta)<= {'original_type','to_ids'}:continue
                if set(meta)-{'original_type','to_ids'}!={'id','created','modified','digest'}:raise ValueError('Malformed indicator row identity metadata.')
                try:
                    if not meta['id'].startswith('indicator--'):raise ValueError()
                    uuid.UUID(meta['id'][11:])
                    created=datetime.fromisoformat(meta['created'].replace('Z','+00:00'))
                    modified=datetime.fromisoformat(meta['modified'].replace('Z','+00:00'))
                    if created.tzinfo is None or modified.tzinfo is None or modified<created or not re.fullmatch('[a-f0-9]{64}',meta['digest']):raise ValueError()
                except (ValueError,TypeError,KeyError,AttributeError):raise ValueError('Invalid indicator row identity or timestamp.')
        group=section.get('stix_meta')
        if group is not None:
            try:
                if not isinstance(group,dict) or set(group)!={'id','created','modified','digest'} or not group['id'].startswith('grouping--'):raise ValueError()
                uuid.UUID(group['id'][10:])
                created=datetime.fromisoformat(group['created'].replace('Z','+00:00'));modified=datetime.fromisoformat(group['modified'].replace('Z','+00:00'))
                if created.tzinfo is None or modified.tzinfo is None or modified<created or not re.fullmatch('[a-f0-9]{64}',group['digest']):raise ValueError()
            except (ValueError,TypeError,KeyError,AttributeError):raise ValueError('Invalid indicator section STIX identity metadata.')
        ids.add(sid)
        total += len(section['rows'])
    if 'default' not in ids:
        raise ValueError('The default indicator section cannot be deleted.')
    if total > 10000:
        raise ValueError(
            'All sections together can contain at most 10,000 indicators.')
    identities=[meta['id'] for s in sections for meta in s.get('row_meta',[]) if meta and 'id' in meta]
    identities += [s['stix_meta']['id'] for s in sections if s.get('stix_meta')]
    if len(identities)!=len(set(identities)):raise ValueError('Indicator row identities must be unique within the case.')
    return [{'id': s['id'], 'title': s['title'].strip(), 'description': s['description'], 'rows': s['rows'], **({'row_meta':s['row_meta']} if 'row_meta' in s else {}), **({'stix_meta':s['stix_meta']} if s.get('stix_meta') else {})} for s in sections]


def load_table(db, cid):
    row = db().execute('SELECT * FROM indicator_tables WHERE case_id=?', (cid,)).fetchone()
    result = {'columns': json.loads(row['columns']), 'rows': json.loads(row['rows']), 'revision': row['revision']} if row else {
        'columns': DEFAULT_COLUMNS.copy(), 'rows': [], 'revision': 0}
    section_row = db().execute(
        'SELECT sections FROM indicator_sections WHERE case_id=?', (cid,)).fetchone()
    result['sections'] = json.loads(section_row['sections']) if section_row else [
        {'id': 'default', 'title': DEFAULT_SECTION_TITLE, 'description': DEFAULT_SECTION_DESCRIPTION, 'rows': result['rows']}]
    return result


def migrate_section_defaults(connection):
    changed = []
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT 1 FROM schema_migrations WHERE name='indicator-section-default-wording'").fetchone():
            return []
        for row in connection.execute('SELECT * FROM indicator_sections').fetchall():
            sections = json.loads(row['sections'])
            default = next((s for s in sections if s['id'] == 'default'), None)
            if default is None:
                sections.insert(0, {'id': 'default', 'title': DEFAULT_SECTION_TITLE,
                                'description': DEFAULT_SECTION_DESCRIPTION, 'rows': []})
            elif default['title'] == 'Default' and not default['description']:
                default['title'] = DEFAULT_SECTION_TITLE
                default['description'] = DEFAULT_SECTION_DESCRIPTION
            else:
                continue
            connection.execute('UPDATE indicator_sections SET sections=? WHERE case_id=?', (json.dumps(
                sections), row['case_id']))
            connection.execute(
                'UPDATE indicator_tables SET revision=revision+1 WHERE case_id=?', (row['case_id'],))
            changed.append(row['case_id'])
        connection.execute(
            "INSERT INTO schema_migrations VALUES('indicator-section-default-wording')")
    return changed


def report_table(table):
    # Use the same type-aware value pipeline as STIX; preserve all other cells.
    from indicator_types import csv_row
    def rows(values): return [csv_row(row) for row in values if any(v.strip() for v in row)]
    result = {'columns': table['columns'], 'rows': rows(table['rows'])}
    if 'sections' in table:
        result['sections'] = [
            {**section, 'rows': rows(section['rows'])} for section in table['sections']]
    return result


def indicator_csv(table):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(DEFAULT_COLUMNS+['section', 'section_description'])
    for section in report_table(table)['sections']:
        writer.writerows([row+[section['title'], section['description']]
                         for row in section['rows']])
    return buffer.getvalue()


def describe_table(table):
    result=copy.deepcopy(table)
    result['stix']=build_bundle(result['sections'])[1]
    result['types']=CATALOG
    return result


def recover_output(root, table, rollback=False):
    directory=root.parent.parent/'.indicator-output-recovery'
    marker=directory/'manifest.json'
    if not marker.is_file():
        if directory.is_dir():shutil.rmtree(directory)  # Publication never began.
        return
    manifest=json.loads(marker.read_text())
    digest=hashlib.sha256(json.dumps(table['sections'],sort_keys=True).encode()).hexdigest()
    if rollback or digest!=manifest['sections']:
        for filename,existed in manifest['old'].items():
            if filename not in ('indicators.csv','indicators.stix.json'):raise ValueError('Invalid indicator recovery filename.')
            if existed:os.replace(directory/filename,root/filename)
            else:(root/filename).unlink(missing_ok=True)
    shutil.rmtree(directory)


def journal_outputs(root, table):
    directory=root.parent.parent/'.indicator-output-recovery'
    directory.mkdir(mode=0o700)
    old={}
    for filename in ('indicators.csv','indicators.stix.json'):
        path=root/filename;old[filename]=path.is_file()
        if old[filename]:shutil.copy2(path,directory/filename)
    manifest={'sections':hashlib.sha256(json.dumps(table['sections'],sort_keys=True).encode()).hexdigest(),'old':old}
    for filename,existed in old.items():
        if existed:
            with (directory/filename).open('rb') as backup:os.fsync(backup.fileno())
    from case_sync import durable_json
    durable_json(directory/'manifest.json',manifest)



def stix_file_is_current(db, cid, path):
    expected,report=build_bundle(load_table(db,cid)['sections'])
    if expected is None or not path.is_file():return False
    try:return path.read_text(encoding='utf-8')==expected
    except (UnicodeError,OSError):return False


def refresh_stix_output(root, sections):
    bundle,report=build_bundle(sections)
    path=root/'indicators.stix.json'
    if bundle is None:
        path.unlink(missing_ok=True)
    else:
        try:current=path.read_text(encoding='utf-8') if path.is_file() else None
        except (UnicodeError,OSError):current=None
        if current==bundle:return report
        root.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.indicator-',suffix='.pending',dir=root.parent.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as output:
                output.write(bundle);output.flush();os.fsync(output.fileno())
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
    return report


def publish_outputs(root, table):
    """Stage complete files, replace atomically; remove stale STIX first."""
    bundle,report=build_bundle(table['sections'])
    root.mkdir(parents=True,exist_ok=True)
    staged=[]
    try:
        for filename,content in [('indicators.csv',indicator_csv(table)),('indicators.stix.json',bundle)]:
            if content is None:continue
            recovery=root.parent.parent/'.indicator-output-recovery'
            fd,path=tempfile.mkstemp(prefix='.indicator-',suffix='.pending',dir=recovery if recovery.is_dir() else root.parent.parent)
            with os.fdopen(fd,'w',encoding='utf-8',newline='') as output:
                output.write(content);output.flush();os.fsync(output.fileno())
            staged.append((path,root/filename))
        (root/'indicators.stix.json').unlink(missing_ok=True)
        for source,target in staged:os.replace(source,target)
    finally:
        for source,target in staged:
            if os.path.exists(source):os.unlink(source)
    return report


def register_indicators(app, ROOT, db, case, package, ensure_package, mark_pending, audit):
    with app.app_context():
        db().execute('CREATE TABLE IF NOT EXISTS indicator_tables(case_id INTEGER PRIMARY KEY REFERENCES cases(id),columns TEXT NOT NULL,rows TEXT NOT NULL,revision INTEGER NOT NULL)')
        db().commit()
        db().execute('CREATE TABLE IF NOT EXISTS indicator_sections(case_id INTEGER PRIMARY KEY REFERENCES cases(id),sections TEXT NOT NULL)')
        db().commit()
        migrated = migrate_fixed_columns(db())
        migrated = list(set(migrated+migrate_section_defaults(db())))
        for cid in migrated:
            table = load_table(db, cid)
            (ensure_package(cid)/'iocs/indicators.csv').write_text(indicator_csv(table))
            mark_pending(cid, 'iocs/indicators.csv')
            mark_pending(cid, 'reports/sections')

    for directory in (ROOT/'cases').glob('*/.indicator-output-recovery'):
        try:cid=int(directory.parent.name)
        except ValueError:continue
        with app.app_context():recover_output(package(cid)/'iocs',load_table(db,cid))

    @app.after_request
    def finish_indicator_outputs(response):
        for cid in getattr(g,'indicator_outputs',[]):
            recover_output(package(cid)/'iocs',load_table(db,cid),rollback=response.status_code>=400)
        return response

    def queue_outputs(cid,table):
        @after_this_request
        def publish(response):
            if response.status_code<400:
                root=ensure_package(cid)/'iocs'
                recover_output(root,load_table(db,cid))
                journal_outputs(root,table)
                g.indicator_outputs=getattr(g,'indicator_outputs',[])+[cid]
                try:publish_outputs(root,table)
                except Exception:
                    recover_output(root,table,rollback=True)
                    raise
            return response

    def save(cid, columns, rows, revision, sections=None):
        validate_table(columns, rows)
        connection = db()
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            c = case(cid)
            if c['stage'] not in (1, 2):
                raise ValueError(
                    'Start analysis or reopen the case before editing indicators.')
            current = load_table(db, cid)
            if revision != current['revision']:
                raise ValueError(
                    'The table changed in another session. Reload before saving; your edits have not been applied.')
            if sections is None:
                if len(current['sections']) != 1:
                    raise ValueError(
                        'Save all sections together to preserve their grouping.')
                sections = [{**{key:value for key,value in current['sections'][0].items() if key!='row_meta'}, 'rows': rows}]
            sections = reconcile_rows(validate_sections(sections, allow_new_meta=True), current['sections'])
            if sections == current['sections']:
                result=describe_table(current)
                queue_outputs(cid,current)
                return result
            rows = [row for section in sections for row in section['rows']]
            connection.execute('INSERT OR REPLACE INTO indicator_tables VALUES(?,?,?,?)',
                               (cid, json.dumps(columns), json.dumps(rows), revision+1))
            connection.execute(
                'INSERT OR REPLACE INTO indicator_sections VALUES(?,?)', (cid, json.dumps(sections)))
        table = load_table(db, cid)
        root = ensure_package(cid)/'iocs'
        queue_outputs(cid,table)
        mark_pending(cid, 'iocs/indicators.csv')
        mark_pending(cid, 'reports/sections')
        audit(f'Updated indicators for case {cid}')
        return describe_table(table)

    app.extensions['indicator_save']=save

    def append_rows(cid, current, rows, originals=None, intents=None):
        sections = current['sections']
        target = request.form.get('section_id', sections[0]['id'])
        section = next((s for s in sections if s['id'] == target), None)
        if section is None:
            raise ValueError('Choose an existing indicator section.')
        original_count=len(section['rows'])
        section['rows'] = section['rows']+rows
        if originals or intents or 'row_meta' in section:
            section.setdefault('row_meta',[None]*original_count)
            section['row_meta'] += [({**({'original_type':value} if value is not None else {}),**({'to_ids':intent} if intent is not None else {})} or None) for value,intent in zip(originals or [None]*len(rows),intents or [None]*len(rows))]
        return save(cid, current['columns'], [], int(request.form['revision']), sections)

    @app.get('/cases/<int:cid>/indicators')
    def indicators_data(cid): case(cid); return describe_table(load_table(db, cid))

    @app.post('/cases/<int:cid>/indicators')
    def indicators_save(cid):
        case(cid)
        try:
            return save(cid, json.loads(request.form.get('columns', json.dumps(DEFAULT_COLUMNS))), json.loads(request.form.get('rows', '[]')), int(request.form['revision']), json.loads(request.form['sections']) if 'sections' in request.form else None)
        except (ValueError, KeyError, TypeError) as exc:
            return {'error': str(exc)}, 409

    @app.get('/cases/<int:cid>/indicators/stix')
    def indicators_stix_download(cid):
        case(cid)
        table=load_table(db,cid)
        expected,report=build_bundle(table['sections'])
        path=package(cid)/'iocs/indicators.stix.json'
        if not stix_file_is_current(db,cid,path):
            return {'error':'STIX is unavailable. Save current edits and correct all flagged rows first.','stix':report},409
        return send_file(path,mimetype='application/stix+json',as_attachment=True,download_name='indicators.stix.json')

    @app.post('/cases/<int:cid>/indicators/import/preview')
    def indicators_import_preview(cid):
        case(cid)
        try:
            current=load_table(db,cid)
            target=next((s for s in current['sections'] if s['id']==request.form.get('section_id')),None)
            if target is None:raise ValueError('Choose an existing indicator section.')
            kind=request.form.get('format','csv')
            if kind not in ('csv','stix'):raise ValueError('Choose CSV or STIX.')
            upload=request.files.get(kind)
            raw=upload.read(4*1024*1024+1) if upload else request.form.get(kind,'').encode()
            if len(raw)>4*1024*1024:raise ValueError('Imports are limited to 4 MiB.')
            rows,skipped,originals,intents=import_document(raw,with_provenance=True,with_intent=True) if kind=='stix' else (parse_csv(raw,upload is not None),[],None,None)
            validate_table(DEFAULT_COLUMNS,rows)
            existing={key for row in target['rows'] if (key:=duplicate_key(row)) is not None}
            preview=[]
            for index,row in enumerate(rows):
                result=analyze(row);duplicate=duplicate_key(row, result=result) in existing
                preview.append({'row':result['row'],'reason':result.get('error',''),'duplicate':duplicate,'normalized':bool(result.get('normalized')),'unknown':canonical_type(row[0]) is None,'original_type':originals[index] if originals else None,'to_ids':intents[index] if intents else None})
            return {'section_id':target['id'],'section':target['title'],'rows':preview,'skipped':skipped,'revision':current['revision']}
        except (ValueError,TypeError,KeyError,UnicodeError,csv.Error,RecursionError) as exc:return {'error':str(exc)},400

    @app.post('/cases/<int:cid>/indicators/import')
    def indicators_import(cid):
        case(cid)
        try:
            current = load_table(db, cid)
            if 'accepted_rows' in request.form:
                rows=json.loads(request.form['accepted_rows']);validate_table(DEFAULT_COLUMNS,rows)
                target=next((s for s in current['sections'] if s['id']==request.form.get('section_id')),None)
                if target is None:raise ValueError('Choose an existing indicator section.')
                existing={key for row in target['rows'] if (key:=duplicate_key(row)) is not None}
                originals=json.loads(request.form.get('accepted_original_types','null')) or [None]*len(rows)
                if not isinstance(originals,list) or len(originals)!=len(rows) or any(value is not None and (not isinstance(value,str) or len(value)>4000) for value in originals):raise ValueError('Invalid original type provenance.')
                intents=json.loads(request.form.get('accepted_intents','null')) or [None]*len(rows)
                if not isinstance(intents,list) or len(intents)!=len(rows) or any(value is not None and not isinstance(value,bool) for value in intents):raise ValueError('Invalid detection intent.')
                accepted=[];accepted_originals=[];accepted_intents=[];skipped=0
                for row,original,intent in zip(rows,originals,intents):
                    result=analyze(row);key=duplicate_key(row, result=result)
                    if request.form.get('skip_duplicates','1')=='1' and key in existing:skipped+=1;continue
                    accepted.append(row);accepted_originals.append(original);accepted_intents.append(intent)
                    if key:existing.add(key)
                result=append_rows(cid,current,accepted,accepted_originals,accepted_intents);result.update(added=len(accepted),skipped_duplicates=skipped);return result
            upload = request.files.get('csv')
            raw = upload.read(
                4*1024*1024+1) if upload else request.form.get('csv', '').encode()
            if len(raw) > 4*1024*1024:
                raise ValueError('CSV imports are limited to 4 MiB.')
            rows = parse_csv(raw, upload is not None)
            result = append_rows(cid, current, rows)
            result['added'] = len(rows)
            return result
        except (ValueError, KeyError, UnicodeError, csv.Error) as exc:
            return {'error': str(exc)}, 400
