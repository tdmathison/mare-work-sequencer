# Public Threat Actors dashboard

`/dashboards/threat-actors` and its dedicated JSON endpoint
`/dashboards/threat-actors/data?page=0&library_page=0` are anonymous and read-only.
The shared registry marks Threat Actors Public and available. Login, the directory,
Dashboards dropdown and public wall navigation link here. The rightmost link is
Login anonymously or Return to the MIP Board when authenticated. Private actor,
attachment, case and management routes retain their existing authorization.

## Public projection and counts

The dedicated server projection shares the Family wall's allowlist infrastructure.
Each card exposes exactly name (up to 200 characters), linked TA_ tag, short
description (up to 1,200 characters), valid update timestamp, linked-case count,
in-progress count, OSINT-entry count and attached-report count. Text is rendered
with `textContent`. No aliases, identities, associations, private research, OSINT
URLs, report metadata/bytes, case details or management links are exposed.

Eligible profiles must exist and link to a valid TA_ tag. Standalone tags do not
count. Profiles have no additional private/hidden flag; deletion is physical.
Eligible cases use the existing public-wall rule: current stage 0–3, including
unassigned cases. Invalid-stage and deleted cases are excluded everywhere.

- Tracked actors counts eligible profiles.
- Actors with work in progress counts distinct profiles linked to current Malware
  Analysis (1) or Packaging & Delivery (2) cases.
- Unique linked cases counts distinct eligible cases across all eligible actor
  tags, once even when several TA_ tags appear on one case.
- Reports collected counts attached report records owned by eligible actors;
  OSINT URLs are separate counts.

Per-actor case counts follow `threat_actors.tag_id` and `case_tags`, never loose
name matching or associated Malware Family tags. Actor-family associations do not
contribute cases. These are research-library/workload metrics, not prevalence or
global threat activity. Four bounded aggregate queries run within one SQLite read
snapshot, without per-profile queries or attachment filesystem access. Requests
do not modify profiles or timestamps.

## Selection, paging and refresh

The spotlight prefers actors with in-progress cases, then newest valid update
date, then ascending stable identity. Without in-progress work it selects the most
recent eligible profile. Missing/invalid dates sort last and are omitted; displayed
dates use the application's configured timezone.

Investigations sort by in-progress count descending, update descending, identity
ascending. Three cards appear per page, rotating every 25 seconds with visible
page/count and manual pause/previous/next controls. The library sorts by name
case-insensitively, then identity, with at most 24 profiles per page. Manual paging
reaches every actor. Overflowing cards move left at 20 CSS pixels/second with one
inert, aria-hidden seam copy. A completed traversal advances the library page.
A stationary short page also advances on the 25-second rotation timer, so a final
one-card page does not stop the library cycle.

Hover, keyboard focus and explicit pause stop motion; arrow keys browse a focused
strip. Reduced motion disables all automatic movement/rotation and removes seam
copies, retaining manual paging and native horizontal browsing. Empty and single
profile states are intentional. Layout stacks at narrow widths without horizontal
page overflow; 1080p displays show the complete overview.

Snapshots refresh every 60 seconds, on visibility return and on page changes.
Requests never overlap; newer intent supersedes old responses and queues the
latest request. Failures/timeouts retain the current display and last successful
update with a stale warning. Valid pages, explicit pauses and unchanged strip
content survive refresh. Leaving cleans up timers, observers and requests; browser
back-forward restoration restarts them. Live JSON uses the existing public walls'
`no-store` policy, avoiding stale data after deletion/restore; styling/scripts use
the existing static asset handling. No response cache or persistent dashboard
configuration is introduced, and existing actor backup coverage is unchanged.

## Verification

```sh
PYTHONPATH=. .venv/bin/pytest -q tests/test_actor_dashboard.py tests/test_family_dashboard.py tests/test_cases_dashboard.py tests/test_dashboard_directory.py tests/test_navigation.py
node tests/browser/actor-dashboard.cjs
node tests/browser/family-dashboard.cjs
node tests/browser/cases-dashboard.cjs
node tests/browser/dashboard-directory.cjs
node tests/browser/threat-actors.cjs
```

Browser checks use disposable data and local Chrome/Playwright. Set
`MARE_BROWSER_EXECUTABLE` to override Chrome or `MARE_ACTOR_WALL_SCREENSHOT` to
save the actor-wall screenshot. Coverage includes 49 actors, long text, distinct
tag counts, association isolation, deterministic selection, field privacy,
pagination, 1080p/desktop/mobile geometry, safe text, movement/seams, pauses,
reduced motion, stale failures/recovery, superseded requests, live updates and
working Cases/Family navigation. Tests never add demonstration records to the
development or production databases. Production data is unavailable here; browser
verification covers Chrome rather than every browser engine.
