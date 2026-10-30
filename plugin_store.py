"""Installed plugin package validation and immutable runtime snapshots."""

import ast
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile
from datetime import datetime, timezone

MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
MAX_FILES = 200
DATA_PERMISSIONS = frozenset(
    (
        "cases:read",
        "cases:update",
        "cases:assets",
        "indicators:read",
        "indicators:write",
        "references:read",
        "references:write",
        "reports:read",
        "reports:write",
    )
)
RESERVED = {
    ".git",
    ".env",
    "__pycache__",
    ".venv",
    "node_modules",
    ".pytest_cache",
    "logs",
    "secrets",
    "plugin-config.json",
}



def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def safe_path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 240
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Use a relative plugin path of at most 240 characters.")
    parts = value.split("/")
    if value.startswith("/") or any(
        p in ("", "..", ".") or p.casefold() in RESERVED for p in parts
    ):
        raise ValueError("Unsafe or reserved plugin path.")
    if len(parts) > 12 or str(PurePosixPath(value)) != value:
        raise ValueError("Invalid plugin path.")
    return value


def manifest(value):
    if not isinstance(value, dict):
        raise ValueError("plugin.json must be an object.")
    allowed = {
        "schema",
        "id",
        "name",
        "description",
        "version",
        "author",
        "entrypoint",
        "api_version",
        "sdk_version",
        "plugin_api",
        "permissions",
        "dependencies",
        "configuration",
    }
    if set(value) - allowed:
        raise ValueError(
            "Unknown plugin manifest fields: " + ", ".join(sorted(set(value) - allowed))
        )
    if (
        value.get("schema") != "mws-plugin/1"
        or value.get("api_version") != "v1"
        or value.get("plugin_api") != "1"
        or value.get("sdk_version") != ">=1,<2"
    ):
        raise ValueError("Requires mws-plugin/1, plugin API 1, REST v1 and SDK >=1,<2.")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", str(value.get("id", ""))):
        raise ValueError(
            "Plugin IDs use 3–64 lowercase letters, digits, underscores or hyphens."
        )
    if not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[A-Za-z0-9.-]+)?",
        str(value.get("version", "")),
    ):
        raise ValueError("Use a semantic version, e.g. 1.0.0.")
    for key, maximum in (("name", 120), ("description", 2000), ("author", 200)):
        if (
            not isinstance(value.get(key), str)
            or (key != "description" and not value[key].strip())
            or len(value[key]) > maximum
        ):
            raise ValueError("Invalid " + key + ".")
    entry = str(value.get("entrypoint", "")).split(":")
    if (
        len(entry) != 2
        or not entry[0].endswith(".py")
        or not re.fullmatch(r"[A-Za-z_]\w*", entry[1])
    ):
        raise ValueError(
            "Entry point must be a Python file and function, e.g. main.py:run."
        )
    safe_path(entry[0])
    permissions = value.get("permissions", [])
    if (
        not isinstance(permissions, list)
        or len(permissions) > len(DATA_PERMISSIONS)
        or any(not isinstance(p, str) or p not in DATA_PERMISSIONS for p in permissions)
        or len(set(permissions)) != len(permissions)
    ):
        raise ValueError("Declare unique supported investigation permissions only.")
    dependencies = value.get("dependencies", [])
    if (
        not isinstance(dependencies, list)
        or len(dependencies) > 30
        or any(
            not isinstance(p, str)
            or len(p) > 120
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]+(?:==|>=|<=|~=|>|<)[A-Za-z0-9.*,+<>=!-]+", p
            )
            for p in dependencies
        )
    ):
        raise ValueError(
            "Use bounded package requirements; URLs, paths and arbitrary install arguments are forbidden."
        )
    configuration = value.get("configuration", {})
    if not isinstance(configuration, dict) or len(configuration) > 30:
        raise ValueError("At most 30 configuration fields are supported.")
    for key, field in configuration.items():
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
            or not isinstance(field, dict)
            or set(field)
            - {"type", "required", "secret", "enum", "description", "default"}
        ):
            raise ValueError("Invalid configuration field.")
        if (
            field.get("type") not in ("string", "number", "boolean")
            or type(field.get("required", False)) is not bool
            or type(field.get("secret", False)) is not bool
        ):
            raise ValueError(
                "Configuration fields require string, number or boolean types."
            )
        if field.get("secret") and (field["type"] != "string" or "default" in field):
            raise ValueError("Secret fields must be strings without defaults.")
        if "enum" in field and (
            not isinstance(field["enum"], list) or not 1 <= len(field["enum"]) <= 30
        ):
            raise ValueError("Invalid configuration options.")
        from developer_configuration import validate_value

        if "description" in field and (
            not isinstance(field["description"], str)
            or len(field["description"]) > 1000
        ):
            raise ValueError("Invalid configuration description.")
        for option in field.get("enum", []):
            validate_value({k: v for k, v in field.items() if k != "enum"}, option)
        if "default" in field:
            validate_value(field, field["default"])
    return value


