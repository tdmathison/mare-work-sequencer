# Historical metrics and imported cases

## Cause and behavior

RAW and all-cases backup metadata already contains `case.created` and workflow
`records.history`. The new-case branch of ImportSync previously discarded the
archived creation date and inserted `now()` instead. The Metrics page then
excluded the current partial week and offered only recent full-week windows.
This combination explained completed inventory cards with an empty weekly chart:
inventory counts depend on current case state, while creation activity depends on
dates inside the selected period. The chart was already reading case records,
not transient audit events.

New imports preserve the archived creation value exactly, including its UTC offset.
A missing creation date stays empty; it is never replaced by import time. Invalid
legacy values remain visible as unavailable date coverage. Existing-case updates
continue preserving local creation dates, ownership and identity. Import operations
remain in audit/sync-import records, separate from lifecycle history.

The Metrics page now defaults to **All time**, through the current reporting
instant, including the current partial week. Recent 4/12/26/52 full-week options
remain available for comparable periods. Weeks begin Monday, end Sunday, include
zero-activity weeks and are ordered by date. UTC is the default reporting timezone;
if DISPLAY_TIMEZONE is configured, UTC-normalized instants are bucketed into that
zone's calendar weeks, including DST boundaries. Legacy naive timestamps mean UTC.
Future or invalid creation dates do not count as historical activity.

All time begins with the earliest valid creation timestamp. For cases with unknown
creation dates, actual recorded historical completions can extend the range so
those completions remain reportable. No creation is inferred from a completion.
A new or empty installation can have just one partial-week point.

Total, current-completed, stage, owner and creator snapshots still count each
existing case once. Historical completions use actual qualifying Packaging &
Delivery exits; a currently completed case without such evidence contributes to
the inventory but has unavailable historical completion timing. Reopenings and
recompletions retain the existing distinct-case-per-period policy. Negative cycle
times are excluded. Monthly completion dashboards already use persisted history;
there is no separate monthly creation chart to repair.

The scorecard adds observed workflow interval coverage: creation to analysis start,
analysis stage, packaging stage, and analysis start to completion. Only consecutive
valid stage exits provide durations; reopenings, missing/invalid timestamps,
nonterminal merged-stage exits and negative intervals do not invent timing. Each
interval shows its sample count and median, or Unavailable. Cycle time remains
the existing creation-to-completion median; the coverage section also reports the
mean using the same valid samples. Historical owner-at-completion is not
recorded and is not inferred from an event author or current owner.

## Portable metadata

No database schema or archive format version changes are required. Existing
workflow timestamps, stages, outcomes, reasons and author strings remain portable,
with history exported explicitly in event order. Imports remap events to the
correct local case ID and replace the incoming case snapshot rather than append
another history copy; synchronization UUIDs prevent repeated imports from creating
extra cases. Existing RAW structure and archive names are unchanged.

An unmatched original creator is no longer replaced with the importing user.
The original name is retained with a null local creator ID. Original creator UUID
and unmatched assignee provenance survive subsequent exports. Current assignments
retain existing account-matching and explicit ownership-review semantics.

The application has no authoritative per-case last-modified, started-at or
completed-at columns. Workflow start/completion dates come from recorded stage
exits. Original synchronization revision timestamps remain in the portable ancestry
graph; they are not used as substitutes for lifecycle dates. Content-event dashboards
keep their existing coverage rules and do not manufacture missing historical events
from case creation dates. Complete installation backups retain the existing database
and metadata using the existing snapshot mechanism.

## Existing production imports

If original dates are still in `cases.created`, deploying this code makes them
visible immediately in All time. No migration or reimport is required. If the old
import code overwrote them, metrics cannot recover the originals from the import
date, case name, workflow duration or filesystem timestamp. Use the original RAW
or all-cases backup with the supported metadata-only recovery command below.
It does not delete/reimport cases, change UUIDs, reset workflow states, reassign
users, replace MIP files or append workflow transitions.

Run using the deployed service account and the same MARE_DATA_DIR as the service.
First take a verified installation backup. The commands below assume the production
layout from PRODUCTION_SUBPATH_DEPLOYMENT.md:

```bash
cd /opt/mws
sudo -u mws env MARE_DATA_DIR=/var/lib/mws/data .venv/bin/flask --app app recover-case-dates /path/readable-by-mws/original-backup.zip
```

This is a dry run. Add `--raw` for a single RAW MIP archive. The command uses the
existing archive validator, validates synchronization ancestry and file hashes,
and matches both stable case UUID and origin UUID. It does not guess matches from
case names. Archives without stable identity are reported unmatched and require
separately reviewed identity reconciliation.

Output contains counts and per-case UUID, original date, current date and status:

