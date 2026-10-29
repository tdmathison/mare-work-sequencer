"""Pooled HTTP transport with safe-read retries and atomic streamed downloads."""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
from pathlib import Path
import random
import re
import tempfile
import time
from typing import Any, Mapping
import httpx
from pydantic import BaseModel, ValidationError
from .authentication import BearerAuth
from .exceptions import *
from .utilities import encode, redact

logger=logging.getLogger('mws_sdk')
RETRY_STATUS={429,502,503,504}
ERRORS={401:MWSAuthenticationError,403:MWSAuthorizationError,404:MWSNotFoundError,400:MWSValidationError,422:MWSValidationError,413:MWSValidationError,409:MWSConflictError,410:MWSConflictError,429:MWSRateLimitError}


def base_url(value):
    value=value or os.environ.get('MWS_BASE_URL')
    if not value:raise MWSValidationError('Supply base_url or MWS_BASE_URL.')
    try:url=httpx.URL(value)
    except Exception:raise MWSValidationError('Invalid base URL.') from None
    if url.scheme not in ('http','https') or not url.host or url.userinfo or url.query or url.fragment:raise MWSValidationError('Use an absolute HTTP(S) base URL without credentials, query or fragment.')
    path=url.path.rstrip('/')
    if path.endswith('/api/v1'):path=path[:-7]
    return str(url.copy_with(path=path+'/api/v1/'))


def delay_for(response,attempt,maximum):
    raw=response.headers.get('Retry-After') if response is not None else None
    if raw:
        try:delay=max(0,float(raw))
        except ValueError:
            try:delay=max(0,(parsedate_to_datetime(raw)-datetime.now(timezone.utc)).total_seconds())
            except (ValueError,TypeError,OverflowError):delay=0
        # Do not retry early if the server asks for a wait beyond the configured cap.
        return delay if delay<=maximum else None
    return min(maximum,.25*2**attempt+random.uniform(0,.1))


def prepared(data, model):
    if data is None:return None
    try:return encode(model.model_validate(data) if model and not isinstance(data,model) else data)
    except ValidationError:raise MWSValidationError('Request does not match the documented model. Check required fields, types and limits.') from None


def query_params(params):
    result=encode(params) or {}
    return {k:('true' if v else 'false') if isinstance(v,bool) else v for k,v in result.items() if v is not None}


def upload_fields(files, stack):
    if not files:return None
    items=files.items() if isinstance(files,Mapping) else files
    result=[]
    for name,value in items:
        if isinstance(value,(str,Path)):
            path=Path(value)
            try:value=(path.name,stack.enter_context(path.open('rb')))
            except OSError:raise MWSValidationError('Unable to open the upload file.') from None
        result.append((name,value))
    return result


def form_data(data):
    return {k:v if k in ('aliases','known_actors','known_families','areas') and isinstance(v,list) else json.dumps(v) if isinstance(v,(dict,list)) else '1' if v is True else '0' if v is False else '' if v is None else str(v) for k,v in (data or {}).items()}


