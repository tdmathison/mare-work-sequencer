"""Case IOC table storage and CSV import."""
import csv
import io
import json
import re
import ipaddress
from flask import request, abort
from reporting import refang, defang, defang_in_text
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


def validate_sections(sections):
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
        ids.add(sid)
        total += len(section['rows'])
    if 'default' not in ids:
        raise ValueError('The default indicator section cannot be deleted.')
    if total > 10000:
        raise ValueError(
            'All sections together can contain at most 10,000 indicators.')
    return [{'id': s['id'], 'title': s['title'].strip(), 'description': s['description'], 'rows': s['rows']} for s in sections]


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
    # Analyst entries remain untouched; delivery copies are defanged.
    def cell(value):
        try:
            ipaddress.ip_address(refang(value).strip())
            return defang(value)
        except ValueError:
            return defang_in_text(value)

    def rows(values): return [[cell(v) for v in row]
                              for row in values if any(v.strip() for v in row)]
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
                sections = [{**current['sections'][0], 'rows': rows}]
            sections = validate_sections(sections)
            if request.form.get('automatic') == '1' and sections == current['sections']:
                return current
            rows = [row for section in sections for row in section['rows']]
            connection.execute('INSERT OR REPLACE INTO indicator_tables VALUES(?,?,?,?)',
                               (cid, json.dumps(columns), json.dumps(rows), revision+1))
            connection.execute(
                'INSERT OR REPLACE INTO indicator_sections VALUES(?,?)', (cid, json.dumps(sections)))
        table = load_table(db, cid)
        root = ensure_package(cid)/'iocs'
        (root/'indicators.csv').write_text(indicator_csv(table))
        mark_pending(cid, 'iocs/indicators.csv')
        mark_pending(cid, 'reports/sections')
        audit(f'Updated indicators for case {cid}')
        return table

    def append_rows(cid, current, rows):
        sections = current['sections']
        target = request.form.get('section_id', sections[0]['id'])
        section = next((s for s in sections if s['id'] == target), None)
        if section is None:
            raise ValueError('Choose an existing indicator section.')
        section['rows'] = section['rows']+rows
        return save(cid, current['columns'], [], int(request.form['revision']), sections)

    @app.get('/cases/<int:cid>/indicators')
    def indicators_data(cid): case(cid); return load_table(db, cid)

    @app.post('/cases/<int:cid>/indicators')
    def indicators_save(cid):
        case(cid)
        try:
            return save(cid, json.loads(request.form.get('columns', json.dumps(DEFAULT_COLUMNS))), json.loads(request.form.get('rows', '[]')), int(request.form['revision']), json.loads(request.form['sections']) if 'sections' in request.form else None)
        except (ValueError, KeyError, TypeError) as exc:
            return {'error': str(exc)}, 409

    @app.post('/cases/<int:cid>/indicators/import')
    def indicators_import(cid):
        case(cid)
        try:
            current = load_table(db, cid)
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
