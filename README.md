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

Indicators start in a Default section; existing indicator rows are preserved there on upgrade. Add new section opens a Title/Description form. Each section has its own editable type/value/description table, Add row, and Import (CSV/STIX). Save table at the top saves every section together. Imports append to the selected section and save all sections, saving any pending edits first.

The generated Word report lists every indicator section beneath Indicators of Compromise, with a subsection heading, description, and table. Empty sections retain their headings and descriptions with an empty table. Delivery network indicator values are defanged; non-network values and descriptions remain literal. `iocs/indicators.csv` contains the type/value/description columns plus section and section_description metadata on each exported row, so grouping accompanies the indicators in the package. Import still matches only type/value/description columns; extra fields are ignored.

Destructive commands appears only at the bottom of Workbench.

Indicator sections have an Edit section action for changing the title and description, including the protected initial section. Additional sections have Delete section, with confirmation before removing that section and its rows from the editor. Save table persists edits and deletions for all sections. The initial section is protected from removal by both the UI and server. Its default title is “Indicators extracted during analysis” and description is “The following table contains indicators extracted during analysis of the malicious artifact.” On upgrade, the previous unmodified Default heading/blank description is updated; analyst overrides are preserved.

## Automatic saving

Settings → Autosave controls your personal interval in whole minutes (default 5, minimum 1). Reopen or refresh case pages after changing it. Report sections, all indicator sections, and references save automatically at that interval, even when their tabs are hidden. Manual save remains available. Autosave preserves edits made during a save and does not rerender table cells or move editor focus. The status beside each editor/table shows save confirmation or errors; failed saves retain unsaved edits and retry at the next interval. Keep the case page open for autosave to run; it is not a substitute for saving before closing the browser. Not-started/completed cases are read-only, and report autosave pauses during generation.

## Backup & Restore

The privileged **Backup & Restore** workspace has focused Export backup and Import
archive tabs, selective cases/families/tags, encrypted complete recovery, automatic
validation and an explicit reviewed Import plan. Complete snapshots include every
persistent table and managed file, credentials, keys, historical case-number
reservations, family reports and actual assets. Threat actor profiles remain disabled.

See [Backup & Restore](docs/backup-restore.md) for the persistent-data inventory,
passphrases, scope/dependencies, merge conflicts, archive compatibility, limits,
host prerequisites, failure rollback, and clean-instance recovery instructions.

## User identities and single-case backups

Every account receives an immutable random identifier on creation or upgrade. Database backups preserve these IDs; independently created accounts with the same username have different IDs. Case backups export creator and assigned-owner usernames and identifiers. Imports resolve these roles by exact username, including older backups without user UUIDs; source numeric IDs are never used for destination attribution. Existing-case updates preserve the local creator and owner unless incoming ownership is explicitly selected; selecting incoming ownership applies the same username lookup. Matching an inactive account does not bypass the existing active-owner editing restriction. Case stage is retained regardless of whether ownership matches, and fresh system numbers are allocated as before.

The MIP board’s Backup button downloads one case’s RAW package with restorable metadata, regardless of stage. It converts .py filenames to _py.txt (decode.py → decode_py.txt). Backup & Restore → Import archive restores _py.txt filenames to .py before adding the case; matching artifact descriptions are restored too. Filename collisions fail safely. Changing these names can help with extension-based email restrictions, but does not guarantee acceptance by every mail filter. The ordinary RAW download also includes case metadata and is importable; the Backup button performs the additional filename conversion.

## Full installation backup and restore

Use **Backup & Restore → Complete application backup** to create an encrypted
recovery archive, then import it through the same workspace on a clean compatible
installation. Replacement requires acknowledgment, retains a temporary rollback
copy and ends existing sessions; sign in using restored administrator credentials.
Settings links to this consolidated workflow. The offline installation restore
script continues to support legacy plaintext installation ZIPs, not the encrypted
`mare-backup/1` envelope. Follow the [recovery procedure](docs/backup-restore.md)
for secrets, schema compatibility, host prerequisites and limitations.

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

Create a bearer token in the API tab (or `POST /api/v1/tokens`) and send `Authorization: Bearer <token>`. Tokens act as their owner, are shown once, can be revoked, and may expire (`expires_in_days`, 1-3650). Each token is limited to 600 requests per minute per process (override with `MARE_API_RATE_LIMIT`; `0` disables). Accounts with a forced password change cannot use the API. Errors are JSON: `{"error": "..."}`. List endpoints accept `limit` (max 500) and `offset` and return `total`.

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
| Backups | `POST /backups/export` (all cases), `POST /backups/import` (multipart `backup`), `POST /backups/import-raw` (single RAW MIP), `POST /backups/database` (retired, 410; use Backup & Restore) |
| Metrics | `GET /metrics` |

Example:

```
curl -H "Authorization: Bearer $TOKEN" https://host/api/v1/cases
curl -H "Authorization: Bearer $TOKEN" -F report=@edited.docx https://host/api/v1/cases/1/report/final
curl -H "Authorization: Bearer $TOKEN" -X POST -o backup.zip https://host/api/v1/backups/export
```

Case-modifying endpoints follow the same stage rules as the web interface (owner required, and no edits in Not started or Completed). Upload limits match the web interface. Add the `/api/v1/` block from `deploy/nginx.conf` when using nginx so large imports are accepted.

## Analyst Tools Workspace

The authenticated **Tools** dropdown follows API and precedes Settings, opening a full-width,
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
  Both provide the shared **Show Preview / Hide Preview** control for current,
  unsaved Markdown, including tables, and support preview in expanded mode.
  Toggling preserves editor state and does not save. Preview remains available
  in readable read-only cases; editing and saving remain restricted.
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

Tags are shared, human-readable strings, stored in uppercase. Examples are
`MAL_REDLINE_STEALER`, `TA_APT41`, `TECH_PERSISTENCE`, and `PHISHING`.
MARE does not interpret prefixes. Surrounding whitespace is trimmed, then the
original input must contain 1–120 ASCII letters, digits, or underscores before
uppercasing. `Apt_29` becomes `APT_29`; spaces, hyphens, dots, and non-ASCII letters
are rejected with “Tags may contain only letters, numbers, and underscores.”
Invalid characters are never silently replaced or removed. Backend validation in
`tagging.name()` is authoritative for creation, rename, restore and synchronization.
The unique canonical key and SQLite write triggers prevent concurrent duplicates;
creating an existing name reuses its tag, while conflicting renames are rejected.
Existing JSON Workbench routes use these same helpers; there is no separate public
REST tag API or bulk-creation bypass.

On the next application startup, the transactional, idempotent
`uppercase-ascii-tags-v1` migration uppercases valid existing names and consolidates
case-only duplicates into the lowest existing numeric ID. All case associations
are preserved without duplicates; an existing canonical association retains its
assignment metadata. Audit records identify consolidated IDs. The current portable
tag format has no tag UUIDs or synchronization identity mappings; case UUIDs and
historical revision definitions remain intact. Keep your normal pre-upgrade
installation backup before starting the upgraded application.

Invalid legacy names remain unchanged, including their IDs and associations.
**Tag Manager** lists them with remediation links: an authorized manager can rename
them to a valid name, or explicitly merge into a valid destination (with confirmation).
No automatic replacement of spaces/hyphens is performed. Local snapshots and backups
retain unresolved legacy names so the application and backups remain usable, but
imports of those names fail visibly in import review. Remediate them before sharing
new backups. The older prototype-table conversion still requires the explicit
backed-up command below; invalid prototype names abort that conversion safely and
must be remediated before retrying.

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
with the selected tags and **Stage** checkboxes. Select any combination of Not
started, Malware Analysis, Packaging & Delivery, and Completed, then Apply.
Dashboard metric tiles apply these same stage filters immediately: In progress
selects both analysis and packaging. Stage tiles retain other search/tag filters;
their counts reflect those filters before the stage restriction. **All MIPs** clears
all search, tag and stage restrictions and displays the total case count.
**Clear Filters** also clears search, tag and stage restrictions while retaining
card/table view and saved sorting. Every table column except Actions supports
ascending/descending sorting by clicking its header (or activating it with the
keyboard). The selected column and direction are saved to your account in the
database, persist across logins, and also order card view. Text columns sort
case-insensitively, Stage follows workflow order, and Reviewed sorts by the
fraction of categories reviewed. Accounts without a saved sort retain newest-first
ordering. Sorting retains the current search, tag and stage filters. Collapse or Escape hides the drawer without
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
{"schema_version": 1, "tags": ["MAL_REDLINE_STEALER", "TA_APT41"]}
```

Export All also includes the entire shared catalog in `backup.json`, preserving
unused definitions. Import validates versions, structure, types, lengths, and
duplicate names before restoring any case. Existing normalized names are reused
with uppercase spelling; missing valid names are created. Incoming invalid tag names
are reported with their value and reason in the import review; nothing is silently dropped. Relationships
are restored against newly allocated IDs. Older archives without tag metadata
continue importing; malformed metadata rejects the import with rollback. The
portable format contains no database IDs or attribution: imported assignments get
the import time and unknown actor. Existing owner/user mapping remains unchanged.
Incoming revision hashes are verified against the exact archived names first.
Only then are tag names compared canonically, avoiding conflicts/repeated updates
for otherwise identical snapshots differing only in tag case. A new case restored
from older mixed-case metadata receives a canonical descendant revision; original
revision UUIDs, definitions and ancestry are retained, and subsequent identical
imports remain unchanged.
Standard MIP deliverables do not include internal tag backup metadata. Older
prototype tag metadata requires explicit conversion rather than a silent import.

### Verification

```sh
.venv/bin/python -m pytest -q tests/test_tag_names.py tests/test_tagging.py tests/test_backups.py tests/test_case_deletion.py tests/test_archive_modes.py tests/test_api.py
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

