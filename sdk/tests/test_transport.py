import asyncio
import io
import json
from pathlib import Path
import httpx
import pytest
from mws_sdk import *
from mws_sdk.models import CasesCreateRequest


def test_constructor_environment_redaction_and_cleanup(monkeypatch):
    monkeypatch.setenv('MWS_BASE_URL','https://example.test/api/v1')
    monkeypatch.setenv('MWS_API_KEY','secret-credential')
    client=MWSClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'user':{'id':1},'permissions':[]})))
    with client:
        assert client.authentication.me().user.id==1
        assert 'secret-credential' not in repr(client) and 'secret-credential' not in repr(client._transport)
    assert client._transport.http.is_closed
    client.close()
    for url in ('https://user:pass@example.test','https://example.test?token=secret','file:///tmp/local'):
        with pytest.raises(MWSValidationError):MWSClient(url,'secret')
    monkeypatch.delenv('MWS_API_KEY')
    with pytest.raises(MWSAuthenticationError):MWSClient('https://example.test')


@pytest.mark.parametrize('status,error',[(401,MWSAuthenticationError),(403,MWSAuthorizationError),(404,MWSNotFoundError),(400,MWSValidationError),(422,MWSValidationError),(409,MWSConflictError),(410,MWSConflictError),(429,MWSRateLimitError),(500,MWSServerError),(302,MWSError)])
def test_typed_errors_and_no_secret_echo(status,error):
    def handler(r):return httpx.Response(status,json={'error':'Bearer credential-token password other-secret','password':'other-secret'},headers={'X-Request-ID':'request-one','Retry-After':'90','Location':'https://other.test/'})
    with MWSClient('https://example.test','credential-token',transport=httpx.MockTransport(handler),retries=0) as c:
        with pytest.raises(error) as e:c.users.create(data={'username':'somebody','password':'other-secret'})
        assert e.value.status_code==status and e.value.request_id=='request-one'
        assert 'credential-token' not in str(e.value) and 'other-secret' not in str(e.value.details)
        assert e.value.retry_after=='90'


def test_retries_are_safe_only_and_retry_after(monkeypatch):
    sleeps=[];monkeypatch.setattr('mws_sdk.transport.time.sleep',sleeps.append)
    calls=[]
    def handler(r):
        calls.append(r.method)
        return httpx.Response(503 if len(calls)==1 else 200,json={'cases':[],'total':0},headers={'Retry-After':'2'})
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as c:
        c.cases.list()
        assert calls==['GET','GET'] and sleeps==[2]
    calls.clear()
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(MWSServerError):c.cases.create(data={'name':'Example'})
    assert calls==['POST']


def test_network_errors_and_model_validation_are_sanitized(monkeypatch):
    monkeypatch.setattr('mws_sdk.transport.time.sleep',lambda n:None)
    calls=[]
    def handler(r):calls.append(r);raise httpx.ConnectError('Authorization: Bearer secret',request=r)
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler),retries=1) as c:
        with pytest.raises(MWSConnectionError) as exc:c.cases.list()
        assert len(calls)==2 and 'secret' not in str(exc.value)
        with pytest.raises(MWSValidationError):c.cases.create(data={'name':123})
        with pytest.raises(MWSValidationError):c.assets.download(1,'../private',destination=Path('/tmp/unused'))


