# Developer Workspace implementation and validation

Changes remain on `feature/developer-workspace`. No commit, push or merge was
performed. No production database was accessed or modified.

This document records the original implementation baseline. The subsequent
Plugins/Editor refactor replaces its advanced Editor controls; the current UI
and deployment instructions are in [Developer Workspace](DEVELOPER_WORKSPACE.md).
Backend version, configuration and debugger facilities described below remain
available through their existing authorized APIs.

## Current File Explorer replacement

The V2 tree is replaced by `frontend/developer-explorer.js`, with original
MIT-licensed SVGs in `frontend/developer-file-icons.js`. There is no external icon
package or second Explorer implementation. `frontend/developer-editor.js` adapts
snapshot changes to open buffers/tabs and restarts LSP after structural changes;
the existing runner and Output/Debug console are reused.

`plugin_file_operations.py` extends the existing `/files` API with bounded atomic
multi-item move/copy/delete. `developer_workspace.py` keeps ownership, RBAC, CSRF,
audit and revision CAS authoritative; `plugin_store.py` additionally rejects
case-variant implicit parent collisions. All changes operate on virtual SQLite
package entries; no host filesystem move/copy/delete is introduced. The root
manifest is protected from structural removal, while its contents remain editable.

`templates/developer_editor.html` and `static/developer-workspace.css` provide the
compact header, internal tree scroll area, inline names, drag feedback and menus.
The frontend bundle and `package.json` browser-check command are updated. New
coverage is in `tests/test_plugin_file_operations.py` and
`tests/browser/developer-explorer.cjs`; the existing page browser flow now uses
tree items and inline names. Documentation is in the current workspace guide.

Copy duplicates saved snapshot bytes, not unsaved text. Collisions never overwrite
existing entries; copies receive unused names. Deletion requires confirmation,
warns about descendants/drafts, and has no Explorer undo/recycle bin. No new
runtime dependency or database migration is required.

## Current V2 replacement

The existing `/plugins` and `/developer/editor` routes now render viewport workspaces;
no parallel routes or registries were added. The old document-height controls and
single long metadata panel were replaced by the Control Center and resizable IDE.

Files for the V2 replacement:

- `templates/developer_plugins.html`, `static/developer-plugins.js`: searchable,
  filtered inventory, five tabs, schema-derived configuration, activity and existing
  enable/disable/create/edit operations.
- `templates/developer_editor.html`, `frontend/developer-editor.js`: compact plugin
  switcher, collapsible explorer, entrypoint selection, word wrap, console allocation,
  and guarded browser history. CodeMirror, LSP and isolated execution are reused.
- `static/developer-layout.js`, `static/developer-workspace.css`: intrinsic-header
  viewport layout, independent scroll regions, accessible pointer/keyboard splitters,
  user-scoped non-sensitive preferences and optional temporary sidebar collapse.
- `developer_workspace.py`: additive manifest inventory metadata, effective scope
  information and owner-scoped activity usernames / bounded diagnostic summaries.
  Configuration, registry, file operations and runner contracts stay authoritative.
- `static/vendor/codemirror/markdown-editor.js`: rebuilt frontend bundle.
- `README.md`, `docs/DEVELOPER_WORKSPACE.md`: current workspace instructions.
- `tests/browser/plugin-pages.cjs`, `tests/test_plugin_pages.py`,
  `tests/test_api_documentation.py`: management, configuration/secrets, geometry,
  splitters/preferences, guarded history, permissions and metadata regressions.

V2 adds no dependencies or database migration. The earlier discovery migration is
unchanged. Container execution still requires deployment verification on Linux
with rootless Podman; browser execution rendering uses explicit transport fixtures,
while LSP checks use real basedpyright and SDK definitions.

## Original components

- `application_shell.py`, `templates/sidebar.html`, `templates/base.html`, and
  `static/application-shell.*`: shared permission-aware left sidebar, breadcrumbs,
  Workbench case context, desktop collapse, mobile drawer, focus handling and
  per-user browser preferences. Existing case tabs and public dashboard layouts
  remain intact. Tools entries come from the existing authorized registry.
