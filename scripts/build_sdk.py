"""Generate standalone typed resources from the reviewed live OpenAPI contract.

Run with MARE_DATA_DIR pointing to a disposable directory. No SDK imports backend.
"""
import ast
import json
import os
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if not os.environ.get('MARE_DATA_DIR'):
    raise RuntimeError('Set an isolated MARE_DATA_DIR before importing the application.')
from app import app
from api_documentation import build_spec

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'sdk/mws_sdk'
spec=build_spec(app)
DEST.joinpath('openapi.json').write_text(json.dumps(spec,indent=2)+'\n')

# Existing operation names intentionally map to stable, friendly resource methods.
NAMES={
'tag_item_get':('tags','get'), 'role_item_get':('roles','get'), 'user_item_get':('users','get'), 'case_task_get':('tasks','get'), 'case_note_get':('notes','get'), 'me_get':('authentication','me'),'tokens_get':('authentication','list_tokens'),'tokens_post':('authentication','create_token'),'revoke_token_delete':('authentication','revoke_token'),
'permissions_get':('roles','permissions'),'roles_get':('roles','list'),'roles_post':('roles','create'),'role_item_patch':('roles','update'),'role_item_delete':('roles','delete'),
'users_get':('users','list'),'users_post':('users','create'),'user_item_patch':('users','update'),'user_item_delete':('users','delete'),
'settings_get':('settings','get'),'settings_patch':('settings','update'),
'case_collection_get':('cases','list'),'case_collection_post':('cases','create'),'case_item_get':('cases','get'),'case_item_patch':('cases','update'),'case_item_delete':('cases','delete'),'advance_case_post':('cases','advance'),'reopen_case_post':('cases','reopen'),'case_readiness_get':('packages','readiness'),'case_readiness_put':('packages','set_readiness'),
'case_tasks_get':('tasks','list'),'case_tasks_post':('tasks','create'),'case_task_patch':('tasks','update'),'case_task_delete':('tasks','delete'),
'case_notes_get':('notes','list'),'case_notes_post':('notes','create'),'case_note_patch':('notes','update'),'case_note_delete':('notes','delete'),'case_draft_get':('notes','get_draft'),'case_draft_put':('notes','update_draft'),'case_draft_delete':('notes','delete_draft'),
'case_assets_get':('assets','list'),'case_assets_post':('assets','upload'),'case_assets_delete':('assets','delete'),'download_case_asset_get':('assets','download'),
'case_indicators_get':('indicators','get'),'case_indicators_put':('indicators','update'),'case_references_get':('references','get'),'case_references_put':('references','update'),
'case_report_get':('reports','get'),'case_report_put':('reports','update'),'case_report_mappings_get':('reports','get_mappings'),'case_report_mappings_put':('reports','update_mappings'),'export_case_post':('packages','export'),'case_report_job_get':('reports','job'),'generate_case_report_post':('reports','generate'),'upload_final_report_post':('reports','upload'),'download_report_get':('reports','download'),'report_images_get':('reports','list_images'),'report_images_post':('reports','upload_image'),'report_image_get':('reports','download_image'),'report_image_delete':('reports','delete_image'),
 'templates_get':('templates','list'),'templates_post':('templates','upload'),'select_template_put':('templates','select'),'template_item_get':('templates','download'),'template_item_delete':('templates','delete'),
'case_backup_post':('backups','case'),'export_all_cases_post':('backups','export_cases'),'api_import_backup_post':('backups','import_cases'),'api_import_backup_post_raw':('backups','import_raw'),'api_database_backup_post':('backups','legacy_database'),'metrics_get':('metrics','get'),
'sync_api_review_get':('backups','sync_review'), 'sync_api_preview_post':('backups','sync_preview'),'sync_api_apply_post':('backups','sync_apply'),
 'tool_registry_get':('tools','list'), 'plugin_capabilities_get':('plugins','capabilities'),
}

models={}
def cname(name):return ''.join(w[:1].upper()+w[1:] for w in re.split(r'[^A-Za-z0-9]',name) if w)
def annotation(schema,name):
    if '$ref' in schema:return schema['$ref'].split('/')[-1]
    if 'allOf' in schema:
        combined={}
        for part in schema['allOf']:
            if '$ref' in part:part=spec['components']['schemas'][part['$ref'].split('/')[-1]]
            previous=combined.get('properties',{});combined.update(part);combined['properties']={**previous,**part.get('properties',{})}
        schema=combined
    kind=schema.get('type')
    if kind=='object' or 'properties' in schema:
        if not schema.get('properties'):return 'dict[str, Any]'
        models.setdefault(name,schema)
        return name
    if kind=='array':return 'list['+annotation(schema.get('items',{}),name+'Item')+']'
    if 'enum' in schema and schema['enum']:return 'Literal['+', '.join(repr(x) for x in schema['enum'])+']'
    return {'string':'str','integer':'int','number':'float','boolean':'bool'}.get(kind,'Any')

