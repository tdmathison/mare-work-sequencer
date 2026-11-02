# Help guide

Help is the last sidebar item for authenticated users. It uses a compact,
single-column guide: introduction, SOP links, FAQ search, and a one-open-answer
accordion. New installations include the introduction only; no illustrative SOPs
or FAQs are seeded. Nothing contacts SharePoint or another external service.

Administrators select **Manage help** to edit the introduction and add, edit,
delete, or move SOPs and FAQs. Expand an entry to edit it. FAQ answers use the
shared Markdown editor with Write and Preview. **Save help** applies the entire
versioned document atomically, for all users, without restarting. Changes to a
page already open in another browser appear on reload.

Deleting an entry requires confirmation, followed by Save help. Closing with
unsaved changes requires confirmation. Failed requests retain edits. A concurrent
save returns HTTP 409; edits remain available until the administrator explicitly
chooses **Reload current content** and confirms discarding them.

SOP URLs must be absolute HTTPS URLs without credentials, control characters, or
whitespace. Query parameters and fragments are preserved. Administrators provide
the actual SharePoint document URLs; SharePoint continues enforcing access. MWS
never fetches, embeds, tests, or synchronizes documents. Links open a new tab with
`noopener noreferrer`. Markdown uses the existing HTML-disabled parser; images
are rendered as alt text to avoid automatic remote requests. Questions and all
non-Markdown content are plain text.

An additive startup migration creates `help_guide`. One row contains the document
revision and JSON with ordered SOPs/FAQs, stable UUIDs, UTC created/updated times,
and author UUIDs. Limits: 2,000-character introduction, 100 entries per section,
200-character SOP titles, 4,096-character URLs, 300-character questions,
20,000-character answers, and 1 MiB of saved content. Every save is audited.

Authenticated web endpoints are `GET /help`, `GET /help/content`,
`POST /help/content` (form fields `csrf`, `document` JSON), and
`POST /help/preview` (`csrf`, `text`). Both POST routes require the built-in
Administrator role server-side. Content updates require the current `revision`.
These are session endpoints, not additions to the bearer-token SDK API.

Complete application backups include the Help table and all identities and
metadata automatically. Recovery validates Help content. Modern snapshots restore
their guide. Older snapshots without the table receive the additive migration;
web replacement retains the destination's configured Help and explicitly notes
that in preview. Offline recovery into an empty destination uses the default
introduction when old archives lack Help. Portable Case/MIP exports are unchanged
and do not include global Help content. No new selectable backup category exists.
