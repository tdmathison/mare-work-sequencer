# MARE Work Sequencer v0.3.2

A self-hosted Python workbench for building a Malware Intelligence Package while the analyst works. The app collects deliverable content and coordinates progress; it does not execute samples or teach malware analysis.

## Install (Ubuntu, Python 3.10+)

```bash
cd mare-work-sequencer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app app create-admin
python -m flask --app app run --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. No default credentials are provided.

For production, run Gunicorn behind nginx with TLS:

```bash
export MARE_SECURE_COOKIES=1
.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8000 app:app
```

Deployment examples are in `deploy/`. Adjust the hostname, certificate paths, and installation paths. Create `/opt/mare-work-sequencer/data` owned by the dedicated service account before starting the service, and create the administrator with that same account. The service uses the data directory inside the installation. Enable secure cookies only with HTTPS. Keep port 8000 on loopback.

## The core loop

Create a case → collect notes and artifacts → review category readiness → complete the report → review and export the ZIP → close the case after delivery.

The workflow has four stages: **Not started → Malware Analysis → Packaging & Delivery → Completed**.

- **Not started:** edit case details, then click Start analysis. Other tabs and content controls are locked.
- **Malware Analysis:** notes, tasks, uploads, report editors, and report generation are available.
- **Packaging & Delivery:** ZIP generation becomes available. The completion checklist links to unresolved actions.
- **Completed:** view and regenerate the ZIP. Click Reopen case to return to Malware Analysis before editing.

Restrictions are enforced by the server as well as the UI. Existing cases migrate automatically on startup: Initial Triage, Data Collection, and the former Reports stage map to Malware Analysis, with history and deferred reasons preserved. Packaging & Delivery and Completed retain their meaning. Stop the service before replacing application files, then restart it after the upgrade.

The MIP board shows each case's stage and seven package readiness indicators, separately. Create case opens a dedicated creation page. New cases automatically receive a unique, immutable number such as `MARE-2026-000001`, plus a package and report/table templates. An optional Vortex, XSIAM, or JIRA reference is stored separately and included in the exported README and manifest. Existing case numbers are preserved on upgrade.

### Workbench

The default case tab contains the current stage, output-oriented guidance, RE notes, quick categorized uploads, and tasks. Notes have titles and timestamps and can be edited. New-note drafts autosave after typing pauses and are private to the signed-in account. Saved notes are shared with the case team. Select “Include in MIP” to deliver a note; internal notes and private drafts are excluded.

Close a stage as Done, No applicable work, or Deferred. Skipped and deferred work require a short explanation. Deferred stages remain visible until resolved. Progress does not lock earlier findings or prevent adding more content.

### Package

The package has seven folders:

| Folder | Contents |
|---|---|
| reports | Analysis report, executive summary, optional selected RE notes |
| iocs | Hashes, domains, IPs, URLs, other indicators |
| signatures | Detection rules of any applicable type |
| scripts | Decoders, extractors, utility scripts |
| mappings | MITRE ATT&CK and MBC tables |
| supporting | Screenshots, configurations, OSINT references, other evidence |
| samples | AES-encrypted ZIPs created from uploaded samples |

Uploads are routed by category, with a description and optional usage command. They are stored directly in the case's package. Duplicate filenames are rejected; rename before uploading a replacement. Maximum request size is 100 MiB. Scripts are stored and can be edited as text; they are never run.

Uploads to Samples are immediately wrapped in AES-encrypted ZIP archives using the site-wide password configured by an administrator under Settings. The default is `infected`. Changing the password affects future uploads only; existing sample archives retain their original password.

Mark each category Pending, Populated, or Not applicable after reviewing it. Not applicable requires a reason. Reports always apply. New uploads and text edits reset that category to Pending so the dashboard reflects the need for review.

### Report

Edit the four narrative sections and generate a Word report locally from a selected template. Indicators and References have dedicated editable tables; see the reporting section below.

### Review & Export

Review the file preview and checklist. Pending categories, open tasks, and deferred stages are listed. They can be resolved or explicitly acknowledged for export; acknowledgments are included in the manifest and README. The untouched report template or an empty report cannot be exported. The site checks presence and template state, not analytical quality. Samples are excluded by default. Explicitly check the red danger option to include password-protected sample archives; exports containing samples end in `-MAL`.

Export generates `YYYYMMDD-MIP-Case_Name.zip`, containing the seven folders, README.md, manifest.json, selected notes, and file hashes. Empty folders are preserved. Untouched executive-summary and MITRE table templates are omitted from export; the archive preview reflects this. Sample archives are excluded by default; checking the red warning adds them and appends `-MAL` to the archive filename. Export does not automatically complete the case. Completing Packaging & Delivery requires the readiness checklist to be resolved.

Sample uploads are wrapped in AES-encrypted ZIP files under `samples/`; they are never stored as loose source files. The default password is `infected`, and administrators can change it under Settings. A password change applies to future uploads only. There is no SAFE/FULL selector. Sample ZIPs are included in Standard or RAW MIP exports only when the red warning checkbox is selected. Analysts should review supporting evidence before release.

## Upgrade from v0.1

1. Stop the service and back up the entire existing `MARE_DATA_DIR`.
2. Replace application code, templates, and static files with this release. Preserve the data directory and service environment settings.
3. Install requirements in the application virtual environment, then restart the service.

Database additions apply automatically. Existing accounts, cases, notes, and tasks remain. Existing notes default to internal. Old indicators and decoders are copied into iocs and scripts; configurations, network evidence, artifacts, references, and detection guidance are copied into supporting subfolders. Original legacy files remain on disk and existing destination files are never overwritten. Legacy sample directories and obsolete root scaffold files are not exported. Existing reports and signatures remain in their original deliverable folders. Review migrated content before export.

## Accounts and storage

Administrator: cases, account management, and audit. User: cases and own password settings. The case workspace is shared; per-case access controls are not included. Accounts are independent of DropZone.

Creation/reset produces a random 12-character temporary password, displayed once, and requires a password change. Enable/disable/reset actions invalidate existing sessions. Password changes require the current password and matching new passwords of at least 12 characters.

`MARE_DATA_DIR` defaults to `data/` beside `app.py`, regardless of the directory from which the process is launched. A relative override is also resolved against the application directory; an explicit absolute override is honored. It contains SQLite, the private session key, and `cases/<id>/mip/`. Keep it outside publicly served directories. Back up the whole data directory while the service is stopped. Notes, draft text, tasks, and stage history live in SQLite; only selected notes are exported.

## Verification

```bash
pip install pytest
python -m pytest -q
```

Integration checks cover the workbench lifecycle, draft saving, note export privacy, uploads, readiness invalidation, report/export gating, deferred stages, manifests and hashes, legacy migration, CSRF, path traversal, and disabled-account rejection.

## Report generation and settings

Tasks have a title and Markdown description with full-workspace editing. Settings provide private Word template uploads. Reports are generated locally; no API keys or AI dependencies are needed.

### Word template sections

Templates can use matching headings or standalone placeholders:

| Heading | Placeholder |
|---|---|
| Executive Summary | `{{ executive_summary }}` |
| Key Findings | `{{ key_findings }}` |
| Detection Opportunities | `{{ detection_opportunities }}` |
| Reverse Engineering Findings | `{{ reverse_engineering_findings }}` |
| MITRE ATT&CK Mapping | `{{ mitre_attack_mapping }}` |
| MITRE MBC Mapping | `{{ mitre_mbc_mapping }}` |
| Indicators of Compromise | `{{ indicators_of_compromise }}` |
| Appendices | `{{ appendices }}` |

Legacy Threat Overview headings and `{{ threat_overview }}` markers are still accepted for Key Findings, and existing saved Threat Overview Markdown loads as Key Findings. The old source files are retained. Legacy heading text becomes Key Findings in generated documents.

The Report tab contains four Markdown editors: Executive Summary, Key Findings, Detection Opportunities, and Reverse Engineering Findings. Each supports syntax highlighting and expansion. Save explicitly or generate to save the current editor text. Markdown source files stay in `reports/sections/` for editing and are excluded from the MIP ZIP.

Generate Word Report inserts the saved IOC table and References table along with narrative Markdown. Under Appendices it creates a Links subsection containing Link and Description columns; HTTP/HTTPS URLs are clickable in Word. MITRE sections remain available in the template for analyst editing; local generation does not infer mappings.

Newly generated reports are saved under `reports/`. The Generate Word Report control can also create a matching PDF using headless LibreOffice Writer; it defaults on when `libreoffice` or `soffice` is available and can be unchecked to generate DOCX only on other platforms. To provide a PDF manually, convert the Word file and upload the PDF with the same base filename to the Reports category using the Asset manager. The same checkbox controls PDF conversion when saving an edited DOCX. The case number uses the external reference when present, otherwise the six-digit system sequence. A leading `YYYYMMDD:` is stripped from the title; spaces, dots, slashes, and other filename-unsafe characters become underscores, with consecutive underscores collapsed. Open latest Word report downloads the tracked report for local editing. Existing legacy report filenames remain usable until regeneration. RAW backups preserve the tracked report path. Regeneration asks whether to back up the old copy first. Backups are excluded from exports, previews, and source collection.

Word templates can also include optional `{{ case_title }}` and `{{ case_number }}` placeholders. The title omits a leading `YYYYMMDD: ` prefix. The number is formatted as `Vortex #1234`, `XSIAM #1234`, or `JIRA #1234` when an external reference is set, otherwise as `MARE #2026-000001`.

