# Public Malware Families dashboard

`/dashboards/malware-families` and its dedicated JSON endpoint
`/dashboards/malware-families/data?page=0&library_page=0` are anonymous, read-only.
The login header and public navigation link to Cases, Malware Families and Threat
Actors. Login stays at the far right for anonymous visitors; authenticated visitors
see Return to the MIP Board. Internal profile, case, OSINT, attachment and API permissions
are unchanged. Deployment operators should understand that all existing eligible
profile names, MAL_ tags and short descriptions are intentionally public here.

The server projection allows only family name (200 characters), linked tag, short
description (1,200 characters), valid profile update timestamp, and aggregate linked
cases, in-progress cases, OSINT entries and attached reports. Envelope fields are
snapshot time, display timezone, metrics and pagination. No profile/user IDs, long
descriptions, attribution, OSINT URLs/content, report metadata/bytes, case details,
management links, settings or credentials are serialized. Text uses `textContent`;
no archived code, HTML or Markdown executes. Visually bounded long names/tags retain
full text for assistive technology and title tooltips. Short descriptions are
summaries rather than a replacement for authenticated research views.

## Eligibility and metrics

The profile model has no additional hidden/private flag; deletion removes records
physically. Existing profiles linked to a current valid MAL_ tag qualify. Standalone
MAL_ tags do not count. Cases use the same eligibility as the public Cases dashboard:
current stages 0–3, including unassigned cases; deleted or invalid-stage cases do
not count. Relationships follow `malware_families.tag_id` and `case_tags` foreign
keys, never names, substring matching or source numeric IDs.

* Tracked families: eligible profiles.
* Families with work in progress: profiles with at least one case in Malware
  Analysis (1) or Packaging & Delivery (2).
* Unique linked cases: distinct eligible cases across eligible profile tags; a case
  carrying several family tags counts once.
* Reports collected: existing attached report rows for eligible profiles, excluding
  OSINT URLs. Per-family OSINT/report totals count each respective child table.

These metrics describe the research library and workload, not threat prevalence,
detections or attack frequency. Multiple fixed aggregate queries run inside one
SQLite read snapshot; no per-family queries or filesystem reads occur. Requests do
not change records/timestamps. No derived data or dashboard settings are persisted,
so existing complete backup coverage needs no changes.

## Selection, paging and motion

The spotlight prefers a profile with in-progress work, then newest valid update
date, then ascending stable profile UUID. With no active work it uses newest update
and UUID. The number of active cases does not determine the spotlight. Invalid or
missing dates sort last and are omitted in cards. Dates use `MARE_DISPLAY_TIMEZONE`,
the same application configuration as the Cases wall.

Investigations sort by in-progress count descending, update descending, UUID
ascending. Three cards show per page, rotating every 25 seconds, with previous,
next and pause controls. Current page and total are always visible.

The library sorts by case-insensitive name and stable UUID and returns **at most
24 profiles per server page**. Manual library navigation reaches every page. An
overflowing window moves at 20 CSS pixels/second; one inert, aria-hidden copy
provides a seamless loop within that window. After a full traversal it requests the
next library page, allowing all profiles to appear without an unbounded payload.
Library-window changes reconcile the cards at the start of the new window. The
payload is bounded to one spotlight, three investigation cards and 24 tracked
cards, independent of total library size. Each request returns a complete current
snapshot for those pages; out-of-range pages clamp after deletion.

Hover, keyboard focus and explicit pause stop strip motion. While focused, left
and right arrow keys browse overflowing cards without waiting for animation. Pauses and valid page
positions survive data refresh. Nonoverflowing content is stationary; a short final page in a multi-page library
automatically advances on the 25-second rotation timer. Reduced
motion disables automatic scrolling and investigation rotation, removes duplicate
cards, and uses native horizontal scrolling plus manual paging. The screen has
intentional empty and single-profile states. Wide screens use side-by-side main
cards; narrow screens stack and allow ordinary vertical scrolling.

Refresh runs every 60 seconds and when a hidden tab becomes visible; page changes
also fetch a fresh snapshot. Only one request runs at a time. Newer refresh intent
supersedes an outstanding response and queues the latest request. Twenty-second
timeouts and errors retain the previous display and expose a stale-data warning
with the last successful timestamp. Subsequent refreshes retry. Unchanged cards
are not rebuilt, preserving strip position and avoiding flashes. Animation remains
independent of fetch timing. Leaving cancels requests/timers/animation and disconnects
observers; back-forward-cache navigation restarts them. Responses use `no-store`
like the Cases wall, preventing stale intermediaries; no server cache contains
public projections that could outlive deleted records.

## Verification

Run:

```
.venv/bin/python -m pytest -q tests/test_family_dashboard.py tests/test_cases_dashboard.py tests/test_malware_families.py tests/test_family_reports.py tests/test_navigation.py
node tests/browser/family-dashboard.cjs
node tests/browser/cases-dashboard.cjs
```

Browser checks require Playwright and local Chrome (`MARE_BROWSER_EXECUTABLE` may
override the executable). They use disposable isolated application data, including
long text, eight active families and 33 tracked profiles. They check 1080p, desktop
and mobile geometry; text safety; movement, seam copies, pause/focus/hover; both
pagination controls; reduced motion; stale failures and recovery; nonoverlapping
superseded responses; live database changes without reload; empty/single profiles;
and navigation back to the working Cases dashboard. They never populate production
with example records. Optional `MARE_FAMILY_WALL_SCREENSHOT` saves a screenshot.
