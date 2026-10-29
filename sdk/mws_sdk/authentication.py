"""Existing MWS personal bearer tokens, supplied explicitly or through environment."""
import os
import httpx
from pydantic import SecretStr
from .exceptions import MWSAuthenticationError

class BearerAuth(httpx.Auth):
    """Never include the token in repr, logs, or URLs."""
    def __init__(self, api_key: str | SecretStr | None = None):
        value=api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key if api_key is not None else os.environ.get('MWS_API_KEY')
        if not value or any(c.isspace() or ord(c)<32 for c in value):
            raise MWSAuthenticationError('Supply a bearer API key or MWS_API_KEY.')
        self.secret=SecretStr(value)
    def auth_flow(self, request):
        request.headers['Authorization']='Bearer '+self.secret.get_secret_value()
        yield request
