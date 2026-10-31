# Dashboards directory

`/dashboards` is a public directory. It renders static dashboard metadata without
loading Case Metrics, Cases, Malware Families or Threat Actors datasets. Search matches names and
descriptions, combines with visibility filters, and hides empty groups. Result
announcements are debounced; filtering leaves the existing controls in place.

The authenticated navigation replaces METRICS with the shared compact DASHBOARDS
dropdown. Its text opens the directory; its separate chevron opens quick links.
API remains immediately before Tools. Public wall pages retain their standalone
header and layouts. The login page keeps its existing public dashboard links and
adds a Dashboards link.

## Routes and access

- Content Metrics: `/content-metrics`, private and permission-scoped; see [definitions](CONTENT_METRICS.md). It follows Case Metrics in the directory and sidebar.
- Case Metrics: `/metrics`, authenticated and authorized by `metrics:read` (the same
  permission used by the existing Case Metrics API). Standard User and Administrator
  roles have this permission. Custom roles without it receive HTTP 403.
- Cases: `/dashboards/cases`, public.
- Malware Families: `/dashboards/malware-families`, public.
- Threat Actors: `/dashboards/threat-actors`, public.

Anonymous Case Metrics launch links use `/login?next=/metrics`. Both the GET parameter
and posted hidden field are validated against exact registered private dashboard
paths. Invalid destinations fall back to the board after login. Existing forced
password-change routing still takes precedence. A signed-in user without Case Metrics
permission sees a noninteractive restricted state in the directory and dropdown.

## Registering dashboards

Add a `Dashboard` entry in `dashboard_directory.py` with identifier, display name,
description, Flask endpoint, visibility, availability, permission and sort order.
The directory, quick-link menu and public wall navigation all consume this registry.
A coming-later entry has no endpoint. Implemented private endpoints must enforce
the declared permission on the server; registry labels do not authorize requests.
Only public entries appear in public wall navigation. Visibility and availability
remain separate. Inline lock/globe SVGs use the existing navigation SVG approach;
this repository has no shared icon library.

## Verification

Server coverage checks anonymous and authorized views, restricted direct Case Metrics
requests, registry consistency, active navigation, preserved API/Tools ordering,
public walls and safe login returns. `tests/browser/dashboard-directory.cjs`
uses disposable data and Chrome to exercise search/filter combinations, empty
states, retained focus, public launch links/new tabs, login return, compact menu
geometry, hover/keyboard/Escape/outside dismissal, Settings and narrow touch layout.
Existing Tools, Settings, Case Metrics, Cases and Malware Families browser regressions
cover their original functionality and layouts.

Production data is not available in this development environment. Verification
uses isolated fixtures and does not change production or development case records.
