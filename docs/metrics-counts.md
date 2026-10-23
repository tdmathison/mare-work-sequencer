# Metrics inventory and dated activity

The Board and Metrics previously showed different quantities under similarly broad
labels. The Board lists existing cases; the executive scorecard's former “MIPs
created” and “MIPs completed” cards counted activity in the last 12 **complete**
Monday–Sunday weeks by default. The current partial week, creation dates outside
the period, invalid/missing timestamps and undated completions could legitimately
make activity smaller than the current inventory. Different creation/completion
cohorts also allow more period completions than period creations.

The reported 16 / 14 / 15 production dataset is unavailable in development. An
isolated regression reproduces precisely that shape without changing production
or development records: 16 existing Completed cases, 14 valid period creations,
15 cases with qualifying period completion history, and one undated completion.
It verifies the corrected inventory cards show **16 Total MIPs / 16 Completed
MIPs**, while dated activity remains honestly 14 / 15.

## Definitions and shared scope

* **Total MIPs:** distinct eligible existing cases. Creation dates are irrelevant.
* **Completed MIPs:** those cases currently in state 3, including imported/restored
  cases with no usable completion timestamp.
* **In progress:** current states 1 and 2. Not started and Completed pipeline counts
  likewise use each existing case's current state.
* **Created during period:** valid authoritative `cases.created` in the displayed
  activity window. It is not the total number of records remaining in the database.
* **Completed during period:** distinct existing cases with a qualifying terminal
  Packaging & Delivery exit in that window. It includes cases subsequently reopened.
  Recompletion counts at most once per case per reporting window, using the first
  qualifying event in that window; a case can count again in a later window.

`case_queries.py` is the shared inventory relation/eligibility source for the Board,
scorecard and API metrics. The current Board has no owner visibility filter and no
soft-delete flag: all existing rows are eligible for authenticated web viewers,
including cases assigned to disabled users and unassigned cases. Workflow ownership
locks govern editing, not visibility. Deleted cases are physically removed. User
joins are by unique IDs; distinct case projections protect totals against row
multiplication. Metrics authorization is unchanged, including the API's separate
`metrics:read` gate. No new role access or hidden owner filter was introduced.

The Board retains its intentional search/tag/stage controls. Metrics' inventory
states visibly that it is unfiltered and that Board filters are independent. The
Board's All MIPs tile remains its all-inventory/reset count; its other state tiles
retain their existing search/tag scope. Metrics' reporting-period control changes
activity, comparisons and cycle time, not inventory or current ownership snapshots.
All totals use the full inventory, independent of paginated case API responses or
client presentation. Unrecognized states are reported separately without repairing
records or inventing a valid lifecycle state.

## Dates, related metrics and freshness

Activity windows use `MARE_DISPLAY_TIMEZONE` (UTC by default), including local
Monday boundaries across daylight-saving changes. Legacy naive timestamps are
interpreted as UTC, not server-local time. SVG/table labels display the actual zone.
Cycle time remains elapsed UTC duration between authoritative creation and the
selected completion; negative or unavailable durations are excluded with coverage
counts. Weekly creation and completion totals use exactly the selected period
cohorts. Missing/future creation dates affect dated activity and age only.

History records the stage left, not the state entered. Only qualifying final stage-2
exits, followed by reopening or terminal for a currently Completed case, establish
completion events. Adjacent legacy stage-2 records do not create duplicate output.
Current completion-date coverage now checks the **current terminal completion**:
a valid earlier completion does not conceal an invalid final date after reopening.
No timestamps are fabricated and no case/history migration or repair is performed.

The public Cases wall's calendar-month completion metric remains a separate,
explicitly dated count of currently Completed cases with their current terminal
completion inside the configured month. It is not an all-time inventory count or
historical count of subsequently reopened cases. Its existing boundary/reopening
regressions remain applicable.

Analyst assigned/current-completed totals include Unassigned and deleted-account
buckets and reconcile with inventory. Period owner output remains current-owner
attribution because owner-at-completion history is not recorded. The API owner
completion chart now includes unassigned/deleted-owner buckets instead of silently
omitting them; its `users` list still contains actual user accounts only.

Every scorecard reads inventory, users and history in one SQLite read snapshot. API
metrics likewise snapshot their inputs. No persisted metric cache or search-index
cache is consulted; each request recomputes after create/delete/state changes or
import/restore. Metrics HTML and API responses explicitly use `private, no-store`
so an intermediary/browser cannot retain stale scorecards. No cache invalidation
queue or data rewrite is needed.

## Verification

```
.venv/bin/python -m pytest -q tests/test_performance_metrics.py tests/test_cases_dashboard.py tests/test_backup_workspace.py tests/test_api.py::test_backup_import_export_and_metrics
node tests/browser/performance-metrics.cjs
```

Regression coverage includes the 16/14/15 scenario; Board/metric eligible-ID equality;
shared case tags and repeated lifecycle history; actual RAW import with missing
dates; an actual complete-restore subprocess; reopened cases; current-completion
coverage; unassigned/disabled owners; deleted cases; paginated API results; fresh
requests after state/deletion changes; UTC/local-week/DST boundaries; and both
existing authenticated web roles. The Chrome browser test compares an isolated
16-Completed-case Board with 16/16 inventory cards, keeps period values separate,
and exercises all reporting windows, SVG interactions and desktop/mobile layouts.

For the production instance, compare its unfiltered Board with read-only queries:

```sql
SELECT id, stage, created FROM cases ORDER BY id;
SELECT count(DISTINCT id) AS total_mips,
       count(DISTINCT CASE WHEN stage=3 THEN id END) AS completed_mips
FROM cases;
```

The production database must be checked there; development cannot identify which
specific production timestamps caused the old 14/15 activity figures. Missing dates
remain an explicit data limitation, not a reason to exclude current cases or to
rewrite historical records.
