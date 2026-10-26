"""Threat actor persistence and stable, analyst-created family associations."""
import uuid
from flask import abort, g, jsonify, request
from authorization import has_permission
from family_reports import initialize as initialize_reports
from malware_families import Conflict
from profile_types import ACTOR
from tagging import prototype

MAX_FAMILIES = 100


def initialize(connection):
    if prototype(connection):
        return
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS threat_actors(
      id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
      tag_id INTEGER NOT NULL UNIQUE REFERENCES tags(id) ON DELETE RESTRICT,
      short_description TEXT NOT NULL DEFAULT '', long_description TEXT NOT NULL DEFAULT '',
      attribution_notes TEXT NOT NULL DEFAULT '', aliases TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL, version INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX IF NOT EXISTS threat_actor_name ON threat_actors(name COLLATE NOCASE,id);
    CREATE TABLE IF NOT EXISTS actor_osint(
      id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES threat_actors(id) ON DELETE CASCADE,
      title TEXT NOT NULL, url TEXT NOT NULL, position INTEGER NOT NULL, UNIQUE(actor_id,position));
    CREATE TABLE IF NOT EXISTS actor_families(
      actor_id TEXT NOT NULL REFERENCES threat_actors(id) ON DELETE CASCADE,
      family_uuid TEXT NOT NULL, family_id TEXT REFERENCES malware_families(id) ON DELETE SET NULL,
      family_name TEXT NOT NULL, family_tag TEXT NOT NULL, tag_identity TEXT NOT NULL,
      position INTEGER NOT NULL, PRIMARY KEY(actor_id,family_uuid), UNIQUE(actor_id,position));
    CREATE TRIGGER IF NOT EXISTS actor_tag_namespace_insert BEFORE INSERT ON threat_actors
      WHEN NOT EXISTS(SELECT 1 FROM tags WHERE id=NEW.tag_id AND substr(name,1,3)='TA_' AND length(name)>3)
      BEGIN SELECT RAISE(ABORT,'Actor tags require TA_ and a nonempty suffix.'); END;
    CREATE TRIGGER IF NOT EXISTS actor_tag_namespace_update BEFORE UPDATE OF tag_id ON threat_actors
      WHEN NOT EXISTS(SELECT 1 FROM tags WHERE id=NEW.tag_id AND substr(name,1,3)='TA_' AND length(name)>3)
      BEGIN SELECT RAISE(ABORT,'Actor tags require TA_ and a nonempty suffix.'); END;
    CREATE TRIGGER IF NOT EXISTS actor_tag_rename BEFORE UPDATE OF name ON tags
      WHEN EXISTS(SELECT 1 FROM threat_actors WHERE tag_id=OLD.id)
        AND (substr(NEW.name,1,3)<>'TA_' OR length(NEW.name)<=3)
      BEGIN SELECT RAISE(ABORT,'Relink or delete the threat actor before leaving the TA_ namespace.'); END;
    CREATE TRIGGER IF NOT EXISTS actor_tag_revision AFTER UPDATE OF name ON tags
      WHEN NEW.name<>OLD.name
      BEGIN UPDATE threat_actors SET version=version+1,
        updated_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now'),updated_by=NULL WHERE tag_id=NEW.id; END;
    CREATE TRIGGER IF NOT EXISTS actor_tag_delete BEFORE DELETE ON tags
      WHEN EXISTS(SELECT 1 FROM threat_actors WHERE tag_id=OLD.id)
      BEGIN SELECT RAISE(ABORT,'Relink or delete the threat actor before deleting or merging its tag.'); END;
    CREATE TRIGGER IF NOT EXISTS actor_family_deleted BEFORE DELETE ON malware_families
      BEGIN UPDATE threat_actors SET version=version+1,
        updated_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now'),updated_by=NULL
        WHERE id IN (SELECT actor_id FROM actor_families WHERE family_id=OLD.id); END;
    INSERT OR IGNORE INTO schema_migrations VALUES('threat-actors-v1');
    ''')
    connection.commit()
    initialize_reports(connection, spec=ACTOR)


def associations(connection, actor_id):
    return [dict(row) for row in connection.execute('''
      SELECT a.*,f.name AS current_name,t.name AS current_tag FROM actor_families a
      LEFT JOIN malware_families f ON f.id=a.family_id
      LEFT JOIN tags t ON t.id=f.tag_id WHERE a.actor_id=? ORDER BY a.position
    ''', (actor_id,))]


def choices(connection, values, actor_id=None, *, strict=False):
    if len(values) > MAX_FAMILIES or len(set(values)) != len(values):
        raise ValueError('Choose at most 100 distinct configured Malware Families.')
    previous = {row['family_uuid']:row for row in associations(connection, actor_id)} if actor_id else {}
    result = []
    for value in values:
        try:
            if str(uuid.UUID(value)) != value: raise ValueError()
        except (ValueError, TypeError):
            if strict: raise ValueError('Invalid malware-family profile identity.')
        row = connection.execute('''SELECT f.id AS family_uuid,f.id AS family_id,
          f.name AS family_name,t.name AS family_tag,i.identity AS tag_identity,
          f.name AS current_name,t.name AS current_tag FROM malware_families f
          JOIN tags t ON t.id=f.tag_id JOIN family_tag_identities i ON i.tag_id=t.id WHERE f.id=?''', (value,)).fetchone()
        if value in previous and previous[value]['family_id'] is None:
            result.append(previous[value])  # Never reattach a deleted profile implicitly.
        elif row:
            result.append(dict(row))
        elif value in previous:
            result.append(previous[value])
        elif strict:
            raise Conflict('A selected Malware Family is unavailable. Remove it or choose an existing configured profile; no replacement was linked.')
        else:
            result.append(dict(family_uuid=value, family_id=None, family_name=value, family_tag='Unavailable', current_name=None, current_tag=None, tag_identity=''))
    return result


def save_associations(connection, actor_id, values):
    selected = choices(connection, values, actor_id, strict=True)
    before = associations(connection, actor_id)
    connection.execute('DELETE FROM actor_families WHERE actor_id=?', (actor_id,))
    for position, row in enumerate(selected, 1):
        connection.execute('INSERT INTO actor_families VALUES(?,?,?,?,?,?,?)',
            (actor_id,row['family_uuid'],row['family_id'],row['family_name'],row['family_tag'],row['tag_identity'],position))
    return [(r['family_uuid'],r['tag_identity']) for r in before] != [(r['family_uuid'],r['tag_identity']) for r in selected]


def register_actors(app, db, root):
    with app.app_context():
        initialize(db())
    from profile_workspace import register_profiles
    register_profiles(app, db, root, ACTOR)

    @app.get('/threat-actors/families/search')
    def actors_families_search():
        if not has_permission(g.user, 'tags:read', db()): abort(403)
        query = request.args.get('q','').strip()[:200]
        rows = db().execute('''SELECT f.id,f.name,t.name AS tag FROM malware_families f
          JOIN tags t ON t.id=f.tag_id WHERE instr(lower(f.name),lower(?))>0 OR instr(lower(t.name),lower(?))>0
          ORDER BY f.name COLLATE NOCASE,f.id LIMIT 50''',(query,query)).fetchall()
        response = jsonify(families=[dict(row) for row in rows])
        response.headers['Cache-Control'] = 'private, no-store'
        return response


def export_associations(connection, actor_id):
    result = []
    for row in associations(connection, actor_id):
        current = connection.execute('''SELECT i.identity FROM malware_families f
          JOIN family_tag_identities i ON i.tag_id=f.tag_id WHERE f.id=?''', (row['family_id'],)).fetchone()
        result.append({key:row[key] for key in ('family_uuid','family_name','family_tag','tag_identity','position')}
                      | dict(available=bool(row['family_id']), target_tag_identity=current[0] if current else None))
    return result


def validate_associations(values):
    import re
    from profile_workspace import profile_tag
    from profile_types import FAMILY
    if not isinstance(values, list) or len(values)>MAX_FAMILIES:
        raise ValueError('Invalid known Malware Family collection.')
    seen = set()
    for index, row in enumerate(values, 1):
        if not isinstance(row, dict) or set(row) != {'family_uuid','family_name','family_tag','tag_identity','position','available','target_tag_identity'}:
            raise ValueError('Invalid known Malware Family reference.')
        if not isinstance(row['family_uuid'],str) or str(uuid.UUID(row['family_uuid'])) != row['family_uuid'] or row['family_uuid'] in seen:
            raise ValueError('Invalid or duplicate known Malware Family identity.')
        seen.add(row['family_uuid'])
        if type(row['position']) is not int or row['position']!=index or type(row['available']) is not bool:
            raise ValueError('Invalid family association ordering or availability.')
        if not isinstance(row['family_name'],str) or not row['family_name'].strip() or len(row['family_name'])>200:
            raise ValueError('Invalid family association name.')
        if profile_tag(row['family_tag'],FAMILY)!=row['family_tag'] or not isinstance(row['tag_identity'],str) or not re.fullmatch('[a-f0-9]{32}',row['tag_identity']):
            raise ValueError('Invalid family association tag identity.')
        target = row['target_tag_identity']
        if (row['available'] and (not isinstance(target,str) or not re.fullmatch('[a-f0-9]{32}',target))) or (not row['available'] and target is not None):
            raise ValueError('Invalid family association target identity.')


def check_dependencies(connection, actors, incoming_families=()):
    incoming = {row['id']:row['tag_identity'] for row in incoming_families}
    for actor in actors:
        validate_associations(actor['known_families'])
        for link in actor['known_families']:
            if not link['available']:
                continue  # Deliberately unavailable references stay unavailable.
            local = connection.execute('''SELECT i.identity FROM malware_families f
              JOIN family_tag_identities i ON i.tag_id=f.tag_id WHERE f.id=?''',(link['family_uuid'],)).fetchone()
            identity = local[0] if local else incoming.get(link['family_uuid'])
            if identity != link['target_tag_identity']:
                raise ValueError(f"Threat actor family dependency unavailable or changed: {link['family_name']} ({link['family_uuid']}). Restore the matching configured family or keep the destination actor; names and numeric IDs are never used as substitutes.")


def restore_associations(connection, actor_id, values):
    check_dependencies(connection, [dict(known_families=values)])
    connection.execute('DELETE FROM actor_families WHERE actor_id=?',(actor_id,))
    for row in values:
        connection.execute('INSERT INTO actor_families VALUES(?,?,?,?,?,?,?)',
            (actor_id,row['family_uuid'],row['family_uuid'] if row['available'] else None,
             row['family_name'],row['family_tag'],row['tag_identity'],row['position']))
