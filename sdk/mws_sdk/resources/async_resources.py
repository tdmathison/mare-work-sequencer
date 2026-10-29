"""Generated, explicit REST resource methods; sync/async contracts are identical."""
from __future__ import annotations
from typing import Any, Mapping
from pathlib import Path
from ..models import *
from ..utilities import path_value
from .base import AsyncResource

class AsyncActorsResource(AsyncResource):
    """Authorized actors operations. Server-side RBAC remains authoritative."""
    async def list(self, *, params: ActorsListParams | Mapping[str, Any] | None = None) -> ActorsListResponse:
        'Read Threat Actors. GET /api/v1/actors. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'actors', params=params, response_model=ActorsListResponse)

    async def create(self, *, data: ActorsCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsCreateResponse:
        'Actors edit. POST /api/v1/actors. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors', data=data, files=files, request_model=ActorsCreateRequest, media='application/json', response_model=ActorsCreateResponse)

    async def get(self, fid: str, *, params: ActorsGetParams | Mapping[str, Any] | None = None) -> ActorsGetResponse:
        'Read Threat Actors. GET /api/v1/actors/{fid}. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'actors/{fid}'.replace('{fid}', path_value(fid, nested=False)), params=params, response_model=ActorsGetResponse)

    async def delete(self, fid: str, *, data: ActorsDeleteRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsDeleteResponse:
        'Actors delete. POST /api/v1/actors/{fid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/delete'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=ActorsDeleteRequest, media='application/json', response_model=ActorsDeleteResponse)

    async def update(self, fid: str, *, data: ActorsUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsUpdateResponse:
        'Actors edit. POST /api/v1/actors/{fid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/edit'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=ActorsUpdateRequest, media='application/json', response_model=ActorsUpdateResponse)

    async def add_osint(self, fid: str, *, data: ActorsAddOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsAddOsintResponse:
        'Actors osint edit. POST /api/v1/actors/{fid}/osint. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/osint'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=ActorsAddOsintRequest, media='multipart/form-data', response_model=ActorsAddOsintResponse)

    async def delete_osint(self, fid: str, eid: str, *, data: ActorsDeleteOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsDeleteOsintResponse:
        'Actors osint delete. POST /api/v1/actors/{fid}/osint/{eid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/osint/{eid}/delete'.replace('{fid}', path_value(fid, nested=False)).replace('{eid}', path_value(eid, nested=False)), data=data, files=files, request_model=ActorsDeleteOsintRequest, media='multipart/form-data', response_model=ActorsDeleteOsintResponse)

    async def update_osint(self, fid: str, eid: str, *, data: ActorsUpdateOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsUpdateOsintResponse:
        'Actors osint edit. POST /api/v1/actors/{fid}/osint/{eid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/osint/{eid}/edit'.replace('{fid}', path_value(fid, nested=False)).replace('{eid}', path_value(eid, nested=False)), data=data, files=files, request_model=ActorsUpdateOsintRequest, media='multipart/form-data', response_model=ActorsUpdateOsintResponse)

    async def upload_reports(self, fid: str, *, data: ActorsUploadReportsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsUploadReportsResponse:
        'Actors reports upload. POST /api/v1/actors/{fid}/reports. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/reports'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=ActorsUploadReportsRequest, media='multipart/form-data', response_model=ActorsUploadReportsResponse)

    async def delete_report(self, fid: str, aid: str, *, data: ActorsDeleteReportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsDeleteReportResponse:
        'Actors reports delete. POST /api/v1/actors/{fid}/reports/{aid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/reports/{aid}/delete'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), data=data, files=files, request_model=ActorsDeleteReportRequest, media='multipart/form-data', response_model=ActorsDeleteReportResponse)

    async def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Actors reports download. GET /api/v1/actors/{fid}/reports/{aid}/download. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'actors/{fid}/reports/{aid}/download'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), destination=destination, overwrite=overwrite)

    async def update_report(self, fid: str, aid: str, *, data: ActorsUpdateReportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ActorsUpdateReportResponse:
        'Actors reports edit. POST /api/v1/actors/{fid}/reports/{aid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'actors/{fid}/reports/{aid}/edit'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), data=data, files=files, request_model=ActorsUpdateReportRequest, media='multipart/form-data', response_model=ActorsUpdateReportResponse)

    async def iter_all(self, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'profiles', (), params):
            yield item

class AsyncAssetsResource(AsyncResource):
    """Authorized assets operations. Server-side RBAC remains authoritative."""
    async def delete(self, case_id: int, *, data: AssetsDeleteRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> None:
        'Delete a package artifact. DELETE /api/v1/cases/{case_id}/assets. \n\nRequired role permission: cases:assets.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}/assets'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=AssetsDeleteRequest, media='application/json')

    async def list(self, case_id: int, *, params: AssetsListParams | Mapping[str, Any] | None = None) -> AssetsListResponse:
        'List package files. GET /api/v1/cases/{case_id}/assets. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/assets'.replace('{case_id}', path_value(case_id, nested=False)), params=params, response_model=AssetsListResponse)

    async def upload(self, case_id: int, *, data: AssetsUploadRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> AssetsUploadResponse:
        'Upload a package artifact. POST /api/v1/cases/{case_id}/assets. Maximum 100 MiB per file. Sanitized duplicate filenames are rejected. Samples are wrapped in password-protected AES ZIP files using the configured sample password.\n\nRequired role permission: cases:assets.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/assets'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=AssetsUploadRequest, media='multipart/form-data', response_model=AssetsUploadResponse)

    async def download(self, case_id: int, relative_path: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Download a package artifact. GET /api/v1/cases/{case_id}/assets/{relative_path}. relative_path may include slashes, e.g. scripts/example.txt; it must remain within the case directory. Content-Type is inferred from the filename. Generated indicators.stix.json returns 409 if it does not match the current saved table.\n\nRequired role permission: cases:assets.'
        return await self._transport.request('GET', 'cases/{case_id}/assets/{relative_path}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{relative_path}', path_value(relative_path, nested=True)), destination=destination, overwrite=overwrite)

