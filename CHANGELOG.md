# Latest update

- Added a free-form YARA Rule Editor under Tools, with CodeMirror completion, condition snippets, safe metadata helpers, diagnostics, optional classic YARA 4.5.4 validation and bounded positive/baseline scans. Added recoverable account drafts, complete-file version-checked case storage and read-only asset previews; includes are disabled. Documented the curated language profile, execution limits and YARA-X distinction, with real compiler and browser regression coverage.

- Completed Snort Request bytes and Option library insertion workflows with local target/match selectors, content previews/configuration, shared mapped source anchors, sticky-buffer restoration, dependency checks, duplicate-free modifiers and explicit advanced templates. Added browser coverage for byte-to-source insertion, history, stale targets and selected-signature saves.

- Fixed Snort signature boundary scanning for inline/multiline block comments, retaining exact byte spans and completed prefix rules when a later region is unsafe. Added filename/line/column/excerpt diagnostics for malformed quotes and option blocks, explicit partial-file review, and safe-prefix save checks. Added reported malformed-file fixtures and browser regressions for repeated middle-signature edits with unchanged surrounding content.

- Improved Snort Construct controls with visible native action/protocol/direction selectors, editable address/port presets and categorized additive flow choices. Aligned checkbox labels and centralized official references in a searchable Docs tab. Corrected service-based full-header guidance and added browser regressions for controls, alignment and link placement.

- Added an editor-first Snort Rule Builder with semantic match groups, source-range inspectors, selection highlighting, byte assistance and bounded offline jobs. Multi-rule files remain intact: searchable signature selection tracks snapshot byte ranges and saves only the selected rule with atomic version checks. Save As and download operate on the selected signature; uncertain files offer whole-file inspection. Removed automatic splitting from browser/web/API uploads, preserved earlier split files, and standardized scoped action spacing. Added byte-preservation, selection, concurrency and browser regressions plus deployment documentation.

- Enabled the shared Show Preview control for MITRE ATT&CK and MBC editors, including unsaved content and expanded mode. Kept save/edit controls locked in read-only cases while allowing authenticated, CSRF-protected Markdown rendering through the existing safe preview endpoint.

- Made MIP Dashboard metric tiles apply shared stage filters and added multi-stage checkboxes to the Filters drawer. In progress includes analysis and packaging; All MIPs and Clear Filters clear stage, search and tag filters. Preserved filters when sorting or switching views, and made stage/search filters available without tag permissions.

- Corrected the MIP Dashboard title and added ascending/descending sorting to all non-action table columns. Sort preferences persist per account in the database and apply to both table and card views, retaining filters and existing backup actions.

- Fixed single-case and full-backup imports to resolve creators and assigned owners by exact destination username, including accounts with different installation UUIDs. Preserved unmatched-owner Unassigned behavior, creator fallback to the importing account, existing-case creator attribution and explicit incoming-ownership decisions.

- Added compact yellow duplicate warnings after indicator saves/autosaves, including the first row in each set. Saved feedback reuses import canonical type/value normalization, preserves blocking-error priority, and exposes “Duplicate rows detected” on hover, keyboard focus and tap. Warnings neither remove data nor block exports; stale autosave results cannot overwrite edited row feedback.

- Added focus-based highlighting of exact, nonblank duplicate indicator values across sections and a per-section Remove duplicates action beside Refang. Removal keeps the first row and its identity/metadata, leaves blank rows intact, and uses the existing save/autosave flow.

- Replaced persistent Indicators row help and export labels with compact accessible check/X status icons. Blank and unvalidated edits remain neutral; backend validation is tied to exact row content to reject stale autosave feedback. Errors are available on hover, keyboard focus and tap without increasing row height or changing export/import behavior.

- Closed the 165-type indicator storage/export gap using pinned official MISP event/attribute conversion and its contextual fallback writer. Added 68 verified native pattern mappings and two intent-constrained descriptive mappings (plus the existing MARE software extension); all 192 non-binary MISP types now round-trip through the actual importer. Preserved explicit detection intent, stable identities/unchanged revisions, section context and output-specific refanging; only invalid values, missing binary content and explicit converter failures withhold complete STIX. Replaced fallback validation errors with informational statuses, documented exact upstream limitations, and added complete-catalog, native, API/package/intent and browser regressions.

- Bundled all 194 official PyMISP 2.5.34.4 attribute types with local version/hash/license and offline update tooling. Separated literal storage support from native/contextual/unsupported export capabilities. Added faithful non-detection text/comment/other and application/extension-ID contextual exports verified with the official MISP converter; documented its boundary-whitespace trimming. Canonicalized legacy Android aliases to mobile-application-id on save while preserving identities/provenance. Added explicit unknown-import text/other correction, deduplicated searchable selector options, contextual help, and storage/CSV/STIX/API/RAW-sync/browser regressions.

