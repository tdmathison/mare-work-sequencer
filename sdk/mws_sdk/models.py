"""Generated typed API models. Regenerate with scripts/build_sdk.py; do not edit."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, RootModel, SecretStr

class APIModel(BaseModel):
    """Forward-compatible server object with unknown fields retained."""
    model_config = ConfigDict(extra="allow", populate_by_name=True, hide_input_in_errors=True)

class Error(APIModel):
    """Error version-1 API fields."""
    error: str = ...
    required_permission: str | None = None
    blockers: list[str] | None = None
    needs_choice: bool | None = None

class User(APIModel):
    """User version-1 API fields."""
    id: int | None = None
    uuid: str | None = None
    username: str | None = None
    role: str | None = None
    active: bool | None = None
    forced_password_change: bool | None = None

class Token(APIModel):
    """Token version-1 API fields."""
    name: str | None = None
    token_prefix: str | None = None
    created: str | None = None
    id: int | None = None
    last_used: str | None = None
    revoked: str | None = None
    expires: str | None = None

class Role(APIModel):
    """Role version-1 API fields."""
    name: str | None = None
    description: str | None = None
    builtin: bool | None = None
    permissions: list[str] | None = None

class Case(APIModel):
    """Case version-1 API fields."""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    owner_id: int | None = None
    external_system: Literal['', 'Vortex', 'XSIAM', 'JIRA'] | None = None
    external_number: str | None = Field(None, max_length=200)
    id: int | None = None
    number: str | None = None
    stage: int | None = Field(None, ge=0, le=3)
    stage_name: str | None = None
    created: str | None = None
    report_path: str | None = None
    owner_name: str | None = None
    creator_name: str | None = None
    creator_id: int | None = None
    owner_active: bool | None = None

class Task(APIModel):
    """Task version-1 API fields."""
    title: str | None = Field(None, min_length=1, max_length=200)
    body: str | None = Field(None, max_length=20000)
    priority: Literal['Low', 'Normal', 'High', 'Critical'] | None = None
    id: int | None = None
    state: Literal['Not Started', 'In Progress', 'Completed'] | None = None
    done: int | None = None
    created: str | None = None
    group_id: str | None = None
    source_collection_id: str | None = None
    source_template_id: str | None = None
    source_revision: int | None = None
    position: int | None = None

class Note(APIModel):
    """Note version-1 API fields."""
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=100000)
    include_export: int | None = None
    id: int | None = None
    author: str | None = None
    created: str | None = None

class Draft(APIModel):
    """Draft version-1 API fields."""
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=100000)
    updated: str | None = None

class Readiness(RootModel['list[ReadinessValueItem]']):
    """Readiness value."""
    def __iter__(self): return iter(self.root)
    def __len__(self): return len(self.root)
    def __getitem__(self, key): return self.root[key]

class File(APIModel):
    """File version-1 API fields."""
    path: str | None = None
    size: int | None = None
    description: str | None = None

class IndicatorRowIdentity(APIModel):
    """IndicatorRowIdentity version-1 API fields."""
    id: str | None = None
    created: str | None = None
    modified: str | None = None
    digest: str | None = None
    original_type: str | None = Field(None, max_length=4000)
    to_ids: bool | None = None

class IndicatorSection(APIModel):
    """IndicatorSection version-1 API fields."""
    id: str = Field(..., pattern='^[A-Za-z0-9_-]{1,64}$')
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=4000)
    rows: list[list[str]] = Field(..., max_length=10000)
    row_meta: list[IndicatorSectionRowMetaItem] | None = None
    stix_meta: IndicatorRowIdentity | None = None

class Indicators(APIModel):
    """Indicators version-1 API fields."""
    columns: list[str] | None = None
    rows: list[list[str]] | None = Field(None, max_length=10000)
    sections: list[IndicatorSection] | None = None
    revision: int | None = None
    stix: IndicatorsStix | None = None
    types: list[dict[str, Any]] | None = None

class References(APIModel):
    """References version-1 API fields."""
    columns: list[str] | None = None
    rows: list[list[str]] | None = Field(None, max_length=10000)
    revision: int | None = None

class Template(APIModel):
    """Template version-1 API fields."""
    id: str | None = None
    name: str | None = None
    created: str | None = None
    selected: bool | None = None

class Image(APIModel):
    """Image version-1 API fields."""
    name: str | None = None
    section: str | None = None
    figure: int | None = None
    url: str | None = None
    markdown_url: str | None = None

class Job(APIModel):
    """Job version-1 API fields."""
    id: str | None = None
    status: Literal['queued', 'running', 'completed', 'failed'] | None = None
    messages: list[str] | None = None
    updated: int | None = None

class SyncCase(APIModel):
    """SyncCase version-1 API fields."""
    title: str | None = None
    owner_warning: str | None = None
    summary: Any | None = None
    suggestions: list[dict[str, Any]] | None = None
    classification: str | None = None
    reason: str | None = None
    case_uuid: str | None = None
    incoming_number: str | None = None
    destination_number: str | None = None
    incoming_revision: str | None = None
    local_revision: str | None = None
    fingerprint: str | None = None
    destination_id: int | None = None

class SyncOutcome(APIModel):
    """SyncOutcome version-1 API fields."""
    index: int | None = None
    case_uuid: str | None = None
    classification: str | None = None
    action: str | None = None
    reason: str | None = None
    decision: str | None = None
    ownership_decision: str | None = None
    recovery: str | None = None
    incoming_number: str | None = None
    destination_number: str | None = None
    previous_revision: str | None = None
    incoming_revision: str | None = None

class SyncResult(APIModel):
    """SyncResult version-1 API fields."""
    operation: str | None = None
    status: Literal['preview', 'complete'] | None = None
    cases: list[SyncCase] | None = None
    outcomes: list[SyncOutcome] | None = None

class TaskCollection(APIModel):
    """TaskCollection version-1 API fields."""
    id: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    revision: int | None = None
    tasks: list[TaskCollectionTasksItem] | None = None
    creator_uuid: str | None = None
    creator_name: str | None = None
    created: str | None = None
    updated: str | None = None
    task_count: int | None = None
    can_edit: bool | None = None
    can_delete: bool | None = None
    origin: Literal['core', 'custom'] | None = None
    read_only: bool | None = None

class ActorsListParams(APIModel):
    """ActorsListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None

class ActorsListResponse(APIModel):
    """ActorsListResponse version-1 API fields."""
    profiles: list[ActorsListResponseProfilesItem] | None = None
    total: int | None = None
    limit: int | None = None
    offset: int | None = None

class ActorsCreateRequest(APIModel):
    """ActorsCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class ActorsCreateResponse(APIModel):
    """ActorsCreateResponse version-1 API fields."""
    message: str | None = None

class ActorsGetParams(APIModel):
    """ActorsGetParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None

class ActorsGetResponse(APIModel):
    """ActorsGetResponse version-1 API fields."""
    profile: ActorsGetResponseProfile | None = None

class ActorsDeleteRequest(APIModel):
    """ActorsDeleteRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class ActorsDeleteResponse(APIModel):
    """ActorsDeleteResponse version-1 API fields."""
    message: str | None = None

class ActorsUpdateRequest(APIModel):
    """ActorsUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class ActorsUpdateResponse(APIModel):
    """ActorsUpdateResponse version-1 API fields."""
    message: str | None = None