- `unchanged`: original and current dates represent the same instant.
- `would-repair`: an eligible date repair, without making changes.
- `review-required`: current date is valid and differs; protected by default.
- `unrecoverable`: source creation date is absent, invalid or in the future.
- `unmatched`: no stable matching local case/origin.
- `repaired`: an eligible date was written with `--apply`.

For missing/invalid destination dates, rerun with `--apply` after reviewing the dry
run. Valid dates are never overwritten automatically. If a valid current date is
known to be the old import timestamp, explicitly review the original archive and
create a JSON file mapping that case UUID to its **exact current stored value**:

```json
{
  "case-uuid-from-dry-run-output": "2026-11-17T10:00:00+00:00"
}
```

Store this reviewed file somewhere readable by mws. Run another dry run, then apply:

```bash
sudo -u mws env MARE_DATA_DIR=/var/lib/mws/data .venv/bin/flask --app app recover-case-dates /path/readable-by-mws/original-backup.zip --expected-current /path/readable-by-mws/reviewed-dates.json
sudo -u mws env MARE_DATA_DIR=/var/lib/mws/data .venv/bin/flask --app app recover-case-dates /path/readable-by-mws/original-backup.zip --expected-current /path/readable-by-mws/reviewed-dates.json --apply
```

Add `--raw` to both commands when appropriate. Each replacement requires the current
value still to equal the reviewed value. Changed values require another review.
The operation is transactional, holds the existing case synchronization lock,
records an audit entry for each change, and is idempotent: a second run reports
unchanged. No server restart or hard refresh is required after recovery; navigate
to Metrics. The CLI requires no public access and works with `/mws` deployments.

The command repairs creation dates only. Already restored workflow history is left
intact. Missing transition histories cannot be reconstructed from current state;
retain the original archive for a separately reviewed recovery if it contains
history no longer in the destination. Without an original archive or other
trustworthy historical source, permanently lost dates remain unavailable.

## Refresh and validation

Metrics uses fresh database queries on every request and sends private, no-store.
Navigation after import sees newly restored data. A Metrics page restored from
browser back/forward cache reloads itself; no hard refresh or restart is needed.
The selector uses url_for and works at both `/` and `/mws`.

Regression coverage includes an actual 24-case completed backup round trip,
multiple months, zero weeks, repeated imports, unknown dates, timestamp offsets,
completion coverage, real workflow intervals, source creator attribution,
reviewed/idempotent recovery, single-week rendering and both URL mounts.

## Implementation files and test results

Modified or added files:

- `import_sync.py`: original creation dates and creator/assignee provenance.
- `backups.py`: explicit history ordering, creation-field type validation and
  original identity preservation on reexport.
- `performance_metrics.py`: all-time calendar weeks, current partial week,
  historical coverage and mean cycle time.
- `workflow_metrics.py`: observed workflow duration samples and coverage.
- `historical_recovery.py`: transactional dry-run/reviewed creation-date recovery.
- `app.py`: all-time default, period validation and recovery CLI registration.
- `templates/metrics.html`: period selector, safe single-week chart and workflow
  timing/coverage presentation.
- `static/performance-metrics.js`: refresh after back/forward-cache restoration.
- `tests/test_historical_metrics.py`: historical import, metrics and recovery tests.
- `tests/test_case_sync.py`: unmatched creators retain original attribution rather
  than being attributed to the importer.
- `tests/browser/performance-metrics.cjs`: all-time default and optional subpath
  browser coverage.
- `README.md` and `docs/HISTORICAL_METRICS.md`: behavior and recovery instructions.

Executed validation:

```bash
.venv/bin/python -m pytest -q tests/test_historical_metrics.py tests/test_performance_metrics.py tests/test_case_sync.py tests/test_backups.py tests/test_cases_dashboard.py tests/test_content_metrics.py tests/test_base_path.py --disable-warnings
.venv/bin/python -m pytest -q --ignore=tests/test_samples.py --disable-warnings
node tests/browser/performance-metrics.cjs
MWS_BASE_PATH=/mws node tests/browser/performance-metrics.cjs
```

- Focused regression suite: **94 passed**.
- Broader suite: **1183 passed, 9 failed, 4 skipped**. The nine failures are the
  same known baseline failures in audit dates, autosave, alias filtering, staged
  import expectations, MITRE autosave and workflow/archive expectations.
- Full collection was checked separately: `tests/test_samples.py:21` still has
  its pre-existing IndentationError. It was left unchanged and excluded from
  the broader run above.
- Metrics browser tests passed at root and `/mws`: populated/empty states,
  all/recent periods, desktop/mobile layouts, keyboard/touch/hover interaction,
  current totals, unavailable timing and local assets.
- Python formatting checks, JavaScript syntax and `git diff --check` passed.

There is no schema migration to run. Production recovery is optional and is
required only for creation dates that were overwritten or otherwise lost.
