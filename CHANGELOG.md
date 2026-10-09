# Latest update

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