class ActorsAddOsintRequest(APIModel):
    """ActorsAddOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsAddOsintResponse(APIModel):
    """ActorsAddOsintResponse version-1 API fields."""
    message: str | None = None

class ActorsDeleteOsintRequest(APIModel):
    """ActorsDeleteOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsDeleteOsintResponse(APIModel):
    """ActorsDeleteOsintResponse version-1 API fields."""
    message: str | None = None

class ActorsUpdateOsintRequest(APIModel):
    """ActorsUpdateOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsUpdateOsintResponse(APIModel):
    """ActorsUpdateOsintResponse version-1 API fields."""
    message: str | None = None

class ActorsUploadReportsRequest(APIModel):
    """ActorsUploadReportsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsUploadReportsResponse(APIModel):
    """ActorsUploadReportsResponse version-1 API fields."""
    message: str | None = None

class ActorsDeleteReportRequest(APIModel):
    """ActorsDeleteReportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsDeleteReportResponse(APIModel):
    """ActorsDeleteReportResponse version-1 API fields."""
    message: str | None = None

class ActorsUpdateReportRequest(APIModel):
    """ActorsUpdateReportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class ActorsUpdateReportResponse(APIModel):
    """ActorsUpdateReportResponse version-1 API fields."""
    message: str | None = None

class AuditExportCsvParams(APIModel):
    """AuditExportCsvParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    actor: str | None = None

class BackupsCreateJobRequest(APIModel):
    """BackupsCreateJobRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    kind: str | None = None
    complete: bool | None = None
    areas: list[str] | None = None
    passphrase: SecretStr | None = None
    choices: dict[str, Any] | None = None
    ack: str | None = None

class BackupsCreateJobResponse(APIModel):
    """BackupsCreateJobResponse version-1 API fields."""
    message: str | None = None

class BackupsJobResponse(APIModel):
    """BackupsJobResponse version-1 API fields."""
    message: str | None = None

class BackupsApplyRequest(APIModel):
    """BackupsApplyRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    kind: str | None = None
    complete: bool | None = None
    areas: list[str] | None = None
    passphrase: SecretStr | None = None
    choices: dict[str, Any] | None = None
    ack: str | None = None

class BackupsApplyResponse(APIModel):
    """BackupsApplyResponse version-1 API fields."""
    message: str | None = None

class BackupsPreviewRequest(APIModel):
    """BackupsPreviewRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    kind: str | None = None
    complete: bool | None = None
    areas: list[str] | None = None
    passphrase: SecretStr | None = None
    choices: dict[str, Any] | None = None
    ack: str | None = None

class BackupsPreviewResponse(APIModel):
    """BackupsPreviewResponse version-1 API fields."""
    message: str | None = None

class BackupsSyncApplyRequest(APIModel):
    """BackupsSyncApplyRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    pass

class BackupsImportCasesResponse(APIModel):
    """BackupsImportCasesResponse version-1 API fields."""
    operation: str | None = None
    cases: list[SyncCase] | None = None
    apply_url: str | None = None

class BackupsImportCasesRequest(APIModel):
    """BackupsImportCasesRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    pass

class BackupsImportRawResponse(APIModel):
    """BackupsImportRawResponse version-1 API fields."""
    operation: str | None = None
    cases: list[SyncCase] | None = None
    apply_url: str | None = None

class BackupsImportRawRequest(APIModel):
    """BackupsImportRawRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    pass

class CasesListParams(APIModel):
    """CasesListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None
    stage: int | None = None
    owner_id: int | None = None
    sort: Literal['newest', 'oldest', 'number', 'name'] | None = None

class CasesListResponse(APIModel):
    """CasesListResponse version-1 API fields."""
    cases: list[Case] | None = None
    limit: int | None = None
    offset: int | None = None
    total: int | None = None

class CasesCreateRequest(APIModel):
    """CasesCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    owner_id: int | None = None
    external_system: Literal['', 'Vortex', 'XSIAM', 'JIRA'] | None = None
    external_number: str | None = Field(None, max_length=200)

class CasesCreateResponse(APIModel):
    """CasesCreateResponse version-1 API fields."""
    case: Case | None = None

class CasesGetResponse(APIModel):
    """CasesGetResponse version-1 API fields."""
    case: CasesGetResponseCase | None = None

class CasesUpdateRequest(APIModel):
    """CasesUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    owner_id: int | None = None
    external_system: Literal['', 'Vortex', 'XSIAM', 'JIRA'] | None = None
    external_number: str | None = Field(None, max_length=200)

class CasesUpdateResponse(APIModel):
    """CasesUpdateResponse version-1 API fields."""
    case: Case | None = None

class PackagesExportRequest(APIModel):
    """PackagesExportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    archive_type: Literal['standard', 'raw'] | None = None
    include_samples: bool | None = None
    acknowledge: bool | None = None

class AssetsDeleteRequest(APIModel):
    """AssetsDeleteRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str = ...

class AssetsListParams(APIModel):
    """AssetsListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    category: Literal['reports', 'iocs', 'signatures', 'scripts', 'mappings', 'supporting', 'samples'] | None = None

class AssetsListResponse(APIModel):
    """AssetsListResponse version-1 API fields."""
    files: list[File] | None = None

class AssetsUploadRequest(APIModel):
    """AssetsUploadRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    category: Literal['reports', 'iocs', 'signatures', 'scripts', 'mappings', 'supporting', 'samples'] = ...
    description: str | None = None

class AssetsUploadResponse(APIModel):
    """AssetsUploadResponse version-1 API fields."""
    file: File | None = None

class NotesGetDraftResponse(APIModel):
    """NotesGetDraftResponse version-1 API fields."""
    draft: Draft | None = None

class NotesUpdateDraftRequest(APIModel):
    """NotesUpdateDraftRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=100000)

class NotesUpdateDraftResponse(APIModel):
    """NotesUpdateDraftResponse version-1 API fields."""
    draft: Draft | None = None

class IndicatorsUpdateRequest(APIModel):
    """IndicatorsUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int = ...
    columns: list[str] | None = None
    rows: list[list[str]] | None = Field(None, max_length=10000)
    sections: list[IndicatorSection] | None = None

class NotesListParams(APIModel):
    """NotesListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)

class NotesListResponse(APIModel):
    """NotesListResponse version-1 API fields."""
    notes: list[Note] | None = None
    limit: int | None = None
    offset: int | None = None
    total: int | None = None

class NotesCreateRequest(APIModel):
    """NotesCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    title: str | None = Field(None, max_length=200)
    body: str = Field(..., min_length=1, max_length=100000)
    include_export: bool | None = None

class NotesCreateResponse(APIModel):
    """NotesCreateResponse version-1 API fields."""
    note: Note | None = None

class NotesGetResponse(APIModel):
    """NotesGetResponse version-1 API fields."""
    note: Note | None = None

class NotesUpdateRequest(APIModel):
    """NotesUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, max_length=100000)
    include_export: bool | None = None

class NotesUpdateResponse(APIModel):
    """NotesUpdateResponse version-1 API fields."""
    note: Note | None = None

class PackagesReadinessResponse(APIModel):
    """PackagesReadinessResponse version-1 API fields."""
    readiness: Readiness | None = None

class PackagesSetReadinessRequest(APIModel):
    """PackagesSetReadinessRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    category: Literal['reports', 'iocs', 'signatures', 'scripts', 'mappings', 'supporting', 'samples'] = ...
    status: Literal['Pending', 'Populated', 'Not applicable'] = ...
    reason: str | None = None