class Transport:
    """Owns one httpx.Client pool; only GET/HEAD/OPTIONS may be retried."""
    asynchronous=False
    def __init__(self, *, base_url=None, api_key=None, connect_timeout=10., read_timeout=60., verify=True, retries=2, max_retry_delay=60., max_connections=20, max_keepalive_connections=10, transport=None, trust_env=False):
        if type(retries) is not int or not 0<=retries<=10:raise MWSValidationError('retries must be between 0 and 10.')
        if min(connect_timeout,read_timeout,max_retry_delay)<=0:raise MWSValidationError('Timeouts and retry delay must be positive.')
        self.auth=BearerAuth(api_key);self.retries=retries;self.maximum=max_retry_delay
        factory=httpx.AsyncClient if self.asynchronous else httpx.Client
        self.http=factory(base_url=globals()['base_url'](base_url),auth=self.auth,headers={'Accept':'application/json','User-Agent':'mws-sdk/1.0.0'},timeout=httpx.Timeout(read_timeout,connect=connect_timeout),limits=httpx.Limits(max_connections=max_connections,max_keepalive_connections=max_keepalive_connections),verify=verify,follow_redirects=False,transport=transport,trust_env=trust_env)
    def __repr__(self):return f'{type(self).__name__}(credentials=[REDACTED])'
    def error(self,response,data=None):
        if response.is_success:return
        try:details=response.json()
        except (ValueError,UnicodeError):details={'error':'Non-JSON error response.'}
        secrets=[self.auth.secret.get_secret_value()]
        def collect(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if isinstance(item,str) and re.search('password|passphrase|token|secret|api.?key',key,re.I):secrets.append(item)
                    elif isinstance(item,(dict,list)):collect(item)
            elif isinstance(value,list):
                for item in value:collect(item)
        collect(data)
        details=redact(details,tuple(secrets));message=details.get('error','Request failed.') if isinstance(details,dict) else 'Request failed.'
        cls=ERRORS.get(response.status_code,MWSServerError if response.status_code>=500 else MWSError)
        raise cls(str(message),status_code=response.status_code,request_id=redact(response.headers.get('X-Request-ID'),tuple(secrets)),details=details,retry_after=response.headers.get('Retry-After'))
    def result(self,response,model,data):
        self.error(response,data)
        if response.status_code==204 or not response.content:return None
        try:value=response.json()
        except (ValueError,UnicodeError):raise MWSError('Expected JSON from this API operation.',status_code=response.status_code) from None
        if not model:return value
        try:return model.model_validate(value)
        except ValidationError:raise MWSError('Server response does not match the versioned API contract.',status_code=response.status_code,request_id=response.headers.get('X-Request-ID')) from None
    def request(self,method,path,*,params=None,data=None,request_model=None,response_model=None,media='application/json',files=None,destination=None,overwrite=False):
        body=prepared(data,request_model);query=query_params(params);safe=method in ('GET','HEAD','OPTIONS')
        with ExitStack() as stack:
            uploads=upload_fields(files,stack)
            kwargs={'params':query}
            if uploads or media in ('multipart/form-data','application/x-www-form-urlencoded'):kwargs.update(data=form_data(body),files=uploads)
            elif body is not None:kwargs['json']=body
            if destination is not None:return self.download(method,path,destination,overwrite,body,kwargs)
            for attempt in range(self.retries+1):
                try:response=self.http.request(method,path,**kwargs)
                except httpx.RequestError:
                    if safe and attempt<self.retries:time.sleep(delay_for(None,attempt,self.maximum));continue
                    raise MWSConnectionError('Unable to reach MWS or the request timed out.') from None
                logger.debug('%s API operation returned %s',method,response.status_code)
                wait=delay_for(response,attempt,self.maximum) if safe and response.status_code in RETRY_STATUS and attempt<self.retries else None
                if wait is not None:response.close();time.sleep(wait);continue
                try:return self.result(response,response_model,body)
                finally:response.close()
    def download(self,method,path,destination,overwrite,body,kwargs):
        target=Path(destination)
        if target.exists() and not overwrite:raise MWSConflictError('Download destination already exists.')
        # Stream failures are never replayed; callers explicitly retry the whole transfer.
        temp=None
        try:
            with self.http.stream(method,path,**kwargs) as response:
                if not response.is_success:response.read();self.error(response,body)
                with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.mws-',delete=False) as output:
                    temp=Path(output.name)
                    for chunk in response.iter_bytes():output.write(chunk)
                if target.exists() and not overwrite:raise MWSConflictError('Download destination already exists.')
                os.replace(temp,target)
            return target
        except httpx.RequestError:raise MWSConnectionError('Download interrupted; partial output was removed.') from None
        finally:
            if temp:temp.unlink(missing_ok=True)
    def close(self):self.http.close()


class AsyncTransport(Transport):
    """Async equivalent with cooperative retry waits and streamed responses."""
    asynchronous=True
    async def request(self,method,path,*,params=None,data=None,request_model=None,response_model=None,media='application/json',files=None,destination=None,overwrite=False):
        body=prepared(data,request_model);query=query_params(params);safe=method in ('GET','HEAD','OPTIONS')
        with ExitStack() as stack:
            uploads=upload_fields(files,stack);kwargs={'params':query}
            if uploads or media in ('multipart/form-data','application/x-www-form-urlencoded'):kwargs.update(data=form_data(body),files=uploads)
            elif body is not None:kwargs['json']=body
            if destination is not None:return await self.download(method,path,destination,overwrite,body,kwargs)
            for attempt in range(self.retries+1):
                try:response=await self.http.request(method,path,**kwargs)
                except httpx.RequestError:
                    if safe and attempt<self.retries:await asyncio.sleep(delay_for(None,attempt,self.maximum));continue
                    raise MWSConnectionError('Unable to reach MWS or the request timed out.') from None
                wait=delay_for(response,attempt,self.maximum) if safe and response.status_code in RETRY_STATUS and attempt<self.retries else None
                if wait is not None:await response.aclose();await asyncio.sleep(wait);continue
                try:return self.result(response,response_model,body)
                finally:await response.aclose()
    async def download(self,method,path,destination,overwrite,body,kwargs):
        target=Path(destination)
        if target.exists() and not overwrite:raise MWSConflictError('Download destination already exists.')
        temp=None
        try:
            async with self.http.stream(method,path,**kwargs) as response:
                if not response.is_success:await response.aread();self.error(response,body)
                with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.mws-',delete=False) as output:
                    temp=Path(output.name)
                    async for chunk in response.aiter_bytes():output.write(chunk)
                if target.exists() and not overwrite:raise MWSConflictError('Download destination already exists.')
                os.replace(temp,target)
            return target
        except httpx.RequestError:raise MWSConnectionError('Download interrupted; partial output was removed.') from None
        finally:
            if temp:temp.unlink(missing_ok=True)
    async def close(self):await self.http.aclose()