def test_pagination_filtering_and_streamed_upload_download(tmp_path):
    uploaded=[];seen=[]
    def handler(r):
        seen.append(r)
        if r.method=='GET' and r.url.path.endswith('/cases'):
            offset=int(r.url.params.get('offset',0));assert r.url.params['q']=='analysis'
            return httpx.Response(200,json={'cases':[{'id':offset+1}],'limit':1,'offset':offset,'total':3})
        if r.method=='POST':
            uploaded.append(r.read());return httpx.Response(201,json={'file':{'path':'scripts/test.bin','size':3}})
        return httpx.Response(200,content=b'a'*150000)
    path=tmp_path/'test.bin';path.write_bytes(b'abc')
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as c:
        assert [case.id for case in c.cases.iter_all(params={'q':'analysis','limit':1})]==[1,2,3]
        c.assets.upload(1,data={'category':'scripts'},files={'file':path})
        assert b'abc' in uploaded[0] and b'name="category"' in uploaded[0]
        destination=c.assets.download(1,'scripts/test.bin',destination=tmp_path/'result')
        assert destination.stat().st_size==150000
        with pytest.raises(MWSConflictError):c.assets.download(1,'scripts/test.bin',destination=destination)
        assert not list(tmp_path.glob('.mws-*'))


def test_async_retries_pagination_upload_download_and_cleanup(tmp_path,monkeypatch):
    seen=[]
    async def no_sleep(n):seen.append(n)
    monkeypatch.setattr('mws_sdk.transport.asyncio.sleep',no_sleep)
    calls=[]
    async def handler(r):
        calls.append(r.method)
        if len(calls)==1:return httpx.Response(429,json={'error':'wait'},headers={'Retry-After':'1'})
        if r.url.path.endswith('/cases'):
            offset=int(r.url.params.get('offset',0));return httpx.Response(200,json={'cases':[{'id':offset+1}],'total':2})
        return httpx.Response(200,content=b'async file')
    async def run():
        c=AsyncMWSClient('https://example.test','secret',transport=httpx.MockTransport(handler))
        async with c:
            assert [row.id async for row in c.cases.iter_all(params={'limit':1})]==[1,2]
            file=await c.assets.download(1,'scripts/test',destination=tmp_path/'async-result')
            assert file.read_bytes()==b'async file'
        assert c._transport.http.is_closed
    asyncio.run(run());assert seen==[1]


def test_partial_download_cleanup_and_caller_handle_ownership(tmp_path):
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b'partial'
            raise httpx.ReadError('sensitive transport failure')
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Broken()))) as c:
        with pytest.raises(MWSConnectionError):c.assets.download(1,'scripts/file',destination=tmp_path/'result')
    assert not (tmp_path/'result').exists() and not list(tmp_path.glob('.mws-*'))
    handle=io.BytesIO(b'caller owned')
    with MWSClient('https://example.test','secret',transport=httpx.MockTransport(lambda r:httpx.Response(201,json={'file':{'path':'scripts/test'}}))) as c:
        c.assets.upload(1,data={'category':'scripts'},files={'file':('test',handle)})
    assert not handle.closed


def test_http_date_retry_after_and_refusal_to_retry_early():
    from datetime import datetime,timedelta,timezone
    from email.utils import format_datetime
    from mws_sdk.transport import delay_for
    response=httpx.Response(429,headers={'Retry-After':format_datetime(datetime.now(timezone.utc)+timedelta(seconds=20))})
    assert 18<=delay_for(response,0,60)<=20
    assert delay_for(response,0,1) is None


def test_async_stream_failure_cleanup_and_multipart(tmp_path):
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'partial'
            raise httpx.ReadError('interrupted')
    upload=tmp_path/'upload';upload.write_bytes(b'async upload bytes')
    async def handler(request):
        if request.method=='POST':
            assert b'async upload bytes' in await request.aread()
            return httpx.Response(201,json={'file':{'path':'scripts/upload'}})
        return httpx.Response(200,stream=Broken())
    async def run():
        async with AsyncMWSClient('https://example.test','secret',transport=httpx.MockTransport(handler)) as client:
            await client.assets.upload(1,data={'category':'scripts'},files={'file':upload})
            with pytest.raises(MWSConnectionError):await client.assets.download(1,'scripts/upload',destination=tmp_path/'partial')
        assert not (tmp_path/'partial').exists() and not list(tmp_path.glob('.mws-*'))
    asyncio.run(run())
