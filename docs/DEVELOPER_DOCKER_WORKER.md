# Developer execution with rootless Docker

The Editor diagnostic `Isolated developer worker is not configured.` comes from
`developer_worker/client.py` when the **web process** lacks
`MARE_DEVELOPER_WORKER_SOCKET`. The previous supervisor implemented rootless Podman
only; installing Docker did not configure or start it. The worker now supports
Docker through the same private Unix-socket contract, runtime, manifest entrypoint,
installed SDK and per-execution API gateway. No plugin Python runs in Flask.

There is no Compose deployment in this repository. Use a dedicated Linux account,
rootless Docker user service and the supplied worker user service. The supervisor
runs on the same Linux host as its daemon so bind mounts and Unix sockets resolve
locally. Do not put the supervisor in the web service or mount an engine socket in
any plugin container. Docker Desktop and remote Docker daemons are not supported
by this deployment configuration.

## Provision the host

As administrator, create `mws-worker` with a home directory and subordinate UID/GID
ranges, following [Docker's rootless installation instructions](https://docs.docker.com/engine/security/rootless/).
Install rootless Docker for that account and enable lingering. This deployment
requires Linux, systemd, cgroup v2, default seccomp, and delegated CPU, memory, swap
and PID limits. The supervisor refuses startup when Docker does not report these
capabilities. Do not give this account access to MWS data, database or secret files.

From the repository root, as administrator (adjust the web account name if needed):

```sh
sudo groupadd -f mws-developer
sudo usermod -aG mws-developer mws-worker
sudo usermod -aG mws-developer mare-work-sequencer
sudo loginctl enable-linger mws-worker
sudo install -d -m 0755 /opt/mws-worker/developer_worker
sudo install -m 0644 developer_worker/*.py /opt/mws-worker/developer_worker/
sudo install -m 0644 deploy/mws-developer-tmpfiles.conf /etc/tmpfiles.d/mws-developer.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/mws-developer.conf
sudo install -d /etc/systemd/system/mare-work-sequencer.service.d
sudo install -m 0644 deploy/mws-developer-web.conf /etc/systemd/system/mare-work-sequencer.service.d/developer.conf
```

Start a fresh login session for `mws-worker` after group changes. Install the
rootless Docker daemon with `dockerd-rootless-setuptool.sh install` in that session
if not already installed. Run `systemctl --user enable --now docker.service`.
The Docker context selected for **this account** must target its local rootless
daemon. Never point it at a rootful daemon. Run `docker info` to verify.

## Build and start

As `mws-worker`, from a reviewed checkout with no production secrets:

```sh
docker build -f developer_worker/Containerfile -t mws-developer:reviewed .
mkdir -p ~/.config/mws-worker ~/.config/systemd/user
chmod 700 ~/.config/mws-worker
docker image inspect mws-developer:reviewed --format 'MARE_DEVELOPER_IMAGE={{.Id}}' > ~/.config/mws-worker/environment
printf '%s\n' 'MARE_WORKER_API_ORIGIN=https://mws.internal.example' >> ~/.config/mws-worker/environment
chmod 600 ~/.config/mws-worker/environment
cp deploy/mare-developer-worker-docker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mare-developer-worker-docker.service
```

Replace `https://mws.internal.example` with the trusted HTTPS MWS API origin before
starting. No registry is required: the local immutable `sha256:…` image ID is
accepted. Registry references pinned as `repository@sha256:…` also work if already
pulled. Mutable tags are rejected. The image installs Python 3.12, the repository
SDK, basedpyright, debugpy, pytest and reviewed dependencies. Dependencies are never
installed from plugin code at execution time.

As administrator, restart the web service to apply its socket/group configuration:

```sh
sudo systemctl daemon-reload
sudo systemctl restart mare-work-sequencer.service
```

| Setting | Process | Value |
| --- | --- | --- |
| `MARE_DEVELOPER_WORKER_SOCKET` | Web / health check | `/run/mws-developer/worker.sock` |
| `MARE_DEVELOPER_IMAGE` | Worker unit | Actual local image ID or registry digest |
| `MARE_WORKER_API_ORIGIN` | Worker unit | Trusted HTTPS MWS origin |
| `DOCKER_HOST` or `DOCKER_CONTEXT` | Worker, optional | Local rootless daemon if not the account default |
| `MARE_DEVELOPER_CONNECTORS_JSON` | Worker, optional | Administrator-approved external connectors; omit by default |

The supervisor forwards only engine configuration to its Docker CLI, never the
application environment. Containers receive no API token or connector secrets.
The gateway holds scoped credentials and applies the existing permission checks.
Editor runs accept no case selection and are read-only through declared SDK API
permissions. A plugin with no API permissions has no authorized API access.

## Health and verification

As either authorized socket group member, with Python able to import the worker:

```sh
MARE_DEVELOPER_WORKER_SOCKET=/run/mws-developer/worker.sock PYTHONPATH=/opt/mws-worker python3 -m developer_worker.healthcheck
systemctl --user status mare-developer-worker-docker.service
journalctl --user -u mare-developer-worker-docker.service -n 100
```

Health checks verify RPC availability and that Docker can inspect the configured
image; startup checks verify engine confinement and resource support. Health does
not replace a real execution probe. From the checkout, in a test virtualenv with
MWS test dependencies, run as the worker account:

```sh
export MARE_TEST_WORKER_IMAGE="$(docker image inspect mws-developer:reviewed --format '{{.Id}}')"
MARE_TEST_WORKER_ENGINE=docker PYTHONPATH=.:sdk .venv/bin/pytest -q tests/worker
MARE_TEST_WORKER_ENGINE=docker PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_developer_worker_integration.py
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_developer_execution.py tests/test_developer_docker_worker.py tests/test_plugin_pages.py
```

`tests/worker` actually executes Hello World, an exception, a 60-second timeout,
cancellation, and filesystem/network probes, then checks container and workspace
cleanup. Without `MARE_TEST_WORKER_IMAGE`, these tests explicitly skip. Unit tests
and browser fixtures are not evidence that a container ran.

For an Editor smoke test, register the included `examples/hello_world_plugin`
package through Plugins using your normal plugin directory, select it in
Developer → Editor and click Run. No case is needed. The console expands, Output
shows `Hello World`, and Debug shows the context diagnostic plus worker lifecycle
messages. Cancel is enabled while an execution is active. Replace the function
body with `raise ValueError("deliberate failure")` to check Debug exception output.
The browser → API → worker smoke test must be performed against the deployed host.

## Isolation and cleanup

Each job uses a non-root UID, no network, no capabilities, no new privileges,
read-only root filesystem, 1 CPU, 512 MiB RAM with no extra swap, 64 processes,
bounded `/work` and `/tmp` tmpfs and read-only mounts of only its snapshot and
per-job API socket. The engine socket, host application files and database are
never mounted. Snapshot file modes explicitly permit the container UID to read
under the service's restrictive umask.

The supervisor enforces a 60-second execution timeout (600 seconds for language
and debugger sessions), captures stdout/stderr separately, records exceptions on
stderr, reports status/duration/exit code, and kills/removes the container on
cancel or timeout. Completion waits for resource cleanup. Output is capped at
256 KiB. SIGTERM stops active jobs. A host crash or SIGKILL can prevent cleanup;
after an abnormal supervisor termination inspect `docker ps -a --filter
name=mws-dev-` and remove only its abandoned job containers before restarting.
Do not run multiple supervisors under the same account/work directory.

## Troubleshooting

- Missing configuration diagnostic: set the socket in the **Gunicorn service**,
  then restart it. Setting it only in an interactive terminal has no effect.
- Connection refused/missing socket: inspect the worker user unit and Docker user
  unit logs. Confirm `/run/mws-developer` was created by tmpfiles at boot.
- Permission denied: verify the socket directory group is `mws-developer`, directory
  mode is 2770, socket mode is 0660, and both services have fresh group membership.
- Startup refuses rootless/seccomp/cgroups: fix the host's rootless Docker setup;
  do not remove the checks. Docker documents that rootless resource flags require
  [cgroup v2 and systemd](https://docs.docker.com/engine/security/rootless/tips/).
- Image missing: build under the same worker account/daemon and update the image
  ID in its environment file, then restart the worker unit.
- Missing Python imports: rebuild the reviewed image with approved dependencies.
- SDK errors: verify the trusted API origin/certificate and user/plugin permissions.
  Direct network calls from plugins are blocked by design.