def initialize(connection):
    # Preserve the released registry schema/default for SQLite backup compatibility.
    # New registrations explicitly become Installed; no draft API or lifecycle remains.
    connection.executescript(
        """
    CREATE TABLE IF NOT EXISTS developer_plugins(
      id TEXT PRIMARY KEY,owner_uuid TEXT NOT NULL,name TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,
      development TEXT NOT NULL DEFAULT 'Draft',enabled INTEGER NOT NULL DEFAULT 0,published_version TEXT,
      configuration TEXT NOT NULL DEFAULT '{}',secret_box BLOB,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS plugin_packages(plugin_id TEXT PRIMARY KEY REFERENCES developer_plugins(id),archive BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS developer_versions(
      plugin_id TEXT NOT NULL REFERENCES developer_plugins(id),version TEXT NOT NULL,fingerprint TEXT NOT NULL,
      archive BLOB NOT NULL,manifest TEXT NOT NULL,publisher_uuid TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(plugin_id,version));
    CREATE TABLE IF NOT EXISTS developer_executions(
      id TEXT PRIMARY KEY,plugin_id TEXT NOT NULL,plugin_version TEXT NOT NULL,fingerprint TEXT NOT NULL,
      owner_uuid TEXT NOT NULL,case_id INTEGER,mode TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,
      ended_at TEXT,duration REAL,worker_id TEXT,details TEXT NOT NULL DEFAULT '{}',snapshot BLOB NOT NULL,grant_id INTEGER,
      FOREIGN KEY(grant_id) REFERENCES api_tokens(id) ON DELETE SET NULL);
    CREATE INDEX IF NOT EXISTS developer_execution_owner ON developer_executions(owner_uuid,started_at);
    CREATE UNIQUE INDEX IF NOT EXISTS developer_case_running ON developer_executions(case_id) WHERE mode='run' AND status IN ('Starting','Running');
    CREATE TABLE IF NOT EXISTS developer_grants(
      token_id INTEGER PRIMARY KEY REFERENCES api_tokens(id) ON DELETE CASCADE,execution_id TEXT NOT NULL,permissions TEXT NOT NULL,case_id INTEGER,artifact TEXT);
    INSERT OR IGNORE INTO schema_migrations VALUES('developer-workspace-v1');
    """
    )
    if "artifact" not in {
        row[1] for row in connection.execute("PRAGMA table_info(developer_grants)")
    }:
        connection.execute("ALTER TABLE developer_grants ADD COLUMN artifact TEXT")
    if "source_location" not in {
        row[1] for row in connection.execute("PRAGMA table_info(developer_plugins)")
    }:
        connection.execute(
            "ALTER TABLE developer_plugins ADD COLUMN source_location TEXT"
        )
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations VALUES('developer-package-discovery-v1')"
    )
    connection.commit()
    retire_editor_schema(connection)


def files(connection, pid):
    row = connection.execute("SELECT archive FROM plugin_packages WHERE plugin_id=?", (pid,)).fetchone()
    return inspect_archive(bytes(row[0]))[0] if row else {}


def retire_editor_schema(connection):
    """Forward-only upgrade. Preserve packages/configuration/history, revoke obsolete sessions."""
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'developer_plugins' not in tables:
        return
    connection.execute("CREATE TABLE IF NOT EXISTS plugin_packages(plugin_id TEXT PRIMARY KEY REFERENCES developer_plugins(id),archive BLOB NOT NULL)")
    if 'developer_files' in tables:
        for (pid,) in connection.execute('SELECT id FROM developer_plugins').fetchall():
            entries = {r[0]: dict(body=bytes(r[1]),directory=bool(r[2])) for r in connection.execute('SELECT path,body,directory FROM developer_files WHERE plugin_id=?',(pid,))}
            if entries:
                connection.execute('INSERT OR IGNORE INTO plugin_packages VALUES(?,?)',(pid,archive(entries)))
        connection.execute('DROP TABLE developer_files')
    connection.execute("UPDATE developer_plugins SET development=CASE WHEN published_version IS NULL THEN 'Uninstalled' ELSE 'Installed' END")
    if 'developer_executions' in tables:
        connection.execute("UPDATE api_tokens SET revoked=? WHERE id IN (SELECT grant_id FROM developer_executions WHERE mode!='run') AND revoked IS NULL",(now(),))
        connection.execute("UPDATE developer_executions SET status='Canceled',ended_at=? WHERE mode!='run' AND status IN ('Starting','Running')",(now(),))
    if 'role_permissions' in tables:
        # Registration is still a normal folder-plugin permission; keep existing grants.
        connection.execute("INSERT OR IGNORE INTO role_permissions SELECT role_name,'plugins:install' FROM role_permissions WHERE permission='plugins:create'")
        connection.execute("DELETE FROM role_permissions WHERE permission IN ('plugins:create','plugins:edit','plugins:validate','plugins:test','plugins:debug','plugins:publish')")
    connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES('retire-developer-editor-v1')")
    connection.commit()


