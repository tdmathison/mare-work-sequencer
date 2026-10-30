# Shared workspace tabs

Case Workbench, Tools, Settings, Import/Export, Developer plugin details and
research profile sections use `templates/components/tabs.html`,
`static/mws-tabs.css` and `static/mws-tabs.js`. The stylesheet is extracted from
Case Workbench: 4 px gap, muted inactive text, gold active text and 3 px underline,
flat corners, panel active background, 14 px type and the original padding.
Optional icons use a constrained line height so glyph fonts cannot increase tab
height. Focus outlines sit inside the scroll area to remain visible.

`bar(label, classes, links, attributes)` renders a tablist or a routed navigation
bar. `item(label, identifier, active, href, controls, disabled, title, icon, badge,
attributes)` renders a button or link. Existing section classes, identifiers and
data attributes remain available to their adapters. Permission-filtered Settings
and Tools entries continue to be supplied by the existing server handlers.

`MwsTabs.bind(element, select)` handles Left/Right, Home/End, skips disabled items,
and reveals focused/selected items in the horizontally scrolling bar. The
selection callback retains ownership of routing, lazy content loading, guards and
persistence. Routed Settings links use native link activation, including existing
unsaved-form protection. Case tabs represent selection in the existing `tab`
query parameter and support browser Back/Forward. Tools retains its existing
history state and iframe leave guards. Routed bars automatically opt into native
link keyboard handling through `bar(..., links=true)`. Specialized nested editor controls remain separate.

All three bars scroll horizontally instead of wrapping on narrow screens. Page
content, permissions and routes are unchanged. Component tests live in
`tests/test_shared_tabs.py`; `tests/browser/shared-tabs.cjs` compares computed
active/inactive/hover/focus styles across all three pages and exercises routing,
keyboard behavior, history, dirty-form protection and responsive overflow.

## Application-wide audit and adoption

The same component now also renders **Import & Export → Export backup / Import
archive**, **Developer → Plugins detail sections**, and the **Malware Family /
Threat Actor profile sections** (one shared profile template). Obsolete backup,
profile and plugin-detail tab selectors, active indicators and responsive padding
rules were removed. Case/Tools adapters no longer reproduce ARIA selection and
panel switching; click handling is also owned by the component.

`MwsTabs.bind(element, {activeId, onSelect, panels})` binds pointer and keyboard
activation. A callback remains supported as shorthand. Without a callback it
selects locally. `MwsTabs.setActive(element, identifierOrElement, {panels:true})`
updates active ARIA state, roving tabindex and controlled-panel visibility. Tabs
can control a shared panel (the Developer metadata view) without hiding that
panel when another tab is inactive. Routing, leave guards and data loading remain
in the caller; the component has no case/tool/settings dependencies.

Visual defaults are declared once in `static/mws-tabs.css` as
`--mws-tabs-indicator`, `--mws-tabs-padding-block` and
`--mws-tabs-padding-inline`. A change there affects every adopter. The shared
browser regression substitutes a different indicator thickness in this one
stylesheet and verifies that Case Workbench, Tools and Settings all change.

### Intentionally separate controls

| Location | Reason |
| --- | --- |
| Developer Editor open files and Output/Debug console | Nested IDE controls with close/dirty state and console layout; not workspace navigation. |
| Task/report Raw/Preview (`tasks.html`, `report_workspace.html`) | Segmented editor presentation modes inside editing surfaces. |
| Case RAW/Standard archive selector (`case.html`) | Export-format selection, not section navigation. |
| Indicator CSV/STIX import selector (`indicators.html`) | Input-format selection within a dialog. |
| Snort and YARA assistance (`snort_builder.html`, `yara_editor.html`) | Nested editor docks with specialized persistence and editor sizing. |
| Data Explorer Investigation Coverage/Knowledge Gaps (`data_explorer.html`) | Compact inventory-mode switch within a resizable graph dock and toolbar. |
| Import stage indicators and inventory filters | Workflow progress and filtering buttons, not tabs. |
| Developer SDK contents and application sidebar | Vertical document/application navigation, not horizontal tabs. |
| Swagger UI and embedded CyberChef/vendor controls | Third-party application internals; managed by their upstream components. |

`tests/test_shared_tabs.py` checks adoption and rejects shared-tab CSS outside the
component stylesheet. Its explicit inventory of specialist raw tablists requires
an audit decision when a new one is added. Shared CSS must not be overridden by
page selectors; layout-specific content styling belongs outside the tab bar.
