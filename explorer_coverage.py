"""Read-only, authorization-first inventory of saved investigation content."""
import json
import re
from time import monotonic
from pathlib import Path
from flask import abort, g, jsonify, request, url_for
from authorization import has_permission
from indicator_types import analyze
from indicators import DEFAULT_COLUMNS, DEFAULT_SECTION_TITLE, DEFAULT_SECTION_DESCRIPTION, validate_sections
from reporting import SECTIONS
from standard_package import planned_standard

MAX_CASES = 2000
PAGE_SIZE = 50
MAX_TEXT = 1024 * 1024
MAX_CARRIER = 16 * 1024 * 1024
MAX_PAYLOAD = 64 * 1024 * 1024
MAX_SECONDS = 5


def meaningful_markdown(text):
    """Ignore headings, table scaffolding, comments and recognized prompts only."""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        line = line.strip()
        if not line or re.match(r'^#{1,6}\s', line) or re.fullmatch(r'[-*_`~\s]{3,}', line):
            continue
        if re.fullmatch(r'\[(?:add|record|summarize|reference|enter|insert|describe|todo|placeholder)\b[^\]]*\]\.?', line, re.I):
            continue
        if line.casefold().strip('.: ') in {'todo', 'tbd', 'placeholder', *[s.casefold() for s in SECTIONS.values()], 'threat overview'}:
            continue
        if '|' in line and index + 1 < len(lines):
            next_cells = [c.strip() for c in lines[index + 1].strip().strip('|').split('|')]
            if len(next_cells) > 1 and all(re.fullmatch(r':?-+:?', c) for c in next_cells):
                continue
        if line.startswith('|'):
            cells = [c.strip() for c in line.strip('|').split('|')]
            if all(not c or re.fullmatch(r':?-+:?', c) for c in cells):
                continue
            if cells and cells[0].casefold() in ('technique id', 'behavior id'):
                continue
        if line:
            return True
    return False


