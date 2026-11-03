# Package Artifact Register

Package prepares content; Review & Export remains the delivery workspace. The
register uses the existing seven package directories and asset services. It has
section filters (including empty and Not applicable), filename search, type
filters, 50-row pages, safe existing file previews, focused editors, downloads,
and page-scoped selection. Generated content opens Indicators, References, or
Report. Internal report source Markdown is not added as a Package editor.

Upload files opens a multi-file queue. Each entry requires a destination, shows
size/progress/status, and can be removed or renamed explicitly. A selected section
prefills the destination. Successful entries are not resent on retry. Samples
continue using the existing password-protected ZIP handling. Duplicate names
return a conflict and never overwrite. Scripts and samples are never executed.
Current report replacement remains in Report. There is no arbitrary move action.
Bulk removal reuses each existing asset deletion operation and reports failures;
bulk downloads retain directory-relative names and existing sample permissions
(maximum 200 files / 100 MiB). Closed Cases permit reading and authorized downloads.

## Presence and applicability

`package_status.py` is shared by Package, review checks, board summaries, REST,
export readiness manifests, and CaseSync. Counts describe content, not analytical
quality or sign-off. Independent report requirements, STIX checks, deferred work,
job locks, and workflow gates remain in effect. In particular, marking Reports
Not applicable does not bypass the existing completed-report delivery requirement.

- **Populated**: qualifying saved content exists; no manual population action.
- **Empty**: no qualifying content and no applicability decision.
- **Not applicable**: explicit decision, available only while the section is empty.

Only Not applicable decisions remain in the existing `readiness` table. The
existing reason is retained; the checkbox uses “No content expected.” Explicit
changes and automatic clearing use existing audit and Case activity records,
including actor/time/provenance preserved by existing backup metadata. Repeated
refreshes do not create activity. CaseSync normalizes after successful mutations,
under its existing Case write lock/transaction. Failed requests, canceled queues,
unsaved drafts, and empty editor saves do not clear applicability. A successful
qualifying save clears it; removing the last qualifying item leaves Empty.

Qualifying content:

| Section | Definition |
|---|---|
| Reports | Meaningful saved narrative sections and nonempty saved report artifacts; known default Markdown scaffolds and report-editor image/source duplicates are excluded. Working Word sources remain omitted from Standard exports under existing rules. |
| IOCs | Saved rows with an indicator value, plus independent saved IOC artifacts. CSV/STIX carrier files are not extra items and stale carriers do not imply saved rows. |
| Signatures | Nonempty saved signature artifacts under existing storage rules. Presence does not certify engine validation or rule quality. |
| Scripts | Meaningful saved script/text artifacts. Nothing runs here. |
| MITRE tables | Meaningful saved mapping tables; headings, separators, and known blank templates do not count. The two maintained tables open Report. |
| Supporting evidence | Saved evidence plus nonblank saved References links; generated references.csv is not an extra item. |
| Samples | Saved nonempty ZIP archives. Legacy raw sample files remain visible for review but do not count as deliverable archives. |

Zero-byte/blank text and empty JSON templates do not count. Such saved artifacts
remain visible for maintenance. Temporary uploads, backups and symlink paths do
not count. Package logical counts can differ from physical export-file counts:
for example, many saved indicators appear as one register group and generated
carrier files. Existing CSV download paths and Standard exports render those carriers from current saved records rather than stale disk copies. Data Explorer reads indicator/reference rows from their owning
records; Content Metrics excludes blank artifacts rather than counting them as
new content.

## Migration, API and backups

The idempotent `automatic-package-status-v1` migration preserves files, keeps old
Not applicable decisions only for empty sections, and removes old Pending and
Populated records. Content always wins over a contradictory Not applicable flag.
Emptiness never implies Not applicable. No package directory or file naming
schema changes. The old four-column table layout is retained for archive readers.

`GET /api/v1/cases/{id}/readiness` returns the existing fields with canonical
`status` values **Empty**, **Populated**, **Not applicable**. `legacy_status` maps
Empty to Pending for read consumers needing the old unresolved label.
`PUT` accepts only Empty (clear applicability) or Not applicable. Pending and
Populated writes now return HTTP 400 with an explicit automatic-presence message;
marking a populated section Not applicable returns 409. Permissions and canonical
closed-Case restrictions are enforced server-side. The generated sync/async SDK
uses the updated contract and can still parse Pending responses from older servers.

Complete backups retain decisions, Case activity and existing files. Older complete
archives receive the additive migration before publication. Case backups and RAW
MIPs retain the existing readiness records and activity provenance; old manual
statuses remain accepted by archive validation, then normalize against restored
content. States are recalculated rather than trusting incoming population flags.
Standard/RAW inclusion rules and directory mappings are unchanged. No placeholder
files are added for empty or Not applicable sections.

Focused verification:

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_package_register.py tests/test_reporting.py tests/test_backups.py tests/test_backup_workspace.py tests/test_data_explorer.py tests/test_content_metrics.py sdk/tests
node tests/browser/package-register.cjs
```
