# Shared Intelligence workspaces

Malware Families and Threat Actors continue to use `malware_families.html` with
their existing profile specification. Tags uses `tags.html`. All three render
`components/intelligence_workspace.html` for their header, metadata summary,
primary action, search toolbar, directory rows, selected-object header, tab inset,
empty state, metadata footer, and Case History table.

`static/intelligence-workspace.css` owns workspace geometry: the 300px directory,
24px pane gap, common panel surfaces, 30px content inset (20px on phones), toolbar
control sizes, title/action layout, and responsive behavior. The existing outer
application padding and shared `MwsTabs` remain authoritative. Domain styles must
not redefine these boundaries. `malware-families.css` retains profile forms,
research content and shared family theme primitives; `tag-workspace.css` retains
only tag chips, facts and management disclosures.

On narrow screens, each workspace shows its directory or selected object, with
the same Back to directory control. The directory scrolls internally within a
viewport-relative maximum only; short lists keep their natural height. Scrollbar
chrome and its reserved gutter are hidden on this directory alone, while native
wheel, trackpad, touch and keyboard scrolling remain enabled. Selected rows are
revealed inside the directory after navigation or returning from details. Detail content follows the normal page scroll; tables
have their own horizontal scrolling boundary. Long names and metadata wrap.
Tags retains its existing Type and Sort fields within a keyboard-accessible
Filters disclosure in the common toolbar. It closes on Escape or an outside
click and stays within the viewport, without moving the panels below it.

Summaries use the existing filtered totals and authorized Case counts. Profiles
retain aliases, canonical tags, descriptions, OSINT links and reports. Tags retain
namespace, identity, actual profile association, prefilled profile creation and
management actions. Case History shares its table markup, stage badges and links;
queries, authorization and pagination remain with their existing controllers.
No schema, API, SDK or backup changes are introduced by this layout consolidation.

Checks:

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_intelligence_workspace.py tests/test_tag_workspace.py tests/test_tagging.py tests/test_tag_names.py tests/test_malware_families.py tests/test_threat_actors.py tests/test_family_reports.py tests/test_sidebar_hierarchy.py tests/test_shared_tabs.py tests/test_navigation.py tests/test_api.py tests/test_sdk_api_extensions.py
node tests/browser/intelligence-workspace.cjs
node tests/browser/intelligence-directory.cjs
node tests/browser/tag-workspace.cjs
node tests/browser/malware-families.cjs
node tests/browser/threat-actors.cjs
node tests/browser/tags.cjs
node tests/browser/sidebar-navigation.cjs
```

Browser checks use disposable data. Set `MARE_BROWSER_EXECUTABLE` to an installed
Chromium/Chrome executable if needed. The comparison suite records screenshots
under `/tmp/mws-intelligence` and checks major boundaries at 1440, 1024, 901, 768
and 390px in no-selection, selected-object, History and empty-result states. It
also checks long names/metadata, mobile selection/return and filter panel bounds.