for name,schema in spec['components']['schemas'].items():
    if schema.get('type')=='object':models[name]=schema
    else:models[name]={'__root__':schema}

operations=[]
for path,methods in spec['paths'].items():
 for method,operation in methods.items():
    op=operation['operationId']
    if op=='api_database_backup_post':continue  # Retired HTTP 410 endpoint; use complete encrypted backup jobs.
    pair=NAMES.get(op)
    if pair is None:
        endpoint=operation.get('x-service-target') or op.rsplit('_'+method,1)[0]
        if path.startswith('/coverage'):pair=('coverage','get')
        elif path.startswith('/explorer'):
            n={'explorer_data':'graph','explorer_evidence':'evidence','explorer_connections':'connections','explorer_connection_objects':'connection_objects','explorer_shared_indicators':'shared_indicators','explorer_views':'list_views','explorer_view':'get_view','explorer_view_create':'create_view','explorer_view_update':'update_view','explorer_view_delete':'delete_view','explorer_contents':'contents','explorer_category':'category','explorer_file':'download'};pair=('explorer',n[endpoint])
        elif path.startswith('/tools/text'):pair=('tools','process_text')
        elif path.startswith('/tools/yara') or '/yara/' in path:pair=('tools',endpoint)
        elif path.startswith('/tools/snort') or '/snort/' in path:pair=('tools',endpoint)
        elif path.startswith('/backup-jobs'):pair=('backups',{'backup_jobs_create':'create_job','backup_jobs_status':'job','backup_jobs_download':'download','backup_jobs_preview':'preview','backup_jobs_apply':'apply'}[endpoint])
        elif '/indicators/' in path:pair=('indicators',{'indicators_stix_download':'download_stix','indicators_import_preview':'preview_import','indicators_import':'import_rows'}[endpoint])
        elif path.startswith('/families') or path.startswith('/actors'):
            resource=path.strip('/').split('/')[0];name=endpoint.replace('profiles_'+resource+'_','').replace(resource+'_','');name={'item':'get','edit':'create' if path=='/'+resource else 'update','osint_edit':'add_osint' if '<eid>' not in path and '{eid}' not in path else 'update_osint','osint_delete':'delete_osint','reports_upload':'upload_reports','reports_edit':'update_report','reports_delete':'delete_report','reports_download':'download_report'}.get(name,name)
            pair=(resource,name)
        elif path.startswith('/search'):pair=('search','query')
        elif path.startswith('/audit'):pair=('audit','export_csv' if path.endswith('.csv') else 'export_all')
        elif path.startswith('/tags') or path.endswith('/tags') or '/tags/' in path:
            name={'tags_search':'list','tags_create':'create','case_tags_list':'for_case','case_tag_change':path.split('/')[-1],'tag_manage':path.split('/')[-1]}[endpoint];pair=('tags',name)
        else:raise ValueError('Unmapped operation '+op)
    resource,name=pair
    if any(r['resource']==resource and r['name']==name for r in operations):raise ValueError('Duplicate method '+str(pair))
    request_content=operation.get('requestBody',{}).get('content',{})
    media=next(iter(request_content),'application/json')
    schema=request_content.get(media,{}).get('schema')
    if schema:
        schema=json.loads(json.dumps(schema))
        binary_keys=[k for k,v in schema.get('properties',{}).items() if v.get('format')=='binary' or v.get('items',{}).get('format')=='binary']
        for key in binary_keys:schema['properties'].pop(key)
        if 'required' in schema:schema['required']=[k for k in schema['required'] if k not in binary_keys]
    req=cname(resource+'_'+name)+'Request' if schema else None
    if schema:annotation(schema,req)
    parameters=operation.get('parameters',[])
    paths=sorted((p for p in parameters if p['in']=='path'),key=lambda p:path.index('{'+p['name']+'}'));queries={p['name']:p['schema'] for p in parameters if p['in']=='query'}
    query=cname(resource+'_'+name)+'Params' if queries else None
    if query:models[query]={'type':'object','properties':queries}
    responses=operation['responses'];success=next((v for k,v in responses.items() if k.startswith('2')),None)
    content=success.get('content',{}) if success else {}
    binary=bool(content and 'application/json' not in content)
    response=None
    if 'application/json' in content:
        response=cname(resource+'_'+name)+'Response';rs=content['application/json']['schema'];ann=annotation(rs,response)
        if '$ref' in rs:response=ann
        elif ann!=response:models[response]={'__root__':rs}
    if req and req not in models:models[req]=schema
    collection=next((k for k,v in content.get('application/json',{}).get('schema',{}).get('properties',{}).items() if v.get('type')=='array'),None)
    operations.append(dict(resource=resource,name=name,operation_id=op,path=path.lstrip('/'),method=method.upper(),permission=operation.get('x-required-permission'),paths=paths,request=req,response=response,query=query,media=media,binary=binary,collection=collection,summary=operation['summary'],description=operation['description']))