- Added distinct searchable software-name and Android-package mappings with explicit STIX round-trip semantics and Software observable imports. Scoped the type selector to one painted disclosure arrow. Made CSV serialization type-aware so non-network values/descriptions stay literal while STIX consistently validates/refangs network values, including combined defanged URL schemes. Preserved identities, no-op saves and package/sync behavior; added server/browser and official MISP software conversion regressions, documenting that package patterns convert to generic MISP software rather than android-app objects.

- Added a shared canonical indicator catalog/searchable type selector, alias/value validation with preserved invalid drafts, stable row/section STIX identities, and local STIX 2.1 export beside CSV. Unified each section’s Import dialog with CSV/STIX tabs, correction previews, bounded local-only pattern/observable extraction, duplicate-safe additive application and explicit skipped-item reasons. Added save-before-download, stale-output guards/recovery, RAW/sync integration and OpenAPI updates. Verified all 23 mappings with official MISP attribute-labelled conversion; documented external-mode limitations and added server/browser regressions.

- Enforced uppercase ASCII tag names through shared backend validation, canonical uniqueness and SQLite write guards. Added an atomic, idempotent migration preserving tag associations, auditing case-only consolidation and retaining invalid legacy names with Tag Manager remediation. Imports reject invalid names visibly; synchronization verifies raw revision hashes before canonical comparison and retains ancestry when restoring older mixed-case tags. Added naming, concurrency, migration, API/import, synchronization and browser coverage.

- Fixed Search case groups reopening after indexing refreshes: individual and bulk disclosure controls share stable case/archive state, retained through same-search polling and pagination, reset on new submissions, with stale-response guards and browser race regressions.

- Added locally hosted Swagger UI 5.33.3 to the API tab with a validated OpenAPI 3.0.3 contract covering existing public operations, route/permission drift checks, authenticated specification access, same-origin session-gated execution, and no credential persistence. Kept token management with CSRF-protected one-time revelation; reused shared CodeMirror 6 for the read-only Python example and Copy code. Added isolated server/browser coverage and maintenance documentation.

- Grouped synchronization review by proposed action with accessible folding, restrained action badges, original classification counts, and a separate live planned-outcome summary. Preserved indexed decisions through folding, added replacement warnings and legacy-link validation, and distinguished actual completion/failure outcomes from plans.

- Fixed streamed ZIP entries defaulting to 1980: Standard/RAW exports and backups now preserve source modification timestamps, compression, and attributes through independent metadata copies and Python filename conversion. Generated entries use generation time; validated restores retain safe artifact/directory times. Documented local timezone, two-second precision, range clamping, and unrecoverable legacy dates; added archive/restore regressions.

- Redesigned METRICS as an executive scorecard with UTC full-week reporting, truthful period comparisons, distinct historical completion output and cycle times, an accessible local SVG activity chart, current pipeline and unfinished age buckets, and explicitly labeled current-owner analyst attribution. Preserved all-time snapshots and API metrics; added data-coverage notes and server/browser regressions without schema changes or dependencies.

- Added application-wide SEARCH after MIP BOARD: permission-aware literal/refanged MIP content search, grouped findings, exact-version read-only previews, filters and pagination. Added a derived background SQLite index with cached text/DOCX/PDF extraction, bounded Standard/RAW archive inspection, stale-source validation, and coverage/skip reporting. Existing downloads remain unretained; optional managed archives are searched locally. Added pypdf, documentation, and server/browser regressions.

- Added Tools → Text Manipulation: compact one-shot IOC/IP, line, replacement, regex, sorting, defang/refang, and JSON/XML/Python commands. Reuses the shared CodeMirror 6 bundle/theme with native atomic Undo/Redo, retained tab state, independent scrolling, and minimal toolbar. Added local worker processing, authenticated CSRF-protected 2 MiB processing endpoint, pinned Black formatter, offline IANA classification snapshot, and server/browser regression coverage.

- Added simple shared string tags: a compact inline Workbench autocomplete, collapsible left MIP Board filter drawer with Match Any/All, card chips, and a dense Tag Manager with permission-controlled rename, merge, and deletion. Added audited transactional persistence, validated RAW/full-backup tag metadata, and an explicit backed-up conversion path for prototype tables. Standard MIP contents and Markdown editors remain unchanged.

- Moved Markdown Preview and Expand/Collapse into dedicated right-aligned toolbar buttons with state-synchronized labels and glyphs; View now contains only editor preference checkboxes. Preserved top placement, viewport-aware menus, and existing preview/expansion handlers.

