# MWS Python SDK

`mws-sdk` 1.0.0 is a standalone Python 3.10+ client for the MARE Work Sequencer REST API v1. It imports only its own modules, httpx and pydantic, never the server or database.

## Install and authenticate

From this directory, or from the repository root:

```sh
python -m pip install -e .
export MWS_BASE_URL=https://mws.example.com
export MWS_API_KEY=your-personal-bearer-token
```

Create a token once using the application's API page, after completing any forced password change. Existing tokens are user-bound SHA-256 hashes with optional expiration, revocation and the user's **current** RBAC permissions. Token secrets are returned once; store them in a secret manager. The SDK uses bearer authentication, not login cookies or browser CSRF tokens. There is no second API-key database or plugin runtime.

```python
from mws_sdk import MWSClient
from mws_sdk.models import CasesListParams

with MWSClient() as client:
    page = client.cases.list(params=CasesListParams(limit=50, q="analysis", sort="number"))
    for case in page.cases:
        print(case.number, case.name)
    for case in client.cases.iter_all(params={"limit": 50}):
        print(case.number)
```

Explicit `base_url=` and `api_key=` override environment variables. A deployment subpath or trailing `/api/v1` is accepted. URLs containing credentials, query strings or fragments are rejected. Client/model repr and SDK errors redact credentials; never print a token's `get_secret_value()`.

## Connection configuration and async

```python
from mws_sdk import AsyncMWSClient

async def read_cases():
    async with AsyncMWSClient(connect_timeout=10, read_timeout=120, retries=2,
                              max_retry_delay=60, verify=True,
                              max_connections=20, max_keepalive_connections=10) as client:
        async for case in client.cases.iter_all(params={"limit": 100}):
            print(case.number)
```

Clients own pooled connections. Always close them or use context managers. `trust_env=False` avoids implicit proxy configuration; enable it explicitly if needed. `verify` accepts httpx TLS verification options including a configured SSL context. TLS verification defaults on. Retries use exponential backoff with jitter for connection errors and HTTP 429/502/503/504 on GET/HEAD/OPTIONS only. Retry-After seconds and HTTP dates are honored; waits over `max_retry_delay` return the error instead of retrying early. Mutations, report generation, imports and POST exports are never retried automatically. Stream interruptions remove partial output and require explicit caller retry.

## Cases, workflow, tasks and findings

```python
with MWSClient() as client:
    me = client.authentication.me().user
    case = client.cases.create(data={"name": "Sample investigation", "owner_id": me.id}).case
    client.cases.advance(case.id, data={"expected": 0})
    client.tasks.create(case.id, data={"title": "Inspect persistence", "priority": "High"})
    client.notes.create(case.id, data={"title": "Finding", "body": "Observed scheduled-task persistence."})
```

Case numbers are immutable. An active owner is required to start, edits require analysis/packaging stages, and completion uses the existing readiness/blocker rules. Advance uses optimistic `expected` stage checks; reopening uses `cases.reopen(case_id)`. Metadata updates do not change stage. Delete is a real destructive action; no SDK method executes until called.

## Indicators, imports and references

```python
with MWSClient() as client:
    current = client.indicators.get(123)
    client.indicators.update(123, data={"revision": current.revision,
                                      "sections": [s.model_dump(exclude_unset=True) for s in current.sections]})
    preview = client.indicators.preview_import(123, data={"section_id": "default", "format": "csv",
                                                       "csv": "domain,example.test,Observed"})
    # Review preview.rows; explicitly choose rows before applying.
    client.indicators.import_rows(123, data={"revision": preview.revision, "section_id": "default",
                                            "accepted_rows": [["domain", "example.test", "Observed"]]})
    client.references.update(123, data={"revision": client.references.get(123).revision,
                                      "rows": [["https://example.test/research", "Research"]]})
```

Preserve all sections and their `row_meta`/`stix_meta` when editing. The `default` section cannot be removed. A revision conflict requires reloading and merging deliberately. Invalid/draft indicators can remain saved with `stix.issues`; successful storage does not guarantee STIX export availability. `download_stix` only succeeds for a current valid export. CSV/STIX preview accepts text or multipart files in the existing `csv`/`stix` fields. The preview itself never imports rows. Original types and detection intent can be supplied through accepted provenance arrays; they are never inferred by the SDK.

## Reports, images, assets and packages