# Expand nested schemas first; all references resolve after class declarations.
index=0
while index<len(models):
    name=list(models)[index];schema=models[name];index+=1
    if '__root__' in schema:annotation(schema['__root__'],name+'Value');continue
    for field,s in schema.get('properties',{}).items():annotation(s,name+cname(field))

lines=['"""Generated typed API models. Regenerate with scripts/build_sdk.py; do not edit."""','from __future__ import annotations','from typing import Any, Literal','from pydantic import BaseModel, ConfigDict, Field, RootModel, SecretStr','', 'class APIModel(BaseModel):','    """Forward-compatible server object with unknown fields retained."""','    model_config = ConfigDict(extra="allow", populate_by_name=True, hide_input_in_errors=True)','']
for name,schema in models.items():
    if '__root__' in schema:
        lines.extend([f'class {name}(RootModel[{annotation(schema["__root__"],name+"Value")!r}]):',f'    """{name} value."""','    def __iter__(self): return iter(self.root)','    def __len__(self): return len(self.root)','    def __getitem__(self, key): return self.root[key]','']);continue
    lines.extend([f'class {name}(APIModel):',f'    """{name} version-1 API fields."""'])
    if name.endswith(('Request','Params')):lines.append('    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)')
    props=schema.get('properties',{});required=schema.get('required',[])
    for key,s in props.items():
        field_name=key if key.isidentifier() and key not in ('schema','model_config') else key+'_field'
        ann=annotation(s,name+cname(key))
        if ann=='str' and (s.get('writeOnly') or s.get('format')=='password' or key in ('token','api_key','passphrase','password')):ann='SecretStr'
        default='...' if key in required else 'None'
        if default=='None' or s.get('nullable'):ann+=' | None'
        opts=[]
        if field_name!=key:opts.append('alias='+repr(key))
        for source,target in [('minLength','min_length'),('maxLength','max_length'),('minimum','ge'),('maximum','le'),('minItems','min_length'),('maxItems','max_length'),('pattern','pattern')]:
            if source in s:opts.append(f'{target}={s[source]!r}')
        lines.append(f'    {field_name}: {ann} = '+(f'Field({default}, '+', '.join(opts)+')' if opts else default))
    if not props:lines.append('    pass')
    lines.append('')
# RootModels with forward refs are resolved in their declaration order above; named refs point to core models first.
lines.extend(['for _value in list(globals().values()):','    if isinstance(_value, type) and issubclass(_value, BaseModel) and _value.__module__ == __name__:','        _value.model_rebuild()',''])
DEST.joinpath('models.py').write_text('\n'.join(lines))
DEST.joinpath('operations.json').write_text(json.dumps(operations,indent=2)+'\n')

