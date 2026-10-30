# Reusable task collections

Case Workbench → Tasks keeps the existing task editor, Markdown descriptions,
images, priorities, and three states. Its shared application tabs provide **Case
tasks** and **Collection library**. The same library is available at
`/task-collections`; collections are global, not owned by a Case.

Case task checkboxes select definitions to save to a collection. They do not set
status. Filtering preserves selection and shows a count and Clear selection.
Status changes use the separate status control. Groups and Case totals show
completed/total counts; Custom tasks contains existing and individually added
tasks. Task rows support editing, deletion and accessible move-up/down controls.
Task completion is advisory and never blocks Case progression. Other existing
report/deliverable completion requirements remain in force.

## Authoring and application

Create collections directly in the library, or select Case tasks and choose **Add
to collection**. The contextual editor supports a new collection or appending to
an owned/managed collection, removal and ordering of the selected definitions,
and duplicate-name warnings. Duplicate names are retained, never merged.
Only names and descriptions are copied; Case IDs, status, priority, assignment and
history are not template fields. Descriptions remain Markdown text; case-local
image files are not published into the library. Use reusable guidance and avoid
case-specific or confidential details, including links to case-local assets.

**Add task collection** opens a right-side drawer with search, category filtering,
ordered preview and selected-task counts. Initial tasks are selected. Adding
copies their names/descriptions/order into a new Case group and starts each at
**Not Started**, with Normal priority. The Case retains a group-name snapshot,
source collection ID/revision, a source fingerprint, immutable selected-definition
snapshots, and per-task template IDs. Updating or deleting the
library collection never changes these copies.

For a previously applied collection, the drawer shows application dates. Missing
mode adds only template IDs never previously applied, even if a previous copy was
renamed or deleted. Another copy must be selected explicitly and creates a
separate group. Task IDs are used instead of matching names. Requests carry an
opaque idempotency key; the same key and payload replay the original result.
Reusing a key with different content fails. Application, task insertion, provenance,
and audit recording are one serialized SQLite transaction.

A changed collection revision rejects an open preview with HTTP 409; the drawer
notifies the analyst and refreshes before requiring another confirmation.
Removing a Case group requires confirmation and deletes its copied tasks, not
its global collection. Application history/audit is retained.

## Migration and permissions

Startup applies additive migration `task-collections-v1`. Existing task IDs,
names, descriptions, dates, priorities, done flags and states are unchanged.
New nullable provenance columns leave existing tasks in Custom tasks. The initial
position follows existing task ID order. No production collections or tasks are
seeded.

New tables:

- `task_collections`: current definitions, permanent UUID, creator and revision.
- `task_collection_revisions`: historical definition snapshots; retained on delete.
- `task_groups`: independent Case group names and provenance snapshots.
- `task_collection_applications`: idempotency records and previously applied IDs.

Authenticated users can browse the global library. Existing `cases:read` and
`cases:update` rights govern Case tasks. New explicit permissions are:

| Permission | Scope |
| --- | --- |
| `task_collections:create` | Create global guidance |
| `task_collections:update` | Update/append to collections created by the caller |
| `task_collections:delete` | Delete collections created by the caller |
| `task_collections:manage` | Manage any collection |

Administrators can manage all collections. Standard User defaults include the
first three permissions. During migration, existing roles with `cases:update`
receive those three owner-scoped permissions. Broader management is not granted
automatically. Future custom roles use the existing role-management interface.

Every write checks current permissions on the server. Case mutations also recheck
workflow stage and mandatory active ownership inside their transaction. New and
Completed Cases remain read-only under the existing rules. The library remains
readable, and editing global guidance uses its independent permissions. Collection
creation, revision, deletion, application, and Case task/group changes are audited.

## REST API and Python SDK

Versioned endpoints use the existing bearer-token model. Session UI adapters use
the same service and existing CSRF protection. Existing task endpoints and SDK
`client.tasks` methods remain compatible and now expose optional provenance.

