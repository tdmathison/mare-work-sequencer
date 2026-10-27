"""Authenticated bounded relationship graph and read-only Standard package summaries."""
import csv
import io
import json
from pathlib import Path
from flask import abort, g, jsonify, render_template, request, send_file, url_for
from authorization import has_permission
from standard_package import planned_standard
from malware_families import STATES

LIMIT=400
PAGE_SIZE=200
MAX_TABLE_BYTES=16*1024*1024
KINDS=('case','family','actor')
CATEGORY_LABELS={'indicators':'Indicators','references':'References','reports':'Reports',
                 'files':'Package files','images':'Images'}
DEFINITIONS={
 'indicators':'Nonblank entries in exported indicators.csv; if absent, saved rows represented by generated STIX. CSV and STIX are not counted twice.',
 'references':'Nonblank entries in exported supporting/references.csv, excluding the header.',
 'reports':'Included PDF, Word, RTF and ODT documents. Existing Standard export report exclusions apply.',
 'images':'Included image files only; report-editor/source images excluded by Standard export are not counted.',
 'files':'Other included files, plus the generated README.md and manifest.json. Indicator/reference carrier files, report documents and images are counted only in their own categories.'}


def permissions(connection):
    return {p:has_permission(g.user,p,connection) for p in
            ('cases:read','tags:read','cases:assets','indicators:read','references:read','reports:read')}


def graph(connection, allowed, query='', kinds=KINDS,limit=LIMIT,edge_limit=None):
    # All graph queries use the same authorized CTE, including search neighborhoods
    # and limits. No full private records, per-node queries or inferred edges.
    nodes=[];edges=[]
    if allowed['cases:read']:
        nodes.append("SELECT 'case:'||id id,'case' kind,id uid,name,number,'' tag,'[]' aliases,stage FROM cases")
    if allowed['tags:read']:
        for kind,table,prefix in (('family','malware_families','MAL_'),('actor','threat_actors','TA_')):
            nodes.append(f"SELECT '{kind}:'||f.id id,'{kind}' kind,f.id uid,f.name,'' number,t.name tag,f.aliases,NULL stage FROM {table} f JOIN tags t ON t.id=f.tag_id WHERE substr(t.name,1,{len(prefix)})='{prefix}' AND length(t.name)>{len(prefix)}")
        edges.append("SELECT 'family:'||family_id source,'actor:'||actor_id target,'Configured profile association' explanation FROM actor_families WHERE family_id IS NOT NULL")
        if allowed['cases:read']:
            for kind,table,prefix in (('family','malware_families','MAL_'),('actor','threat_actors','TA_')):
                edges.append(f"SELECT 'case:'||ct.case_id source,'{kind}:'||f.id target,'Case carries '||t.name explanation FROM case_tags ct JOIN {table} f ON f.tag_id=ct.tag_id JOIN tags t ON t.id=f.tag_id WHERE substr(t.name,1,{len(prefix)})='{prefix}'")
    edge_sql=' UNION '.join(edges) or "SELECT '' source,'' target,'' explanation WHERE 0"
    tag_search="OR (n.kind='case' AND EXISTS(SELECT 1 FROM case_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.case_id=n.uid AND instr(lower(t.name),lower(:q))>0))" if allowed['tags:read'] else ''
    cte=f"""WITH nodes AS ({' UNION ALL '.join(nodes)}),
    edges AS (SELECT DISTINCT e.* FROM ({edge_sql}) e JOIN nodes a ON a.id=e.source JOIN nodes b ON b.id=e.target),
    seeds AS (SELECT id FROM nodes n WHERE :q='' OR instr(lower(n.name),lower(:q))>0
      OR instr(lower(n.number),lower(:q))>0 OR instr(lower(n.tag),lower(:q))>0
      OR EXISTS(SELECT 1 FROM json_each(n.aliases) a WHERE instr(lower(a.value),lower(:q))>0) {tag_search}),
    neighborhood AS (SELECT id FROM seeds UNION SELECT target FROM edges JOIN seeds ON source=seeds.id
      UNION SELECT source FROM edges JOIN seeds ON target=seeds.id),
    chosen AS (SELECT n.* FROM nodes n JOIN neighborhood h ON h.id=n.id WHERE n.kind IN ({','.join(':'+kind for kind in KINDS)})) """
    params=dict(q=query,**{kind:kind if kind in kinds else '' for kind in KINDS})
    connection.execute('SAVEPOINT explorer_graph')
    try:
        total=connection.execute(cte+'SELECT count(*) FROM chosen',params).fetchone()[0]
        if total>limit:
            return dict(error=f'{total} matching objects exceed the {limit}-object view limit. Search for a case, profile, alias or tag, or narrow the type filters.',total=total,limit=limit),413
        result=[]
        for row in connection.execute(cte+'SELECT * FROM chosen ORDER BY kind,name COLLATE NOCASE,id',params):
            record=dict(row)
            record['aliases']=json.loads(record['aliases'])
            if record['kind']=='case':
                stage=record['stage']
                record['status']=STATES[stage] if isinstance(stage,int) and 0<=stage<len(STATES) else 'Unavailable'
            else:
                record.pop('stage')
            record['label']=(record['number']+' · ' if record['number'] else '')+record['name']
            record['url']=url_for({'case':'detail','family':'families_workspace','actor':'actors_workspace'}[record['kind']],**({'cid':record['uid']} if record['kind']=='case' else {'fid':record['uid']}))
            result.append(record)
        relationships=[dict(row) for row in connection.execute(cte+'''SELECT 'edge:'||e.source||':'||e.target id,e.* FROM edges e
          JOIN chosen a ON a.id=e.source JOIN chosen b ON b.id=e.target ORDER BY e.source,e.target'''+(' LIMIT '+str(edge_limit+1) if edge_limit else ''),params)]
    finally:
        connection.execute('RELEASE explorer_graph')
    limited=bool(edge_limit and len(relationships)>edge_limit)
    if limited:relationships=relationships[:edge_limit]
    return dict(nodes=result,edges=relationships,edge_limited=limited,total=total,limit=limit,query=query,
                scope='Search matches and their immediate neighbors' if query else 'All authorized objects'),200