## Application-wide MIP Search

The **SEARCH** tab immediately after MIP BOARD searches saved case data and actual
artifact contents. User and Administrator roles use their existing permissions;
custom roles need `cases:read`. Files and archives additionally require
`cases:assets`, with indicator, reference, and report read permissions applied to
the corresponding content. Case ownership is not a read restriction in the current
application. Unassociated archives are restricted to administrators.

Search uses case-insensitive literal substrings, retaining punctuation in hashes,
IPs, domains, URLs, and technical identifiers. Refanged and defanged forms match
(e.g. `evil.example.com` matches `evil[.]example[.]com`, and `https://` matches
`hxxps://`). No user regular expressions, AI, URL fetching, or external service is
involved. Excerpts retain the stored text and are escaped before highlighting.

Search covers case numbers, external references, title, description, creator and
owner; saved notes; task titles, descriptions, priority and state; indicator
section titles/descriptions and individual rows; reference rows; artifact
descriptions; report Markdown sections; filenames and relative paths. Generated
indicator/reference CSV mirrors are searched by filename while their current
contents are represented by database rows, avoiding duplicate content findings.
Unsaved editor content and private note drafts are outside the index.

Readable formats include UTF-8 (with optional BOM) and BOM-marked UTF-16 text:
CSV, TXT, Markdown, JSON/JSONL, XML, HTML, YAML, Python (including email-safe `.py_`),
PowerShell, JavaScript/TypeScript, shell/batch/VBS scripts, YARA/signatures, logs,
configuration files, and other listed source formats. HTML is searched as literal
source text, never rendered. Word `.docx` paragraphs/tables are extracted with
python-docx; text PDF pages with pypdf. Install the updated dependencies:

```sh
.venv/bin/python -m pip install -r requirements.txt
```

### Stored archives and source previews

Existing Standard/RAW MIP ZIPs are discovered in the configured data directory's
`archives/` subtree and within current `cases/<id>/mip/` package categories. The
`archives/` directory is optional and can be populated by an administrator using
normal filesystem deployment tools; there is no new upload endpoint. MIP ZIP
exports still stream downloads and **are not automatically retained**. A ZIP
previously downloaded to an analyst's computer is not searchable on the server.
Installation backups, imported temporary files, account folders, samples, report
backups, keys, databases, and private/dot files are not searched.

A single `mare-mip/2.0` manifest identifies Standard or RAW packages and associates
an archive with a current case using its system case number. Renumbered imported
cases may leave an archive unassociated. RAW `case-data.json` supplies archived
case fields, notes, tasks, indicators and references; account/job/history records
are not indexed. Different retained ZIP versions remain distinct sources within
their associated case group. ZIP contents are read in memory, never unpacked into
case folders; nested ZIPs are not recursively searched. DOCX containers are handled
only by the document parser.

Results group by case/package, with ten whole groups per page. Multiple occurrences
within a source artifact become one row with a count and up to three excerpts.
**Open finding** shows read-only extracted content and locations from the exact
indexed source version, including archived members. **Open case/section** links
reach the associated workspace; current assets also provide a download link.
Saved notes/tasks link to their item anchors where possible. The server accepts
opaque finding IDs and rechecks permissions and source identity. Changed/deleted
sources produce an explicit stale result; run the search again. Once a refresh
replaces that version, its previous finding ID expires. A current workspace file
is never substituted for an archived match.

### Indexing, limits, and coverage

`MARE_DATA_DIR/search-index/index.sqlite3` is derived local data containing readable
case text. Protect it like the source data. It uses the existing configured data
location, has restrictive directory/file permissions, and is excluded from
installation backups. Stop workers and remove `search-index/` to rebuild it; the
next search repopulates it without modifying source cases or artifacts.

The first search and later invalidations launch a background refresh. Successful
mutation requests invalidate the index across Gunicorn workers through a shared
marker; report-job completion also invalidates it. A subsequent search refreshes
it, and ongoing searches poll during indexing. Independently changed files and
retained archives are rechecked on searches at most two minutes after the last
refresh. File identities include device, inode, size, modification and change
timestamps. Unchanged file extractions are reused, so PDFs and DOCX files are not
reparsed per query. A process-shared lock serializes refreshes; atomic publication
retains the previous snapshot during indexing. Results are explicitly incomplete
while indexing or when limits are reached.

Limits: 16 MiB per extracted file/member; 2 million characters per artifact;
64 MiB total indexed original text; 40,000 database records; 20,000 file/member
records; 90 seconds per refresh (plus at most one parser timeout); 4,000 ZIP/DOCX
members, 128 MiB per ZIP container/declared expansion, and member paths limited to
2,048 characters/32 components; a 200:1 ZIP compression ratio limit
for members larger than 1 MiB; PDF limit 500 pages; ten seconds per document
extraction with an eight-second CPU budget and a 512 MiB address-space cap on
Linux (macOS enforces time/content limits, but lacks the Linux memory cap).
Search processing has a five-second result-processing budget; totals are labeled
partial if reached. Each displayed group is capped at 200 findings; narrow the
query/filters when that limit is shown. The coverage drawer lists up to 500 skip
reasons and the total skipped/partial count.

Unsafe member paths, duplicate members, and symlinks reject an entire archive.
Encrypted, oversized, unsupported, binary, unreadable, and nested artifacts have
explicit skip/partial reasons; safe member filenames may still be searchable.
Scanned PDFs with no extractable text are reported as unsupported for content
search; OCR is out of scope. A parser failure does not imply successful coverage.
PDF extraction order/layout can differ from its visual page, and Word extraction
is text-only rather than a reproduction of document formatting.

Validation commands:

```sh
.venv/bin/python -m pytest -q tests/test_mip_search.py tests/test_archive_modes.py tests/test_backups.py tests/test_case_deletion.py tests/test_ownership.py tests/test_installation_paths.py tests/test_reporting.py
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/mip-search.cjs
```

Manual checks: run a long search during background indexing; verify metadata,
indicator rows, report tables and PDF pages; switch category/source/stage filters;
compare two retained archive versions; open an archived result after changing the
workspace; verify a stale warning after changing its ZIP; try a restricted role;
check pagination, Clear/Enter, and laptop layout; confirm skipped-file coverage and
that no source HTML executes. No reverse-proxy route or timeout changes are needed;
normal search requests do not wait for document extraction.

## Executive Metrics scorecard

See [Metrics count definitions and verification](docs/metrics-counts.md) for the
inventory/activity distinction and production comparison queries.

METRICS presents **MARE performance overview** with 4, 12 (default), 26, or 52
full Monday–Sunday weeks for activity, alongside an all-time inventory. Reporting
uses `MARE_DISPLAY_TIMEZONE` (UTC by default); the current partial week is excluded
from activity. The inventory always includes existing cases regardless of dates.
Legacy timestamps without an offset are interpreted as UTC. No server-local timezone or browser timezone is
used; week boundaries follow the configured IANA display zone, including DST.
Changing the period affects activity and comparisons, not current snapshots.

- **Total MIPs:** distinct eligible existing cases, using the shared Board scope.
  Imports/restores and missing timestamps do not remove cases from this inventory.
- **Completed MIPs:** existing cases currently in Completed, independent of history
  and reporting period. In-progress and pipeline cards likewise use current state.
- **Created during period:** creation timestamps in the selected period, compared with the
  immediately preceding equal-length period. Missing, malformed, or future
  creation dates are excluded from activity or aging as appropriate.
- **Completed during period:** distinct cases with reliable completion history in the
  period. The existing history records the stage being exited: the final
  Packaging & Delivery exit (stage 2, outcome Done, No applicable work, or
  Deferred), followed by a recorded Reopened event or remaining as the terminal
  history entry of a currently Completed case, establishes completion. Adjacent
  legacy stage-2 entries are treated as a run; only the final qualifying exit is
  used. Completed status alone supplies no event date. Missing/inconsistent
  history is not backfilled. Deleted cases and their deleted history are absent.
- **Recompletion:** count at most once per case in each reporting period, using
  its earliest qualifying completion in that period. A reopened case may count
  again in a later period. Weekly totals use exactly the same selected events.
  Completed is a workflow state, not proof of delivery.
- **In progress:** current Malware Analysis plus Packaging & Delivery cases.
- **Median cycle time:** elapsed days from creation to the selected completion
  event. Cases with missing/invalid creation dates or history predating creation
  (including imports) are excluded from timing, but valid completion events still
  count as output. The dashboard reports exclusions and valid timing coverage.
  Differences are in days, rounded to one decimal; unavailable periods are explicit.
- **Comparisons:** percentage changes use one decimal. A zero prior period and
  positive activity displays “No prior-period baseline”; two zeros display
  “No change.” No fabricated historical values are used.
- **Pipeline and age:** current snapshots across all cases, independent of period.
  Age is whole elapsed days since creation for all unfinished cases, grouped into
  0–7, 8–14, 15–30, and 31+ days. Invalid/future dates have unavailable age.
  These buckets are descriptive, not an SLA or an overdue assessment.