class PackagesSetReadinessResponse(APIModel):
    """PackagesSetReadinessResponse version-1 API fields."""
    readiness: Readiness | None = None

class ReferencesUpdateRequest(APIModel):
    """ReferencesUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int = ...
    rows: list[list[str]] = Field(..., max_length=10000)

class CasesReopenResponse(APIModel):
    """CasesReopenResponse version-1 API fields."""
    case: Case | None = None

class ReportsGetResponse(APIModel):
    """ReportsGetResponse version-1 API fields."""
    sections: ReportsGetResponseSections | None = None
    mappings: ReportsGetResponseMappings | None = None
    report_path: str | None = None
    report_exists: bool | None = None

class ReportsUpdateRequest(APIModel):
    """ReportsUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    sections: ReportsUpdateRequestSections = ...

class ReportsUpdateResponse(APIModel):
    """ReportsUpdateResponse version-1 API fields."""
    sections: ReportsUpdateResponseSections | None = None

class ReportsDownloadParams(APIModel):
    """ReportsDownloadParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    format: Literal['docx', 'pdf'] | None = None

class ReportsUploadRequest(APIModel):
    """ReportsUploadRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    backup: Literal['0', '1'] | None = None
    generate_pdf: Literal['0', '1'] | None = None

class ReportsUploadResponse(APIModel):
    """ReportsUploadResponse version-1 API fields."""
    saved: bool | None = None
    report_exists: bool | None = None
    report_path: str | None = None
    report_files: list[File] | None = None

class ReportsGenerateRequest(APIModel):
    """ReportsGenerateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    generation_mode: Literal['manual'] | None = None
    previous: Literal['backup', 'overwrite'] | None = None
    generate_pdf: Any | None = None
    sections: ReportsGenerateRequestSections | None = None
    executive_summary: str | None = Field(None, max_length=100000)
    key_findings: str | None = Field(None, max_length=100000)
    detection_opportunities: str | None = Field(None, max_length=100000)
    reverse_engineering_findings: str | None = Field(None, max_length=100000)

class ReportsGenerateResponse(APIModel):
    """ReportsGenerateResponse version-1 API fields."""
    job_id: str | None = None

class ReportsListImagesResponse(APIModel):
    """ReportsListImagesResponse version-1 API fields."""
    images: list[Image] | None = None

class ReportsUploadImageRequest(APIModel):
    """ReportsUploadImageRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    section: str = ...

class ReportsJobResponse(APIModel):
    """ReportsJobResponse version-1 API fields."""
    job: Job | None = None

class ReportsGetMappingsResponse(APIModel):
    """ReportsGetMappingsResponse version-1 API fields."""
    mappings: ReportsGetMappingsResponseMappings | None = None

class ReportsUpdateMappingsRequest(APIModel):
    """ReportsUpdateMappingsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    mappings: ReportsUpdateMappingsRequestMappings = ...

class ReportsUpdateMappingsResponse(APIModel):
    """ReportsUpdateMappingsResponse version-1 API fields."""
    mappings: ReportsUpdateMappingsResponseMappings | None = None

class CasesAdvanceRequest(APIModel):
    """CasesAdvanceRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    expected: int = Field(..., ge=0, le=3)
    outcome: Literal['Done', 'No applicable work', 'Deferred'] | None = None
    reason: str | None = None

class CasesAdvanceResponse(APIModel):
    """CasesAdvanceResponse version-1 API fields."""
    case: Case | None = None

class TasksListParams(APIModel):
    """TasksListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)

class TasksListResponse(APIModel):
    """TasksListResponse version-1 API fields."""
    tasks: list[Task] | None = None
    limit: int | None = None
    offset: int | None = None
    total: int | None = None

class TasksCreateRequest(APIModel):
    """TasksCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    title: str = Field(..., min_length=1, max_length=200)
    body: str | None = Field(None, max_length=20000)
    description: str | None = Field(None, max_length=20000)
    priority: Literal['Low', 'Normal', 'High', 'Critical'] | None = None

class TasksCreateResponse(APIModel):
    """TasksCreateResponse version-1 API fields."""
    task: Task | None = None

class TasksGetResponse(APIModel):
    """TasksGetResponse version-1 API fields."""
    task: Task | None = None

class TasksUpdateRequest(APIModel):
    """TasksUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    title: str | None = Field(None, min_length=1, max_length=200)
    body: str | None = Field(None, max_length=20000)
    description: str | None = Field(None, max_length=20000)
    priority: Literal['Low', 'Normal', 'High', 'Critical'] | None = None
    state: Literal['Not Started', 'In Progress', 'Completed'] | None = None

class TasksUpdateResponse(APIModel):
    """TasksUpdateResponse version-1 API fields."""
    task: Task | None = None

class IndicatorsImportRowsRequest(APIModel):
    """IndicatorsImportRowsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int | None = None
    section_id: str | None = None
    format: str | None = None
    csv: str | None = None
    stix: str | None = None
    accepted_rows: list[list[str]] | None = None
    accepted_original_types: list[str] | None = None
    accepted_intents: list[bool] | None = None
    skip_duplicates: bool | None = None

class IndicatorsImportRowsResponse(APIModel):
    """IndicatorsImportRowsResponse version-1 API fields."""
    message: str | None = None

class IndicatorsPreviewImportRequest(APIModel):
    """IndicatorsPreviewImportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int | None = None
    section_id: str | None = None
    format: str | None = None
    csv: str | None = None
    stix: str | None = None
    accepted_rows: list[list[str]] | None = None
    accepted_original_types: list[str] | None = None
    accepted_intents: list[bool] | None = None
    skip_duplicates: bool | None = None

class IndicatorsPreviewImportResponse(APIModel):
    """IndicatorsPreviewImportResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortOpenParams(APIModel):
    """ToolsSnortOpenParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsSnortOpenResponse(APIModel):
    """ToolsSnortOpenResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortSaveRequest(APIModel):
    """ToolsSnortSaveRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortSaveParams(APIModel):
    """ToolsSnortSaveParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsSnortSaveResponse(APIModel):
    """ToolsSnortSaveResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortInventoryParams(APIModel):
    """ToolsSnortInventoryParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsSnortInventoryResponse(APIModel):
    """ToolsSnortInventoryResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortNormalizeRequest(APIModel):
    """ToolsSnortNormalizeRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortNormalizeParams(APIModel):
    """ToolsSnortNormalizeParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsSnortNormalizeResponse(APIModel):
    """ToolsSnortNormalizeResponse version-1 API fields."""
    message: str | None = None

class TagsForCaseResponse(APIModel):
    """TagsForCaseResponse version-1 API fields."""
    message: str | None = None

class TagsAssignResponse(APIModel):
    """TagsAssignResponse version-1 API fields."""
    message: str | None = None

class TagsRemoveResponse(APIModel):
    """TagsRemoveResponse version-1 API fields."""
    message: str | None = None

class TaskCollectionsFromTasksRequest(APIModel):
    """TaskCollectionsFromTasksRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    task_ids: list[int] = ...
    collection_id: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    revision: int | None = None
    tasks: list[TaskCollectionsFromTasksRequestTasksItem] | None = None

class TaskCollectionsFromTasksResponse(APIModel):
    """TaskCollectionsFromTasksResponse version-1 API fields."""
    collection: TaskCollection | None = None

