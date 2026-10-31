# Content Metrics — Content Overview

Content Metrics is a private, permission-filtered dashboard at `/content-metrics`.
It follows Case Metrics in the private directory and Dashboards sidebar submenu.
`/metrics` remains the Case Metrics URL and its calculations are unchanged. Public
walls and anonymous login-page links remain unchanged.

The page requires `metrics:read`. Its session-authenticated data endpoint is
`GET /content-metrics/data`; external clients use `GET /api/v1/content-metrics`
with the existing bearer authentication, account restrictions and rate limits.
The public OpenAPI contract documents the same aggregator. Every response is
private/no-store; there is no shared chart cache. No content values, filenames,
user identities or file bodies are returned by the aggregation endpoint.

## Definitions

Inventory counts current logical records. A retained addition counts once by its
stable event identity. These are contribution counts, not unique malware/IOC
values, analyst rankings, quality scores or historical inventory snapshots.

| Type | Source and counted unit | Classification / exclusions | Recorded addition date | Scope / read permission |
| --- | --- | --- | --- | --- |
| Malware Families | `malware_families`, one profile UUID | Actor/family associations do not duplicate profiles | Original `created_at`; never `updated_at` | Profiles, `tags:read` |
| Threat Actors | `threat_actors`, one profile UUID | Associations are relationships, not new objects | Original `created_at` | Profiles, `tags:read` |
| Tags | `tags` plus permanent `family_tag_identities`, one tag object | Case assignments do not multiply counts; renames retain identity | Original `created_at`, or unknown for legacy restores without provenance | Global, `tags:read` |
| Snort signatures | Stored Case signature-file records | Explicit Snort persistence classification; legacy `.rules` in the Signatures category must contain recognized active Snort rules. One stored file counts once, regardless of lines or embedded rule definitions. Scripts/supporting files with suggestive filenames are excluded | Transactional first addition; legacy files without dates are unknown | Cases, `cases:read` + `cases:assets` |
| YARA signatures | Stored Case signature-file records | Explicit YARA persistence classification; legacy `.yar`/`.yara` in Signatures requires recognizable rule and condition structure, beyond the suffix. One file is the existing persistence unit, not each line or embedded definition | Transactional first addition; unknown for undated legacy files | Cases, `cases:read` + `cases:assets` |
| PDF reports | Case PDF attachment records and `family_reports` / `actor_reports` | Profile MIME is `application/pdf`; Case PDF records require the PDF header and Reports/Supporting attachment classification; legacy stored PDFs in those RAW directories are recognized conservatively with unknown dates. Generated current-report PDFs, DOC/DOCX, embedded report images, backups and exports are excluded unless an explicit independent PDF upload record exists. Direct attachment tables count once, without joining profile relationships | Profile `uploaded_at`; Case first recorded upload, never filesystem mtime or Case creation | Profile PDFs: `tags:read`; Case PDFs: `cases:read` + `cases:assets` |
| Indicators | Nonblank saved indicator rows across all sections | Each saved entry counts, even if another entry has the same value. STIX/CSV generated outputs are not additional entries | Saved row identity's `created`, or recorded first addition; legacy rows without creation metadata remain unknown | Cases, `cases:read` + `indicators:read` |
| Reference links | Nonempty Case reference rows plus `family_osint` and `actor_osint` records | Descriptive supporting files and generated reference CSV are not new links; an OSINT record is counted once regardless of profile associations | New Case-row addition or profile SQL insert; legacy rows without dates are unknown | Case links: `cases:read` + `references:read`; profile links: `tags:read` |
| Scripts | Case asset records in the explicit Scripts RAW category | Count each stored script asset once, independently of extension; a script named `.yar` remains a script. Copies in exported MIPs/backups are excluded | Recorded asset addition; unregistered legacy/discovered files without a recorded date remain unknown | Cases, `cases:read` + `cases:assets` |
| Malware samples | Registered asset-manager records in Samples | One attached sample archive, not each extracted member or a globally unique hash. Arbitrary supporting attachments and extracted unregistered copies are excluded | Recorded asset addition; legacy records without dates remain unknown | Cases, `cases:read` + `cases:assets` |

Classifications describe stored record types, not syntax validity or malware
verdicts. The metrics service does not execute samples, scripts or signatures.
Symlinks and files outside the Case RAW root are excluded. Source files are
examined only during migration / Case reconciliation, never per chart request.

## Durable history and identity

`content_events` is authoritative addition history, retaining only event identity,
content kind, opaque scope identity, record locator/hash, recorded date, observation
time and current presence. No indicator values, reference URLs or document bodies
are copied into it. Shared-object SQL triggers record inserts and deletions in the
same transaction as the existing UI, REST, SDK and import services. Edits do not
create additions. Case collectors participate in the existing CaseSync transaction
for all dirty Cases; signature classification is recorded inside its existing
savepoint. Bulk edits and imports use the same services.

