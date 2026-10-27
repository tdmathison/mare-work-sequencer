# Backup & Restore

Administrators and roles granted `backups:manage` use **Backup & Restore** in the
Settings → Import & Export. The Export backup and Import archive tabs share the existing RAW,
installation-backup, family-report, and case synchronization services. The old
Settings database download now links here. The former plaintext full-database API
returns 410 with a link to the encrypted workspace; selective APIs remain supported. Individual case Backup shortcuts remain.

## Persistent-data inventory

A complete export snapshots every SQLite table, not just the selective areas:
cases and UUID/revision state; lifecycle/history, tasks, notes, indicators,
references, reports and asset metadata; tag identities/assignments; family profiles,
ordered OSINT and research-report metadata; threat actor profiles, aliases and
stable Malware Family relationships; users, password hashes, roles,
permissions, disabled state, user identities, API credentials, settings, audit;
case sequence and historical number reservations; synchronization history and
application migrations. Future tables are included automatically.

All durable files below `MARE_DATA_DIR` are included, including case packages,
samples, scripts, images, generated reports and backups, family and actor report bytes,
user customizations and templates, private Snort/YARA drafts, `session.key`,
application-managed key files, and synchronization staging/recovery data. Unknown
persistent files are included. Symlinks fail export explicitly. Paths are relative.

Excluded derived/transient directories: `search-index`, `report-jobs`, `snort-jobs`,
`yara-jobs`, `family-report-staging`, `actor-report-staging`, temporary `case-import-*` directories, SQLite
journals and lock files. Active analysis/report jobs must finish first. Derived
search indexes rebuild after replacement. In-flight jobs and browser sessions do
not resume; application-managed recovery files remain available.

Application source, Python/browser/tool dependencies, TLS certificates outside the
data directory, reverse-proxy/systemd configuration, external services, and
**environment-provided secrets** are installation prerequisites. Provision these
separately, including `MARE_SECRET_KEY` when configured. The application-managed
session key is included; environment variables are not copied into archives.

## Export scopes and encryption

Complete application backup checks all implemented rows and adds system data.
Unchecking a row turns off complete mode; manually selecting every row stays
selective. Unchecking complete retains the checked rows. Threat Actors is an
implemented selective area. Empty selection disables Export. Counts come from the database;
archive size is shown only after generation.

| Selective area | Included content | Automatic dependency |
| --- | --- | --- |
| Cases | Full editable RAW state, stable case identities, samples and assets, user references, source number reservations | Referenced tag definitions and identities |
| Malware families | All profiles, ordered OSINT, attached report bytes, including profiles without cases | Required tags/identities and associated actor profiles with their family dependencies |
| Threat actors | Profiles, ordered aliases/OSINT, report bytes and stable Malware Family associations | Required TA_ tags, referenced configured family profiles and their tags; no unrelated cases |
| Tags | Definitions and stable identities | None |

Selective archives exclude authentication credentials and unrelated cases. Shared
family reports are stored once. RAW reversible `.py` / `_py.txt` conventions remain
supported. Exact usernames map selective owner/creator references through existing
services; numeric source user IDs never identify destination accounts. Unmapped
owners remain unassigned and existing creator fallback rules apply.

Complete archives require a user-supplied passphrase of at least 16 characters;
selective encryption is optional with the same minimum. The existing AES ZIP
library encrypts and authenticates both manifest and payload with AES-256. Use a
long unique passphrase and store it separately: MARE cannot recover it. No
passphrase is stored in job metadata, audit, sessionStorage, or preview. The private
working copy and rollback files are plaintext on disk: protect the service account,
data volume and backups. Export downloads expire after 24 hours.

## Formats and validated plans

New exports use `mare-backup/1`, one ZIP with `mare-backup.json` and `payload.zip`.
The manifest records archive UUID, creation/application version, complete/selective
scope, dependencies, counts, file sizes/hashes, payload SHA-256, schema contract,
and exclusions. The payload uses installation format 3 or selective case format 3; installation
formats 1 and 2 remain supported for recovery.
`MARE_APP_VERSION` may identify a deployment release; otherwise the workspace
format identifies the application capability. Matching database schema is required
for web replacement. Install a compatible release first; upgrade an isolated copy
of older data before exporting a replacement for a newer schema.

