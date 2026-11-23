# Case Impact

Case Impact records a confirmed enterprise security outcome attributable to a
malware-analysis case. Enable it for an actual detection improvement, confirmed
malicious activity or infrastructure discovery, or another actionable security
improvement. Useful analysis alone does not require an impact flag. Impact is
independent of workflow stage, severity, tags and completion.

## Analyst workflow

In **Workbench**, the compact **Case Impact** panel sits beside Case details.
It defaults to collapsed for an unrecorded case and expanded for a confirmed one.
The browser retains the analyst's explicit expansion preference per case and user
for the session. Collapsing the panel keeps its input values.

Select **Enterprise Impact Confirmed**, choose one outcome, and enter a plain-text
summary explaining what was detected or discovered, the case's contribution, and
why the result mattered. Leading/trailing whitespace is trimmed; the maximum is
4,000 characters. Type and a nonempty summary are required for confirmed impact.

| Display label | Stored value |
|---|---|
| New or Improved Detection | `detection` |
| Confirmed Discovery | `discovery` |
| Detection and Discovery | `both` |

Valid edits save after a short pause, use the existing shared autosave mechanism,
and have a Save impact button and visible save/error status. Unsaved edits trigger
the existing browser leave-page safeguard. Workbench refreshes apply new saved
impact values only when the impact form is pristine; unsaved text is retained.
No new tab or navigation item is added.

Users need the existing `cases:update` permission. Impact can be edited in every
workflow stage, including Not Started and Completed, and when ownership is absent
or disabled. This exception is specific to impact metadata; content/workflow locks
and all existing role permissions remain unchanged. CSRF/session protections apply
to the web form; bearer-token protections apply to the API.

Disabling impact removes it from active badges and metrics while retaining the
last saved type, summary and first-confirmation timestamp. Re-enabling restores
those details. The first known confirmation timestamp never resets on unrelated
edits or disable/re-enable. Imported confirmed impacts with no timestamp remain
unknown when details are edited. If such an impact is explicitly disabled and
subsequently confirmed again, that genuine confirmation records the current time.

## MIP Board

Confirmed cases have a compact amber **★ Impact** badge near the stage indicator
on cards and in a dedicated Impact column immediately after Case title in table
view. Unconfirmed table rows show a neutral **No known impact** badge. Workflow
colors remain unchanged: Completed stays green. Hover or keyboard focus reveals
context; click, Enter or touch opens it. Cards retain their native disclosures and
360-character previews. Table previews wrap the full summary in a bounded popup;
full text is also available in Workbench and Metrics.

The existing filter drawer adds All Cases (default), Impactful Cases and
Non-Impactful Cases. Impact filtering composes with existing search, tags and stage
filters, persists when changing views or sorting, and resets with Clear Filters.

## Metrics and historical dates

The existing Case Metrics page adds Impactful MIPs, Impact Rate, Detection Outcomes
and Discovery Outcomes, a native SVG weekly trend, a small outcome breakdown, and
an Impactful Cases table. Existing metrics and reporting periods remain intact.
Both outcomes count toward detection and discovery separately, but each case counts
only once toward Impactful MIPs and the mutually exclusive breakdown.

Reporting dates use this ordered rule:

1. Latest valid recorded completion, including a completed cycle before reopening.
2. First recorded impact confirmation, when completion is unavailable.
3. Original case creation date, explicitly labelled **Creation fallback**.
4. **Unavailable** when none of those dates is usable.

These rules never substitute restoration/import time or the current date for
unknown historical evidence. Future and invalid dates are not usable. Source UTC
offsets are preserved; reporting normalizes instants and groups into the existing
Monday-based calendar weeks in DISPLAY_TIMEZONE (UTC by default). All time extends
to earlier available impact evidence when necessary and includes the current
partial week. Recent selections retain the existing full-week convention. Zero
weeks are present in the trend.

For All time, the rate denominator is the entire existing case inventory, including
undated cases; confirmed undated cases count in the total but are identified as
missing from the trend. For recent periods, both numerator and denominator use
the same reporting-date rule. Non-impactful cases without a completion use creation
for scope membership. Undated cases are excluded from recent-period counts. The
page states the numerator and denominator explicitly.

The table shows case links, current analyst, outcome, an expandable full summary,
current stage and reporting date/source. Search and sort controls affect only the
table, preserving the selected period and dashboard totals. Date sorts newest
first; number/name/analyst/type/stage sorts are ascending. Existing shared table,
form, chart and disclosure styling is reused.