Case indicator identities use the existing saved row UUIDs. File locators identify
stored attachment records: edits retain identity; deleting then uploading a new
record produces a new addition. A partial unique index prevents two current events
for the same Case record. Deleted history remains retained when current presence
is cleared. Restores reactivate matching identities rather than count them again.

The existing reference-table API replaces rows without supplying stable per-row
IDs. `content_reference_slots` adds portable record identities: exact-row matches
are paired first (including duplicate occurrences/reordering), remaining existing
rows are paired as edits, and additional unmatched rows receive new identities.
Consequently a simultaneous delete-and-replace with no row identity is treated as
an edit; historical intent cannot be recovered from a replacement table. Ordinary
append, edit, reorder, delete and subsequent append preserve the expected counts.
Only hashes and identity/position metadata are stored, not reference text.

`content_asset_types` preserves explicit signature/PDF classifications. Current
presence can be reconciled against managed Case state, while historical event
identities and dates must be retained. These tables are not disposable chart caches.
Out-of-band filesystem writes are not an application submission workflow; when
legacy/unregistered content is discovered, no upload time is invented.

## Dates and coverage

The configured `MARE_DISPLAY_TIMEZONE` is used for dates, aggregation, labels and
tooltips; UTC is the fallback and is displayed. Legacy naive recorded dates are
interpreted as UTC. Defaults are the first day five months before the current
month through today: six calendar months including the current month. Date bounds
are inclusive, limited to three years, with no future end date. Weeks begin Monday;
month/year and DST boundaries are bucketed on the server in the reporting zone.
Date-clipped buckets and the current week/month are marked partial.

Inventory is independent of the date controls. Added-per-period counts dated first
additions in each bucket. Cumulative additions use the full known baseline before
the selected range, then accumulate additions; they are explicitly not historical
inventory. The right summary and Case bars always show additions across the whole
range, even in cumulative mode. Sparklines likewise use period additions.

Migration is additive (`content-metrics-v1`). Installations awaiting the existing
prototype-tag migration defer metrics setup (503) until that migration and restart;
legacy tags are not silently flattened. Existing reliable creation/upload
fields are preserved. Undated legacy content has NULL/unknown addition dates and
remains in inventory but not dated buckets. No Case creation or modification time
is substituted. Historical deletions before ledger installation cannot be rebuilt;
coverage starts at ledger initialization. Earlier recorded contributions are a
lower bound. Before coverage, empty dated buckets are unavailable, not fabricated
zeroes; fully covered empty buckets are zero. The page reports the coverage start
and current accessible unknown-date count.

Deleted-content history is restricted to Administrators, with the relevant source
permissions still applied. Other viewers see additions for currently accessible
records and an explicit notice that deletions are excluded. Restricted content
returns unavailable/null counters, never global totals. Queries are grouped and
indexed, filtered by effective source permissions. Filters/request results are not
shared between accounts. Browser cancellation and request generations prevent
older filter responses from replacing newer results.

## Backups, imports and recovery

Complete backups include the authoritative ledger, reference identities and asset
classifications in the existing SQLite snapshot, without a new selectable backup
category. Recovery verifies original archive hashes/counts before additive metrics
migration and publishing the recovered directory. The backup schema contract is
captured after this feature's schema is initialized.

RAW Case metadata carries a versioned optional `content_metrics` sidecar, including
that Case's event identities/dates, reference identities and classifications.
Profile-library records carry their own optional metric history. It does not
change the existing Case synchronization fingerprint or research-content conflict
fingerprints. Older archives without this field remain valid. Known profile/row
creation and upload fields are retained; missing dates stay unknown.

Repeated restoration of the same logical object/event does not create another
addition. Restoring deleted content reactivates its original event. Explicit Case
copies with a new Case UUID receive deterministic per-copy event identities and
an import-time addition date for current copied records. Deleted source history
is not replayed as new submissions in an independent copy. Shared profile UUIDs
and permanent tag identities retain their original dates on transfer. Where old
archives cannot distinguish these identities/dates, coverage remains partial.

## Verification

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_content_metrics.py tests/test_dashboard_directory.py tests/test_performance_metrics.py tests/test_family_reports.py tests/test_backups.py tests/test_sidebar_hierarchy.py tests/test_case_sync.py tests/test_sync_review.py tests/test_backup_workspace.py tests/test_threat_actors.py tests/test_api_documentation.py tests/test_api.py tests/test_sdk_api_extensions.py
MARE_BROWSER_EXECUTABLE='/path/to/chrome' node tests/browser/content-metrics.cjs
MARE_BROWSER_EXECUTABLE='/path/to/chrome' node tests/browser/performance-metrics.cjs
```

Browser fixtures use disposable data and real uploads. Screenshots are written to
`/tmp/mws-content-overview-{width}.png` and `/tmp/mws-content-empty.png`.
