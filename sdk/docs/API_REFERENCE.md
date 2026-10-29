# SDK API reference

Generated from source docstrings and signatures. Both clients expose the same resource methods; async calls must be awaited.

## client.py

### MWSClient

Pooled synchronous REST client; close it or use a with statement.

Args:
    base_url: Deployment URL, optionally including a reverse-proxy subpath.
        Defaults to MWS_BASE_URL. A trailing /api/v1 is also accepted.
    api_key: Personal bearer token, returned once by MWS token creation.
        Defaults to MWS_API_KEY. Existing current-user RBAC is authoritative.
    **configuration: connect_timeout, read_timeout, verify, retries,
        max_retry_delay, max_connections, max_keepalive_connections,
        trust_env, and optional httpx transport for testing.

```python
def close(self)
```

Close the HTTP pool; safe to call repeatedly.

### AsyncMWSClient

Async counterpart with equivalent resources; use async with or await close().

```python
async def close(self)
```

Close the asynchronous HTTP pool.

## sync_resources.py

### ActorsResource

Authorized actors operations. Server-side RBAC remains authoritative.

```python
def list(self, *, params: ActorsListParams | Mapping[str, Any] | None=None) -> ActorsListResponse
```

Read Threat Actors. GET /api/v1/actors. 

Required role permission: tags:read.

```python
def create(self, *, data: ActorsCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsCreateResponse
```

