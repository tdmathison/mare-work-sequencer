# Data Explorer

`/data-explorer` is an authenticated application view. Its top-level link sits
at the far right after flexible space and a subtle divider; it retains the existing
compact desktop navigation height and wrapping behavior. It is separate from the
public dashboards. The request attachment included text requirements but no separate
mockup asset. The Focus Canvas uses floating controls, a full-width graph and a compact selection tray
with MARE panels, typography, gold, muted blue and existing neutral CSS tokens.
There is currently one application theme; the explorer inherits its color tokens.

## Relationships and access

The metadata-only `/data-explorer/data` endpoint builds stable, deduplicated IDs
for actual cases, Malware Family profiles and Threat Actor profiles. Case-to-profile
edges use `case_tags` and each profile's stable `tag_id`, validated against its
MAL_ or TA_ namespace. Unconfigured tags never fabricate profiles. The single
`actor_families` table supplies live family-to-actor associations once, without
inference through names, descriptions or related cases. Deleted/unavailable links
are absent from the graph.

Cases require `cases:read`; profiles and tag-based relationships/search require
`tags:read`. Either permission grants access to the page, with the other object
types disabled if unavailable. The same authorized CTE supplies counts, selected
nodes and edges in three batched queries inside one SQLite snapshot. Metadata is
limited to labels, profile aliases/tags and existing authorized workspace links;
long research descriptions and case contents are not fetched with the graph.
Responses use private `no-store` caching.

Search matches case number/title, profile name/alias/tag, or case tags where
permitted. Results include the matching seeds and their immediate neighbors,
then apply the selected type filters. A view has an explicit **400-primary-object
limit**. An oversized view returns HTTP 413 and an instruction to narrow search
or filters, rather than quietly omitting objects. Search/filter state survives
refresh via the URL; object positions stay fixed during ordinary selection,
expansion, filtering and panning within the page. Refresh data reloads saved state.

## Graph interaction and accessibility