- **Analyst workload & output:** Created uses the stored creator identifier and
  selected period; Assigned includes all currently owned cases; In Progress uses
  current ownership in stages 1–2. Completed is explicitly a **current-owner
  attribution fallback**, because history has no owner-at-completion identifier.
  It is not a historical ownership claim or an analyst ranking. Disabled accounts
  remain visible, deleted creators retain their saved names, and unassigned or
  missing owners receive explicit rows. Expand the all-time snapshot to see the
  previous dashboard's all-time creator and current completed-owner counts.

The chart uses lightweight, locally served native SVG and JavaScript rather than
an external chart service. Hover, keyboard focus, Enter/Space, or touch shows the
week range and created/completed counts; an expandable weekly table supplies the
same data without JavaScript. Narrow screens scroll the chart inside its panel to
keep date labels readable. Aggregation lives in `performance_metrics.py`, uses
batched read-only queries over existing records, and adds no schema or dependencies.
The existing API metrics response remains unchanged. The board currently filters
text and tags, not stages or age; snapshot counts therefore do not link to
misleading unfiltered board results.

Metrics regression checks:

```bash
.venv/bin/python -m pytest -q tests/test_performance_metrics.py tests/test_ownership.py tests/test_navigation.py tests/test_api.py
# Use installed Playwright Chromium, or set MARE_BROWSER_EXECUTABLE to local Chrome.
node tests/browser/performance-metrics.cjs
```

The browser test uses an isolated temporary database and checks populated/empty
scorecards, all reporting periods, long/disabled analysts, desktop/mobile layout,
chart mouse/keyboard/touch details, local-only requests, and the active METRICS tab.

## ZIP modification timestamps

Standard/RAW MIP exports and case backups preserve source-file modification times
while streaming content and calculating the existing SHA-256 checksums. Repackaging
copies entry timestamps, compression, and file/directory attributes; email-safe
`.py` → `_py.txt` renaming does not change modification times. Generated README,
notes, manifests, case metadata, backup indexes, and nested case ZIP entries use
export-generation time. Real category directories preserve their modification
times; generated directories receive current timestamps.

ZIP's standard timestamp stores **modification time only**, has two-second
precision, and contains no timezone. Conversion consistently uses the deployment
host's local timezone (including its `TZ` configuration) for writing and restoring.
Use the same timezone on export and restore hosts; configuring both to UTC avoids
DST ambiguity. ZIP alone cannot identify the original timezone or distinguish
ambiguous DST times. Valid source dates are retained; dates before 1980 or after
2107 are clamped to ZIP's minimum or maximum date without crashing.

RAW/full-case imports restore artifact and represented directory modification
times after checksum validation in the staging directory. Renaming Python files
and moving the directory preserve these times. Imports reject timestamp application
for invalid calendar dates, dates beyond ZIP's range, dates over 24 hours in the
future, or the exact legacy default `1980-01-01 00:00:00`; those files retain their
extraction-time modification date. Unsupported filesystem timestamp operations
are safely skipped. Original dates for legacy entries containing the 1980 default
cannot be recovered from the ZIP alone. Case creation dates, stage history, and
account metadata follow their existing import behavior unchanged.

## Interactive API documentation

Open **API → Interactive API reference** while signed in. Swagger UI lists the
implemented public `/api/v1` operations, schemas, required role permissions,
uploads, downloads, and error responses. The **Raw OpenAPI specification (JSON)**
link serves `/api/openapi.json` under the same web-session protection as the API
tab. Internal Workbench JSON routes are not public APIs.

Create a bearer token using the existing token controls. Choose **Reveal new
token once**, copy it to secure storage, then use Swagger's **Authorize** control
and enter only the secret (without `Bearer `). Revelation uses the existing web
session and CSRF protection; the secret is not embedded in the initial HTML or
specification and is never automatically supplied to Swagger. Authorizations
remain in memory only, are cleared when leaving the page, and are not stored in
local/session storage. Each Execute checks the current web session first, so a
logged-out or expired documentation session cannot continue executing requests.
External API clients still use bearer authentication independently of the web
session; logout does not revoke tokens. Revoke them explicitly when appropriate.

Expand an operation, select **Try it out**, enter parameters/body or choose a
file, then **Execute**. Inspect the actual status, headers, response body, and
file download link. Nothing runs automatically. **Writes and deletes affect real
application data**: use isolated test cases, review identifiers, and respect
existing permissions, workflow/revision checks, sample-export acknowledgements,
and report-replacement choices. A successful request status is not a guarantee
that every staged backup case applied: inspect individual synchronization
outcomes. The database/installation backup additionally requires the built-in
Administrator role. Tokens, passwords, uploaded material and API responses are
sensitive; do not share screenshots or copied requests containing credentials.

The existing Python workflow remains at the bottom, displayed by the shared
CodeMirror 6 bundle with Python highlighting, line numbers, horizontal scrolling,
and read-only selection/copy. **Copy code** copies only the original code. It
uses `MARE_TOKEN` from the environment, never a rendered secret. Clipboard access
requires a secure browser context (HTTPS or localhost); select/copy directly if
browser policy prevents the button from using the clipboard.

Swagger UI **5.33.3** is pinned in `package-lock.json`; official compiled assets
are committed under `static/vendor/swagger-ui/` with Apache-2.0 LICENSE/NOTICE and
origin information. No Node.js or downloads are needed at Flask startup or in
production. Reproduce assets at build time with Node.js 20+:

```sh
npm ci
npm run build:api-docs
npm run build:editors
```

The initial `npm ci` requires access to the configured npm registry (or a populated
offline cache). Runtime documentation uses only local assets and same-origin
requests. The external validator and query-string configuration are disabled.
The relative server URL includes Flask's `SCRIPT_NAME`; a proxy mounting the app
under a prefix must configure the WSGI script root correctly. No CORS, CSRF or
existing Content Security Policy settings are weakened. If adding a stricter CSP
at the proxy, verify Swagger/CodeMirror's runtime style elements and Swagger's
local blob-based downloads with that policy; do not allow broad external hosts
or unsafe script execution. Missing assets or an unavailable session/spec show
an actionable loading message. Check `/api/openapi.json`, browser console/network
errors, installed asset paths, proxy prefix/HTTPS forwarding, and login state.

Maintain contracts in `api_documentation.py`, separate from presentation code.
The builder derives paths/methods and permission metadata from registered public
Flask routes; request/response schemas and operational descriptions are explicit.
When editing an API, update its contract and response examples/constraints too.
The coverage test fails for missing or obsolete contracts and mismatched methods,
paths, parameter names or permissions. Fields returned from extensible storage
records allow additional properties; this is not a generated client SDK contract.
To update Swagger, pin a reviewed `swagger-ui-dist` version, rebuild local assets,
retain licensing, and verify scoped overrides in `static/api-documentation.css`.
Python examples reuse `frontend/python-example.js` and the existing MARE theme.

```sh
.venv/bin/python -m pytest -q tests/test_api_documentation.py tests/test_api.py tests/test_navigation.py
npm run test:api-docs
# Optional installed Chrome instead of Playwright's Chromium:
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm run test:api-docs
```

The focused tests validate OpenAPI 3.0.3 using pinned Swagger Parser with external
reference resolution disabled. The browser test creates a temporary database,
executes GET/write/upload/download/error requests, verifies session gating,
checks local-only loading and narrow layouts, and tests read-only Python copying.
For manual release verification, also test User/custom-role permissions, revoked
and expired tokens, logout in another tab, HTTPS behind the deployed proxy (with
any configured path prefix/CSP), large upload limits, and native keyboard
selection/copy. No real cases should be used for destructive verification.


## Canonical indicator types, STIX export, and unified import

Indicators retain three columns (`type`, `value`, `description`) and all existing
sections and Word-report behavior. Type is now a native searchable combobox using
the backend catalog in `indicator_types.py`. Search by canonical name, friendly
label, or an explicit alias. Use arrows/Enter to choose a suggestion and Tab to
continue editing. Common aliases such as `SHA256`, `SHA-256`, `SHA1`, `MD5`,
`domain-name` and `registry-key` normalize when a valid row is saved. Exact official names take precedence over old aliases: `URI` now selects the distinct MISP `uri` type, not `url`.
Unknown, ambiguous, invalid and unfinished rows remain saved drafts; their
original text is retained and **Needs correction** explains the problem. A generic
`IP`/`IPv4`/`IPv6` never establishes source or destination direction.

