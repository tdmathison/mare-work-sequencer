"""Safe model serialization, paths and server-error redaction."""
import re
from typing import Any
from urllib.parse import quote
from pydantic import BaseModel, SecretStr
from .exceptions import MWSValidationError

SENSITIVE=re.compile(r'(password|passphrase|authorization|api.?key|token|secret)',re.I)

def encode(value: Any) -> Any:
    """Unwrap request secrets only at the HTTP boundary."""
    if isinstance(value,SecretStr):return value.get_secret_value()
    if isinstance(value,BaseModel):return encode(value.model_dump(exclude_unset=True))
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [encode(v) for v in value]
    return value

def redact(value: Any, secrets: tuple[str,...] = ()) -> Any:
    if isinstance(value,dict):return {k:'[REDACTED]' if SENSITIVE.search(str(k)) else redact(v,secrets) for k,v in value.items()}
    if isinstance(value,list):return [redact(v,secrets) for v in value]
    if isinstance(value,str):
        for secret in sorted((s for s in secrets if s),key=len,reverse=True):value=value.replace(secret,'[REDACTED]')
        return re.sub(r'(?i)Bearer\s+\S+','Bearer [REDACTED]',value)
    return value

def path_value(value: str | int, *, nested: bool = False) -> str:
    text=str(value)
    if not text or any(c in text for c in ('\x00','?','#','\\')) or any(p in ('.','..','') for p in text.split('/')):
        raise MWSValidationError('Invalid path identifier.')
    if not nested and '/' in text:raise MWSValidationError('An object identifier cannot contain slashes.')
    return quote(text,safe='/' if nested else '')
