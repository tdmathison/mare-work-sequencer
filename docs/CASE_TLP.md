# Case Traffic Light Protocol (TLP)

MWS uses [FIRST TLP 2.0](https://www.first.org/tlp/) to describe sharing boundaries,
not threat severity or authenticated Case access. Stored/API values are the exact
labels below. Shared metadata lives in `case_tlp.py`; selectors, badges, and compact
markers use `templates/components/tlp.html`, `static/tlp.css`, and `static/tlp.js`.

| Designation | Foreground on black | Sharing boundary |
| --- | --- | --- |
| TLP:RED | #FF2B2B | Individual recipients only; no further sharing. |
| TLP:AMBER+STRICT | #FFC000 | Within the recipient's organization, as needed. |
| TLP:AMBER | #FFC000 | Within the organization and with its clients, as needed. |
| TLP:GREEN | #33FF00 | Within the relevant community; no public publication. |
| TLP:CLEAR | #FFFFFF | Public sharing allowed, subject to copyright and applicable rules. |

Text badges and generated Word header/footer markings use the official foreground
on black. Compact swatches add a border, and AMBER+STRICT adds `+`. Each marker has
the exact accessible label, native title, and keyboard-focus tooltip. Native select
options retain readable labels; an adjacent swatch shows the selected color without
relying on native option-background rendering.

## Storage, defaults, and editing

Startup runs the idempotent `case_tlp.initialize` forward migration. It adds
`cases.tlp TEXT NOT NULL DEFAULT 'TLP:AMBER'` when absent, fills legacy null/empty
values with AMBER, preserves valid values, and installs insert/update validation
triggers. Unsupported existing nonempty designations require correction rather
than silent conversion. No tag, stage, malware family, or impact inference occurs.

**Migrated AMBER is a default assignment, not a historical analyst assessment.**

Administrators can change **Default Case TLP** in Settings → General. It is stored
in `site_settings.default_case_tlp`, falls back to AMBER when absent, and applies
only to newly created Cases. The existing personal Autosave preference is separate.
Ordinary users cannot change this system setting.

Create Case renders the current default synchronously beside Case name, with a
stacked layout on small screens. Name prefix/caret logic is unchanged. Failed
validation retains entered values. Workbench exposes the same selector in Case
details using Case update permissions; completed Cases cannot change TLP. Actual
changes appear in audit and Case activity. Metadata revalidation updates the swatch
and saved badge while retaining local draft selections. The Board refreshes mounted
markers on focus and restored history without replacing the page.

`POST /api/v1/cases` and `PATCH /api/v1/cases/{id}` accept `tlp`; every Case response
includes it. Omission on creation uses the system default, and omission on update
preserves the saved value. Explicit null, blank, wrong-case, and unsupported values
are rejected. The regenerated OpenAPI contract and synchronous/asynchronous SDK
models carry the five-label enum. Older clients can continue omitting it on create.

## Public dashboard implications

**Legacy Cases become AMBER and disappear from anonymous Case listings/counts.**
Only CLEAR Cases can pass the public Case dashboard's existing lifecycle rules.
CLEAR does not change a stage or independently publish content. Public family and
actor dashboards likewise exclude restricted Cases from linked-Case counts, without
changing their independent public profile content or layout. Authenticated inventory
visibility is unchanged.

Filtering happens in SQL before serialization, pagination, summaries, and counts.
These public endpoints already use `Cache-Control: no-store` and no server snapshot
cache; the next data request reflects a change immediately. Existing wall refresh
cadence remains in place. A previously displayed or downloaded public disclosure
cannot be recalled by changing its designation.

## Archives and generated reports

Complete recovery preserves the database column and system default. Its preview
warns about TLP differences on matching permanent Case identities before the
existing replace-instance acknowledgement. Case backups
and RAW MIPs include the explicit value in Case metadata and package manifests.
Standard manifests and package README text carry it too. Generated Word reports
mark default, first-page, and even-page headers/footers in right-aligned 12-point text; generated PDFs inherit the
Word markings through the existing converter. Existing template header content is
retained. A designation change detected during generation prevents publishing that
outdated report.

Existing uploaded/generated report files are preserved, including during backup
round trips; regenerate older reports to apply a changed Case designation to their
textual markings. Package metadata always states the current saved designation.

Old archives with no TLP field assume AMBER for new Cases, explicitly stated in
both import review paths. Missing TLP never silently resets an existing destination.
Malformed explicit values, including null/blank values in archives, are rejected.
Differing incoming designations use existing conflict review and require an explicit
replacement/keep decision before an update. Older ancestry that would not replace
content remains skipped. AMBER is encoded implicitly in revision fingerprints to
preserve pre-TLP ancestry; TLP edits mark the Case dirty and participate
in semantic revision checks. All newly exported Case metadata remains explicit.

## Executed verification

- Focused Case TLP Python tests cover storage migration, defaults/permissions,
  validation, activity, public filtering, backup recovery, malformed archives,
  conflict decisions, old-archive replacement, and Word markings.
- Existing API, sync, backups, reporting, create-name, and public projection tests.
- SDK method/transport/model tests, including TLP create/update and omission.
- `node tests/browser/case-tlp.cjs`, at `/` and with `MWS_BASE_PATH=/mws`, checks
  create geometry, native selection/swatches, caret, validation retention, strict
  tooltips, row height, live Board updates, and anonymous exclusion.
- Existing create-name and Cases/family/actor public-dashboard browser checks.

Final focused results: 13 Case TLP tests and 361 SDK tests passed. The broader
regression invocation reported 181 passed and one existing failure in
`test_mitre_mapping_save_has_autosave_countdown_and_manual_reset`: its source-string
expectation omits the already-present mapping conflict guard. Reporting checks
passed after final marking changes. TLP browser checks passed at both base paths;
Create Case, Board Impact, Case tab synchronization, and all three public wall
browser regressions passed. The older comprehensive Board table script still
reports a metrics-grid overflow at 1024px even with the table hidden; the TLP
create layout and compact-marker checks pass independently. These unrelated
failures were left unchanged.