The mappings follow the [OASIS STIX 2.1 standard](https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html)
and the official MISP [attribute-to-STIX mapping](https://misp.github.io/misp-stix/documentation/misp_attributes_to_stix21.html)
and [STIX-to-attribute mapping](https://misp.github.io/misp-stix/documentation/stix21_to_misp_attributes.html).
STIX object types and MISP attribute types are distinct. Canonical names are
recorded in `misp:type` labels for MISP attributes and `mare:type` for the retained software-name extension, never in `indicator_types`.

| Canonical types | STIX pattern properties |
| --- | --- |
| `domain`, `hostname` | `domain-name:value` (label distinguishes hostname) |
| `url` | `url:value` |
| `software` | `software:name` (human-readable software/application name) |
| `mobile-application-id` | Non-detection MISP `x-misp-attribute` contextual representation (literal identifier) |
| `text`, `comment`, `other`, `chrome-extension-id`, `edge-extension-id` | Non-detection MISP `x-misp-attribute` contextual representation (literal values) |
| `ip-src`, `ip-dst` | `network-traffic:src_ref` / `dst_ref`, with explicit address type and value; IPv4 and IPv6 supported |
| `mac-address` | `mac-addr:value` |
| `filename` | `file:name` |
| `md5`, `sha1`, `sha256`, `sha512` | `file:hashes` with MD5, SHA-1, SHA-256, SHA-512 keys |
| `filename\|md5`, `filename\|sha1`, `filename\|sha256` | Same-file name AND hash constraints |
| `email-src`, `email-dst` | `email-message:from_ref.value` / `to_refs[*].value` |
| `email-subject` | `email-message:subject` |
| `email-attachment` | `email-message:body_multipart[*].body_raw_ref.name` |
| `mutex` | `mutex:name` |
| `regkey`, `regkey\|value` | Registry key; key AND `values[*].data` for key/data composites |
| `x509-fingerprint-sha1`, `x509-fingerprint-sha256` | `x509-certificate:hashes` |

Validation checks hash lengths/hex digits, IP addresses, DNS/IDNA names, supported
absolute HTTP/HTTPS/FTP URLs, colon-separated MAC addresses, email addresses and
explicit Windows registry hive paths. Composites require exactly one `|` separator;
ambiguous delimiters require correction. Filenames, mutexes, subjects and registry
data are literal strings; quotes/backslashes are escaped using STIX grammar.
No URLs are visited or names resolved.

### Complete storage catalog versus export capabilities

The searchable selector loads **all 194 official MISP attribute types** from the
locally bundled **PyMISP 2.5.34.4** `describeTypes.json`, plus MARE's retained
`software` extension (195 unique choices). It does not list every STIX SDO/SCO or
MISP object template. Exact canonical names are preserved, including `AS` and
`named pipe`; tag uppercase rules do not apply. One option per canonical type
shows a category, friendly label and compatibility/search aliases, without alias
duplicates. Searching `text`, `free text`, `unknown`, `miscellaneous` or `catch all`
finds contextual choices. `unknown` is a search term, **not** an automatic import
conversion. Type help is available beside the field and through `aria-describedby`.

The source/version/file SHA-256 and BSD-2-Clause license live in `vendor/misp`.
See [catalog maintenance](vendor/misp/README.md) for an offline wheel-based update
procedure. Flask reads the catalog locally; runtime conversion now uses pinned PyMISP/misp-stix Python dependencies and never requires runtime internet. On an explicitly connected maintenance machine:

```sh
python3 -m pip download --no-deps --only-binary=:all: pymisp==2.5.34.4 -d /tmp/mare-misp-catalog
python3 scripts/update_indicator_catalog.py /tmp/mare-misp-catalog/pymisp-2.5.34.4-py3-none-any.whl --expected-version 2.5.34.4
```

The central catalog exposes `export` capability, help and default detection intent.
UI rows show **Native STIX mapping**, **MISP-compatible representation**, or
**Requires correction/additional data**. Fallback notices are informational in
`stix.notices`; they do not populate `stix.issues` or block download.

- **71 native-capable choices**: 68 official detection-pattern mappings, two
  official descriptive mappings (Campaign/Vulnerability), and the retained MARE
  `software:name` extension. The complete tested profile is in
  [stix21-capabilities.json](vendor/misp/stix21-capabilities.json). New native-capable
  types default to non-detection contextual export unless detection intent is
  explicitly supplied by import/API; legacy native rows keep their previous intent.
- **122 contextual choices**: all remaining non-binary catalog entries use the
  official converter's `x-misp-attribute` representation, including ports,
  contextual prose, application IDs, rule text and attributes without a faithful
  scalar native round trip. Native-capable rows also use this representation when
  required to retain non-detection intent. Types and values are never silently
  substituted. Fallback alone is not a validation error.
- **2 binary-required choices**: `attachment` needs the actual attachment bytes;
  `malware-sample` needs sample/archive bytes and associated metadata. A filename
  or hash alone is not enough. Their rows and CSV remain saved, but complete STIX
  export is withheld with a precise correction message until the needed content
  can be represented. This three-column editor does not accept binary attachments.

The former gap comprised 165 types for which the initial implementation had no
fallback; the exact list and upstream constraints are retained in the profile.
There is no remaining blanket “mapping unavailable” restriction for valid scalar
MISP attributes. Validation uses type-aware MARE normalization and PyMISP's
attribute validator. Invalid hashes, IPs/CIDRs, ports, composites, timestamps and
other typed values still require correction; their saved draft data is retained.
A catalog entry is not a promise that every possible string is valid for its type.

Runtime conversion uses proper MISP event/attribute models through pinned
`misp-stix==2026.10.12` and `pymisp==2.5.34.4`. The isolated adapter in
`misp_indicator_export.py` calls the upstream custom writer for fallback; it does
not invent a new object format. The protected fallback/model hooks are version
coupled and covered by actual importer tests. Internal model organization/event
objects and synthesized observations are not published. Native patterns use
validated/refanged components and upstream property syntax; source values remain
unchanged. No observation timestamps, vendor information or extra sample content
are invented.

`row_meta.to_ids` optionally records explicit detection intent. It survives API
saves, native/custom imports, RAW backup and synchronization. Contextual/default
new types use `false`; legacy native types retain their previous detection behavior.
`text`, `comment`, `other` never become fake detection patterns, even if an incoming
attribute explicitly carries detection intent: their custom representation retains
the flag instead. Imports do not default arbitrary content to IDS-enabled. Source
row UUID/creation time, original-type provenance, section identity and descriptions
remain stable. A capability/converter upgrade alone does not revise saved metadata.

All official types can be saved through manual edit, autosave, CSV, API, RAW backup
and synchronization. `text`/`comment`/`other` preserve punctuation, Unicode,
whitespace and line breaks within the existing 4,000-character cell limit. They
are not validated, defanged or refanged as network indicators. Unknown names
remain flagged drafts; the import preview offers explicit **Use text**/**Use other**
choices without changing value/description. The original type is retained in
`row_meta.original_type`, RAW/sync metadata and an escaped `mare:original-type`
label on contextual exports. Nothing is silently converted to a catch-all.

`mobile-application-id` is the canonical MISP identifier type. Existing MARE
`android-package`/Android/package aliases normalize on the next ordinary
save/autosave, retaining exact values, row UUID/creation time and original-type
provenance. Normalization advances the revision once; subsequent unchanged saves
are stable. Existing RAW snapshots are validated unchanged before normalization,
so their revision/hash integrity is preserved. Identifiers remain literal, including
dots and case, in CSV and STIX. A generic `software:name`/Software SCO imports as
`software`; reverse-DNS appearance never supplies Android semantics. Legacy
explicit package-labelled patterns and Software SCOs remain importable. Software
SCOs with CPE/SWID/vendor/version/language/extensions require review rather than
silently losing their structured content.

CSV serialization is type-aware: only recognized network **value cells** are
defanged. It preserves column order, quoting, section metadata, descriptions,
filenames, hashes, mutexes, registry data, software names and dotted packages.
Explicit CSV-only network mappings (such as `domain|ip`, IP/hostname-plus-port, generic email and `uri`) transform only network components; ports remain literal. These types use the verified MISP-compatible export when a native pattern would not preserve semantics. Generic legacy IP/email drafts retain defanged CSV delivery without inventing a
source/destination role. STIX uses the same component validation pipeline with
refanged values, escaping pattern literals afterwards. Supported `[.]`, `[@]`,
`[:]`, `hxxp`/`hxxps` combinations (including `hxxps[:]//`) round-trip; URL paths
retain case. Exports never mutate stored values, resolve DNS or fetch URLs.
All manual/autosave/download/package/import-regeneration paths use these helpers.

### Saving, identity and outputs

The top actions are **Add new section | Download STIX | Save table**. Manual save
and autosave use the same backend flow as REST indicator PUTs. Valid aliases are
canonicalized, and CSV is refreshed at `iocs/indicators.csv` with existing defanging
and section columns. Valid tables also produce `iocs/indicators.stix.json`, a STIX
2.1 Bundle of native Indicators, supported contextual attributes and standard Grouping objects for section titles,
descriptions and membership. Patterns use validated/refanged network values, not
defanged display text. Direction is never invented. `valid_from` records the local
row's creation/validity time, not an inferred first-seen observation.

Rows have stable `row_meta` identities/creation/modification timestamps alongside
section JSON, and sections retain `stix_meta` for their Grouping. The internal row ID keeps its `indicator--` prefix for compatibility; exported native/custom object prefixes use the same stable UUID. This adds no new
indicator tables and leaves the three-column layout unchanged. Unchanged saves
retain object IDs/timestamps and table/case revisions. Actual row or section edits
update the corresponding object's modification timestamp. RAW backups preserve
metadata; synchronized STIX is a derived artifact excluded from content hashes,
avoiding a regeneration/revision loop. Incoming standalone STIX IDs are not reused
as new local row IDs. Existing stored legacy rows are reviewed without blocking
case loading and normalize through the ordinary next save/autosave.

If any nonblank row needs correction **or requires missing binary content / encounters a converter failure**, the saved data and CSV remain intact, **STIX is
unavailable** for the entire table (no supposedly complete partial export), precise section/row reasons are returned, a completion-review item appears,
and the previous STIX file is removed. Partially filled rows are errors; completely
blank placeholders are ignored. An empty table produces an empty Bundle, without
invented Indicator objects. Downloads validate the file against current saved
metadata, including downloads through generic case-asset routes. Generated STIX is
read-only in the general file editor. Archive generation refreshes valid derived STIX or excludes it when invalid, and RAW
restores regenerate/remove this derived file from validated table metadata.

Output publication uses staged files and atomic replacements with a case-local
recovery journal outside the MIP directory. Transaction failure restores prior files; startup
recovers an interrupted publication according to committed section data. A failed
generation never exposes partial JSON. Download STIX first saves current edits,
then downloads the matching attachment (`application/stix+json`); its GET never
mutates data. Completed/read-only cases can download a valid saved file without
reopening. Import/save does not mark readiness complete or change workflow stage.

### Unified CSV/STIX import

Each section's **Import** dialog defaults to **CSV**, preserving file upload and
pasted CSV (with or without headers). Files require case-insensitive `type`,
`value`, `description` headers; extra columns remain ignored. **STIX** accepts
`.json` and `.stix` files, validates their content, and accepts STIX 2.1 Bundles or
standalone supported objects. The displayed destination section remains selected
when switching tabs. Opening another upload or changing format clears the preview
and disables Apply until it has been validated again.

Choose **Preview import** before **Append accepted rows**. Preview distinguishes
ready rows, correctable rows, unsupported/skipped objects and exact destination
duplicates. Correct type/value/description using the same catalog, or deselect a
row. Correctable unresolved rows can be retained as flagged drafts. Imports append
to the chosen section, preserving its title, description and existing row order.
By default duplicates are skipped using canonical type and normalized matching
value (refanging, IP compression, hash/MAC case, DNS/URL host normalization).
Descriptions are not part of the duplicate key. The result reports actual added
and skipped counts; reimporting an unchanged application export into the same
section does not duplicate its rows.

Supported STIX Indicator patterns are one string equality or exactly one approved
composite from the catalog (including same-file filename/hash, registry key/data,
and directional traffic address type/value). Arbitrary AND/OR expressions are not
flattened. Negations, ranges, regex/LIKE/set predicates, observation combinations,
temporal qualifiers and numeric list positions are skipped with review reasons.
Revoked, expired/windowed or marked Indicators also need explicit review. YARA,
Sigma and other non-STIX patterns never become ordinary IOC values.

Supported observable facts include domain-name, URL, MAC, IP/email addresses,
file name/hash, mutex, registry key/data, certificate hashes and single supported
network/email references. Generic IP/email observables remain correctable rather
than inventing direction. References resolve only to objects in the uploaded
file. Missing references, multi-endpoint traffic tuples/ports, multiple simultaneous
hash constraints, unrepresentable registry values or MIME/email combinations are
listed explicitly as skipped. Context-only objects (including Groupings) do not
invent independent rows. This is a bounded IOC projection, not a complete STIX
event/model importer.

Limits: 4 MiB per CSV/STIX upload, 2,000 STIX objects, 256 KiB per object, 4,096
characters per pattern, a 64-bracket/parenthesis complexity budget, and a five-second
processing budget checked between bounded objects. Table limits remain 10,000
rows/100 sections and 4,000 characters per cell. Split large bundles if they exceed
these limits, including very large application exports. No external references,
TAXII servers, MISP services, credentials, or executable pattern engines are used.
All UI mutations retain session authentication, CSRF, stage/owner restrictions,
revision conflict checks and synchronization recovery. The preview/download routes
are internal UI routes; the existing public `/api/v1/cases/{case_id}/indicators`
contract documents draft status, canonical normalization and identity metadata.

### Verified MISP conversion and limitations

The original 23 attribute types, normalized values and row descriptions were tested using the
official **misp-stix 2026.10.12**, in its **attribute-labelled/internal** conversion
mode. Section Grouping titles become event titles. Grouping descriptions are
standard STIX context; their complete preservation in every MISP UI is not claimed.

The converter's default external mode did **not** preserve all distinctions in this
verification: hostname became domain, directional IPs produced converter errors,
and email-attachment fell back to a STIX-pattern object. MARE deliberately does
not add a false MISP tool-provenance label to force auto-detection. For reliable
attribute conversion, select the converter's explicit `--classification internal`
option, or use its `InternalSTIX2toMISPParser`, then manually import the resulting
MISP JSON. Direct STIX upload through MISP interfaces that cannot select this mode
is not verified as preserving every type. No MISP instance/publishing was tested.

Generic `software:name` patterns were separately verified with the official
external parser: they become MISP **software** objects, not `android-app` objects.
New `mobile-application-id` exports instead use the converter's contextual custom
attribute format, preserving the canonical attribute type and literal identifier.
The official [object mappings](https://misp.github.io/misp-stix/documentation/misp_objects_to_stix21.html)
do not imply that a scalar package name recreates an Android object template.

The mandatory coverage fixture contains **all 192 non-binary MISP types** and
was converted back through the actual official internal importer: all types,
normalized machine values, descriptions, UUIDs, section event titles and detection
flags survive, with no missing attributes or converter errors. A second fixture
verifies all **68 native detection patterns** with explicit detection intent, and
separate tests verify the two native descriptive mappings. This proves attribute
round trips for representative values, not successful rule execution or full
structured MISP object-template support.

Known pinned-converter limitations and adapter handling:

- Five numeric/composite patterns (`port`, `size-in-bytes`, IP-source/destination
  plus port, hostname plus port) quote numeric operands upstream. MARE uses the
  faithful contextual representation instead of publishing misleading native patterns.
- The internal importer sets native Campaign/Vulnerability attributes to IDS-enabled
  even with a false label. Default/non-detection rows therefore use contextual
  objects; native descriptive objects are used only for explicit true intent.
- PyMISP's validator lacks `edge-extension-id` and `filename|impfuzzy` dispatch and
  has a MAC EUI-64 colon-regex defect. The adapter uses the catalog-backed model,
  validates the composite/EUI-64 scalar shape locally and uses the official
  contextual writer/importer. These paths have actual round-trip coverage.
- PyMISP trims boundary whitespace/NULs on MISP import and serializes a `datetime`
  UTC `Z` as `+00:00`. Exact literal content remains in MARE/CSV/STIX JSON; boundary
  whitespace after MISP import is not promised. Application identifiers and ordinary
  prose are not defanged/refanged. Escaped original-type provenance becomes a MISP tag.
- The retained `software` extension is not a canonical MISP attribute. Its native
  pattern converts to a MISP software object in external mode; explicit non-detection
  software-name export lacks a verified scalar MISP representation and is reported
  precisely. Use an appropriate canonical MISP type when attribute round trips matter.

A MISP instance/direct upload UI, complete section-description retention in every
MISP UI, and external-mode preservation of custom attributes are not verified.
Use internal conversion with custom STIX content enabled; no false tool-provenance
label is added to force auto-detection.

Install runtime requirements during deployment, never Flask startup:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q tests/test_indicator_export_coverage.py tests/test_indicator_catalog.py tests/test_indicator_stix.py tests/test_indicators.py tests/test_case_sync.py tests/test_backups.py tests/test_api_documentation.py
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/indicator-stix.cjs
```

`tests/verify_indicator_misp.py` calls the real official importer offline. The
mandatory complete-catalog tests use the installed pinned runtime converter;
`MARE_MISP_PYTHON=/path/to/another/python` optionally enables the additional legacy
probe tests against a separate converter environment. Updates must review both
converter pins and the capability profile and rerun all round-trip tests.

Runtime conversion uses pinned `stix2==3.0.2` and `stix2-patterns==2.1.2` with the pinned MISP adapter locally. Its upstream dependencies include legacy STIX/CybOX libraries; they are package dependencies, not a separate backend or runtime service.
The browser test covers keyboard editing, format tabs, selected-section targeting,
preview correction, additive CSV/STIX imports, round-trip deduplication, stale
preview reset, saved/draft downloads and narrow layout without external requests.

### Snort Rule Builder — editor-first match groups

**Tools → Snort Rule Builder** is an authenticated, case-independent source editor
with a persistent case signature browser. It uses the existing MARE CodeMirror 6
theme, undo/redo, line numbers, syntax highlighting and word wrap. The editor stays
visible above Construct, Request bytes, Option library, Review & test and Docs. Adjust
Editor height with the accessible slider; only that layout preference is stored
in browser local storage. The browser is collapsible on narrow screens.

#### Source and semantic outline

Source is authoritative. `frontend/snort-model.js` recognizes source ranges and
relationships; `frontend/snort-editor.js` patches those ranges through native
CodeMirror transactions. Inspectors cover full/service headers, flow, content,
common modifiers, sticky buffers, identity and references. Header actions and
directions use native selectors; protocol/service choices include custom entry.
Address/port preset selectors populate editable fields, including `$HOME_NET`,
`$EXTERNAL_NET` and common server/port variables. Presets do not certify that a
variable or service exists in the configured profile. Flow options can be added
from categorized choices and removed individually, combining one option per
category. Apply preserves source ranges and validates incompatible combinations.
All official documentation links are centralized in the searchable Docs tab;
Construct and Option library no longer scatter links among editing actions. Unknown options remain
source-editable components. Comments, unknown options, order and unrelated
whitespace are retained. Caret movement selects outline components; outline
selection highlights and scrolls source without taking editor focus. Gold marks
the primary component; blue marks related buffer/match spans. Shared sticky
buffers can govern several matches, rather than belonging exclusively to one.

Add component and library insertion require an explicit location. Removal checks
known relative-match dependencies and asks for confirmation. Only independent
references can be moved through buttons in this version; detection constructs
must be reordered deliberately in source because order can change meaning.
Formatting is an explicit undoable action, never an implicit load-time rewrite.
Incomplete source remains untouched; unsafe inspector operations are disabled
until reparsing succeeds. This is a bounded lexical model, not a complete Snort
compiler. Source files are limited to 100,000 UTF-8 bytes. Uniform LF/CRLF endings
are preserved while editing; mixed line endings are retained on unchanged saves
and normalized to the detected convention after an edit.

The supplied ProxyBack example is loaded exactly, including its legacy HTTP
modifiers and `alert http` full header. It is reference data, never a fetched URL
or a claim of Snort 3 compatibility. Legacy trailing HTTP modifiers attach to the
preceding content; Snort 3 sticky buffers attach to following matches. Standalone
legacy modifiers provide dialect evidence. Ambiguous buffer-after-content source
requires the analyst to choose Legacy or Snort 3 interpretation before content
inspection is enabled. That choice changes interpretation, not source.

Conversion is explicitly previewed before application. Conservative legacy
conversions move per-content selectors before matches and convert supported
standalone modifiers to comma modifiers. Unknown/context-sensitive options,
advanced/relative modifiers and service-specific conversions outside the verified
subset block automatic application. Service names are valid in full Snort 3
headers; detected-service matching still requires the configured inspector.
The example's `http` header is never silently changed
to `tcp` or a two-field service header. Even an applied conversion requires actual
engine validation and representative target/baseline tests. Parser success,
compatibility findings, quality heuristics, engine validation and PCAP results are
shown separately. SID warnings cover the selected case/current source, not global
uniqueness.

References: [official Snort 3 rule guide](https://docs.snort.org/rules/),
[content syntax](https://docs.snort.org/rules/options/payload/content),
[HTTP buffers](https://docs.snort.org/rules/options/payload/http/),
[service headers](https://docs.snort.org/rules/headers/service_rules),
[protocol headers](https://docs.snort.org/rules/headers/protocols),
[legacy HTTP modifiers](https://www.snort.org/faq/readme-http_inspect),
[CLI discovery](https://docs.snort.org/start/help), and
[JSON alerts](https://docs.snort.org/start/alert_logging).

#### Case files, signature selection and drafts

Select a case by number/title and open an actual `.rules` file recursively under
its `signatures/` directory. Save updates its original path; Save as selects a case
and relative filename. Existing permissions, stage and active-owner restrictions
remain authoritative. Content hashes detect concurrent changes; selected-rule
overwrite is blocked, while separate Save As collisions require confirmation. Save/discard/cancel protects
unsaved content before opening files, switching cases or creating a new rule.
Download never counts as a completed save without explicit analyst confirmation.
Drafts are autosaved per immutable user UUID in `MARE_DATA_DIR/snort-drafts/`, not
browser storage or case tables. Separate tabs for one account use last-writer-wins
drafts. Wait for the draft-saved status before closing/reloading; a pending
network save cannot guarantee persistence after abrupt browser termination.

Multi-rule `.rules` files now remain intact. Web and API asset uploads preserve
original filenames and bytes (within the existing size/path/overwrite limits).
Files previously split by older versions are left alone; no automatic combining
or recovery-copy reconstruction occurs. The former normalization endpoint returns
410 and never mutates files.

Opening a multi-rule file displays a searchable **Select signature** dialog with
message, SID, revision, header, source line range, source-order position and a
preview. Missing/duplicate SIDs do not affect selection. The editor contains only
the chosen rule; its complete UTF-8 file snapshot (including BOM where present)
is retained separately. **Change signature** uses the same save/discard/cancel
flow as changing files or cases. File context shows Signature X of Y.

Save replaces the exact selected byte span under the per-case file lock, checked
against the loaded file hash. The server revalidates the range against active
rule boundaries and requires exactly one complete rule in the editor. All bytes
outside that span remain unchanged, including other signatures, adjacent comments,
disabled rules, directives and mixed LF/CRLF endings. SIDs/messages are metadata,
never replacement identities. After saving, boundaries and the selected position
are refreshed. A disk change blocks selected-rule overwrite; reload explicitly or
Save As. The tool never guesses a relocated target.

**Save As** writes only the selected rule to a separate destination, with explicit
collision confirmation; it cannot replace the original selected file. **Download
selected signature** downloads only the editor rule. Draft autosave does not mark
a case file as saved. Files with no safely bounded rules offer whole-file source
inspection with selected-rule saving/inspectors disabled. When a later region
fails, a diagnostic gives the filename, line/column, reason, short excerpt and
safe-signature count. The completed prefix remains selectable; scanning stops at
the first uncertain region without guessing where subsequent rules begin.
The open dialog offers safe-signature selection or whole-file inspection.
Saving a safe prefix rule also verifies that the unchanged uncertain suffix has
the same diagnostic at its adjusted source position.
Whole-file inspection has an explicitly labeled source download for recovery.

The shared `signature_files.py` scanner recognizes multiline/full/service headers,
quoted escapes and punctuation, hex content, multiple rules per line, line comments,
and Snort 3 `/* … */` inline/multiline comments (including parentheses/quotes),
matched disabled blocks and common single-line directives (`include`, `var`,
`ipvar`, `portvar`, `config`, `preprocessor`, `output`, `ruletype`). Unknown or
multiline configuration syntax, unmatched disabled blocks, incomplete rules and
unquoted nested parentheses fail closed for selected editing. Non-UTF-8 source
requires deliberate conversion before inspection; the tool never guesses an
encoding. Block comments crossing single-line directive boundaries remain
unsupported and stop scanning. Typographic quote delimiters and missing opening
quotes are reported; the tool never silently repairs them. For example, an
unquoted regex parenthesis after `pcre:/...` needs the missing ASCII opening
quote corrected, rather than relaxed boundary checks. Compare the
[official Snort rule/comment syntax](https://docs.snort.org/rules/) and
[PCRE syntax](https://docs.snort.org/rules/options/payload/pcre).
Rule-file inspection is lexical, not Snort engine validation; recognizing a
complete option block does not certify option spelling, semantics or compatibility.

Inventory/open GETs never change files. Atomic writes preserve artifact metadata,
set readiness Pending and use normal revision/search/audit mechanisms. Existing
permissions, ownership and lifecycle restrictions apply. No complete file is
regenerated from parsed rules, and no selected rule is appended as a duplicate.

Request bytes accepts at most 4,096 whitespace-separated byte pairs. Select by
mouse, arrows/Shift+arrows, or numeric range. This tab shows start/end/count,
hex/printable ASCII, the proposed content expression, the target inspection
buffer and an insertion selector. Both this tab and Option library share the
Construct insertion target: before/after a specific match or the end of the
option block. A safe single rule defaults to after its last match, or the end
of the block when it has no matches. Unsafe defaults require an explicit choice.
Construct also offers Insert before, Insert after and Add modifier controls.
Source-range anchors survive edits elsewhere; changing/removing a target
invalidates it instead of silently selecting a different ordinal match.

Add as content group creates one undoable source transaction, updates/highlights
the outline and offers View in Construct. Byte input and selection remain
available. Buffer changes for new Snort 3 matches restore the previous buffer
before existing later options; legacy HTTP buffers apply only to the new match.
Later relative matches and advanced/unknown cursor dependencies block insertion
at that location: choose the end of the option block or resolve them explicitly
in source. No existing matches are silently reassigned to another buffer.

Adding/replacing content imposes no positioning. Replacement and positioning
have their own content-match selector in Request bytes. Applying offset/depth is
separate and requires the matching transport-payload or exact application-buffer
origin. Full-frame offsets are refused; this version performs no packet decoding
or HTTP buffer normalization.

Option library actions open configuration for new content, required modifier
values or explicit option source. Content must be nonempty. Buffer entries add
a configured content match in that buffer rather than changing later matches.
Modifiers use the selected compatible content match, with a match selector
available in the library; Already applied selects the existing modifier without
duplicating it. Advanced templates require an explicit source-insertion action;
REPLACE_ME is selected and remains flagged for correction. Lexical acceptance
of a template never establishes Snort engine compatibility. Errors appear in
the active workflow and leave inputs unchanged. All actions edit the same
CodeMirror source and use its native history; case-file saves still replace
only the selected signature's verified byte span.

#### Snort execution setup and isolation

Editing, saving and downloads work without an engine. Install Snort **3** using its
[official installation instructions](https://docs.snort.org/start/installation).
No dependencies are downloaded at startup. Configure trusted absolute paths:

```sh
export MARE_SNORT_EXECUTABLE=/usr/local/bin/snort
export MARE_SNORT_PROFILE=/etc/mare/snort-profile/snort.lua
export MARE_SNORT_RUNNER=/usr/local/libexec/mare-snort-offline
```

Install `deploy/snort-offline-runner.py` at the runner path as an
administrator-owned executable. The service user must not be able to modify the
engine, runner or profile. Use a dedicated profile-only directory containing its
required defaults/rules; configure HTTP/stream inspectors and HOME_NET/EXTERNAL_NET
as appropriate. Do not include unrelated production rules, which would contaminate
alert counts. The runner requires Linux, `/usr/bin/bwrap`, unprivileged user
namespaces, and an engine installed below `/usr`. Never run MARE or Snort as root.
The runner must terminate its sandbox if its parent dies (the supplied wrapper
uses bubblewrap `--die-with-parent`). Process-group termination is preferred; a
host denial falls back to direct-child termination under that contract.
It creates private network/PID/mount namespaces, private `/tmp`, read-only runtime
and profile mounts, read-only rule/capture inputs and a per-job writable `/work`.
Control/ownership files remain outside that mount. Place application/job data
outside `/usr`, `/bin`, `/sbin` and runtime library mounts. Mount only a dedicated
profile directory; never include application secrets there. Site administrators
must maintain the kernel/Snort, filesystem quotas and appropriate cgroup/OS policy.
macOS supports the editor; execution needs an audited isolated runner implementing
the same contract, rather than direct unsandboxed Snort execution.

Version, `--help-options` and `--list-modules` discovery is cached for five minutes.
Catalog labels distinguish discovered modules from curated help; they do not
certify all plugin options. Jobs use `-T` validation, then fixed offline `-r` PCAP
arguments with `alert_json`, bounded diagnostics and fixed logger fields. Ordinary
users cannot supply executable/configuration/plugin paths or flags. The interface
never enables live capture or executes uploaded artifacts. Target and optional
baseline results remain separate; successful zero matches differ from errors.

Optional environment settings (enforced bounds):

- `MARE_SNORT_TIMEOUT`: 1–60 seconds per invocation, default 30.
- `MARE_SNORT_UPLOAD_LIMIT`: 1,024–41,943,040 bytes per capture, default 20 MiB.
- `MARE_SNORT_CONCURRENCY`: 1–4 cross-worker slots, default 2.
- `MARE_SNORT_JOB_TTL`: 60–86,400 seconds for job metadata, default 3,600.
- `MARE_SNORT_PCAPNG=1`: only after confirming support in the configured engine.

Captures are checked by content, stored temporarily under private
`MARE_DATA_DIR/snort-jobs/<id>/work/`, and removed on success/failure/cancellation.
Abandoned jobs are cleaned at startup and subsequent tool/job requests. Bounded
stdout/stderr are 64 KiB each; alert files are capped at 16 MiB with at most 200
alerts displayed. Cross-worker file leases prevent cleanup of running jobs.
Installation backups exclude transient jobs; drafts remain included. Captures
are never automatically saved into a case or browser storage. Save them separately
through the existing asset workflow only when intended.

Verification:

```sh
npm run build:editors
node tests/browser/snort-model.cjs
.venv/bin/python -m pytest -q tests/test_snort.py tests/test_tools.py tests/test_navigation.py
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/snort-builder.cjs
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/snort-workflows.cjs
```

Fake-engine tests verify job lifecycle, never Snort compatibility. The separate
real integration test skips unless all three engine/profile/runner variables are
configured; it validates the rule and checks target versus baseline alerts using
harmless synthetic fixtures under `tests/fixtures/snort/`. After deployment test
real engine errors, PCAP/PCAPNG support, cancellation/cleanup, browser console,
reverse proxy upload/time limits, narrow layouts and unchanged case permissions.

### YARA Rule Editor — editor with assistance dock

Tools → **YARA Rule Editor** is independent of cases. The source document is
always authoritative: paste or type complete files, including multiple rules,
imports, comments, dependencies and unsupported syntax. Helpers edit localized
source ranges through native CodeMirror history; they never regenerate a file.

The left pane searches cases and browses nested `signatures/*.yara` files.
Changing the browser case does **not** replace the document. Opening a file offers
Save / Discard / Cancel for unsaved edits. Save replaces the complete opened file
using its snapshot hash, safe paths, the existing per-case file lock and atomic
asset writer. Save As / Save to case accepts a relative `.yara` path in a case the
user may modify, with explicit confirmation before replacing a destination.
Concurrent disk edits block Save; reopen explicitly or use another destination.
Existing ownership, lifecycle, report-job locks, authorization, CSRF, readiness,
revision, indexing and archive handling remain in effect. There are no new tables.
Case asset links show a read-only escaped source preview; edit with the YARA tool
so the atomic/version checks are retained. Existing `.yar` assets keep their
existing behavior; this first tool version browses and saves `.yara` files.

The editor provides line numbers, highlighting, indentation, brace matching and
folding, comment toggling (Cmd/Ctrl+/), search/replace, native history, default-on
word wrap, completion (automatic and Ctrl+Space), and module-member hover details.
The editor-height slider adjusts the vertical editor/dock split. Dock visibility
and height are saved per account in local storage; rule content is not. The editor
toolbar’s **Options → Word wrap** item toggles wrapping without changing source or
history, and saves that preference per account in the same browser. Narrow
screens have a collapsible case pane. The dock tabs are **Completion**, **Conditions**,
**Metadata**, **Problems**, **Test**, then **Docs**. All documentation links are in
Docs; source, snippets, metadata and test output are rendered as text.

Completion is a curated **classic YARA 4.5.4** profile, not a claim of latest or
complete specification support. It accounts for the cursor's rule/section,
local string identifiers, other rule names, common built-ins, string modifiers,
metadata conventions and imported members of `pe`, `elf`, `math`, `hash`, `time`
and `dotnet`. Known duplicate/incompatible modifier suggestions are suppressed;
comments and literal bodies do not receive unrelated suggestions. The dock uses
the same contextual suggestions as the primary editor popup. Imports are never
added implicitly: preview and apply an import explicitly, without duplication.
Other modules and language constructs remain source-editable and compiler-checked.
There is no language-server dependency. The
[official YARA-X language server](https://github.com/virustotal/yara-x/tree/main/ls)
was evaluated, but its diagnostics do not establish classic YARA compatibility.

Conditions is an optional searchable snippet library. Insert at cursor and
Replace selection are distinct operations; neither adds Boolean operators or
silently replaces a whole condition. Prerequisites and placeholders are shown.
Metadata keys are user-defined: suggestions such as author, description and
malware_family are conventions, not condition variables or a mandatory schema.
Choose the rule by cursor or explicit selector and provide a key, type and value.
String values are escaped; integers are signed 64-bit; booleans are true/false.
A meta section is created if needed. Existing keys are selected for direct source
editing rather than duplicated. Values are never invented or populated from
account/sample data automatically. Helpers require complete lexical rule bounds;
unsupported/incomplete documents remain intact and editable.

#### Optional classic compiler and scanner

The reproducible target is **classic YARA engine and binding 4.5.4**, installed
through the official `yara-python` package. Later upstream releases exist; the
profile is deliberately versioned. It is **not YARA-X** and never switches engines
silently. No executable dependencies are downloaded during Flask startup.

```sh
.venv/bin/python -m pip install -r requirements-yara.txt
# Optional when the compiler is installed in a separate administrator-owned venv:
export MARE_YARA_PYTHON=/absolute/path/to/yara-venv/bin/python
npm ci
npm run build:editors
```

Node is needed only to build committed editor assets. The Flask application
works without the optional compiler: editing, client-side assistance, drafts,
case saves and downloads remain available. Test reports Engine unavailable with
setup guidance. The worker checks both the binding and native library version.
Update the pin, profile, curated completion catalog and integration tests together
when approving another target. Official references:
[language](https://yara.readthedocs.io/en/latest/writingrules.html),
[compiler/scanner API](https://yara.readthedocs.io/en/latest/yarapython.html),
[classic releases](https://github.com/VirusTotal/yara/releases),
[binding releases](https://github.com/VirusTotal/yara-python/releases).
Upstream online documentation may describe a newer 4.5 release than this profile.

Checks compile the **complete current document**, including imports and in-file
rule dependencies. Source changes debounce automatic checks for 1.5 seconds.
Results are tied to the editor revision; old responses cannot repaint newer text
as valid. Problems separates lexical-helper findings from compiler errors/warnings
and sample results. Compiler line information is navigable; when the binding
provides no column, the UI says unavailable instead of inventing a column.
Balanced braces and keyword recognition never produce a valid indicator.

**Includes are disabled** with the official `includes=False` compiler option.
They are preserved in stored source but produce an actionable compiler error.
Neither absolute nor relative includes can read server files. External-variable
configuration, external module data and include-workspace resolution are not
provided in this version. Imported built-in modules use the selected compiler's
installed module support; the UI's curated list is not a complete module schema.

Test accepts a positive sample and optional benign baseline, uploaded temporarily
or selected from authorized case `samples/` assets. All files are scanned **as
data**, never executed or unpacked; encrypted sample archives are scanned as
stored archive bytes. Results identify each sample/rule and bounded string
identifiers, offsets, lengths and 32-byte hex previews. Match/no match/error are
separate states, and positive/baseline outcomes remain separate. A match does not
establish rule quality. Cancellation kills the worker process group. Scan errors,
timeouts and nonzero process exits are never represented as successful no-match.

Workers use administrator-controlled Python and a trusted local worker script,
argument arrays (`shell=False`), private temporary job directories, file leases,
process-group cancellation, 64 KiB stdout/stderr limits, CPU/file/open-file limits,
and a 512 MiB address-space limit on Linux. macOS has no reliable address-space
limit here; production deployment targets Linux/Gunicorn. These process limits
are not a container or general native-code security boundary: run the service
under a dedicated unprivileged account and apply host service isolation as needed.
Only trusted application code controls worker paths and flags. Source is limited
to 100,000 UTF-8 bytes; the original BOM and unchanged bytes are retained on
unchanged saves, while edited line endings follow the loaded file's convention.

Configuration (bounded ranges are validated at startup):

| Variable | Default | Range / meaning |
| --- | --- | --- |
| `MARE_YARA_PYTHON` | Flask's Python | Absolute administrator-owned interpreter |
| `MARE_YARA_TIMEOUT` | 15 | 1–60 seconds for each worker process |
| `MARE_YARA_CONCURRENCY` | 2 | 1–4 jobs across Gunicorn workers |
| `MARE_YARA_UPLOAD_LIMIT` | 10485760 | 1024–20971520 bytes per sample |
| `MARE_YARA_JOB_TTL` | 3600 | 60–86400 seconds for result metadata |

The worker also limits total CPU to 10 seconds, each sample scan to 5 seconds,
and reports at most 100 matched rules and 100 string instances per rule. An
oversized response fails with a bounded-output error rather than silent omission.
Temporary source/samples are removed on success, failure, cancellation and
abandoned-job cleanup. Job results under `MARE_DATA_DIR/yara-jobs` are excluded
from installation backups. Account drafts under `yara-drafts` are persistent and
included. Draft writes are serialized and stale save-status responses are ignored.
Save/Discard/Cancel is offered for document replacement, Tools-tab switches and
ordinary same-origin application navigation. Discard leaves the case file alone;
a recoverable draft may remain. Browser refresh, browser close and external
navigation use the browser's restricted native unsaved-change prompt, which
cannot offer application-defined Save/Discard/Cancel buttons.

#### YARA verification

```sh
node tests/browser/yara-language.cjs
.venv/bin/python -m pytest -q tests/test_yara.py tests/test_snort.py tests/test_tools.py tests/test_navigation.py
MARE_BROWSER_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node tests/browser/yara-editor.cjs
```

Real compiler tests skip explicitly if the pinned optional engine is unavailable.
Browser acceptance requires it: it covers standalone completion, snippet history,
metadata/import edits, real validation, positive/baseline scanning, full-file case
save/reopen, dirty cancellation/discard, stale responses, source navigation, draft
recovery and narrow layouts. Also verify dock resize/collapse, keyboard completion,
case asset selection, permissions and concurrent disk edits under the production
reverse proxy. Configure proxy request limits for two sample uploads plus source
and multipart overhead; do not expose the temporary data directory through Nginx.

### Public cases delivery wall

`/dashboards/cases` is an anonymous, read-only display, linked from the login
header. `/dashboards/cases/data?page=0` is its dedicated public JSON projection.
Only system case number, title (up to 200 characters), description (up to 1,200
characters), lifecycle state and completion timestamp are exposed, alongside
aggregate counts, snapshot time, display timezone and pagination metadata.
Descriptions are displayed as plain-text summaries. No workbench links or
report/package delivery claims are included. Case deletion removes the case
from this view; the existing case model has no additional visibility flag.

In progress includes Malware Analysis and Packaging & Delivery; preparing for
delivery is the latter subset. Not started counts stage zero. Completed this
month counts currently completed cases whose terminal Packaging & Delivery exit
falls in the display timezone's calendar month. This follows the executive
scorecard's terminal-exit interpretation of legacy merged stage history.
Reopened cases are excluded from completed results. Missing, invalid or future
completion dates display “Completion date unavailable” and do not contribute to
the monthly count. Dated completions sort first; system number breaks ties.
The wall defaults to the application's UTC convention. Set
`MARE_DISPLAY_TIMEZONE` to an IANA timezone to change wall dates and month
boundaries together. Other application views retain their existing UTC behavior.

Active cases show four per page, ordered by Packaging & Delivery first, then
latest dated transition and system number. Pages rotate every 15 seconds, with
pause and manual paging controls. Each page request supplies an atomic snapshot
of metrics, active page and completions. The dashboard also refreshes every 60
seconds and when a hidden tab becomes visible. Requests never overlap, time out
after 20 seconds, and retain the last valid display on failure. Responses are
not cached. Queries and public payloads return at most four active cards, one
spotlight and 20 recent completions; a case/history index supports history lookup.

Recent completions exclude the spotlight. When they overflow, a presentation
copy creates a seamless loop at 20 CSS pixels/second. Resize measurements control
the loop distance; unchanged snapshots preserve the animation and explicit pause
state. Hover, keyboard focus and the pause control stop motion. Reduced motion
uses native horizontal scrolling and manual active paging. Few cards remain
stationary. Titles and descriptions use bounded line summaries for wall display.

Checks: `.venv/bin/python -m pytest -q tests/test_cases_dashboard.py` and
`node tests/browser/cases-dashboard.cjs`. The browser test uses disposable data
and installed Google Chrome by default; `MARE_BROWSER_EXECUTABLE` overrides its
path. It checks 1920×1080, 1366×768 and mobile layouts, safe text, motion and loop
geometry, pause, pagination, reduced motion, refresh retention and recovery.

### Malware Families

The authenticated Malware Families tab provides a profile workspace with Overview, ordered OSINT links and live tag-derived case History. It uses existing MAL_ tags and preserves case assignments during relinking or profile deletion. `tags:read` permits viewing; `tags:manage` permits management; `cases:read` controls linked-case counts and links. The additive `malware-families-v1` migration stores profiles and OSINT in SQLite. [Feature and recovery documentation](docs/malware-families.md) covers edit conflicts, tag protections, full-system backup and offline clean-instance restore. Profiles are internal and are not exposed through anonymous dashboards.

Malware Families now supports **OSINT & Reports** with PDF/DOC/DOCX multi-file
uploads, authenticated downloads, editable report metadata and confirmed removal.
Reports use durable family-owned storage under `MARE_DATA_DIR/family-reports/`.
Tags offers direct View/Create malware family actions with identity-checked
prefilling. Installation backup format 2 and Export All format 3 include actual
report bytes and verify their SHA-256 during restore; older formats remain
supported. See [report storage and recovery details](docs/malware-families.md).

### Public malware-family research wall

`/dashboards/malware-families` adds the anonymous Family spotlight dashboard, linked
from login and the Cases wall. It exposes only profile names, linked tags, short
descriptions, update dates and approved aggregate counts. The deterministic focus,
three-family investigation pages, bounded 24-profile library strip, pause controls,
reduced-motion alternative and 60-second snapshot refresh use actual library data.
See [Public Malware Families dashboard](docs/family-dashboard.md) for eligibility,
metric definitions, privacy boundaries, paging and verification.

### Consolidated Settings administration

Settings now contains General, Users, Audit, and Import & Export at stable
`/settings/...` URLs. Its text opens General; hover or the adjacent accessible
button opens authorized category links. Existing bookmarks redirect with their
query strings, mutation/export endpoints remain supported, and backup jobs survive
category navigation. The redundant General backup shortcut is removed; recovery
remains in Import & Export. See [Settings navigation](docs/settings-navigation.md)
for permissions, unsaved-form handling and verification.


### Threat Actors

The authenticated **Threat Actors** tab shares the Malware Families workspace:
ordered aliases, a required `TA_` tag, descriptions, configured Malware Family
associations, OSINT links, attached PDF/DOC/DOCX reports and current tag-derived
case History. It reuses `tags:read` / `tags:manage`; case links require
`cases:read`. Deleting/relinking profiles preserves tags and case assignments.
Backup & Restore supports selective actors with required family/tag dependencies
and complete recovery including report bytes. See [Threat Actors](docs/threat-actors.md) for association
identity rules, migrations, backup compatibility and verification.


### Public Threat Actors dashboard

`/dashboards/threat-actors` and `/dashboards/threat-actors/data` provide an anonymous,
read-only spotlight wall. Login, the dashboard directory, dropdown and public
navigation now link to it. Only names, TA_ tags, short descriptions, update dates
and aggregate counts are public. The wall shares the Family dashboard layout,
bounded paging, accessible scrolling and 60-second snapshot refresh. See
[Public Threat Actors dashboard](docs/actor-dashboard.md) for counting definitions,
privacy, selection, motion and verification.


Malware Family Create/Edit Profile also supports **Known Threat Actors** using the
same searchable chip picker. Both profile types edit one shared relationship;
renames/tag changes retain it and deletion removes live links. Family exports
include related actor dependencies. See [Shared actor–family associations](docs/threat-actors.md)
for migration, conflict handling and backup compatibility.

### Data Explorer

The authenticated **Data Explorer** link at the far right of navigation opens
`/data-explorer`: an interactive graph of cases, configured Malware Families and
Threat Actors. Search includes aliases/tags and immediate connections; type filters,
zoom/pan, dragging, Auto Arrange and a keyboard object list support exploration.
Cases expand into permission-filtered Standard MIP category counts and read-only
contents without generating an archive. The graph uses locally pinned Cytoscape.js
and has an explicit 400-object view limit. See [Data Explorer](docs/data-explorer.md)
for permissions, exact count definitions, exporter sharing and verification.

Data Explorer now uses a **Focus Canvas**: full-width graph, floating search and
filters, primary-object count chips, brighter connections, emphasized case nodes,
and a compact selection tray with an overlay Details drawer. Existing permissions,
relationships and Standard MIP inclusion rules remain unchanged.

## Python SDK

The standalone Python 3.10+ SDK is in [`sdk/`](sdk/README.md). Install with
`python -m pip install -e .` from this repository root or from the `sdk` directory.
It provides `MWSClient` and `AsyncMWSClient` over the existing bearer-authenticated
API v1, without importing the backend or accessing its database. See the
[SDK/API coverage matrix](sdk/docs/API_COVERAGE.md),
[generated API reference](sdk/docs/API_REFERENCE.md), and
[implementation report](sdk/docs/IMPLEMENTATION_REPORT.md).

SDK development tests require `python -m pip install -e '.[test]'`. Backend-only
installations do not need httpx or pydantic; in-process SDK integration tests skip
when those optional development dependencies are absent.

### Developer Workspace

The shared sidebar includes Developer → API, SDK, Editor and Plugins. Plugins
is a full-height Control Center with inventory filters, configuration, permissions,
dependencies and activity tabs. Editor provides a viewport-filling CodeMirror
workspace, resizable explorer and Output/Debug console, persistent layout preferences,
automatic Python/SDK completion and unpublished development runs. See the [Developer Workspace guide](docs/DEVELOPER_WORKSPACE.md)
for discovery, permissions, manifests, configuration, backups,
rootless-worker deployment, and deployment verification requirements.