class AsyncAuditResource(AsyncResource):
    """Authorized audit operations. Server-side RBAC remains authoritative."""
    async def export_all(self, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Audit export all zip. GET /api/v1/audit/export-all.zip. \n\nRequired role permission: users:manage.'
        return await self._transport.request('GET', 'audit/export-all.zip', destination=destination, overwrite=overwrite)

    async def export_csv(self, *, params: AuditExportCsvParams | Mapping[str, Any] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Audit export csv. GET /api/v1/audit/export.csv. \n\nRequired role permission: users:manage.'
        return await self._transport.request('GET', 'audit/export.csv', params=params, destination=destination, overwrite=overwrite)

class AsyncAuthenticationResource(AsyncResource):
    """Authorized authentication operations. Server-side RBAC remains authoritative."""
    async def me(self) -> AuthenticationMeResponse:
        'Inspect the authenticated account and permissions. GET /api/v1/me. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'me', response_model=AuthenticationMeResponse)

    async def list_tokens(self) -> AuthenticationListTokensResponse:
        'List your token metadata (no secrets). GET /api/v1/tokens. \n\nRequired role permission: tokens:manage.'
        return await self._transport.request('GET', 'tokens', response_model=AuthenticationListTokensResponse)

    async def create_token(self, *, data: AuthenticationCreateTokenRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> AuthenticationCreateTokenResponse:
        'Create a bearer token. POST /api/v1/tokens. \n\nRequired role permission: tokens:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tokens', data=data, files=files, request_model=AuthenticationCreateTokenRequest, media='application/json', response_model=AuthenticationCreateTokenResponse)

    async def revoke_token(self, token_id: int) -> None:
        'Revoke a token. DELETE /api/v1/tokens/{token_id}. Own tokens only, unless users:manage is also held. Repeated revocation returns 204.\n\nRequired role permission: tokens:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'tokens/{token_id}'.replace('{token_id}', path_value(token_id, nested=False)))

class AsyncBackupsResource(AsyncResource):
    """Authorized backups operations. Server-side RBAC remains authoritative."""
    async def create_job(self, *, data: BackupsCreateJobRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> BackupsCreateJobResponse:
        'Backup jobs create. POST /api/v1/backup-jobs. \n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backup-jobs', data=data, files=files, request_model=BackupsCreateJobRequest, media='multipart/form-data', response_model=BackupsCreateJobResponse)

    async def job(self, jid: str) -> BackupsJobResponse:
        'Backup jobs status. GET /api/v1/backup-jobs/{jid}. \n\nRequired role permission: backups:manage.'
        return await self._transport.request('GET', 'backup-jobs/{jid}'.replace('{jid}', path_value(jid, nested=False)), response_model=BackupsJobResponse)

    async def apply(self, jid: str, *, data: BackupsApplyRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> BackupsApplyResponse:
        'Backup jobs apply. POST /api/v1/backup-jobs/{jid}/apply. \n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backup-jobs/{jid}/apply'.replace('{jid}', path_value(jid, nested=False)), data=data, files=files, request_model=BackupsApplyRequest, media='multipart/form-data', response_model=BackupsApplyResponse)

    async def download(self, jid: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Backup jobs download. GET /api/v1/backup-jobs/{jid}/download. \n\nRequired role permission: backups:manage.'
        return await self._transport.request('GET', 'backup-jobs/{jid}/download'.replace('{jid}', path_value(jid, nested=False)), destination=destination, overwrite=overwrite)

    async def preview(self, jid: str, *, data: BackupsPreviewRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> BackupsPreviewResponse:
        'Backup jobs preview. POST /api/v1/backup-jobs/{jid}/preview. \n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backup-jobs/{jid}/preview'.replace('{jid}', path_value(jid, nested=False)), data=data, files=files, request_model=BackupsPreviewRequest, media='multipart/form-data', response_model=BackupsPreviewResponse)

    async def sync_apply(self, operation: str, *, data: BackupsSyncApplyRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> SyncResult:
        'Apply validated per-case synchronization decisions. POST /api/v1/backups/apply/{operation}. Object keyed by the zero-based review case index (string). Omitted decisions apply safe automatic new/update/unchanged/older actions; unresolved/invalid cases are skipped. Conflicts need explicit keep or replace. Legacy review also supports new or link (target is a local numeric case ID). Revision validation, ownership checks and recovery snapshots remain enforced; inspect each actual outcome for failure/rollback. Only the staging account may apply; preview expires after one hour.\n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backups/apply/{operation}'.replace('{operation}', path_value(operation, nested=False)), data=data, files=files, request_model=BackupsSyncApplyRequest, media='application/json', response_model=SyncResult)

    async def export_cases(self, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Download a full case backup ZIP. POST /api/v1/backups/export. Includes nested case RAW ZIPs and metadata; excludes malware samples.\n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backups/export', destination=destination, overwrite=overwrite)

    async def import_cases(self, *, data: BackupsImportCasesRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> BackupsImportCasesResponse:
        'Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.\n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backups/import', data=data, files=files, request_model=BackupsImportCasesRequest, media='multipart/form-data', response_model=BackupsImportCasesResponse)

    async def import_raw(self, *, data: BackupsImportRawRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> BackupsImportRawResponse:
        'Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import-raw. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.\n\nRequired role permission: backups:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'backups/import-raw', data=data, files=files, request_model=BackupsImportRawRequest, media='multipart/form-data', response_model=BackupsImportRawResponse)

    async def sync_review(self, operation: str) -> SyncResult:
        'Review a staged synchronization or its outcomes. GET /api/v1/backups/review/{operation}. Only the account that staged the archive may access it. Expired preview returns 410.\n\nRequired role permission: backups:manage.'
        return await self._transport.request('GET', 'backups/review/{operation}'.replace('{operation}', path_value(operation, nested=False)), response_model=SyncResult)

    async def case(self, case_id: int, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Download a case RAW backup ZIP. POST /api/v1/cases/{case_id}/backup. Includes case metadata and email-safe Python filenames. Malware samples excluded.\n\nRequired role permission: cases:export.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/backup'.replace('{case_id}', path_value(case_id, nested=False)), destination=destination, overwrite=overwrite)

class AsyncCasesResource(AsyncResource):
    """Authorized cases operations. Server-side RBAC remains authoritative."""
    async def list(self, *, params: CasesListParams | Mapping[str, Any] | None = None) -> CasesListResponse:
        'List cases newest first. GET /api/v1/cases. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases', params=params, response_model=CasesListResponse)

    async def create(self, *, data: CasesCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> CasesCreateResponse:
        'Create a case. POST /api/v1/cases. A date prefix is added to the title if absent; the resulting name must remain ≤200 characters. External system and number must be supplied together. Owner must be active.\n\nRequired role permission: cases:create.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases', data=data, files=files, request_model=CasesCreateRequest, media='application/json', response_model=CasesCreateResponse)

    async def delete(self, case_id: int) -> None:
        'Permanently delete a case and its files. DELETE /api/v1/cases/{case_id}. Real destructive operation. Active report generation blocks deletion; there is no additional API confirmation field.\n\nRequired role permission: cases:delete.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}'.replace('{case_id}', path_value(case_id, nested=False)))

    async def get(self, case_id: int) -> CasesGetResponse:
        'Read case details and workflow history. GET /api/v1/cases/{case_id}. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}'.replace('{case_id}', path_value(case_id, nested=False)), response_model=CasesGetResponse)

    async def update(self, case_id: int, *, data: CasesUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> CasesUpdateResponse:
        'Update case metadata or ownership. PATCH /api/v1/cases/{case_id}. External system/number must be paired. Stage changes use the dedicated workflow endpoint.\n\nRequired role permission: cases:update.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'cases/{case_id}'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=CasesUpdateRequest, media='application/json', response_model=CasesUpdateResponse)

    async def reopen(self, case_id: int) -> CasesReopenResponse:
        'Reopen a completed case for analysis. POST /api/v1/cases/{case_id}/reopen. Completed cases only; active owner required when ownership is mandatory.\n\nRequired role permission: cases:workflow.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/reopen'.replace('{case_id}', path_value(case_id, nested=False)), response_model=CasesReopenResponse)

    async def advance(self, case_id: int, *, data: CasesAdvanceRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> CasesAdvanceResponse:
        'Advance one workflow stage. POST /api/v1/cases/{case_id}/stage. expected must equal the current stage. Active owner required to start; skipped/deferred outcomes require a reason. Completion checks readiness and review blockers. Stage 0 always records Started.\n\nRequired role permission: cases:workflow.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/stage'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=CasesAdvanceRequest, media='application/json', response_model=CasesAdvanceResponse)

    async def iter_all(self, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'cases', (), params):
            yield item

class AsyncCoverageResource(AsyncResource):
    """Authorized coverage operations. Server-side RBAC remains authoritative."""
    async def get(self, *, params: CoverageGetParams | Mapping[str, Any] | None = None) -> CoverageGetResponse:
        'Explorer coverage. GET /api/v1/coverage. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'coverage', params=params, response_model=CoverageGetResponse)

class AsyncExplorerResource(AsyncResource):
    """Authorized explorer operations. Server-side RBAC remains authoritative."""
    async def contents(self, case_id: int, *, params: ExplorerContentsParams | Mapping[str, Any] | None = None) -> ExplorerContentsResponse:
        'Explorer contents. GET /api/v1/explorer/cases/{case_id}/contents. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'explorer/cases/{case_id}/contents'.replace('{case_id}', path_value(case_id, nested=False)), params=params, response_model=ExplorerContentsResponse)

    async def category(self, case_id: int, category: str, *, params: ExplorerCategoryParams | Mapping[str, Any] | None = None) -> ExplorerCategoryResponse:
        'Explorer category. GET /api/v1/explorer/cases/{case_id}/contents/{category}. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'explorer/cases/{case_id}/contents/{category}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{category}', path_value(category, nested=False)), params=params, response_model=ExplorerCategoryResponse)

    async def download(self, case_id: int, *, params: ExplorerDownloadParams | Mapping[str, Any] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Explorer file. GET /api/v1/explorer/cases/{case_id}/file. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'explorer/cases/{case_id}/file'.replace('{case_id}', path_value(case_id, nested=False)), params=params, destination=destination, overwrite=overwrite)

    async def connection_objects(self, *, params: ExplorerConnectionObjectsParams | Mapping[str, Any] | None = None) -> ExplorerConnectionObjectsResponse:
        'Explorer connection objects. GET /api/v1/explorer/connection-objects. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/connection-objects', params=params, response_model=ExplorerConnectionObjectsResponse)

    async def connections(self, *, params: ExplorerConnectionsParams | Mapping[str, Any] | None = None) -> ExplorerConnectionsResponse:
        'Explorer connections. GET /api/v1/explorer/connections. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/connections', params=params, response_model=ExplorerConnectionsResponse)

    async def evidence(self, *, params: ExplorerEvidenceParams | Mapping[str, Any] | None = None) -> ExplorerEvidenceResponse:
        'Explorer evidence. GET /api/v1/explorer/evidence. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/evidence', params=params, response_model=ExplorerEvidenceResponse)

    async def graph(self, *, params: ExplorerGraphParams | Mapping[str, Any] | None = None) -> ExplorerGraphResponse:
        'Explorer data. GET /api/v1/explorer/graph. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/graph', params=params, response_model=ExplorerGraphResponse)

    async def shared_indicators(self, *, params: ExplorerSharedIndicatorsParams | Mapping[str, Any] | None = None) -> ExplorerSharedIndicatorsResponse:
        'Explorer shared indicators. GET /api/v1/explorer/shared-indicators. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/shared-indicators', params=params, response_model=ExplorerSharedIndicatorsResponse)

    async def list_views(self) -> ExplorerListViewsResponse:
        'Explorer views. GET /api/v1/explorer/views. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/views', response_model=ExplorerListViewsResponse)

    async def create_view(self, *, data: ExplorerCreateViewRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ExplorerCreateViewResponse:
        'Explorer view create. POST /api/v1/explorer/views. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'explorer/views', data=data, files=files, request_model=ExplorerCreateViewRequest, media='application/json', response_model=ExplorerCreateViewResponse)

    async def get_view(self, vid: str) -> ExplorerGetViewResponse:
        'Explorer view. GET /api/v1/explorer/views/{vid}. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'explorer/views/{vid}'.replace('{vid}', path_value(vid, nested=False)), response_model=ExplorerGetViewResponse)

    async def delete_view(self, vid: str, *, data: ExplorerDeleteViewRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ExplorerDeleteViewResponse:
        'Explorer view delete. POST /api/v1/explorer/views/{vid}/delete. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'explorer/views/{vid}/delete'.replace('{vid}', path_value(vid, nested=False)), data=data, files=files, request_model=ExplorerDeleteViewRequest, media='application/json', response_model=ExplorerDeleteViewResponse)

    async def update_view(self, vid: str, *, data: ExplorerUpdateViewRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ExplorerUpdateViewResponse:
        'Explorer view update. POST /api/v1/explorer/views/{vid}/update. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'explorer/views/{vid}/update'.replace('{vid}', path_value(vid, nested=False)), data=data, files=files, request_model=ExplorerUpdateViewRequest, media='application/json', response_model=ExplorerUpdateViewResponse)

class AsyncFamiliesResource(AsyncResource):
    """Authorized families operations. Server-side RBAC remains authoritative."""
    async def list(self, *, params: FamiliesListParams | Mapping[str, Any] | None = None) -> FamiliesListResponse:
        'Read Malware Families. GET /api/v1/families. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'families', params=params, response_model=FamiliesListResponse)

    async def create(self, *, data: FamiliesCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesCreateResponse:
        'Families edit. POST /api/v1/families. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families', data=data, files=files, request_model=FamiliesCreateRequest, media='application/json', response_model=FamiliesCreateResponse)

    async def get(self, fid: str, *, params: FamiliesGetParams | Mapping[str, Any] | None = None) -> FamiliesGetResponse:
        'Read Malware Families. GET /api/v1/families/{fid}. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'families/{fid}'.replace('{fid}', path_value(fid, nested=False)), params=params, response_model=FamiliesGetResponse)

    async def delete(self, fid: str, *, data: FamiliesDeleteRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesDeleteResponse:
        'Families delete. POST /api/v1/families/{fid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/delete'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=FamiliesDeleteRequest, media='application/json', response_model=FamiliesDeleteResponse)

    async def update(self, fid: str, *, data: FamiliesUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesUpdateResponse:
        'Families edit. POST /api/v1/families/{fid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/edit'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=FamiliesUpdateRequest, media='application/json', response_model=FamiliesUpdateResponse)

    async def add_osint(self, fid: str, *, data: FamiliesAddOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesAddOsintResponse:
        'Families osint edit. POST /api/v1/families/{fid}/osint. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/osint'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=FamiliesAddOsintRequest, media='multipart/form-data', response_model=FamiliesAddOsintResponse)

    async def delete_osint(self, fid: str, eid: str, *, data: FamiliesDeleteOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesDeleteOsintResponse:
        'Families osint delete. POST /api/v1/families/{fid}/osint/{eid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/osint/{eid}/delete'.replace('{fid}', path_value(fid, nested=False)).replace('{eid}', path_value(eid, nested=False)), data=data, files=files, request_model=FamiliesDeleteOsintRequest, media='multipart/form-data', response_model=FamiliesDeleteOsintResponse)

    async def update_osint(self, fid: str, eid: str, *, data: FamiliesUpdateOsintRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesUpdateOsintResponse:
        'Families osint edit. POST /api/v1/families/{fid}/osint/{eid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/osint/{eid}/edit'.replace('{fid}', path_value(fid, nested=False)).replace('{eid}', path_value(eid, nested=False)), data=data, files=files, request_model=FamiliesUpdateOsintRequest, media='multipart/form-data', response_model=FamiliesUpdateOsintResponse)

    async def upload_reports(self, fid: str, *, data: FamiliesUploadReportsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesUploadReportsResponse:
        'Families reports upload. POST /api/v1/families/{fid}/reports. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/reports'.replace('{fid}', path_value(fid, nested=False)), data=data, files=files, request_model=FamiliesUploadReportsRequest, media='multipart/form-data', response_model=FamiliesUploadReportsResponse)

    async def delete_report(self, fid: str, aid: str, *, data: FamiliesDeleteReportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesDeleteReportResponse:
        'Families reports delete. POST /api/v1/families/{fid}/reports/{aid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/reports/{aid}/delete'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), data=data, files=files, request_model=FamiliesDeleteReportRequest, media='multipart/form-data', response_model=FamiliesDeleteReportResponse)

    async def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Families reports download. GET /api/v1/families/{fid}/reports/{aid}/download. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'families/{fid}/reports/{aid}/download'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), destination=destination, overwrite=overwrite)

    async def update_report(self, fid: str, aid: str, *, data: FamiliesUpdateReportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> FamiliesUpdateReportResponse:
        'Families reports edit. POST /api/v1/families/{fid}/reports/{aid}/edit. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'families/{fid}/reports/{aid}/edit'.replace('{fid}', path_value(fid, nested=False)).replace('{aid}', path_value(aid, nested=False)), data=data, files=files, request_model=FamiliesUpdateReportRequest, media='multipart/form-data', response_model=FamiliesUpdateReportResponse)

    async def iter_all(self, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'profiles', (), params):
            yield item

class AsyncIndicatorsResource(AsyncResource):
    """Authorized indicators operations. Server-side RBAC remains authoritative."""
    async def get(self, case_id: int) -> Indicators:
        'Read indicators and revision. GET /api/v1/cases/{case_id}/indicators. \n\nRequired role permission: indicators:read.'
        return await self._transport.request('GET', 'cases/{case_id}/indicators'.replace('{case_id}', path_value(case_id, nested=False)), response_model=Indicators)

    async def update(self, case_id: int, *, data: IndicatorsUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> Indicators:
        'Replace indicators with revision validation. PUT /api/v1/cases/{case_id}/indicators. Send all sections to preserve grouping, or rows when exactly one section exists. Each row has three text cells (≤4,000 characters), 1–100 sections with unique IDs (1–64 alphanumeric/underscore/hyphen), a nonempty title ≤200 characters and description ≤4,000 characters. The default section must remain; ≤10,000 rows total. revision must equal the current revision. The bundled official MISP attribute catalog is selectable/storable; export capability/help is supplied per type. Known compatibility aliases normalize on save; exact MISP canonical names take precedence. text/comment/other retain literal Unicode/whitespace and export as non-detection x-misp-attribute objects; Valid scalar attributes without native mappings use the official MISP-compatible contextual representation, with informational stix.notices. Missing attachment/sample bytes and invalid values retain saved drafts with explicit stix.issues. Legacy android-package aliases normalize to mobile-application-id while retaining identity and original_type provenance. Unknown/ambiguous types and invalid values remain saved as drafts with stix.issues; CSV is refreshed and stale STIX removed. Fully exportable tables generate iocs/indicators.stix.json with refanged native patterns and faithful contextual objects; any unsupported row withholds the entire STIX output. Preserve optional row_meta (including explicit boolean to_ids detection intent) and stix_meta when editing to retain IDs/timestamps/intent; do not generate them yourself. Unchanged saves do not advance revision. The authenticated web Indicators workspace provides CSV/STIX import previews and a read-only download; equivalent versioned preview/import/STIX download endpoints are also available to SDK clients.\n\nRequired role permission: indicators:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/indicators'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=IndicatorsUpdateRequest, media='application/json', response_model=Indicators)

    async def import_rows(self, cid: int, *, data: IndicatorsImportRowsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> IndicatorsImportRowsResponse:
        'Indicators import. POST /api/v1/cases/{cid}/indicators/import. \n\nRequired role permission: indicators:write.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/indicators/import'.replace('{cid}', path_value(cid, nested=False)), data=data, files=files, request_model=IndicatorsImportRowsRequest, media='application/json', response_model=IndicatorsImportRowsResponse)

    async def preview_import(self, cid: int, *, data: IndicatorsPreviewImportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> IndicatorsPreviewImportResponse:
        'Indicators import preview. POST /api/v1/cases/{cid}/indicators/import/preview. \n\nRequired role permission: indicators:write.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/indicators/import/preview'.replace('{cid}', path_value(cid, nested=False)), data=data, files=files, request_model=IndicatorsPreviewImportRequest, media='application/json', response_model=IndicatorsPreviewImportResponse)

    async def download_stix(self, cid: int, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Indicators stix download. GET /api/v1/cases/{cid}/indicators/stix. \n\nRequired role permission: indicators:read.'
        return await self._transport.request('GET', 'cases/{cid}/indicators/stix'.replace('{cid}', path_value(cid, nested=False)), destination=destination, overwrite=overwrite)

class AsyncMetricsResource(AsyncResource):
    """Authorized metrics operations. Server-side RBAC remains authoritative."""
    async def get(self) -> MetricsGetResponse:
        'Read all-time metrics. GET /api/v1/metrics. Legacy all-time API metrics; independent of dashboard period filters.\n\nRequired role permission: metrics:read.'
        return await self._transport.request('GET', 'metrics', response_model=MetricsGetResponse)

class AsyncNotesResource(AsyncResource):
    """Authorized notes operations. Server-side RBAC remains authoritative."""
    async def delete_draft(self, case_id: int) -> None:
        'Delete your case note draft. DELETE /api/v1/cases/{case_id}/draft. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}/draft'.replace('{case_id}', path_value(case_id, nested=False)))

    async def get_draft(self, case_id: int) -> NotesGetDraftResponse:
        'Read your case note draft. GET /api/v1/cases/{case_id}/draft. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/draft'.replace('{case_id}', path_value(case_id, nested=False)), response_model=NotesGetDraftResponse)

    async def update_draft(self, case_id: int, *, data: NotesUpdateDraftRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> NotesUpdateDraftResponse:
        'Replace your case note draft. PUT /api/v1/cases/{case_id}/draft. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/draft'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=NotesUpdateDraftRequest, media='application/json', response_model=NotesUpdateDraftResponse)

    async def list(self, case_id: int, *, params: NotesListParams | Mapping[str, Any] | None = None) -> NotesListResponse:
        'List case notes. GET /api/v1/cases/{case_id}/notes. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/notes'.replace('{case_id}', path_value(case_id, nested=False)), params=params, response_model=NotesListResponse)

    async def create(self, case_id: int, *, data: NotesCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> NotesCreateResponse:
        'Create a note. POST /api/v1/cases/{case_id}/notes. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/notes'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=NotesCreateRequest, media='application/json', response_model=NotesCreateResponse)

    async def delete(self, case_id: int, note_id: int) -> None:
        'Delete a note. DELETE /api/v1/cases/{case_id}/notes/{note_id}. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}/notes/{note_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{note_id}', path_value(note_id, nested=False)))

    async def get(self, case_id: int, note_id: int) -> NotesGetResponse:
        'Read a case note. GET /api/v1/cases/{case_id}/notes/{note_id}. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/notes/{note_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{note_id}', path_value(note_id, nested=False)), response_model=NotesGetResponse)

    async def update(self, case_id: int, note_id: int, *, data: NotesUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> NotesUpdateResponse:
        'Update a note. PATCH /api/v1/cases/{case_id}/notes/{note_id}. The resulting body must contain non-whitespace text.\n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'cases/{case_id}/notes/{note_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{note_id}', path_value(note_id, nested=False)), data=data, files=files, request_model=NotesUpdateRequest, media='application/json', response_model=NotesUpdateResponse)

    async def iter_all(self, case_id, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'notes', (case_id,), params):
            yield item

class AsyncPackagesResource(AsyncResource):
    """Authorized packages operations. Server-side RBAC remains authoritative."""
    async def export(self, case_id: int, *, data: PackagesExportRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Download a Standard or RAW MIP ZIP. POST /api/v1/cases/{case_id}/archive. Packaging & Delivery or Completed only; active owner required when mandatory. Standard requires a completed Word report. Outstanding review blockers require acknowledge=true. Including samples additionally requires samples:export. Malware sample archives are dangerous; handle only in an isolated analysis environment.\n\nRequired role permission: cases:export.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/archive'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=PackagesExportRequest, media='application/json', destination=destination, overwrite=overwrite)

    async def readiness(self, case_id: int) -> PackagesReadinessResponse:
        'Read package readiness. GET /api/v1/cases/{case_id}/readiness. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/readiness'.replace('{case_id}', path_value(case_id, nested=False)), response_model=PackagesReadinessResponse)

    async def set_readiness(self, case_id: int, *, data: PackagesSetReadinessRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> PackagesSetReadinessResponse:
        'Set one category readiness. PUT /api/v1/cases/{case_id}/readiness. Not applicable requires a reason and is forbidden for reports. Populated requires an existing file.\n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/readiness'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=PackagesSetReadinessRequest, media='application/json', response_model=PackagesSetReadinessResponse)

class AsyncPluginsResource(AsyncResource):
    """Authorized plugins operations. Server-side RBAC remains authoritative."""
    async def capabilities(self) -> PluginsCapabilitiesResponse:
        'Inspect existing plugin integration capabilities. GET /api/v1/plugins. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'plugins', response_model=PluginsCapabilitiesResponse)

class AsyncReferencesResource(AsyncResource):
    """Authorized references operations. Server-side RBAC remains authoritative."""
    async def get(self, case_id: int) -> References:
        'Read references and revision. GET /api/v1/cases/{case_id}/references. \n\nRequired role permission: references:read.'
        return await self._transport.request('GET', 'cases/{case_id}/references'.replace('{case_id}', path_value(case_id, nested=False)), response_model=References)

    async def update(self, case_id: int, *, data: ReferencesUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> References:
        'Replace references with revision validation. PUT /api/v1/cases/{case_id}/references. Fixed columns Link, Description. revision must equal the current revision.\n\nRequired role permission: references:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/references'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReferencesUpdateRequest, media='application/json', response_model=References)

class AsyncReportsResource(AsyncResource):
    """Authorized reports operations. Server-side RBAC remains authoritative."""
    async def get(self, case_id: int) -> ReportsGetResponse:
        'Read report sections and mappings. GET /api/v1/cases/{case_id}/report. \n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report'.replace('{case_id}', path_value(case_id, nested=False)), response_model=ReportsGetResponse)

    async def update(self, case_id: int, *, data: ReportsUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ReportsUpdateResponse:
        'Save manual report sections. PUT /api/v1/cases/{case_id}/report. Only manual sections are written; generated sections are accepted but not persisted. Omitted manual sections retain their current values.\n\nRequired role permission: reports:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/report'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReportsUpdateRequest, media='application/json', response_model=ReportsUpdateResponse)

    async def download(self, case_id: int, *, params: ReportsDownloadParams | Mapping[str, Any] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Download the current report. GET /api/v1/cases/{case_id}/report/download. 404 if the requested output has not been generated.\n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report/download'.replace('{case_id}', path_value(case_id, nested=False)), params=params, destination=destination, overwrite=overwrite)

    async def upload(self, case_id: int, *, data: ReportsUploadRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ReportsUploadResponse:
        'Upload an edited DOCX report. POST /api/v1/cases/{case_id}/report/final. Valid DOCX ≤20 MiB required. backup=1 saves the previous report. generate_pdf=0 skips PDF conversion; otherwise LibreOffice is required. Active report jobs block replacement.\n\nRequired role permission: reports:generate.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/report/final'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReportsUploadRequest, media='multipart/form-data', response_model=ReportsUploadResponse)

    async def generate(self, case_id: int, *, data: ReportsGenerateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ReportsGenerateResponse:
        'Start local Word report generation. POST /api/v1/cases/{case_id}/report/generate. Select an available template first. Generation saves supplied manual sections; omitted manual fields become empty. Read and submit existing sections to retain them. Existing reports require an explicit previous=backup or overwrite choice (409 needs_choice otherwise). Poll report/job; PDF generation requires LibreOffice. Accepts JSON or form fields.\n\nRequired role permission: reports:generate.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/report/generate'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReportsGenerateRequest, media='application/json', response_model=ReportsGenerateResponse)

    async def list_images(self, case_id: int) -> ReportsListImagesResponse:
        'List report image metadata. GET /api/v1/cases/{case_id}/report/images. \n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report/images'.replace('{case_id}', path_value(case_id, nested=False)), response_model=ReportsListImagesResponse)

    async def upload_image(self, case_id: int, *, data: ReportsUploadImageRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> Image:
        'Upload a report or task image. POST /api/v1/cases/{case_id}/report/images. Readable image ≤10 MiB and ≤20 megapixels; normalized to PNG. Active report jobs block changes.\n\nRequired role permission: reports:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/report/images'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReportsUploadImageRequest, media='multipart/form-data', response_model=Image)

    async def delete_image(self, case_id: int, name: str) -> None:
        'Delete a report image. DELETE /api/v1/cases/{case_id}/report/images/{name}. \n\nRequired role permission: reports:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}/report/images/{name}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{name}', path_value(name, nested=False)))

    async def download_image(self, case_id: int, name: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Download a report image. GET /api/v1/cases/{case_id}/report/images/{name}. \n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report/images/{name}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{name}', path_value(name, nested=False)), destination=destination, overwrite=overwrite)

    async def job(self, case_id: int) -> ReportsJobResponse:
        'Read the latest report generation job. GET /api/v1/cases/{case_id}/report/job. \n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report/job'.replace('{case_id}', path_value(case_id, nested=False)), response_model=ReportsJobResponse)

    async def get_mappings(self, case_id: int) -> ReportsGetMappingsResponse:
        'Read MITRE mappings. GET /api/v1/cases/{case_id}/report/mappings. \n\nRequired role permission: reports:read.'
        return await self._transport.request('GET', 'cases/{case_id}/report/mappings'.replace('{case_id}', path_value(case_id, nested=False)), response_model=ReportsGetMappingsResponse)

    async def update_mappings(self, case_id: int, *, data: ReportsUpdateMappingsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ReportsUpdateMappingsResponse:
        'Save MITRE mapping Markdown. PUT /api/v1/cases/{case_id}/report/mappings. Blank text removes that mapping. Active report generation blocks saving.\n\nRequired role permission: reports:write.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'cases/{case_id}/report/mappings'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=ReportsUpdateMappingsRequest, media='application/json', response_model=ReportsUpdateMappingsResponse)

class AsyncRolesResource(AsyncResource):
    """Authorized roles operations. Server-side RBAC remains authoritative."""
    async def permissions(self) -> RolesPermissionsResponse:
        'List known permission names. GET /api/v1/permissions. \n\nRequired role permission: roles:manage.'
        return await self._transport.request('GET', 'permissions', response_model=RolesPermissionsResponse)

    async def list(self) -> RolesListResponse:
        'List roles and permissions. GET /api/v1/roles. \n\nRequired role permission: roles:manage.'
        return await self._transport.request('GET', 'roles', response_model=RolesListResponse)

    async def create(self, *, data: RolesCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> Role:
        'Create a custom role. POST /api/v1/roles. Only known, unique permissions already held by the caller may be granted.\n\nRequired role permission: roles:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'roles', data=data, files=files, request_model=RolesCreateRequest, media='application/json', response_model=Role)

    async def delete(self, name: str) -> None:
        'Delete an unused custom role. DELETE /api/v1/roles/{name}. Built-in roles and roles assigned to users cannot be deleted.\n\nRequired role permission: roles:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'roles/{name}'.replace('{name}', path_value(name, nested=False)))

    async def get(self, name: str) -> Role:
        'Read role metadata. GET /api/v1/roles/{name}. \n\nRequired role permission: roles:manage.'
        return await self._transport.request('GET', 'roles/{name}'.replace('{name}', path_value(name, nested=False)), response_model=Role)

    async def update(self, name: str, *, data: RolesUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> Role:
        'Update a custom role. PATCH /api/v1/roles/{name}. Built-in roles are immutable. Cannot grant permissions the caller does not hold.\n\nRequired role permission: roles:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'roles/{name}'.replace('{name}', path_value(name, nested=False)), data=data, files=files, request_model=RolesUpdateRequest, media='application/json', response_model=Role)

class AsyncSearchResource(AsyncResource):
    """Authorized search operations. Server-side RBAC remains authoritative."""
    async def query(self, *, params: SearchQueryParams | Mapping[str, Any] | None = None) -> SearchQueryResponse:
        'Mip search results. GET /api/v1/search. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'search', params=params, response_model=SearchQueryResponse)

class AsyncSettingsResource(AsyncResource):
    """Authorized settings operations. Server-side RBAC remains authoritative."""
    async def get(self) -> SettingsGetResponse:
        'Inspect configured settings (no secrets). GET /api/v1/settings. \n\nRequired role permission: settings:read.'
        return await self._transport.request('GET', 'settings', response_model=SettingsGetResponse)

    async def update(self, *, data: SettingsUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> SettingsUpdateResponse:
        'Set the sample archive password. PATCH /api/v1/settings. NUL characters are rejected. Changes affect future sample archives; the password is never returned.\n\nRequired role permission: settings:write.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'settings', data=data, files=files, request_model=SettingsUpdateRequest, media='application/json', response_model=SettingsUpdateResponse)

class AsyncTagsResource(AsyncResource):
    """Authorized tags operations. Server-side RBAC remains authoritative."""
    async def for_case(self, cid: int) -> TagsForCaseResponse:
        'Case tags list. GET /api/v1/cases/{cid}/tags. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'cases/{cid}/tags'.replace('{cid}', path_value(cid, nested=False)), response_model=TagsForCaseResponse)

    async def assign(self, cid: int, tid: int) -> TagsAssignResponse:
        'Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/assign. \n\nRequired role permission: tags:assign.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/tags/{tid}/assign'.replace('{cid}', path_value(cid, nested=False)).replace('{tid}', path_value(tid, nested=False)), response_model=TagsAssignResponse)

    async def remove(self, cid: int, tid: int) -> TagsRemoveResponse:
        'Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/remove. \n\nRequired role permission: tags:assign.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/tags/{tid}/remove'.replace('{cid}', path_value(cid, nested=False)).replace('{tid}', path_value(tid, nested=False)), response_model=TagsRemoveResponse)

    async def list(self, *, params: TagsListParams | Mapping[str, Any] | None = None) -> TagsListResponse:
        'Tags search. GET /api/v1/tags. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'tags', params=params, response_model=TagsListResponse)

    async def create(self, *, data: TagsCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TagsCreateResponse:
        'Tags create. POST /api/v1/tags. \n\nRequired role permission: tags:create.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tags', data=data, files=files, request_model=TagsCreateRequest, media='application/json', response_model=TagsCreateResponse)

    async def get(self, tid: int) -> TagsGetResponse:
        'Read a tag. GET /api/v1/tags/{tid}. \n\nRequired role permission: tags:read.'
        return await self._transport.request('GET', 'tags/{tid}'.replace('{tid}', path_value(tid, nested=False)), response_model=TagsGetResponse)

    async def delete(self, tid: int, *, data: TagsDeleteRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TagsDeleteResponse:
        'Tag manage. POST /api/v1/tags/{tid}/delete. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tags/{tid}/delete'.replace('{tid}', path_value(tid, nested=False)), data=data, files=files, request_model=TagsDeleteRequest, media='application/json', response_model=TagsDeleteResponse)

    async def merge(self, tid: int, *, data: TagsMergeRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TagsMergeResponse:
        'Tag manage. POST /api/v1/tags/{tid}/merge. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tags/{tid}/merge'.replace('{tid}', path_value(tid, nested=False)), data=data, files=files, request_model=TagsMergeRequest, media='application/json', response_model=TagsMergeResponse)

    async def rename(self, tid: int, *, data: TagsRenameRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TagsRenameResponse:
        'Tag manage. POST /api/v1/tags/{tid}/rename. \n\nRequired role permission: tags:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tags/{tid}/rename'.replace('{tid}', path_value(tid, nested=False)), data=data, files=files, request_model=TagsRenameRequest, media='application/json', response_model=TagsRenameResponse)

class AsyncTasksResource(AsyncResource):
    """Authorized tasks operations. Server-side RBAC remains authoritative."""
    async def list(self, case_id: int, *, params: TasksListParams | Mapping[str, Any] | None = None) -> TasksListResponse:
        'List case tasks. GET /api/v1/cases/{case_id}/tasks. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/tasks'.replace('{case_id}', path_value(case_id, nested=False)), params=params, response_model=TasksListResponse)

    async def create(self, case_id: int, *, data: TasksCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TasksCreateResponse:
        'Create a task. POST /api/v1/cases/{case_id}/tasks. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{case_id}/tasks'.replace('{case_id}', path_value(case_id, nested=False)), data=data, files=files, request_model=TasksCreateRequest, media='application/json', response_model=TasksCreateResponse)

    async def delete(self, case_id: int, task_id: int) -> None:
        'Delete a task. DELETE /api/v1/cases/{case_id}/tasks/{task_id}. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'cases/{case_id}/tasks/{task_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{task_id}', path_value(task_id, nested=False)))

    async def get(self, case_id: int, task_id: int) -> TasksGetResponse:
        'Read a case task. GET /api/v1/cases/{case_id}/tasks/{task_id}. \n\nRequired role permission: cases:read.'
        return await self._transport.request('GET', 'cases/{case_id}/tasks/{task_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{task_id}', path_value(task_id, nested=False)), response_model=TasksGetResponse)

    async def update(self, case_id: int, task_id: int, *, data: TasksUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TasksUpdateResponse:
        'Update a task. PATCH /api/v1/cases/{case_id}/tasks/{task_id}. \n\nRequired role permission: cases:update.\n\nContent edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'cases/{case_id}/tasks/{task_id}'.replace('{case_id}', path_value(case_id, nested=False)).replace('{task_id}', path_value(task_id, nested=False)), data=data, files=files, request_model=TasksUpdateRequest, media='application/json', response_model=TasksUpdateResponse)

    async def iter_all(self, case_id, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'tasks', (case_id,), params):
            yield item

class AsyncTemplatesResource(AsyncResource):
    """Authorized templates operations. Server-side RBAC remains authoritative."""
    async def list(self) -> TemplatesListResponse:
        'List your Word templates. GET /api/v1/templates. \n\nRequired role permission: templates:manage.'
        return await self._transport.request('GET', 'templates', response_model=TemplatesListResponse)

    async def upload(self, *, data: TemplatesUploadRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TemplatesUploadResponse:
        'Upload and select a Word template. POST /api/v1/templates. DOCX ≤10 MiB, containing every report section heading or placeholder. Templates belong to the requesting user.\n\nRequired role permission: templates:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'templates', data=data, files=files, request_model=TemplatesUploadRequest, media='multipart/form-data', response_model=TemplatesUploadResponse)

    async def delete(self, template_id: str) -> None:
        'Delete your Word template. DELETE /api/v1/templates/{template_id}. \n\nRequired role permission: templates:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'templates/{template_id}'.replace('{template_id}', path_value(template_id, nested=False)))

    async def download(self, template_id: str, *, destination: str | Path, overwrite: bool = False) -> Path:
        'Download your Word template. GET /api/v1/templates/{template_id}. \n\nRequired role permission: templates:manage.'
        return await self._transport.request('GET', 'templates/{template_id}'.replace('{template_id}', path_value(template_id, nested=False)), destination=destination, overwrite=overwrite)

    async def select(self, *, data: TemplatesSelectRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> TemplatesSelectResponse:
        'Select your Word template. PUT /api/v1/templates/selected. \n\nRequired role permission: templates:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PUT', 'templates/selected', data=data, files=files, request_model=TemplatesSelectRequest, media='application/json', response_model=TemplatesSelectResponse)

class AsyncToolsResource(AsyncResource):
    """Authorized tools operations. Server-side RBAC remains authoritative."""
    async def snort_open(self, cid: int, *, params: ToolsSnortOpenParams | Mapping[str, Any] | None = None) -> ToolsSnortOpenResponse:
        'Snort open. GET /api/v1/cases/{cid}/snort/file. \n\nRequired role permission: cases:assets.'
        return await self._transport.request('GET', 'cases/{cid}/snort/file'.replace('{cid}', path_value(cid, nested=False)), params=params, response_model=ToolsSnortOpenResponse)

    async def snort_save(self, cid: int, *, data: ToolsSnortSaveRequest | Mapping[str, Any] | None = None, params: ToolsSnortSaveParams | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsSnortSaveResponse:
        'Snort save. POST /api/v1/cases/{cid}/snort/file. \n\nRequired role permission: cases:assets.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/snort/file'.replace('{cid}', path_value(cid, nested=False)), data=data, files=files, request_model=ToolsSnortSaveRequest, media='multipart/form-data', params=params, response_model=ToolsSnortSaveResponse)

    async def snort_inventory(self, cid: int, *, params: ToolsSnortInventoryParams | Mapping[str, Any] | None = None) -> ToolsSnortInventoryResponse:
        'Snort inventory. GET /api/v1/cases/{cid}/snort/files. \n\nRequired role permission: cases:assets.'
        return await self._transport.request('GET', 'cases/{cid}/snort/files'.replace('{cid}', path_value(cid, nested=False)), params=params, response_model=ToolsSnortInventoryResponse)

    async def snort_normalize(self, cid: int, *, data: ToolsSnortNormalizeRequest | Mapping[str, Any] | None = None, params: ToolsSnortNormalizeParams | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsSnortNormalizeResponse:
        'Snort normalize. POST /api/v1/cases/{cid}/snort/normalize. \n\nRequired role permission: cases:assets.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/snort/normalize'.replace('{cid}', path_value(cid, nested=False)), data=data, files=files, request_model=ToolsSnortNormalizeRequest, media='multipart/form-data', params=params, response_model=ToolsSnortNormalizeResponse)

    async def yara_open(self, cid: int, *, params: ToolsYaraOpenParams | Mapping[str, Any] | None = None) -> ToolsYaraOpenResponse:
        'Yara open. GET /api/v1/cases/{cid}/yara/file. \n\nRequired role permission: cases:assets.'
        return await self._transport.request('GET', 'cases/{cid}/yara/file'.replace('{cid}', path_value(cid, nested=False)), params=params, response_model=ToolsYaraOpenResponse)

    async def yara_save(self, cid: int, *, data: ToolsYaraSaveRequest | Mapping[str, Any] | None = None, params: ToolsYaraSaveParams | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsYaraSaveResponse:
        'Yara save. POST /api/v1/cases/{cid}/yara/file. \n\nRequired role permission: cases:assets.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'cases/{cid}/yara/file'.replace('{cid}', path_value(cid, nested=False)), data=data, files=files, request_model=ToolsYaraSaveRequest, media='multipart/form-data', params=params, response_model=ToolsYaraSaveResponse)

    async def yara_files(self, cid: int, *, params: ToolsYaraFilesParams | Mapping[str, Any] | None = None) -> ToolsYaraFilesResponse:
        'Yara files. GET /api/v1/cases/{cid}/yara/files. \n\nRequired role permission: cases:assets.'
        return await self._transport.request('GET', 'cases/{cid}/yara/files'.replace('{cid}', path_value(cid, nested=False)), params=params, response_model=ToolsYaraFilesResponse)

    async def list(self) -> ToolsListResponse:
        'List authorized installed analyst tools. GET /api/v1/tools. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'tools', response_model=ToolsListResponse)

    async def snort_download(self, *, data: ToolsSnortDownloadRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Snort download. POST /api/v1/tools/snort/download. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/snort/download', data=data, files=files, request_model=ToolsSnortDownloadRequest, media='multipart/form-data', destination=destination, overwrite=overwrite)

    async def snort_draft(self, *, data: ToolsSnortDraftRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsSnortDraftResponse:
        'Snort draft. POST /api/v1/tools/snort/draft. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/snort/draft', data=data, files=files, request_model=ToolsSnortDraftRequest, media='multipart/form-data', response_model=ToolsSnortDraftResponse)

    async def snort_jobs(self, *, data: ToolsSnortJobsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsSnortJobsResponse:
        'Snort jobs. POST /api/v1/tools/snort/jobs. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/snort/jobs', data=data, files=files, request_model=ToolsSnortJobsRequest, media='multipart/form-data', response_model=ToolsSnortJobsResponse)

    async def snort_job(self, job: str) -> ToolsSnortJobResponse:
        'Snort job. GET /api/v1/tools/snort/jobs/{job}. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'tools/snort/jobs/{job}'.replace('{job}', path_value(job, nested=False)), response_model=ToolsSnortJobResponse)

    async def snort_cancel(self, job: str, *, data: ToolsSnortCancelRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsSnortCancelResponse:
        'Snort cancel. POST /api/v1/tools/snort/jobs/{job}/cancel. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/snort/jobs/{job}/cancel'.replace('{job}', path_value(job, nested=False)), data=data, files=files, request_model=ToolsSnortCancelRequest, media='multipart/form-data', response_model=ToolsSnortCancelResponse)

    async def snort_state(self) -> ToolsSnortStateResponse:
        'Snort state. GET /api/v1/tools/snort/state. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'tools/snort/state', response_model=ToolsSnortStateResponse)

    async def process_text(self, *, data: ToolsProcessTextRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsProcessTextResponse:
        'Tools text process. POST /api/v1/tools/text/process. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/text/process', data=data, files=files, request_model=ToolsProcessTextRequest, media='application/json', response_model=ToolsProcessTextResponse)

    async def yara_download(self, *, data: ToolsYaraDownloadRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None, destination: str | Path, overwrite: bool = False) -> Path:
        'Yara download. POST /api/v1/tools/yara/download. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/yara/download', data=data, files=files, request_model=ToolsYaraDownloadRequest, media='multipart/form-data', destination=destination, overwrite=overwrite)

    async def yara_draft(self, *, data: ToolsYaraDraftRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsYaraDraftResponse:
        'Yara draft. POST /api/v1/tools/yara/draft. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/yara/draft', data=data, files=files, request_model=ToolsYaraDraftRequest, media='multipart/form-data', response_model=ToolsYaraDraftResponse)

    async def yara_jobs(self, *, data: ToolsYaraJobsRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsYaraJobsResponse:
        'Yara jobs. POST /api/v1/tools/yara/jobs. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/yara/jobs', data=data, files=files, request_model=ToolsYaraJobsRequest, media='multipart/form-data', response_model=ToolsYaraJobsResponse)

    async def yara_job(self, job: str) -> ToolsYaraJobResponse:
        'Yara job. GET /api/v1/tools/yara/jobs/{job}. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'tools/yara/jobs/{job}'.replace('{job}', path_value(job, nested=False)), response_model=ToolsYaraJobResponse)

    async def yara_cancel(self, job: str, *, data: ToolsYaraCancelRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> ToolsYaraCancelResponse:
        'Yara cancel. POST /api/v1/tools/yara/jobs/{job}/cancel. \n\nRequired role permission: any authenticated API user.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'tools/yara/jobs/{job}/cancel'.replace('{job}', path_value(job, nested=False)), data=data, files=files, request_model=ToolsYaraCancelRequest, media='multipart/form-data', response_model=ToolsYaraCancelResponse)

    async def yara_state(self) -> ToolsYaraStateResponse:
        'Yara state. GET /api/v1/tools/yara/state. \n\nRequired role permission: any authenticated API user.'
        return await self._transport.request('GET', 'tools/yara/state', response_model=ToolsYaraStateResponse)

class AsyncUsersResource(AsyncResource):
    """Authorized users operations. Server-side RBAC remains authoritative."""
    async def list(self, *, params: UsersListParams | Mapping[str, Any] | None = None) -> UsersListResponse:
        'List accounts. GET /api/v1/users. \n\nRequired role permission: users:manage.'
        return await self._transport.request('GET', 'users', params=params, response_model=UsersListResponse)

    async def create(self, *, data: UsersCreateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> UsersCreateResponse:
        'Create an account. POST /api/v1/users. The role must exist. Without roles:manage, only roles whose permissions are a subset of the caller’s role may be assigned.\n\nRequired role permission: users:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('POST', 'users', data=data, files=files, request_model=UsersCreateRequest, media='application/json', response_model=UsersCreateResponse)

    async def delete(self, user_id: int) -> None:
        'Delete an account. DELETE /api/v1/users/{user_id}. Cannot delete yourself or the last active Administrator. Case ownership/creator references are cleared.\n\nRequired role permission: users:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('DELETE', 'users/{user_id}'.replace('{user_id}', path_value(user_id, nested=False)))

    async def get(self, user_id: int) -> UsersGetResponse:
        'Read account metadata. GET /api/v1/users/{user_id}. \n\nRequired role permission: users:manage.'
        return await self._transport.request('GET', 'users/{user_id}'.replace('{user_id}', path_value(user_id, nested=False)), response_model=UsersGetResponse)

    async def update(self, user_id: int, *, data: UsersUpdateRequest | Mapping[str, Any] | None = None, files: Mapping[str, Any] | list[tuple[str, Any]] | None = None) -> UsersUpdateResponse:
        'Change account role or active status. PATCH /api/v1/users/{user_id}. Cannot disable/demote the last active Administrator. Role assignment uses the same permission constraints as account creation. Changes invalidate existing web sessions.\n\nRequired role permission: users:manage.\n\nExecute affects real application data. Nothing executes automatically.'
        return await self._transport.request('PATCH', 'users/{user_id}'.replace('{user_id}', path_value(user_id, nested=False)), data=data, files=files, request_model=UsersUpdateRequest, media='application/json', response_model=UsersUpdateResponse)

    async def iter_all(self, *, params=None):
        """Yield authorized records across offset pages without preloading the dataset."""
        async for item in self._iterate(self.list, 'users', (), params):
            yield item