Metrics represent **currently confirmed** impact, not an immutable historical
ledger of every past flag change. Disabling a flag removes it from all active
impact reporting; editing its type updates counters. Assigned analyst is current
ownership, not inferred historical ownership at the time of the outcome.

## API and Python SDK

The existing create, list, retrieve and PATCH case operations expose:

- `impact_confirmed`: boolean; defaults false.
- `impact_type`: `detection`, `discovery`, `both`, or null while unrecorded.
- `impact_summary`: plain text, at most 4,000 characters.
- `impact_confirmed_at`: server-managed first confirmation timestamp or null;
  retrieval only, rejected if supplied to a create/PATCH request.

Omitted impact fields remain unchanged on PATCH. Old clients may continue sending
their existing metadata payloads. A partial impact-only update does not require
an active owner or workflow transition. OpenAPI and generated SDK models/resources
are updated without adding a new API endpoint.

```python
from mws_sdk.models import CasesUpdateRequest

case = client.cases.update(case_id, data=CasesUpdateRequest(
    impact_confirmed=True,
    impact_type="both",
    impact_summary="Confirmed malicious infrastructure and deployed a new detection.",
)).case
print(case.impact_confirmed_at)
client.cases.update(case_id, data={"impact_confirmed": False})
```

The Workbench uses the existing case POST handler with `operation=impact`; it does
not submit or mutate unrelated case-detail fields.

## SQLite, synchronization and backups

Startup adds the four columns to `cases` if absent: INTEGER NOT NULL DEFAULT 0,
TEXT, TEXT NOT NULL DEFAULT '', and TEXT, respectively. Existing rows default to
unrecorded impact. Migration is repeatable and leaves case IDs, assignments,
workflow states, creation dates, files and directory structure unchanged. A
separate idempotent CaseSync trigger marks impact edits dirty for revision tracking.
No new database table or runtime dependency is introduced.

Complete installation backups retain the SQLite fields. Individual RAW MIPs and
all-case portable backups include the state, type, summary and original timestamp.
Validation restores those values without inventing a missing confirmation date.
Disabled retained details also survive export/import.

Older archives without the fields remain importable: a newly imported case defaults
to disabled. Applying an older client/archive snapshot over an existing case does
not erase existing impact information when the source omitted it. Explicit modern
impact values are restored as part of the reviewed incoming snapshot. Default
unrecorded fields are omitted from semantic synchronization fingerprints so
pre-feature revision ancestry remains valid; actual impact edits create revisions.
Repeated imports use existing UUID/revision deduplication, not duplicate case rows.
Archive schema versions and naming conventions are unchanged.

Standard MIP files and report sections remain unchanged. This feature adds metadata
to structured application backups, not new Standard MIP files or report sections.
Case impact is not inferred for older cases; analysts can record it after deployment.
If original dates were lost by earlier imports, use the separately documented
historical-date recovery workflow rather than guessing an impact date.

## Production deployment

1. Create and verify an encrypted complete application backup using the existing
   Backup & Restore workflow.
2. Stop only the MWS service (`sudo systemctl stop mws` for the documented deployment).
3. Deploy this release, including its Python modules, templates, static files and
   generated SDK artifacts. There are no additional dependencies or Nginx changes.
4. Start MWS (`sudo systemctl start mws`). Normal application startup applies the
   additive SQLite migration and installs the synchronization trigger.
5. Verify the service log, open a case, record a test outcome, inspect the Board
   filter/badge and Case Metrics, then disable the test flag if appropriate.

No manual SQL, database reset or case reimport is required. Existing `/mws`
configuration is retained; routes and assets use existing prefix-aware URL
construction. Metrics queries are uncached and private/no-store. Normal navigation
after saves or imports shows current values, and back/forward-cache restoration
refreshes Metrics through the existing handler.

When rolling back, restore the previous release and its verified pre-upgrade
backup together. Older application code will not understand or preserve impact
metadata in new portable exports, even though SQLite tolerates additional columns.

## Implementation and validation

The dedicated Case Impact regression suite covers migration repeatability,
validation, all four workflow stages, inactive/unassigned owners, permissions,
CSRF, timestamp policy, Board filters and previews, historical rates/outcomes,
unknown dates, portable round trips, repeated imports, old archives, synchronization
revisions, installation recovery, RAW versus Standard exports, SDK requests and
safe plain-text rendering. It adds 29 passing parametrized test cases.

Executed checks:

- Focused impact/API/SDK export regressions: **40 passed**. Additional focused
  application regressions passed as well.