for asynchronous in (False,True):
 prefix='Async' if asynchronous else ''
 output=['"""Generated, explicit REST resource methods; sync/async contracts are identical."""','from __future__ import annotations','from typing import Any, Mapping','from pathlib import Path','from ..models import *','from ..utilities import path_value','from .base import '+prefix+'Resource','']
 for namespace in sorted({r['resource'] for r in operations}):
    cls=prefix+cname(namespace)+'Resource';output.extend([f'class {cls}({prefix}Resource):',f'    """Authorized {namespace} operations. Server-side RBAC remains authoritative."""'])
    for op in (r for r in operations if r['resource']==namespace):
        params=[f"{p['name']}: {'int' if p['schema'].get('type')=='integer' else 'str'}" for p in op['paths']]
        params.append('*')
        if op['request']:params.append(f"data: {op['request']} | Mapping[str, Any] | None = None")
        if op['query']:params.append(f"params: {op['query']} | Mapping[str, Any] | None = None")
        # Files are explicit and may be paths, caller-owned handles or httpx file tuples.
        if op['request']:params.append('files: Mapping[str, Any] | list[tuple[str, Any]] | None = None')
        if op['binary']:params.extend(['destination: str | Path','overwrite: bool = False'])
        if params[-1]=='*':params.pop()
        output.append(f"    {'async ' if asynchronous else ''}def {op['name']}(self{', ' if params else ''}{', '.join(params)}) -> {'Path' if op['binary'] else op['response'] or 'None'}:")
        output.append('        '+repr(op['summary']+'. '+op['method']+' /api/v1/'+op['path']+'. '+op['description']))
        expression=repr(op['path'])
        for p in op['paths']:
            expression+=f".replace('{{{p['name']}}}', path_value({p['name']}, nested={p['name']=='relative_path'}))"
        arguments=[repr(op['method']),expression]
        if op['request']:arguments.extend(['data=data','files=files',f"request_model={op['request']}",f"media={op['media']!r}"])
        if op['query']:arguments.append('params=params')
        if op['response']:arguments.append(f"response_model={op['response']}")
        if op['binary']:arguments.extend(['destination=destination','overwrite=overwrite'])
        output.extend([f"        return {'await ' if asynchronous else ''}self._transport.request({', '.join(arguments)})",''])
    listing=next((r for r in operations if r['resource']==namespace and r['name']=='list' and r['collection'] and r['query'] and 'limit' in models[r['query']].get('properties',{})),None)
    if listing:
        pnames=[p['name'] for p in listing['paths']]
        args=', '.join(pnames)
        output.extend([f"    {'async ' if asynchronous else ''}def iter_all(self{', '+args if args else ''}, *, params=None):",'        """Yield authorized records across offset pages without preloading the dataset."""'])
        if asynchronous:output.extend([f"        async for item in self._iterate(self.list, {listing['collection']!r}, ({args+',' if args else ''}), params):",'            yield item',''])
        else:output.extend([f"        yield from self._iterate(self.list, {listing['collection']!r}, ({args+',' if args else ''}), params)",''])
 DEST.joinpath('resources', 'async_resources.py' if asynchronous else 'sync_resources.py').write_text('\n'.join(output))

# API coverage includes operation, permission, models and SDK method in one reproducible inventory.
rows=['# API-to-SDK coverage matrix','', 'Generated from registered routes and reviewed OpenAPI contracts. All rows are implemented; runtime authorization, workflow and revision errors remain authoritative. Tests exercise every method with mocked HTTP and representative isolated backend workflows.','', '| Method | REST endpoint | Permission | Request / query model | Response | SDK method | Status |','|---|---|---|---|---|---|---|']
for op in operations:rows.append('| '+' | '.join([op['method'],'`/api/v1/'+op['path']+'`',op['permission'] or 'Authenticated / handler checks',op['request'] or op['query'] or 'None','Download' if op['binary'] else op['response'] or 'No body',f"`client.{op['resource']}.{op['name']}`",'Implemented'])+' |')
rows.append('| POST | `/api/v1/backups/database` | backups:manage | None | HTTP 410 | No SDK method; use `backups.create_job` for complete encrypted backups | Retired, retained for old clients |')
ROOT.joinpath('sdk/docs/API_COVERAGE.md').write_text('\n'.join(rows)+'\n')
print(f'Generated {len(operations)} operations, {len(models)} typed models.')

reference=['# SDK API reference','', 'Generated from source docstrings and signatures. Both clients expose the same resource methods; async calls must be awaited.','']
for source in [DEST/'client.py',DEST/'resources/sync_resources.py',DEST/'resources/async_resources.py',DEST/'models.py']:
 tree=ast.parse(source.read_text())
 reference.extend(['## '+source.name,''])
 for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
  reference.extend(['### '+cls.name,'',ast.get_docstring(cls) or '', ''])
  for node in cls.body:
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith('_'):
    reference.extend(['```python',('async ' if isinstance(node,ast.AsyncFunctionDef) else '')+'def '+node.name+'('+ast.unparse(node.args)+')'+(' -> '+ast.unparse(node.returns) if node.returns else ''),'```','',ast.get_docstring(node) or '', ''])
ROOT.joinpath('sdk/docs/API_REFERENCE.md').write_text('\n'.join(reference))

# Ship explicit namespace annotations for editor completion and static consumers.
client_path=DEST/'client.py'
client_source=client_path.read_text()
for cls,prefix,module in [('MWSClient','','sync_resources'),('AsyncMWSClient','Async','async_resources')]:
 start=client_source.index('class '+cls+':')
 init=client_source.index('    def __init__',start)
 marker=client_source.find('    # BEGIN RESOURCE TYPES',start,init)
 if marker>=0:
  end=client_source.index('    # END RESOURCE TYPES',marker)+len('    # END RESOURCE TYPES\n')
  client_source=client_source[:marker]+client_source[end:]
  init=client_source.index('    def __init__',start)
 declarations='    # BEGIN RESOURCE TYPES\n'+''.join('    '+name+': '+module+'.'+prefix+cname(name)+'Resource\n' for name in sorted({op['resource'] for op in operations}))+'    # END RESOURCE TYPES\n'
 client_source=client_source[:init]+declarations+client_source[init:]
client_path.write_text(client_source)
