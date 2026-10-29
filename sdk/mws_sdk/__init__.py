"""MWS SDK 1.x: typed API-v1 resources for Python 3.10+."""
from .client import MWSClient, AsyncMWSClient
from .exceptions import (MWSError, MWSAuthenticationError, MWSAuthorizationError,
    MWSNotFoundError, MWSValidationError, MWSConflictError, MWSRateLimitError,
    MWSServerError, MWSConnectionError)
__version__='1.0.0'
__all__=['MWSClient','AsyncMWSClient','MWSError','MWSAuthenticationError',
'MWSAuthorizationError','MWSNotFoundError','MWSValidationError','MWSConflictError',
'MWSRateLimitError','MWSServerError','MWSConnectionError']
