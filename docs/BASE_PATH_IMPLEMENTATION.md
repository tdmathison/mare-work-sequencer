# Configurable base-path implementation

## Architecture and compatibility

The startup variable `MWS_BASE_PATH` defaults to empty. `base_path.py` validates
and normalizes it, sets APPLICATION_ROOT, cookie scope and the application-specific
`mws_session` cookie name, and mounts the unchanged Flask routing table via
SCRIPT_NAME. The outer middleware also covers the existing backup maintenance
middleware. PATH_INFO is always an internal stripped route; Blueprint prefixes
remain unchanged. The application uses SQLite directly, not SQLAlchemy.

An explicit immediate-peer allowlist (`MWS_TRUSTED_PROXIES`, empty by default)
gates ProxyFix. The startup prefix remains authoritative even when forwarded
headers claim another prefix. Only client IP, scheme and the configured prefix
are applied; forwarded host/port are ignored. The production Gunicorn invocation
disables its separate forwarded-header handling.

Templates receive the server-generated mount. An external configuration script
reads an escaped data attribute, preserving the standalone editors' existing
Content Security Policy. Explicit JavaScript URL constructors use MWS.path for
internal routes; MWS.url handles already mounted URLs without a second prefix.
Python app_url similarly distinguishes known internal URLs with internal=True.
This distinction supports mounts that coincide with route names, such as /cases.
No global fetch override, response-body replacement, schema migration or new
runtime dependency is introduced. Existing endpoints and HTTP semantics remain.

Report-image response URLs, Markdown previews, search findings, redirects,
settings destinations, editor downloads, task operations and frontend requests
were updated. Existing url_for calls naturally inherit the mount, including
Swagger/OpenAPI server URLs and SDK documentation. The CodeMirror bundle is
rebuilt from the updated editor sources. SDK clients already support subpaths.

Root-path installations continue to use the same routes. The session cookie name
changes from Flask's default session to mws_session; users must sign in again.
DropZone source/configuration is untouched. The deployment examples are additive
and are not installed or activated by this change.

## Remaining assumptions and manual checks

Internal Flask route definitions, request.path authorization checks, API/SDK
operation identifiers, filesystem paths, document-package paths and URL suffixes
remain unprefixed intentionally. External, relative, data and blob URLs are not
rewritten. No known application-owned browser URL constructor remains hardcoded
to the public root after the source audit and browser smoke tests.

Production Nginx must strip the prefix; direct internal diagnostic requests use
unprefixed paths and produce public prefixed links. They do not form a separately
browsable deployment. Only a WSGI server-provided SCRIPT_NAME is respected when
the startup prefix is empty; untrusted HTTP forwarded headers cannot set it.

No Nginx or Ubuntu/systemd runtime is available here. The browser proxy simulator
tests canonical 308 redirects and stripped-path handling; it is not an Nginx
binary/configuration test. Run nginx -t on the target host, then reload. Verify
existing DropZone behavior, real TLS, cookie-name uniqueness and the full analyst
workflow in production. Browser checks exercise the shell, case workspace,
settings, search, tool frames, API docs and SDK docs; they do not exhaust every
interactive workflow or third-party tool operation.

## Validation

- New Flask regression suite: root, /mws, /team/tools and /cases; 28 tests pass.
- Real Chrome/Playwright smoke tests: all four mounts pass, with no unexpected
  failed responses, failed requests, page errors or requests outside the mount.
- npm run build:editors passes; all top-level static JavaScript syntax checks pass.
- Gunicorn --check-config with the production binding/header flags passes.
- SDK tests: 359 pass.
- Full repository tests cannot collect tests/test_samples.py because of an
  existing IndentationError at line 21. That unrelated file remains unchanged.
- With that file excluded: **1172 passed, 9 failed, 4 skipped** (91.32 seconds). All nine failing
  tests were reproduced from a clean git archive of HEAD using the same dependencies.
  They concern audit dates, autosave expectations, alias filtering, staged imports,
  MITRE autosave, and older workflow/archive expectations.

Baseline reproduction: 9 failed, 46 passed across test_audit.py, test_autosave.py,
test_family_aliases.py, test_mip_search.py, test_report_media.py and test_workflow.py.

## Modified and added files

- `README.md`
- `api.py`
- `app.py`
- `backups.py`
- `case_notes.py`
- `family_reports.py`
- `frontend/snort-editor.js`
- `frontend/yara-editor.js`
- `import_sync.py`
- `mip_search.py`
- `package.json`
- `profile_workspace.py`
- `report_assets.py`
- `report_routes.py`
- `settings_navigation.py`
- `static/asset-manager.js`
- `static/backup-workspace.js`
- `static/case-notes.js`
- `static/editor-tools.js`
- `static/explorer-coverage.js`
- `static/explorer-research.js`
- `static/indicators.js`
- `static/mip-search.js`
- `static/package-refresh.js`
- `static/package-register.js`
- `static/references.js`
- `static/report-workspace.js`
- `static/sample-export.js`
- `static/tag-workspace.js`
- `static/tags.js`
- `static/task-collections.js`
- `static/tasks.js`
- `static/vendor/codemirror/markdown-editor.js`
- `tagging.py`
- `templates/account.html`
- `templates/base.html`
- `templates/board_tags.html`
- `templates/case.html`
- `templates/case_tags.html`
- `templates/create_case.html`
- `templates/dashboard.html`
- `templates/file.html`
- `templates/import_export.html`
- `templates/indicators.html`
- `templates/package_register.html`
- `templates/report_workspace.html`
- `templates/sample_archive_settings.html`
- `templates/snort_builder.html`
- `templates/tags.html`
- `templates/tasks.html`
- `templates/text_manipulation.html`
- `templates/users.html`
- `templates/yara_editor.html`
- `base_path.py`
- `deploy/mws-subpath.service`
- `deploy/mws.env.example`
- `deploy/nginx-subpath.conf`
- `docs/BASE_PATH_IMPLEMENTATION.md`
- `docs/PRODUCTION_SUBPATH_DEPLOYMENT.md`
- `static/mws-url.js`
- `templates/url_config.html`
- `tests/browser/base-path-server.py`
- `tests/browser/base-path.cjs`
- `tests/test_base_path.py`
