"""Data-area registry and explicit portable tag identity mappings."""

import copy
import json
import re
from pathlib import Path
from dataclasses import dataclass
from tagging import name, create
from family_portable import (
    check_conflicts,
    SCHEMA as FAMILY_SCHEMA,
)


@dataclass(frozen=True)
class Area:
    key: str
    label: str
    table: str | None
    description: str
    dependencies: tuple = ()
    available: bool = True
    formats: tuple = ("mare-backup/1", "mare-case-backup/3")

    def count(self, con):
        return (
            con.execute(f"SELECT count(*) FROM {self.table}").fetchone()[0]
            if self.table
            else None
        )

    def export(self, helpers):
        return helpers["export"]

    def validate(self, helpers):
        return helpers["stage_upload"]

    def importer(self, app):
        return app.extensions["case_import_sync"]


AREAS = (
    Area(
        "cases",
        "Case data",
        "cases",
        "Editable RAW case records, assets, samples and relationship mappings.",
        ("tags",),
    ),
    Area(
        "families",
        "Malware families",
        "malware_families",
        "Profiles, ordered OSINT links and attached report bytes.",
        ("tags",),
    ),
    Area(
        "tags", "Tags", "tags", "Shared tag definitions and permanent tag identities."
    ),
    Area("actors", "Threat actors", "threat_actors", "Profiles, aliases, TA_ tags, related Malware Family dependencies, ordered OSINT and attached report bytes; unrelated cases are excluded.", ("tags", "families")),
)
KEYS = {a.key for a in AREAS if a.available}


def initialize(con):
    con.executescript(
        """CREATE TABLE IF NOT EXISTS backup_tag_aliases(
      source_identity TEXT PRIMARY KEY,tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
      canonical_name TEXT NOT NULL);
      INSERT OR IGNORE INTO schema_migrations VALUES('backup-workspace-v1');"""
    )
    con.commit()


def selection(values, complete=False):
    if not isinstance(values, list) or any(v not in KEYS for v in values):
        raise ValueError("Choose implemented data areas only.")
    chosen = KEYS if complete else set(values)
    if not chosen:
        raise ValueError("Select at least one data area.")
    dependencies = sorted(
        {d for a in AREAS if a.key in chosen for d in a.dependencies} - chosen
    )
    return sorted(chosen), dependencies


def validate_tags(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Invalid tag identity registry.")
    names = set()
    ids = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"name", "identity", "created_at"}
            or name(row["name"]) != row["name"]
            or not isinstance(row["identity"], str)
            or not re.fullmatch("[a-f0-9]{32}", row["identity"])
            or not isinstance(row["created_at"], str)
            or len(row["created_at"]) > 100
        ):
            raise ValueError("Invalid tag identity record.")
        if row["name"] in names or row["identity"] in ids:
            raise ValueError("Duplicate tag identity or name.")
        names.add(row["name"])
        ids.add(row["identity"])
    return rows