```python
with MWSClient() as client:
    client.reports.update(123, data={"sections": {"executive_summary": "Analyst findings."}})
    client.reports.update_mappings(123, data={"mappings": {"attack": "Observed T1059.", "mbc": "Observed behavior."}})
    client.assets.upload(123, data={"category": "scripts"}, files={"file": "analysis.py"})
    client.reports.upload_image(123, data={"section": "executive_summary"}, files={"image": "evidence.png"})
    # Reports generation uses the current user's selected Word template and real server jobs.
    client.reports.generate(123, data={"generation_mode": "manual", "generate_pdf": "0"})
    print(client.reports.job(123).job)
    # After packaging prerequisites are satisfied:
    client.packages.export(123, data={"archive_type": "standard", "acknowledge": True}, destination="standard.zip")
    client.packages.export(123, data={"archive_type": "raw", "acknowledge": True}, destination="raw.zip")
```

`templates` manages the caller's Word templates. `reports.upload` accepts an edited DOCX in the `report` multipart field. Final Word/PDF downloads and image transfers use the same permissions as the web application. Standard and RAW remain different exporter modes; the SDK does not reconstruct archives. Samples require an explicit `include_samples` option and `samples:export`. Upload dictionaries accept local paths, caller-owned binary handles or httpx `(filename, handle, content_type)` tuples; repeated multipart fields use a list of `(field, value)` pairs. SDK-opened file handles are closed; caller-owned handles remain caller-owned. Downloads stream to a temporary sibling file and publish only after success; existing destinations require `overwrite=True`. They do not trust server-provided filenames. Async file I/O uses bounded synchronous filesystem operations while HTTP transfers remain asynchronous.

## Coverage, profiles, tools and plugins

```python
with MWSClient() as client:
    result = client.coverage.get(params={"scope": "all", "missing": "1", "sort": "missing"})
    for row in result.rows:
        print(row.number, row.missing, row.indicators.state)
    for gap in result.gaps:
        print(gap.name, gap.explanation)
    print(client.tools.list().tools)
    print(client.plugins.capabilities().plugin_registry)  # False: no plugin registry exists.
```

Coverage is saved-content presence, never an analysis-quality or completion score; inspect `limited`, `note`, `pages` and `gap_pages`. Current-Graph scope accepts the existing JSON-encoded `ids` query field supplied by a caller; viewport state is not guessed by the SDK. `explorer` exposes authorized graph data, evidence, bounded connections/shared indicators, contents and owner-scoped saved views. `families`, `actors` and `tags` expose profiles, aliases, shared associations, OSINT/report attachments and tag management. Profile changes require the current `version`; omitted profile fields/relationships are preserved, while explicitly empty alias/association collections remove them.

Future plugins use this client exactly like any external integration: retrieve `cases.get`, read/update report/indicator data, submit `notes` findings, references and assets, inspect coverage, and invoke permitted tool actions. There is no invented registration, install or arbitrary execution endpoint. CyberChef runs only in the browser; the registry describes it but does not invent a server execution method. Native text operations, Snort and YARA drafts, saves, job submission/status/cancel and downloads are actual server handlers. Engine availability and upload limits remain server-managed; source is JSON-encoded in the established `source_json` field. Job results and tool-specific contexts retain forward-compatible extra fields.

## Users, roles, settings, metrics and backups

`users` provides account creation, role/active updates and authorized deletion. `roles` exposes known permissions and custom role administration; privilege-escalation and last-administrator safeguards remain server enforced. Account bootstrap/forced password changes and interactive login/logout remain browser operations. `settings` exposes the existing non-secret configuration status and write-only sample password update. `metrics.get` returns the existing metrics projection, not an invented replacement. Audit exports retain Administrator-only enforcement.

`backups.case` and `backups.export_cases` stream existing case backups. `import_cases`/`import_raw` stage archives for `sync_review` and explicit `sync_apply`, rather than silently replacing data. `backups.create_job` exposes the newer selective/complete backup workflow:

```python
import os

with MWSClient() as client:
    job = client.backups.create_job(data={"kind": "export", "complete": True,
                                          "passphrase": os.environ["MWS_BACKUP_PASSPHRASE"]})
    print(client.backups.job(job.id))
    # Poll until completed, then explicitly download:
    # client.backups.download(job.id, destination="encrypted-backup.zip")
```

Load backup passphrases from a secret manager or environment; keep them out of source code. Inspect imports upload in `archive`, provide the passphrase, then inspect `job`, resolve choices with `preview`, and explicitly call `apply` only after review. Complete replacement requires `ack="REPLACE"`. Jobs are owner-scoped. Passphrases are not stored in saved job configurations. The retired `/backups/database` HTTP-410 endpoint has no nonfunctional SDK method; use encrypted jobs instead.