class TaskCollectionsApplyRequest(APIModel):
    """TaskCollectionsApplyRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int = ...
    template_ids: list[str] = ...
    mode: Literal['missing', 'copy'] | None = None
    request_key: str = ...

class TaskCollectionsApplyResponse(APIModel):
    """TaskCollectionsApplyResponse version-1 API fields."""
    group_id: str | None = None
    task_ids: list[int] | None = None
    count: int | None = None
    source_collection_id: str | None = None
    source_revision: int | None = None
    source_fingerprint: str | None = None
    source_tasks: list[TaskCollectionsApplyResponseSourceTasksItem] | None = None
    added: str | None = None
    replayed: bool | None = None

class TaskCollectionsCaseGroupsResponse(APIModel):
    """TaskCollectionsCaseGroupsResponse version-1 API fields."""
    tasks: list[Task] | None = None
    groups: list[TaskCollectionsCaseGroupsResponseGroupsItem] | None = None
    applications: list[TaskCollectionsCaseGroupsResponseApplicationsItem] | None = None
    editable: bool | None = None

class TaskCollectionsRemoveGroupRequest(APIModel):
    """TaskCollectionsRemoveGroupRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    confirm: bool = ...

class TaskCollectionsRemoveGroupResponse(APIModel):
    """TaskCollectionsRemoveGroupResponse version-1 API fields."""
    ok: bool | None = None

class TaskCollectionsReorderRequest(APIModel):
    """TaskCollectionsReorderRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    group_id: str | None = None
    task_ids: list[int] = ...

class TaskCollectionsReorderResponse(APIModel):
    """TaskCollectionsReorderResponse version-1 API fields."""
    ok: bool | None = None

class ToolsYaraOpenParams(APIModel):
    """ToolsYaraOpenParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsYaraOpenResponse(APIModel):
    """ToolsYaraOpenResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraSaveRequest(APIModel):
    """ToolsYaraSaveRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsYaraSaveParams(APIModel):
    """ToolsYaraSaveParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsYaraSaveResponse(APIModel):
    """ToolsYaraSaveResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraFilesParams(APIModel):
    """ToolsYaraFilesParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None

class ToolsYaraFilesResponse(APIModel):
    """ToolsYaraFilesResponse version-1 API fields."""
    message: str | None = None

class CoverageGetParams(APIModel):
    """CoverageGetParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    scope: str | None = None
    ids: str | None = None
    page: str | None = None
    gap_page: str | None = None
    q: str | None = None
    sort: str | None = None
    missing: str | None = None

class CoverageGetResponse(APIModel):
    """CoverageGetResponse version-1 API fields."""
    rows: list[CoverageGetResponseRowsItem] | None = None
    total: int | None = None
    scope_total: int | None = None
    page: int | None = None
    pages: int | None = None
    gaps: list[CoverageGetResponseGapsItem] | None = None
    gap_total: int | None = None
    gap_page: int | None = None
    gap_pages: int | None = None
    limited: bool | None = None
    note: str | None = None

class ExplorerContentsParams(APIModel):
    """ExplorerContentsParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None
    page: int | None = None

class ExplorerContentsResponse(APIModel):
    """ExplorerContentsResponse version-1 API fields."""
    message: str | None = None

class ExplorerCategoryParams(APIModel):
    """ExplorerCategoryParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None
    page: int | None = None

class ExplorerCategoryResponse(APIModel):
    """ExplorerCategoryResponse version-1 API fields."""
    message: str | None = None

class ExplorerDownloadParams(APIModel):
    """ExplorerDownloadParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    path: str | None = None
    page: int | None = None

class ExplorerConnectionObjectsParams(APIModel):
    """ExplorerConnectionObjectsParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    scope: str | None = None
    q: str | None = None
    type: list[str] | None = None

class ExplorerConnectionObjectsResponse(APIModel):
    """ExplorerConnectionObjectsResponse version-1 API fields."""
    message: str | None = None

class ExplorerConnectionsParams(APIModel):
    """ExplorerConnectionsParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    scope: str | None = None
    source: str | None = None
    target: str | None = None
    ids: str | None = None
    q: str | None = None
    depth: str | None = None
    shared: str | None = None
    type: list[str] | None = None
    indicator_type: list[str] | None = None
    minimum: str | None = None

class ExplorerConnectionsResponse(APIModel):
    """ExplorerConnectionsResponse version-1 API fields."""
    message: str | None = None

class ExplorerEvidenceParams(APIModel):
    """ExplorerEvidenceParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source: str | None = None
    target: str | None = None
    shared: str | None = None
    indicator_type: list[str] | None = None
    minimum: str | None = None

class ExplorerEvidenceResponse(APIModel):
    """ExplorerEvidenceResponse version-1 API fields."""
    message: str | None = None

class ExplorerGraphParams(APIModel):
    """ExplorerGraphParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    q: str | None = None
    type: list[str] | None = None

class ExplorerGraphResponse(APIModel):
    """ExplorerGraphResponse version-1 API fields."""
    message: str | None = None

class ExplorerSharedIndicatorsParams(APIModel):
    """ExplorerSharedIndicatorsParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    q: str | None = None
    type: list[str] | None = None
    indicator_type: list[str] | None = None
    minimum: str | None = None

class ExplorerSharedIndicatorsResponse(APIModel):
    """ExplorerSharedIndicatorsResponse version-1 API fields."""
    message: str | None = None

class ExplorerListViewsResponse(APIModel):
    """ExplorerListViewsResponse version-1 API fields."""
    message: str | None = None

class ExplorerCreateViewRequest(APIModel):
    """ExplorerCreateViewRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    description: str | None = None
    configuration: dict[str, Any] | None = None

class ExplorerCreateViewResponse(APIModel):
    """ExplorerCreateViewResponse version-1 API fields."""
    message: str | None = None

class ExplorerGetViewResponse(APIModel):
    """ExplorerGetViewResponse version-1 API fields."""
    message: str | None = None

class ExplorerDeleteViewRequest(APIModel):
    """ExplorerDeleteViewRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    description: str | None = None
    configuration: dict[str, Any] | None = None

class ExplorerDeleteViewResponse(APIModel):
    """ExplorerDeleteViewResponse version-1 API fields."""
    message: str | None = None

class ExplorerUpdateViewRequest(APIModel):
    """ExplorerUpdateViewRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    description: str | None = None
    configuration: dict[str, Any] | None = None

class ExplorerUpdateViewResponse(APIModel):
    """ExplorerUpdateViewResponse version-1 API fields."""
    message: str | None = None

class FamiliesListParams(APIModel):
    """FamiliesListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None

class FamiliesListResponse(APIModel):
    """FamiliesListResponse version-1 API fields."""
    profiles: list[FamiliesListResponseProfilesItem] | None = None
    total: int | None = None
    limit: int | None = None
    offset: int | None = None

class FamiliesCreateRequest(APIModel):
    """FamiliesCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class FamiliesCreateResponse(APIModel):
    """FamiliesCreateResponse version-1 API fields."""
    message: str | None = None

class FamiliesGetParams(APIModel):
    """FamiliesGetParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None

class FamiliesGetResponse(APIModel):
    """FamiliesGetResponse version-1 API fields."""
    profile: FamiliesGetResponseProfile | None = None

