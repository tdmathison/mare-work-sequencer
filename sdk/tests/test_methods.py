"""Every generated public operation runs through both actual HTTP transports."""
import asyncio
import inspect
import json
from pathlib import Path
import httpx
import pytest
from mws_sdk import MWSClient, AsyncMWSClient
from mws_sdk import models
from mws_sdk.exceptions import MWSError
from mws_sdk.resources import sync_resources, async_resources

ROOT=Path(__file__).resolve().parents[1]/'mws_sdk'
SPEC=json.loads((ROOT/'openapi.json').read_text())
OPS=json.loads((ROOT/'operations.json').read_text())


def sample(schema, document=None):
    document=document or SPEC
    if '$ref' in schema:
        value=document
        for bit in schema['$ref'].split('/')[1:]:value=value[bit]
        return sample(value,document)
    if 'allOf' in schema:
        result={}
        for s in schema['allOf']:result.update(sample(s,document) or {})
        return result
    if schema.get('nullable'):return None
    if 'anyOf' in schema:return sample(next((s for s in schema['anyOf'] if s.get('type')!='null'),schema['anyOf'][0]),document)
    if schema.get('enum'):return schema['enum'][0]
    kind=schema.get('type')
    if kind=='object' or 'properties' in schema:return {k:sample(s,document) for k,s in schema.get('properties',{}).items()}
    if kind=='array':return [sample(schema.get('items',{}),document) for _ in range(schema.get('minItems',0))]
    if kind=='boolean':return False
    if kind in ('number','integer'):return max(1,schema.get('minimum',0))
    if kind=='null':return None
    if kind=='string':return 'sdk_role' if 'pattern' in schema else 's'*max(16,schema.get('minLength',0))
    return {}


@pytest.mark.parametrize('op',OPS,ids=lambda op:op['resource']+'.'+op['name'])
@pytest.mark.parametrize('asynchronous',[False,True],ids=['sync','async'])
def test_every_resource_operation(op,asynchronous,tmp_path):
    operation=SPEC['paths']['/'+op['path']][op['method'].lower()]
    success=next(((k,v) for k,v in operation['responses'].items() if k.startswith('2')),None)
    status=int(success[0]) if success else 410
    payload=sample(success[1].get('content',{}).get('application/json',{}).get('schema',{})) if success else {'error':'Legacy endpoint retired.'}
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers['Authorization']=='Bearer unit-secret'
        assert request.method==op['method']
        assert request.url.path.startswith('/subpath/api/v1/')
        if op['binary']:return httpx.Response(status,content=b'archive-content')
        return httpx.Response(status,json=payload) if status!=204 else httpx.Response(204)
    kwargs={p['name']:1 if p['schema'].get('type')=='integer' else 'object-id' for p in op['paths']}
    if op['request']:
        model=getattr(models,op['request']);schema=model.model_json_schema()
        # Construct only required request values; optional fields stay absent.
        data=sample(schema,schema)
        data={k:v for k,v in data.items() if k in schema.get('required',[])}
        kwargs['data']=data
    if op['binary']:kwargs['destination']=tmp_path/'result.bin'
    async def run_async():
        async with AsyncMWSClient('https://example.test/subpath','unit-secret',transport=httpx.MockTransport(handler)) as client:
            return await getattr(getattr(client,op['resource']),op['name'])(**kwargs)
    def run_sync():
        with MWSClient('https://example.test/subpath','unit-secret',transport=httpx.MockTransport(handler)) as client:
            return getattr(getattr(client,op['resource']),op['name'])(**kwargs)
    if success:
        result=asyncio.run(run_async()) if asynchronous else run_sync()
        if op['binary']:assert result.read_bytes()==b'archive-content'
    else:
        with pytest.raises(MWSError):asyncio.run(run_async()) if asynchronous else run_sync()
    assert len(calls)==1


def test_sync_async_surface_and_no_backend_imports():
    for op in OPS:
        title=''.join(w.title() for w in op['resource'].split('_'))+'Resource'
        sync=getattr(getattr(sync_resources,title),op['name'])
        async_=getattr(getattr(async_resources,'Async'+title),op['name'])
        assert inspect.signature(sync)==inspect.signature(async_)
        assert sync.__doc__ and inspect.iscoroutinefunction(async_)
    for path in ROOT.rglob('*.py'):
        source=path.read_text()
        assert 'from app import' not in source and 'import sqlite' not in source


@pytest.mark.parametrize('op',[op for op in OPS if op['name']=='list' and op['query'] and op['collection'] and 'limit' in getattr(models,op['query']).model_fields],ids=lambda op:op['resource'])
@pytest.mark.parametrize('asynchronous',[False,True])
def test_every_namespace_pagination_helper(op,asynchronous):
    operation=SPEC['paths']['/'+op['path']]['get'];schema=next(v for k,v in operation['responses'].items() if k.startswith('2'))['content']['application/json']['schema']
    data=sample(schema);item_schema=schema['properties'][op['collection']]['items'];item=sample(item_schema)
    calls=[]
    def handler(request):
        calls.append(int(request.url.params.get('offset',0)))
        return httpx.Response(200,json={**data,op['collection']:[item], 'total':2,'offset':calls[-1],'limit':1})
    args=[1 if p['schema'].get('type')=='integer' else 'object' for p in op['paths']]
    async def run():
        async with AsyncMWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as c:
            return [item async for item in getattr(c,op['resource']).iter_all(*args,params={'limit':1})]
    if asynchronous:items=asyncio.run(run())
    else:
        with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as c:items=list(getattr(c,op['resource']).iter_all(*args,params={'limit':1}))
    assert len(items)==2 and calls==[0,1]