def validate_tree(entries):
    if (
        len(entries) > MAX_FILES
        or sum(len(v["body"]) for v in entries.values()) > MAX_TOTAL
    ):
        raise ValueError("Workspace exceeds size limits.")
    seen = set()
    canonical = {}
    for path, item in entries.items():
        safe_path(path)
        if len(item["body"]) > MAX_FILE:
            raise ValueError("Files are limited to 2 MiB.")
        folded = path.casefold()
        if folded in seen:
            raise ValueError("Case-insensitive path collisions are forbidden.")
        seen.add(folded)
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            logical = "/".join(parts[:index])
            previous = canonical.setdefault(logical.casefold(), logical)
            if previous != logical:
                raise ValueError("Case-insensitive path collisions are forbidden.")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if parent in entries and not entries[parent]["directory"]:
                raise ValueError("A file cannot contain children.")
    return entries


def fingerprint(entries):
    return digest(
        dumps(
            [
                (path, item["directory"], digest(item["body"]))
                for path, item in sorted(entries.items())
            ]
        ).encode()
    )


def archive(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, item in sorted(entries.items()):
            safe_path(path)
            z.writestr(path + "/" if item["directory"] else path, item["body"])
    return out.getvalue()


def inspect_archive(raw):
    if len(raw) > MAX_TOTAL:
        raise ValueError("Plugin archives are limited to 20 MiB.")
    entries = {}
    total = 0
    compressed_total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise ValueError("At most 200 plugin entries are supported.")
        for info in infos:
            path = safe_path(
                info.filename.rstrip("/") if info.is_dir() else info.filename
            )
            if (
                path in entries
                or info.flag_bits & 1
                or (
                    stat.S_IFMT(info.external_attr >> 16)
                    not in (0, stat.S_IFREG, stat.S_IFDIR)
                )
            ):
                raise ValueError(
                    "Duplicate, encrypted or symbolic-link entries are forbidden."
                )
            compressed_total += info.compress_size
            if compressed_total > MAX_TOTAL or info.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise ValueError("Archive compression exceeds supported limits.")
            total += info.file_size
            if (
                info.file_size > MAX_FILE
                or total > MAX_TOTAL
                or (
                    info.file_size > 1024 * 1024
                    and info.file_size > max(1, info.compress_size) * 200
                )
            ):
                raise ValueError("Plugin archive expansion exceeds resource limits.")
            body = z.read(info)
            entries[path] = dict(body=body, directory=info.is_dir())
    validate_tree(entries)
    validated = static_validation(entries)
    if not validated["valid"]:
        raise ValueError("; ".join(d["message"] for d in validated["diagnostics"][:5]))
    return entries, validated["manifest"]


def static_validation(entries):
    diagnostics = []
    value = None
    try:
        validate_tree(entries)
        value = manifest(json.loads(entries["plugin.json"]["body"].decode("utf-8")))
        if "requirements.txt" in entries:
            requirements = [
                line.strip()
                for line in entries["requirements.txt"]["body"]
                .decode("utf-8")
                .splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if set(requirements) != {"mws-sdk>=1,<2", *value.get("dependencies", [])}:
                raise ValueError(
                    "requirements.txt must match the SDK and bounded dependencies declared in plugin.json."
                )
        path, function = value["entrypoint"].split(":")
        if path not in entries:
            raise ValueError("The entry-point file does not exist.")
        for name, item in entries.items():
            safe_path(name)
            if item["directory"] or not name.endswith(".py"):
                continue
            if len(item["body"]) > 1024 * 1024:
                raise ValueError("Python files are limited to 1 MiB.")
            try:
                tree = ast.parse(item["body"].decode("utf-8"), filename=name)
                if name == path and not any(
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == function
                    for n in tree.body
                ):
                    raise ValueError("Entry-point function does not exist.")
                for node in ast.walk(tree):
                    names = (
                        [n.name for n in node.names]
                        if isinstance(node, ast.Import)
                        else (
                            [node.module or ""]
                            if isinstance(node, ast.ImportFrom)
                            else []
                        )
                    )
                    if any(
                        n.split(".")[0]
                        in (
                            "app",
                            "api",
                            "sqlite3",
                            "sqlalchemy",
                            "psycopg",
                            "plugin_routes",
                            "plugin_execution",
                            "plugin_runtime",
                            "developer_configuration",
                            "plugin_store",
                        )
                        for n in names
                    ):
                        raise ValueError(
                            "Plugins must use mws_sdk; backend/database imports are forbidden."
                        )
            except SyntaxError as error:
                diagnostics.append(
                    dict(
                        path=name,
                        line=error.lineno or 1,
                        severity="error",
                        message=error.msg,
                    )
                )
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
        diagnostics.append(
            dict(path="plugin.json", line=1, severity="error", message=str(error))
        )
    return dict(
        valid=not diagnostics,
        manifest=value,
        diagnostics=diagnostics,
        scope="Static manifest/syntax checks only; isolated import/type checks and tests are required before publishing.",
    )
