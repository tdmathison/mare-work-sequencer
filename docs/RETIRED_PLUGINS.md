# Retirement upgrade and legacy backups

MWS no longer installs, discovers, configures, or runs application plugins.
Developer contains API and SDK only. External analyst scripts continue to use
personal bearer tokens and the installable Python SDK. No extension service,
container image, package directory, or extension environment variable is needed.

## Existing deployments

Stop the web application before deploying the removal release so old web workers
cannot accept submissions. Stop the retired runtime **using its old service unit
before replacing its files**: its SIGTERM handler cancels jobs and waits for their
container cleanup. Run these only for the unit actually installed, as its existing
worker account (these were user units, not the application host's system unit):

```sh
systemctl --user disable --now mare-plugin-runtime.service
# Or, for the rootless Docker variant:
systemctl --user disable --now mare-plugin-runtime-docker.service
systemctl --user is-active mare-plugin-runtime.service mare-plugin-runtime-docker.service
```

After confirming both units are inactive and their job containers stopped, stale
Starting/Running database records can be marked canceled **before deployment**.
Use the actual MWS data directory and its virtual environment:

```sh
.venv/bin/python - /actual/mws-data/workflow.sqlite3 <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as con:
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='developer_executions'").fetchone():
        con.execute("UPDATE developer_executions SET status='Canceled',ended_at=datetime('now') WHERE status IN ('Starting','Running')")
PY
```

Alternatively, if the old worker is still reachable through its configured Unix
socket, the one-time startup migration revokes delegated capabilities and cancels
only recorded active jobs through the old cancellation endpoint. It stops the
upgrade rather than drop those records if shutdown cannot be confirmed. No new
jobs can be submitted by this release. Archives never contact a worker.

Remove the web service's retired drop-in and tmpfiles rule **only if installed
from these former MWS deployment files**, then reload the service manager:

```sh
sudo rm -- /etc/systemd/system/mare-work-sequencer.service.d/plugins.conf
sudo rm -- /etc/tmpfiles.d/mws-plugins.conf
sudo systemctl daemon-reload
```

As the worker account, remove its dedicated installed unit file(s) after stopping:

```sh
rm -- ~/.config/systemd/user/mare-plugin-runtime.service
rm -- ~/.config/systemd/user/mare-plugin-runtime-docker.service
systemctl --user daemon-reload
```

Remove obsolete assignments from the deployment's environment configuration:
`MARE_PLUGINS_DIR`, `MARE_PLUGIN_WORKER_SOCKET`, `MARE_PLUGIN_IMAGE`,
`MARE_PLUGIN_CONNECTORS_JSON`, `MARE_WORKER_API_ORIGIN`, and any earlier
`MARE_DEVELOPER_*` execution/language-service settings. Do not remove variables
used by supported tool workers. Restart MWS after deploying and configuring it.

Operator-authored packages, dedicated worker workspaces and environments, old
images, sockets, and the worker account/group are **not automatically deleted**.
Inspect those exact locations from the retired service/environment files and
archive or remove them manually if no longer needed. Do not run Docker/system
prune, remove unrelated containers, or recursively delete shared directories.
No cleanup commands in this document are executed by the application.

## Database and backups

The additive `remove-plugins-v1` migration drops the obsolete registry, versions,
package BLOBs, file drafts, execution and grant tables; removes delegated tokens,
`plugins:*` role assignments and plugin-only settings; and leaves existing released
migration markers intact. It does not edit historical audit events, Case notes,
references, personal API tokens, global Help, or supported jobs. No retired tables
are created on a fresh installation.

New complete backups omit retired directories and database data. Existing
operator-owned retired directories in the destination are left outside complete
replacement and its old-data cleanup; administrators remove them separately. Old complete
archives still pass the existing path, symlink, size, checksum and supported-record
validation, including skipped members. Their obsolete directories are never
extracted. Database retirement removes obsolete data before publication; snapshot
VACUUM prevents package/configuration BLOBs surviving in SQLite free pages.
Restore results and web previews report that legacy plugin data was skipped.
Portable Case/MIP content and user-authored text mentioning plugins stay intact.