The one upload field auto-inspects new archives, supported legacy installation
ZIPs, Export All versions, and single-case RAW packages. Enter the passphrase
before choosing an encrypted file. Invalid archives cannot enable Import. Legacy
formats receive limitations in preview; absent newer sections are not treated as
deletions. Incomplete historical archives are not complete recovery snapshots.
The offline `scripts/restore_installation.py` remains available for legacy
installation ZIPs; it does not decrypt the new envelope.

Inspection stages and validates without changing application records. Operational
preview/job/audit records may be created. It checks paths, links, entry/size limits,
hashes, database integrity, relationships, compatibility and an accessible active
administrator. Complete preview includes the account used for completion handoff.
Defaults: 1 GiB upload, 2 GiB expanded data, 256 MiB individual content files/case
ZIPs, 64 MiB metadata, and existing archive entry/case limits. Large installations
must plan compatible limits and reverse-proxy capacity; archives beyond these
bounds fail rather than silently omit data. Keep enough free disk space for the
archive, extraction, current destination and retained rollback copy.

Merge preserves unrelated data and uses stable identities. A matching name with a
different tag identity requires an explicit verified mapping. Family uniqueness or
content conflicts permit keeping the destination and skipping the incoming family;
reconcile source/destination profiles separately to import conflicting content.
Case synchronization exposes its supported keep/replace/new decisions. Renamed
identity conflicts require reconciliation in the application. Accepted tag aliases
are persisted for idempotent repeated imports. Missing sections never delete data.
Source historical case numbers remain reserved and allocation advances safely.

Each resolution regenerates the preview. Archive/options changes invalidate it.
Import checks the exact archive/payload hash and destination state; changes require
a fresh preview. Shared records apply transactionally and cases use the established
per-case staged-file recovery journals. An interrupted multi-case merge can have
completed cases: results distinguish partial failure; inspect again before retrying.
There is no unsafe whole-batch success claim or unsupported cancellation.

## Fresh-install disaster recovery

1. Install the compatible application source and dependencies. Provision host
   services/configuration, environment secrets, service ownership and writable data
   **and parent directory**. Start a clean instance and create a bootstrap admin.
2. Sign in, open Settings → Import & Export → Import archive, enter the backup passphrase and
   select the complete archive. Wait for automatic validation.
3. Review coverage, compatibility, file counts, restored administrator identity and
   replacement warning. Resolve blockers. Check the replacement acknowledgment and
   select **Import**. No second confirmation dialog follows.
4. Existing requests drain within the maintenance boundary. The archive is validated
   again into fresh staging; files/database publish under an exclusive cross-process
   lock. Previous sessions are invalidated even with an environment signing key.
5. Sign in with a restored active administrator's credentials. Completion details are
   available on the Import tab. Verify cases, settings and report downloads. The
   bootstrap account is replaced by the source snapshot.

Jobs run outside the request and persist owner-scoped status across reloads. All
status, preview, upload, apply and download routes require authorization; mutations
require CSRF. Archive files are never served from public data paths. Audit contains
operation/job identity, not archive contents. Samples/scripts/macros never execute.

HTTP mutations and background indexing participate in maintenance/snapshot locks.
Run all application workers on the same local filesystem supporting `flock` and
atomic rename; external writers must be stopped. Avoid simultaneous deployments or
manual data edits. Backup jobs serialize operations and refuse active analysis jobs.

A private sibling `.mare-backup-work-<directory-hash>` stores jobs, locks and the
replacement journal. Journal intent is flushed before each rename. Publication
failure rolls back; startup performs interrupted rollback **before database
initialization**. A committed previous destination is retained privately for 24
hours, then removed on a subsequent cleanup/request/startup. Keep normal independent
backups; this retention is not archival storage. On disk failure, stop the service
and preserve the data directory and sibling workspace together before repair.
Interrupted jobs fail honestly rather than replaying a lost passphrase. Abandoned
uploads/staging expire after 24 hours and are cleaned on subsequent activity/startup.

## Extending data areas

`backup_areas.py` defines labels, availability, real count queries, dependencies,
formats and shared export/validation/import services. Add a registry entry and
portable stable-identity validation/mapping to the shared payload service; test
isolated transfers, conflicts and repeated merges before enabling its checkbox.
Complete snapshots already include every durable table/file even without a row.
Do not enable Threat actor profiles until its persistence and portable handlers
exist. Change the envelope version for incompatible format changes.

Threat Actor dependency and unavailable-reference conflict handling is documented
in [Threat Actors](threat-actors.md). Shared actor/family imports commit their
records and report publications together. Older archives without actors do not
clear destination actor data.