def resolve(con, root, staged, choices):
    """Pure destination planning; choices are applied only after a new preview."""
    path = Path(staged) / "tag-registry.json"
    rows = validate_tags(json.loads(path.read_text())) if path.exists() else []
    conflicts = []
    mapping = []
    rewrites = {}
    for row in rows:
        source = row["identity"]
        local = con.execute(
            "SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE i.identity=?",
            (source,),
        ).fetchone()
        alias = con.execute(
            "SELECT t.id,t.name,i.identity FROM backup_tag_aliases a JOIN tags t ON t.id=a.tag_id JOIN family_tag_identities i ON i.tag_id=t.id WHERE a.source_identity=? AND a.canonical_name=t.name",
            (source,),
        ).fetchone()
        byname = con.execute(
            "SELECT t.id,t.name,i.identity FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE t.normalized_name=?",
            (row["name"],),
        ).fetchone()
        local = local or alias
        if local and local["name"] != row["name"]:
            conflicts.append(
                dict(
                    key="tag:" + source,
                    label="Tag identity was renamed: " + row["name"],
                    options=[],
                )
            )
            continue
        if not local and byname:
            key = "tag:" + source
            if choices.get(key) != "reuse":
                conflicts.append(
                    dict(
                        key=key,
                        label="Different tag identity uses " + row["name"],
                        options=[
                            [
                                "reuse",
                                "Reuse this canonical tag as an explicit verified mapping",
                            ]
                        ],
                    )
                )
                continue
            local = byname
        if local:
            rewrites[source] = local["identity"]
        mapping.append(
            {
                **row,
                "target_identity": local["identity"] if local else source,
                "outcome": "Reuse verified tag" if local else "Add tag",
            }
        )
    library_path = Path(staged) / "family-library.json"
    library = (
        json.loads(library_path.read_text())
        if library_path.exists()
        else {"schema": FAMILY_SCHEMA, "families": []}
    )
    library = copy.deepcopy(library)
    retained = []
    for record in library["families"]:
        record["tag_identity"] = rewrites.get(
            record["tag_identity"], record["tag_identity"]
        )
        try:
            check_conflicts(con, root, {"schema": FAMILY_SCHEMA, "families": [record]})
        except ValueError as exc:
            key = "family:" + record["id"]
            if choices.get(key) == "keep":
                continue
            conflicts.append(
                dict(
                    key=key,
                    label=str(exc),
                    options=[
                        [
                            "keep",
                            "Keep destination family; skip this incoming family and its reports",
                        ]
                    ],
                )
            )
        retained.append(record)
    library["families"] = retained
    actor_retained = []
    from family_portable import check_profile_conflicts, profile_data
    from profile_types import ACTOR
    from threat_actors import check_dependencies
    for record in library.get('actors', []):
        actor_skip = set()
        actor_conflicts = []
        record['tag_identity'] = rewrites.get(record['tag_identity'], record['tag_identity'])
        for link in record['known_families']:
            link['tag_identity'] = rewrites.get(link['tag_identity'], link['tag_identity'])
            if link['available']:
                link['target_tag_identity'] = rewrites.get(link['target_tag_identity'], link['target_tag_identity'])
        try:
            actor_skip = check_profile_conflicts(con, root, {'schema': FAMILY_SCHEMA, 'actors': [record]}, spec=ACTOR)
            check_dependencies(con, [record], retained)
        except ValueError as exc:
            key = 'actor:' + record['id']
            if choices.get(key) == 'keep':
                continue
            actor_conflicts.append(dict(key=key, label=str(exc), options=[['keep', 'Keep destination research; skip this incoming actor and its reports']]))
        if record['id'] not in actor_skip:
            skip_actor = False
            for link in record['known_families']:
                if link['available']:
                    continue
                key = 'actor-unavailable:' + record['id'] + ':' + link['family_uuid']
                decision = choices.get(key)
                if decision == 'skip':
                    skip_actor = True
                    break
                if decision != 'retain':
                    actor_conflicts.append(dict(key=key, label='Unavailable family association: ' + link['family_name'] + ' for ' + record['name'], options=[['retain', 'Retain this association explicitly as unavailable; do not attach a replacement'], ['skip', 'Skip the incoming actor and its reports']]))
            if skip_actor:
                continue
        conflicts.extend(actor_conflicts)
        actor_retained.append(record)
    if 'actors' in library:
        library['actors'] = actor_retained
    return conflicts, mapping, library


def merge_registry(con, rows):
    for row in rows:
        target = con.execute(
            "SELECT t.id,t.name FROM tags t JOIN family_tag_identities i ON i.tag_id=t.id WHERE i.identity=?",
            (row["target_identity"],),
        ).fetchone()
        if target:
            if target["name"] != row["name"]:
                raise ValueError("Tag mapping changed; refresh the preview.")
            tid = target["id"]
        else:
            if con.execute(
                "SELECT 1 FROM tags WHERE normalized_name=?", (row["name"],)
            ).fetchone():
                raise ValueError("New tag name conflict; refresh the preview.")
            tid, _ = create(con, row["name"])
            con.execute(
                "UPDATE tags SET created_at=? WHERE id=?", (row["created_at"], tid)
            )
            con.execute(
                "UPDATE family_tag_identities SET identity=? WHERE tag_id=?",
                (row["target_identity"], tid),
            )
        con.execute(
            "INSERT OR REPLACE INTO backup_tag_aliases VALUES(?,?,?)",
            (row["identity"], tid, row["name"]),
        )