- Final broader suite: **1212 passed, 9 failed, 4 skipped** (98.94 seconds), using
  `python -m pytest -q --ignore=tests/test_samples.py --disable-warnings`.
- The nine failures are the same known baseline failures in audit dates,
  autosave expectations, alias filtering, staged imports, MITRE autosave and
  workflow/archive expectations. No new impact or Board-sort failure remains.
- `tests/test_samples.py:21` still has its pre-existing IndentationError, confirmed
  by a separate collection check; that unrelated file remains unchanged.
- `npm run test:case-impact` and `MWS_BASE_PATH=/mws npm run test:case-impact`
  pass with an isolated fixture database/server and real Chrome. They cover
  autosave, retention, panel state, completed cases, hover/focus/touch previews,
  popup viewport bounds, Board filters, historical Metrics and prefix-safe requests.
- Generated OpenAPI/SDK artifacts were rebuilt (163 existing operations, 317 typed
  models). SDK compatibility/integration checks passed.
- Python formatting checks, JavaScript syntax and `git diff --check` pass.

The Workbench preview is a small disclosure with a checkbox, outcome select and
plain-text summary. The Board places the amber badge beside the unchanged green
Completed label. Metrics adds a matching amber trend and outcome bars above its
searchable, sortable cases table. Browser captures of all three views were produced
during validation.

Modified and added files:

- `README.md`
- `api.py`
- `api_documentation.py`
- `app.py`
- `backups.py`
- `case_queries.py`
- `case_sync.py`
- `import_sync.py`
- `package.json`
- `performance_metrics.py`
- `sdk/README.md`
- `sdk/docs/API_REFERENCE.md`
- `sdk/mws_sdk/models.py`
- `sdk/mws_sdk/openapi.json`
- `sdk/mws_sdk/operations.json`
- `sdk/mws_sdk/resources/async_resources.py`
- `sdk/mws_sdk/resources/sync_resources.py`
- `static/package-refresh.js`
- `static/tags.js`
- `templates/base.html`
- `templates/board_tags.html`
- `templates/case.html`
- `templates/dashboard.html`
- `templates/metrics.html`
- `case_impact.py`
- `docs/CASE_IMPACT.md`
- `static/case-impact.css`
- `static/case-impact.js`
- `templates/case_impact.html`
- `templates/impact_badge.html`
- `templates/impact_metrics.html`
- `tests/browser/case-impact.cjs`
- `tests/test_case_impact.py`

## Impact Summary editing and autosave stability

Impact autosave retains the existing 700 ms debounce and shared autosave service.
The live textarea is a raw local draft. A successful response acknowledges the
exact draft submitted; the backend's normalized representation is tracked as a
separate server baseline. Neither a successful save nor timestamp display writes
back into the textarea, replaces its node, or refreshes the Workbench.

The previous implementation invalidated the Workbench after each impact save.
Revalidation read the trimmed server summary and assigned it to textarea.value,
which moved the cursor and removed boundary whitespace. FormData's CRLF line
endings versus textarea/HTML LF line endings could also make equivalent server
values appear different. The timestamp shared the transient save-status element.
The fix removes the per-save invalidation, compares normalized server values
without modifying the draft, and gives First confirmed its own time element.

Normal Workbench revalidation still accepts genuine external changes when the
impact form is pristine and unfocused. It never overwrites an active or dirty
impact editor. Revalidations carry an impact generation captured before their
request, so a response predating a local edit or completed save is ignored for
impact fields. Delayed save responses acknowledge only their submitted draft;
newer input remains pending and saves after its own debounce deadline. Failures
retain the draft and expose retry feedback. Navigation warns about unsaved drafts
and in-flight saves, including when input was reverted while a save was pending.

Existing backend requirements, trimming on persistence, permissions and timestamp
policy are unchanged. Leading/trailing whitespace remains visible while editing;
a fresh page load reflects the existing stored, trimmed summary. Interior spaces,
newlines and indentation are retained. First confirmed updates only its own display
from the saved server timestamp; summary/type edits do not establish a new date.

Additional regression checks for this correction:

```bash
.venv/bin/python -m pytest -q tests/test_case_impact.py tests/test_shared_tabs.py tests/test_case_tab_sync.py tests/test_historical_metrics.py --disable-warnings
node tests/browser/case-impact.cjs
MWS_BASE_PATH=/mws node tests/browser/case-impact.cjs
node tests/browser/case-tab-sync.cjs
```