### Indicators

Indicators is a directly editable table with fixed `type`, `value`, and `description` columns. Click a cell to edit. Tab moves across cells, Enter moves down, and either key adds a row at the end. Shift+Enter adds a line break. Add row and Delete manage rows. Save table writes `iocs/indicators.csv`, with defanged delivery copies. Save before generating a report.

CSV file imports require the three headers, matched case-insensitively in any order; extra columns are ignored. Pasted CSV accepts these headers or assumes type,value,description order. Imports append rows, support quoted commas/multiline cells, and reject missing file headers or inconsistent widths. Limits: 10,000 rows, 4,000 characters per cell, 4 MiB per CSV import. Concurrent revisions prevent silent overwrites. Previous custom tables are preserved in `indicator_table_legacy` and normalized to the fixed columns on upgrade.

### References

References is a directly editable table with fixed Link and Description columns, Add row, Delete, and Save table. Saving stages `supporting/references.csv` and resets supporting/report readiness. Saved rows are included under Appendices → Links during Word generation. Save both References and Indicators before generating. Both tables are locked before Start analysis and after Completed; reopen the case to edit.

### Upgrade

Stop the service, replace application files while preserving the data directory, install requirements in the virtual environment, and restart. Database tables are added automatically. Hard-refresh the browser to load the updated scripts and CSS. Existing templates continue to work through the Key Findings compatibility aliases.