## Errors and compatibility

Catch `MWSError` or its authentication, authorization, not-found, validation, conflict, rate-limit, server and connection subclasses. HTTP errors retain `status_code`, sanitized `details`, `request_id` and `retry_after`. Client validation omits sensitive pydantic input dumps. Redirects are not followed, preventing bearer forwarding to another origin. Response models retain additional fields for additive API evolution; malformed known fields raise a compatibility error. Use the API v1 shipped with this SDK for new namespaces; older servers can return 404 for extensions rather than silently fabricating capabilities.

Request/response model names, all methods, exact permissions and endpoints: [API coverage matrix](docs/API_COVERAGE.md), [generated API reference](docs/API_REFERENCE.md). [Discovery and limitations](docs/DISCOVERY.md) maps browser-only and operational capabilities explicitly.

## Development and tests

```sh
python -m pip install -e '.[test]'
python -m pytest sdk/tests                   # repository root, entirely mocked HTTP
PYTHONPATH=.:sdk python -m pytest tests/test_sdk_integration.py tests/test_sdk_api_extensions.py
```

The second command's backend conftest creates a disposable data directory and uses in-process WSGI transport. It cannot target a URL or production installation. Regenerate contracts/models/resources with `MARE_DATA_DIR=$(mktemp -d) python scripts/build_sdk.py`; this safety guard prevents the generator from importing the application against development/production data. Generated source is shipped in the wheel; installation does not run the backend or generator.

Token rotation (the new secret is a `SecretStr` and returned only once):

```python
with MWSClient() as client:
    created = client.authentication.create_token(data={"name": "automation rotation", "expires_in_days": 30})
    # Pass created.token.get_secret_value() directly to your secret manager.
    # After validating the replacement credential, explicitly revoke the old token ID:
    # client.authentication.revoke_token(old_token_id)
```

### External plugin development

Use Python 3 in VS Code or another external environment. From a repository checkout:

```sh
python3 -m venv .venv-plugin
.venv-plugin/bin/python -m pip install -e ./sdk
.venv-plugin/bin/python -m pip install pytest
```

Select `.venv-plugin/bin/python` in VS Code. Install the Python/Pylance extensions
if desired; IntelliSense uses the installed SDK's type annotations. No application
editor or language service is required. Set `MWS_BASE_URL` to your HTTPS MWS origin
and `MWS_API_KEY` to a short-lived API token with only the required permissions.
Keep credentials in your shell/secret manager, outside source control and packages.
For example, run a standalone script using the SDK's environment configuration:

```python
from mws_sdk import MWSClient

with MWSClient() as client:
    print(client.plugins.capabilities())
```

Copy `examples/hello_world_plugin` from the repository as a starting package:
`plugin.json` declares `mws-plugin/1`, its validated identifier, SDK/API versions,
permissions and `main.py:run` entrypoint; `main.py` defines `run(context)`.
Test locally using pytest and a fixture implementing `mws_sdk.plugin.PluginContext`.
Use an explicit case identifier when accessing case data. The installed runtime's
SDK grants are scoped to that case, declared permissions and current user RBAC.
`context.configuration` holds public configuration; approved connector credentials
remain in the gateway and are accessed through `context.external(service,path)`.

An administrator copies the complete package directory into `MARE_PLUGINS_DIR`
(default: repository `plugins/`), then opens Developer → Plugins and refreshes.
Discovery validates the manifest/source contract without executing Python. Configure
required values, then Enable. To deploy changes, increment the manifest version,
replace the directory atomically and rescan; existing executions retain their
immutable snapshots. Source files are managed on disk, never through the web UI.
The operator must review dependencies and include them in the approved runtime
image; no dependency installation happens during execution.

`client.plugins.capabilities()` reports available tools and authorized registered
plugins. It does not execute code. Normal enabled-plugin runs remain isolated;
see the repository's `docs/PLUGIN_RUNTIME.md` for deployment and lifecycle routes.

## Task collections

`client.task_collections` and its async equivalent support shared guidance CRUD,
ordered template updates, creating/appending definitions from Case tasks, Case
groups, reordering and atomic application with an idempotency key. Existing
`client.tasks` methods remain supported. See the [task collection guide](../docs/TASK_COLLECTIONS.md#rest-api-and-python-sdk)
and [explicit-write example](examples/task_collections.py).