def read_csv(content):
    size=content.stat().st_size if isinstance(content,Path) else len(content)
    if size>MAX_TABLE_BYTES:raise ValueError('A deliverable table exceeds the 16 MiB inspection limit. Open its case workspace instead.')
    raw=content.read_bytes() if isinstance(content,Path) else content
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    if any(len(row)>100 for row in rows) or len(rows)>20001:
        raise ValueError('A deliverable table exceeds the 20,000-row / 100-column inspection limit. Open its case workspace instead.')
    return (rows[0] if rows else []),[row for row in rows[1:] if any(cell.strip() for cell in row)]


def package_categories(connection, record, root, allowed):
    files=planned_standard(connection,record,root)
    groups={kind:[] for kind in CATEGORY_LABELS}
    columns={}
    restricted=[]
    csv_paths={'indicators':'iocs/indicators.csv','references':'supporting/references.csv'}
    for kind,path in csv_paths.items():
        if not allowed[kind+':read']:
            restricted.append(kind);continue
        if path in files:
            columns[kind],rows=read_csv(files[path]);groups[kind]=[dict(cells=row) for row in rows]
        elif kind=='indicators' and 'iocs/indicators.stix.json' in files:
            # Every non-grouping exported object represents one validated row.
            from indicators import load_table, report_table
            table=report_table(load_table(lambda:connection,record['id']))
            columns[kind]=table['columns']
            groups[kind]=[dict(cells=row) for section in table['sections'] for row in section['rows']]
    for path,content in files.items():
        if path in {*csv_paths.values(),'iocs/indicators.stix.json'}:continue
        suffix=Path(path).suffix.lower()
        kind=('reports' if path.startswith('reports/') and suffix in ('.pdf','.doc','.docx','.rtf','.odt')
              else 'images' if suffix in ('.png','.jpg','.jpeg','.gif','.webp','.svg','.bmp','.tif','.tiff') else 'files')
        if not allowed['reports:read'] and path.startswith('reports/'):continue
        if not allowed['indicators:read'] and path.startswith('iocs/'):continue
        if kind=='reports':
            if not allowed['reports:read']:continue
        elif not allowed['cases:assets']:continue
        item=dict(filename=path)
        if allowed['cases:assets'] and isinstance(content,Path):
            item['download']=url_for('explorer_file',case_id=record['id'],path=path)
        groups[kind].append(item)
    if allowed['cases:assets']:
        groups['files'].extend([dict(filename=name,generated=True) for name in ('README.md','manifest.json')])
    else:
        restricted.extend(['files','images'])
    if not allowed['reports:read']:restricted.append('reports')
    return {kind:dict(kind=kind,label=CATEGORY_LABELS[kind],count=len(items),definition=DEFINITIONS[kind],
                      columns=columns.get(kind,[]),items=items) for kind,items in groups.items() if items},restricted