| Endpoint | Methods |
| --- | --- |
| `/api/v1/task-collections` | GET (q/category/limit/offset), POST |
| `/api/v1/task-collections/{collection_id}` | GET, PATCH, DELETE |
| `/api/v1/cases/{cid}/task-groups` | GET: tasks, groups, provenance, editability |
| `/api/v1/cases/{cid}/task-collections` | POST: create/append selected Case definitions |
| `/api/v1/cases/{cid}/task-collections/{collection_id}/apply` | POST |
| `/api/v1/cases/{cid}/task-order` | PUT: complete ordered IDs within a group |
| `/api/v1/cases/{cid}/task-groups/{gid}` | DELETE with `confirm: true` |

Collection updates replace the ordered template array and require the current
revision. Preserve existing template IDs when editing definitions. Omit an ID for
a new template. Creating a collection requires 1–500 definitions; names are at
most 200 characters, descriptions 20,000 and categories 100.

```python
import uuid
from mws_sdk import MWSClient

with MWSClient() as client:
    # Read available collections; this does not apply anything.
    available = client.task_collections.list(params={"category": "Windows"})

    # Explicit writes. Supply guidance chosen by the analyst.
    guide = client.task_collections.create(data={
        "name": "Document review",
        "tasks": [{"name": "Review document structure", "description": "Record findings."}],
    }).collection
    result = client.task_collections.apply(case_id, guide.id, data={
        "revision": guide.revision,
        "template_ids": [task.id for task in guide.tasks],
        "mode": "missing",  # or explicit "copy"
        "request_key": uuid.uuid4().hex,
    })
```

Both sync and async SDK resources are generated from the live reviewed OpenAPI
contract. [The command-line example](../sdk/examples/task_collections.py) defaults
to listing; `--apply` is required for writes. Regenerate the SDK in a disposable
data directory after contract changes:

```sh
MARE_DATA_DIR=/tmp/mws-sdk-review PYTHONPATH=.:sdk .venv/bin/python scripts/build_sdk.py
```

## Backup and restore

**Task Collections** is a dedicated selectable Import & Export data type. Its
filename code is `TC`, appended to the existing ordered codes. Collection-only
archives contain current global definitions and all their ordered revisions, with
no Cases. The existing single-archive validation, preview, conflict decisions and
results interface displays collection and template counts.

Portable restore matches collection UUIDs, never names. Exact identities/content
and revision histories are retained on repeat import. Different content under the
same UUID requires an explicit keep-destination or replace decision. Different
UUIDs with the same name remain separate collections. Creator attribution uses
exact destination usernames, following the existing portable Case restoration
rules; source numeric user IDs are never trusted. Unmapped creators remain
unowned, manageable by Administrators or explicitly authorized managers.

Case-only backups carry copied task content, state, ordering, group-name snapshots,
immutable source definitions/fingerprints, application history and source IDs/revisions. They do not contain or create global collections. A
missing source collection does not break restored tasks; restoring a collection
separately reconnects provenance through its permanent ID. Application history in
a Case snapshot preserves previously applied template IDs, while transport retry
keys are scoped to the restored Case rather than replaying old task row IDs.

Complete backups include every SQLite table, revision history, application/audit
records, creators, tasks, groups and states. Older archives with no collection
section remain supported. Complete snapshots from before this feature receive its
additive migration only after their original checksums/counts validate. Other
historical schema incompatibilities retain the existing upgrade-copy rules.

## Verification

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_task_collections.py tests/test_task_workspace.py tests/test_api.py tests/test_backups.py tests/test_backup_workspace.py tests/test_case_sync.py tests/test_backup_presentation.py tests/test_backup_filenames.py tests/test_api_documentation.py tests/test_sdk_integration.py tests/test_sdk_api_extensions.py tests/test_sidebar_hierarchy.py sdk/tests
npm run test:task-collections
node tests/browser/backup-import-model.cjs
```

Tests cover legacy task preservation, owner/RBAC/closed-Case checks, definitions
from selected tasks, independent copies, repeat/concurrent application, transaction
rollback, real SDK calls, selective/complete/older backup restoration, conflict
resolution, and real browser authoring/drawer/mobile behavior. No task execution,
scheduling, dependencies or mandatory playbook stages are introduced.
