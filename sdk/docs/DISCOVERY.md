# Discovery, API boundaries and compatibility

The server is Flask/SQLite. `api.py` registers the existing `api` Blueprint under `/api/v1`; `api_extensions.py` adds explicitly allowlisted adapters in a second Blueprint at the same versioned prefix. OpenAPI derives paths and permission metadata from registered routes; request/response contracts remain explicit in `api_documentation.py` and the adapters. The SDK ships a frozen OpenAPI snapshot and generated source. SDK generation imports the server only in a disposable data directory; installed SDK code never does.

Authentication is the existing personal bearer-token system: SHA-256 hashes, one-time secrets, user association, last-used timestamps, expiration, revocation and per-token request quotas. Current user roles govern every call. Existing token issuance and revocation routes remain unchanged. New responses include generated `X-Request-ID`; mutation audit metadata records token ID, operation endpoint, status and request ID, without secrets or bodies. That metadata is recorded after the normal case-sync transaction commits or rolls back. Browser sessions/CSRF remain separate and cannot substitute for API authentication.

## Capability inventory

| Application capability | REST / SDK | Disposition |
|---|---|---|
| MIP Board, case metadata, ownership, lifecycle/history | `/cases`, item/stage/reopen; `cases` | Existing API retained; added query/title/number, owner/stage filters and stable allowlisted sorting |
| Case tasks, note findings and personal drafts | Case tasks/notes/draft; `tasks`, `notes` | Existing revisions/state/audit rules preserved |
| Structured indicator sections and row identities | Case indicators; `indicators` | Existing PUT with revision/section restrictions; added actual CSV/STIX preview/apply/current-STIX download adapters |
| References | Case references; `references` | Existing revision-controlled two-column table |
| Four analyst report sections, ATT&CK/MBC Markdown | Case report/mappings; `reports` | Existing API preserved, no invented mapping counts |
| Word templates, report jobs, edited DOCX and images | Case report and `/templates`; `reports`, `templates` | Existing upload/generation/ownership rules; shared final-report handler now preserves its deferred report-path update |
| Standard/RAW MIP and malware samples | Case archive; `packages` | Existing exporter, readiness, sample permissions and archive contents unchanged |
| Package assets/artifacts | Case assets; `assets` | Existing bounded uploads, traversal restrictions and streamed downloads |
| Case backups and cross-install synchronization | `/backups`; `backups` | Existing staged preview/review/apply, fingerprints/conflicts and ownership retained |
| New selective/complete encrypted backups | `/backup-jobs`; `backups` | Adapter to existing durable owner-scoped jobs, choices, encryption and explicit replacement acknowledgement |
| Raw database backup | `/backups/database` | Intentionally retired HTTP 410; no fake SDK implementation; encrypted complete backup jobs are the supported replacement |
| Investigation Coverage and Knowledge Gaps | `/coverage`; `coverage.get` | Same derived definitions, granularity, permissions, pagination and partial-data limits as the dock |
| Explorer graph, direct evidence, connections, computed shared indicators and saved views | `/explorer`; `explorer` | Existing authorized handlers reused; no canvas positions or relationships changed by reading |
| Malware Families / Threat Actors, aliases, OSINT, attached reports, shared associations | `/families`, `/actors`; matching namespaces | Existing optimistic versions, namespaces, report storage validation, conflict handling and audit paths reused |
| Shared tags / case assignments | `/tags`, case tags; `tags` | Existing normalization, protected linked-profile tags and assignment permissions retained |
| Package/search index | `/search`; `search.query` | Existing index scheduling, filters, authorized results and partial/index status reused; hits link to authorized web findings |
| Installed analyst tool registry | `/tools`; `tools.list` | Actual enabled/authorized `AnalystTool` entries only |
| Text Manipulation | `/tools/text/process`; `tools.process_text` | Same bounded offline local operations |
| YARA/Snort editing, assets, local drafts, downloads and bounded jobs | `/tools/yara`, `/tools/snort`, case tool paths; `tools` | Existing validation, job ownership, engine availability and case asset permissions retained |
| CyberChef recipes and interactive execution | Registry metadata only | Browser-owned JavaScript application, no server execution API exists; no fake execution method |
| Plugins | `/plugins`; `plugins.capabilities` | There is no user plugin registry. This reports that fact plus installed tools; external plugins use the standalone REST client |
| Account/role/token administration | `/users`, `/roles`, `/permissions`, `/tokens`, `/me`; `users`, `roles`, `authentication` | Existing last-admin/role-grant/forced-password/revocation protections retained |
| Application secret configuration | `/settings`; `settings` | Existing sample-password configured status/write-only update; secrets not exposed as settings reads |
| Per-user browser autosave interval | Browser Settings | UI preference, not an investigation or integration capability; no second SDK autosave scheduler |
| Metrics | `/metrics`; `metrics.get` | Existing API projection is retained; callers can combine with case listings or coverage, not invented chart endpoints |
| Administrator audit exports | `/audit/export.csv`, `/audit/export-all.zip`; `audit` | Existing Administrator-only handlers retained in addition to REST permission metadata |
| Login/logout, forced password/bootstrap, interactive account password changes and temporary-password reset display | Browser account/user pages | Browser identity/bootstrap operations intentionally remain interactive; API automation uses tokens and existing account CRUD |
| Anonymous Cases/Family/Actor dashboards, dashboard landing page and application navigation | Public/browser HTML and read-only dashboard JSON | Presentation-only existing endpoints remain available to browsers; the SDK uses richer authorized resources instead of weakening authentication for anonymous dashboard projections |
| Installation repair/migrations, vendor download/install scripts, key files and filesystem recovery | Operator CLI/deployment tooling | Not remote application APIs; exposing them would create unrelated privileged remote execution/install surfaces |
| Canvas layout/selection/marquee, UI collapse state, preview renderers and editor autosave | Browser-only interactions | No invented persistent server data or SDK methods; saved view configurations can be stored through `explorer` |

The generated [operation matrix](API_COVERAGE.md) gives the exact method, route, permission, model and SDK method for every versioned operation, including the explained retired endpoint. Adapters expose the same validation boundary, not arbitrary endpoint dispatch from user-controlled names.

## Practical limits

- API v1 and SDK 1.x are the compatibility boundary. Newly added routes require this server revision; old deployments return normal not-found errors for missing features.
- Tool job contexts and extension payloads retain additional fields. Typed stable fields are modeled; the SDK does not fabricate schemas for opaque tool-engine output.
- Optional native engines (Snort/YARA/LibreOffice) still require server configuration. Missing engine behavior is returned by existing handlers, not simulated.
- Full backup replacement retains its existing reauthentication/maintenance semantics; a replaced installation may revoke or remove the token being used. Polling clients must handle authentication failure deliberately.
- Indicator/coverage/graph limits remain server-enforced. An API call succeeding does not mean every stored draft indicator can be exported.
- Profile writes require current versions. Keep omitted fields to preserve data; explicit empty collections remove associations/aliases. Multipart writes use the established full-form contract; JSON profile edits additionally preserve omitted metadata and associations.
- No idempotency guarantee exists for writes. The SDK never retries mutations automatically. Streaming interruptions do not publish partial output; retry explicitly if appropriate.
- Async network I/O is asynchronous; bounded local file reads/writes use ordinary filesystem operations. There is no background transfer manager.
- Native engine execution, encrypted complete replacement and every external deployment combination are not exhaustively exercised by the mocked SDK suite. Backend suites and isolated integration tests cover the underlying rules; a real deployment still needs its configured engines and operational backup procedures.
