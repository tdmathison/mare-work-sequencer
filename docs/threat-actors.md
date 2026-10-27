# Threat Actors

The authenticated **Threat Actors** tab (`/threat-actors`) uses the same profile
workspace, alias chips, optimistic edit guards, pagination, OSINT editor and durable
report infrastructure as Malware Families. The shared implementation is in
`profile_workspace.py`, `profile_types.py`, and `family_reports.py`; existing
Malware Families URLs and behavior remain supported.

Create/Edit fields are name, aliases, Tag, short description, long description,
and Known Malware Families. Names require 1–200 characters. Optional aliases use
the existing Enter-to-add gold chips, preserve capitalization/order, trim whitespace,
and reject empty/case-insensitive duplicates (50 aliases, 200 characters each).
Aliases never create shared tags. Failed validation, stale versions, unavailable
families and database write failures preserve the submitted form.

## Access, tags and History

- `tags:read` permits profiles, family choices and report downloads.
- `tags:manage` together with read permission permits profile/OSINT/report changes.
- `tags:create` is additionally required when saving a new shared tag.
- `cases:read` controls case counts, current-case History and case links.
- Backup & Restore retains its existing `backups:manage` authorization.

Every mutation requires the existing CSRF token. The literal canonical tag prefix
is `TA_` with a nonempty suffix and normal shared-tag rules. An existing tag is
reused; a new tag, stable identity, profile and relationships are saved atomically.
The database enforces one actor profile per tag. Tags-page **View threat actor**
and **Create threat actor** links mirror Malware Families; GET only selects a tag
and does not create data. Deleted/renamed/replaced tag selections and concurrent
creation receive existing conflict handling.

Tag deletion/merge and renaming outside the TA_ namespace are blocked while an
actor references the tag. Relink or delete the profile explicitly first. Relinking
a profile preserves both shared tags and case assignments. History is the bounded,
paginated set of distinct existing cases **currently carrying the selected TA_
tag**, with current lifecycle states. Refreshing reads current records; related
MAL_ tags or family associations never add cases to this list.

## Shared actor–family associations

The searchable keyboard-operable picker offers configured family profiles, showing
both name and current MAL_ tag. An unlinked MAL_ tag is not a configured family.
Up to 100 distinct associations are stored in order using stable family UUIDs and
tag identity snapshots. The Overview links to the same internal family profiles.
These are analyst-created relationships, without an implied attribution confidence.
Selecting/removing one does not change any tag, case assignment or either History.

Malware Family Create/Edit Profile forms offer the corresponding **Known Threat
Actors** picker, limited to existing configured actor profiles by name or TA_ tag.
Standalone TA_ tags are excluded. Both controls edit `actor_families`; no separate
reverse list is stored. Family Overview shows linked actor names/tags in a
structured section after Long description, with an explicit empty state. Existing
free-text descriptions and attribution notes are preserved.

A rename or tag relink preserves the relationship to the same profile UUID, and
both Overviews resolve current names/tags. Saving adds/removes the same edge on
both sides immediately; duplicate submissions are rejected and changes are
transactional. Family selections display in name order; an actor's family list
keeps its saved order. New associations allow up to 100 distinct profiles per side.
The other profile's edit version advances when membership changes, preventing an
older open form from silently restoring or deleting a newer relationship.

Deleting either profile removes its live associations and advances surviving
profiles' versions. Related profiles, shared tags, case assignments and cases are
preserved. Owned OSINT and reports follow existing deletion behavior. Profile,
tag relink, association, OSINT and report changes are audited.

Legacy unavailable references retained by older versions remain explicitly
unavailable; migration does not discard them or silently attach a same-name/tag
replacement. Remove/save an unavailable reference before deliberately selecting a
restored profile. New family deletions remove live edges rather than creating new
unavailable references.

## Reports and storage

PDF, DOC and DOCX use the same bounded validation as family reports: 25 MiB/file,
10 files and 75 MiB/batch, 100 reports/profile. Actual bytes live under
`MARE_DATA_DIR/actor-reports/<uuid>.bin`. Names are display metadata; storage paths
are derived from validated UUIDs. Reports download as attachments with private
no-store, nosniff and sandbox headers. They are never executed or previewed inline.

`actor-report-staging` contains durable file-operation journals. Startup recovery
uses the corresponding actor report records to undo interrupted publication or
finalize committed removals. Profile deletion, upload and removal serialize file
and database changes. Shared family/actor imports use one database transaction and
journals for both stores, so publication failures roll back both profile sets and
new report files together.