- `developer_pages.py`, Developer templates, `static/developer-docs.js`: existing
  Swagger alias and native SDK guide/reference search, anchors, code copy and
  version display, using shipped documentation rather than a second manual.
- `plugin_store.py`, `developer_workspace.py`: owner-scoped draft registry,
  bounded virtual files, compare-and-swap revisions, four wizard templates,
  non-executing static checks and safe portable ZIP import/export.
- `frontend/developer-{editor,language,protocol,debug}.js` and workspace CSS:
  existing CodeMirror theme and editor components; language-aware multi-file tabs,
  file tree, save/discard/cancel, binary downloads, wrapping/indent controls,
  resizable/collapsible panels, real LSP completion/hover/signatures/diagnostics/
  navigation, and real DAP breakpoints/current-line/stack/scope/variable controls.
  In-flight saves retain subsequent edits as dirty; stale requests cannot replace
  another selected plugin's buffers.
- `developer_execution.py`: immutable snapshots, version publication and rollback,
  independent enablement, owner-bound history/inspection/cancel, fingerprint-bound
  validation/test eligibility, and existing audit integration. Selected case
  artifacts up to 8 MiB are available only through explicitly scoped read grants.
- `developer_configuration.py`: typed configuration and AES-encrypted secret fields
  using the existing site key and encryption dependency. Secret values never
  return in configuration GETs, ZIP exports or debuggee context/environment.
- `developer_worker/{client,supervisor,runtime}.py`, Containerfile and the supplied
  user service: private worker RPC, real basedpyright/debugpy/pytest, rootless
  Podman confinement and per-job API gateway. No user source is imported or run
  by Flask. No unsafe local-execution fallback exists.
- `authorization.py`, `api.py`, `api_extensions.py`: granular Developer permissions,
  bearer-grant intersection with current RBAC, case/artifact endpoint restriction,
  compatible API documentation routes and additive plugin-capability metadata.
- `sdk/mws_sdk/plugin.py`: typed plugin API 1 context, still independent of Flask.
  SDK models, OpenAPI snapshot and generated reference were regenerated for the
  additive plugin capability response. No SDK resource method was removed.
- `README.md`, SDK README and Developer guide: tutorial, manifest, permissions,
  isolation model, deployment configuration and troubleshooting.

## Routes and migration

New page routes: `/workbench`, `/developer/api` (alias), `/developer/sdk`,
`/developer/editor`, `/plugins`. `/api` and all existing case deep links continue
to work. Documentation permissions do not grant data/API permissions.

Authenticated session/CSRF workspace endpoints are rooted at
`/developer/workspace`: plugin collection/create, import, plugin detail/files/
configuration/export/delete/history, static validation, isolated validate/test/
run/debug/language, publish/enable/rollback, execution polling/cancel/RPC, and
selected-case artifact listing. Browser RPC is not an unauthenticated debug port.
`/api/v1/plugins` remains the existing SDK capability endpoint, now accurately
reporting owner-authorized plugin registrations in addition to trusted tools.

Idempotent migration `developer-workspace-v1` adds five tables:
`developer_plugins`, `developer_files`, `developer_versions`,
`developer_executions`, `developer_grants`, plus indexes and optional selected
artifact binding. Schema initialization precedes complete-backup schema discovery.
Published versions and execution snapshots are immutable; draft deletion is soft
and does not erase history. Complete backups preserve the new SQLite data;
portable plugin ZIPs intentionally exclude configuration, grants and histories.

## Dependencies and deployment

No new web-process Python dependency or npm package is needed. Existing
CodeMirror packages, local Swagger, SDK, Flask RBAC and pyzipper are reused.
The worker image installs basedpyright 1.38.4, debugpy 1.8.20, pytest 9.0.2,
httpx 0.28.1, packaging 26.0 and the SDK. These are not installed into the web
application environment or from user manifests at execution time.