class FamiliesDeleteRequest(APIModel):
    """FamiliesDeleteRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class FamiliesDeleteResponse(APIModel):
    """FamiliesDeleteResponse version-1 API fields."""
    message: str | None = None

class FamiliesUpdateRequest(APIModel):
    """FamiliesUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    tag: str | None = None
    version: int | None = None
    aliases: list[str] | None = None
    aliases_present: bool | None = None
    known_families: list[str] | None = None
    known_actors: list[str] | None = None
    known_actors_present: bool | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    confirm_name: str | None = None

class FamiliesUpdateResponse(APIModel):
    """FamiliesUpdateResponse version-1 API fields."""
    message: str | None = None

class FamiliesAddOsintRequest(APIModel):
    """FamiliesAddOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesAddOsintResponse(APIModel):
    """FamiliesAddOsintResponse version-1 API fields."""
    message: str | None = None

class FamiliesDeleteOsintRequest(APIModel):
    """FamiliesDeleteOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesDeleteOsintResponse(APIModel):
    """FamiliesDeleteOsintResponse version-1 API fields."""
    message: str | None = None

class FamiliesUpdateOsintRequest(APIModel):
    """FamiliesUpdateOsintRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesUpdateOsintResponse(APIModel):
    """FamiliesUpdateOsintResponse version-1 API fields."""
    message: str | None = None

class FamiliesUploadReportsRequest(APIModel):
    """FamiliesUploadReportsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesUploadReportsResponse(APIModel):
    """FamiliesUploadReportsResponse version-1 API fields."""
    message: str | None = None

class FamiliesDeleteReportRequest(APIModel):
    """FamiliesDeleteReportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesDeleteReportResponse(APIModel):
    """FamiliesDeleteReportResponse version-1 API fields."""
    message: str | None = None

class FamiliesUpdateReportRequest(APIModel):
    """FamiliesUpdateReportRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    version: int | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    position: int | None = None
    confirm: bool | None = None

class FamiliesUpdateReportResponse(APIModel):
    """FamiliesUpdateReportResponse version-1 API fields."""
    message: str | None = None

class AuthenticationMeResponse(APIModel):
    """AuthenticationMeResponse version-1 API fields."""
    user: User | None = None
    permissions: list[str] | None = None

class MetricsGetResponse(APIModel):
    """MetricsGetResponse version-1 API fields."""
    users: list[MetricsGetResponseUsersItem] | None = None
    stages: list[MetricsGetResponseStagesItem] | None = None
    completed: list[MetricsGetResponseCompletedItem] | None = None

class RolesPermissionsResponse(APIModel):
    """RolesPermissionsResponse version-1 API fields."""
    permissions: list[RolesPermissionsResponsePermissionsItem] | None = None

class PluginsCapabilitiesResponse(APIModel):
    """PluginsCapabilitiesResponse version-1 API fields."""
    tools: list[dict[str, Any]] | None = None
    plugin_registry: bool | None = None
    description: str | None = None
    plugins: list[PluginsCapabilitiesResponsePluginsItem] | None = None

class RolesListResponse(APIModel):
    """RolesListResponse version-1 API fields."""
    roles: list[Role] | None = None

class RolesCreateRequest(APIModel):
    """RolesCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = Field(..., pattern='^[a-z][a-z0-9_-]{2,31}$')
    description: str | None = Field(None, max_length=300)
    permissions: list[str] | None = None

class RolesUpdateRequest(APIModel):
    """RolesUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    description: str | None = Field(None, max_length=300)
    permissions: list[str] | None = None

class SearchQueryParams(APIModel):
    """SearchQueryParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    q: str | None = None
    kind: str | None = None
    source: str | None = None
    stage: str | None = None
    page: str | None = None

class SearchQueryResponse(APIModel):
    """SearchQueryResponse version-1 API fields."""
    message: str | None = None

class SettingsGetResponse(APIModel):
    """SettingsGetResponse version-1 API fields."""
    settings: SettingsGetResponseSettings | None = None

class SettingsUpdateRequest(APIModel):
    """SettingsUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    sample_archive_password: SecretStr = Field(..., min_length=1, max_length=256)

class SettingsUpdateResponse(APIModel):
    """SettingsUpdateResponse version-1 API fields."""
    settings: SettingsUpdateResponseSettings | None = None

class TagsListParams(APIModel):
    """TagsListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    q: str | None = None

class TagsListResponse(APIModel):
    """TagsListResponse version-1 API fields."""
    message: str | None = None

class TagsCreateRequest(APIModel):
    """TagsCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = ...

class TagsCreateResponse(APIModel):
    """TagsCreateResponse version-1 API fields."""
    message: str | None = None

class TagsGetResponse(APIModel):
    """TagsGetResponse version-1 API fields."""
    tag: TagsGetResponseTag | None = None

class TagsDeleteRequest(APIModel):
    """TagsDeleteRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    destination: int | None = None
    confirm: bool | None = None

class TagsDeleteResponse(APIModel):
    """TagsDeleteResponse version-1 API fields."""
    message: str | None = None

class TagsMergeRequest(APIModel):
    """TagsMergeRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    destination: int | None = None
    confirm: bool | None = None

class TagsMergeResponse(APIModel):
    """TagsMergeResponse version-1 API fields."""
    message: str | None = None

class TagsRenameRequest(APIModel):
    """TagsRenameRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None
    destination: int | None = None
    confirm: bool | None = None

class TagsRenameResponse(APIModel):
    """TagsRenameResponse version-1 API fields."""
    message: str | None = None

class TaskCollectionsListParams(APIModel):
    """TaskCollectionsListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)
    q: str | None = None
    category: str | None = None
    origin: Literal['all', 'core', 'custom'] | None = None

class TaskCollectionsListResponse(APIModel):
    """TaskCollectionsListResponse version-1 API fields."""
    collections: list[TaskCollection] | None = None
    permissions: TaskCollectionsListResponsePermissions | None = None
    total: int | None = None
    limit: int | None = None
    offset: int | None = None

class TaskCollectionsCreateRequest(APIModel):
    """TaskCollectionsCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = ...
    description: str | None = None
    category: str | None = None
    revision: int | None = None
    tasks: list[TaskCollectionsCreateRequestTasksItem] = ...

class TaskCollectionsCreateResponse(APIModel):
    """TaskCollectionsCreateResponse version-1 API fields."""
    collection: TaskCollection | None = None

class TaskCollectionsDeleteRequest(APIModel):
    """TaskCollectionsDeleteRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    revision: int = ...

class TaskCollectionsGetResponse(APIModel):
    """TaskCollectionsGetResponse version-1 API fields."""
    collection: TaskCollection | None = None

class TaskCollectionsUpdateRequest(APIModel):
    """TaskCollectionsUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = ...
    description: str | None = None
    category: str | None = None
    revision: int = ...
    tasks: list[TaskCollectionsUpdateRequestTasksItem] = ...

class TaskCollectionsUpdateResponse(APIModel):
    """TaskCollectionsUpdateResponse version-1 API fields."""
    collection: TaskCollection | None = None

class TaskCollectionsDuplicateRequest(APIModel):
    """TaskCollectionsDuplicateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str | None = None

class TaskCollectionsDuplicateResponse(APIModel):
    """TaskCollectionsDuplicateResponse version-1 API fields."""
    collection: TaskCollection | None = None