## Migrations and backup compatibility

Startup adds `threat-actors-v1` (actor profiles, OSINT, associations and namespace /
family-deletion triggers) and `actor-reports-v1` (report metadata and import state).
`profile-associations-v2` adds the reverse lookup index and symmetric deletion
triggers, retaining the existing relationship table and every live or legacy
unavailable row. It does not rewrite profile descriptions, tags, or case records.
Existing family, tag, case and alias data is retained. Aliases are ordered JSON
collections; profile and attachment IDs are UUIDs. Numeric source user IDs are
never used to identify destination users during selective imports.

Complete installation payloads now use `mare-installation-backup/3`, required
migration `threat-actors-v1`, and include actor counts, all tables, relationships,
report hashes and actual bytes. Formats 1 and 2 remain accepted. Known additive
alias/actor migrations run on a staged copy **after** the original archive's
hashes and counts are verified. Other schema incompatibilities still block web
replacement. Complete replacement retains its explicit acknowledgement, rollback,
account handoff and session invalidation behavior.

Selective **Threat actors** exports include actors, aliases, TA_ tags, ordered
OSINT, report bytes and only their referenced available configured family profiles
and required tags. Those dependencies are named in the export summary; unrelated
cases and unrelated families are excluded. Selective **Malware families** exports
include the full family library plus only its associated actors and their required
family/tag dependencies, including those actor profiles' OSINT/report bytes.
The preview identifies these dependencies and counts before export/import.
Relationships retain their existing portable representation in each actor's
`known_families` collection; no duplicate reverse collection or new archive format
is needed. Export All includes each global research profile
and report once; individual case archives never duplicate them.

The existing shared-library format accepts an optional `actors` section. Older
backups without it leave destination actors untouched. Exact repeated imports
skip existing research. Changed actor/family research follows the existing
conflict policy: keep destination/skip incoming, or retain a backup and explicitly
resolve the difference before importing again. There is no silent overwrite.

Incoming live family references require the exact family UUID and target tag
identity, either already present or included in the planned family import. Missing,
changed or ambiguous dependencies become preview conflicts; restore the matching
family or skip the incoming actor. Separate archives work by importing the matching
family profiles first, then retrying the actor import. If their research differs,
the existing keep-destination/skip-incoming conflict choice still applies; identity
matching is rechecked against the retained destination. Missing dependencies block
that actor instead of inventing a placeholder or matching only by name/tag. Incoming deliberately unavailable relationships
require an explicit preview choice to retain them as unavailable or skip that
actor. They never bind to a same-name/tag replacement. Existing identical actor
records remain idempotent without a new missing-link choice.

## Privacy and verification

Management routes remain authenticated. The separate [public Threat Actors
dashboard](actor-dashboard.md) exposes only approved profile summaries and aggregate
counts through its dedicated projection. Aliases, associations, private research,
report metadata/bytes, OSINT URLs and case details remain private.

Run relevant server coverage with:

```sh
PYTHONPATH=. .venv/bin/pytest -q tests/test_profile_associations.py tests/test_threat_actors.py tests/test_malware_families.py tests/test_family_reports.py tests/test_family_aliases.py tests/test_backup_workspace.py tests/test_navigation.py tests/test_tagging.py tests/test_tag_names.py tests/test_settings_navigation.py tests/test_tools.py tests/test_dashboard_directory.py tests/test_cases_dashboard.py tests/test_family_dashboard.py
node tests/browser/threat-actors.cjs
node tests/browser/malware-families.cjs
node tests/browser/tools-navigation.cjs
```

The actor browser test uses disposable data and installed Chrome. It covers an
existing TA_ tag → aliases/family picker → OSINT/report and hash-checked download →
tag-only History → edit/reopen, plus Tags navigation, search failure/empty states,
safe rendering, unsaved changes and desktop/narrow layouts. Server tests additionally
cover concurrency, family deletion/relinking, permissions, pagination, file cleanup,
complete/selective recovery into fresh instances with different numeric tag IDs,
missing dependencies, legacy formats and rollback of cross-profile publication.

The wider suite still has 11 failures reproduced against an unchanged HEAD copy:
report downloads, audit markup, autosave assumptions, stale Metrics navigation /
permissions, legacy import redirects and workflow expectations. `tests/test_samples.py`
has an existing indentation error on line 21 and was excluded from that wider run.
These unrelated issues remain unchanged. Browser verification used Chrome; other
browser engines were not exercised. Production data was not available or modified.
