"""Standalone SDK clients. Neither client imports MWS server modules."""
import json
from pathlib import Path
from .transport import Transport, AsyncTransport
from .resources import sync_resources, async_resources

NAMESPACES=sorted({op['resource'] for op in json.loads(Path(__file__).with_name('operations.json').read_text())})

def class_name(name):return ''.join(p.title() for p in name.split('_'))+'Resource'

class MWSClient:
    """Pooled synchronous REST client; close it or use a with statement.

    Args:
        base_url: Deployment URL, optionally including a reverse-proxy subpath.
            Defaults to MWS_BASE_URL. A trailing /api/v1 is also accepted.
        api_key: Personal bearer token, returned once by MWS token creation.
            Defaults to MWS_API_KEY. Existing current-user RBAC is authoritative.
        **configuration: connect_timeout, read_timeout, verify, retries,
            max_retry_delay, max_connections, max_keepalive_connections,
            trust_env, and optional httpx transport for testing.
    """
    # BEGIN RESOURCE TYPES
    actors: sync_resources.ActorsResource
    assets: sync_resources.AssetsResource
    audit: sync_resources.AuditResource
    authentication: sync_resources.AuthenticationResource
    backups: sync_resources.BackupsResource
    cases: sync_resources.CasesResource
    coverage: sync_resources.CoverageResource
    explorer: sync_resources.ExplorerResource
    families: sync_resources.FamiliesResource
    indicators: sync_resources.IndicatorsResource
    metrics: sync_resources.MetricsResource
    notes: sync_resources.NotesResource
    packages: sync_resources.PackagesResource
    plugins: sync_resources.PluginsResource
    references: sync_resources.ReferencesResource
    reports: sync_resources.ReportsResource
    roles: sync_resources.RolesResource
    search: sync_resources.SearchResource
    settings: sync_resources.SettingsResource
    tags: sync_resources.TagsResource
    tasks: sync_resources.TasksResource
    templates: sync_resources.TemplatesResource
    tools: sync_resources.ToolsResource
    users: sync_resources.UsersResource
    # END RESOURCE TYPES
    def __init__(self,base_url=None,api_key=None,**configuration):
        self._transport=Transport(base_url=base_url,api_key=api_key,**configuration)
        for name in NAMESPACES:setattr(self,name,getattr(sync_resources,class_name(name))(self._transport))
    def close(self):
        """Close the HTTP pool; safe to call repeatedly."""
        self._transport.close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
    def __repr__(self):return 'MWSClient(credentials=[REDACTED])'

class AsyncMWSClient:
    """Async counterpart with equivalent resources; use async with or await close()."""
    # BEGIN RESOURCE TYPES
    actors: async_resources.AsyncActorsResource
    assets: async_resources.AsyncAssetsResource
    audit: async_resources.AsyncAuditResource
    authentication: async_resources.AsyncAuthenticationResource
    backups: async_resources.AsyncBackupsResource
    cases: async_resources.AsyncCasesResource
    coverage: async_resources.AsyncCoverageResource
    explorer: async_resources.AsyncExplorerResource
    families: async_resources.AsyncFamiliesResource
    indicators: async_resources.AsyncIndicatorsResource
    metrics: async_resources.AsyncMetricsResource
    notes: async_resources.AsyncNotesResource
    packages: async_resources.AsyncPackagesResource
    plugins: async_resources.AsyncPluginsResource
    references: async_resources.AsyncReferencesResource
    reports: async_resources.AsyncReportsResource
    roles: async_resources.AsyncRolesResource
    search: async_resources.AsyncSearchResource
    settings: async_resources.AsyncSettingsResource
    tags: async_resources.AsyncTagsResource
    tasks: async_resources.AsyncTasksResource
    templates: async_resources.AsyncTemplatesResource
    tools: async_resources.AsyncToolsResource
    users: async_resources.AsyncUsersResource
    # END RESOURCE TYPES
    def __init__(self,base_url=None,api_key=None,**configuration):
        self._transport=AsyncTransport(base_url=base_url,api_key=api_key,**configuration)
        for name in NAMESPACES:setattr(self,name,getattr(async_resources,'Async'+class_name(name))(self._transport))
    async def close(self):
        """Close the asynchronous HTTP pool."""
        await self._transport.close()
    async def __aenter__(self):return self
    async def __aexit__(self,*exc):await self.close()
    def __repr__(self):return 'AsyncMWSClient(credentials=[REDACTED])'
