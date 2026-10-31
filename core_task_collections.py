"""Bundled, stable identities installed into the existing revisioned collection library."""
import json
from pathlib import Path

MIGRATION = 'core-task-collections-v1'
RESOURCE = Path(__file__).with_name('resources') / 'core_task_collections.json'


def definitions():
    return json.loads(RESOURCE.read_text())['collections']


def reserved_ids():
    return frozenset(item['id'] for item in definitions())


def install(connection):
    """Only a newer bundled revision changes Core rows. Never touch Case copies."""
    from task_collections import now
    with connection:
        # Serialize concurrent application starts before inspecting revisions/schema.
        connection.execute('BEGIN IMMEDIATE')
        if 'origin' not in {r[1] for r in connection.execute('PRAGMA table_info(task_collections)')}:
            connection.execute("ALTER TABLE task_collections ADD COLUMN origin TEXT NOT NULL DEFAULT 'custom'")
        for bundled in definitions():
            current = connection.execute('SELECT origin,revision,created FROM task_collections WHERE id=?', (bundled['id'],)).fetchone()
            if current:
                if current[0] != 'core':
                    raise ValueError('A custom collection uses a reserved Core identity; no collection was overwritten.')
                if current[1] >= bundled['revision']:
                    continue
            stamp = now()
            record = {key: bundled[key] for key in ('id','name','description','category','tasks','revision')}
            record.update(creator_uuid=None, creator_name='MWS Core', created=current[2] if current else stamp, updated=stamp, origin='core')
            columns = ('id','name','description','category','tasks','revision','creator_uuid','creator_name','created','updated','origin')
            connection.execute(
                'INSERT INTO task_collections ('+','.join(columns)+') VALUES(?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,category=excluded.category,'
                'tasks=excluded.tasks,revision=excluded.revision,updated=excluded.updated',
                tuple(json.dumps(record[k]) if k=='tasks' else record[k] for k in columns))
            connection.execute('INSERT INTO task_collection_revisions VALUES(?,?,?)', (record['id'],record['revision'],json.dumps(record)))
        connection.execute('INSERT OR IGNORE INTO schema_migrations VALUES(?)', (MIGRATION,))