The graph uses pinned, locally served **Cytoscape.js 3.33.1 (MIT)**. It provides
pointer-centered wheel zoom, touch gestures, background pan, node dragging and a
bounded CoSE force-directed layout. The [official API](https://js.cytoscape.org/)
documents these interactions, layout and destruction. CoSE runs to completion
without continuous motion; Auto Arrange is explicit. No layout worker is started.
Fit View accounts for floating top controls, the selection tray and any open
long-details drawer. Reset View is a secondary action in Legend & objects. Neither
resets manual object positions.

Cases are larger document icons in blue rounded rectangles with a restrained blue
underlay; selection strengthens their outline/halo. Case numbers stay visible, with
current lifecycle labels when space permits. Those labels come from existing case
stages and the established application state names. Families keep gold bug icons
in hexagons and actors neutral shield/person icons in pentagons. Brighter slate-blue
relationships remain visible; the selected neighborhood uses gold. No directional
arrows, continuous movement or glow effects imply fictional causality/activity.

The canvas fills the application content width. The prior permanent sidebars are
removed. Floating search/Filters sit upper left, Auto Arrange/Fit View upper right,
and zoom controls lower right. Type-count chips include only displayed primary
nodes; expanded categories never inflate these counts. The compact bottom tray
shows the selected object, status/tag, relationship count, profile/case links,
case expansion and permission-filtered nonempty MIP summary chips. Details opens
a dismissible overlay drawer for aliases, relationship lists and category contents.
Opening/closing overlays, selecting objects and MIP visibility changes never resize
the canvas or change its viewport/model positions.

Filters contains the supported type toggles and Show MIP contents. The latter
shows/hides categories already expanded from cases rather than expanding every
case. Its default is on. The badge counts excluded authorized types plus an off
MIP visibility toggle; default/unavailable types do not inflate it. Reset Filters
restores authorized types and MIP visibility while retaining the search text.
Type/MIP filters persist in the URL; `type=none` preserves a fully empty view.
Popovers dismiss with close, Escape or outside click. Escape prioritizes the
focused overlay and restores its toggle's focus. Details has a close button and
Escape dismissal. Legend & objects offers the keyboard object list, gesture help,
Refresh data and Reset View without adding another overflow menu.

Normal desktop screens fit without page scrolling. On narrow screens the controls
reflow and popovers/drawers scroll within their own bounds. The canvas has a
480px mobile minimum (320px otherwise), allowing natural page scrolling when the
existing mobile application header/navigation occupies most of a short screen.
The tray clears zoom controls; mobile Help becomes a named compact button beside
it. Labels simplify on compact/zoomed-out views while full names/statuses remain
available in tooltips/tray/details. Reduced motion removes decorative transitions;
layout and viewport changes are always unanimated. Resizing fits the current
view without changing model positions.
Loading, no-match, oversized-view, expired-session and request-error states are
visible. Text uses `textContent`, never arbitrary HTML. Leaving aborts requests,
stops layouts, disconnects resize observation and destroys the graph; back-forward
cache restoration reloads it.

## Standard MIP categories

Selecting a case offers **Expand Standard MIP**. Only nonzero categories are added,
as compact icon/count summaries connected directly to the case. Collapse removes
only those summaries and edges, preserving all primary positions/relationships.
Children are placed near their parent with clearance from existing objects.
Expansion fits only if the new children fall outside the usable canvas, without
moving primary objects. MIP summaries load once per case in a graph refresh and
are reused by the tray/expansion. Refresh data reloads saved-state summaries.
Expansion calls `/data-explorer/cases/<id>/contents`; selecting a category reads
`/contents/<category>?page=0`, with **200 entries per detail page**.

The exporter and explorer share `standard_package.py` file selection, including
existing report exclusions, template/backup exclusions and symlink protection.
The explorer predicts the export's generated STIX from saved rows without writing
it, scaffolding package directories, generating reports or building a ZIP. It
uses the Standard package **without optional malware samples**, independent of
case stage. Composition does not certify export readiness; normal report/review
and stage checks still apply when actually exporting.

Counts are defined as follows:

| Category | Counting unit |
| --- | --- |
| Indicators | Nonblank CSV entries excluding the header. If the CSV is absent and generated STIX is available, its represented saved rows. CSV/STIX representations never count twice. |
| References | Nonblank entries from the exported references CSV, excluding the header. |
| Reports | Included PDF, DOC/DOCX, RTF and ODT documents. The existing Standard predicate excludes the tracked current Word report; Explorer preserves that rule. |
| Images | Included image files. Editor/source images under `reports/sections` are excluded by Standard selection. |
| Package files | Remaining included files plus generated `README.md` and `manifest.json`. Indicator/reference carriers, reports and images are excluded from this category. |

The two generated files are listed honestly as generated during export and have
no fabricated download action. Empty Standard packages therefore still have two
package-file entries. RAW-only source/editor files, backup files and samples never
contribute. Custom files under the exporter’s permitted package directories follow
its existing inclusion rules; other IOC files are files rather than invented rows.

Category lists/counts require `cases:read` plus their existing domain permissions:
`indicators:read`, `references:read`, `reports:read`, or `cases:assets`. Missing
permissions are reported as hidden categories rather than misleading zeroes.
Downloads additionally require `cases:assets`; report/IOC paths retain their domain
checks. The explorer's download wrapper rechecks current Standard membership and
serves attachments with octet-stream, `nosniff`, sandbox and private no-store.
There is no inline execution/preview. References become external links only for
HTTP(S) URLs without credentials; other values remain plain text.

CSV inspection is bounded to 16 MiB, 20,000 data rows and 100 columns. Unsupported
or changing tables return an explicit error with the existing case workspace as
the fallback. Filesystem and database writes by another client are not jointly
transactional; a changed file may require retry/Refresh data. No explorer data,
layout positions or configuration is persisted, and backup formats do not change.

## Verification

```sh
npm run build:explorer
PYTHONPATH=. .venv/bin/pytest -q tests/test_data_explorer.py tests/test_zip_metadata.py tests/test_indicator_export_coverage.py tests/test_indicator_stix.py tests/test_indicators.py tests/test_references.py tests/test_navigation.py
npm run test:explorer
```

Server tests compare categorized paths and counts against an actual Standard ZIP,
exercise authorization, stable relationships/deduplication, filtered search/limits,
pagination, missing packages, zero categories and no-write STIX planning. Existing
ZIP metadata and indicator export tests cover exporter regression. Browser tests
use isolated data in Chrome for navigation height/order, zoom/pan/drag/layout,
settled positions, category expansion/collapse/details/downloads, safe text/URLs,
filter badge/reset/persistence and keyboard dismissal, overlay viewport stability,
MIP visibility and primary-only counts, brighter edges/case emphasis, errors and
1920/1366/390px geometry. Desktop checks assert no unnecessary page scrolling. Set `MARE_EXPLORER_SCREENSHOT`
to a temporary filename prefix to capture layouts. Production data and other
browser engines are not available in these checks.
