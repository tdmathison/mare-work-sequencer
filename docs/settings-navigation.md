# Administration under Settings

Settings follows Tools in the application navigation; API sits immediately before Tools. Clicking its
text opens General. Its adjacent **Open Settings menu** button independently
opens the category links; desktop mouse hover also opens them. The dropdown and
the Settings shell show authorized categories in this order:

| Category | Canonical URL | Existing content and access |
| --- | --- | --- |
| General | `/settings/general` | Password, autosave, board defaults, private Word templates; administrator sample-archive protection remains available. All signed-in accounts retain their existing General access. |
| Users | `/settings/users` | Account list, roles, enabled state, last login, create/reset/delete actions; existing built-in Administrator restriction. |
| Audit | `/settings/audit` | User filter, existing grouped/sorted history and CSV/ZIP exports; existing Administrator restriction. |
| Import & Export | `/settings/import-export` | Backup & Restore, including its nested Export backup / Import archive workflows; existing `backups:manage` permission. |

`/settings` opens General. General is always available to authenticated accounts
under the current authorization model, including accounts required to change their
password. Menu construction chooses the first authorized category as its Settings
link. Unauthorized categories are omitted from both navigation surfaces, and their
existing handlers still reject direct access. No role permissions were broadened.
No other category's sensitive content is rendered in the selected page.

All category tabs are ordinary links. The URL determines the selected category on
refresh, Back/Forward and new-tab navigation; invalid category paths return the
existing authenticated not-found behavior. Settings is gold/active for each category
and related actions. Nested backup workflow tabs retain their separate line-tab
styling and existing state/job behavior.

## Compatibility and recovery coverage

GET bookmarks `/account`, `/users`, `/audit`, `/import-export`, and `/backup-restore`
redirect to their corresponding canonical category. Query strings survive unchanged,
including actor filters and pagination parameters. Existing POST routes, user
mutation routes, audit export URLs, template downloads and backup job endpoints
remain supported. Canonical General and Users URLs also accept their existing forms'
POSTs. Validation failures stay in their category. API endpoints are unchanged.

General's redundant Backup & Restore shortcut panel was removed. It had no separate
recovery engine: it already pointed to the consolidated archive workspace. Complete
encrypted database/file snapshots, key material, selective transfer, legacy archive
validation, full replacement and staged rollback remain in Import & Export through
the same shared services. No backup files, recovery journals, stored data or shared
services were deleted. Sample archive protection remains in General because it
configures uploads rather than installation recovery.

Jobs remain independent of category navigation. Their owner-scoped durable status,
download/apply endpoints, sessionStorage references and existing job lifetimes are
unchanged. The backup script runs only on its category and stops polling on page
exit; returning resumes known status and nested workflow selection. Existing RAW
case synchronization review routes remain valid and use the same Settings shell.

## Interaction and unsaved changes

The dropdown has normal navigation links, not ARIA menu roles. Its separate button
exposes `aria-expanded` and `aria-controls`; Enter/Space toggle it and Arrow Down
focuses the first link. Tab reaches all visible links. Escape closes and restores
focus to the toggle. Pointer exit closes unless focus remains inside; outside
pointer/touch interaction dismisses it. Positioning is clamped to the viewport and
recomputed on resize; the navigation container does not clip it. Category tabs wrap
on narrow screens. Styles are scoped to Settings/navigation and retain typography.

General and user-create forms use the existing unsaved-dialog pattern. Changed
forms prompt before same-window navigation: Save and continue, Discard changes or
Cancel. A single changed form can submit through its original handler and navigate
to a validated local category only after a successful save. Validation failures
remain visible. Browser navigation/reloads also retain the native unsaved warning.
Secrets and file contents are never copied into persistent browser storage.

Existing forms save independently. If multiple forms are changed, Save and continue
is disabled and the dialog explains that they need review or explicit discard.
Submitting one form while another is dirty also warns before losing the latter's
changes. This is not a new multi-form transaction. Opening a link in a new tab leaves
the current form intact. Backup selections/jobs use their own existing workflow
state and do not initialize General's form guard.

## Verification

```
.venv/bin/python -m pytest -q tests/test_settings_navigation.py tests/test_navigation.py tests/test_backup_workspace.py tests/test_family_reports.py tests/test_tools.py tests/test_api_documentation.py
node tests/browser/settings-navigation.cjs
node tests/browser/backup-workspace.cjs
```

Browser checks run against disposable local data with Chrome/Playwright and cover
hover continuity, direct navigation, keyboard/Escape, outside click, touch controls,
viewport bounds, refresh/history/new tabs, save/discard/cancel, user creation,
category navigation during export, resumed downloads and nested backup tabs.
Server checks cover canonical and legacy routes, query preservation, permissions,
CSRF, mutations, validation, safe save destinations and retained recovery services.

## Compact centered-chevron navigation

Chrome measurements identified the height regression: the global form-button rule
contributed `margin-top: 22px` to the dropdown toggle. The bar was 67px high and the
toggle center sat 11px below its label. The scoped navigation toggle now resets its
margin and padding, centers a 14px inline SVG with flex, and uses a minimum 44px-high
target (28px wide for fine pointers, 44px for coarse/touch pointers). Label font size
remains 11px. Other application buttons retain their original margins and styling.

The bar uses a 52px minimum height with small vertical padding and automatic height,
not a fixed height. It wraps as space decreases and can grow with enlarged text.
Measured desktop height is 52px and label/icon centers coincide. Overlay menus do
not contribute to layout; opening them preserves bar height and the main-content
position. There are no icon offsets, negative margins, or alignment transforms.
No expansion animation is introduced, so reduced-motion users see the same static
chevron. Existing viewport-clamping translation only positions the overlay.

`templates/navigation_components.html` provides the shared dropdown markup and SVG
icon. The repository has no application-wide icon library; this follows its existing
inline-SVG approach without adding a dependency. The shared `.dropdown-navigation`
styles and initialization work for each component using its own `aria-controls` ID.
Explicitly opened dropdowns remain open when pointer/focus leaves until dismissed;
hover-only menus close on pointer exit unless focus remains inside. Escape and
outside interaction clear explicit state. All category routes, permissions, content,
forms and background services remain unchanged by the compact styling.

The browser suite asserts desktop geometry, icon dimensions/centering, unchanged
label typography, absence of pseudo-element indicators, unchanged form-button
margins, overlay stability, enlarged-text containment, zoom-sized viewport reflow,
and 44px touch targets, alongside the original interaction checks. Native browser
zoom and Firefox/Safari still require manual verification.
