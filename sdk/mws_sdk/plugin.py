"""Typed context supplied by the MWS isolated plugin runtime (plugin API 1)."""

from typing import Any, Protocol
from .client import MWSClient


class PluginContext(Protocol):
    client: MWSClient
    artifact: str | None
    case_id: int | None
    inputs: dict[str, Any]
    configuration: dict[str, Any]
    dry_run: bool

    def log(self, message: str) -> None: ...
    def external(self, service: str, path: str) -> Any: ...