def read_saved(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Saved content cannot be safely inspected.')
    if not path.exists():
        return ''
    if not path.is_file() or path.stat().st_size > MAX_TEXT:
        raise ValueError('Saved content exceeds the inspection limit.')
    return path.read_text(encoding='utf-8')


def status(present=None, explanation='', count=None, url=None):
    result = dict(state='unavailable' if present is None else 'present' if present else 'missing',
                  label='Unavailable' if present is None else 'Present' if present else 'Not added', explanation=explanation)
    if count is not None:
        result['count'] = count
    if url:
        result['url'] = url
    return result


def indicator_table(row, section):
    table = dict(columns=DEFAULT_COLUMNS, rows=[], sections=[])
    if row:
        table.update(columns=json.loads(row['columns']), rows=json.loads(row['rows']))
    table['sections'] = json.loads(section['sections']) if section else [dict(id='default', title=DEFAULT_SECTION_TITLE, description=DEFAULT_SECTION_DESCRIPTION, rows=table['rows'])]
    if table['columns'] != DEFAULT_COLUMNS:
        raise ValueError('Invalid saved indicator columns.')
    table['sections'] = validate_sections(table['sections'])
    return table


def indicator_count(table):
    count = 0
    for section in table['sections']:
        meta = section.get('row_meta', [])
        for i, row in enumerate(section['rows']):
            if not row[1].strip():
                continue
            result = analyze(row, to_ids=(meta[i] or {}).get('to_ids') if i < len(meta) else None)
            if not result.get('error') and not result.get('blank'):
                count += 1
    return count


def coverage_row(connection, record, root, allowed, table, applicability=None):
    cid = record['id']
    link = lambda tab: url_for('detail', cid=cid, tab=tab)
    result = dict(id=f'case:{cid}', number=record['number'], title=record['name'], url=link('workbench'))
    if allowed['indicators:read']:
        try:
            if table is None:
                raise ValueError('Invalid saved indicators.')
            count = indicator_count(table)
            result['indicators'] = status(count > 0, 'Valid nonempty saved entries across indicator sections.', count, link('indicators'))
        except (ValueError, TypeError, KeyError, IndexError):
            result['indicators'] = status(explanation='Saved indicators could not be validated. Open the case to inspect them.', url=link('indicators'))
    else:
        result['indicators'] = status(explanation='Indicator read permission is required.')
    mappings = []
    for key, filename in (('attack', 'mitre-attack.md'), ('mbc', 'mitre-mbc.md')):
        try:
            mappings.append(status(meaningful_markdown(read_saved(root, 'mappings/' + filename)),
                'Saved editor content; a structured mapping count is unavailable.', url=link('report')) if allowed['reports:read'] else status(explanation='Report read permission is required.'))
        except (OSError, UnicodeError, ValueError):
            mappings.append(status(explanation='Saved mapping content could not be inspected.', url=link('report')))
    result['attack'], result['mbc'] = mappings
    try:
        content = []
        if allowed['reports:read']:
            for key in SECTIONS:
                value = read_saved(root, f'reports/sections/{key}.md')
                if key == 'key_findings' and not (root / f'reports/sections/{key}.md').exists():
                    value = read_saved(root, 'reports/sections/threat_overview.md')
                content.append(meaningful_markdown(value))
        result['report'] = status(any(content), 'Meaningful saved prose in the four analyst report sections.', url=link('report')) if allowed['reports:read'] else status(explanation='Report read permission is required.')
    except (OSError, UnicodeError, ValueError):
        result['report'] = status(explanation='Saved report sections could not be inspected.', url=link('report'))
    if all(allowed[p] for p in ('cases:assets', 'reports:read', 'indicators:read', 'references:read')):
        try:
            if table is None:
                raise ValueError('Invalid indicators prevent Standard package inspection.')
            if any(p.is_symlink() for p in (root, *root.parents)):
                raise ValueError('Unsafe package root.')
            files = planned_standard(connection, record, root, indicator_table=table)
            count = 0
            from data_explorer import read_csv
            for name, content in files.items():
                if name == 'iocs/indicators.stix.json':
                    bundle = json.loads(content.read_text() if isinstance(content, Path) else content)
                    count += any(o.get('type') != 'grouping' for o in bundle.get('objects', []))
                elif name.endswith('.csv'):
                    _, rows = read_csv(content)
                    count += bool(rows)
                elif name.endswith('.md'):
                    count += meaningful_markdown(read_saved(root, name))
                else:
                    count += bool(content.stat().st_size if isinstance(content, Path) else len(content))
            result['package'] = status(count > 0, 'Nonempty content included by Standard export, excluding generated archive wrappers and empty scaffolding.', count, link('package'))
        except (OSError, UnicodeError, ValueError, TypeError, KeyError):
            result['package'] = status(explanation='Standard package content could not be fully inspected.', url=link('package'))
    else:
        result['package'] = status(explanation='Asset, indicator, reference and report read permissions are required to inspect the full Standard package.')
    # Reuse explicit package-category applicability only where it maps directly.
    # Never turn restricted/unreadable content into an applicability claim.
    for category, keys in (('iocs', ('indicators',)), ('mappings', ('attack', 'mbc'))):
        if (applicability or {}).get(category) == 'Not applicable':
            for key in keys:
                if result[key]['state'] == 'missing':
                    result[key] = dict(state='not-applicable', label='Not applicable',
                        explanation=f'Explicit saved {category} applicability decision in Package Content.', url=result[key]['url'])
    mappings = [result['attack'], result['mbc']]
    # ATT&CK/MBC is one category: either missing catalog makes it missing;
    # an unavailable catalog excludes the entire category from this count.
    result['missing'] = sum(result[k]['state'] == 'missing' for k in ('indicators', 'report', 'package'))
    result['missing'] += int(all(v['state'] != 'unavailable' for v in mappings) and any(v['state'] == 'missing' for v in mappings))
    return result


def chunks(values):
    for index in range(0, len(values), 400):
        yield values[index:index + 400]


def register_coverage(app, db, require, root):
    @app.get('/data-explorer/coverage')
    def explorer_coverage():
        allowed = require()
        scope = request.args.get('scope', 'graph')
        if scope not in ('graph', 'all'):
            abort(400)
        try:
            ids = json.loads(request.args.get('ids', '[]'))
            if not isinstance(ids, list) or len(ids) > 2400 or any(not isinstance(x, str) or len(x) > 160 for x in ids):
                raise ValueError()
            page = int(request.args.get('page', 0)); gap_page = int(request.args.get('gap_page', 0))
            if not 0 <= page <= 1000000 or not 0 <= gap_page <= 1000000:
                raise ValueError()
        except (ValueError, TypeError):
            abort(400)
        sorting = request.args.get('sort', 'case')
        if sorting not in ('case', 'missing'):
            abort(400)
        connection = db()
        connection.execute('SAVEPOINT coverage_read')
        try:
            records = connection.execute('SELECT * FROM cases ORDER BY number COLLATE NOCASE,id').fetchall() if allowed['cases:read'] else []
            if scope == 'graph':
                records = [r for r in records if f"case:{r['id']}" in ids]
            available = len(records); limited = available > MAX_CASES; records = records[:MAX_CASES]
            cases = {r['id']: r for r in records}
            tables, sections, applicability = {}, {}, {}
            for batch in chunks(list(cases)):
                for row in connection.execute(f"SELECT case_id,category,status FROM readiness WHERE case_id IN ({','.join('?' * len(batch))}) AND category IN ('iocs','mappings')", batch):
                    applicability.setdefault(row['case_id'], {})[row['category']] = row['status']
            payload = 0
            def bounded_table(row, fields):
                nonlocal payload
                result = dict(row)
                size = sum(len(result[k] or '') for k in fields)
                payload += size
                if payload > MAX_PAYLOAD:
                    for key in fields:
                        result[key] = None
                return result
            if allowed['indicators:read']:
                for batch in chunks(list(cases)):
                    marks = ','.join('?' * len(batch))
                    for r in connection.execute(f'SELECT case_id, CASE WHEN length(columns)<1000 THEN columns END AS columns, CASE WHEN length(rows)<=? THEN rows END AS rows FROM indicator_tables WHERE case_id IN ({marks})', (MAX_CARRIER, *batch)):
                        tables[r['case_id']] = bounded_table(r, ('columns', 'rows'))
                    for r in connection.execute(f'SELECT case_id, CASE WHEN length(sections)<=? THEN sections END AS sections FROM indicator_sections WHERE case_id IN ({marks})', (MAX_CARRIER, *batch)):
                        sections[r['case_id']] = bounded_table(r, ('sections',))
            rows = []; started = monotonic()
            for record in records:
                if monotonic() - started > MAX_SECONDS:
                    limited = True
                    break
                try:
                    table = indicator_table(tables.get(record['id']), sections.get(record['id'])) if allowed['indicators:read'] else None
                except (ValueError, TypeError, KeyError):
                    table = None
                rows.append(coverage_row(connection, record, root / 'cases' / str(record['id']) / 'mip', allowed, table, applicability.get(record['id'])))
            inspected = {int(row['id'].split(':')[1]) for row in rows}
            gaps = knowledge_gaps(connection, allowed, {cid:record for cid,record in cases.items() if cid in inspected}, ids if scope == 'graph' else None)
        finally:
            connection.execute('RELEASE coverage_read')
        query = request.args.get('q', '').strip().casefold()[:200]
        rows = [r for r in rows if not query or query in (r['number'] + ' ' + r['title']).casefold()]
        if request.args.get('missing') == '1':
            rows = [r for r in rows if r['missing'] > 0]
        rows.sort(key=lambda r: ((-r['missing'],) if sorting == 'missing' else ()) + (r['number'].casefold(), r['id']))
        total = len(rows); pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE); page = min(page, pages - 1)
        gap_total = len(gaps); gap_pages = max(1, (gap_total + PAGE_SIZE - 1) // PAGE_SIZE); gap_page = min(gap_page, gap_pages - 1)
        return jsonify(rows=rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], total=total, scope_total=available,
                       page=page, pages=pages, gaps=gaps[gap_page * PAGE_SIZE:(gap_page + 1) * PAGE_SIZE], gap_total=gap_total,
                       gap_page=gap_page, gap_pages=gap_pages, limited=limited,
                       note=f'Partial data: {len(inspected)} of {available} cases inspected within the {MAX_CASES}-case / {MAX_SECONDS}-second limit; filters, sorting and case-derived gaps apply to that subset.' if limited else 'Content presence only. This does not assess analysis quality or case completion.'), 200, {'Cache-Control': 'private, no-store'}