def register_explorer(app, db, root):
    def require():
        allowed=permissions(db())
        if not (allowed['cases:read'] or allowed['tags:read']):abort(403)
        return allowed

    from explorer_views import register_views
    register_views(app,db,require)

    def case_record(case_id):
        allowed=require()
        if not allowed['cases:read']:abort(403)
        record=db().execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if not record:abort(404)
        return record,allowed

    def snapshot_categories(case_id):
        db().execute('SAVEPOINT explorer_contents')
        try:
            record,allowed=case_record(case_id)
            return package_categories(db(),record,root/'cases'/str(case_id)/'mip',allowed)
        except (ValueError,UnicodeError,csv.Error):
            abort(422,description='Unable to inspect a deliverable table within the supported limits. Open the case workspace to inspect it.')
        except OSError:
            abort(409,description='Package files changed or are unavailable. Retry after saving the case.')
        finally:
            db().execute('RELEASE explorer_contents')

    from explorer_coverage import register_coverage
    register_coverage(app,db,require,root)

    from explorer_shared import register_shared
    register_shared(app,db,require,graph)
    from explorer_research import register_research
    register_research(app,db,require,graph,snapshot_categories)

    @app.context_processor
    def explorer_permission():
        return dict(can_data_explorer=bool(g.user) and (has_permission(g.user,'cases:read',db()) or has_permission(g.user,'tags:read',db())))

    @app.get('/data-explorer')
    def data_explorer():
        allowed=require()
        return render_template('data_explorer.html',explorer_permissions=allowed)

    @app.get('/data-explorer/data')
    def explorer_data():
        allowed=require()
        kinds=request.args.getlist('type') or KINDS
        if any(kind not in KINDS for kind in kinds):abort(400)
        result,status=graph(db(),allowed,request.args.get('q','').strip()[:200],kinds)
        return jsonify(result),status,{'Cache-Control':'private, no-store'}

    @app.get('/data-explorer/cases/<int:case_id>/contents')
    def explorer_contents(case_id):
        groups,restricted=snapshot_categories(case_id)
        return jsonify(categories=[{k:v for k,v in group.items() if k!='items'} for group in groups.values()],
                       restricted=restricted,note='Standard package without optional samples. Saved-state composition only; normal export readiness rules still apply.'),200,{'Cache-Control':'private, no-store'}

    @app.get('/data-explorer/cases/<int:case_id>/contents/<category>')
    def explorer_category(case_id,category):
        if category not in CATEGORY_LABELS:abort(404)
        groups,restricted=snapshot_categories(case_id)
        if category in restricted:abort(403)
        group=groups.get(category,dict(kind=category,label=CATEGORY_LABELS[category],count=0,columns=[],items=[],definition=DEFINITIONS[category]))
        try:page=int(request.args.get('page','0'));assert 0<=page<=1000000
        except (ValueError,AssertionError):abort(400)
        pages=max(1,(group['count']+PAGE_SIZE-1)//PAGE_SIZE);page=min(page,pages-1)
        return jsonify(**{**group,'items':group['items'][page*PAGE_SIZE:(page+1)*PAGE_SIZE]},page=page,pages=pages),200,{'Cache-Control':'private, no-store'}

    @app.get('/data-explorer/cases/<int:case_id>/file')
    def explorer_file(case_id):
        record,allowed=case_record(case_id)
        if not allowed['cases:assets']:abort(403)
        path=request.args.get('path','')
        groups,_=snapshot_categories(case_id)
        if not any(item.get('filename')==path and item.get('download') for group in groups.values() for item in group['items']):abort(404)
        selected=planned_standard(db(),record,root/'cases'/str(case_id)/'mip').get(path)
        if not isinstance(selected,Path) or not selected.is_file():abort(404)
        response=send_file(selected,as_attachment=True,mimetype='application/octet-stream')
        response.headers.update({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'"})
        return response