## Task cards, package review, and report preview

Case tabs are ordered Workbench, Tasks, Indicators, References, Package, Report, Review & Export. Tasks has an Add Task button that opens a Name/Description/Priority dialog. New tasks start in Not Started. Cards show name, description, priority, and state; Edit task opens a full-workspace dialog to update Markdown, priority, and state (Not Started, In Progress, or Completed). Priority options are Low, Normal, High, and Critical. Existing completed tasks remain completed on upgrade. Completion-checklist task links open the Tasks tab.

Asset uploads retain descriptions but no longer collect or export usage text. Package cards show the relevant directory's files and a Readiness menu. Not applicable no longer requires a reason. Backups remain hidden from file lists and archives.

Expanded report editors have Raw and Preview tabs, defaulting to Raw each time. Preview renders the current editor text locally without saving or calling AI, supporting headings, lists, code, emphasis, links, and tables. Raw HTML is escaped, unsafe URL schemes are blocked, and uploaded case images are rendered; remote image URLs are shown as labels without being fetched. Escape collapses the editor; editing and saving continue through the normal report controls.

## Markdown images and asset management

Report editors have a separate, non-selectable line-number gutter and toolbar buttons for italic, bold, URL, bullets, images, and tables. Long raw lines scroll horizontally so line numbers remain aligned. GitHub-style previews support tables, strikethrough, automatic links, and task lists through markdown-it-py with its GFM-like preset and task-list extension.

Drag an image onto a report textarea or use Insert Image. The image is validated and normalized to a uniquely named PNG in `reports/sections/assets/`, and an `assets/report-image-....png` Markdown reference is inserted. Limits: 10 MiB input and 20 megapixels. Save report sections after insertion. Images are listed below each editor with X deletion controls. Deletion removes the file and references in saved narratives; regenerate Word after changing images. Word generation embeds these local images without fetching remote URLs. MIP ZIPs include the image files while still excluding report section Markdown source files.

The Workbench Asset manager retains the selected category in the current browser session, uploads without leaving the page, lists files in that directory, and supports deletion. Content changes reset readiness. Image deletion and asset deletion are blocked while a Word report is being generated. Completed cases remain read-only until reopened.