def knowledge_gaps(connection, allowed, cases, graph_ids):
    if not allowed['tags:read']:
        return []
    from profile_types import FAMILY, ACTOR
    manage = has_permission(g.user, 'tags:manage', connection)
    tags = {}
    for batch in chunks(list(cases)):
        for row in connection.execute(f"SELECT DISTINCT t.id,t.name,ct.case_id FROM tags t JOIN case_tags ct ON ct.tag_id=t.id WHERE ct.case_id IN ({','.join('?' * len(batch))})", batch):
            tags.setdefault(row['id'], dict(name=row['name'], cases=set()))['cases'].add(row['case_id'])
    gaps = []
    for kind, spec in (('family', FAMILY), ('actor', ACTOR)):
        profiles = connection.execute(f'''SELECT f.id,f.name,f.tag_id,
          EXISTS(SELECT 1 FROM {spec.osint_table} o WHERE o.{spec.foreign_key}=f.id) has_osint,
          EXISTS(SELECT 1 FROM {spec.reports_table} r WHERE r.{spec.foreign_key}=f.id) has_reports
          FROM {spec.table} f JOIN tags t ON t.id=f.tag_id WHERE substr(t.name,1,?)=? AND length(t.name)>?''', (len(spec.tag_prefix), spec.tag_prefix, len(spec.tag_prefix))).fetchall()
        linked = {p['tag_id'] for p in profiles}
        def supports(tag_id):
            chosen = sorted(tags.get(tag_id, {}).get('cases', []))
            return [dict(label=cases[c]['number'], url=url_for('detail', cid=c)) for c in chosen[:5]], len(chosen)
        for tid, tag in tags.items():
            if tag['name'].startswith(spec.tag_prefix) and len(tag['name']) > len(spec.tag_prefix) and tid not in linked:
                links, count = supports(tid)
                gaps.append(dict(id=f'missing-{kind}:{tid}', name=tag['name'], kind=spec.singular,
                    suggestion='Review suggested: tag without a profile', explanation=f'Tag used by {count} scoped accessible case(s) has no linked profile.',
                    supports=links, case_count=count, action=dict(label='Create profile', url=url_for(spec.key + '_edit', tag_id=tid)) if manage else None))
        for profile in profiles:
            visible = f"{kind}:{profile['id']}" in graph_ids if graph_ids is not None else profile['tag_id'] in tags
            if visible and not profile['has_osint'] and not profile['has_reports']:
                links, count = supports(profile['tag_id'])
                gaps.append(dict(id=f"references-{kind}:{profile['id']}", name=profile['name'], kind=spec.singular,
                    suggestion='Review suggested: profile without references', explanation='No OSINT links or attached research reports are recorded.',
                    supports=links, case_count=count, action=dict(label='Review profile', url=url_for(spec.key + '_workspace', fid=profile['id'], tab='osint'))))
    return sorted(gaps, key=lambda r: (r['name'].casefold(), r['id']))
