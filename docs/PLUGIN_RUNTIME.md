# Installed-plugin operational runtime

The old browser-editor worker also ran normal enabled plugins. Removing it without
replacement would break those plugins or move arbitrary code into Flask. Its
operational execution boundary is therefore retained as the smaller
`plugin_runtime` service: **run only**, with no source endpoints, LSP, debugger,
validation/test sessions, RPC or editor credentials. Nothing requires this service
merely to start MWS, view API/SDK pages, discover or configure packages.

The image contains Python 3, the installed local SDK, httpx and packaging. Approved
additional dependencies must be reviewed and baked into the image. It does not
contain basedpyright, debugpy or pytest. Existing isolation remains: dedicated
unprivileged supervisor account, rootless engine with seccomp and delegated cgroup
v2 limits, non-root UID 10001, read-only root filesystem, private tmpfs workspace,
network disabled, one CPU, 512 MiB memory/swap, 64 processes, dropped capabilities,
no host namespaces, no privileged mode and no Docker socket mounted into plugins.
Only the bounded immutable package and a scoped API gateway socket are mounted.
Application database/session keys and environment secrets are never supplied.
Runs have a 60-second timeout and bounded output; cancellation and completion
remove containers and temporary resources. Tokens expire and are revoked on
completion/cancellation. Manifest scopes, user RBAC, selected case/artifact and
connector allowlists remain enforced. No API credentials are passed into plugin
code; API requests go through the grant-restricted gateway.

## Build and start

Use a Linux worker account with rootless Docker, seccomp and systemd cgroup-v2
CPU/memory/process delegation already configured. The service refuses an engine
that cannot enforce these limits. The web service must never own the Docker socket.
The repository `.dockerignore` admits only the SDK and trusted runtime entrypoint,
excluding application data, configuration and operator-installed plugins from the
build context. Build from the repository root using that account:

```sh
docker build -f plugin_runtime/Containerfile -t mws-plugin-runtime:reviewed .
docker image inspect mws-plugin-runtime:reviewed --format '{{.Id}}'
```

Use the returned immutable `sha256:...` image ID (not the mutable tag). The
supervisor uses only the standard library; copy `plugin_runtime/*.py` to
`/opt/mws-plugin-worker/plugin_runtime/` on the worker, without the MWS data tree.
Create the dedicated `mws-plugin-worker` account and shared `mws-plugins` socket
group. Add only the web service account and worker account to that group. Install
`deploy/mws-plugins-tmpfiles.conf` as `/etc/tmpfiles.d/mws-plugins.conf`, then run
`sudo systemd-tmpfiles --create /etc/tmpfiles.d/mws-plugins.conf`.

For a foreground check, as the unprivileged worker account:

```sh
python3 -m plugin_runtime.supervisor --engine docker \
  --socket /run/mws-plugins/worker.sock --work "$HOME/jobs" \
  --image sha256:REPLACE_WITH_ACTUAL_IMAGE_ID \
  --api-origin https://YOUR_MWS_ORIGIN
```

For service startup install `deploy/mare-plugin-runtime-docker.service` into that
account's `~/.config/systemd/user/`. Create
`~/.config/mws-plugin-worker/environment` (mode 0600):

```ini
MARE_PLUGIN_IMAGE=sha256:REPLACE_WITH_ACTUAL_IMAGE_ID
MARE_WORKER_API_ORIGIN=https://YOUR_MWS_ORIGIN
```

As that account:

```sh
systemctl --user daemon-reload
systemctl --user enable --now mare-plugin-runtime-docker.service
```

`deploy/mws-plugins-web.conf` is the web service drop-in; set
`MARE_PLUGIN_WORKER_SOCKET=/run/mws-plugins/worker.sock` and restart your existing
web service after installing it. `MARE_PLUGIN_CONNECTORS_JSON` is optional on the
supervisor only; leave it unset unless approved operational plugins require an
explicit HTTPS connector allowlist. `MARE_PLUGINS_DIR` configures the web server's
operator-managed package directory. The Podman unit is an alternative to the
Docker unit, never an additional service. No Compose deployment exists to update.

Health check from an account with socket-group access:

```sh
MARE_PLUGIN_WORKER_SOCKET=/run/mws-plugins/worker.sock \
  python3 -m plugin_runtime.healthcheck
```

Normal session-authenticated, CSRF-protected lifecycle routes are
`POST /plugins/registry/<validated-id>/run`,
`GET /plugins/executions/<execution-id>` and
`POST /plugins/executions/<execution-id>/cancel`. POST bodies use a form `payload`
JSON object and CSRF field. Runs accept optional `case_id`, `artifact`, `inputs`,
and an installed `version`; they require `plugins:read`, `plugins:execute`, an
enabled installed plugin, ownership and every manifest permission. Arbitrary
source, archive uploads and development modes are not accepted. Logs and status
remain available for operational integrations and Activity history; there is no
browser execution console. Version enable/disable and rollback retain their
existing server permission checks.

An optional connector setting on the supervisor can map a named service to one
reviewed HTTPS origin and a configured secret field, for example:

```json
{"intel":{"origin":"https://intel.example.test","secret_field":"service_key","header":"Authorization","prefix":"Bearer "}}
```

Store this JSON as `MARE_PLUGIN_CONNECTORS_JSON` in the worker environment file.
The plugin calls `context.external("intel", "/lookup")`; the gateway adds the
configured secret, performs a bounded GET without redirects, and returns JSON.
Paths are limited to slashes, letters, digits, underscores and hyphens. Direct
container network access remains disabled. Leave connectors unset by default.

## Verification and troubleshooting

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_installed_plugins.py tests/test_plugin_runtime.py
MARE_TEST_PLUGIN_IMAGE=sha256:YOUR_REVIEWED_IMAGE_ID MARE_TEST_WORKER_ENGINE=docker \
  PYTHONPATH=.:sdk .venv/bin/pytest -q tests/worker
```

The second command runs real container tests, including folder discovery through
the application lifecycle, stdout/stderr, exceptions, isolation, cancellation,
timeout and cleanup. They skip unless an actual reviewed image is configured;
unit test results alone do not prove a container ran. A missing socket only makes
operational runs unavailable. Check the service journal, socket group/access,
pinned image availability, rootless/seccomp configuration, cgroup delegation and
approved image dependencies. Never solve an engine check by using privileged
Docker, exposing its socket to the web service or executing plugins in Flask.

## Removing an older editor deployment

After active jobs finish, stop and disable whichever old user unit you installed:
`mare-developer-worker-docker.service` or `mare-developer-worker.service`. Remove
that unit, its web drop-in `mws-developer-web.conf`, its tmpfiles configuration and
`MARE_DEVELOPER_*` settings. Remove old image IDs only after confirming they are
unused; do not prune Docker or delete plugin/data directories. Install the normal
runtime above only if operational plugin execution is needed. The SDK, REST API,
other tool workers and plugin packages do not need those old editor services.
