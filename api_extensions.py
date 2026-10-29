"""Versioned adapters reuse existing handlers, validators, ownership and audit paths.

Only explicitly reviewed operations are published. This is not a generic web proxy.
"""
import json
import hashlib
import uuid
from functools import wraps
from flask import Blueprint, abort, g, get_flashed_messages, jsonify, request, template_rendered
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import HTTPException
from authorization import has_permission
from api_documentation import contract, obj, array, TEXT, INT, BOOL, BINARY, json_response, download, field, PAGING


def register_api_extensions(app, db):
    api = Blueprint('api_ext', __name__, url_prefix='/api/v1')

    @api.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @api.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception('REST adapter failed')
        return jsonify(error='Internal server error.'), 500

    def require(permission):
        if permission and not has_permission(g.user, permission, db()):
            abort(403, description='Permission denied.')

    def editable(cid):
        return app.extensions['api_editable_case'](cid)

    def adapt(endpoint, arguments, write=False, post=False):
        """Translate JSON to the established form boundary, without a second transaction."""
        original_form, original_method = request.form, request.method
        active_request = request._get_current_object()
        def rendered(sender, template, context: dict, **extra):
            if request._get_current_object() is active_request:
                captured.update(context)
        captured = {}
        if request.is_json:
            value = request.get_json(silent=True)
            if not isinstance(value, dict):
                abort(400, description='Request body must be a JSON object.')
            if endpoint in ('families_edit', 'actors_edit'):
                if 'aliases' in value:value['aliases_present'] = True
                if 'known_actors' in value:value['known_actors_present'] = True
                fid = arguments.get('fid')
                if fid:
                    actor = endpoint == 'actors_edit'
                    record = db().execute(f"SELECT f.*,t.name tag FROM {'threat_actors' if actor else 'malware_families'} f JOIN tags t ON t.id=f.tag_id WHERE f.id=?", (fid,)).fetchone()
                    if not record:abort(404)
                    for key in ('name','tag','short_description','long_description','attribution_notes'):
                        value.setdefault(key,record[key])
                    if actor and 'known_families' not in value:
                        from threat_actors import associations
                        value['known_families']=[r['family_uuid'] for r in associations(db(),fid)]
            fields = []
            for key, value in value.items():
                if key in ('aliases', 'known_families', 'known_actors', 'areas') and isinstance(value, list):
                    fields.extend((key, str(item)) for item in value)
                else:
                    fields.append((key, json.dumps(value) if isinstance(value, (dict, list)) else '1' if value is True else '0' if value is False else '' if value is None else str(value)))
            request.form = ImmutableMultiDict(fields)
        if post:
            request.method = 'POST'
        template_rendered.connect(rendered, app, weak=False)
        try:
            response = app.make_response(app.view_functions[endpoint](**arguments))
            messages = get_flashed_messages()
            if response.is_json or (200 <= response.status_code < 300 and response.mimetype != 'text/html'):
                return response
            if response.status_code in (301, 302, 303):
                expected = {'tags_create':'Tag saved.', 'tag_manage':'Tag catalog updated.',
                            'case_tag_change':'Case tags updated.'}
                if endpoint.endswith('_osint_delete'):expected[endpoint]='OSINT link removed.'
                if endpoint.endswith('_reports_delete'):expected[endpoint]='Attached report removed.'
                if endpoint in expected and messages and messages[-1]!=expected[endpoint]:
                    return jsonify(error=messages[-1]), 409 if 'another session' in messages[-1] else 400
                if messages and any(str(m).startswith(('Wait', 'Unable', 'Invalid', 'Cannot', 'Could not', 'Choose', 'Enter', 'Select', 'Upload failed', 'Report removal failed')) for m in messages):
                    return jsonify(error=messages[-1]), 409
                return jsonify(message=messages[-1] if messages else 'Saved.', location=response.headers.get('Location')), 200
            return jsonify(error=captured.get('error') or (messages[-1] if messages else 'Request did not complete.')), max(400, response.status_code)
        finally:
            template_rendered.disconnect(rendered, app)
            request.form, request.method = original_form, original_method

    def bridge(path, method, endpoint, permission=None, *, arguments=None, edit_case=False, post=False, body_schema=None, binary=False, query=()):
        name='ext_'+endpoint+'_'+method.lower()
        # Some existing handlers serve both collection and item URLs.
        name += '_'+hashlib.sha256(path.encode()).hexdigest()[:8]
        def handler(**values):
            require(permission)
            if edit_case:
                editable(values.get('cid', values.get('case_id')))
            return adapt(endpoint, {**(arguments or {}), **values}, write=method!='GET', post=post)
        handler.permission=permission
        handler.__name__=name
        api.add_url_rule(path, name, handler, methods=[method])
        contract(name, method, endpoint.replace('_',' ').capitalize(), download('application/octet-stream') if binary else json_response(obj({'message':TEXT},additionalProperties=True)),
                 body=body_schema if method!='GET' else None, parameters=query, media='multipart/form-data' if body_schema and any(v.get('format')=='binary' or v.get('items',{}).get('format')=='binary' for v in body_schema.get('properties',{}).values()) else 'application/json')
        from api_documentation import CONTRACTS
        CONTRACTS[(name, method)]['x-service-target']=endpoint
        return name

    # Existing authenticated Explorer handlers enforce granular content permissions.
    for path, endpoint, query in [
        ('/explorer/graph','explorer_data',[field('q',TEXT),field('type',array(TEXT))]),
        ('/coverage','explorer_coverage',[field(n,TEXT) for n in ('scope','ids','page','gap_page','q','sort','missing')]),
        ('/explorer/evidence','explorer_evidence',[field(n,TEXT) for n in ('source','target','shared','indicator_type','minimum')]),
        ('/explorer/connections','explorer_connections',[field(n,TEXT) for n in ('scope','source','target','ids','q','depth','shared','type','indicator_type','minimum')]),
        ('/explorer/connection-objects','explorer_connection_objects',[field(n,TEXT) for n in ('scope','q','type')]),
        ('/explorer/shared-indicators','explorer_shared_indicators',[field(n,TEXT) for n in ('q','type','indicator_type','minimum')]),
        ('/explorer/views','explorer_views',[]),
        ('/explorer/views/<vid>','explorer_view',[])]:
        if endpoint not in app.view_functions:
            # Fail discovery loudly if the underlying feature is renamed.
            raise RuntimeError('Missing reviewed REST adapter target: '+endpoint)
        bridge(path,'GET',endpoint,query=query)
    for path, endpoint in [('/explorer/views','explorer_view_create'),('/explorer/views/<vid>/update','explorer_view_update'),('/explorer/views/<vid>/delete','explorer_view_delete')]:
        bridge(path,'POST',endpoint,body_schema=obj({'name':TEXT,'description':TEXT,'configuration':obj(additionalProperties=True)}))
    for path, endpoint in [('/explorer/cases/<int:case_id>/contents','explorer_contents'),('/explorer/cases/<int:case_id>/contents/<category>','explorer_category'),('/explorer/cases/<int:case_id>/file','explorer_file')]:
        bridge(path,'GET',endpoint,'cases:read',binary=endpoint=='explorer_file',query=[field('path',TEXT),field('page',INT)])

    @api.get('/tools')
    def tool_registry():
        tools=[dict(id=t.identifier,name=t.name,description=t.description,type=t.tool_type,permission=t.permission,enabled=t.enabled) for t in app.extensions['analyst_tools'].values() if t.enabled and (not t.permission or has_permission(g.user,t.permission,db()))]
        return jsonify(tools=tools,plugin_registry=False,description='Trusted installed analyst tools. External plugins integrate through the versioned REST API.')
    contract('tool_registry','GET','List authorized installed analyst tools',json_response(obj({'tools':array(obj({'id':TEXT,'name':TEXT,'description':TEXT,'type':TEXT,'permission':{**TEXT,'nullable':True},'enabled':BOOL})),'plugin_registry':BOOL,'description':TEXT})))
    bridge('/tools/text/process','POST','tools_text_process',body_schema=obj({'operation':TEXT,'text':TEXT},('operation','text')))
    for tool,prefix in [('yara','yara'),('snort','snort')]:
        source=obj({'source_json':TEXT,'filename':TEXT,'case_id':INT,'name':TEXT,'kind':TEXT,'version':TEXT,'context':obj(additionalProperties=True),'operation':TEXT,'start':INT,'end':INT,'origin_path':TEXT,'origin_cid':INT,'positive_path':TEXT,'baseline_path':TEXT,'target':BINARY,'positive':BINARY,'baseline':BINARY},additionalProperties=True)
        for path,method,endpoint in [('/state','GET',prefix+'_state'),('/draft','POST',prefix+'_draft'),('/download','POST',prefix+'_download'),('/jobs','POST',prefix+'_jobs'),('/jobs/<job>','GET',prefix+'_job'),('/jobs/<job>/cancel','POST',prefix+'_cancel')]:
            bridge('/tools/'+tool+path,method,endpoint,body_schema=source,binary=path=='/download')
        paths=[('/files','GET','yara_files'),('/file','GET','yara_open'),('/file','POST','yara_save')] if tool=='yara' else [('/files','GET','snort_inventory'),('/file','GET','snort_open'),('/file','POST','snort_save'),('/normalize','POST','snort_normalize')]
        for path,method,endpoint in paths:
            bridge('/cases/<int:cid>/'+tool+path,method,endpoint,'cases:assets',edit_case=method=='POST',body_schema=source,query=[field('path',TEXT)])
    for path, method, endpoint in [('/backup-jobs','POST','backup_jobs_create'),('/backup-jobs/<jid>','GET','backup_jobs_status'),('/backup-jobs/<jid>/download','GET','backup_jobs_download'),('/backup-jobs/<jid>/preview','POST','backup_jobs_preview'),('/backup-jobs/<jid>/apply','POST','backup_jobs_apply')]:
        bridge(path,method,endpoint,'backups:manage',body_schema=obj({'kind':TEXT,'complete':BOOL,'areas':array(TEXT),'passphrase':{**TEXT,'format':'password','writeOnly':True},'choices':obj(additionalProperties=True),'ack':TEXT,'archive':BINARY}),binary=path.endswith('download'))
    for path,method,endpoint,perm in [('/indicators/stix','GET','indicators_stix_download','indicators:read'),('/indicators/import/preview','POST','indicators_import_preview','indicators:write'),('/indicators/import','POST','indicators_import','indicators:write')]:
        bridge('/cases/<int:cid>'+path,method,endpoint,perm,edit_case=method=='POST',body_schema=obj({'revision':INT,'section_id':TEXT,'format':TEXT,'csv':TEXT,'stix':TEXT,'accepted_rows':array(array(TEXT)),'accepted_original_types':array(TEXT),'accepted_intents':array(BOOL),'skip_duplicates':BOOL}),binary=method=='GET')
    @api.get('/tags/<int:tid>')
    def tag_item(tid):
        require('tags:read')
        row=db().execute('SELECT id,name,created_at FROM tags WHERE id=?',(tid,)).fetchone()
        if not row:abort(404)
        return jsonify(tag=dict(row))
    tag_item.permission='tags:read'
    contract('tag_item','GET','Read a tag',json_response(obj({'tag':obj({'id':INT,'name':TEXT,'created_at':TEXT})})))
    bridge('/tags','GET','tags_search','tags:read',query=[field('q',TEXT)])
    bridge('/tags','POST','tags_create','tags:create',body_schema=obj({'name':TEXT},('name',)))
    bridge('/cases/<int:cid>/tags','GET','case_tags_list','tags:read')
    for operation in ('assign','remove'):
        bridge('/cases/<int:cid>/tags/<int:tid>/'+operation,'POST','case_tag_change','tags:assign',arguments={'operation':operation},edit_case=True)
    for operation in ('rename','merge','delete'):
        bridge('/tags/<int:tid>/'+operation,'POST','tag_manage','tags:manage',arguments={'operation':operation},body_schema=obj({'name':TEXT,'destination':INT,'confirm':BOOL}))

    # Profile read models deliberately exclude storage paths and report bytes.
    from profile_types import FAMILY, ACTOR
    from family_aliases import load_aliases
    from threat_actors import associations, family_associations
    for spec in (FAMILY,ACTOR):
        def records(fid=None,spec=spec):
            require('tags:read')
            query=request.args.get('q','').strip()[:200]
            try:limit=max(1,min(500,int(request.args.get('limit',100))));offset=max(0,int(request.args.get('offset',0)))
            except ValueError:abort(400)
            predicate='f.id=?' if fid else "(?='' OR instr(lower(f.name),lower(?))>0 OR instr(lower(t.name),lower(?))>0 OR EXISTS(SELECT 1 FROM json_each(f.aliases) a WHERE instr(lower(a.value),lower(?))>0))"
            args=(fid,) if fid else (query,)*4
            source=f' FROM {spec.table} f JOIN tags t ON t.id=f.tag_id WHERE '+predicate
            total=db().execute('SELECT count(*)'+source,args).fetchone()[0]
            selected=db().execute('SELECT f.*,t.name tag'+source+' ORDER BY f.name COLLATE NOCASE,f.id LIMIT ? OFFSET ?',(*args,1 if fid else limit,0 if fid else offset)).fetchall()
            values=[]
            for row in selected:
                item=dict(row);item['aliases']=load_aliases(item['aliases'])
                item['associations']=associations(db(),row['id']) if spec.actor else family_associations(db(),row['id'])
                item['osint']=[dict(r) for r in db().execute(f'SELECT id,title,url,position FROM {spec.osint_table} WHERE {spec.foreign_key}=? ORDER BY position',(row['id'],))]
                item['reports']=[dict(r) for r in db().execute(f'SELECT id,original_filename,title,description,sha256,size,uploaded_at FROM {spec.reports_table} WHERE {spec.foreign_key}=? ORDER BY uploaded_at,id',(row['id'],))]
                values.append(item)
            if fid:
                if not values:abort(404)
                return jsonify(profile=values[0])
            return jsonify(profiles=values,total=total,limit=limit,offset=offset)
        records.permission='tags:read'
        for suffix in ('','/<fid>'):
            name='profiles_'+spec.key+('_item' if suffix else '_list')
            api.add_url_rule('/'+spec.key+suffix,name,records,methods=['GET'])
            contract(name,'GET','Read '+spec.title,json_response(obj({'message':TEXT},additionalProperties=True)),parameters=PAGING+[field('q',TEXT)])
        profile_body=obj({'name':TEXT,'tag':TEXT,'version':INT,'aliases':array(TEXT),'aliases_present':BOOL,'known_families':array(TEXT),'known_actors':array(TEXT),'known_actors_present':BOOL,'short_description':TEXT,'long_description':TEXT,'attribution_notes':TEXT,'confirm_name':TEXT},additionalProperties=False)
        for suffix,endpoint in [('',spec.key+'_edit'),('/<fid>/edit',spec.key+'_edit'),('/<fid>/delete',spec.key+'_delete')]:
            bridge('/'+spec.key+suffix,'POST',endpoint,'tags:manage',post=True,body_schema=profile_body)
        for suffix,endpoint in [('/<fid>/osint',spec.key+'_osint_edit'),('/<fid>/osint/<eid>/edit',spec.key+'_osint_edit'),('/<fid>/osint/<eid>/delete',spec.key+'_osint_delete'),('/<fid>/reports',spec.key+'_reports_upload'),('/<fid>/reports/<aid>/edit',spec.key+'_reports_edit'),('/<fid>/reports/<aid>/delete',spec.key+'_reports_delete')]:
            bridge('/'+spec.key+suffix,'POST',endpoint,'tags:manage',post=True,body_schema=obj({'version':INT,'title':TEXT,'url':TEXT,'description':TEXT,'position':INT,'confirm':BOOL,'reports':array(BINARY)},additionalProperties=True))
        bridge('/'+spec.key+'/<fid>/reports/<aid>/download','GET',spec.key+'_reports_download','tags:read',binary=True)

    bridge('/search','GET','mip_search_results','cases:read',query=[field(n,TEXT) for n in ('q','kind','source','stage','page')])
    bridge('/audit/export.csv','GET','audit_export_csv','users:manage',binary=True,query=[field('actor',TEXT)])
    bridge('/audit/export-all.zip','GET','audit_export_all_zip','users:manage',binary=True)

    @api.get('/plugins')
    def plugin_capabilities():
        return tool_registry()
    contract('plugin_capabilities','GET','Inspect existing plugin integration capabilities',json_response(obj({'tools':array(obj(additionalProperties=True)),'plugin_registry':BOOL,'description':TEXT})))

    # Detailed additive response schemas for new structured resources.
    from api_documentation import CONTRACTS
    cell=obj({'state':{**TEXT,'enum':['present','missing','unavailable','not-applicable']},'label':TEXT,'explanation':TEXT,'count':INT,'url':TEXT})
    support=obj({'label':TEXT,'url':TEXT})
    gap=obj({'id':TEXT,'name':TEXT,'kind':TEXT,'suggestion':TEXT,'explanation':TEXT,'supports':array(support),'case_count':INT,'action':{**obj({'label':TEXT,'url':TEXT}),'nullable':True}})
    coverage=obj({'rows':array(obj({'id':TEXT,'number':TEXT,'title':TEXT,'url':TEXT,'missing':INT,**{k:cell for k in ('indicators','attack','mbc','report','package')}})), 'total':INT,'scope_total':INT,'page':INT,'pages':INT,'gaps':array(gap),'gap_total':INT,'gap_page':INT,'gap_pages':INT,'limited':BOOL,'note':TEXT})
    profile=obj({'id':TEXT,'name':TEXT,'tag':TEXT,'tag_id':INT,'version':INT,'aliases':array(TEXT),'short_description':TEXT,'long_description':TEXT,'attribution_notes':TEXT,'associations':array(obj(additionalProperties=True)),'osint':array(obj({'id':TEXT,'title':TEXT,'url':TEXT,'position':INT})),'reports':array(obj({'id':TEXT,'original_filename':TEXT,'title':TEXT,'description':TEXT,'sha256':TEXT,'size':INT,'uploaded_at':TEXT}))},additionalProperties=True)
    for (name,method),item in CONTRACTS.items():
        if name.startswith('ext_explorer_coverage_'):item['responses']['200']=json_response(coverage)
        if name.startswith('profiles_'):
            item['responses']['200']=json_response(obj({'profile':profile}) if '_item' in name else obj({'profiles':array(profile),'total':INT,'limit':INT,'offset':INT}))
        for param in item.get('parameters',[]):
            if name.startswith('ext_') and param['name'] in ('type','indicator_type'):param['schema']=array(TEXT)
    @app.after_request
    def api_observability(response):
        if request.path.startswith('/api/v1/'):
            identifier=str(uuid.uuid4())
            response.headers['X-Request-ID']=identifier
            response.headers['Cache-Control']='private, no-store'
            if getattr(g,'api_token_id',None) and request.method in ('POST','PUT','PATCH','DELETE'):
                from app import audit
                audit(f"API token id={g.api_token_id}: {request.method} endpoint={request.endpoint} status={response.status_code} request={identifier}")
        return response
    # Audit only after normal after-request commit/rollback and sync reconciliation.
    app.after_request_funcs[None].remove(api_observability)
    app.after_request_funcs[None].insert(0, api_observability)
    app.register_blueprint(api)
