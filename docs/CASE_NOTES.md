# Case Notes — Split Notebook

Open a Case's Notes tab, immediately after Workbench. The notebook uses the shared
Case tabs, CodeMirror Markdown editor/toolbar, and HTML-disabled Markdown renderer.
Existing HTTP/archive byte budgets still apply; the composer adds no character limit.
Raw HTML is escaped, unsafe link protocols are rejected, and image rendering uses
only the existing Case report-image endpoint. Note content never executes.

The feed filters All/User/System, searches body, legacy title and actor, and sorts
by creation instant then ID (offsets normalized for sorting; unknown times sort
first in oldest-first order and last in newest-first order). Counts match the search across all pages **before** the
type filter. Pages hold 30 entries in the UI (API limit 1–500). Refresh loads
concurrent additions. Filter, order and pagination changes preserve the composer.
Successful creation retains feed filters and offers View note; following it clears
the filters and locates the note. Failed writes preserve the draft. Submission IDs
protect creation retries; duplicate submissions with changed content return 409.

## Migration and compatibility

The existing `notes` table is extended additively with per-Case stable note UUIDs,
User/System type, author UUID, edited time, structured event metadata/type, source
identity, and migration time. Existing nonempty reverse-engineering records retain
their exact body, title, author display name and recorded creation time. Each is
labeled Imported reverse engineering notes and displays its actual migration time.
Unknown original times remain unknown. A legacy username alone does not establish
a portable author identity; those records are Administrator-managed. Empty legacy
records do not receive a fabricated notebook entry. Migration is idempotent.

There is one editable record store. `/cases/{id}/notes` form adapters and the
existing versioned REST notes endpoints write that same store. Optional legacy
`title` and `include_export` fields remain supported for existing consumers; the
new composer requires neither. `include_export` defaults false and edits retain
its existing value. The Workbench no longer exposes a separate notes editor.
Private old drafts remain available in the new composer, including legacy titles.
New-note drafts continue saving privately after typing pauses; saving a note waits
for an in-flight draft write so it cannot recreate a submitted draft. Notes are not report
reverse-engineering findings: report section APIs and report documents are unchanged.

## Authorization and activity

Listing/reading requires `cases:read`. Adding requires `cases:update`. Authors
identified by account UUID with edit rights can edit/delete their own User notes;
Administrators can manage User notes. Server identity/timestamps are authoritative.
Ordinary clients cannot create System entries or change provenance. All mutations
reuse the existing `workspace_locked` Case rule, including start-analysis, closed
Cases, and inactive required owners. Opening a composer before closure does not
permit a later write. Reopening restores controls after refresh, with permissions
checked again. Search, reading and preview remain available when closed.

`case_notes.activity(connection, case_id, event_type, message, metadata, source_id)`
is the internal extensible writer. It participates in the caller's transaction and
never commits or recursively logs. Optional source IDs deduplicate trusted events.
The shared CaseSync reconciliation compares a minimal prior state to committed
Case state and aggregates changes per successful operation. Initial coverage:

- Case creation, stage transitions (including completion/reopening), assigned owner.
- Task collection application and removal, including idempotent replay handling.
- Registered Case assets attached/removed.
- Indicator entry additions/removals, summarized by count.
- Snort/YARA signature file additions/removals through shared persistence.

No activity is emitted for views, downloads, identical saves, or note draft saves.
Failed requests roll back note/activity/state changes with the Case transaction.
Existing Cases receive a baseline, not invented historical activity. Replacing an
existing asset at the same registered path is an edit, not an attachment event.
Messages retain object names/counts needed for understanding without file contents,
indicator values, credentials or external links. User-note CRUD also writes the
existing privileged audit log; the notebook does not replace that log.

## API and SDK

`GET /api/v1/cases/{case_id}/notes` accepts `type=all|user|system`, `q`,
`order=newest|oldest`, `limit`, and `offset`. It returns notes, search-relative
counts, total, pagination and current editability. Existing individual-note
GET/PATCH/DELETE paths are unchanged. POST creates only User notes; optional
`request_id` is a 32-character lowercase hex retry identity scoped to Case/author.
Authentication, plugin grants and role permissions use the existing API layer.

```python
entries = client.notes.list(case_id, params={"type": "user", "q": "finding"})
note = client.notes.create(case_id, data={"body": "## Finding\n\nAnalyst observation"}).note
client.notes.update(case_id, note.id, data={"body": "Updated observation"})
client.notes.delete(case_id, note.id)
```

The generated synchronous/asynchronous SDK models and OpenAPI explorer describe
these fields. System entries have no unrestricted public creation endpoint.

## Backups and exports

Complete SQLite backups preserve the notebook and comparison state. Case backups
and RAW MIPs carry all note types, bodies, timestamps, edited state, UUIDs, actor
UUID/display names, event metadata and migration markers in existing case-data
records. Restoration replaces Case records transactionally, retains provenance,
and resets the activity baseline without replaying restored objects. Missing
accounts remain historical actors, never the importing user. Older archives with
only legacy note records remain valid and migrate once; old revision fingerprints
remain verifiable through compatibility normalization. Activity is supplemental
append-only history rather than a semantic ownership/content conflict: unchanged
Case imports merge System entries by stable UUID without replaying events.

Standard recipient-facing MIPs exclude notebook notes, System activity and RAW
metadata. The pre-existing `include_export` compatibility flag continues generating
`reports/reverse-engineering-notes.md` for selected User notes in RAW archives;
Standard package selection is unchanged. System entries cannot opt in through
normal controls. No new backup area or infrastructure is needed.

## Verification

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_case_notes.py tests/test_case_sync.py tests/test_backups.py tests/test_backup_workspace.py sdk/tests
MARE_BROWSER_EXECUTABLE='/path/to/chrome' node tests/browser/case-notes.cjs
```

Browser fixtures use disposable data. Screenshots are written to
`/tmp/mws-notes-{1440,1024,768,390}.png`. Recovery coverage includes an actual
encrypted complete-backup replacement in a fresh application process.
