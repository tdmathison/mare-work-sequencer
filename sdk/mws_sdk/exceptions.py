"""Stable errors with sanitized server details; no request bodies or credentials."""
from typing import Any

class MWSError(Exception):
    """Base SDK error carrying status, request ID and sanitized details."""
    def __init__(self, message: str, *, status_code: int | None = None, request_id: str | None = None, details: Any = None, retry_after: str | None = None):
        super().__init__(message)
        self.status_code, self.request_id, self.details, self.retry_after = status_code, request_id, details, retry_after

class MWSAuthenticationError(MWSError):
    """Missing, expired or revoked credentials (401)."""
class MWSAuthorizationError(MWSError):
    """The current account lacks permission (403)."""
class MWSNotFoundError(MWSError):
    """Missing or inaccessible resource (404)."""
class MWSValidationError(MWSError):
    """Invalid client model or server validation (400/422/413)."""
class MWSConflictError(MWSError):
    """Revision, ownership, lifecycle or concurrent-job conflict (409/410)."""
class MWSRateLimitError(MWSError):
    """Request quota exceeded (429)."""
class MWSServerError(MWSError):
    """Transient or unexpected server failure (5xx)."""
class MWSConnectionError(MWSError):
    """Network or timeout failure, without sensitive request representations."""