`reports/indicators-of-compromise.md` is no longer generated. Legacy copies are excluded from MIP ZIPs and removed when regenerating Word. The tool-managed indicator file is `iocs/indicators.csv`; the saved table is embedded directly into Word.

This update adds Pillow, linkify-it-py, and mdit-py-plugins. Run `pip install -r requirements.txt` inside the application's virtual environment before restarting.

## Standard and RAW archives

Review & Export offers two download buttons and matching Standard/RAW preview tabs. Standard is the stakeholder deliverable: it includes a matching PDF report if present and deliverable files, but excludes the tracked Word report, Markdown under reports/, and all report editor source/image assets under reports/sections/. RAW includes both Word and PDF reports when available, working Markdown, report images, untouched scaffold files, and export-selected notes within the seven MIP directories. RAW filenames end in -RAW.zip, with -MAL appended when samples are included. Both archives exclude backups, symlinks, legacy sample payload directories, and application secrets; neither exports unsaved browser editor changes or generates PDFs during download. README.md and manifest.json are generated in both modes, and the manifest records archive_type. Standard requires a Word report; provide its PDF separately if needed. The Package tab and its file counts show Standard deliverable content.

Report toolbars now offer Word wrap (enabled by default), Left/Center/Right alignment, and Paragraph/Heading 1–6/Quote/Code block styles. Word wrap is a view setting and does not alter saved text. Line-number heights follow wrapped logical lines. Alignment commands wrap the selected/current block in ::: align-left, ::: align-center, or ::: align-right containers; these are supported in preview and Word generation. Save editor changes before downloading RAW so its sources match your work.

## Case ownership and team metrics

New cases record the signed-in creator and default to Unassigned. Select an active owner during creation or in Workbench → Case details. Start analysis remains disabled until an active owner is assigned; the server enforces the same rule. MIP board cards show creator and owner. Metrics lists each user’s created and assigned cases, with In Progress (Malware Analysis, Packaging & Delivery) and Completed counts based on ownership. Existing cases preserve their owner and initialize creator from that owner where known. Creator names are retained if an account is later deleted.

Word template upload and selection are private to each account. Existing template selections are preserved during migration; saved OpenAI settings and their encryption key are removed.

Inserted report images use a centered figure container with a 1px #444 border and a centered italic numbered caption (Figure X:). Edit the caption in Markdown. Figure numbering is per case and continues across deletions. These styles are applied in Preview and generated Word documents.

## Removing accidental or duplicate cases

The system case number is display-only and cannot be changed. At the bottom of a case, Destructive commands lets you permanently delete the entire case by typing its exact system number. Deletion removes its workspace files and case records, including reports, notes, tasks, indicators, references, and history. An audit entry and a reservation of the deleted number remain. Case numbers are never recycled. Deletion works at any stage, but waits for active report generation to finish.

Add Task opens a workspace-sized dialog with a large description editor. Cancel or Escape returns to the Tasks tab.

## Indicator sections

Indicators start in a Default section; existing indicator rows are preserved there on upgrade. Add new section opens a Title/Description form. Each section has its own editable type/value/description table, Add row, and Import CSV. Save table at the top saves every section together. Imports append to the selected section and save all sections, saving any pending edits first.

The generated Word report lists every indicator section beneath Indicators of Compromise, with a subsection heading, description, and table. Empty sections retain their headings and descriptions with an empty table. Delivery indicator values are defanged. `iocs/indicators.csv` contains the type/value/description columns plus section and section_description metadata on each exported row, so grouping accompanies the indicators in the package. Import still matches only type/value/description columns; extra fields are ignored.

Destructive commands appears only at the bottom of Workbench.

Indicator sections have an Edit section action for changing the title and description, including the protected initial section. Additional sections have Delete section, with confirmation before removing that section and its rows from the editor. Save table persists edits and deletions for all sections. The initial section is protected from removal by both the UI and server. Its default title is “Indicators extracted during analysis” and description is “The following table contains indicators extracted during analysis of the malicious artifact.” On upgrade, the previous unmodified Default heading/blank description is updated; analyst overrides are preserved.

## Automatic saving

Settings → Autosave controls your personal interval in whole minutes (default 5, minimum 1). Reopen or refresh case pages after changing it. Report sections, all indicator sections, and references save automatically at that interval, even when their tabs are hidden. Manual save remains available. Autosave preserves edits made during a save and does not rerender table cells or move editor focus. The status beside each editor/table shows save confirmation or errors; failed saves retain unsaved edits and retry at the next interval. Keep the case page open for autosave to run; it is not a substitute for saving before closing the browser. Not-started/completed cases are read-only, and report autosave pauses during generation.

