"""Forward-only removal of obsolete database/backup data, never a plugin registry.

No package scanning or filesystem deletion. Keep this compatibility code isolated.
"""

import http.client
import json
import os
import re
import socket
from datetime import datetime, timezone

MIGRATION = "remove-plugins-v1"
TABLES = (
    "developer_grants",
    "developer_executions",
    "developer_versions",
    "developer_files",
    "plugin_packages",
    "developer_plugins",
)
DIRECTORIES = frozenset(
    (
        "plugins",
        "plugin-jobs",
        "plugin-runtime",
        "developer-workspaces",
        "developer-jobs",
    )
)


def obsolete_path(relative):
    """Called only after the archive's existing path and symlink validation."""
    return relative.split("/", 1)[0] in DIRECTORIES


def cancel_legacy_job(worker_id):
    """One-time upgrade: only cancel an already recorded job using the old RPC."""
    location = os.environ.get("MARE_PLUGIN_WORKER_SOCKET")
    if not location or not re.fullmatch("[a-f0-9]{32}", worker_id or ""):
        raise RuntimeError(
            "Stop the retired runtime and mark its remaining executions Canceled before upgrading; see docs/RETIRED_PLUGINS.md."
        )
    connection = http.client.HTTPConnection("localhost", timeout=30)
    try:
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        channel.settimeout(30)
        connection.sock = channel
        channel.connect(location)
        connection.request(
            "POST",
            "/jobs/" + worker_id + "/cancel",
            "{}",
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(65537)
        if (
            response.status != 200
            or len(raw) > 65536
            or json.loads(raw).get("status")
            not in ("Canceled", "Failed", "Completed", "Succeeded", "Timed out")
        ):
            raise RuntimeError("Legacy execution did not confirm shutdown.")
    except (OSError, ValueError, http.client.HTTPException, RuntimeError) as error:
        raise RuntimeError(
            "Cannot confirm retired execution shutdown. Stop its runtime, mark remaining executions Canceled, then retry; see docs/RETIRED_PLUGINS.md."
        ) from error
    finally:
        connection.close()


def retire(con, *, live=False):
    tables = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    present = tables.intersection(TABLES)
    delegated = set()
    active = []
    if "developer_grants" in tables:
        delegated.update(
            r[0] for r in con.execute("SELECT token_id FROM developer_grants")
        )
    if "developer_executions" in tables:
        delegated.update(
            r[0]
            for r in con.execute(
                "SELECT grant_id FROM developer_executions WHERE grant_id IS NOT NULL"
            )
        )
        if live:
            active = con.execute(
                "SELECT worker_id FROM developer_executions WHERE status IN ('Starting','Running')"
            ).fetchall()
    if "api_tokens" in tables and delegated:
        for token_id in delegated:
            con.execute(
                "UPDATE api_tokens SET revoked=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), token_id),
            )
        # Even failed shutdown must immediately invalidate delegated capabilities.
        con.commit()
    for (worker_id,) in active:
        cancel_legacy_job(worker_id)
    con.execute("PRAGMA secure_delete=ON")
    for table in TABLES:
        if table in tables:
            con.execute("DROP TABLE " + table)
    if "api_tokens" in tables:
        for token_id in delegated:
            con.execute("DELETE FROM api_tokens WHERE id=?", (token_id,))
    skipped = bool(present)
    if "role_permissions" in tables:
        skipped |= (
            con.execute(
                "DELETE FROM role_permissions WHERE permission GLOB 'plugins:*'"
            ).rowcount
            > 0
        )
    if "site_settings" in tables:
        skipped |= (
            con.execute(
                "DELETE FROM site_settings WHERE name GLOB 'plugin_*' OR name GLOB 'plugins_*' OR name GLOB 'plugins.*' OR name GLOB 'plugins:*' OR name GLOB 'developer_plugins*'"
            ).rowcount
            > 0
        )
    if "schema_migrations" in tables:
        con.execute("INSERT OR IGNORE INTO schema_migrations VALUES(?)", (MIGRATION,))
    con.commit()
    return skipped


def scrub_snapshot(con):
    skipped = retire(con)
    # Removed package/configuration BLOBs must not survive in SQLite free pages.
    con.execute("VACUUM")
    return skipped
