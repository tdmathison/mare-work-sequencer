# API-to-SDK coverage matrix

Generated from registered routes and reviewed OpenAPI contracts. All rows are implemented; runtime authorization, workflow and revision errors remain authoritative. Tests exercise every method with mocked HTTP and representative isolated backend workflows.

| Method | REST endpoint | Permission | Request / query model | Response | SDK method | Status |
|---|---|---|---|---|---|---|
| GET | `/api/v1/actors` | tags:read | ActorsListParams | ActorsListResponse | `client.actors.list` | Implemented |
| POST | `/api/v1/actors` | tags:manage | ActorsCreateRequest | ActorsCreateResponse | `client.actors.create` | Implemented |
| GET | `/api/v1/actors/{fid}` | tags:read | ActorsGetParams | ActorsGetResponse | `client.actors.get` | Implemented |
| POST | `/api/v1/actors/{fid}/delete` | tags:manage | ActorsDeleteRequest | ActorsDeleteResponse | `client.actors.delete` | Implemented |
| POST | `/api/v1/actors/{fid}/edit` | tags:manage | ActorsUpdateRequest | ActorsUpdateResponse | `client.actors.update` | Implemented |
| POST | `/api/v1/actors/{fid}/osint` | tags:manage | ActorsAddOsintRequest | ActorsAddOsintResponse | `client.actors.add_osint` | Implemented |
| POST | `/api/v1/actors/{fid}/osint/{eid}/delete` | tags:manage | ActorsDeleteOsintRequest | ActorsDeleteOsintResponse | `client.actors.delete_osint` | Implemented |
| POST | `/api/v1/actors/{fid}/osint/{eid}/edit` | tags:manage | ActorsUpdateOsintRequest | ActorsUpdateOsintResponse | `client.actors.update_osint` | Implemented |
| POST | `/api/v1/actors/{fid}/reports` | tags:manage | ActorsUploadReportsRequest | ActorsUploadReportsResponse | `client.actors.upload_reports` | Implemented |
| POST | `/api/v1/actors/{fid}/reports/{aid}/delete` | tags:manage | ActorsDeleteReportRequest | ActorsDeleteReportResponse | `client.actors.delete_report` | Implemented |
| GET | `/api/v1/actors/{fid}/reports/{aid}/download` | tags:read | None | Download | `client.actors.download_report` | Implemented |
| POST | `/api/v1/actors/{fid}/reports/{aid}/edit` | tags:manage | ActorsUpdateReportRequest | ActorsUpdateReportResponse | `client.actors.update_report` | Implemented |
| GET | `/api/v1/audit/export-all.zip` | users:manage | None | Download | `client.audit.export_all` | Implemented |
| GET | `/api/v1/audit/export.csv` | users:manage | AuditExportCsvParams | Download | `client.audit.export_csv` | Implemented |
| POST | `/api/v1/backup-jobs` | backups:manage | BackupsCreateJobRequest | BackupsCreateJobResponse | `client.backups.create_job` | Implemented |
| GET | `/api/v1/backup-jobs/{jid}` | backups:manage | None | BackupsJobResponse | `client.backups.job` | Implemented |
| POST | `/api/v1/backup-jobs/{jid}/apply` | backups:manage | BackupsApplyRequest | BackupsApplyResponse | `client.backups.apply` | Implemented |
| GET | `/api/v1/backup-jobs/{jid}/download` | backups:manage | None | Download | `client.backups.download` | Implemented |
| POST | `/api/v1/backup-jobs/{jid}/preview` | backups:manage | BackupsPreviewRequest | BackupsPreviewResponse | `client.backups.preview` | Implemented |
| POST | `/api/v1/backups/apply/{operation}` | backups:manage | BackupsSyncApplyRequest | SyncResult | `client.backups.sync_apply` | Implemented |
| POST | `/api/v1/backups/export` | backups:manage | None | Download | `client.backups.export_cases` | Implemented |
| POST | `/api/v1/backups/import` | backups:manage | BackupsImportCasesRequest | BackupsImportCasesResponse | `client.backups.import_cases` | Implemented |
| POST | `/api/v1/backups/import-raw` | backups:manage | BackupsImportRawRequest | BackupsImportRawResponse | `client.backups.import_raw` | Implemented |
| GET | `/api/v1/backups/review/{operation}` | backups:manage | None | SyncResult | `client.backups.sync_review` | Implemented |
| GET | `/api/v1/cases` | cases:read | CasesListParams | CasesListResponse | `client.cases.list` | Implemented |
| POST | `/api/v1/cases` | cases:create | CasesCreateRequest | CasesCreateResponse | `client.cases.create` | Implemented |
| DELETE | `/api/v1/cases/{case_id}` | cases:delete | None | No body | `client.cases.delete` | Implemented |
| GET | `/api/v1/cases/{case_id}` | cases:read | None | CasesGetResponse | `client.cases.get` | Implemented |
| PATCH | `/api/v1/cases/{case_id}` | cases:update | CasesUpdateRequest | CasesUpdateResponse | `client.cases.update` | Implemented |
| POST | `/api/v1/cases/{case_id}/archive` | cases:export | PackagesExportRequest | Download | `client.packages.export` | Implemented |
| DELETE | `/api/v1/cases/{case_id}/assets` | cases:assets | AssetsDeleteRequest | No body | `client.assets.delete` | Implemented |
| GET | `/api/v1/cases/{case_id}/assets` | cases:read | AssetsListParams | AssetsListResponse | `client.assets.list` | Implemented |
| POST | `/api/v1/cases/{case_id}/assets` | cases:assets | AssetsUploadRequest | AssetsUploadResponse | `client.assets.upload` | Implemented |
| GET | `/api/v1/cases/{case_id}/assets/{relative_path}` | cases:assets | None | Download | `client.assets.download` | Implemented |
| POST | `/api/v1/cases/{case_id}/backup` | cases:export | None | Download | `client.backups.case` | Implemented |
| DELETE | `/api/v1/cases/{case_id}/draft` | cases:update | None | No body | `client.notes.delete_draft` | Implemented |
| GET | `/api/v1/cases/{case_id}/draft` | cases:read | None | NotesGetDraftResponse | `client.notes.get_draft` | Implemented |
| PUT | `/api/v1/cases/{case_id}/draft` | cases:update | NotesUpdateDraftRequest | NotesUpdateDraftResponse | `client.notes.update_draft` | Implemented |
| GET | `/api/v1/cases/{case_id}/indicators` | indicators:read | None | Indicators | `client.indicators.get` | Implemented |
| PUT | `/api/v1/cases/{case_id}/indicators` | indicators:write | IndicatorsUpdateRequest | Indicators | `client.indicators.update` | Implemented |
| GET | `/api/v1/cases/{case_id}/notes` | cases:read | NotesListParams | NotesListResponse | `client.notes.list` | Implemented |
| POST | `/api/v1/cases/{case_id}/notes` | cases:update | NotesCreateRequest | NotesCreateResponse | `client.notes.create` | Implemented |
| DELETE | `/api/v1/cases/{case_id}/notes/{note_id}` | cases:update | None | No body | `client.notes.delete` | Implemented |
| GET | `/api/v1/cases/{case_id}/notes/{note_id}` | cases:read | None | NotesGetResponse | `client.notes.get` | Implemented |
| PATCH | `/api/v1/cases/{case_id}/notes/{note_id}` | cases:update | NotesUpdateRequest | NotesUpdateResponse | `client.notes.update` | Implemented |
| GET | `/api/v1/cases/{case_id}/readiness` | cases:read | None | PackagesReadinessResponse | `client.packages.readiness` | Implemented |
| PUT | `/api/v1/cases/{case_id}/readiness` | cases:update | PackagesSetReadinessRequest | PackagesSetReadinessResponse | `client.packages.set_readiness` | Implemented |
| GET | `/api/v1/cases/{case_id}/references` | references:read | None | References | `client.references.get` | Implemented |
| PUT | `/api/v1/cases/{case_id}/references` | references:write | ReferencesUpdateRequest | References | `client.references.update` | Implemented |
| POST | `/api/v1/cases/{case_id}/reopen` | cases:workflow | None | CasesReopenResponse | `client.cases.reopen` | Implemented |
| GET | `/api/v1/cases/{case_id}/report` | reports:read | None | ReportsGetResponse | `client.reports.get` | Implemented |
| PUT | `/api/v1/cases/{case_id}/report` | reports:write | ReportsUpdateRequest | ReportsUpdateResponse | `client.reports.update` | Implemented |
| GET | `/api/v1/cases/{case_id}/report/download` | reports:read | ReportsDownloadParams | Download | `client.reports.download` | Implemented |
| POST | `/api/v1/cases/{case_id}/report/final` | reports:generate | ReportsUploadRequest | ReportsUploadResponse | `client.reports.upload` | Implemented |
| POST | `/api/v1/cases/{case_id}/report/generate` | reports:generate | ReportsGenerateRequest | ReportsGenerateResponse | `client.reports.generate` | Implemented |
| GET | `/api/v1/cases/{case_id}/report/images` | reports:read | None | ReportsListImagesResponse | `client.reports.list_images` | Implemented |
| POST | `/api/v1/cases/{case_id}/report/images` | reports:write | ReportsUploadImageRequest | Image | `client.reports.upload_image` | Implemented |
| DELETE | `/api/v1/cases/{case_id}/report/images/{name}` | reports:write | None | No body | `client.reports.delete_image` | Implemented |
| GET | `/api/v1/cases/{case_id}/report/images/{name}` | reports:read | None | Download | `client.reports.download_image` | Implemented |
| GET | `/api/v1/cases/{case_id}/report/job` | reports:read | None | ReportsJobResponse | `client.reports.job` | Implemented |
| GET | `/api/v1/cases/{case_id}/report/mappings` | reports:read | None | ReportsGetMappingsResponse | `client.reports.get_mappings` | Implemented |
| PUT | `/api/v1/cases/{case_id}/report/mappings` | reports:write | ReportsUpdateMappingsRequest | ReportsUpdateMappingsResponse | `client.reports.update_mappings` | Implemented |
| POST | `/api/v1/cases/{case_id}/stage` | cases:workflow | CasesAdvanceRequest | CasesAdvanceResponse | `client.cases.advance` | Implemented |
| GET | `/api/v1/cases/{case_id}/tasks` | cases:read | TasksListParams | TasksListResponse | `client.tasks.list` | Implemented |
| POST | `/api/v1/cases/{case_id}/tasks` | cases:update | TasksCreateRequest | TasksCreateResponse | `client.tasks.create` | Implemented |
| DELETE | `/api/v1/cases/{case_id}/tasks/{task_id}` | cases:update | None | No body | `client.tasks.delete` | Implemented |
| GET | `/api/v1/cases/{case_id}/tasks/{task_id}` | cases:read | None | TasksGetResponse | `client.tasks.get` | Implemented |
| PATCH | `/api/v1/cases/{case_id}/tasks/{task_id}` | cases:update | TasksUpdateRequest | TasksUpdateResponse | `client.tasks.update` | Implemented |
| POST | `/api/v1/cases/{cid}/indicators/import` | indicators:write | IndicatorsImportRowsRequest | IndicatorsImportRowsResponse | `client.indicators.import_rows` | Implemented |
| POST | `/api/v1/cases/{cid}/indicators/import/preview` | indicators:write | IndicatorsPreviewImportRequest | IndicatorsPreviewImportResponse | `client.indicators.preview_import` | Implemented |
| GET | `/api/v1/cases/{cid}/indicators/stix` | indicators:read | None | Download | `client.indicators.download_stix` | Implemented |
| GET | `/api/v1/cases/{cid}/snort/file` | cases:assets | ToolsSnortOpenParams | ToolsSnortOpenResponse | `client.tools.snort_open` | Implemented |
| POST | `/api/v1/cases/{cid}/snort/file` | cases:assets | ToolsSnortSaveRequest | ToolsSnortSaveResponse | `client.tools.snort_save` | Implemented |
| GET | `/api/v1/cases/{cid}/snort/files` | cases:assets | ToolsSnortInventoryParams | ToolsSnortInventoryResponse | `client.tools.snort_inventory` | Implemented |
| POST | `/api/v1/cases/{cid}/snort/normalize` | cases:assets | ToolsSnortNormalizeRequest | ToolsSnortNormalizeResponse | `client.tools.snort_normalize` | Implemented |
| GET | `/api/v1/cases/{cid}/tags` | tags:read | None | TagsForCaseResponse | `client.tags.for_case` | Implemented |
| POST | `/api/v1/cases/{cid}/tags/{tid}/assign` | tags:assign | None | TagsAssignResponse | `client.tags.assign` | Implemented |
| POST | `/api/v1/cases/{cid}/tags/{tid}/remove` | tags:assign | None | TagsRemoveResponse | `client.tags.remove` | Implemented |
| POST | `/api/v1/cases/{cid}/task-collections` | Authenticated / handler checks | TaskCollectionsFromTasksRequest | TaskCollectionsFromTasksResponse | `client.task_collections.from_tasks` | Implemented |
| POST | `/api/v1/cases/{cid}/task-collections/{collection_id}/apply` | cases:update | TaskCollectionsApplyRequest | TaskCollectionsApplyResponse | `client.task_collections.apply` | Implemented |
| GET | `/api/v1/cases/{cid}/task-groups` | cases:read | None | TaskCollectionsCaseGroupsResponse | `client.task_collections.case_groups` | Implemented |
| DELETE | `/api/v1/cases/{cid}/task-groups/{gid}` | cases:update | TaskCollectionsRemoveGroupRequest | TaskCollectionsRemoveGroupResponse | `client.task_collections.remove_group` | Implemented |
| PUT | `/api/v1/cases/{cid}/task-order` | cases:update | TaskCollectionsReorderRequest | TaskCollectionsReorderResponse | `client.task_collections.reorder` | Implemented |
| GET | `/api/v1/cases/{cid}/yara/file` | cases:assets | ToolsYaraOpenParams | ToolsYaraOpenResponse | `client.tools.yara_open` | Implemented |
| POST | `/api/v1/cases/{cid}/yara/file` | cases:assets | ToolsYaraSaveRequest | ToolsYaraSaveResponse | `client.tools.yara_save` | Implemented |
| GET | `/api/v1/cases/{cid}/yara/files` | cases:assets | ToolsYaraFilesParams | ToolsYaraFilesResponse | `client.tools.yara_files` | Implemented |
| GET | `/api/v1/coverage` | Authenticated / handler checks | CoverageGetParams | CoverageGetResponse | `client.coverage.get` | Implemented |
| GET | `/api/v1/explorer/cases/{case_id}/contents` | cases:read | ExplorerContentsParams | ExplorerContentsResponse | `client.explorer.contents` | Implemented |
| GET | `/api/v1/explorer/cases/{case_id}/contents/{category}` | cases:read | ExplorerCategoryParams | ExplorerCategoryResponse | `client.explorer.category` | Implemented |
| GET | `/api/v1/explorer/cases/{case_id}/file` | cases:read | ExplorerDownloadParams | Download | `client.explorer.download` | Implemented |
| GET | `/api/v1/explorer/connection-objects` | Authenticated / handler checks | ExplorerConnectionObjectsParams | ExplorerConnectionObjectsResponse | `client.explorer.connection_objects` | Implemented |
| GET | `/api/v1/explorer/connections` | Authenticated / handler checks | ExplorerConnectionsParams | ExplorerConnectionsResponse | `client.explorer.connections` | Implemented |
| GET | `/api/v1/explorer/evidence` | Authenticated / handler checks | ExplorerEvidenceParams | ExplorerEvidenceResponse | `client.explorer.evidence` | Implemented |
| GET | `/api/v1/explorer/graph` | Authenticated / handler checks | ExplorerGraphParams | ExplorerGraphResponse | `client.explorer.graph` | Implemented |
| GET | `/api/v1/explorer/shared-indicators` | Authenticated / handler checks | ExplorerSharedIndicatorsParams | ExplorerSharedIndicatorsResponse | `client.explorer.shared_indicators` | Implemented |
| GET | `/api/v1/explorer/views` | Authenticated / handler checks | None | ExplorerListViewsResponse | `client.explorer.list_views` | Implemented |
| POST | `/api/v1/explorer/views` | Authenticated / handler checks | ExplorerCreateViewRequest | ExplorerCreateViewResponse | `client.explorer.create_view` | Implemented |
| GET | `/api/v1/explorer/views/{vid}` | Authenticated / handler checks | None | ExplorerGetViewResponse | `client.explorer.get_view` | Implemented |
| POST | `/api/v1/explorer/views/{vid}/delete` | Authenticated / handler checks | ExplorerDeleteViewRequest | ExplorerDeleteViewResponse | `client.explorer.delete_view` | Implemented |
| POST | `/api/v1/explorer/views/{vid}/update` | Authenticated / handler checks | ExplorerUpdateViewRequest | ExplorerUpdateViewResponse | `client.explorer.update_view` | Implemented |
| GET | `/api/v1/families` | tags:read | FamiliesListParams | FamiliesListResponse | `client.families.list` | Implemented |
| POST | `/api/v1/families` | tags:manage | FamiliesCreateRequest | FamiliesCreateResponse | `client.families.create` | Implemented |
| GET | `/api/v1/families/{fid}` | tags:read | FamiliesGetParams | FamiliesGetResponse | `client.families.get` | Implemented |
| POST | `/api/v1/families/{fid}/delete` | tags:manage | FamiliesDeleteRequest | FamiliesDeleteResponse | `client.families.delete` | Implemented |
| POST | `/api/v1/families/{fid}/edit` | tags:manage | FamiliesUpdateRequest | FamiliesUpdateResponse | `client.families.update` | Implemented |
| POST | `/api/v1/families/{fid}/osint` | tags:manage | FamiliesAddOsintRequest | FamiliesAddOsintResponse | `client.families.add_osint` | Implemented |
| POST | `/api/v1/families/{fid}/osint/{eid}/delete` | tags:manage | FamiliesDeleteOsintRequest | FamiliesDeleteOsintResponse | `client.families.delete_osint` | Implemented |
| POST | `/api/v1/families/{fid}/osint/{eid}/edit` | tags:manage | FamiliesUpdateOsintRequest | FamiliesUpdateOsintResponse | `client.families.update_osint` | Implemented |
| POST | `/api/v1/families/{fid}/reports` | tags:manage | FamiliesUploadReportsRequest | FamiliesUploadReportsResponse | `client.families.upload_reports` | Implemented |
| POST | `/api/v1/families/{fid}/reports/{aid}/delete` | tags:manage | FamiliesDeleteReportRequest | FamiliesDeleteReportResponse | `client.families.delete_report` | Implemented |
| GET | `/api/v1/families/{fid}/reports/{aid}/download` | tags:read | None | Download | `client.families.download_report` | Implemented |
| POST | `/api/v1/families/{fid}/reports/{aid}/edit` | tags:manage | FamiliesUpdateReportRequest | FamiliesUpdateReportResponse | `client.families.update_report` | Implemented |
| GET | `/api/v1/me` | Authenticated / handler checks | None | AuthenticationMeResponse | `client.authentication.me` | Implemented |
| GET | `/api/v1/metrics` | metrics:read | None | MetricsGetResponse | `client.metrics.get` | Implemented |
| GET | `/api/v1/permissions` | roles:manage | None | RolesPermissionsResponse | `client.roles.permissions` | Implemented |
| GET | `/api/v1/plugins` | Authenticated / handler checks | None | PluginsCapabilitiesResponse | `client.plugins.capabilities` | Implemented |
| GET | `/api/v1/roles` | roles:manage | None | RolesListResponse | `client.roles.list` | Implemented |
| POST | `/api/v1/roles` | roles:manage | RolesCreateRequest | Role | `client.roles.create` | Implemented |
| DELETE | `/api/v1/roles/{name}` | roles:manage | None | No body | `client.roles.delete` | Implemented |
| GET | `/api/v1/roles/{name}` | roles:manage | None | Role | `client.roles.get` | Implemented |
| PATCH | `/api/v1/roles/{name}` | roles:manage | RolesUpdateRequest | Role | `client.roles.update` | Implemented |
| GET | `/api/v1/search` | cases:read | SearchQueryParams | SearchQueryResponse | `client.search.query` | Implemented |
| GET | `/api/v1/settings` | settings:read | None | SettingsGetResponse | `client.settings.get` | Implemented |
| PATCH | `/api/v1/settings` | settings:write | SettingsUpdateRequest | SettingsUpdateResponse | `client.settings.update` | Implemented |
| GET | `/api/v1/tags` | tags:read | TagsListParams | TagsListResponse | `client.tags.list` | Implemented |
| POST | `/api/v1/tags` | tags:create | TagsCreateRequest | TagsCreateResponse | `client.tags.create` | Implemented |
| GET | `/api/v1/tags/{tid}` | tags:read | None | TagsGetResponse | `client.tags.get` | Implemented |
| POST | `/api/v1/tags/{tid}/delete` | tags:manage | TagsDeleteRequest | TagsDeleteResponse | `client.tags.delete` | Implemented |
| POST | `/api/v1/tags/{tid}/merge` | tags:manage | TagsMergeRequest | TagsMergeResponse | `client.tags.merge` | Implemented |
| POST | `/api/v1/tags/{tid}/rename` | tags:manage | TagsRenameRequest | TagsRenameResponse | `client.tags.rename` | Implemented |
| GET | `/api/v1/task-collections` | Authenticated / handler checks | TaskCollectionsListParams | TaskCollectionsListResponse | `client.task_collections.list` | Implemented |
| POST | `/api/v1/task-collections` | task_collections:create | TaskCollectionsCreateRequest | TaskCollectionsCreateResponse | `client.task_collections.create` | Implemented |
| DELETE | `/api/v1/task-collections/{collection_id}` | task_collections:delete | TaskCollectionsDeleteRequest | No body | `client.task_collections.delete` | Implemented |
| GET | `/api/v1/task-collections/{collection_id}` | Authenticated / handler checks | None | TaskCollectionsGetResponse | `client.task_collections.get` | Implemented |
| PATCH | `/api/v1/task-collections/{collection_id}` | task_collections:update | TaskCollectionsUpdateRequest | TaskCollectionsUpdateResponse | `client.task_collections.update` | Implemented |
| POST | `/api/v1/task-collections/{collection_id}/duplicate` | task_collections:create | TaskCollectionsDuplicateRequest | TaskCollectionsDuplicateResponse | `client.task_collections.duplicate` | Implemented |
| GET | `/api/v1/templates` | templates:manage | None | TemplatesListResponse | `client.templates.list` | Implemented |
| POST | `/api/v1/templates` | templates:manage | TemplatesUploadRequest | TemplatesUploadResponse | `client.templates.upload` | Implemented |
| DELETE | `/api/v1/templates/{template_id}` | templates:manage | None | No body | `client.templates.delete` | Implemented |
| GET | `/api/v1/templates/{template_id}` | templates:manage | None | Download | `client.templates.download` | Implemented |
| PUT | `/api/v1/templates/selected` | templates:manage | TemplatesSelectRequest | TemplatesSelectResponse | `client.templates.select` | Implemented |
| GET | `/api/v1/tokens` | tokens:manage | None | AuthenticationListTokensResponse | `client.authentication.list_tokens` | Implemented |
| POST | `/api/v1/tokens` | tokens:manage | AuthenticationCreateTokenRequest | AuthenticationCreateTokenResponse | `client.authentication.create_token` | Implemented |
| DELETE | `/api/v1/tokens/{token_id}` | tokens:manage | None | No body | `client.authentication.revoke_token` | Implemented |
| GET | `/api/v1/tools` | Authenticated / handler checks | None | ToolsListResponse | `client.tools.list` | Implemented |
| POST | `/api/v1/tools/snort/download` | Authenticated / handler checks | ToolsSnortDownloadRequest | Download | `client.tools.snort_download` | Implemented |
| POST | `/api/v1/tools/snort/draft` | Authenticated / handler checks | ToolsSnortDraftRequest | ToolsSnortDraftResponse | `client.tools.snort_draft` | Implemented |
| POST | `/api/v1/tools/snort/jobs` | Authenticated / handler checks | ToolsSnortJobsRequest | ToolsSnortJobsResponse | `client.tools.snort_jobs` | Implemented |
| GET | `/api/v1/tools/snort/jobs/{job}` | Authenticated / handler checks | None | ToolsSnortJobResponse | `client.tools.snort_job` | Implemented |
| POST | `/api/v1/tools/snort/jobs/{job}/cancel` | Authenticated / handler checks | ToolsSnortCancelRequest | ToolsSnortCancelResponse | `client.tools.snort_cancel` | Implemented |
| GET | `/api/v1/tools/snort/state` | Authenticated / handler checks | None | ToolsSnortStateResponse | `client.tools.snort_state` | Implemented |
| POST | `/api/v1/tools/text/process` | Authenticated / handler checks | ToolsProcessTextRequest | ToolsProcessTextResponse | `client.tools.process_text` | Implemented |
| POST | `/api/v1/tools/yara/download` | Authenticated / handler checks | ToolsYaraDownloadRequest | Download | `client.tools.yara_download` | Implemented |
| POST | `/api/v1/tools/yara/draft` | Authenticated / handler checks | ToolsYaraDraftRequest | ToolsYaraDraftResponse | `client.tools.yara_draft` | Implemented |
| POST | `/api/v1/tools/yara/jobs` | Authenticated / handler checks | ToolsYaraJobsRequest | ToolsYaraJobsResponse | `client.tools.yara_jobs` | Implemented |
| GET | `/api/v1/tools/yara/jobs/{job}` | Authenticated / handler checks | None | ToolsYaraJobResponse | `client.tools.yara_job` | Implemented |
| POST | `/api/v1/tools/yara/jobs/{job}/cancel` | Authenticated / handler checks | ToolsYaraCancelRequest | ToolsYaraCancelResponse | `client.tools.yara_cancel` | Implemented |
| GET | `/api/v1/tools/yara/state` | Authenticated / handler checks | None | ToolsYaraStateResponse | `client.tools.yara_state` | Implemented |
| GET | `/api/v1/users` | users:manage | UsersListParams | UsersListResponse | `client.users.list` | Implemented |
| POST | `/api/v1/users` | users:manage | UsersCreateRequest | UsersCreateResponse | `client.users.create` | Implemented |
| DELETE | `/api/v1/users/{user_id}` | users:manage | None | No body | `client.users.delete` | Implemented |
| GET | `/api/v1/users/{user_id}` | users:manage | None | UsersGetResponse | `client.users.get` | Implemented |
| PATCH | `/api/v1/users/{user_id}` | users:manage | UsersUpdateRequest | UsersUpdateResponse | `client.users.update` | Implemented |
| POST | `/api/v1/backups/database` | backups:manage | None | HTTP 410 | No SDK method; use `backups.create_job` for complete encrypted backups | Retired, retained for old clients |