class TemplatesListResponse(APIModel):
    """TemplatesListResponse version-1 API fields."""
    templates: list[Template] | None = None

class TemplatesUploadResponse(APIModel):
    """TemplatesUploadResponse version-1 API fields."""
    message: str | None = None
    templates: list[Template] | None = None

class TemplatesUploadRequest(APIModel):
    """TemplatesUploadRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    pass

class TemplatesSelectRequest(APIModel):
    """TemplatesSelectRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    template_id: str | None = None

class TemplatesSelectResponse(APIModel):
    """TemplatesSelectResponse version-1 API fields."""
    templates: list[Template] | None = None

class AuthenticationListTokensResponse(APIModel):
    """AuthenticationListTokensResponse version-1 API fields."""
    tokens: list[Token] | None = None

class AuthenticationCreateTokenRequest(APIModel):
    """AuthenticationCreateTokenRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    name: str = Field(..., min_length=1, max_length=80)
    expires_in_days: int | None = Field(None, ge=1, le=3650)

class AuthenticationCreateTokenResponse(APIModel):
    """AuthenticationCreateTokenResponse version-1 API fields."""
    id: int | None = None
    name: str | None = None
    token: SecretStr | None = None
    expires: str | None = None

class ToolsListResponse(APIModel):
    """ToolsListResponse version-1 API fields."""
    tools: list[ToolsListResponseToolsItem] | None = None
    plugin_registry: bool | None = None
    description: str | None = None

class ToolsSnortDownloadRequest(APIModel):
    """ToolsSnortDownloadRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortDraftRequest(APIModel):
    """ToolsSnortDraftRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortDraftResponse(APIModel):
    """ToolsSnortDraftResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortJobsRequest(APIModel):
    """ToolsSnortJobsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortJobsResponse(APIModel):
    """ToolsSnortJobsResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortJobResponse(APIModel):
    """ToolsSnortJobResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortCancelRequest(APIModel):
    """ToolsSnortCancelRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsSnortCancelResponse(APIModel):
    """ToolsSnortCancelResponse version-1 API fields."""
    message: str | None = None

class ToolsSnortStateResponse(APIModel):
    """ToolsSnortStateResponse version-1 API fields."""
    message: str | None = None

class ToolsProcessTextRequest(APIModel):
    """ToolsProcessTextRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    operation: str = ...
    text: str = ...

class ToolsProcessTextResponse(APIModel):
    """ToolsProcessTextResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraDownloadRequest(APIModel):
    """ToolsYaraDownloadRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsYaraDraftRequest(APIModel):
    """ToolsYaraDraftRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsYaraDraftResponse(APIModel):
    """ToolsYaraDraftResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraJobsRequest(APIModel):
    """ToolsYaraJobsRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsYaraJobsResponse(APIModel):
    """ToolsYaraJobsResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraJobResponse(APIModel):
    """ToolsYaraJobResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraCancelRequest(APIModel):
    """ToolsYaraCancelRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    source_json: str | None = None
    filename: str | None = None
    case_id: int | None = None
    name: str | None = None
    kind: str | None = None
    version: str | None = None
    context: dict[str, Any] | None = None
    operation: str | None = None
    start: int | None = None
    end: int | None = None
    origin_path: str | None = None
    origin_cid: int | None = None
    positive_path: str | None = None
    baseline_path: str | None = None

class ToolsYaraCancelResponse(APIModel):
    """ToolsYaraCancelResponse version-1 API fields."""
    message: str | None = None

class ToolsYaraStateResponse(APIModel):
    """ToolsYaraStateResponse version-1 API fields."""
    message: str | None = None

class UsersListParams(APIModel):
    """UsersListParams version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    limit: int | None = Field(None, ge=1, le=500)
    offset: int | None = Field(None, ge=0)

class UsersListResponse(APIModel):
    """UsersListResponse version-1 API fields."""
    users: list[User] | None = None
    limit: int | None = None
    offset: int | None = None
    total: int | None = None

class UsersCreateRequest(APIModel):
    """UsersCreateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    username: str = Field(..., pattern='^[A-Za-z0-9_.-]{3,64}$')
    password: SecretStr = Field(..., min_length=12)
    role: str | None = None

class UsersCreateResponse(APIModel):
    """UsersCreateResponse version-1 API fields."""
    user: User | None = None

class UsersGetResponse(APIModel):
    """UsersGetResponse version-1 API fields."""
    user: User | None = None

class UsersUpdateRequest(APIModel):
    """UsersUpdateRequest version-1 API fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, hide_input_in_errors=True)
    role: str | None = None
    active: bool | None = None

class UsersUpdateResponse(APIModel):
    """UsersUpdateResponse version-1 API fields."""
    user: User | None = None

class ReadinessValueItem(APIModel):
    """ReadinessValueItem version-1 API fields."""
    category: Literal['reports', 'iocs', 'signatures', 'scripts', 'mappings', 'supporting', 'samples'] | None = None
    label: str | None = None
    status: str | None = None
    reason: str | None = None
    count: int | None = None

class IndicatorSectionRowMetaItem(APIModel):
    """IndicatorSectionRowMetaItem version-1 API fields."""
    id: str | None = None
    created: str | None = None
    modified: str | None = None
    digest: str | None = None
    original_type: str | None = Field(None, max_length=4000)
    to_ids: bool | None = None

class IndicatorsStix(APIModel):
    """IndicatorsStix version-1 API fields."""
    available: bool | None = None
    issues: list[IndicatorsStixIssuesItem] | None = None
    notices: list[IndicatorsStixNoticesItem] | None = None

