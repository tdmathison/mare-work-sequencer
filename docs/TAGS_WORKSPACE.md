# Intelligence navigation and Tags profile workspace

Intelligence uses the existing sidebar group component and contains Malware
Families, Threat Actors and Tags in that order. Its parent destination is the
existing `/malware-families` workspace; no landing page is added. Active children
expand/highlight the group, and the existing persisted, keyboard and mobile
sidebar behaviors apply. All three destinations retain their `tags:read` gate.

`/tags` and `/tags/<integer-id>` render the same master-detail workspace. It reuses
family/actor page headers, panels, content padding, theme tokens, stage badges and
shared `MwsTabs`. The separate old detail-page template has been retired. Directory
selection and tabs update the workspace without replacing the browser document;
normal URLs remain usable as bookmarks and through browser history.

The directory supports search, All/Malware/Threat actors/Other namespace filters,
name/most-used/least-used sorting, and 50-entry pages. Namespace classification
uses the existing stored `MAL_`/`TA_` prefixes; it is not proof of a profile link.
Tag identity, uppercase ASCII validation and matching remain in `tagging.py`.
On narrower screens the shared Back to directory control switches between the panes.
The common toolbar keeps Type and Sort in its Filters disclosure. Workspace
structure and geometry are shared with profiles; see [shared workspaces](INTELLIGENCE_WORKSPACES.md).

Overview shows only existing tag metadata and live profile associations queried
by tag ID. It links configured family/actor profiles or, for authorized managers,
opens the existing creation form with that tag prefilled. General tags have no
profile-creation action. Existing profile namespace restrictions still apply;
a namespace-only tag needs a valid suffix before profile creation is offered.

History shows current Case membership, not an audit of past assignments. The
header, directory and History tab use the same accessible count. Case rows use
the existing Case-read permission and shared inventory scope, include completed
Cases, count each Case once, and paginate at 50 rows. Without Case-read access,
counts are zero and no Case details are rendered. Profiles currently share the
existing global `tags:read` permission; no new per-profile ACL is introduced.

Creation uses `tags:create`; rename, merge and delete keep `tags:manage`, CSRF,
validation and confirmation checks. Profile-linked tags cannot be deleted or
merged, and server/database protections remain authoritative. Renames retain
identity and references; workspace forms retain filter context and coherent
selection after success or failure. Browsing does not create tags or profiles.

No schema, backup format, versioned REST API or SDK contract changes are needed.
The catalog's optional Case-access argument scopes workspace counts without
changing existing API/export callers.

Verification:

```sh
PYTHONPATH=.:sdk .venv/bin/pytest -q tests/test_tag_workspace.py tests/test_tagging.py tests/test_tag_names.py tests/test_malware_families.py tests/test_threat_actors.py tests/test_family_reports.py tests/test_sidebar_hierarchy.py tests/test_shared_tabs.py
node tests/browser/tag-workspace.cjs
node tests/browser/sidebar-navigation.cjs
node tests/browser/tags.cjs
node tests/browser/malware-families.cjs
node tests/browser/threat-actors.cjs
```

Browser fixtures use disposable data directories. Set `MARE_BROWSER_EXECUTABLE`
when an installed Chromium/Chrome executable is used instead of Playwright's
browser download.
