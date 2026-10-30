"""Session and versioned API adapters over the same collection transactions."""
from functools import wraps
import json
from flask import abort,g,request,render_template,Blueprint
from werkzeug.exceptions import HTTPException
from authorization import has_permission
import task_collections as service
from api_documentation import contract,obj,array,TEXT,INT,BOOL,NULL_TEXT,NULL_INT,SCHEMAS,ref,PAGING,json_response

def register(app,db):
    with app.app_context():service.initialize(db())
    api=Blueprint('task_collection_api',__name__,url_prefix='/api/v1')
    @api.errorhandler(HTTPException)
    def error(e):return {'error':e.description},e.code
    def payload():
        try:value=request.get_json(silent=True) if request.is_json else json.loads(request.form.get('payload','{}'))
        except (ValueError,TypeError):abort(400,description='Invalid task collection request.')
        if not isinstance(value,dict):abort(400)
        return value
    def rights():return {p:has_permission(g.user,'task_collections:'+p,db()) or has_permission(g.user,'task_collections:manage',db()) for p in ('create','update','delete')}
    def library():
        if request.method=='GET':
            items=service.catalog(db(),g.user);query=request.args.get('q','').casefold();category=request.args.get('category','')
            items=[c for c in items if query in (c['name']+' '+c['description']).casefold() and (not category or c['category']==category)]
            if request.path.startswith('/api/v1/'):
                try:limit=max(1,min(int(request.args.get('limit','100')),500));offset=max(0,int(request.args.get('offset','0')))
                except ValueError:abort(400)
                return {'collections':items[offset:offset+limit],'permissions':rights(),'total':len(items),'limit':limit,'offset':offset}
            return {'collections':items,'permissions':rights()}
        return {'collection':service.save(db(),g.user,payload())},201
    def collection(collection_id):
        if request.method=='GET':return {'collection':service.get(db(),collection_id)}
        value=payload()
        if request.method=='DELETE' or value.get('operation')=='delete':
            service.remove(db(),g.user,collection_id,value.get('revision'));return '',204
        return {'collection':service.save(db(),g.user,value,collection_id)}
    def case_workspace(cid):
        result=service.workspace(db(),g.user,cid);c=db().execute('SELECT c.*,u.active owner_active FROM cases c LEFT JOIN users u ON u.id=c.owner WHERE c.id=?',(cid,)).fetchone()
        result['editable']=has_permission(g.user,'cases:update',db()) and c['stage'] in (1,2) and (not c['owner_required'] or bool(c['owner_active']))
        return result
    def application(cid,collection_id):return service.apply(db(),g.user,cid,collection_id,payload()),201
    def from_tasks(cid):return {'collection':service.from_case(db(),g.user,cid,payload())},201
    def change_task(cid,tid):
        value=payload();deleted=value.get('operation')=='delete'
        result=service.mutate_task(db(),g.user,cid,tid,value,deleted)
        return {'task':result}
    def order(cid):
        value=payload();service.reorder(db(),g.user,cid,value.get('group_id'),value.get('task_ids'));return {'ok':True}
    def group_delete(cid,gid):
        value=payload()
        if value.get('confirm') is not True:abort(400,description='Confirm removal of all copied tasks in this group.')
        with db():
            db().execute('BEGIN IMMEDIATE');service.editable(db(),g.user,cid)
            if not db().execute('SELECT 1 FROM task_groups WHERE case_id=? AND id=?',(cid,gid)).fetchone():abort(404)
            db().execute('DELETE FROM tasks WHERE case_id=? AND group_id=?',(cid,gid));db().execute('DELETE FROM task_groups WHERE case_id=? AND id=?',(cid,gid))
            service.event(db(),g.user,f'Removed task group {gid} and copied tasks from case {cid}')
        return {'ok':True}
    def web_adapter(function):
        @wraps(function)
        def wrapped(*args,**kwargs):
            try:return function(*args,**kwargs)
            except HTTPException as error:return {'error':error.description},error.code
        return wrapped
    rows=[('task_collection_list','/task-collections','/task-workspace/collections',library,['GET','POST']),
          ('task_collection_item','/task-collections/<collection_id>','/task-workspace/collections/<collection_id>',collection,['GET','PATCH','DELETE']),
          ('task_collection_case','/cases/<int:cid>/task-groups','/task-workspace/cases/<int:cid>',case_workspace,['GET']),
          ('task_collection_apply','/cases/<int:cid>/task-collections/<collection_id>/apply','/task-workspace/cases/<int:cid>/collections/<collection_id>/apply',application,['POST']),
          ('task_collection_from_tasks','/cases/<int:cid>/task-collections','/task-workspace/cases/<int:cid>/from-tasks',from_tasks,['POST']),
          ('task_collection_order','/cases/<int:cid>/task-order','/task-workspace/cases/<int:cid>/reorder',order,['PUT']),
          ('task_collection_group_delete','/cases/<int:cid>/task-groups/<gid>','/task-workspace/cases/<int:cid>/groups/<gid>/delete',group_delete,['DELETE'])]
    for endpoint,path,webpath,function,methods in rows:
        api.add_url_rule(path,endpoint,function,methods=methods)
        app.add_url_rule(webpath,'web_'+endpoint,web_adapter(function),methods=['GET' if m=='GET' else 'POST' for m in methods])
    app.add_url_rule('/task-workspace/cases/<int:cid>/tasks/<int:tid>','web_collection_task',web_adapter(change_task),methods=['POST'])
    @app.get('/task-collections')
    def global_task_library():return render_template('task_collection_library.html')
    app.register_blueprint(api)

    template=obj({'id':TEXT,'name':TEXT,'description':TEXT},('name',))
    fields={'name':TEXT,'description':TEXT,'category':TEXT,'revision':INT,'tasks':array(template)}
    SCHEMAS['TaskCollection']=obj({'id':TEXT,**fields,'creator_uuid':NULL_TEXT,'creator_name':TEXT,'created':TEXT,'updated':TEXT,'task_count':INT,'can_edit':BOOL,'can_delete':BOOL})
    collection_schema=ref('TaskCollection')
    response=json_response(obj({'collection':collection_schema}))
    contract('task_collection_list','GET','List global task collections',json_response(obj({'collections':array(collection_schema),'permissions':obj({'create':BOOL,'update':BOOL,'delete':BOOL}),'total':INT,'limit':INT,'offset':INT})),parameters=[*PAGING,*[{'name':n,'in':'query','schema':TEXT} for n in ('q','category')]],description='Shared global guidance, with name/description search, category filters and standard limit/offset pagination.')
    contract('task_collection_list','POST','Create a global task collection',response,body=obj(fields,('name','tasks')),status=201,description='Creates ordered, reusable guidance. Avoid case-specific or confidential details. Collection management permission is required.')
    contract('task_collection_item','GET','Read a task collection',response,description='Returns the current revision and ordered templates. Reading a collection never changes Case content.')
    contract('task_collection_item','PATCH','Update ordered collection definitions',response,body=obj(fields,('revision','name','tasks')),errors=(409,),description='Requires the current revision and creator ownership or task_collections:manage. Existing Case copies are never updated.')
    contract('task_collection_item','DELETE','Delete a global collection; retain Case copies',status=204,body=obj({'revision':INT},('revision',)),errors=(409,),description='Requires the current revision and creator ownership or task_collections:manage. Existing Case tasks, source snapshots and historical revisions remain intact.')
    group_schema=obj({'id':TEXT,'case_id':INT,'name':TEXT,'source_collection_id':NULL_TEXT,'source_revision':NULL_INT,'added':TEXT,'position':INT,'source_fingerprint':TEXT,'source_tasks':array(template)})
    contract('task_collection_case','GET','Read Case tasks, groups and source provenance',json_response(obj({'tasks':array(ref('Task')),'groups':array(group_schema),'applications':array(obj({'source_collection_id':TEXT,'template_ids':array(TEXT),'added':TEXT})),'editable':BOOL})),description='Includes Case tasks, group name snapshots, source collection/revision/template IDs, application history and current editability. Source collections need not exist.')
    contract('task_collection_apply','POST','Apply selected templates atomically to a Case',json_response(obj({'group_id':TEXT,'task_ids':array(INT),'count':INT,'source_collection_id':TEXT,'source_revision':INT,'source_fingerprint':TEXT,'source_tasks':array(template),'added':TEXT,'replayed':BOOL})),body=obj({'revision':INT,'template_ids':array(TEXT),'mode':{**TEXT,'enum':['missing','copy']},'request_key':TEXT},('revision','template_ids','request_key')),status=201,errors=(409,),description='Requires an editable Case and current collection revision. All copied tasks start Not Started. Reuse the same request_key with the same payload for safe retries. Missing mode uses historical template IDs; copy mode explicitly creates another group.')
    contract('task_collection_from_tasks','POST','Copy selected Case definitions into a global collection',response,body=obj({'task_ids':array(INT),'collection_id':TEXT,**fields},('task_ids',)),status=201,errors=(409,),description='Creating requires task_collections:create. Appending requires task_collections:update and creator ownership, or task_collections:manage. Appends require the current revision. Case definitions are copied without progress or assignments.')
    contract('task_collection_order','PUT','Reorder all tasks within one Case group',json_response(obj({'ok':BOOL})),body=obj({'group_id':TEXT,'task_ids':array(INT)},('task_ids',)),errors=(409,),description='Submit every current task ID in the selected group, in the desired order. Null group_id selects Custom tasks. Closed Cases reject changes.')
    contract('task_collection_group_delete','DELETE','Remove Case group and its copied tasks',json_response(obj({'ok':BOOL})),body=obj({'confirm':BOOL},('confirm',)),errors=(409,),description='Requires confirm=true and an editable Case. Deletes only the copied tasks and Case group; the global collection and audit/application history remain unchanged.')
    for fn,permissions in [(library,{'GET':None,'POST':'task_collections:create'}),(collection,{'GET':None,'PATCH':'task_collections:update','DELETE':'task_collections:delete'}),(case_workspace,'cases:read'),(application,'cases:update'),(from_tasks,None),(order,'cases:update'),(group_delete,'cases:update')]:fn.permission=permissions
