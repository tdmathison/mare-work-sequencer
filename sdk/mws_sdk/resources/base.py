"""Shared transport binding and bounded progress-aware pagination."""
from ..utilities import encode
from ..exceptions import MWSError

class Resource:
    """An authenticated resource bound to its owning client's connection pool."""
    def __init__(self, transport):self._transport=transport
    def _iterate(self,method,key,args,params):
        query=dict(encode(params) or {});offset=int(query.get('offset',0))
        while True:
            result=method(*args,params={**query,'offset':offset})
            items=getattr(result,key,None) or []
            yield from items
            if not items or offset+len(items)>=getattr(result,'total',offset+len(items)):break
            next_offset=offset+len(items)
            if next_offset<=offset:raise MWSError('Pagination did not advance.')
            offset=next_offset

class AsyncResource(Resource):
    """Asynchronous resource; pagination yields without preloading all pages."""
    async def _iterate(self,method,key,args,params):
        query=dict(encode(params) or {});offset=int(query.get('offset',0))
        while True:
            result=await method(*args,params={**query,'offset':offset})
            items=getattr(result,key,None) or []
            for item in items:yield item
            if not items or offset+len(items)>=getattr(result,'total',offset+len(items)):break
            offset+=len(items)