A dedicated Linux rootless Podman worker is required. Startup requires seccomp,
cgroup v2 CPU/memory/PID controllers and an administrator-reviewed image digest.
Configure its private shared-group socket, HTTPS API origin and optional approved
connectors, then set `MARE_DEVELOPER_WORKER_SOCKET` for Gunicorn. See the
[deployment guide](DEVELOPER_WORKSPACE.md#deploying-the-isolated-worker) for service
installation and commands. Worker-dependent actions return 503 until configured.

Containers have no network or host/application/database/engine-socket mounts;
their root is read-only, user is non-root, capabilities are dropped, and CPU,
RAM, swap, process, descriptor, tmpfs, runtime and output limits apply. Bearer
and connector credentials stay outside containers. Development grants cannot
write; operational grants are constrained by manifest permissions, current RBAC,
selected case/artifact and the existing API's closed-case rules. Publishing
requires isolated validation and tests for the exact source fingerprint.

## Verification

- Focused Python/API/SDK/navigation suite, including real template type checks:
  **411 passed, 1 skipped**. The skipped test requires an actual Linux container
  host and reviewed image.
- New feature core: owner/permission/CSRF enforcement, file operations and stale
  writes, hostile paths/archives, template generation, immutable publication and
  run snapshots, grant revocation, selected-artifact restrictions, protocol path
  restrictions, secret encryption/redaction and refusal of weak worker settings.
- Real basedpyright 1.38.4 protocol test: SDK completion for cases/indicators/
  reports/packages; hover, signatures, definitions, references, symbols and
  undefined-name diagnostics passed. All four wizard templates passed actual
  import/type checks without executing their entrypoints.
- Real debugpy 1.8.20 fixed-fixture test: breakpoint, stack, scopes, variables,
  step, continue and termination passed. This verifies the DAP contract, not
  container-host isolation.
- Developer Chrome test passed creation, multi-tab editing, save/reload,
  in-flight-save preservation, Save/Discard/Cancel, sidebar/group persistence,
  mobile drawer Escape and no page overflow at 1440/1024/768/390px. Desktop/mobile
  screenshots were inspected and inherited control-spacing issues corrected.
- Existing Swagger browser regression passed GET/write/upload/download/errors,
  token non-persistence, session gating, WSGI prefix, narrow layout and read-only
  Python example/copy behavior.
- Existing CodeMirror browser regression passed report/task/mapping/file editors,
  manual save/autosave, images, long documents, expanded view, toolbar controls,
  previews, reload and Word generation, with no browser errors/external requests.
- `npm run build:editors`, Python compilation and `git diff --check` passed.
- Broad Python regression run (excluding the pre-existing broken collection file):
  **932 passed, 5 skipped, 9 failed**. All nine failures were reproduced from a
  clean `git archive HEAD` snapshot: audit markup, two autosave expectations,
  legacy import redirects in search/task tests, ownership/metrics expectation,
  and three old workflow expectations. They were not hidden by changing product
  behavior. `tests/test_samples.py` separately has an unchanged IndentationError
  at line 21, so unqualified full-suite collection remains blocked by that file.
  Navigation assertions were updated only where this requested redesign changes
  the primary shell, active parent, documentation permission or registry state.

## Remaining deployment limits

This Mac has no Docker/Podman engine. Container image build/startup, actual cgroup
limits, timeout/output/network/filesystem enforcement and full browser → worker →
container debugging/execution could not be exercised here. Run the supplied
`tests/worker` check and operational/debug smoke tests on the configured Linux
worker before enabling Developer operations in production. Tests of argv and
protocol boundaries are not substitutes for those host checks.

Language/debug sessions have a ten-minute lifetime and operational jobs sixty
seconds; limits are fixed in the reviewed supervisor. Dependency source definitions
lead to SDK documentation; direct file opening is restricted to the authorized
plugin workspace. Configuration key rotation needs deliberate secret re-entry or
managed migration. Approved connector GETs and artifacts are bounded; arbitrary
network access or arbitrary dependency installation is deliberately unavailable.