The focused Python suite passed **47 tests**. Browser checks passed at both mounts
and for existing cross-tab synchronization. The new
`tests/browser/impact-editing.cjs` helper verifies raw whitespace, unchanged textarea
identity/focus/selection, Enter/Backspace/Delete/paste, non-repeating saves,
focused and unfocused revalidation, stale refreshes, delayed save responses, failed
save/retry and navigation protection, required-summary validation, and stable
confirmation time during summary/type/unrelated case edits. JavaScript syntax and
`git diff --check` passed. No backend or database migration was needed.

## Dedicated Board table Impact column

Table view places **Impact** immediately after Case title. It contains exactly one
compact indicator per row: amber **★ Impact**, or neutral gray **No known impact**.
Missing/null legacy values render as unconfirmed without modifying case data.
The title cell now contains only its original link, with a single-line ellipsis
and the full title retained as its accessible link text and native title tooltip.
Case numbers, other columns and workflow colors are unchanged.

Previously the title's block link was followed by the impact disclosure, which
added a second line, vertical margins and an inline preview to that cell. Dedicated
cells now use matching badge padding/line height and the existing cell alignment.
No fixed row heights are imposed. Long exceptional values in other existing fields
retain their existing wrapping behavior; ordinary rows have matching heights.

The Impact header uses the same POST sort control, direction indicator and saved
account preference as the other columns. Ascending puts unconfirmed first;
descending puts confirmed first. Sorting reads the boolean field (missing/null
means false), not display text. Equal impact values retain their existing newest-
first order in either direction. Other sort keys keep their existing behavior.
Search, tags, stage and impact filters survive sorting and view changes. The Board
currently has no pagination or row-selection implementation to change.

Table badges adapt the existing impact badge/preview styling to a native manual
popover in the browser's top layer, with a fixed-position body fallback for older
browsers. This avoids clipping inside the horizontal table scroller and keeps
preview contents out of row layout. Confirmed previews show Enterprise Impact
Confirmed, the stored outcome and the complete summary. Neutral previews explain
that no enterprise outcome has been recorded. Text wraps and long content scrolls
within a viewport-bounded panel. Hover/focus reveals it; click/touch pins or dismisses
it, outside click and Escape dismiss it. Screen readers receive the description
through aria-describedby, and PageUp/PageDown scroll the focused badge's preview.
Only one preview is open at a time; existing nodes are reused, not cloned.

On narrower desktop/tablet widths, the table can scroll horizontally within its
container. The existing stacked mobile layout remains, with Impact still visible.
Card markup and its native impact disclosures remain unchanged. This refinement
does not change Workbench autosave, timestamps, impact validation, metrics,
backups, APIs, SDK models, or the database schema.

Files changed for this refinement:

- `app.py`: accept the Impact Board sort preference and preserve tie ordering.
- `templates/dashboard.html`: insert the column and its existing sort control;
  remove the title-cell badge and update the empty-row span.
- `templates/board_impact_status.html`: the two status indicators and descriptions.
- `static/case-impact.css`: table-only sizing, ellipsis, neutral badge and popup styles.
- `static/board-impact.js`: table preview activation, positioning and dismissal.
- `tests/test_board_sort.py`: seven-column, stable impact sort, filter and legacy tests.
- `tests/browser/board-impact-column.cjs`: focused browser coverage.
- `tests/browser/board-table.cjs`: seven-column/truncated-title expectations and current
  sidebar selectors in the existing broader regression.
- `package.json`: `test:board-impact` command.
- `docs/CASE_IMPACT.md`: these behavior and verification notes.

Validation executed:

```bash
.venv/bin/python -m pytest -q tests/test_board_sort.py tests/test_board_filters.py tests/test_case_impact.py tests/test_performance_metrics.py tests/test_navigation.py --disable-warnings
npm run test:board-impact
MWS_BASE_PATH=/mws npm run test:board-impact
```

The focused Python suite passed **97 tests**. Dedicated real-Chrome browser checks
passed at root and `/mws`, including measured equal row heights, ellipsis/full title,
both sort directions and ties, filter preservation, unclipped hover/focus/touch
previews, navigation, mobile visibility and byte-equivalent card markup after
normalizing case ordering. JavaScript syntax and `git diff --check` passed.

The broader `tests/browser/board-table.cjs` regression was also executed. It reaches
a pre-existing summary-metric-card overflow at 1024px when the filter drawer opens:
the page measures 1037px wide even with the entire table hidden. This is outside
the new column and remains unchanged to preserve the existing controls/card view.
The broader script therefore does not pass; no claim is made that it completed its
later assertions. Its old sidebar/header selectors were updated to current markup.