class TaskCollectionTasksItem(APIModel):
    """TaskCollectionTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class ActorsListResponseProfilesItem(APIModel):
    """ActorsListResponseProfilesItem version-1 API fields."""
    id: str | None = None
    name: str | None = None
    tag: str | None = None
    tag_id: int | None = None
    version: int | None = None
    aliases: list[str] | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    associations: list[dict[str, Any]] | None = None
    osint: list[ActorsListResponseProfilesItemOsintItem] | None = None
    reports: list[ActorsListResponseProfilesItemReportsItem] | None = None

class ActorsGetResponseProfile(APIModel):
    """ActorsGetResponseProfile version-1 API fields."""
    id: str | None = None
    name: str | None = None
    tag: str | None = None
    tag_id: int | None = None
    version: int | None = None
    aliases: list[str] | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    associations: list[dict[str, Any]] | None = None
    osint: list[ActorsGetResponseProfileOsintItem] | None = None
    reports: list[ActorsGetResponseProfileReportsItem] | None = None

class CasesGetResponseCase(APIModel):
    """CasesGetResponseCase version-1 API fields."""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=20000)
    owner_id: int | None = None
    external_system: Literal['', 'Vortex', 'XSIAM', 'JIRA'] | None = None
    external_number: str | None = Field(None, max_length=200)
    id: int | None = None
    number: str | None = None
    stage: int | None = Field(None, ge=0, le=3)
    stage_name: str | None = None
    created: str | None = None
    report_path: str | None = None
    owner_name: str | None = None
    creator_name: str | None = None
    creator_id: int | None = None
    owner_active: bool | None = None
    readiness: Readiness | None = None
    history: list[CasesGetResponseCaseHistoryItem] | None = None
    deferred: list[CasesGetResponseCaseDeferredItem] | None = None

class ReportsGetResponseSections(APIModel):
    """ReportsGetResponseSections version-1 API fields."""
    executive_summary: str | None = Field(None, max_length=100000)
    key_findings: str | None = Field(None, max_length=100000)
    detection_opportunities: str | None = Field(None, max_length=100000)
    reverse_engineering_findings: str | None = Field(None, max_length=100000)
    mitre_attack_mapping: str | None = Field(None, max_length=100000)
    mitre_mbc_mapping: str | None = Field(None, max_length=100000)
    indicators_of_compromise: str | None = Field(None, max_length=100000)
    appendices: str | None = Field(None, max_length=100000)

class ReportsGetResponseMappings(APIModel):
    """ReportsGetResponseMappings version-1 API fields."""
    attack: str | None = Field(None, max_length=100000)
    mbc: str | None = Field(None, max_length=100000)

class ReportsUpdateRequestSections(APIModel):
    """ReportsUpdateRequestSections version-1 API fields."""
    executive_summary: str | None = Field(None, max_length=100000)
    key_findings: str | None = Field(None, max_length=100000)
    detection_opportunities: str | None = Field(None, max_length=100000)
    reverse_engineering_findings: str | None = Field(None, max_length=100000)
    mitre_attack_mapping: str | None = Field(None, max_length=100000)
    mitre_mbc_mapping: str | None = Field(None, max_length=100000)
    indicators_of_compromise: str | None = Field(None, max_length=100000)
    appendices: str | None = Field(None, max_length=100000)

class ReportsUpdateResponseSections(APIModel):
    """ReportsUpdateResponseSections version-1 API fields."""
    executive_summary: str | None = Field(None, max_length=100000)
    key_findings: str | None = Field(None, max_length=100000)
    detection_opportunities: str | None = Field(None, max_length=100000)
    reverse_engineering_findings: str | None = Field(None, max_length=100000)
    mitre_attack_mapping: str | None = Field(None, max_length=100000)
    mitre_mbc_mapping: str | None = Field(None, max_length=100000)
    indicators_of_compromise: str | None = Field(None, max_length=100000)
    appendices: str | None = Field(None, max_length=100000)

class ReportsGenerateRequestSections(APIModel):
    """ReportsGenerateRequestSections version-1 API fields."""
    executive_summary: str | None = Field(None, max_length=100000)
    key_findings: str | None = Field(None, max_length=100000)
    detection_opportunities: str | None = Field(None, max_length=100000)
    reverse_engineering_findings: str | None = Field(None, max_length=100000)
    mitre_attack_mapping: str | None = Field(None, max_length=100000)
    mitre_mbc_mapping: str | None = Field(None, max_length=100000)
    indicators_of_compromise: str | None = Field(None, max_length=100000)
    appendices: str | None = Field(None, max_length=100000)

class ReportsGetMappingsResponseMappings(APIModel):
    """ReportsGetMappingsResponseMappings version-1 API fields."""
    attack: str | None = Field(None, max_length=100000)
    mbc: str | None = Field(None, max_length=100000)

class ReportsUpdateMappingsRequestMappings(APIModel):
    """ReportsUpdateMappingsRequestMappings version-1 API fields."""
    attack: str | None = Field(None, max_length=100000)
    mbc: str | None = Field(None, max_length=100000)

class ReportsUpdateMappingsResponseMappings(APIModel):
    """ReportsUpdateMappingsResponseMappings version-1 API fields."""
    attack: str | None = Field(None, max_length=100000)
    mbc: str | None = Field(None, max_length=100000)

class TaskCollectionsFromTasksRequestTasksItem(APIModel):
    """TaskCollectionsFromTasksRequestTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class TaskCollectionsApplyResponseSourceTasksItem(APIModel):
    """TaskCollectionsApplyResponseSourceTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class TaskCollectionsCaseGroupsResponseGroupsItem(APIModel):
    """TaskCollectionsCaseGroupsResponseGroupsItem version-1 API fields."""
    id: str | None = None
    case_id: int | None = None
    name: str | None = None
    source_collection_id: str | None = None
    source_revision: int | None = None
    added: str | None = None
    position: int | None = None
    source_fingerprint: str | None = None
    source_tasks: list[TaskCollectionsCaseGroupsResponseGroupsItemSourceTasksItem] | None = None

class TaskCollectionsCaseGroupsResponseApplicationsItem(APIModel):
    """TaskCollectionsCaseGroupsResponseApplicationsItem version-1 API fields."""
    source_collection_id: str | None = None
    template_ids: list[str] | None = None
    added: str | None = None

class CoverageGetResponseRowsItem(APIModel):
    """CoverageGetResponseRowsItem version-1 API fields."""
    id: str | None = None
    number: str | None = None
    title: str | None = None
    url: str | None = None
    missing: int | None = None
    indicators: CoverageGetResponseRowsItemIndicators | None = None
    attack: CoverageGetResponseRowsItemAttack | None = None
    mbc: CoverageGetResponseRowsItemMbc | None = None
    report: CoverageGetResponseRowsItemReport | None = None
    package: CoverageGetResponseRowsItemPackage | None = None

class CoverageGetResponseGapsItem(APIModel):
    """CoverageGetResponseGapsItem version-1 API fields."""
    id: str | None = None
    name: str | None = None
    kind: str | None = None
    suggestion: str | None = None
    explanation: str | None = None
    supports: list[CoverageGetResponseGapsItemSupportsItem] | None = None
    case_count: int | None = None
    action: CoverageGetResponseGapsItemAction | None = None

class FamiliesListResponseProfilesItem(APIModel):
    """FamiliesListResponseProfilesItem version-1 API fields."""
    id: str | None = None
    name: str | None = None
    tag: str | None = None
    tag_id: int | None = None
    version: int | None = None
    aliases: list[str] | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    associations: list[dict[str, Any]] | None = None
    osint: list[FamiliesListResponseProfilesItemOsintItem] | None = None
    reports: list[FamiliesListResponseProfilesItemReportsItem] | None = None

class FamiliesGetResponseProfile(APIModel):
    """FamiliesGetResponseProfile version-1 API fields."""
    id: str | None = None
    name: str | None = None
    tag: str | None = None
    tag_id: int | None = None
    version: int | None = None
    aliases: list[str] | None = None
    short_description: str | None = None
    long_description: str | None = None
    attribution_notes: str | None = None
    associations: list[dict[str, Any]] | None = None
    osint: list[FamiliesGetResponseProfileOsintItem] | None = None
    reports: list[FamiliesGetResponseProfileReportsItem] | None = None

class MetricsGetResponseUsersItem(APIModel):
    """MetricsGetResponseUsersItem version-1 API fields."""
    id: int | None = None
    username: str | None = None
    active: int | None = None
    created_count: int | None = None
    assigned_count: int | None = None
    progress_count: int | None = None
    completed_count: int | None = None

class MetricsGetResponseStagesItem(APIModel):
    """MetricsGetResponseStagesItem version-1 API fields."""
    label: str | None = None
    value: int | None = None

class MetricsGetResponseCompletedItem(APIModel):
    """MetricsGetResponseCompletedItem version-1 API fields."""
    label: str | None = None
    value: int | None = None

class RolesPermissionsResponsePermissionsItem(APIModel):
    """RolesPermissionsResponsePermissionsItem version-1 API fields."""
    name: str | None = None
    description: str | None = None

class PluginsCapabilitiesResponsePluginsItem(APIModel):
    """PluginsCapabilitiesResponsePluginsItem version-1 API fields."""
    id: str | None = None
    name: str | None = None
    development: str | None = None
    enabled: int | None = None
    published_version: str | None = None

class SettingsGetResponseSettings(APIModel):
    """SettingsGetResponseSettings version-1 API fields."""
    sample_archive_password: SettingsGetResponseSettingsSampleArchivePassword | None = None

class SettingsUpdateResponseSettings(APIModel):
    """SettingsUpdateResponseSettings version-1 API fields."""
    sample_archive_password: SettingsUpdateResponseSettingsSampleArchivePassword | None = None

class TagsGetResponseTag(APIModel):
    """TagsGetResponseTag version-1 API fields."""
    id: int | None = None
    name: str | None = None
    created_at: str | None = None

class TaskCollectionsListResponsePermissions(APIModel):
    """TaskCollectionsListResponsePermissions version-1 API fields."""
    create: bool | None = None
    update: bool | None = None
    delete: bool | None = None

class TaskCollectionsCreateRequestTasksItem(APIModel):
    """TaskCollectionsCreateRequestTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class TaskCollectionsUpdateRequestTasksItem(APIModel):
    """TaskCollectionsUpdateRequestTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class ToolsListResponseToolsItem(APIModel):
    """ToolsListResponseToolsItem version-1 API fields."""
    id: str | None = None
    name: str | None = None
    description: str | None = None
    type: str | None = None
    permission: str | None = None
    enabled: bool | None = None

class IndicatorsStixIssuesItem(APIModel):
    """IndicatorsStixIssuesItem version-1 API fields."""
    section_id: str | None = None
    section: str | None = None
    row: int | None = None
    reason: str | None = None

class IndicatorsStixNoticesItem(APIModel):
    """IndicatorsStixNoticesItem version-1 API fields."""
    section_id: str | None = None
    row: int | None = None
    message: str | None = None
    to_ids: bool | None = None

class ActorsListResponseProfilesItemOsintItem(APIModel):
    """ActorsListResponseProfilesItemOsintItem version-1 API fields."""
    id: str | None = None
    title: str | None = None
    url: str | None = None
    position: int | None = None

class ActorsListResponseProfilesItemReportsItem(APIModel):
    """ActorsListResponseProfilesItemReportsItem version-1 API fields."""
    id: str | None = None
    original_filename: str | None = None
    title: str | None = None
    description: str | None = None
    sha256: str | None = None
    size: int | None = None
    uploaded_at: str | None = None

class ActorsGetResponseProfileOsintItem(APIModel):
    """ActorsGetResponseProfileOsintItem version-1 API fields."""
    id: str | None = None
    title: str | None = None
    url: str | None = None
    position: int | None = None

class ActorsGetResponseProfileReportsItem(APIModel):
    """ActorsGetResponseProfileReportsItem version-1 API fields."""
    id: str | None = None
    original_filename: str | None = None
    title: str | None = None
    description: str | None = None
    sha256: str | None = None
    size: int | None = None
    uploaded_at: str | None = None

class CasesGetResponseCaseHistoryItem(APIModel):
    """CasesGetResponseCaseHistoryItem version-1 API fields."""
    stage: int | None = None
    author: str | None = None
    created: str | None = None
    outcome: str | None = None
    reason: str | None = None

class CasesGetResponseCaseDeferredItem(APIModel):
    """CasesGetResponseCaseDeferredItem version-1 API fields."""
    stage: int | None = None
    reason: str | None = None
    resolved: int | None = None

class TaskCollectionsCaseGroupsResponseGroupsItemSourceTasksItem(APIModel):
    """TaskCollectionsCaseGroupsResponseGroupsItemSourceTasksItem version-1 API fields."""
    id: str | None = None
    name: str = ...
    description: str | None = None

class CoverageGetResponseRowsItemIndicators(APIModel):
    """CoverageGetResponseRowsItemIndicators version-1 API fields."""
    state: Literal['present', 'missing', 'unavailable', 'not-applicable'] | None = None
    label: str | None = None
    explanation: str | None = None
    count: int | None = None
    url: str | None = None

class CoverageGetResponseRowsItemAttack(APIModel):
    """CoverageGetResponseRowsItemAttack version-1 API fields."""
    state: Literal['present', 'missing', 'unavailable', 'not-applicable'] | None = None
    label: str | None = None
    explanation: str | None = None
    count: int | None = None
    url: str | None = None

class CoverageGetResponseRowsItemMbc(APIModel):
    """CoverageGetResponseRowsItemMbc version-1 API fields."""
    state: Literal['present', 'missing', 'unavailable', 'not-applicable'] | None = None
    label: str | None = None
    explanation: str | None = None
    count: int | None = None
    url: str | None = None

class CoverageGetResponseRowsItemReport(APIModel):
    """CoverageGetResponseRowsItemReport version-1 API fields."""
    state: Literal['present', 'missing', 'unavailable', 'not-applicable'] | None = None
    label: str | None = None
    explanation: str | None = None
    count: int | None = None
    url: str | None = None

class CoverageGetResponseRowsItemPackage(APIModel):
    """CoverageGetResponseRowsItemPackage version-1 API fields."""
    state: Literal['present', 'missing', 'unavailable', 'not-applicable'] | None = None
    label: str | None = None
    explanation: str | None = None
    count: int | None = None
    url: str | None = None

class CoverageGetResponseGapsItemSupportsItem(APIModel):
    """CoverageGetResponseGapsItemSupportsItem version-1 API fields."""
    label: str | None = None
    url: str | None = None

class CoverageGetResponseGapsItemAction(APIModel):
    """CoverageGetResponseGapsItemAction version-1 API fields."""
    label: str | None = None
    url: str | None = None

class FamiliesListResponseProfilesItemOsintItem(APIModel):
    """FamiliesListResponseProfilesItemOsintItem version-1 API fields."""
    id: str | None = None
    title: str | None = None
    url: str | None = None
    position: int | None = None

class FamiliesListResponseProfilesItemReportsItem(APIModel):
    """FamiliesListResponseProfilesItemReportsItem version-1 API fields."""
    id: str | None = None
    original_filename: str | None = None
    title: str | None = None
    description: str | None = None
    sha256: str | None = None
    size: int | None = None
    uploaded_at: str | None = None

class FamiliesGetResponseProfileOsintItem(APIModel):
    """FamiliesGetResponseProfileOsintItem version-1 API fields."""
    id: str | None = None
    title: str | None = None
    url: str | None = None
    position: int | None = None

class FamiliesGetResponseProfileReportsItem(APIModel):
    """FamiliesGetResponseProfileReportsItem version-1 API fields."""
    id: str | None = None
    original_filename: str | None = None
    title: str | None = None
    description: str | None = None
    sha256: str | None = None
    size: int | None = None
    uploaded_at: str | None = None

class SettingsGetResponseSettingsSampleArchivePassword(APIModel):
    """SettingsGetResponseSettingsSampleArchivePassword version-1 API fields."""
    configured: bool | None = None

class SettingsUpdateResponseSettingsSampleArchivePassword(APIModel):
    """SettingsUpdateResponseSettingsSampleArchivePassword version-1 API fields."""
    configured: bool | None = None

for _value in list(globals().values()):
    if isinstance(_value, type) and issubclass(_value, BaseModel) and _value.__module__ == __name__:
        _value.model_rebuild()
