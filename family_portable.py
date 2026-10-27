"""One shared family section in Export All, never in individual case archives."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
from family_reports import verify_report, storage_transaction, MAX_REPORTS, shared_storage_transaction
from profile_types import FAMILY, ACTOR
from profile_workspace import profile_tag
from contextlib import nullcontext
from malware_families import family_tag, safe_url
from family_aliases import load_aliases, validate_aliases, save_aliases
from tagging import create as create_tag, now
SCHEMA = 'mare-family-library/1'
FIELDS = ('id', 'name', 'short_description', 'long_description', 'attribution_notes', 'created_at', 'updated_at', 'version')
REPORT_FIELDS = ('id', 'family_id', 'title', 'original_filename', 'description', 'storage_ref', 'size', 'file_type', 'sha256', 'uploaded_at')

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def export_profiles(connection, root, *, spec=FAMILY, ids=None):
    users = {row['id']: {'username': row['username'], 'user_uuid': row['user_uuid']} for row in connection.execute('SELECT id,username,user_uuid FROM users')}
    families = []
    for row in connection.execute(f'SELECT f.*,t.name AS tag,i.identity FROM {spec.table} f JOIN tags t ON t.id=f.tag_id JOIN family_tag_identities i ON i.tag_id=t.id ORDER BY f.id'):
        if ids is not None and row['id'] not in ids:
            continue
        record = {key: row[key] for key in FIELDS}
        record['aliases'] = load_aliases(row['aliases'])
        record.update(tag=row['tag'], tag_identity=row['identity'], created_by=users.get(row['created_by']), updated_by=users.get(row['updated_by']))
        record['osint'] = [dict(entry) for entry in connection.execute(f'SELECT * FROM {spec.osint_table} WHERE {spec.foreign_key}=? ORDER BY position,id', (row['id'],))]
        record['reports'] = []
        for report in connection.execute(f'SELECT * FROM {spec.reports_table} WHERE {spec.foreign_key}=? ORDER BY uploaded_at,id', (row['id'],)):
            verify_report(root, report, spec=spec)
            record['reports'].append({**{key: report[key] for key in report_fields(spec)}, 'uploaded_by': users.get(report['uploaded_by'])})
        if spec.actor:
            from threat_actors import export_associations
            record['known_families'] = export_associations(connection, row['id'])
        families.append(record)
    if ids is None and len(families) != connection.execute(f'SELECT count(*) FROM {spec.table}').fetchone()[0]:
        raise ValueError('A malware family has a missing tag identity; repair it before exporting.')
    if ids is None and sum((len(f['reports']) for f in families)) != connection.execute(f'SELECT count(*) FROM {spec.reports_table}').fetchone()[0]:
        raise ValueError('An attached report has a missing parent family.')
    return {'schema': SCHEMA, spec.key: families}

def validate_profiles(data, root, *, spec=FAMILY):
    if not isinstance(data, dict) or set(data) != {'schema', spec.key} or data['schema'] != SCHEMA or (not isinstance(data[spec.key], list)) or (len(data[spec.key]) > 10000):
        raise ValueError(f'Unsupported shared {spec.lower} library.')
    profiles = set()
    tags = set()
    identities = set()
    entries = set()
    attachments = set()

    def identity(value):
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError('Invalid shared library identity.')

    def user(value):
        if value is not None and (not isinstance(value, dict) or set(value) != {'username', 'user_uuid'} or (not isinstance(value['username'], str)) or (len(value['username']) > 200) or (not isinstance(value['user_uuid'], str)) or (len(value['user_uuid']) > 100)):
            raise ValueError('Invalid shared library user reference.')
    for record in data[spec.key]:
        if not isinstance(record, dict) or set(record) - ({'aliases', 'known_families'} if spec.actor else {'aliases'}) != set(FIELDS) | {'tag', 'tag_identity', 'created_by', 'updated_by', 'osint', 'reports'}:
            raise ValueError('Invalid family library record.')
        if 'aliases' in record:
            if validate_aliases(record['aliases']) != record['aliases']:
                raise ValueError('Family library aliases must be trimmed.')
        if spec.actor:
            from threat_actors import validate_associations
            validate_associations(record.get('known_families'))
        identity(record['id'])
        if not isinstance(record['tag'], str) or not isinstance(record['tag_identity'], str):
            raise ValueError('Invalid profile tag identity.')
        if record['id'] in profiles or record['tag'] in tags or record['tag_identity'] in identities or (profile_tag(record['tag'], spec) != record['tag']) or (not re.fullmatch('[a-f0-9]{32}', record['tag_identity'])):
            raise ValueError('Duplicate or invalid family/tag identity.')
        profiles.add(record['id'])
        tags.add(record['tag'])
        identities.add(record['tag_identity'])
        for field, limit in (('name', 200), ('short_description', 1000), ('long_description', 100000), ('attribution_notes', 100000), ('created_at', 100), ('updated_at', 100)):
            if not isinstance(record[field], str) or len(record[field]) > limit:
                raise ValueError('Invalid family library text.')
        if not record['name'].strip() or type(record['version']) is not int or record['version'] < 1:
            raise ValueError('Invalid family name or version.')
        user(record['created_by'])
        user(record['updated_by'])
        if not isinstance(record['osint'], list) or len(record['osint']) > 1000 or (not isinstance(record['reports'], list)) or (len(record['reports']) > MAX_REPORTS):
            raise ValueError('Shared family record limits exceeded.')
        positions = set()
        for entry in record['osint']:
            if not isinstance(entry, dict) or set(entry) != {'id', spec.foreign_key, 'title', 'url', 'position'}:
                raise ValueError('Invalid shared OSINT entry.')
            identity(entry['id'])
            if entry['id'] in entries or entry[spec.foreign_key] != record['id'] or type(entry['position']) is not int or (entry['position'] < 1) or (entry['position'] in positions) or (not isinstance(entry['title'], str)) or (not entry['title'].strip()) or (len(entry['title']) > 300):
                raise ValueError('Invalid shared OSINT relationship/order.')
            safe_url(entry['url'])
            entries.add(entry['id'])
            positions.add(entry['position'])
        for report in record['reports']:
            if not isinstance(report, dict) or set(report) != set(report_fields(spec)) | {'uploaded_by'}:
                raise ValueError('Invalid shared report record.')
            identity(report['id'])
            if report['id'] in attachments or report[spec.foreign_key] != record['id'] or (not isinstance(report['title'], str)) or (not report['title'].strip()) or (len(report['title']) > 300) or (not isinstance(report['description'], str)) or (len(report['description']) > 10000) or (not isinstance(report['uploaded_at'], str)) or (len(report['uploaded_at']) > 100):
                raise ValueError('Invalid shared report relationship or metadata.')
            user(report['uploaded_by'])
            verify_report(root, report, spec=spec)
            attachments.add(report['id'])
    return {'profiles': len(profiles), 'osint': len(entries), 'reports': len(attachments)}

def check_profile_conflicts(connection, root, data, *, spec=FAMILY):
    """Never silently overwrite destination research; exact repeats are skipped."""
    current = {record['id']: record for record in export_profiles(connection, root, spec=spec)[spec.key]}
    skip = set()
    for record in data[spec.key]:
        fid = record['id']
        if fid in current:
            incoming = fingerprint(record)
            local = fingerprint(current[fid])
            state = connection.execute(f'SELECT * FROM {spec.stem}_import_state WHERE {spec.foreign_key}=?', (fid,)).fetchone()
            comparison = dict(current[fid])
            if 'aliases' not in record:
                comparison.pop('aliases', None)
            if incoming == fingerprint(comparison) or (state and state['incoming_hash'] == incoming and (state['local_hash'] == local)):
                skip.add(fid)
                continue
            raise ValueError(f"Shared family conflict: {record['name']}. Keep the destination research, or explicitly delete/relink the conflicting profile after retaining a backup, then preview again. No shared records were overwritten.")
        tag = connection.execute('SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE t.normalized_name=? OR i.identity=?', (record['tag'], record['tag_identity'])).fetchall()
        if tag and (len(tag) != 1 or tag[0]['name'] != record['tag'] or tag[0]['identity'] != record['tag_identity']):
            raise ValueError('Shared tag identity/name conflict for ' + record['tag'] + '. Resolve it explicitly in Tags before retrying; unrelated IDs are never reused.')
        if tag and connection.execute(f'SELECT 1 FROM {spec.table} WHERE tag_id=?', (tag[0]['id'],)).fetchone():
            raise ValueError('A destination profile already uses ' + record['tag'] + '. Resolve its profile-to-tag conflict before retrying.')
        for entry in record['osint']:
            if connection.execute(f'SELECT 1 FROM {spec.osint_table} WHERE id=?', (entry['id'],)).fetchone():
                raise ValueError('OSINT entry identity collision.')
        for report in record['reports']:
            if connection.execute(f'SELECT 1 FROM {spec.reports_table} WHERE id=?', (report['id'],)).fetchone() or (Path(root) / report['storage_ref']).exists():
                raise ValueError('Attached report identity or storage collision.')
    return skip

def restore_profiles(connection, root, staged, data, registry=None, *, spec=FAMILY, changes=None):
    validate_profiles(data, staged, spec=spec)

    def user(source):
        if source is None:
            return None
        row = connection.execute('SELECT id FROM users WHERE username=?', (source['username'],)).fetchone()
        return row[0] if row else None
    with (storage_transaction(connection, root, spec=spec) if changes is None else nullcontext(changes)) as changes:
        if registry:
            from backup_areas import merge_registry
            merge_registry(connection, registry)
        skip = check_profile_conflicts(connection, root, data, spec=spec)
        for record in data[spec.key]:
            if record['id'] in skip:
                continue
            tid, _ = create_tag(connection, record['tag'])
            connection.execute('UPDATE family_tag_identities SET identity=? WHERE tag_id=?', (record['tag_identity'], tid))
            connection.execute(f'INSERT INTO {spec.table}(id,name,short_description,long_description,attribution_notes,created_at,updated_at,version,tag_id,created_by,updated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)', [*[record[key] for key in FIELDS], tid, user(record['created_by']), user(record['updated_by'])])
            save_aliases(connection, record['id'], record.get('aliases', []), table=spec.table)
            for entry in record['osint']:
                connection.execute(f'INSERT INTO {spec.osint_table} VALUES(?,?,?,?,?)', [entry[key] for key in ('id', spec.foreign_key, 'title', 'url', 'position')])
            for report in record['reports']:
                shutil.copyfile(Path(staged) / report['storage_ref'], changes.folder / (report['id'] + '.bin'))
                changes.publish(report['id'])
                connection.execute(f'INSERT INTO {spec.reports_table} VALUES(?,?,?,?,?,?,?,?,?,?,?)', [*[report[key] for key in report_fields(spec)], user(report['uploaded_by'])])
        if spec.actor:
            from threat_actors import restore_associations
            for record in data[spec.key]:
                if record['id'] not in skip:
                    restore_associations(connection, record['id'], record['known_families'])
        local = {r['id']: r for r in export_profiles(connection, root, spec=spec)[spec.key]}
        for record in data[spec.key]:
            connection.execute(f'INSERT OR REPLACE INTO {spec.stem}_import_state VALUES(?,?,?)', (record['id'], fingerprint(record), fingerprint(local[record['id']])))
    return {**validate_profiles(data, staged, spec=spec), 'unchanged': len(skip)}


def report_fields(spec):
    return tuple(spec.foreign_key if field == 'family_id' else field for field in REPORT_FIELDS)


def export_library(connection, root, *, include_actors=True, include_families=True):
    # Relationships have one portable representation: actor.known_families.
    # A selective family export includes its related actors, and those actors'
    # family dependencies, without pulling in unrelated actors or cases.
    related = {r[0] for r in connection.execute('SELECT DISTINCT actor_id FROM actor_families WHERE family_id IS NOT NULL')} if include_families else set()
    actor_data = export_profiles(connection, root, spec=ACTOR, ids=None if include_actors else related)['actors']
    dependencies = {link['family_uuid'] for actor in actor_data for link in actor['known_families'] if link['available']}
    data = export_profiles(connection, root, ids=None if include_families else dependencies)
    data['actors'] = actor_data
    return data


def profile_data(data, spec):
    return {'schema': data['schema'], spec.key: data.get(spec.key, [])}


def validate_library(data, root):
    if not isinstance(data, dict) or not {'schema', 'families'} <= set(data) or set(data) - {'schema', 'families', 'actors'}:
        raise ValueError('Unsupported shared research library.')
    counts = validate_profiles(profile_data(data, FAMILY), root)
    if 'actors' in data:
        actor_counts = validate_profiles(profile_data(data, ACTOR), root, spec=ACTOR)
        counts['actors'] = actor_counts['profiles']
        counts['actor_reports'] = actor_counts['reports']
    return counts


def check_conflicts(connection, root, data):
    skip = check_profile_conflicts(connection, root, profile_data(data, FAMILY))
    if data.get('actors'):
        check_profile_conflicts(connection, root, profile_data(data, ACTOR), spec=ACTOR)
        from threat_actors import check_dependencies
        check_dependencies(connection, data['actors'], data['families'])
    return skip


def restore_library(connection, root, staged, data, registry=None):
    validate_library(data, staged)
    # One transaction and durable journals for both stores; any failure rolls back
    # the research profiles, associations and both sets of report publications.
    with shared_storage_transaction(connection, root, (FAMILY, ACTOR)) as stores:
        if registry:
            from backup_areas import merge_registry
            merge_registry(connection, registry)
        check_conflicts(connection, root, data)
        result = restore_profiles(connection, root, staged, profile_data(data, FAMILY), changes=stores[FAMILY])
        if data.get('actors'):
            actor_result = restore_profiles(connection, root, staged, profile_data(data, ACTOR), spec=ACTOR, changes=stores[ACTOR])
            result.update(actors=actor_result['profiles'], actor_reports=actor_result['reports'])
    return result