## Import & Export: portable case backups

The top navigation has Import & Export after Settings. Export all cases downloads one ZIP containing a nested RAW MIP ZIP for every case, including Not started and unfinished cases. Each RAW package contains the working files plus case metadata needed to restore saved notes (including internal notes), tasks, readiness, history, deferred work, indicator sections, references, image registrations, and figure numbering. Accounts, API keys, user settings, private drafts, and report backup folders are excluded. Save pending changes first; wait for report-generation jobs to finish.

Import backup accepts an archive produced by Export all cases. It validates paths, package manifests, checksums, size limits, and case metadata before adding anything. A failed import rolls back added case rows and files. Existing cases are never replaced. Importing again creates another set of cases with new unique system numbers. The shared case-number sequence and reserved-number list prevent reuse.

Each imported case retains its exported stage, with the importing account as creator. Ownership is restored only when both the permanent user UUID and username match an account in this instance. Otherwise the owner is Unassigned: use Case details → Save assigned owner to resume at the retained stage. Completed cases can be assigned an owner without reopening them. Saved task states, history, notes, files, indicators, and references are retained. Existing Word documents are preserved byte-for-byte, so any source case number inside their content remains until the analyst edits or regenerates the report.

Limits: 1 GiB upload, 2 GiB total expanded case data, 1,000 cases, 256 MiB per case ZIP or individual file, and 64 MiB per metadata document. For larger backups, adjust these limits and reverse-proxy upload limits together. This format supports the same application version or newer versions that recognize mare-case-backup/1; single RAW MIP ZIPs produced by this version also contain restorable case metadata. Older standalone archives without case-data.json cannot restore case state and must be re-exported with this version.

## User identities and single-case backups

Every account receives an immutable random identifier on creation or upgrade. Database backups preserve these IDs; independently created accounts with the same username have different IDs. Case backups export the assigned owner’s username and ID. Both must match on import; username-only matching is never used. Older backups without owner IDs remain importable but restore as Unassigned. Case stage is retained regardless of whether ownership matches, and fresh system numbers are allocated as before.

The MIP board’s Backup button downloads one case’s RAW package with restorable metadata, regardless of stage. It converts .py filenames to _py.txt (decode.py → decode_py.txt). Import & Export → Import single RAW MIP restores _py.txt filenames to .py before adding the case; matching artifact descriptions are restored too. Filename collisions fail safely. Changing these names can help with extension-based email restrictions, but does not guarantee acceptance by every mail filter. The ordinary RAW download also includes case metadata and is importable; the Backup button performs the additional filename conversion.

## Full installation backup and restore

Administrators have Settings → Back up database & all MIP content. This is a separate restore archive containing data/workflow.sqlite3 plus all persistent files: case directories (including report backups), templates, session/encryption keys, and saved account settings. Accounts, permanent user IDs, ownership, and metadata are restored exactly. Report jobs must finish before backup; active HTTP writes are serialized with the backup on Ubuntu/Linux.

Install the application, stop the service, and unzip this archive into its source directory to restore data/. If MARE_DATA_DIR points elsewhere, restore the contents into that configured directory instead. Restore ownership to the service account, retain the deployment environment/TLS configuration, and restart. Application source and deployment configuration are not included. This archive contains credentials and encryption keys and should be kept private. Use the same application version or a newer compatible version.

## Autosave countdowns

Save buttons for report sections, Indicators, and References now show the remaining minutes:seconds. Default is one minute. Manual saves reset that workspace’s timer, and automatic saves reset it after completion. Timers show Paused for locked workspaces or pending loads/generation, then continue when available. Unchanged automatic saves do not invalidate readiness or increment table revisions. Existing accounts using the former five-minute default migrate to one minute; other configured intervals are retained. Refresh case pages after changing the setting.

## Task Markdown workspaces

Add Task and Edit task use full-workspace dialogs rather than expandable card forms. Descriptions have the report editor’s line numbers, syntax highlighting, Raw/Preview tabs, paragraph styles, default-on Word wrap, tables, alignment controls, and image insertion/drop/deletion. Formatting and Insert dropdown menus group common commands in every markdown editor. Cancel or Escape closes the task dialog without submitting description edits. Image uploads are saved immediately to the case; remove an unused image with its X button. Task images are stored with report-editor assets and preserved in RAW case backups, with task associations rebuilt during import.