Actors edit. POST /api/v1/actors. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, fid: str, *, params: ActorsGetParams | Mapping[str, Any] | None=None) -> ActorsGetResponse
```

Read Threat Actors. GET /api/v1/actors/{fid}. 

Required role permission: tags:read.

```python
def delete(self, fid: str, *, data: ActorsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteResponse
```

Actors delete. POST /api/v1/actors/{fid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def update(self, fid: str, *, data: ActorsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateResponse
```

Actors edit. POST /api/v1/actors/{fid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def add_osint(self, fid: str, *, data: ActorsAddOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsAddOsintResponse
```

Actors osint edit. POST /api/v1/actors/{fid}/osint. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete_osint(self, fid: str, eid: str, *, data: ActorsDeleteOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteOsintResponse
```

Actors osint delete. POST /api/v1/actors/{fid}/osint/{eid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def update_osint(self, fid: str, eid: str, *, data: ActorsUpdateOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateOsintResponse
```

Actors osint edit. POST /api/v1/actors/{fid}/osint/{eid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def upload_reports(self, fid: str, *, data: ActorsUploadReportsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUploadReportsResponse
```

Actors reports upload. POST /api/v1/actors/{fid}/reports. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete_report(self, fid: str, aid: str, *, data: ActorsDeleteReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteReportResponse
```

Actors reports delete. POST /api/v1/actors/{fid}/reports/{aid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Actors reports download. GET /api/v1/actors/{fid}/reports/{aid}/download. 

Required role permission: tags:read.

```python
def update_report(self, fid: str, aid: str, *, data: ActorsUpdateReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateReportResponse
```

Actors reports edit. POST /api/v1/actors/{fid}/reports/{aid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AssetsResource

Authorized assets operations. Server-side RBAC remains authoritative.

```python
def delete(self, case_id: int, *, data: AssetsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> None
```

Delete a package artifact. DELETE /api/v1/cases/{case_id}/assets. 

Required role permission: cases:assets.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def list(self, case_id: int, *, params: AssetsListParams | Mapping[str, Any] | None=None) -> AssetsListResponse
```

List package files. GET /api/v1/cases/{case_id}/assets. 

Required role permission: cases:read.

```python
def upload(self, case_id: int, *, data: AssetsUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> AssetsUploadResponse
```

Upload a package artifact. POST /api/v1/cases/{case_id}/assets. Maximum 100 MiB per file. Sanitized duplicate filenames are rejected. Samples are wrapped in password-protected AES ZIP files using the configured sample password.

Required role permission: cases:assets.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def download(self, case_id: int, relative_path: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a package artifact. GET /api/v1/cases/{case_id}/assets/{relative_path}. relative_path may include slashes, e.g. scripts/example.txt; it must remain within the case directory. Content-Type is inferred from the filename. Generated indicators.stix.json returns 409 if it does not match the current saved table.

Required role permission: cases:assets.

### AuditResource

Authorized audit operations. Server-side RBAC remains authoritative.

```python
def export_all(self, *, destination: str | Path, overwrite: bool=False) -> Path
```

Audit export all zip. GET /api/v1/audit/export-all.zip. 

Required role permission: users:manage.

```python
def export_csv(self, *, params: AuditExportCsvParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Audit export csv. GET /api/v1/audit/export.csv. 

Required role permission: users:manage.

### AuthenticationResource

Authorized authentication operations. Server-side RBAC remains authoritative.

```python
def me(self) -> AuthenticationMeResponse
```

Inspect the authenticated account and permissions. GET /api/v1/me. 

Required role permission: any authenticated API user.

```python
def list_tokens(self) -> AuthenticationListTokensResponse
```

List your token metadata (no secrets). GET /api/v1/tokens. 

Required role permission: tokens:manage.

```python
def create_token(self, *, data: AuthenticationCreateTokenRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> AuthenticationCreateTokenResponse
```

Create a bearer token. POST /api/v1/tokens. 

Required role permission: tokens:manage.

Execute affects real application data. Nothing executes automatically.

```python
def revoke_token(self, token_id: int) -> None
```

Revoke a token. DELETE /api/v1/tokens/{token_id}. Own tokens only, unless users:manage is also held. Repeated revocation returns 204.

Required role permission: tokens:manage.

Execute affects real application data. Nothing executes automatically.

### BackupsResource

Authorized backups operations. Server-side RBAC remains authoritative.

```python
def create_job(self, *, data: BackupsCreateJobRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsCreateJobResponse
```

Backup jobs create. POST /api/v1/backup-jobs. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def job(self, jid: str) -> BackupsJobResponse
```

Backup jobs status. GET /api/v1/backup-jobs/{jid}. 

Required role permission: backups:manage.

```python
def apply(self, jid: str, *, data: BackupsApplyRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsApplyResponse
```

Backup jobs apply. POST /api/v1/backup-jobs/{jid}/apply. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def download(self, jid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Backup jobs download. GET /api/v1/backup-jobs/{jid}/download. 

Required role permission: backups:manage.

```python
def preview(self, jid: str, *, data: BackupsPreviewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsPreviewResponse
```

Backup jobs preview. POST /api/v1/backup-jobs/{jid}/preview. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def sync_apply(self, operation: str, *, data: BackupsSyncApplyRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> SyncResult
```

Apply validated per-case synchronization decisions. POST /api/v1/backups/apply/{operation}. Object keyed by the zero-based review case index (string). Omitted decisions apply safe automatic new/update/unchanged/older actions; unresolved/invalid cases are skipped. Conflicts need explicit keep or replace. Legacy review also supports new or link (target is a local numeric case ID). Revision validation, ownership checks and recovery snapshots remain enforced; inspect each actual outcome for failure/rollback. Only the staging account may apply; preview expires after one hour.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def export_cases(self, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a full case backup ZIP. POST /api/v1/backups/export. Includes nested case RAW ZIPs and metadata; excludes malware samples.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def import_cases(self, *, data: BackupsImportCasesRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsImportCasesResponse
```

Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def import_raw(self, *, data: BackupsImportRawRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsImportRawResponse
```

Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import-raw. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
def sync_review(self, operation: str) -> SyncResult
```

Review a staged synchronization or its outcomes. GET /api/v1/backups/review/{operation}. Only the account that staged the archive may access it. Expired preview returns 410.

Required role permission: backups:manage.

```python
def case(self, case_id: int, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a case RAW backup ZIP. POST /api/v1/cases/{case_id}/backup. Includes case metadata and email-safe Python filenames. Malware samples excluded.

Required role permission: cases:export.

Execute affects real application data. Nothing executes automatically.

### CasesResource

Authorized cases operations. Server-side RBAC remains authoritative.

```python
def list(self, *, params: CasesListParams | Mapping[str, Any] | None=None) -> CasesListResponse
```

List cases newest first. GET /api/v1/cases. 

Required role permission: cases:read.

```python
def create(self, *, data: CasesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesCreateResponse
```

Create a case. POST /api/v1/cases. A date prefix is added to the title if absent; the resulting name must remain ≤200 characters. External system and number must be supplied together. Owner must be active.

Required role permission: cases:create.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, case_id: int) -> None
```

Permanently delete a case and its files. DELETE /api/v1/cases/{case_id}. Real destructive operation. Active report generation blocks deletion; there is no additional API confirmation field.

Required role permission: cases:delete.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, case_id: int) -> CasesGetResponse
```

Read case details and workflow history. GET /api/v1/cases/{case_id}. 

Required role permission: cases:read.

```python
def update(self, case_id: int, *, data: CasesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesUpdateResponse
```

Update case metadata or ownership. PATCH /api/v1/cases/{case_id}. External system/number must be paired. Stage changes use the dedicated workflow endpoint.

Required role permission: cases:update.

Execute affects real application data. Nothing executes automatically.

```python
def reopen(self, case_id: int) -> CasesReopenResponse
```

Reopen a completed case for analysis. POST /api/v1/cases/{case_id}/reopen. Completed cases only; active owner required when ownership is mandatory.

Required role permission: cases:workflow.

Execute affects real application data. Nothing executes automatically.

```python
def advance(self, case_id: int, *, data: CasesAdvanceRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesAdvanceResponse
```

Advance one workflow stage. POST /api/v1/cases/{case_id}/stage. expected must equal the current stage. Active owner required to start; skipped/deferred outcomes require a reason. Completion checks readiness and review blockers. Stage 0 always records Started.

Required role permission: cases:workflow.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### CoverageResource

Authorized coverage operations. Server-side RBAC remains authoritative.

```python
def get(self, *, params: CoverageGetParams | Mapping[str, Any] | None=None) -> CoverageGetResponse
```

Explorer coverage. GET /api/v1/coverage. 

Required role permission: any authenticated API user.

### ExplorerResource

Authorized explorer operations. Server-side RBAC remains authoritative.

```python
def contents(self, case_id: int, *, params: ExplorerContentsParams | Mapping[str, Any] | None=None) -> ExplorerContentsResponse
```

Explorer contents. GET /api/v1/explorer/cases/{case_id}/contents. 

Required role permission: cases:read.

```python
def category(self, case_id: int, category: str, *, params: ExplorerCategoryParams | Mapping[str, Any] | None=None) -> ExplorerCategoryResponse
```

Explorer category. GET /api/v1/explorer/cases/{case_id}/contents/{category}. 

Required role permission: cases:read.

```python
def download(self, case_id: int, *, params: ExplorerDownloadParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Explorer file. GET /api/v1/explorer/cases/{case_id}/file. 

Required role permission: cases:read.

```python
def connection_objects(self, *, params: ExplorerConnectionObjectsParams | Mapping[str, Any] | None=None) -> ExplorerConnectionObjectsResponse
```

Explorer connection objects. GET /api/v1/explorer/connection-objects. 

Required role permission: any authenticated API user.

```python
def connections(self, *, params: ExplorerConnectionsParams | Mapping[str, Any] | None=None) -> ExplorerConnectionsResponse
```

Explorer connections. GET /api/v1/explorer/connections. 

Required role permission: any authenticated API user.

```python
def evidence(self, *, params: ExplorerEvidenceParams | Mapping[str, Any] | None=None) -> ExplorerEvidenceResponse
```

Explorer evidence. GET /api/v1/explorer/evidence. 

Required role permission: any authenticated API user.

```python
def graph(self, *, params: ExplorerGraphParams | Mapping[str, Any] | None=None) -> ExplorerGraphResponse
```

Explorer data. GET /api/v1/explorer/graph. 

Required role permission: any authenticated API user.

```python
def shared_indicators(self, *, params: ExplorerSharedIndicatorsParams | Mapping[str, Any] | None=None) -> ExplorerSharedIndicatorsResponse
```

Explorer shared indicators. GET /api/v1/explorer/shared-indicators. 

Required role permission: any authenticated API user.

```python
def list_views(self) -> ExplorerListViewsResponse
```

Explorer views. GET /api/v1/explorer/views. 

Required role permission: any authenticated API user.

```python
def create_view(self, *, data: ExplorerCreateViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerCreateViewResponse
```

Explorer view create. POST /api/v1/explorer/views. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def get_view(self, vid: str) -> ExplorerGetViewResponse
```

Explorer view. GET /api/v1/explorer/views/{vid}. 

Required role permission: any authenticated API user.

```python
def delete_view(self, vid: str, *, data: ExplorerDeleteViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerDeleteViewResponse
```

Explorer view delete. POST /api/v1/explorer/views/{vid}/delete. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def update_view(self, vid: str, *, data: ExplorerUpdateViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerUpdateViewResponse
```

Explorer view update. POST /api/v1/explorer/views/{vid}/update. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

### FamiliesResource

Authorized families operations. Server-side RBAC remains authoritative.

```python
def list(self, *, params: FamiliesListParams | Mapping[str, Any] | None=None) -> FamiliesListResponse
```

Read Malware Families. GET /api/v1/families. 

Required role permission: tags:read.

```python
def create(self, *, data: FamiliesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesCreateResponse
```

Families edit. POST /api/v1/families. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, fid: str, *, params: FamiliesGetParams | Mapping[str, Any] | None=None) -> FamiliesGetResponse
```

Read Malware Families. GET /api/v1/families/{fid}. 

Required role permission: tags:read.

```python
def delete(self, fid: str, *, data: FamiliesDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteResponse
```

Families delete. POST /api/v1/families/{fid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def update(self, fid: str, *, data: FamiliesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateResponse
```

Families edit. POST /api/v1/families/{fid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def add_osint(self, fid: str, *, data: FamiliesAddOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesAddOsintResponse
```

Families osint edit. POST /api/v1/families/{fid}/osint. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete_osint(self, fid: str, eid: str, *, data: FamiliesDeleteOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteOsintResponse
```

Families osint delete. POST /api/v1/families/{fid}/osint/{eid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def update_osint(self, fid: str, eid: str, *, data: FamiliesUpdateOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateOsintResponse
```

Families osint edit. POST /api/v1/families/{fid}/osint/{eid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def upload_reports(self, fid: str, *, data: FamiliesUploadReportsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUploadReportsResponse
```

Families reports upload. POST /api/v1/families/{fid}/reports. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete_report(self, fid: str, aid: str, *, data: FamiliesDeleteReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteReportResponse
```

Families reports delete. POST /api/v1/families/{fid}/reports/{aid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Families reports download. GET /api/v1/families/{fid}/reports/{aid}/download. 

Required role permission: tags:read.

```python
def update_report(self, fid: str, aid: str, *, data: FamiliesUpdateReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateReportResponse
```

Families reports edit. POST /api/v1/families/{fid}/reports/{aid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### IndicatorsResource

Authorized indicators operations. Server-side RBAC remains authoritative.

```python
def get(self, case_id: int) -> Indicators
```

Read indicators and revision. GET /api/v1/cases/{case_id}/indicators. 

Required role permission: indicators:read.

```python
def update(self, case_id: int, *, data: IndicatorsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Indicators
```

Replace indicators with revision validation. PUT /api/v1/cases/{case_id}/indicators. Send all sections to preserve grouping, or rows when exactly one section exists. Each row has three text cells (≤4,000 characters), 1–100 sections with unique IDs (1–64 alphanumeric/underscore/hyphen), a nonempty title ≤200 characters and description ≤4,000 characters. The default section must remain; ≤10,000 rows total. revision must equal the current revision. The bundled official MISP attribute catalog is selectable/storable; export capability/help is supplied per type. Known compatibility aliases normalize on save; exact MISP canonical names take precedence. text/comment/other retain literal Unicode/whitespace and export as non-detection x-misp-attribute objects; Valid scalar attributes without native mappings use the official MISP-compatible contextual representation, with informational stix.notices. Missing attachment/sample bytes and invalid values retain saved drafts with explicit stix.issues. Legacy android-package aliases normalize to mobile-application-id while retaining identity and original_type provenance. Unknown/ambiguous types and invalid values remain saved as drafts with stix.issues; CSV is refreshed and stale STIX removed. Fully exportable tables generate iocs/indicators.stix.json with refanged native patterns and faithful contextual objects; any unsupported row withholds the entire STIX output. Preserve optional row_meta (including explicit boolean to_ids detection intent) and stix_meta when editing to retain IDs/timestamps/intent; do not generate them yourself. Unchanged saves do not advance revision. The authenticated web Indicators workspace provides CSV/STIX import previews and a read-only download; equivalent versioned preview/import/STIX download endpoints are also available to SDK clients.

Required role permission: indicators:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def import_rows(self, cid: int, *, data: IndicatorsImportRowsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> IndicatorsImportRowsResponse
```

Indicators import. POST /api/v1/cases/{cid}/indicators/import. 

Required role permission: indicators:write.

Execute affects real application data. Nothing executes automatically.

```python
def preview_import(self, cid: int, *, data: IndicatorsPreviewImportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> IndicatorsPreviewImportResponse
```

Indicators import preview. POST /api/v1/cases/{cid}/indicators/import/preview. 

Required role permission: indicators:write.

Execute affects real application data. Nothing executes automatically.

```python
def download_stix(self, cid: int, *, destination: str | Path, overwrite: bool=False) -> Path
```

Indicators stix download. GET /api/v1/cases/{cid}/indicators/stix. 

Required role permission: indicators:read.

### MetricsResource

Authorized metrics operations. Server-side RBAC remains authoritative.

```python
def get(self) -> MetricsGetResponse
```

Read all-time metrics. GET /api/v1/metrics. Legacy all-time API metrics; independent of dashboard period filters.

Required role permission: metrics:read.

### NotesResource

Authorized notes operations. Server-side RBAC remains authoritative.

```python
def delete_draft(self, case_id: int) -> None
```

Delete your case note draft. DELETE /api/v1/cases/{case_id}/draft. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def get_draft(self, case_id: int) -> NotesGetDraftResponse
```

Read your case note draft. GET /api/v1/cases/{case_id}/draft. 

Required role permission: cases:read.

```python
def update_draft(self, case_id: int, *, data: NotesUpdateDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesUpdateDraftResponse
```

Replace your case note draft. PUT /api/v1/cases/{case_id}/draft. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def list(self, case_id: int, *, params: NotesListParams | Mapping[str, Any] | None=None) -> NotesListResponse
```

List case notes. GET /api/v1/cases/{case_id}/notes. 

Required role permission: cases:read.

```python
def create(self, case_id: int, *, data: NotesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesCreateResponse
```

Create a note. POST /api/v1/cases/{case_id}/notes. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, case_id: int, note_id: int) -> None
```

Delete a note. DELETE /api/v1/cases/{case_id}/notes/{note_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, case_id: int, note_id: int) -> NotesGetResponse
```

Read a case note. GET /api/v1/cases/{case_id}/notes/{note_id}. 

Required role permission: cases:read.

```python
def update(self, case_id: int, note_id: int, *, data: NotesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesUpdateResponse
```

Update a note. PATCH /api/v1/cases/{case_id}/notes/{note_id}. The resulting body must contain non-whitespace text.

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, case_id, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### PackagesResource

Authorized packages operations. Server-side RBAC remains authoritative.

```python
def export(self, case_id: int, *, data: PackagesExportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Download a Standard or RAW MIP ZIP. POST /api/v1/cases/{case_id}/archive. Packaging & Delivery or Completed only; active owner required when mandatory. Standard requires a completed Word report. Outstanding review blockers require acknowledge=true. Including samples additionally requires samples:export. Malware sample archives are dangerous; handle only in an isolated analysis environment.

Required role permission: cases:export.

Execute affects real application data. Nothing executes automatically.

```python
def readiness(self, case_id: int) -> PackagesReadinessResponse
```

Read package readiness. GET /api/v1/cases/{case_id}/readiness. 

Required role permission: cases:read.

```python
def set_readiness(self, case_id: int, *, data: PackagesSetReadinessRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> PackagesSetReadinessResponse
```

Set one category readiness. PUT /api/v1/cases/{case_id}/readiness. Not applicable requires a reason and is forbidden for reports. Populated requires an existing file.

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### PluginsResource

Authorized plugins operations. Server-side RBAC remains authoritative.

```python
def capabilities(self) -> PluginsCapabilitiesResponse
```

Inspect existing plugin integration capabilities. GET /api/v1/plugins. 

Required role permission: any authenticated API user.

### ReferencesResource

Authorized references operations. Server-side RBAC remains authoritative.

```python
def get(self, case_id: int) -> References
```

Read references and revision. GET /api/v1/cases/{case_id}/references. 

Required role permission: references:read.

```python
def update(self, case_id: int, *, data: ReferencesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> References
```

Replace references with revision validation. PUT /api/v1/cases/{case_id}/references. Fixed columns Link, Description. revision must equal the current revision.

Required role permission: references:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### ReportsResource

Authorized reports operations. Server-side RBAC remains authoritative.

```python
def get(self, case_id: int) -> ReportsGetResponse
```

Read report sections and mappings. GET /api/v1/cases/{case_id}/report. 

Required role permission: reports:read.

```python
def update(self, case_id: int, *, data: ReportsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUpdateResponse
```

Save manual report sections. PUT /api/v1/cases/{case_id}/report. Only manual sections are written; generated sections are accepted but not persisted. Omitted manual sections retain their current values.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def download(self, case_id: int, *, params: ReportsDownloadParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Download the current report. GET /api/v1/cases/{case_id}/report/download. 404 if the requested output has not been generated.

Required role permission: reports:read.

```python
def upload(self, case_id: int, *, data: ReportsUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUploadResponse
```

Upload an edited DOCX report. POST /api/v1/cases/{case_id}/report/final. Valid DOCX ≤20 MiB required. backup=1 saves the previous report. generate_pdf=0 skips PDF conversion; otherwise LibreOffice is required. Active report jobs block replacement.

Required role permission: reports:generate.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def generate(self, case_id: int, *, data: ReportsGenerateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsGenerateResponse
```

Start local Word report generation. POST /api/v1/cases/{case_id}/report/generate. Select an available template first. Generation saves supplied manual sections; omitted manual fields become empty. Read and submit existing sections to retain them. Existing reports require an explicit previous=backup or overwrite choice (409 needs_choice otherwise). Poll report/job; PDF generation requires LibreOffice. Accepts JSON or form fields.

Required role permission: reports:generate.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def list_images(self, case_id: int) -> ReportsListImagesResponse
```

List report image metadata. GET /api/v1/cases/{case_id}/report/images. 

Required role permission: reports:read.

```python
def upload_image(self, case_id: int, *, data: ReportsUploadImageRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Image
```

Upload a report or task image. POST /api/v1/cases/{case_id}/report/images. Readable image ≤10 MiB and ≤20 megapixels; normalized to PNG. Active report jobs block changes.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def delete_image(self, case_id: int, name: str) -> None
```

Delete a report image. DELETE /api/v1/cases/{case_id}/report/images/{name}. 

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def download_image(self, case_id: int, name: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a report image. GET /api/v1/cases/{case_id}/report/images/{name}. 

Required role permission: reports:read.

```python
def job(self, case_id: int) -> ReportsJobResponse
```

Read the latest report generation job. GET /api/v1/cases/{case_id}/report/job. 

Required role permission: reports:read.

```python
def get_mappings(self, case_id: int) -> ReportsGetMappingsResponse
```

Read MITRE mappings. GET /api/v1/cases/{case_id}/report/mappings. 

Required role permission: reports:read.

```python
def update_mappings(self, case_id: int, *, data: ReportsUpdateMappingsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUpdateMappingsResponse
```

Save MITRE mapping Markdown. PUT /api/v1/cases/{case_id}/report/mappings. Blank text removes that mapping. Active report generation blocks saving.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### RolesResource

Authorized roles operations. Server-side RBAC remains authoritative.

```python
def permissions(self) -> RolesPermissionsResponse
```

List known permission names. GET /api/v1/permissions. 

Required role permission: roles:manage.

```python
def list(self) -> RolesListResponse
```

List roles and permissions. GET /api/v1/roles. 

Required role permission: roles:manage.

```python
def create(self, *, data: RolesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Role
```

Create a custom role. POST /api/v1/roles. Only known, unique permissions already held by the caller may be granted.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, name: str) -> None
```

Delete an unused custom role. DELETE /api/v1/roles/{name}. Built-in roles and roles assigned to users cannot be deleted.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, name: str) -> Role
```

Read role metadata. GET /api/v1/roles/{name}. 

Required role permission: roles:manage.

```python
def update(self, name: str, *, data: RolesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Role
```

Update a custom role. PATCH /api/v1/roles/{name}. Built-in roles are immutable. Cannot grant permissions the caller does not hold.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

### SearchResource

Authorized search operations. Server-side RBAC remains authoritative.

```python
def query(self, *, params: SearchQueryParams | Mapping[str, Any] | None=None) -> SearchQueryResponse
```

Mip search results. GET /api/v1/search. 

Required role permission: cases:read.

### SettingsResource

Authorized settings operations. Server-side RBAC remains authoritative.

```python
def get(self) -> SettingsGetResponse
```

Inspect configured settings (no secrets). GET /api/v1/settings. 

Required role permission: settings:read.

```python
def update(self, *, data: SettingsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> SettingsUpdateResponse
```

Set the sample archive password. PATCH /api/v1/settings. NUL characters are rejected. Changes affect future sample archives; the password is never returned.

Required role permission: settings:write.

Execute affects real application data. Nothing executes automatically.

### TagsResource

Authorized tags operations. Server-side RBAC remains authoritative.

```python
def for_case(self, cid: int) -> TagsForCaseResponse
```

Case tags list. GET /api/v1/cases/{cid}/tags. 

Required role permission: tags:read.

```python
def assign(self, cid: int, tid: int) -> TagsAssignResponse
```

Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/assign. 

Required role permission: tags:assign.

Execute affects real application data. Nothing executes automatically.

```python
def remove(self, cid: int, tid: int) -> TagsRemoveResponse
```

Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/remove. 

Required role permission: tags:assign.

Execute affects real application data. Nothing executes automatically.

```python
def list(self, *, params: TagsListParams | Mapping[str, Any] | None=None) -> TagsListResponse
```

Tags search. GET /api/v1/tags. 

Required role permission: tags:read.

```python
def create(self, *, data: TagsCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsCreateResponse
```

Tags create. POST /api/v1/tags. 

Required role permission: tags:create.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, tid: int) -> TagsGetResponse
```

Read a tag. GET /api/v1/tags/{tid}. 

Required role permission: tags:read.

```python
def delete(self, tid: int, *, data: TagsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsDeleteResponse
```

Tag manage. POST /api/v1/tags/{tid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def merge(self, tid: int, *, data: TagsMergeRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsMergeResponse
```

Tag manage. POST /api/v1/tags/{tid}/merge. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
def rename(self, tid: int, *, data: TagsRenameRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsRenameResponse
```

Tag manage. POST /api/v1/tags/{tid}/rename. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

### TasksResource

Authorized tasks operations. Server-side RBAC remains authoritative.

```python
def list(self, case_id: int, *, params: TasksListParams | Mapping[str, Any] | None=None) -> TasksListResponse
```

List case tasks. GET /api/v1/cases/{case_id}/tasks. 

Required role permission: cases:read.

```python
def create(self, case_id: int, *, data: TasksCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TasksCreateResponse
```

Create a task. POST /api/v1/cases/{case_id}/tasks. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, case_id: int, task_id: int) -> None
```

Delete a task. DELETE /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, case_id: int, task_id: int) -> TasksGetResponse
```

Read a case task. GET /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:read.

```python
def update(self, case_id: int, task_id: int, *, data: TasksUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TasksUpdateResponse
```

Update a task. PATCH /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, case_id, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### TemplatesResource

Authorized templates operations. Server-side RBAC remains authoritative.

```python
def list(self) -> TemplatesListResponse
```

List your Word templates. GET /api/v1/templates. 

Required role permission: templates:manage.

```python
def upload(self, *, data: TemplatesUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TemplatesUploadResponse
```

Upload and select a Word template. POST /api/v1/templates. DOCX ≤10 MiB, containing every report section heading or placeholder. Templates belong to the requesting user.

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, template_id: str) -> None
```

Delete your Word template. DELETE /api/v1/templates/{template_id}. 

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

```python
def download(self, template_id: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download your Word template. GET /api/v1/templates/{template_id}. 

Required role permission: templates:manage.

```python
def select(self, *, data: TemplatesSelectRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TemplatesSelectResponse
```

Select your Word template. PUT /api/v1/templates/selected. 

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

### ToolsResource

Authorized tools operations. Server-side RBAC remains authoritative.

```python
def snort_open(self, cid: int, *, params: ToolsSnortOpenParams | Mapping[str, Any] | None=None) -> ToolsSnortOpenResponse
```

Snort open. GET /api/v1/cases/{cid}/snort/file. 

Required role permission: cases:assets.

```python
def snort_save(self, cid: int, *, data: ToolsSnortSaveRequest | Mapping[str, Any] | None=None, params: ToolsSnortSaveParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortSaveResponse
```

Snort save. POST /api/v1/cases/{cid}/snort/file. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
def snort_inventory(self, cid: int, *, params: ToolsSnortInventoryParams | Mapping[str, Any] | None=None) -> ToolsSnortInventoryResponse
```

Snort inventory. GET /api/v1/cases/{cid}/snort/files. 

Required role permission: cases:assets.

```python
def snort_normalize(self, cid: int, *, data: ToolsSnortNormalizeRequest | Mapping[str, Any] | None=None, params: ToolsSnortNormalizeParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortNormalizeResponse
```

Snort normalize. POST /api/v1/cases/{cid}/snort/normalize. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
def yara_open(self, cid: int, *, params: ToolsYaraOpenParams | Mapping[str, Any] | None=None) -> ToolsYaraOpenResponse
```

Yara open. GET /api/v1/cases/{cid}/yara/file. 

Required role permission: cases:assets.

```python
def yara_save(self, cid: int, *, data: ToolsYaraSaveRequest | Mapping[str, Any] | None=None, params: ToolsYaraSaveParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraSaveResponse
```

Yara save. POST /api/v1/cases/{cid}/yara/file. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
def yara_files(self, cid: int, *, params: ToolsYaraFilesParams | Mapping[str, Any] | None=None) -> ToolsYaraFilesResponse
```

Yara files. GET /api/v1/cases/{cid}/yara/files. 

Required role permission: cases:assets.

```python
def list(self) -> ToolsListResponse
```

List authorized installed analyst tools. GET /api/v1/tools. 

Required role permission: any authenticated API user.

```python
def snort_download(self, *, data: ToolsSnortDownloadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Snort download. POST /api/v1/tools/snort/download. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def snort_draft(self, *, data: ToolsSnortDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortDraftResponse
```

Snort draft. POST /api/v1/tools/snort/draft. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def snort_jobs(self, *, data: ToolsSnortJobsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortJobsResponse
```

Snort jobs. POST /api/v1/tools/snort/jobs. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def snort_job(self, job: str) -> ToolsSnortJobResponse
```

Snort job. GET /api/v1/tools/snort/jobs/{job}. 

Required role permission: any authenticated API user.

```python
def snort_cancel(self, job: str, *, data: ToolsSnortCancelRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortCancelResponse
```

Snort cancel. POST /api/v1/tools/snort/jobs/{job}/cancel. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def snort_state(self) -> ToolsSnortStateResponse
```

Snort state. GET /api/v1/tools/snort/state. 

Required role permission: any authenticated API user.

```python
def process_text(self, *, data: ToolsProcessTextRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsProcessTextResponse
```

Tools text process. POST /api/v1/tools/text/process. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def yara_download(self, *, data: ToolsYaraDownloadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Yara download. POST /api/v1/tools/yara/download. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def yara_draft(self, *, data: ToolsYaraDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraDraftResponse
```

Yara draft. POST /api/v1/tools/yara/draft. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def yara_jobs(self, *, data: ToolsYaraJobsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraJobsResponse
```

Yara jobs. POST /api/v1/tools/yara/jobs. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def yara_job(self, job: str) -> ToolsYaraJobResponse
```

Yara job. GET /api/v1/tools/yara/jobs/{job}. 

Required role permission: any authenticated API user.

```python
def yara_cancel(self, job: str, *, data: ToolsYaraCancelRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraCancelResponse
```

Yara cancel. POST /api/v1/tools/yara/jobs/{job}/cancel. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
def yara_state(self) -> ToolsYaraStateResponse
```

Yara state. GET /api/v1/tools/yara/state. 

Required role permission: any authenticated API user.

### UsersResource

Authorized users operations. Server-side RBAC remains authoritative.

```python
def list(self, *, params: UsersListParams | Mapping[str, Any] | None=None) -> UsersListResponse
```

List accounts. GET /api/v1/users. 

Required role permission: users:manage.

```python
def create(self, *, data: UsersCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> UsersCreateResponse
```

Create an account. POST /api/v1/users. The role must exist. Without roles:manage, only roles whose permissions are a subset of the caller’s role may be assigned.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
def delete(self, user_id: int) -> None
```

Delete an account. DELETE /api/v1/users/{user_id}. Cannot delete yourself or the last active Administrator. Case ownership/creator references are cleared.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
def get(self, user_id: int) -> UsersGetResponse
```

Read account metadata. GET /api/v1/users/{user_id}. 

Required role permission: users:manage.

```python
def update(self, user_id: int, *, data: UsersUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> UsersUpdateResponse
```

Change account role or active status. PATCH /api/v1/users/{user_id}. Cannot disable/demote the last active Administrator. Role assignment uses the same permission constraints as account creation. Changes invalidate existing web sessions.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

## async_resources.py

### AsyncActorsResource

Authorized actors operations. Server-side RBAC remains authoritative.

```python
async def list(self, *, params: ActorsListParams | Mapping[str, Any] | None=None) -> ActorsListResponse
```

Read Threat Actors. GET /api/v1/actors. 

Required role permission: tags:read.

```python
async def create(self, *, data: ActorsCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsCreateResponse
```

Actors edit. POST /api/v1/actors. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, fid: str, *, params: ActorsGetParams | Mapping[str, Any] | None=None) -> ActorsGetResponse
```

Read Threat Actors. GET /api/v1/actors/{fid}. 

Required role permission: tags:read.

```python
async def delete(self, fid: str, *, data: ActorsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteResponse
```

Actors delete. POST /api/v1/actors/{fid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def update(self, fid: str, *, data: ActorsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateResponse
```

Actors edit. POST /api/v1/actors/{fid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def add_osint(self, fid: str, *, data: ActorsAddOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsAddOsintResponse
```

Actors osint edit. POST /api/v1/actors/{fid}/osint. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete_osint(self, fid: str, eid: str, *, data: ActorsDeleteOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteOsintResponse
```

Actors osint delete. POST /api/v1/actors/{fid}/osint/{eid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def update_osint(self, fid: str, eid: str, *, data: ActorsUpdateOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateOsintResponse
```

Actors osint edit. POST /api/v1/actors/{fid}/osint/{eid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def upload_reports(self, fid: str, *, data: ActorsUploadReportsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUploadReportsResponse
```

Actors reports upload. POST /api/v1/actors/{fid}/reports. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete_report(self, fid: str, aid: str, *, data: ActorsDeleteReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsDeleteReportResponse
```

Actors reports delete. POST /api/v1/actors/{fid}/reports/{aid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Actors reports download. GET /api/v1/actors/{fid}/reports/{aid}/download. 

Required role permission: tags:read.

```python
async def update_report(self, fid: str, aid: str, *, data: ActorsUpdateReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ActorsUpdateReportResponse
```

Actors reports edit. POST /api/v1/actors/{fid}/reports/{aid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AsyncAssetsResource

Authorized assets operations. Server-side RBAC remains authoritative.

```python
async def delete(self, case_id: int, *, data: AssetsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> None
```

Delete a package artifact. DELETE /api/v1/cases/{case_id}/assets. 

Required role permission: cases:assets.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def list(self, case_id: int, *, params: AssetsListParams | Mapping[str, Any] | None=None) -> AssetsListResponse
```

List package files. GET /api/v1/cases/{case_id}/assets. 

Required role permission: cases:read.

```python
async def upload(self, case_id: int, *, data: AssetsUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> AssetsUploadResponse
```

Upload a package artifact. POST /api/v1/cases/{case_id}/assets. Maximum 100 MiB per file. Sanitized duplicate filenames are rejected. Samples are wrapped in password-protected AES ZIP files using the configured sample password.

Required role permission: cases:assets.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def download(self, case_id: int, relative_path: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a package artifact. GET /api/v1/cases/{case_id}/assets/{relative_path}. relative_path may include slashes, e.g. scripts/example.txt; it must remain within the case directory. Content-Type is inferred from the filename. Generated indicators.stix.json returns 409 if it does not match the current saved table.

Required role permission: cases:assets.

### AsyncAuditResource

Authorized audit operations. Server-side RBAC remains authoritative.

```python
async def export_all(self, *, destination: str | Path, overwrite: bool=False) -> Path
```

Audit export all zip. GET /api/v1/audit/export-all.zip. 

Required role permission: users:manage.

```python
async def export_csv(self, *, params: AuditExportCsvParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Audit export csv. GET /api/v1/audit/export.csv. 

Required role permission: users:manage.

### AsyncAuthenticationResource

Authorized authentication operations. Server-side RBAC remains authoritative.

```python
async def me(self) -> AuthenticationMeResponse
```

Inspect the authenticated account and permissions. GET /api/v1/me. 

Required role permission: any authenticated API user.

```python
async def list_tokens(self) -> AuthenticationListTokensResponse
```

List your token metadata (no secrets). GET /api/v1/tokens. 

Required role permission: tokens:manage.

```python
async def create_token(self, *, data: AuthenticationCreateTokenRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> AuthenticationCreateTokenResponse
```

Create a bearer token. POST /api/v1/tokens. 

Required role permission: tokens:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def revoke_token(self, token_id: int) -> None
```

Revoke a token. DELETE /api/v1/tokens/{token_id}. Own tokens only, unless users:manage is also held. Repeated revocation returns 204.

Required role permission: tokens:manage.

Execute affects real application data. Nothing executes automatically.

### AsyncBackupsResource

Authorized backups operations. Server-side RBAC remains authoritative.

```python
async def create_job(self, *, data: BackupsCreateJobRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsCreateJobResponse
```

Backup jobs create. POST /api/v1/backup-jobs. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def job(self, jid: str) -> BackupsJobResponse
```

Backup jobs status. GET /api/v1/backup-jobs/{jid}. 

Required role permission: backups:manage.

```python
async def apply(self, jid: str, *, data: BackupsApplyRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsApplyResponse
```

Backup jobs apply. POST /api/v1/backup-jobs/{jid}/apply. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def download(self, jid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Backup jobs download. GET /api/v1/backup-jobs/{jid}/download. 

Required role permission: backups:manage.

```python
async def preview(self, jid: str, *, data: BackupsPreviewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsPreviewResponse
```

Backup jobs preview. POST /api/v1/backup-jobs/{jid}/preview. 

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def sync_apply(self, operation: str, *, data: BackupsSyncApplyRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> SyncResult
```

Apply validated per-case synchronization decisions. POST /api/v1/backups/apply/{operation}. Object keyed by the zero-based review case index (string). Omitted decisions apply safe automatic new/update/unchanged/older actions; unresolved/invalid cases are skipped. Conflicts need explicit keep or replace. Legacy review also supports new or link (target is a local numeric case ID). Revision validation, ownership checks and recovery snapshots remain enforced; inspect each actual outcome for failure/rollback. Only the staging account may apply; preview expires after one hour.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def export_cases(self, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a full case backup ZIP. POST /api/v1/backups/export. Includes nested case RAW ZIPs and metadata; excludes malware samples.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def import_cases(self, *, data: BackupsImportCasesRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsImportCasesResponse
```

Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def import_raw(self, *, data: BackupsImportRawRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> BackupsImportRawResponse
```

Stage a backup or RAW ZIP for synchronization review. POST /api/v1/backups/import-raw. Validates archive paths, resource limits, checksums and case metadata. Does not immediately apply changes. Review with backups/review/{operation}, then explicitly apply. Review is bound to the importing account and expires after one hour. import and import-raw are aliases.

Required role permission: backups:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def sync_review(self, operation: str) -> SyncResult
```

Review a staged synchronization or its outcomes. GET /api/v1/backups/review/{operation}. Only the account that staged the archive may access it. Expired preview returns 410.

Required role permission: backups:manage.

```python
async def case(self, case_id: int, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a case RAW backup ZIP. POST /api/v1/cases/{case_id}/backup. Includes case metadata and email-safe Python filenames. Malware samples excluded.

Required role permission: cases:export.

Execute affects real application data. Nothing executes automatically.

### AsyncCasesResource

Authorized cases operations. Server-side RBAC remains authoritative.

```python
async def list(self, *, params: CasesListParams | Mapping[str, Any] | None=None) -> CasesListResponse
```

List cases newest first. GET /api/v1/cases. 

Required role permission: cases:read.

```python
async def create(self, *, data: CasesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesCreateResponse
```

Create a case. POST /api/v1/cases. A date prefix is added to the title if absent; the resulting name must remain ≤200 characters. External system and number must be supplied together. Owner must be active.

Required role permission: cases:create.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, case_id: int) -> None
```

Permanently delete a case and its files. DELETE /api/v1/cases/{case_id}. Real destructive operation. Active report generation blocks deletion; there is no additional API confirmation field.

Required role permission: cases:delete.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, case_id: int) -> CasesGetResponse
```

Read case details and workflow history. GET /api/v1/cases/{case_id}. 

Required role permission: cases:read.

```python
async def update(self, case_id: int, *, data: CasesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesUpdateResponse
```

Update case metadata or ownership. PATCH /api/v1/cases/{case_id}. External system/number must be paired. Stage changes use the dedicated workflow endpoint.

Required role permission: cases:update.

Execute affects real application data. Nothing executes automatically.

```python
async def reopen(self, case_id: int) -> CasesReopenResponse
```

Reopen a completed case for analysis. POST /api/v1/cases/{case_id}/reopen. Completed cases only; active owner required when ownership is mandatory.

Required role permission: cases:workflow.

Execute affects real application data. Nothing executes automatically.

```python
async def advance(self, case_id: int, *, data: CasesAdvanceRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> CasesAdvanceResponse
```

Advance one workflow stage. POST /api/v1/cases/{case_id}/stage. expected must equal the current stage. Active owner required to start; skipped/deferred outcomes require a reason. Completion checks readiness and review blockers. Stage 0 always records Started.

Required role permission: cases:workflow.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AsyncCoverageResource

Authorized coverage operations. Server-side RBAC remains authoritative.

```python
async def get(self, *, params: CoverageGetParams | Mapping[str, Any] | None=None) -> CoverageGetResponse
```

Explorer coverage. GET /api/v1/coverage. 

Required role permission: any authenticated API user.

### AsyncExplorerResource

Authorized explorer operations. Server-side RBAC remains authoritative.

```python
async def contents(self, case_id: int, *, params: ExplorerContentsParams | Mapping[str, Any] | None=None) -> ExplorerContentsResponse
```

Explorer contents. GET /api/v1/explorer/cases/{case_id}/contents. 

Required role permission: cases:read.

```python
async def category(self, case_id: int, category: str, *, params: ExplorerCategoryParams | Mapping[str, Any] | None=None) -> ExplorerCategoryResponse
```

Explorer category. GET /api/v1/explorer/cases/{case_id}/contents/{category}. 

Required role permission: cases:read.

```python
async def download(self, case_id: int, *, params: ExplorerDownloadParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Explorer file. GET /api/v1/explorer/cases/{case_id}/file. 

Required role permission: cases:read.

```python
async def connection_objects(self, *, params: ExplorerConnectionObjectsParams | Mapping[str, Any] | None=None) -> ExplorerConnectionObjectsResponse
```

Explorer connection objects. GET /api/v1/explorer/connection-objects. 

Required role permission: any authenticated API user.

```python
async def connections(self, *, params: ExplorerConnectionsParams | Mapping[str, Any] | None=None) -> ExplorerConnectionsResponse
```

Explorer connections. GET /api/v1/explorer/connections. 

Required role permission: any authenticated API user.

```python
async def evidence(self, *, params: ExplorerEvidenceParams | Mapping[str, Any] | None=None) -> ExplorerEvidenceResponse
```

Explorer evidence. GET /api/v1/explorer/evidence. 

Required role permission: any authenticated API user.

```python
async def graph(self, *, params: ExplorerGraphParams | Mapping[str, Any] | None=None) -> ExplorerGraphResponse
```

Explorer data. GET /api/v1/explorer/graph. 

Required role permission: any authenticated API user.

```python
async def shared_indicators(self, *, params: ExplorerSharedIndicatorsParams | Mapping[str, Any] | None=None) -> ExplorerSharedIndicatorsResponse
```

Explorer shared indicators. GET /api/v1/explorer/shared-indicators. 

Required role permission: any authenticated API user.

```python
async def list_views(self) -> ExplorerListViewsResponse
```

Explorer views. GET /api/v1/explorer/views. 

Required role permission: any authenticated API user.

```python
async def create_view(self, *, data: ExplorerCreateViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerCreateViewResponse
```

Explorer view create. POST /api/v1/explorer/views. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def get_view(self, vid: str) -> ExplorerGetViewResponse
```

Explorer view. GET /api/v1/explorer/views/{vid}. 

Required role permission: any authenticated API user.

```python
async def delete_view(self, vid: str, *, data: ExplorerDeleteViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerDeleteViewResponse
```

Explorer view delete. POST /api/v1/explorer/views/{vid}/delete. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def update_view(self, vid: str, *, data: ExplorerUpdateViewRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ExplorerUpdateViewResponse
```

Explorer view update. POST /api/v1/explorer/views/{vid}/update. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

### AsyncFamiliesResource

Authorized families operations. Server-side RBAC remains authoritative.

```python
async def list(self, *, params: FamiliesListParams | Mapping[str, Any] | None=None) -> FamiliesListResponse
```

Read Malware Families. GET /api/v1/families. 

Required role permission: tags:read.

```python
async def create(self, *, data: FamiliesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesCreateResponse
```

Families edit. POST /api/v1/families. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, fid: str, *, params: FamiliesGetParams | Mapping[str, Any] | None=None) -> FamiliesGetResponse
```

Read Malware Families. GET /api/v1/families/{fid}. 

Required role permission: tags:read.

```python
async def delete(self, fid: str, *, data: FamiliesDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteResponse
```

Families delete. POST /api/v1/families/{fid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def update(self, fid: str, *, data: FamiliesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateResponse
```

Families edit. POST /api/v1/families/{fid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def add_osint(self, fid: str, *, data: FamiliesAddOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesAddOsintResponse
```

Families osint edit. POST /api/v1/families/{fid}/osint. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete_osint(self, fid: str, eid: str, *, data: FamiliesDeleteOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteOsintResponse
```

Families osint delete. POST /api/v1/families/{fid}/osint/{eid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def update_osint(self, fid: str, eid: str, *, data: FamiliesUpdateOsintRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateOsintResponse
```

Families osint edit. POST /api/v1/families/{fid}/osint/{eid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def upload_reports(self, fid: str, *, data: FamiliesUploadReportsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUploadReportsResponse
```

Families reports upload. POST /api/v1/families/{fid}/reports. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete_report(self, fid: str, aid: str, *, data: FamiliesDeleteReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesDeleteReportResponse
```

Families reports delete. POST /api/v1/families/{fid}/reports/{aid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def download_report(self, fid: str, aid: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Families reports download. GET /api/v1/families/{fid}/reports/{aid}/download. 

Required role permission: tags:read.

```python
async def update_report(self, fid: str, aid: str, *, data: FamiliesUpdateReportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> FamiliesUpdateReportResponse
```

Families reports edit. POST /api/v1/families/{fid}/reports/{aid}/edit. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AsyncIndicatorsResource

Authorized indicators operations. Server-side RBAC remains authoritative.

```python
async def get(self, case_id: int) -> Indicators
```

Read indicators and revision. GET /api/v1/cases/{case_id}/indicators. 

Required role permission: indicators:read.

```python
async def update(self, case_id: int, *, data: IndicatorsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Indicators
```

Replace indicators with revision validation. PUT /api/v1/cases/{case_id}/indicators. Send all sections to preserve grouping, or rows when exactly one section exists. Each row has three text cells (≤4,000 characters), 1–100 sections with unique IDs (1–64 alphanumeric/underscore/hyphen), a nonempty title ≤200 characters and description ≤4,000 characters. The default section must remain; ≤10,000 rows total. revision must equal the current revision. The bundled official MISP attribute catalog is selectable/storable; export capability/help is supplied per type. Known compatibility aliases normalize on save; exact MISP canonical names take precedence. text/comment/other retain literal Unicode/whitespace and export as non-detection x-misp-attribute objects; Valid scalar attributes without native mappings use the official MISP-compatible contextual representation, with informational stix.notices. Missing attachment/sample bytes and invalid values retain saved drafts with explicit stix.issues. Legacy android-package aliases normalize to mobile-application-id while retaining identity and original_type provenance. Unknown/ambiguous types and invalid values remain saved as drafts with stix.issues; CSV is refreshed and stale STIX removed. Fully exportable tables generate iocs/indicators.stix.json with refanged native patterns and faithful contextual objects; any unsupported row withholds the entire STIX output. Preserve optional row_meta (including explicit boolean to_ids detection intent) and stix_meta when editing to retain IDs/timestamps/intent; do not generate them yourself. Unchanged saves do not advance revision. The authenticated web Indicators workspace provides CSV/STIX import previews and a read-only download; equivalent versioned preview/import/STIX download endpoints are also available to SDK clients.

Required role permission: indicators:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def import_rows(self, cid: int, *, data: IndicatorsImportRowsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> IndicatorsImportRowsResponse
```

Indicators import. POST /api/v1/cases/{cid}/indicators/import. 

Required role permission: indicators:write.

Execute affects real application data. Nothing executes automatically.

```python
async def preview_import(self, cid: int, *, data: IndicatorsPreviewImportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> IndicatorsPreviewImportResponse
```

Indicators import preview. POST /api/v1/cases/{cid}/indicators/import/preview. 

Required role permission: indicators:write.

Execute affects real application data. Nothing executes automatically.

```python
async def download_stix(self, cid: int, *, destination: str | Path, overwrite: bool=False) -> Path
```

Indicators stix download. GET /api/v1/cases/{cid}/indicators/stix. 

Required role permission: indicators:read.

### AsyncMetricsResource

Authorized metrics operations. Server-side RBAC remains authoritative.

```python
async def get(self) -> MetricsGetResponse
```

Read all-time metrics. GET /api/v1/metrics. Legacy all-time API metrics; independent of dashboard period filters.

Required role permission: metrics:read.

### AsyncNotesResource

Authorized notes operations. Server-side RBAC remains authoritative.

```python
async def delete_draft(self, case_id: int) -> None
```

Delete your case note draft. DELETE /api/v1/cases/{case_id}/draft. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def get_draft(self, case_id: int) -> NotesGetDraftResponse
```

Read your case note draft. GET /api/v1/cases/{case_id}/draft. 

Required role permission: cases:read.

```python
async def update_draft(self, case_id: int, *, data: NotesUpdateDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesUpdateDraftResponse
```

Replace your case note draft. PUT /api/v1/cases/{case_id}/draft. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def list(self, case_id: int, *, params: NotesListParams | Mapping[str, Any] | None=None) -> NotesListResponse
```

List case notes. GET /api/v1/cases/{case_id}/notes. 

Required role permission: cases:read.

```python
async def create(self, case_id: int, *, data: NotesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesCreateResponse
```

Create a note. POST /api/v1/cases/{case_id}/notes. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, case_id: int, note_id: int) -> None
```

Delete a note. DELETE /api/v1/cases/{case_id}/notes/{note_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, case_id: int, note_id: int) -> NotesGetResponse
```

Read a case note. GET /api/v1/cases/{case_id}/notes/{note_id}. 

Required role permission: cases:read.

```python
async def update(self, case_id: int, note_id: int, *, data: NotesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> NotesUpdateResponse
```

Update a note. PATCH /api/v1/cases/{case_id}/notes/{note_id}. The resulting body must contain non-whitespace text.

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, case_id, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AsyncPackagesResource

Authorized packages operations. Server-side RBAC remains authoritative.

```python
async def export(self, case_id: int, *, data: PackagesExportRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Download a Standard or RAW MIP ZIP. POST /api/v1/cases/{case_id}/archive. Packaging & Delivery or Completed only; active owner required when mandatory. Standard requires a completed Word report. Outstanding review blockers require acknowledge=true. Including samples additionally requires samples:export. Malware sample archives are dangerous; handle only in an isolated analysis environment.

Required role permission: cases:export.

Execute affects real application data. Nothing executes automatically.

```python
async def readiness(self, case_id: int) -> PackagesReadinessResponse
```

Read package readiness. GET /api/v1/cases/{case_id}/readiness. 

Required role permission: cases:read.

```python
async def set_readiness(self, case_id: int, *, data: PackagesSetReadinessRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> PackagesSetReadinessResponse
```

Set one category readiness. PUT /api/v1/cases/{case_id}/readiness. Not applicable requires a reason and is forbidden for reports. Populated requires an existing file.

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### AsyncPluginsResource

Authorized plugins operations. Server-side RBAC remains authoritative.

```python
async def capabilities(self) -> PluginsCapabilitiesResponse
```

Inspect existing plugin integration capabilities. GET /api/v1/plugins. 

Required role permission: any authenticated API user.

### AsyncReferencesResource

Authorized references operations. Server-side RBAC remains authoritative.

```python
async def get(self, case_id: int) -> References
```

Read references and revision. GET /api/v1/cases/{case_id}/references. 

Required role permission: references:read.

```python
async def update(self, case_id: int, *, data: ReferencesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> References
```

Replace references with revision validation. PUT /api/v1/cases/{case_id}/references. Fixed columns Link, Description. revision must equal the current revision.

Required role permission: references:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### AsyncReportsResource

Authorized reports operations. Server-side RBAC remains authoritative.

```python
async def get(self, case_id: int) -> ReportsGetResponse
```

Read report sections and mappings. GET /api/v1/cases/{case_id}/report. 

Required role permission: reports:read.

```python
async def update(self, case_id: int, *, data: ReportsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUpdateResponse
```

Save manual report sections. PUT /api/v1/cases/{case_id}/report. Only manual sections are written; generated sections are accepted but not persisted. Omitted manual sections retain their current values.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def download(self, case_id: int, *, params: ReportsDownloadParams | Mapping[str, Any] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Download the current report. GET /api/v1/cases/{case_id}/report/download. 404 if the requested output has not been generated.

Required role permission: reports:read.

```python
async def upload(self, case_id: int, *, data: ReportsUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUploadResponse
```

Upload an edited DOCX report. POST /api/v1/cases/{case_id}/report/final. Valid DOCX ≤20 MiB required. backup=1 saves the previous report. generate_pdf=0 skips PDF conversion; otherwise LibreOffice is required. Active report jobs block replacement.

Required role permission: reports:generate.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def generate(self, case_id: int, *, data: ReportsGenerateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsGenerateResponse
```

Start local Word report generation. POST /api/v1/cases/{case_id}/report/generate. Select an available template first. Generation saves supplied manual sections; omitted manual fields become empty. Read and submit existing sections to retain them. Existing reports require an explicit previous=backup or overwrite choice (409 needs_choice otherwise). Poll report/job; PDF generation requires LibreOffice. Accepts JSON or form fields.

Required role permission: reports:generate.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def list_images(self, case_id: int) -> ReportsListImagesResponse
```

List report image metadata. GET /api/v1/cases/{case_id}/report/images. 

Required role permission: reports:read.

```python
async def upload_image(self, case_id: int, *, data: ReportsUploadImageRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Image
```

Upload a report or task image. POST /api/v1/cases/{case_id}/report/images. Readable image ≤10 MiB and ≤20 megapixels; normalized to PNG. Active report jobs block changes.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def delete_image(self, case_id: int, name: str) -> None
```

Delete a report image. DELETE /api/v1/cases/{case_id}/report/images/{name}. 

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def download_image(self, case_id: int, name: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download a report image. GET /api/v1/cases/{case_id}/report/images/{name}. 

Required role permission: reports:read.

```python
async def job(self, case_id: int) -> ReportsJobResponse
```

Read the latest report generation job. GET /api/v1/cases/{case_id}/report/job. 

Required role permission: reports:read.

```python
async def get_mappings(self, case_id: int) -> ReportsGetMappingsResponse
```

Read MITRE mappings. GET /api/v1/cases/{case_id}/report/mappings. 

Required role permission: reports:read.

```python
async def update_mappings(self, case_id: int, *, data: ReportsUpdateMappingsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ReportsUpdateMappingsResponse
```

Save MITRE mapping Markdown. PUT /api/v1/cases/{case_id}/report/mappings. Blank text removes that mapping. Active report generation blocks saving.

Required role permission: reports:write.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

### AsyncRolesResource

Authorized roles operations. Server-side RBAC remains authoritative.

```python
async def permissions(self) -> RolesPermissionsResponse
```

List known permission names. GET /api/v1/permissions. 

Required role permission: roles:manage.

```python
async def list(self) -> RolesListResponse
```

List roles and permissions. GET /api/v1/roles. 

Required role permission: roles:manage.

```python
async def create(self, *, data: RolesCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Role
```

Create a custom role. POST /api/v1/roles. Only known, unique permissions already held by the caller may be granted.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, name: str) -> None
```

Delete an unused custom role. DELETE /api/v1/roles/{name}. Built-in roles and roles assigned to users cannot be deleted.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, name: str) -> Role
```

Read role metadata. GET /api/v1/roles/{name}. 

Required role permission: roles:manage.

```python
async def update(self, name: str, *, data: RolesUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> Role
```

Update a custom role. PATCH /api/v1/roles/{name}. Built-in roles are immutable. Cannot grant permissions the caller does not hold.

Required role permission: roles:manage.

Execute affects real application data. Nothing executes automatically.

### AsyncSearchResource

Authorized search operations. Server-side RBAC remains authoritative.

```python
async def query(self, *, params: SearchQueryParams | Mapping[str, Any] | None=None) -> SearchQueryResponse
```

Mip search results. GET /api/v1/search. 

Required role permission: cases:read.

### AsyncSettingsResource

Authorized settings operations. Server-side RBAC remains authoritative.

```python
async def get(self) -> SettingsGetResponse
```

Inspect configured settings (no secrets). GET /api/v1/settings. 

Required role permission: settings:read.

```python
async def update(self, *, data: SettingsUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> SettingsUpdateResponse
```

Set the sample archive password. PATCH /api/v1/settings. NUL characters are rejected. Changes affect future sample archives; the password is never returned.

Required role permission: settings:write.

Execute affects real application data. Nothing executes automatically.

### AsyncTagsResource

Authorized tags operations. Server-side RBAC remains authoritative.

```python
async def for_case(self, cid: int) -> TagsForCaseResponse
```

Case tags list. GET /api/v1/cases/{cid}/tags. 

Required role permission: tags:read.

```python
async def assign(self, cid: int, tid: int) -> TagsAssignResponse
```

Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/assign. 

Required role permission: tags:assign.

Execute affects real application data. Nothing executes automatically.

```python
async def remove(self, cid: int, tid: int) -> TagsRemoveResponse
```

Case tag change. POST /api/v1/cases/{cid}/tags/{tid}/remove. 

Required role permission: tags:assign.

Execute affects real application data. Nothing executes automatically.

```python
async def list(self, *, params: TagsListParams | Mapping[str, Any] | None=None) -> TagsListResponse
```

Tags search. GET /api/v1/tags. 

Required role permission: tags:read.

```python
async def create(self, *, data: TagsCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsCreateResponse
```

Tags create. POST /api/v1/tags. 

Required role permission: tags:create.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, tid: int) -> TagsGetResponse
```

Read a tag. GET /api/v1/tags/{tid}. 

Required role permission: tags:read.

```python
async def delete(self, tid: int, *, data: TagsDeleteRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsDeleteResponse
```

Tag manage. POST /api/v1/tags/{tid}/delete. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def merge(self, tid: int, *, data: TagsMergeRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsMergeResponse
```

Tag manage. POST /api/v1/tags/{tid}/merge. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def rename(self, tid: int, *, data: TagsRenameRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TagsRenameResponse
```

Tag manage. POST /api/v1/tags/{tid}/rename. 

Required role permission: tags:manage.

Execute affects real application data. Nothing executes automatically.

### AsyncTasksResource

Authorized tasks operations. Server-side RBAC remains authoritative.

```python
async def list(self, case_id: int, *, params: TasksListParams | Mapping[str, Any] | None=None) -> TasksListResponse
```

List case tasks. GET /api/v1/cases/{case_id}/tasks. 

Required role permission: cases:read.

```python
async def create(self, case_id: int, *, data: TasksCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TasksCreateResponse
```

Create a task. POST /api/v1/cases/{case_id}/tasks. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, case_id: int, task_id: int) -> None
```

Delete a task. DELETE /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, case_id: int, task_id: int) -> TasksGetResponse
```

Read a case task. GET /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:read.

```python
async def update(self, case_id: int, task_id: int, *, data: TasksUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TasksUpdateResponse
```

Update a task. PATCH /api/v1/cases/{case_id}/tasks/{task_id}. 

Required role permission: cases:update.

Content edits require Malware Analysis or Packaging & Delivery stage and an active owner when ownership is mandatory.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, case_id, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

### AsyncTemplatesResource

Authorized templates operations. Server-side RBAC remains authoritative.

```python
async def list(self) -> TemplatesListResponse
```

List your Word templates. GET /api/v1/templates. 

Required role permission: templates:manage.

```python
async def upload(self, *, data: TemplatesUploadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TemplatesUploadResponse
```

Upload and select a Word template. POST /api/v1/templates. DOCX ≤10 MiB, containing every report section heading or placeholder. Templates belong to the requesting user.

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, template_id: str) -> None
```

Delete your Word template. DELETE /api/v1/templates/{template_id}. 

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def download(self, template_id: str, *, destination: str | Path, overwrite: bool=False) -> Path
```

Download your Word template. GET /api/v1/templates/{template_id}. 

Required role permission: templates:manage.

```python
async def select(self, *, data: TemplatesSelectRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> TemplatesSelectResponse
```

Select your Word template. PUT /api/v1/templates/selected. 

Required role permission: templates:manage.

Execute affects real application data. Nothing executes automatically.

### AsyncToolsResource

Authorized tools operations. Server-side RBAC remains authoritative.

```python
async def snort_open(self, cid: int, *, params: ToolsSnortOpenParams | Mapping[str, Any] | None=None) -> ToolsSnortOpenResponse
```

Snort open. GET /api/v1/cases/{cid}/snort/file. 

Required role permission: cases:assets.

```python
async def snort_save(self, cid: int, *, data: ToolsSnortSaveRequest | Mapping[str, Any] | None=None, params: ToolsSnortSaveParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortSaveResponse
```

Snort save. POST /api/v1/cases/{cid}/snort/file. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
async def snort_inventory(self, cid: int, *, params: ToolsSnortInventoryParams | Mapping[str, Any] | None=None) -> ToolsSnortInventoryResponse
```

Snort inventory. GET /api/v1/cases/{cid}/snort/files. 

Required role permission: cases:assets.

```python
async def snort_normalize(self, cid: int, *, data: ToolsSnortNormalizeRequest | Mapping[str, Any] | None=None, params: ToolsSnortNormalizeParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortNormalizeResponse
```

Snort normalize. POST /api/v1/cases/{cid}/snort/normalize. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_open(self, cid: int, *, params: ToolsYaraOpenParams | Mapping[str, Any] | None=None) -> ToolsYaraOpenResponse
```

Yara open. GET /api/v1/cases/{cid}/yara/file. 

Required role permission: cases:assets.

```python
async def yara_save(self, cid: int, *, data: ToolsYaraSaveRequest | Mapping[str, Any] | None=None, params: ToolsYaraSaveParams | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraSaveResponse
```

Yara save. POST /api/v1/cases/{cid}/yara/file. 

Required role permission: cases:assets.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_files(self, cid: int, *, params: ToolsYaraFilesParams | Mapping[str, Any] | None=None) -> ToolsYaraFilesResponse
```

Yara files. GET /api/v1/cases/{cid}/yara/files. 

Required role permission: cases:assets.

```python
async def list(self) -> ToolsListResponse
```

List authorized installed analyst tools. GET /api/v1/tools. 

Required role permission: any authenticated API user.

```python
async def snort_download(self, *, data: ToolsSnortDownloadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Snort download. POST /api/v1/tools/snort/download. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def snort_draft(self, *, data: ToolsSnortDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortDraftResponse
```

Snort draft. POST /api/v1/tools/snort/draft. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def snort_jobs(self, *, data: ToolsSnortJobsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortJobsResponse
```

Snort jobs. POST /api/v1/tools/snort/jobs. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def snort_job(self, job: str) -> ToolsSnortJobResponse
```

Snort job. GET /api/v1/tools/snort/jobs/{job}. 

Required role permission: any authenticated API user.

```python
async def snort_cancel(self, job: str, *, data: ToolsSnortCancelRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsSnortCancelResponse
```

Snort cancel. POST /api/v1/tools/snort/jobs/{job}/cancel. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def snort_state(self) -> ToolsSnortStateResponse
```

Snort state. GET /api/v1/tools/snort/state. 

Required role permission: any authenticated API user.

```python
async def process_text(self, *, data: ToolsProcessTextRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsProcessTextResponse
```

Tools text process. POST /api/v1/tools/text/process. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_download(self, *, data: ToolsYaraDownloadRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None, destination: str | Path, overwrite: bool=False) -> Path
```

Yara download. POST /api/v1/tools/yara/download. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_draft(self, *, data: ToolsYaraDraftRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraDraftResponse
```

Yara draft. POST /api/v1/tools/yara/draft. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_jobs(self, *, data: ToolsYaraJobsRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraJobsResponse
```

Yara jobs. POST /api/v1/tools/yara/jobs. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_job(self, job: str) -> ToolsYaraJobResponse
```

Yara job. GET /api/v1/tools/yara/jobs/{job}. 

Required role permission: any authenticated API user.

```python
async def yara_cancel(self, job: str, *, data: ToolsYaraCancelRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> ToolsYaraCancelResponse
```

Yara cancel. POST /api/v1/tools/yara/jobs/{job}/cancel. 

Required role permission: any authenticated API user.

Execute affects real application data. Nothing executes automatically.

```python
async def yara_state(self) -> ToolsYaraStateResponse
```

Yara state. GET /api/v1/tools/yara/state. 

Required role permission: any authenticated API user.

### AsyncUsersResource

Authorized users operations. Server-side RBAC remains authoritative.

```python
async def list(self, *, params: UsersListParams | Mapping[str, Any] | None=None) -> UsersListResponse
```

List accounts. GET /api/v1/users. 

Required role permission: users:manage.

```python
async def create(self, *, data: UsersCreateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> UsersCreateResponse
```

Create an account. POST /api/v1/users. The role must exist. Without roles:manage, only roles whose permissions are a subset of the caller’s role may be assigned.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def delete(self, user_id: int) -> None
```

Delete an account. DELETE /api/v1/users/{user_id}. Cannot delete yourself or the last active Administrator. Case ownership/creator references are cleared.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def get(self, user_id: int) -> UsersGetResponse
```

Read account metadata. GET /api/v1/users/{user_id}. 

Required role permission: users:manage.

```python
async def update(self, user_id: int, *, data: UsersUpdateRequest | Mapping[str, Any] | None=None, files: Mapping[str, Any] | list[tuple[str, Any]] | None=None) -> UsersUpdateResponse
```

Change account role or active status. PATCH /api/v1/users/{user_id}. Cannot disable/demote the last active Administrator. Role assignment uses the same permission constraints as account creation. Changes invalidate existing web sessions.

Required role permission: users:manage.

Execute affects real application data. Nothing executes automatically.

```python
async def iter_all(self, *, params=None)
```

Yield authorized records across offset pages without preloading the dataset.

## models.py

### APIModel

Forward-compatible server object with unknown fields retained.

### Error

Error version-1 API fields.

### User

User version-1 API fields.

### Token

Token version-1 API fields.

### Role

Role version-1 API fields.

### Case

Case version-1 API fields.

### Task

Task version-1 API fields.

### Note

Note version-1 API fields.

### Draft

Draft version-1 API fields.

### Readiness

Readiness value.

### File

File version-1 API fields.

### IndicatorRowIdentity

IndicatorRowIdentity version-1 API fields.

### IndicatorSection

IndicatorSection version-1 API fields.

### Indicators

Indicators version-1 API fields.

### References

References version-1 API fields.

### Template

Template version-1 API fields.

### Image

Image version-1 API fields.

### Job

Job version-1 API fields.

### SyncCase

SyncCase version-1 API fields.

### SyncOutcome

SyncOutcome version-1 API fields.

### SyncResult

SyncResult version-1 API fields.

### ActorsListParams

ActorsListParams version-1 API fields.

### ActorsListResponse

ActorsListResponse version-1 API fields.

### ActorsCreateRequest

ActorsCreateRequest version-1 API fields.

### ActorsCreateResponse

ActorsCreateResponse version-1 API fields.

### ActorsGetParams

ActorsGetParams version-1 API fields.

### ActorsGetResponse

ActorsGetResponse version-1 API fields.

### ActorsDeleteRequest

ActorsDeleteRequest version-1 API fields.

### ActorsDeleteResponse

ActorsDeleteResponse version-1 API fields.

### ActorsUpdateRequest

ActorsUpdateRequest version-1 API fields.

### ActorsUpdateResponse

ActorsUpdateResponse version-1 API fields.

### ActorsAddOsintRequest

ActorsAddOsintRequest version-1 API fields.

### ActorsAddOsintResponse

ActorsAddOsintResponse version-1 API fields.

### ActorsDeleteOsintRequest

ActorsDeleteOsintRequest version-1 API fields.

### ActorsDeleteOsintResponse

ActorsDeleteOsintResponse version-1 API fields.

### ActorsUpdateOsintRequest

ActorsUpdateOsintRequest version-1 API fields.

### ActorsUpdateOsintResponse

ActorsUpdateOsintResponse version-1 API fields.

### ActorsUploadReportsRequest

ActorsUploadReportsRequest version-1 API fields.

### ActorsUploadReportsResponse

ActorsUploadReportsResponse version-1 API fields.

### ActorsDeleteReportRequest

ActorsDeleteReportRequest version-1 API fields.

### ActorsDeleteReportResponse

ActorsDeleteReportResponse version-1 API fields.

### ActorsUpdateReportRequest

ActorsUpdateReportRequest version-1 API fields.

### ActorsUpdateReportResponse

ActorsUpdateReportResponse version-1 API fields.

### AuditExportCsvParams

AuditExportCsvParams version-1 API fields.

### BackupsCreateJobRequest

BackupsCreateJobRequest version-1 API fields.

### BackupsCreateJobResponse

BackupsCreateJobResponse version-1 API fields.

### BackupsJobResponse

BackupsJobResponse version-1 API fields.

### BackupsApplyRequest

BackupsApplyRequest version-1 API fields.

### BackupsApplyResponse

BackupsApplyResponse version-1 API fields.

### BackupsPreviewRequest

BackupsPreviewRequest version-1 API fields.

### BackupsPreviewResponse

BackupsPreviewResponse version-1 API fields.

### BackupsSyncApplyRequest

BackupsSyncApplyRequest version-1 API fields.

### BackupsImportCasesResponse

BackupsImportCasesResponse version-1 API fields.

### BackupsImportCasesRequest

BackupsImportCasesRequest version-1 API fields.

### BackupsImportRawResponse

BackupsImportRawResponse version-1 API fields.

### BackupsImportRawRequest

BackupsImportRawRequest version-1 API fields.

### CasesListParams

CasesListParams version-1 API fields.

### CasesListResponse

CasesListResponse version-1 API fields.

### CasesCreateRequest

CasesCreateRequest version-1 API fields.

### CasesCreateResponse

CasesCreateResponse version-1 API fields.

### CasesGetResponse

CasesGetResponse version-1 API fields.

### CasesUpdateRequest

CasesUpdateRequest version-1 API fields.

### CasesUpdateResponse

CasesUpdateResponse version-1 API fields.

### PackagesExportRequest

PackagesExportRequest version-1 API fields.

### AssetsDeleteRequest

AssetsDeleteRequest version-1 API fields.

### AssetsListParams

AssetsListParams version-1 API fields.

### AssetsListResponse

AssetsListResponse version-1 API fields.

### AssetsUploadRequest

AssetsUploadRequest version-1 API fields.

### AssetsUploadResponse

AssetsUploadResponse version-1 API fields.

### NotesGetDraftResponse

NotesGetDraftResponse version-1 API fields.

### NotesUpdateDraftRequest

NotesUpdateDraftRequest version-1 API fields.

### NotesUpdateDraftResponse

NotesUpdateDraftResponse version-1 API fields.

### IndicatorsUpdateRequest

IndicatorsUpdateRequest version-1 API fields.

### NotesListParams

NotesListParams version-1 API fields.

### NotesListResponse

NotesListResponse version-1 API fields.

### NotesCreateRequest

NotesCreateRequest version-1 API fields.

### NotesCreateResponse

NotesCreateResponse version-1 API fields.

### NotesGetResponse

NotesGetResponse version-1 API fields.

### NotesUpdateRequest

NotesUpdateRequest version-1 API fields.

### NotesUpdateResponse

NotesUpdateResponse version-1 API fields.

### PackagesReadinessResponse

PackagesReadinessResponse version-1 API fields.

### PackagesSetReadinessRequest

PackagesSetReadinessRequest version-1 API fields.

### PackagesSetReadinessResponse

PackagesSetReadinessResponse version-1 API fields.

### ReferencesUpdateRequest

ReferencesUpdateRequest version-1 API fields.

### CasesReopenResponse

CasesReopenResponse version-1 API fields.

### ReportsGetResponse

ReportsGetResponse version-1 API fields.

### ReportsUpdateRequest

ReportsUpdateRequest version-1 API fields.

### ReportsUpdateResponse

ReportsUpdateResponse version-1 API fields.

### ReportsDownloadParams

ReportsDownloadParams version-1 API fields.

### ReportsUploadRequest

ReportsUploadRequest version-1 API fields.

### ReportsUploadResponse

ReportsUploadResponse version-1 API fields.

### ReportsGenerateRequest

ReportsGenerateRequest version-1 API fields.

### ReportsGenerateResponse

ReportsGenerateResponse version-1 API fields.

### ReportsListImagesResponse

ReportsListImagesResponse version-1 API fields.

### ReportsUploadImageRequest

ReportsUploadImageRequest version-1 API fields.

### ReportsJobResponse

ReportsJobResponse version-1 API fields.

### ReportsGetMappingsResponse

ReportsGetMappingsResponse version-1 API fields.

### ReportsUpdateMappingsRequest

ReportsUpdateMappingsRequest version-1 API fields.

### ReportsUpdateMappingsResponse

ReportsUpdateMappingsResponse version-1 API fields.

### CasesAdvanceRequest

CasesAdvanceRequest version-1 API fields.

### CasesAdvanceResponse

CasesAdvanceResponse version-1 API fields.

### TasksListParams

TasksListParams version-1 API fields.

### TasksListResponse

TasksListResponse version-1 API fields.

### TasksCreateRequest

TasksCreateRequest version-1 API fields.

### TasksCreateResponse

TasksCreateResponse version-1 API fields.

### TasksGetResponse

TasksGetResponse version-1 API fields.

### TasksUpdateRequest

TasksUpdateRequest version-1 API fields.

### TasksUpdateResponse

TasksUpdateResponse version-1 API fields.

### IndicatorsImportRowsRequest

IndicatorsImportRowsRequest version-1 API fields.

### IndicatorsImportRowsResponse

IndicatorsImportRowsResponse version-1 API fields.

### IndicatorsPreviewImportRequest

IndicatorsPreviewImportRequest version-1 API fields.

### IndicatorsPreviewImportResponse

IndicatorsPreviewImportResponse version-1 API fields.

### ToolsSnortOpenParams

ToolsSnortOpenParams version-1 API fields.

### ToolsSnortOpenResponse

ToolsSnortOpenResponse version-1 API fields.

### ToolsSnortSaveRequest

ToolsSnortSaveRequest version-1 API fields.

### ToolsSnortSaveParams

ToolsSnortSaveParams version-1 API fields.

### ToolsSnortSaveResponse

ToolsSnortSaveResponse version-1 API fields.

### ToolsSnortInventoryParams

ToolsSnortInventoryParams version-1 API fields.

### ToolsSnortInventoryResponse

ToolsSnortInventoryResponse version-1 API fields.

### ToolsSnortNormalizeRequest

ToolsSnortNormalizeRequest version-1 API fields.

### ToolsSnortNormalizeParams

ToolsSnortNormalizeParams version-1 API fields.

### ToolsSnortNormalizeResponse

ToolsSnortNormalizeResponse version-1 API fields.

### TagsForCaseResponse

TagsForCaseResponse version-1 API fields.

### TagsAssignResponse

TagsAssignResponse version-1 API fields.

### TagsRemoveResponse

TagsRemoveResponse version-1 API fields.

### ToolsYaraOpenParams

ToolsYaraOpenParams version-1 API fields.

### ToolsYaraOpenResponse

ToolsYaraOpenResponse version-1 API fields.

### ToolsYaraSaveRequest

ToolsYaraSaveRequest version-1 API fields.

### ToolsYaraSaveParams

ToolsYaraSaveParams version-1 API fields.

### ToolsYaraSaveResponse

ToolsYaraSaveResponse version-1 API fields.

### ToolsYaraFilesParams

ToolsYaraFilesParams version-1 API fields.

### ToolsYaraFilesResponse

ToolsYaraFilesResponse version-1 API fields.

### CoverageGetParams

CoverageGetParams version-1 API fields.

### CoverageGetResponse

CoverageGetResponse version-1 API fields.

### ExplorerContentsParams

ExplorerContentsParams version-1 API fields.

### ExplorerContentsResponse

ExplorerContentsResponse version-1 API fields.

### ExplorerCategoryParams

ExplorerCategoryParams version-1 API fields.

### ExplorerCategoryResponse

ExplorerCategoryResponse version-1 API fields.

### ExplorerDownloadParams

ExplorerDownloadParams version-1 API fields.

### ExplorerConnectionObjectsParams

ExplorerConnectionObjectsParams version-1 API fields.

### ExplorerConnectionObjectsResponse

ExplorerConnectionObjectsResponse version-1 API fields.

### ExplorerConnectionsParams

ExplorerConnectionsParams version-1 API fields.

### ExplorerConnectionsResponse

ExplorerConnectionsResponse version-1 API fields.

### ExplorerEvidenceParams

ExplorerEvidenceParams version-1 API fields.

### ExplorerEvidenceResponse

ExplorerEvidenceResponse version-1 API fields.

### ExplorerGraphParams

ExplorerGraphParams version-1 API fields.

### ExplorerGraphResponse

ExplorerGraphResponse version-1 API fields.

### ExplorerSharedIndicatorsParams

ExplorerSharedIndicatorsParams version-1 API fields.

### ExplorerSharedIndicatorsResponse

ExplorerSharedIndicatorsResponse version-1 API fields.

### ExplorerListViewsResponse

ExplorerListViewsResponse version-1 API fields.

### ExplorerCreateViewRequest

ExplorerCreateViewRequest version-1 API fields.

### ExplorerCreateViewResponse

ExplorerCreateViewResponse version-1 API fields.

### ExplorerGetViewResponse

ExplorerGetViewResponse version-1 API fields.

### ExplorerDeleteViewRequest

ExplorerDeleteViewRequest version-1 API fields.

### ExplorerDeleteViewResponse

ExplorerDeleteViewResponse version-1 API fields.

### ExplorerUpdateViewRequest

ExplorerUpdateViewRequest version-1 API fields.

### ExplorerUpdateViewResponse

ExplorerUpdateViewResponse version-1 API fields.

### FamiliesListParams

FamiliesListParams version-1 API fields.

### FamiliesListResponse

FamiliesListResponse version-1 API fields.

### FamiliesCreateRequest

FamiliesCreateRequest version-1 API fields.

### FamiliesCreateResponse

FamiliesCreateResponse version-1 API fields.

### FamiliesGetParams

FamiliesGetParams version-1 API fields.

### FamiliesGetResponse

FamiliesGetResponse version-1 API fields.

### FamiliesDeleteRequest

FamiliesDeleteRequest version-1 API fields.

### FamiliesDeleteResponse

FamiliesDeleteResponse version-1 API fields.

### FamiliesUpdateRequest

FamiliesUpdateRequest version-1 API fields.

### FamiliesUpdateResponse

FamiliesUpdateResponse version-1 API fields.

### FamiliesAddOsintRequest

FamiliesAddOsintRequest version-1 API fields.

### FamiliesAddOsintResponse

FamiliesAddOsintResponse version-1 API fields.

### FamiliesDeleteOsintRequest

FamiliesDeleteOsintRequest version-1 API fields.

### FamiliesDeleteOsintResponse

FamiliesDeleteOsintResponse version-1 API fields.

### FamiliesUpdateOsintRequest

FamiliesUpdateOsintRequest version-1 API fields.

### FamiliesUpdateOsintResponse

FamiliesUpdateOsintResponse version-1 API fields.

### FamiliesUploadReportsRequest

FamiliesUploadReportsRequest version-1 API fields.

### FamiliesUploadReportsResponse

FamiliesUploadReportsResponse version-1 API fields.

### FamiliesDeleteReportRequest

FamiliesDeleteReportRequest version-1 API fields.

### FamiliesDeleteReportResponse

FamiliesDeleteReportResponse version-1 API fields.

### FamiliesUpdateReportRequest

FamiliesUpdateReportRequest version-1 API fields.

### FamiliesUpdateReportResponse

FamiliesUpdateReportResponse version-1 API fields.

### AuthenticationMeResponse

AuthenticationMeResponse version-1 API fields.

### MetricsGetResponse

MetricsGetResponse version-1 API fields.

### RolesPermissionsResponse

RolesPermissionsResponse version-1 API fields.

### PluginsCapabilitiesResponse

PluginsCapabilitiesResponse version-1 API fields.

### RolesListResponse

RolesListResponse version-1 API fields.

### RolesCreateRequest

RolesCreateRequest version-1 API fields.

### RolesUpdateRequest

RolesUpdateRequest version-1 API fields.

### SearchQueryParams

SearchQueryParams version-1 API fields.

### SearchQueryResponse

SearchQueryResponse version-1 API fields.

### SettingsGetResponse

SettingsGetResponse version-1 API fields.

### SettingsUpdateRequest

SettingsUpdateRequest version-1 API fields.

### SettingsUpdateResponse

SettingsUpdateResponse version-1 API fields.

### TagsListParams

TagsListParams version-1 API fields.

### TagsListResponse

TagsListResponse version-1 API fields.

### TagsCreateRequest

TagsCreateRequest version-1 API fields.

### TagsCreateResponse

TagsCreateResponse version-1 API fields.

### TagsGetResponse

TagsGetResponse version-1 API fields.

### TagsDeleteRequest

TagsDeleteRequest version-1 API fields.

### TagsDeleteResponse

TagsDeleteResponse version-1 API fields.

### TagsMergeRequest

TagsMergeRequest version-1 API fields.

### TagsMergeResponse

TagsMergeResponse version-1 API fields.

### TagsRenameRequest

TagsRenameRequest version-1 API fields.

### TagsRenameResponse

TagsRenameResponse version-1 API fields.

### TemplatesListResponse

TemplatesListResponse version-1 API fields.

### TemplatesUploadResponse

TemplatesUploadResponse version-1 API fields.

### TemplatesUploadRequest

TemplatesUploadRequest version-1 API fields.

### TemplatesSelectRequest

TemplatesSelectRequest version-1 API fields.

### TemplatesSelectResponse

TemplatesSelectResponse version-1 API fields.

### AuthenticationListTokensResponse

AuthenticationListTokensResponse version-1 API fields.

### AuthenticationCreateTokenRequest

AuthenticationCreateTokenRequest version-1 API fields.

### AuthenticationCreateTokenResponse

AuthenticationCreateTokenResponse version-1 API fields.

### ToolsListResponse

ToolsListResponse version-1 API fields.

### ToolsSnortDownloadRequest

ToolsSnortDownloadRequest version-1 API fields.

### ToolsSnortDraftRequest

ToolsSnortDraftRequest version-1 API fields.

### ToolsSnortDraftResponse

ToolsSnortDraftResponse version-1 API fields.

### ToolsSnortJobsRequest

ToolsSnortJobsRequest version-1 API fields.

### ToolsSnortJobsResponse

ToolsSnortJobsResponse version-1 API fields.

### ToolsSnortJobResponse

ToolsSnortJobResponse version-1 API fields.

### ToolsSnortCancelRequest

ToolsSnortCancelRequest version-1 API fields.

### ToolsSnortCancelResponse

ToolsSnortCancelResponse version-1 API fields.

### ToolsSnortStateResponse

ToolsSnortStateResponse version-1 API fields.

### ToolsProcessTextRequest

ToolsProcessTextRequest version-1 API fields.

### ToolsProcessTextResponse

ToolsProcessTextResponse version-1 API fields.

### ToolsYaraDownloadRequest

ToolsYaraDownloadRequest version-1 API fields.

### ToolsYaraDraftRequest

ToolsYaraDraftRequest version-1 API fields.

### ToolsYaraDraftResponse

ToolsYaraDraftResponse version-1 API fields.

### ToolsYaraJobsRequest

ToolsYaraJobsRequest version-1 API fields.

### ToolsYaraJobsResponse

ToolsYaraJobsResponse version-1 API fields.

### ToolsYaraJobResponse

ToolsYaraJobResponse version-1 API fields.

### ToolsYaraCancelRequest

ToolsYaraCancelRequest version-1 API fields.

### ToolsYaraCancelResponse

ToolsYaraCancelResponse version-1 API fields.

### ToolsYaraStateResponse

ToolsYaraStateResponse version-1 API fields.

### UsersListParams

UsersListParams version-1 API fields.

### UsersListResponse

UsersListResponse version-1 API fields.

### UsersCreateRequest

UsersCreateRequest version-1 API fields.

### UsersCreateResponse

UsersCreateResponse version-1 API fields.

### UsersGetResponse

UsersGetResponse version-1 API fields.

### UsersUpdateRequest

UsersUpdateRequest version-1 API fields.

### UsersUpdateResponse

UsersUpdateResponse version-1 API fields.

### ReadinessValueItem

ReadinessValueItem version-1 API fields.

### IndicatorSectionRowMetaItem

IndicatorSectionRowMetaItem version-1 API fields.

### IndicatorsStix

IndicatorsStix version-1 API fields.

### ActorsListResponseProfilesItem

ActorsListResponseProfilesItem version-1 API fields.

### ActorsGetResponseProfile

ActorsGetResponseProfile version-1 API fields.

### CasesGetResponseCase

CasesGetResponseCase version-1 API fields.

### ReportsGetResponseSections

ReportsGetResponseSections version-1 API fields.

### ReportsGetResponseMappings

ReportsGetResponseMappings version-1 API fields.

### ReportsUpdateRequestSections

ReportsUpdateRequestSections version-1 API fields.

### ReportsUpdateResponseSections

ReportsUpdateResponseSections version-1 API fields.

### ReportsGenerateRequestSections

ReportsGenerateRequestSections version-1 API fields.

### ReportsGetMappingsResponseMappings

ReportsGetMappingsResponseMappings version-1 API fields.

### ReportsUpdateMappingsRequestMappings

ReportsUpdateMappingsRequestMappings version-1 API fields.

### ReportsUpdateMappingsResponseMappings

ReportsUpdateMappingsResponseMappings version-1 API fields.

### CoverageGetResponseRowsItem

CoverageGetResponseRowsItem version-1 API fields.

### CoverageGetResponseGapsItem

CoverageGetResponseGapsItem version-1 API fields.

### FamiliesListResponseProfilesItem

FamiliesListResponseProfilesItem version-1 API fields.

### FamiliesGetResponseProfile

FamiliesGetResponseProfile version-1 API fields.

### MetricsGetResponseUsersItem

MetricsGetResponseUsersItem version-1 API fields.

### MetricsGetResponseStagesItem

MetricsGetResponseStagesItem version-1 API fields.

### MetricsGetResponseCompletedItem

MetricsGetResponseCompletedItem version-1 API fields.

### RolesPermissionsResponsePermissionsItem

RolesPermissionsResponsePermissionsItem version-1 API fields.

### PluginsCapabilitiesResponsePluginsItem

PluginsCapabilitiesResponsePluginsItem version-1 API fields.

### SettingsGetResponseSettings

SettingsGetResponseSettings version-1 API fields.

### SettingsUpdateResponseSettings

SettingsUpdateResponseSettings version-1 API fields.

### TagsGetResponseTag

TagsGetResponseTag version-1 API fields.

### ToolsListResponseToolsItem

ToolsListResponseToolsItem version-1 API fields.

### IndicatorsStixIssuesItem

IndicatorsStixIssuesItem version-1 API fields.

### IndicatorsStixNoticesItem

IndicatorsStixNoticesItem version-1 API fields.

### ActorsListResponseProfilesItemOsintItem

ActorsListResponseProfilesItemOsintItem version-1 API fields.

### ActorsListResponseProfilesItemReportsItem

ActorsListResponseProfilesItemReportsItem version-1 API fields.

### ActorsGetResponseProfileOsintItem

ActorsGetResponseProfileOsintItem version-1 API fields.

### ActorsGetResponseProfileReportsItem

ActorsGetResponseProfileReportsItem version-1 API fields.

### CasesGetResponseCaseHistoryItem

CasesGetResponseCaseHistoryItem version-1 API fields.

### CasesGetResponseCaseDeferredItem

CasesGetResponseCaseDeferredItem version-1 API fields.

### CoverageGetResponseRowsItemIndicators

CoverageGetResponseRowsItemIndicators version-1 API fields.

### CoverageGetResponseRowsItemAttack

CoverageGetResponseRowsItemAttack version-1 API fields.

### CoverageGetResponseRowsItemMbc

CoverageGetResponseRowsItemMbc version-1 API fields.

### CoverageGetResponseRowsItemReport

CoverageGetResponseRowsItemReport version-1 API fields.

### CoverageGetResponseRowsItemPackage

CoverageGetResponseRowsItemPackage version-1 API fields.

### CoverageGetResponseGapsItemSupportsItem

CoverageGetResponseGapsItemSupportsItem version-1 API fields.

### CoverageGetResponseGapsItemAction

CoverageGetResponseGapsItemAction version-1 API fields.

### FamiliesListResponseProfilesItemOsintItem

FamiliesListResponseProfilesItemOsintItem version-1 API fields.

### FamiliesListResponseProfilesItemReportsItem

FamiliesListResponseProfilesItemReportsItem version-1 API fields.

### FamiliesGetResponseProfileOsintItem

FamiliesGetResponseProfileOsintItem version-1 API fields.

### FamiliesGetResponseProfileReportsItem

FamiliesGetResponseProfileReportsItem version-1 API fields.

### SettingsGetResponseSettingsSampleArchivePassword

SettingsGetResponseSettingsSampleArchivePassword version-1 API fields.

### SettingsUpdateResponseSettingsSampleArchivePassword

SettingsUpdateResponseSettingsSampleArchivePassword version-1 API fields.
