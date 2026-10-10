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

Add Task and Edit task use full-workspace dialogs rather than expandable card forms. Descriptions have the report editor’s line numbers, syntax highlighting, preview, heading styles, default-on Word wrap, tables, alignment controls, and image insertion/drop/deletion. Shared Format, Insert, and View dropdown menus group commands in every Markdown editor. Cancel or Escape closes the task dialog without submitting description edits. Image uploads are saved immediately to the case; remove an unused image with its X button. Task images are stored with report-editor assets and preserved in RAW case backups, with task associations rebuilt during import.

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

## Analyst Tools Workspace

The authenticated **Tools** tab sits between Metrics and Users and opens a full-width,
case-independent workspace. CyberChef is the first utility. It retains its operation
search, draggable recipes, input/output tabs, settings, files, and recipe import/export.
Tools are lazy-loaded into retained panels: switching secondary tabs or using
**Expand / Restore** does not recreate the iframe. Arrow keys, Home, and End select
tools; Escape restores the expanded workspace when focus is in the parent page.
Reloading or leaving the Tools page ends that retained in-memory session. CyberChef
may retain its own settings and explicitly saved recipes in browser local storage.
No Tools database tables, migrations, case transfers, or automatic saves are added.

### Install and deploy CyberChef locally

The integration pins the official [CyberChef v11.5.0 release](https://github.com/gchq/CyberChef/releases/tag/v11.5.0),
commit `8cd426dd4f40f1423912d5fad91b578a86a65112`, under Apache-2.0 (Crown Copyright).
The official compiled ZIP has SHA-256
`f6478925d3eaa16ec08626a85f5b85eed10d531a5e18700615fed7ecb024cccf`.
Dependency notices remain in the bundle; the upstream license is also included at
`vendor/cyberchef/LICENSE`. No upstream development repository is committed.

From the application directory, before starting Gunicorn:

```sh
python3 scripts/install_cyberchef.py
```

The Python 3.10+ installer downloads that exact official production release,
validates its checksum and archive paths, and installs all assets in
`vendor/cyberchef/dist/`. It renames the versioned HTML entry to `index.html`.
The original ZIP is retained for CyberChef’s local Download CyberChef control.
The official bundle is already built; Node.js is unnecessary for installation or
Flask production runtime. Flask startup never downloads or builds anything.
Generated assets are ignored by Git: include this installation step in release
packaging and provision them on every application instance. Install with a deployment
account that can write the application folder, before starting the hardened systemd
service (which grants runtime write access only to `data/`). The service account needs
read access to the resulting files. Restart is not necessary after installation;
reload the workspace to use new assets. Avoid replacing assets during active recipes.

For an offline deployment, transfer the official ZIP via your approved process:

```sh
python3 scripts/install_cyberchef.py --archive /path/to/CyberChef_8cd426dd4f40f1423912d5fad91b578a86a65112.zip
```

An optional `--destination /path/to/dist` installs elsewhere. Set Flask's
`app.config['CYBERCHEF_DIR']` to the matching absolute path when customizing deployment.
Do not put these assets in Flask's public `static/` directory or expose them with
an unauthenticated Nginx alias. The existing `deploy/nginx.conf` forwards `/tools/`
to Gunicorn and requires no additional location block. All vendor requests use the
same existing session authentication, including active-account, password-change,
and session-version checks. No second backend or authentication mechanism exists.

To update, review upstream changes/security advisories, choose a release, and change
`VERSION`, `COMMIT`, `SHA256` in `scripts/install_cyberchef.py` using the official release
metadata. Update `vendor/cyberchef/README.md`, its license if needed, and this section;
run the installer and the verification checklist below. The installer validates the
expected entry and `assets/main.js` layout before replacing the installed directory.
For a source build instead, check out that commit in a separate build directory and
follow its upstream Node/npm/Grunt production build instructions; the installer
intentionally accepts only the checksum-pinned official ZIP.

### Routes, registry, and the next tool

- `/tools`: selects the first enabled, permitted registry entry.
- `/tools/<tool_id>`: selects a registered tool; unknown/disabled IDs return 404,
  permission failures return 403.
- `/tools/cyberchef/app/`: authenticated HTML entry, with an injected MARE stylesheet.
- `/tools/cyberchef/app/<path:filename>`: authenticated vendor assets, workers, and
  the virtual `mare-theme.css` / `mare-palette.css` files.

`analyst_tools.py` stores immutable `AnalystTool` metadata in
`app.extensions['analyst_tools']`. Entries include identifier, name, description,
icon, Flask endpoint, type (`embedded` or `native`), enabled flag, and optional
existing permission name. Navigation is generated from those entries. No plugin
loader or database is needed. CyberChef is registered first.

To add a native Flask tool, define its routes in a normal `register_*` module,
then register it after `register_tools(app, db)` in `app.py`:

```python
from analyst_tools import AnalystTool, register_tool, require_tool

@app.get('/tools/example/app/')
def tools_example():
    require_tool(app, db, 'example')
    return render_template('example_tool.html')

register_tool(app, AnalystTool(
    identifier='example', name='Example', description='A native analyst utility',
    endpoint='tools_example', tool_type='native', permission=None,
))
```

Use a standalone tool template inside the retained iframe and the existing MARE
stylesheet/components. Tool CSS/JavaScript can be referenced by that template.
Every backend route must call `require_tool`, including download and data routes,
to enforce enabled state and any existing role permission. Normal Flask session and
CSRF rules still apply; POST forms must include the existing session `csrf` token.
No new case endpoint or permission is required by default. Only register trusted
application code, with unique lowercase identifiers. `register_tool` rejects
invalid/duplicate metadata. Enabled/permitted tools appear automatically without
editing main navigation or workspace JavaScript.

For another embedded JavaScript application, register its authenticated HTML
endpoint in the same way. Keep compiled assets outside `static/`, protect every
asset route, retain relative asset paths, and provide its own isolated theme and
reviewed CSP. The workspace handles lazy initialization and retained iframe state
for either type. Review download, worker, and sandbox requirements per application.

### Theme and security

`resources/cyberchef-theme.css` loads **inside** CyberChef and overrides upstream
CSS variables and Bootstrap controls. Its authenticated `mare-palette.css` import
extracts the canonical `:root` block from `static/mare.css`, so dark backgrounds,
borders, gold accents, and status colors track MARE. Typography follows MARE's
system-font stack while editors retain monospace fonts. No vendor JavaScript is
modified. On updates, verify upstream theme variable names, panel selectors,
editor colors, dialogs, dropdowns, hover states, and worker paths; keep overrides
isolated to this iframe.

Processing happens in the browser. Input/output/recipes are not automatically
submitted to Flask or saved to cases. This integration does not exchange messages
or inject vendor output into the parent DOM. CyberChef's built-in share links may
include recipes/input in a **URL fragment** (not a server query parameter); treat
shared URLs and explicitly saved recipes as sensitive. Imported recipes and output
are untrusted analysis material.

The iframe permits scripts, same-origin access (needed for local workers/storage),
and downloads; it disallows popups, forms, and top navigation. Scripts plus
same-origin access do **not** isolate a compromised trusted vendor application
from MARE's origin. This is a compatibility choice for the official frontend,
not a security boundary. Deploy only reviewed, checksum-verified assets. Stronger
origin isolation would require a separately authenticated origin and is out of scope.

Vendor responses disable caching, set same-origin framing, prevent MIME sniffing,
and apply a CSP that permits local/blob workers, fonts, images, inline vendor
scripts/styles and dynamic evaluation needed by upstream. It denies external
connections, nested frames, objects, and form submission. Existing MARE CSRF/session
protections remain unchanged. `connect-src 'self' blob: data:` supports local assets
and file/blob processing, but prohibits outside API requests. CyberChef operations
such as **HTTP request** and **DNS over HTTPS**, remote URL inputs, and any other
operation fetching third-party resources will fail under this policy. Local OCR
assets are included; inspect the browser Network panel for any future operation's
external requirements. Documentation links can open only when browser/sandbox
restrictions permit; popup links are restricted. Do not silently relax the CSP to
make network operations work. Offline analysis works after the local workspace and
its required assets have loaded, although access to the MARE host/session is still
required for newly requested assets. No service worker/offline cache is introduced.

### Troubleshooting and manual verification

Missing `dist/index.html` produces a setup message (HTTP 503), with the installation
command shown to administrators and a contact-administrator message for other users.
A blank/loading iframe: inspect its HTML and asset responses for 302 login/account
redirects, 404 files, CSP violations, or expired sessions. Confirm the complete
bundle was installed and that Nginx proxies every `/tools/` path through Flask;
do not rewrite the app entry to `/static/`. Check permissions and the pinned checksum.

Automated coverage is in `tests/test_tools.py`. Run:

```sh
.venv/bin/python -m pytest -q
node --check static/tools.js
```

Manual browser release checklist (repeat through the production HTTPS proxy):

- Sign out: Tools is absent; vendor entry, JS, CSS, and workers require login.
- Sign in without opening a case: Tools opens CyberChef; all scripts, fonts,
  images, dynamically loaded modules, and workers return 200 with local URLs.
- Search **From Base64**, drag it into the recipe, input `SGVsbG8=`, and verify
  output `Hello`. Run manual and automatic bake; add/reorder/remove operations.
- Open a local file, switch input/output tabs, export output, and import/export
  a recipe. Verify standard settings and search controls.
- Exercise a worker-backed operation and local OCR if used; check Network and
  console for asset errors or unintended outbound requests.
- Inspect operation sidebar, recipe, input/output, toolbar, dialogs, menus,
  scrollbars, hover/selection, and typography against the MARE dark/gold palette.
- Temporarily register a second local test utility; navigate with mouse and
  keyboard, then return to CyberChef and confirm recipe/input/output survive.
- Expand, resize, and Restore at 1366×768 and 1920×1080; confirm state survives
  and the application panels fit without clipped controls or nested page scrolling.
- Verify session expiry/forced-password redirects, disabled/permission-gated tools,
  and the missing-assets message; inspect browser console for unexpected errors.
- Confirm external HTTP/DNS operations are blocked by policy, while local
  decoding, file downloads, and recipes work. Validate HTTPS Nginx/Gunicorn asset
  MIME types and worker requests; do not enable public vendor caching/aliases.

## Markdown Editors (CodeMirror 6)

MARE uses the official CodeMirror 6 packages for Markdown source editing. The
editor owns text rendering, the caret, selections, wrapping, and its built-in line
number gutter in one scroll container. There is no textarea highlighting overlay,
custom gutter measurement, or independent scroll synchronization. The migration
leaves Markdown storage, report section identifiers, API payloads, authentication,
MIP packaging and backup/import/export formats unchanged. Word prose defaults to Aptos when the template has no explicit Normal font; explicit template fonts and code styles are preserved.

### Migration inventory and capabilities

- **Report sections:** the four existing source fields, shared Format/Insert/View menus,
  headings, quotes, code fences, bold/italic, bullets, links, generated tables,
  HTML/tab-delimited table conversion, alignment containers, figure captions,
  image picker/drop/paste, manual saves, configurable autosave, Raw/Preview, and
  Expand/Restore remain supported. Numbered lists are also available in Format.
- **Tasks:** the same shared component and toolbar run inside existing Add/Edit
  workspace dialogs, with existing image section/storage IDs and preview endpoints.
- **MITRE ATT&CK/MBC:** dynamically created Markdown editors use CodeMirror, retain
  their identifiers, and save through the existing manual/autosave mapping routes.
- **Markdown files:** `.md` and `.markdown` files opened through the existing file
  editor use CodeMirror and submit the original `content` field. Other file types
  retain their ordinary text editor.
- Notes/drafts, CSV imports, case metadata, HTML-table input, and the generated
  copyable MITRE prompt are plain-text/form controls and retain their existing
  behavior. They were not the custom Markdown editors.

Word wrap and line numbers default to enabled; View preferences reconfigure CodeMirror
without changing text or selection. Markdown and fenced-language highlighting,
line numbers, local search/replace (Ctrl/Cmd-F), undo/redo, and selection management
come from official packages. Tab indents inside the editor; Ctrl-M (Shift-Alt-M on macOS) toggles Tab
back to focus navigation using CodeMirror's keyboard accessibility behavior.
Escape retains the existing dialog Cancel / report Collapse behavior. Expanded
report focus handling respects keys already handled by CodeMirror, so search-panel
Escape does not also collapse the workspace. Existing Markdown previews still use
the server renderer and its sanitization, without changing the source document.

Autosave reads the CodeMirror document and compares the submitted snapshot with
current text. A response never recreates an editor or replaces new typing, cursor,
history, or scroll state. Expand/Collapse retains the same EditorView and uses
CodeMirror layout measurements and a logical scroll snapshot. Task dialog Cancel
still resets its form content intentionally. Stored content remains plain Markdown;
CodeMirror does not render untrusted Markdown as live HTML in the source editor.

Existing maximum lengths remain enforced (100,000 for report/mapping sources and
20,000 for tasks). An edit that would increase a document beyond its limit is
rejected as a transaction rather than partially truncating a paste. Existing stored
content is loaded intact. Original syntax colors are replaced with the shared MARE
palette; code-source boxes no longer add borders/padding that can change wrapping.

### Format, Insert, and View

Every source editor has three compact menus. **Format** provides Heading 1–6,
Normal text, Bold, Italic, Strikethrough, Inline code, Fenced code block, Bulleted
list, Numbered list, Blockquote, Horizontal rule, Indent/Outdent, and the existing
MARE Left/Center/Right alignment containers. **Insert** provides Link, Image,
Table, Paste Table, Fenced code block, and Horizontal rule. **View** provides Word
Wrap, Line Numbers, Active Line Highlight, and Code Folding only. Dedicated
right-aligned **Show Preview / Hide Preview** and **Expand / Collapse** buttons
invoke the existing handlers and follow actual pane/workspace state, including
keyboard changes. They wrap gracefully on narrow screens and remain above the
editor in expanded mode. Preview is shown only where the existing renderer is
supported. Task dialogs already use an expanded workspace, so
the additional expansion command is disabled there. Mapping/file editors can
expand without changing their document or editor instance. Escape restores them.

Heading commands change the current logical line, replacing an existing ATX
heading prefix. Block commands affect all intersecting selected logical lines;
a selection ending exactly at the beginning of a line excludes that last line.
Duplicate/overlapping line selections are processed once. Prefix edits map all
selection ranges through the transaction. Inline commands wrap selected text,
remove matching surrounding markers when repeated, or insert paired markers with
the caret between them for an empty selection. Each custom transaction is undoable.
Official indent commands handle selected lines; the Markdown language supplies
Enter/Backspace list continuation behavior. Find/Replace remains Ctrl/Cmd-F.

Multiple selections support Ctrl-click (Cmd-click on macOS) and Alt-drag rectangular
selection. Official heading/fence folding uses gutter controls and Ctrl-Shift-[ / ]
(Cmd-Alt-[ / ] on macOS); Ctrl-Alt-[ / ] folds/unfolds all. Active-line, matching
selection, and bracket highlights use the subdued MARE palette. View preferences
use compartments, retaining content, selections, history, and a logical scroll
anchor; they are local to each mounted editor and reset to defaults on reload.
No preferences database or external completion/AI service is introduced. Existing
Markdown HTML-tag completion sources remain available; no aggressive completion
popup extension is added for prose.

**Images:** Insert → Image, image-file drop, or image-only clipboard paste uses the
existing authenticated `/cases/<id>/report-images` endpoint and normalized PNG files
under `reports/sections/assets/` in the MIP. Rich clipboard data containing text
continues to paste text normally. The existing per-case monotonic figure sequence
allocates numbers and survives deletion/backup/import; existing captions are never
renumbered. Inserted `::: figure` containers center both the image and italic
`*Figure X:*` caption in preview and Word. Type the description after the caption.
Asset listing/deletion and Standard/RAW packaging conventions remain unchanged.
Manually edited caption numbers do not change the stored allocation sequence.

**Table:** Insert → Table opens a MARE dialog for 1–20 columns and 1–100 **body rows,
excluding the header**. It creates a header, separator, and the requested empty
body rows, adds blank-line boundaries even inside existing prose, and places the
caret at the first header cell. Invalid dimensions leave the dialog open. Undo
removes the entire insertion in one step.

**Paste Table:** Open Insert → Paste Table and paste spreadsheet TSV or clipboard
HTML, or enter HTML table markup. Valid clipboard HTML takes precedence; otherwise
TSV is used. The first row becomes the header. CRLF/LF, empty cells/rows, uneven
widths, and literal pipes are normalized without dropping extra columns. Cells use
text extraction from an inert parsed document, never injected clipboard HTML.
Merged-cell text appears once at the top-left; covered rowspan/colspan slots remain
empty and missing cells are padded. Nested tables are flattened into their parent
cell's text; CSS layout, formulas, and advanced table formatting are not retained.
Very large/malformed spans are bounded to 1,000 columns and existing row count.
Editing the paste input clears captured clipboard HTML so the edited text wins.

Preview prose uses locally available Aptos, Segoe UI, or Arial. Source and preview
code use JetBrains Mono, Cascadia Code, Consolas, Menlo, then system monospace.
No font files are bundled. Word accepts a single family rather than a CSS font
stack: generated prose supplies Aptos only when Normal has no explicit font;
explicit template fonts/headings remain intact and code retains Consolas.

Add commands in `frontend/markdown-commands.js` and the menu metadata in
`frontend/markdown-toolbar.js`. Use the existing EditorView/EditorState transactions,
respect read-only state, isolate custom undo steps, and emit changes through the
shared component so autosave continues to work. Use official CodeMirror commands
where suitable. The installed Markdown package provides parsing, folding and
list continuation; it does not supply heading/inline toolbar commands. Rebuild
the local bundle after edits. Never create a second source layer or gutter.

### Frontend dependencies and build

JavaScript dependencies are pinned to exact versions in `package.json`, with
transitive versions and integrity hashes in `package-lock.json`. Source is in
`frontend/markdown-editor.js`, `frontend/markdown-commands.js`,
`frontend/markdown-toolbar.js`, and `frontend/markdown-editor.css`; esbuild is the
single frontend bundler. This repository previously had no npm build system.
Use Node.js 20+ and npm on a build/development machine:

```sh
npm ci
npm run build:editors
```

The build produces local files in `static/vendor/codemirror/`: `markdown-editor.js`,
`markdown-editor.css`, and `THIRD_PARTY_LICENSES.txt`. Keep these generated production
assets with the source and lockfile when publishing a release. The full fenced-
language bundle is approximately 1.6 MB before HTTP compression. License texts for
production dependencies are bundled alongside it. No runtime CDN, dynamic external
module service, or Node process is required to run Flask/Gunicorn. No frontend build
or dependency download happens at application startup. `node_modules/`, browser
reports, and test output are ignored by Git.

### Shared API, theming, and adding an editor

Add a named textarea with `data-markdown-editor`; its initial text and existing
field name are preserved:

```html
<label>Markdown source
  <textarea name="content" data-markdown-editor aria-label="Markdown source"
            maxlength="100000">Initial Markdown</textarea>
</label>
```

The local bundle in `base.html` initializes marked textareas before page scripts.
It hides each source field and mounts CodeMirror; the textarea is only a synchronized
HTML form submission/validation target. New dynamically inserted fields need
`window.MareEditors.init(container)` or `window.MareEditors.create(textarea)`.
Do not manipulate the hidden textarea's value or selection to edit a mounted
instance. Use the component API:

```javascript
const editor = window.MareEditors.get(textarea);
editor.getValue();
editor.setValue(markdown);                  // Silent load; same-value updates are no-ops.
editor.setValue(markdown, {notify: true});   // Deliberate programmatic change notification.
editor.selection();                        // {anchor, head, from, to}
editor.setSelection(anchor, head);
editor.insert(markdown);                   // Undoable transaction replacing selection.
editor.setWordWrap(true);
editor.setPreference('numbers', false);     // wrap / numbers / active / folding
editor.command('h2');                      // Shared undoable formatting commands.
editor.insertBlock(markdown);              // Blank-line boundaries around a block.
editor.setReadOnly(true);
editor.focus();
editor.measure();                          // After showing/resizing a panel.
const unsubscribe = editor.onChange((text, update) => { /* mark unsaved */ });
unsubscribe();
editor.destroy();                          // Cleanup; restore the plain source field.
```

`setValue` maps selections through a minimal change and defaults to excluding loads
from undo history. `insert` creates a distinct undo step. Normal document changes
synchronize the submission field and dispatch its bubbling `input` event, preserving
existing dirty-state listeners. `formdata` events read current CodeMirror content;
form resets synchronize the editor. Disabled fieldsets and readonly fields use
CodeMirror read-only/editable facets, and the server's original workflow/CSRF checks
remain authoritative. All marked editors receive the shared menus. Report/task
sections retain their existing image picker; image uploads are disabled for mapping
and standalone file editors without an associated MARE upload workflow.
Image events in report/task sections go through the existing upload routes and
insert the existing `::: figure`, asset URL, and caption syntax as transactions.

The CodeMirror theme and HighlightStyle in `frontend/markdown-editor.js` use
`static/mare.css` variables (`--bg`, `--panel`, `--panel-2`, `--text`, `--muted`,
`--accent`, `--accent-dim`, `--line`, `--ok`). The companion CSS scopes scrollbar and
search-panel rules to `.mare-editor-host`. Rebuild after changing frontend sources.
Keep decoration styling inside CodeMirror; never reintroduce a separate text layer
or apply legacy global textarea styles to `.cm-content`.

If an editor does not load, inspect the console and Network tab for missing local
JS/CSS, stale cached assets, or a CSP blocking CodeMirror's generated scoped styles.
Confirm both bundle files were deployed together and rebuild with `npm ci` followed
by `npm run build:editors`. A visible unenhanced textarea means the frontend failed
to initialize; fix asset loading before relying on previews/toolbar/autosave.
Production security headers must permit the editor's dynamically generated styles;
this migration does not weaken existing application headers.

### Editor regression verification

Enhancement checks: change all six headings and Normal, repeat inline toggles,
format multiline/multiple selections, fold headings/fences, toggle each View
preference while scrolled, and verify undo/redo. Insert tables in the middle of
prose; test invalid sizes, body-row counts, empty/uneven TSV, literal pipes,
clipboard HTML precedence, and merged cells. Verify images/captions in both
preview and Word, retained asset deletion, and template font preservation.


Server compatibility tests are in `tests/test_markdown_editors.py`; real browser
interaction/geometry tests are in `tests/browser/markdown-editor.cjs`. The browser
suite starts a temporary Flask instance with its own database, accounts, case,
images, and Word template; it never uses the live `data/` directory. Install a
Playwright browser once on a development machine, then run:

```sh
npx playwright install chromium
npm run test:editors
.venv/bin/python -m pytest -q
```

Alternatively, reuse an installed Chrome browser:

```sh
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm run test:editors
```

`PYTHON_BIN` selects another Python environment with the project requirements;
`MARE_EDITOR_TEST_PORT` changes the default localhost test port (8779). The suite
checks existing saved Markdown, a 700-line document, beginning/middle/end typing,
gutter/line-block and caret coordinate agreement, wrapping, scrolling, desktop/laptop
resizes, retained expansion state, toolbar transactions, history, search, images,
previews, concurrent manual/automatic saves, reloads, Word generation, tasks,
MITRE editors, and Markdown-file submission. The old implementation had confirmed
wrap mismatches because syntax spans added inline padding/borders; both gutter
scripts also rebuilt every line on scroll. These components have been removed.

Manual release checklist:

- Open saved reports/tasks/mappings and verify source text is unchanged; also edit
  a `.md` file and save/reload it through the existing file route.
- Type continuously in long documents at the top, middle, and bottom. Mix inline
  code, fenced Python/shell/JavaScript, long URLs, tabs, Unicode, and blank lines.
- Scroll using wheel/trackpad, scrollbar, arrows, and Page Up/Down. Verify the
  built-in gutter follows the visible logical lines and typing follows the caret.
- Toggle wrapping around long paragraphs and resize to 1366×768 and 1920×1080;
  repeat at 125%/150% zoom and with OS scrollbars always visible.
- Apply bold/italic/headings/bullets/links/tables/alignment to selections. Undo and
  redo. Exercise search and replace and keyboard focus exit from the editor.
- Upload/drop/paste images and check figures/captions, image deletion, and ordinary
  rich-text clipboard pastes containing both text and images.
- Expand/collapse and toggle Raw/Preview without losing document, selection,
  history, or scroll; confirm malicious preview markup remains sanitized.
- Keep typing during autosave and manual save responses. Save, reload, generate a
  Word report, and check content and figures. Confirm completed/not-started cases
  remain read-only and existing CSRF/workflow rules still reject unauthorized edits.
- Repeat critical editing flows in supported Chromium, Firefox, and Safari browsers
  through production HTTPS/Nginx/Gunicorn; check for console errors and asset failures.

## Case Tags

Tags are shared, human-readable strings. Analysts choose their own conventions,
for example `MAL-REDLINE_STEALER`, `TA-APT41`, `TECH-PERSISTENCE`, or `PHISHING`.
MARE does not interpret prefixes. Names retain their entered spelling, with
surrounding whitespace trimmed; Unicode case-folded names prevent duplicates.
Names may contain 1–120 characters, without control characters.

### Workbench and board

The thin **Tags** bar at the top of the Workbench contains assigned chips and one
inline **+ Add tag…** input. Type to search, click a suggestion, or select it with
Arrow Up/Down and Enter. Escape dismisses suggestions. With no suggestion selected,
Enter assigns an exact existing name or creates and assigns the typed name. Partial
matches never implicitly replace the typed name. A **Create “name”** suggestion
makes creation explicit. Assignment-only roles must select an existing tag.
Chip **×** controls remove case assignments while retaining the shared definition.
Hover over a chip for assignment attribution. Writes use normal server-confirmed
forms and CSRF protection, and preserve existing workflow/owner edit restrictions.

On the MIP Board, **Filters** opens a narrow left drawer. Search tags, check multiple
names, choose **Match Any** (OR) or **Match All** (AND), then Apply. Case search combines
with the selected tags. **Clear Filters** removes tag restrictions while retaining
case search and card/table view. Collapse or Escape hides the drawer without
clearing active filters; the Filters button shows the active selection count.
The closed drawer consumes no horizontal space; below 900px it overlays the board.
Cards show up to three subdued chips and a **+N** overflow indicator with remaining
names in its tooltip; all tags are available in the case Workbench.

Search controls return up to 100 matching suggestions; narrow the search for larger
catalogs. Selected board filters remain selected across searches. Controls support
keyboard navigation and use the existing MARE theme.

### Tag Manager and permissions

The authenticated **Tags** navigation item appears between Metrics and Tools.
The compact manager lists Tag Name, Cases, and Actions, supports search and
name/usage sorting, and provides inline creation. Click a name or usage count to
view associated case numbers, names, workflow stages, and owners.

Administrators can rename a tag, merge it into an explicitly selected destination,
or delete it. Rename preserves its ID and immediately changes its display everywhere.
A conflicting name is rejected with a suggestion to merge. Merge shows names and
usage counts, requires confirmation, moves assignments without duplicates, keeps
the destination identity, and deletes the source in one transaction. Existing
destination attribution wins on duplicate assignments. Deletion shows usage and
requires confirmation; it deletes assignments and the tag, never case records.
Creation, assignment, removal, rename, merge, and deletion use the existing audit log.

Custom roles use `tags:read`, `tags:create`, `tags:assign`, and `tags:manage`.
The built-in User role receives the first three; Administrator receives all four.
Case assignment/removal also requires `cases:update`, and existing case edit locks
apply. Related case details require `cases:read`. Custom roles need explicit grants.
Authorization is enforced by the server.

Backend helpers and routes live in `tagging.py`: `/tags`, `/tags/search`,
`/tags/<id>`, `/tags/create`, `/tags/<id>/<rename|merge|delete>`,
`/cases/<id>/tags` (read), `/cases/<id>/tags/create`, and
`/cases/<id>/tags/<tag_id>/<assign|remove>`. These follow existing session-authenticated
Flask conventions rather than adding a second REST authentication system.

### Persistence, migration, and backups

Startup adds only `tags` (ID, display name, unique normalized name, creation time)
and `case_tags` (case/tag IDs, assignment time, optional user), plus the reverse
relationship index and `simple-case-tags-v1` migration marker. Initialization is
repeatable. Foreign keys remove assignments when a case or tag is deleted; user
deletion clears attribution. Cases, reports, numbering, and Markdown editors are
not rewritten. No additional runtime dependencies are required.

If a prototype schema is detected, MARE leaves it untouched, shows a setup message,
and disables tag routes and RAW backup export rather than silently losing tags.
To explicitly convert a known earlier prototype, **stop MARE**, then run:

```sh
.venv/bin/python tagging.py --migrate-prototype data/workflow.sqlite3 --confirm-flatten
```

Use the actual database path if `MARE_DATA_DIR` differs. The command creates and
prints a full SQLite backup path before conversion. It retains original tables
as `prototype_tags`, `prototype_case_tags`, and `prototype_tag_categories`.
Identical case-insensitive names across former groups merge into one shared tag;
the lowest original ID supplies display spelling and creation time. Assignment
collisions retain the earliest assignment and its actor. IDs are remapped, case
records remain untouched, and conversion is transactional. Unknown schemas are
refused. Restart MARE after success. For rollback, keep MARE stopped and restore
the printed full database backup. Historical prototype tables are retained for
manual inspection, not used by the new interface.

Individual RAW backups include optional `tagging` in `case-data.json`:

```json
{"schema_version": 1, "tags": ["MAL-REDLINE_STEALER", "TA-APT41"]}
```

Export All also includes the entire shared catalog in `backup.json`, preserving
unused definitions. Import validates versions, structure, types, lengths, and
duplicate names before restoring any case. Existing normalized names are reused
without overwriting display spelling; missing names are created. Relationships
are restored against newly allocated IDs. Older archives without tag metadata
continue importing; malformed metadata rejects the import with rollback. The
portable format contains no database IDs or attribution: imported assignments get
the import time and unknown actor. Existing owner/user mapping remains unchanged.
Standard MIP deliverables do not include internal tag backup metadata. Older
prototype tag metadata requires explicit conversion rather than a silent import.

### Verification

```sh
.venv/bin/python -m pytest -q tests/test_tagging.py tests/test_backups.py tests/test_case_deletion.py tests/test_archive_modes.py tests/test_api.py
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/tags.cjs
```

The browser check uses an isolated temporary database and verifies partial/exact
Enter behavior, keyboard selection and Escape, long names/many chips, desktop and
narrow drawers, Match All/card overflow, merge, rename, and assignment removal.
For manual release checks, also test custom roles, assignment-only users, empty
results, large catalogs, duplicate creation, confirmation failures, RAW/full
restore on another installation, and drawer use with card/table view. Confirm
case workflow controls and CodeMirror editor/preview/expanded mode remain usable.

### Text Manipulation

Open **Tools → Text Manipulation** for one-shot processing of text, logs, and IOC
lists. Paste into the CodeMirror editor and click a command; the result replaces
the current document. The compact command panel contains Extract, Remove, Replace,
Regex, IP Functions, Misc, and Formatting sections. Its scrolling is independent
of the editor. Clear, Copy All, Undo, Redo, and Word Wrap appear above the editor.
Text and native history remain initialized while switching tool tabs or expanding
the workspace; a page reload clears them. Nothing is saved to cases automatically.

Each changed result is one isolated CodeMirror history transaction, including
large transformations. Undo/Redo buttons track available native history and restore
content and selection without rebuilding the editor. Standard shortcuts are
Cmd+Z / Cmd+Shift+Z on macOS and Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z on Windows/Linux.
Typing and pasting use the same history. Successful commands record a whole-document
replacement even when a nonempty result is unchanged, keeping operation-by-operation
Undo predictable. Clear is also undoable. An already-empty document has no text
change for CodeMirror to record.

Simple line operations, literal splitting, exact line deduplication/counting, and
alphabetical sorting run in a local browser worker. The Regex buttons use
**ECMAScript Unicode regular expressions**, not POSIX ERE/GNU grep: JS escapes,
lookarounds, alternation, and leftmost-first matching apply; POSIX bracket classes
and GNU flags are not supported. egrep and egrep -v return matching/nonmatching
lines; egrep -o returns nonempty matches per line and safely skips zero-length
matches. Split by always uses a literal, nonempty delimiter. Patterns are retained
across commands. Workers time out after two seconds, leaving the input unchanged.

IOC extraction uses validated Python `ipaddress`, URL parsing, and offline IDNA
handling on the local MARE server. IPv6 representations normalize to compressed
form; mapped addresses do not also become standalone IPv4s. All IPs emits IPv4
then IPv6; IPs & Domains preserves cross-type order. Extraction deduplicates;
IP Sort retains duplicates and places malformed lines last with a warning.
Domains use IDNA (Python's built-in IDNA 2003) plus DNS-label/TLD syntax checks,
without DNS or a public suffix list. Consequently a syntactically valid filename
or nonexistent domain can match; extraction does not establish registration or
reachability. Emails use common unquoted mailbox syntax, not every RFC mailbox form.
URLs preserve paths, queries, and fragments; closing prose punctuation is trimmed.

Non-Routable IPs uses the bundled `resources/ip-special-purpose.json` snapshot
of the [IANA IPv4](https://www.iana.org/assignments/iana-ipv4-special-registry/)
and [IPv6](https://www.iana.org/assignments/iana-ipv6-special-registry/) registries,
following [RFC 6890](https://www.rfc-editor.org/rfc/rfc6890). The snapshot was
checked on 2026-10-09 against registries updated 2025-10-09. Longest-prefix matching
honors globally reachable exceptions; False/unspecified designations are removed.
Multicast is excluded explicitly. Unlisted IPv4 is retained; unlisted IPv6 is
retained only in global-unicast `2000::/3`. This is address designation, not live
routing verification, and does not depend on Python-version `is_global` behavior.
Only whole lines containing validated nonglobal IPs are removed. Unrelated lines,
invalid IP-looking text, and log lines containing a private IP remain intact.
For updates, download the official CSV URLs recorded in the JSON, regenerate its
network/global entries, review changed prefixes/exceptions, update snapshot dates,
and run the classification tests. No registry access occurs during processing.

Defang uses `[.]`, IPv6 `[:]`, and http(s) → hxxp(s); Refang reverses these
conventions inside recognized indicators. URL paths/query strings are preserved.
Defanging is idempotent for supported indicators. Refang is heuristic for common
conventions and does not perform network validation.

Format JSON uses four-space indentation and preserves arbitrary-precision numeric
values. Format XML rejects DTDs/entities, performs no external resolution, and
preserves mixed content, existing whitespace-only nodes, and `xml:space` rather
than inserting semantic whitespace. Format Python uses pinned **Black 25.1.0**
with its AST safety check; source is parsed/formatted, never executed. All three
switch the editor's syntax highlighting without replacing its instance. Errors
leave content/history intact. Nested JSON/XML formatting is limited to 150 levels.

IOC/IP, defang/refang, JSON/XML/Python commands explicitly POST text to the existing
local authenticated `/tools/text-manipulation/process` endpoint using session CSRF.
The frontend entry point is `/tools/text-manipulation/app/`. Requests are capped at
2 MiB of UTF-8 input. Responses are not cached; submitted text is not audited or
persisted. There are no third-party processing requests, shell commands, or code
execution endpoints. If editing continues while a request is running, its stale
result is rejected. Install Python requirements before deployment:

```sh
.venv/bin/pip install -r requirements.txt
npm ci
npm run build:editors
```

Node is needed only to build the existing shared CodeMirror bundle and local worker,
not to run Flask. No additional frontend dependencies were added. The Text
Manipulation editor uses the same bundled CodeMirror modules/theme as Markdown,
without Markdown toolbars. Bundled licenses remain under `static/vendor/codemirror`.

```sh
.venv/bin/python -m pytest -q tests/test_text_manipulation.py tests/test_tools.py
node tests/text-operations.cjs
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/text-manipulation.cjs
```

Manually verify large pastes, every command group, errors preserving input,
consecutive Undo/Redo and platform shortcuts, Copy All under HTTPS, Word Wrap,
independent panel scrolling, tab state retention, expanded/restored workspace,
small laptop layouts, and CyberChef recipes after switching tabs. Confirm existing
Markdown editing/preview/autosave still works. Clipboard access requires a secure
browser context; if unavailable, select and copy manually.
