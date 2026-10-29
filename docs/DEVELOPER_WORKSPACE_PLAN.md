# Developer Workspace architecture and implementation plan

## Discovery

MWS uses Flask/Jinja, SQLite, cookie/CSRF browser sessions and separately authenticated bearer API v1. RBAC is in `authorization.py`; Administrator receives all declared permissions. The shared application layout is `templates/base.html`; navigation categories are derived from matched routes. Anonymous dashboards use standalone templates. Local browser storage already holds Explorer layout preferences. CodeMirror 6, bundled through esbuild, supplies shared editor theming and Python examples. Swagger/OpenAPI and the standalone `sdk/mws_sdk` are implemented and must be reused.

There is no user-authored plugin registry, manifest or runtime. `analyst_tools` registers trusted built-in tools only; those entries remain intact. Existing Snort/YARA subprocess integrations handle constrained input, not arbitrary Python, and are not a general plugin sandbox. This environment has no container engine. Arbitrary plugin execution, debugging and language-service sessions must fail closed until an administrator configures the separate worker.

## Ordered implementation

1. Shared application shell: reusable sidebar, header/breadcrumb/account controls, persisted collapsed/group state and accessible responsive drawer. Preserve existing route destinations and case tabs; add a Workbench selector where no case is selected.
2. Developer routes: new explicit RBAC, reuse existing Swagger page and protected schema, render/search shipped SDK Markdown/reference with code copy and real SDK links.
3. One plugin registry: schema-versioned manifest, owner-scoped draft files, optimistic file versions, safe paths, binary metadata, four SDK templates and a creation wizard. SQLite stores registry/version/execution metadata; source stays in a dedicated data directory. No direct database access from plugins.
4. CodeMirror workspace: multi-file buffers, draft conflict handling, file operations, SDK context panel, resizable/collapsible panels and unsaved navigation guards.
5. Separate worker protocol: authenticated backend-to-worker HTTP control and container-isolated, non-root sessions; read-only runtime image, per-session source snapshot, resource/time/output limits, no host/app/data mounts and no network in plugin containers. Worker is deployed separately from MWS. No fallback executes Python in the web server.
6. Language service: basedpyright JSON-RPC in an isolated worker session with the installed real SDK; LSP completion/hover/signature/diagnostics/definitions/references/symbols, workspace-only URIs and explicit cleanup.
7. Validation/testing/runtime/debugging: immutable execution snapshots; manifest/static validation without executing entry points; isolated test/run processes and debugpy/DAP with authenticated, session-bound control. Scoped REST gateway separates credentials from plugin/debug memory. Test/debug use fixtures/read-only API grants, not a trusted dry-run flag.
8. Lifecycle/configuration: validation/test results tied to exact draft fingerprint, immutable published versions, independent enablement, rollback/history/audit, encrypted secret configuration and typed non-secret fields. No arbitrary dependency installation; administrator-built worker images provide approved dependencies.
9. Import/export: bounded portable archives, no traversal/symlinks/secret configuration/caches/logs; imported drafts remain unpublished/disabled.
10. Deployment documentation, tutorial, threat boundaries and focused backend/browser/worker contract/regression tests. Report actual isolation/language/debug integration verification separately from unavailable local deployment capabilities.

## Components

- `application_shell.py`, shared sidebar template/CSS/JS; existing route compatibility retained.
- `developer_workspace.py`, plugin storage/manifest services and existing RBAC/audit integration.
- `frontend/developer-editor.js` built with existing CodeMirror packages/theme.
- Dedicated worker package, runtime image, service configuration, SDK gateway and LSP/DAP protocol adapters.
- Developer routes stay authenticated, including file, session and worker-control actions. Every mutation checks permissions and optimistic state server-side. Publishing does not automatically enable a plugin.

## Deployment invariants

Only the trusted supervisor can reach the rootless container engine; containers never receive its socket, app source, database, production environment or raw secrets. Worker endpoint and images are administrator configuration, never plugin-controlled command lines. Session identifiers are owner-bound, expiring and canceled on shutdown. A missing worker disables execution/language/debug actions with an explicit reason. Secrets are encrypted at rest and are omitted from plugin archives and browser reads. External service access must use administrator-defined allowlisted gateway connectors.

Implementation uses a private Unix-socket supervisor on the application host,
under a separate unprivileged service account with rootless Podman. Each job
gets only its immutable ZIP, non-secret context, and a job-specific API gateway
socket. The supervisor retains bearer and connector secrets outside containers.
No plugin dependencies are installed into the web service or on demand. Image
builds are administrator-reviewed and the supervisor requires an immutable digest.