- Kept Markdown toolbars above source and preview in expanded workspaces; menus now fit the viewport, open upward when needed, and scroll without clipping. Added normal/expanded, laptop, task-dialog, and standalone layout regressions while retaining the same CodeMirror instance and state.

- Enhanced the existing CodeMirror editors with shared Format/Insert/View menus, six heading levels, reversible inline formatting, lists, folding, multiple selections, and compartment-based View preferences. Preserved MARE image/caption workflows and alignment controls; added validated body-row table dialogs and HTML/TSV merged-cell conversion. Preview prose uses local Aptos fallbacks; Word defaults to Aptos only without an explicit template Normal font. Added browser and Word typography regressions.

- Replaced report, task, MITRE mapping, and Markdown-file source editors with locally bundled CodeMirror 6, using official Markdown/fenced-language highlighting, line numbers, wrapping, search/replace, history, and a MARE theme. Removed custom overlays and both gutter synchronization implementations that could disagree at wrap boundaries.
- Preserved Markdown toolbars, images/captions, previews, form/API payloads, configurable autosave, and expanded editing; saves retain current typing/selection/scroll, with server and browser regression coverage and reproducible frontend build documentation. No database, authentication, report, or archive-format changes.

- Added the authenticated, case-independent Analyst Tools workspace between Metrics and Users, with a lightweight permission-aware registry, retained lazy tool panels, keyboard tabs, and Expand/Restore controls.
- Integrated locally installed official CyberChef v11.5.0 with authenticated vendor assets, a checksum-pinned offline-capable installer, isolated MARE theme overrides, a local-only connection policy, setup messages, tests, and deployment/update documentation. No case storage or database migrations were added.

- Completed the REST API (`/api/v1`): final report upload, report downloads, report images, Word template management, case and full backups, RAW imports, database backup, metrics, pagination, richer case detail, token expiry, per-token rate limiting, JSON errors, tests, and documentation. See the REST API section of the README.
- Renamed the application folder and deployment examples to mare-work-sequencer; default and relative data locations follow app.py instead of the launch working directory.

- Generated Word reports now use YYYYMMDD-MARE_<external number or system sequence>_RE_Report_<sanitized title>.docx. Open/edit, replacement backups, completion checks, exports, and RAW imports track the report filename.

- Removed OpenAI settings, API routes, key storage, and AI/extraction dependencies while preserving Word template selections.
- Matched generated Word tables to the provided example.
- Fixed task Raw/Preview tab styling to match Report editors.
- Added a copyable MITRE prompt based on current report text and local ingestion of uploaded mapping Markdown.
- Stopped creating default mappings and removed only unchanged legacy mapping placeholders.

# v0.3.2

- Full-workspace task creation/editing with report-style Markdown descriptions and Raw/Preview views.
- Shared Formatting/Insert toolbar menus across task and report editors.
- Task image upload, figure insertion, deletion, and RAW-backup restoration of associations.

- Preserve exported stages on full and single RAW case imports.
- Immutable user identifiers and ownership restoration requiring both identifier and username.
- MIP-card Backup actions convert Python filenames for email; imports restore extensions with collision checks.
- Administrator installation backups include SQLite, account identities/settings, encryption keys, templates, and all case files.
- One-minute default autosave countdowns, manual/automatic timer resets, and no-op handling for unchanged automatic saves.

- Import & Export navigation with a single portable backup containing every case as a RAW MIP package.
- Case metadata restores saved notes/tasks/history/readiness, indicator sections, references, and report images.
- Additive imports use fresh system numbers, the importer as creator, no owner, and Not started status.
- Checksum/path/size validation and transactional rollback protect existing cases during import.

- Per-user autosave intervals in Settings, defaulting to five minutes, for report sections, indicators, and references.
- Autosave feedback, dirty checks, and preservation of edits typed during saves.
- Four-stage workflow removing Reports, with existing cases, history, and deferred work migrated safely.
- Updated completed-case permissions, export gating, and Metrics for the four stages.

- Editable titles/descriptions for every indicator section.
- Confirmed deletion of additional indicator sections and their rows; the initial section is protected server-side and in the UI.
- Updated initial indicator section wording, with migration that preserves analyst overrides.

- Indicator sections with titles/descriptions, a preserved Default section, and per-section inline rows/CSV import.
- One Save table action saves all sections and writes grouping metadata to iocs/indicators.csv.
- Word reports render each indicator section as a subsection with description and table.
- Destructive commands is confined to Workbench; anchor links reveal their containing tab.