### MITRE mapping workflow and report table formatting

In Report, Generate MITRE prompt uses the current content of all four narrative editors, including unsaved changes. Copy the prompt into your preferred external assistant; review its Markdown tables and upload `mitre-attack.md` and `mitre-mbc.md` to `mappings/` using the asset manager. Local Word generation inserts those files into the matching MITRE sections. No external request is made by this application. New cases have an empty mappings directory; unchanged old placeholder files are removed while analyst-edited files are retained.

Generated Markdown, indicator, and reference tables match the provided Word example: Aptos text, blue header with bold white text, thin pale blue borders, alternating pale blue body rows, and a bold first column. Existing tables and the rest of the uploaded template retain their formatting.

### Moving an existing installation

Stop the service before renaming or moving the installation. Keep the complete existing data directory (database, session key, cases, templates, and backups) together and place it in `mare-work-sequencer/data/`. If both old and new data directories exist, keep a backup of both and choose the directory containing your existing accounts and cases; do not merge SQLite databases. Update the installed service WorkingDirectory, ExecStart, and ReadWritePaths to the new location. Remove stale MARE_DATA_DIR overrides from the service or shell if the default data location is desired. Adjust User/Group to your existing service account, reload systemd with `sudo systemctl daemon-reload`, and restart the service. Existing virtual environments may contain absolute paths; recreate `.venv` at the new location and install requirements if it was moved.

## REST API

Create a bearer token in Settings (or `POST /api/v1/tokens`) and send `Authorization: Bearer <token>`. Tokens act as their owner, are shown once, can be revoked, and may expire (`expires_in_days`, 1-3650). Each token is limited to 600 requests per minute per process (override with `MARE_API_RATE_LIMIT`; `0` disables). Accounts with a forced password change cannot use the API. Errors are JSON: `{"error": "..."}`. List endpoints accept `limit` (max 500) and `offset` and return `total`.

Each endpoint requires a role permission (see `GET /api/v1/permissions`). New permissions: `metrics:read` and `templates:manage` (both granted to the User role), plus the existing `backups:manage` and `audit:read`.

| Area | Endpoints |
| --- | --- |
| Identity | `GET /me`, `GET/POST /tokens`, `DELETE /tokens/<id>`, `GET /permissions` |
| Admin | `/roles`, `/roles/<name>`, `/users`, `/users/<id>`, `/settings` |
| Cases | `GET/POST /cases`, `GET/PATCH/DELETE /cases/<id>`, `POST /cases/<id>/stage`, `POST /cases/<id>/reopen`, `GET/PUT /cases/<id>/readiness` |
| Case content | `/cases/<id>/tasks`, `/notes`, `/draft`, `/assets` (multipart upload with `category` and `file`), `/indicators`, `/references` |
| Report | `GET/PUT /cases/<id>/report`, `/report/mappings`, `POST /report/generate`, `GET /report/job`, `POST /report/final` (multipart `report`, optional `backup=1`, `generate_pdf=0`), `GET /report/download?format=docx|pdf` |
| Report images | `GET/POST /cases/<id>/report/images` (multipart `section` and `image`), `GET/DELETE /cases/<id>/report/images/<name>` |
| Word templates | `GET/POST /templates` (multipart `template`), `PUT /templates/selected` (`{"template_id": "..."}`), `GET/DELETE /templates/<id>` |
| Export and archive | `POST /cases/<id>/archive`, `POST /cases/<id>/backup` |
| Backups | `POST /backups/export` (all cases), `POST /backups/import` (multipart `backup`), `POST /backups/import-raw` (single RAW MIP), `POST /backups/database` (Administrator) |
| Metrics | `GET /metrics` |

Example:

```
curl -H "Authorization: Bearer $TOKEN" https://host/api/v1/cases
curl -H "Authorization: Bearer $TOKEN" -F report=@edited.docx https://host/api/v1/cases/1/report/final
curl -H "Authorization: Bearer $TOKEN" -X POST -o backup.zip https://host/api/v1/backups/export
```

Case-modifying endpoints follow the same stage rules as the web interface (owner required, and no edits in Not started or Completed). Upload limits match the web interface. Add the `/api/v1/` block from `deploy/nginx.conf` when using nginx so large imports are accepted.
