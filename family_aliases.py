"""Ordered profile aliases, independent of shared application tags."""
import json

MAX_ALIASES = 50
MAX_ALIAS_LENGTH = 200


def validate_aliases(values):
    if not isinstance(values, list) or len(values) > MAX_ALIASES:
        raise ValueError('Use at most 50 aliases per malware family.')
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError('Aliases must be text.')
        value = value.strip()
        if not value or len(value) > MAX_ALIAS_LENGTH or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Each alias must contain 1–200 characters without control characters.')
        key = value.casefold()
        if key in seen:
            raise ValueError('Aliases must be unique within a profile (ignoring capitalization).')
        seen.add(key)
        result.append(value)
    return result


def load_aliases(value):
    try:
        return validate_aliases(json.loads(value))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid malware-family aliases collection.') from exc


def save_aliases(connection, fid, values, *, table="malware_families"):
    if table not in ("malware_families", "threat_actors"):
        raise ValueError("Unknown profile type.")
    connection.execute(f'UPDATE {table} SET aliases=? WHERE id=?',
                       (json.dumps(validate_aliases(values), ensure_ascii=False), fid))


def initialize(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(malware_families)')}
    with connection:
        if 'aliases' not in columns:
            connection.execute("ALTER TABLE malware_families ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
        connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES('family-aliases-v1')")