- Display-only immutable system case numbers, with permanent reservations after deletion.
- Bottom-of-case Destructive commands panel with typed case-number confirmation and complete case/file deletion.
- Workspace-sized Add Task dialog with expanded description space, Cancel, and Escape support.

- Centered report images with dark gray borders and numbered italic figure captions in previews and Word reports.
- OpenAI key/model configuration is separate from Word templates.
- Case creators and optional assigned owners, with owner assignment required before starting analysis.
- Creator/owner labels on MIP cards and per-user workload Metrics.
- Existing cases retain their previous owner; their creator is initialized from that owner where available.

- Default-on Word wrap with wrapped-line number alignment, paragraph styles, and alignment controls.
- Separate Standard and RAW archive buttons/previews with distinct working-file inclusion rules.
- Package reports list and Standard exports exclude report Markdown and editor images.

- Markdown line-number gutters, formatting toolbar, drag/drop report images, image deletion, and Word embedding.
- GitHub-style table/strikethrough/autolink/task-list rendering with styled previews.
- Workbench asset manager with persistent category, existing file list, and deletion.
- Report images are included in MIP ZIPs; removed generated IOC Markdown duplicate.

- Dedicated Tasks tab with task cards, names/descriptions, priorities, and three task states.
- Package directory contents alongside readiness without reason fields; removed asset usage tracking.
- Expanded report editors now support Raw and locally rendered Preview tabs.

- Four narrative editors with Key Findings replacing Threat Overview; legacy content/templates remain compatible.
- References table with saved links rendered under Appendices → Links in Word reports.
- Removed AI action controls and client logic; Generate Word Report uses local generation.
- Retained OpenAI settings, dependencies, and backend helper code for future extraction features.

- Indicator save feedback explicitly confirms iocs/indicators.csv.
- On-demand AI narrative summaries from uploaded case files and rewording of analyst drafts.
- Draft preview, explicit application, and independent saving preserve analyst control over reporting.

- Spreadsheet-style indicator cells with fixed type, value, and description headers.
- File CSV imports match headers case-insensitively, support reordered columns, and ignore extras.
- Pasted CSV supports optional headers or the fixed three-field order.

- Dedicated Indicators tab with inline rows, custom columns, additive CSV imports, and AI report ingestion.
- Saved indicator table populates the Word report in both manual and AI modes and exports as defanged CSV.
- Removed IOC and MITRE mapping Markdown editors from the Report tab.

- Five-stage workflow with automatic migration of existing case progress and deferred work.
- Start analysis unlocks the workspace; ZIP generation is limited to Packaging & Delivery and Completed.
- Completed cases are read-only until explicitly reopened; MIP regeneration remains available.
- Report editor Markdown sources are excluded from MIP delivery.

- Actionable completion checklist at Packaging & Delivery and Review & Export.
- Completion blockers link directly to category review, tasks, and deferred stages.
- Blocked completion automatically opens the checklist and records details in audit.
- Clarified why ZIP acknowledgment does not satisfy case completion.

# v0.3.1

- Expand/collapse each report editor, including keyboard escape and focus handling.
- Local Markdown-to-Word generation without an API key or AI request.
- Manual editing of mapping, IOC, and appendix sections.
- Open the latest Word report independently of AI settings.
- Upload the edited DOCX as the canonical final report with an optional hidden backup.

# v0.3.0

- Detailed tasks with title, body, and editing.
- Per-user encrypted OpenAI keys, model selection, and private Word templates.
- Four manual Markdown report editors with syntax highlighting.
- Evidence-grounded AI draft ATT&CK/MBC and defanged IOC tables, with deterministic appendix links.
- Source review, persisted generation progress, and automatic Word report saving.
- Backup/replace choice; backups excluded from previews, source reading, and MIP export.
- Formatting-preserving template injection and Markdown-to-Word tables, links, and code.

# v0.2.0

- Automatic unique system case numbers and optional Vortex/XSIAM/JIRA references.
- Dedicated case creation page; dashboard shows existing cases only.

- Recentered the application on assembling the deliverable during analysis.
- Added MIP board with separate lifecycle and category-readiness indicators.
- Four case tabs: Workbench, Package, Report, Review & Export.
- Automatic six-folder package creation and non-destructive legacy asset migration.
- Titled/editable RE notes, private autosaved drafts, and opt-in delivery of notes.
- Categorized asset uploads with descriptions and script usage commands.
- Done / No applicable work / Deferred stage closure, with tracked deferrals.
- Pending / Populated / Not applicable readiness, reset when content changes.
- Reviewed ZIP exports with generated README, manifest, hashes, and acknowledged outstanding items.
- Omit untouched optional templates and legacy sample directories from delivery.
- Preserved account management and existing case data.
