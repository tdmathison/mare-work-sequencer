# Ubuntu 26.04 LTS: MWS alongside DropZone

DropZone already listens on 127.0.0.1:8000, and an existing Nginx HTTPS server
uses a self-signed certificate on port 443. Preserve its server block, certificate
settings, and `location /`. This guide adds MWS on 127.0.0.1:8001 at `/mws/`.
No new public port, Docker, database schema change, or DropZone change is required.

## Mount and trust contract

`MWS_BASE_PATH` defaults to empty (root deployment). `/` means empty; a trailing
slash is removed. Multi-segment prefixes such as `/team/analysis` work too.
Prefixes must consist of slash-separated ASCII letters, digits, `_`, `~`, `.`,
and `-`. Empty segments, dot segments, escapes, URLs, whitespace, queries and
fragments are rejected at startup. See `deploy/mws.env.example`.

Nginx strips the prefix with the trailing slash in `proxy_pass`. Thus public
`/mws/cases/1?tab=report` becomes internal `/cases/1?tab=report`. The application
sets WSGI `SCRIPT_NAME=/mws` from startup configuration and leaves `PATH_INFO`
unchanged. There is no Blueprint mount prefix. Flask `url_for`, redirects,
static files, API docs, and explicit frontend URL constructors use that mount.
Frontend `MWS.path()` constructs known internal routes; `MWS.url()` also accepts
already mounted URLs. Known internal paths use the explicit constructor so a
mount such as `/cases` works even though it matches an application route stem.
Do not set Gunicorn `SCRIPT_NAME`, add a route prefix, or forward an unstripped
path. `/mws` is canonicalized to `/mws/` by Nginx with a 308 and preserves queries.

`MWS_TRUSTED_PROXIES` defaults to empty. Set it to `127.0.0.1/32` for this single
local Nginx hop. Only an immediate peer in that list may supply one forwarded
client IP and scheme. Werkzeug ProxyFix uses `x_for=1`, `x_proto=1`, `x_prefix=1`,
`x_host=0`, `x_port=0`. The configured mount overrides the forwarded prefix even
from a trusted peer; a client cannot select another mount. Nginx overwrites
scheme/prefix and supplies Host directly. Disable Gunicorn's separate forwarded
header handling as shown below. Only list actual proxy addresses, never all IPs.
Loopback clients are within this trust boundary; do not share it with untrusted
local users. With empty MWS_BASE_PATH, a WSGI server-provided SCRIPT_NAME remains
supported; HTTP forwarded prefix headers cannot set it arbitrarily.

The session cookie is `mws_session` with Path `/mws` (Path `/` at root), HttpOnly,
SameSite=Lax, and Secure when MARE_SECURE_COOKIES=1. Deployments previously using
Flask's `session` cookie require users to sign in again. DropZone cookies are
untouched. Confirm DropZone does not independently use the name `mws_session`.

## Install code and dependencies

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential git nginx curl libreoffice-writer
sudo useradd --system --user-group --home-dir /var/lib/mws --shell /usr/sbin/nologin mws
sudo install -d -o root -g root -m 0755 /opt/mws
sudo install -d -o mws -g mws -m 0700 /var/lib/mws /var/lib/mws/data
sudo install -d -o root -g mws -m 0750 /etc/mws
```

Copy the reviewed MWS release into `/opt/mws`, including committed static/vendor
assets and vendor applications. Use your organization's repository or release
archive; do not include another installation's `data/` or `.venv/`. Keep source
root-owned and readable by mws. The runtime uses SQLite, not SQLAlchemy or a
separate database service. LibreOffice provides Word-to-PDF conversion. Optional
YARA/Snort engines retain their existing installation instructions.

```bash
sudo python3 -m venv /opt/mws/.venv
sudo /opt/mws/.venv/bin/pip install -r /opt/mws/requirements.txt
sudo install -o root -g mws -m 0640 /opt/mws/deploy/mws.env.example /etc/mws/mws.env
sudoedit /etc/mws/mws.env
```

Set the production environment file to:

```ini
MWS_BASE_PATH=/mws
MWS_TRUSTED_PROXIES=127.0.0.1/32
MARE_SECURE_COOKIES=1
MARE_DATA_DIR=/var/lib/mws/data
```

The generated `/var/lib/mws/data/session.key` is persistent; back it up and keep
it private. Alternatively set a persistent random MARE_SECRET_KEY in the protected
environment file. Data, SQLite journals and report output must be writable by mws.
The backup implementation also writes `.mare-backup-work-*` beside the data
directory, which is why the service permits writes throughout `/var/lib/mws`.

Create the first administrator using the existing interactive command:

```bash
cd /opt/mws
sudo -u mws env MARE_DATA_DIR=/var/lib/mws/data /opt/mws/.venv/bin/python -m flask --app app create-admin
```

If rebuilding frontend assets from source, run `npm ci` and
`npm run build:editors` in a build checkout with a supported Node version before
installing the release. Node is not needed by the running service.

## Install systemd service

```bash
sudo install -m 0644 /opt/mws/deploy/mws-subpath.service /etc/systemd/system/mws.service
sudo systemctl daemon-reload
sudo systemctl enable --now mws
sudo systemctl status mws
sudo ss -ltnp 'sport = :8001'
```

The supplied service runs one Gunicorn worker with four threads on loopback:

```ini
[Service]
User=mws
Group=mws
WorkingDirectory=/opt/mws
EnvironmentFile=/etc/mws/mws.env
ExecStart=/opt/mws/.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8001 --forwarded-allow-ips= app:app
```

Use the full supplied service for filesystem hardening and restart behavior.
Never bind this listener to 0.0.0.0. Only port 443 needs external access.

## Extend the existing HTTPS Nginx server

Save a copy of the existing enabled site configuration first. Inside its existing
HTTPS `server { ... }`, add the contents of `deploy/nginx-subpath.conf`:

```nginx
location = /mws {
    return 308 /mws/$is_args$args;
}
location ^~ /mws/ {
    client_max_body_size 100m;
    proxy_pass http://127.0.0.1:8001/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /mws;
    proxy_read_timeout 300s;
}
```

`^~` prevents a pre-existing static-file regex from capturing MWS assets. Leave
DropZone's `/` location forwarding to 8000. Do not replace the HTTPS server block
or its certificate directives. Adjust timeouts for unusually long operations.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Reload only after validation succeeds. No Nginx restart is needed.

## Verify and troubleshoot

Substitute the actual server address for SERVER_IP:

```bash
curl -kI https://SERVER_IP/mws
curl -kI 'https://SERVER_IP/mws?check=1'
curl -kI https://SERVER_IP/mws/login
curl -kI https://SERVER_IP/mws/static/mws-url.js
curl -kI https://SERVER_IP/
sudo journalctl -u mws -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

Use `-k` only for the self-signed verification above; configure certificate trust
for normal clients. Expect 308 to `/mws/`, a login page/static file returning 200,
and unchanged DropZone behavior. Sign in, create/edit a case, upload/download an
artifact, preview/upload a report image, save Markdown, open API/SDK docs and the
YARA/Snort tools. In browser Network, verify every MWS request stays under `/mws/`
and no request fails unexpectedly. Confirm logout and password changes.

A direct internal `http://127.0.0.1:8001/login` receives the stripped route and
produces links under `/mws/`. It is a diagnostic endpoint, not a browsable
standalone deployment: following `/mws/login` directly sends an unstripped route
and normally returns 404. Secure cookies require the public HTTPS endpoint.
Normal development needs no Nginx: omit MWS_BASE_PATH and MWS_TRUSTED_PROXIES,
leave MARE_SECURE_COOKIES=0, and run `flask --app app run --host 127.0.0.1 --port 8001`.

404s for prefixed internal requests mean the proxy did not strip the prefix.
Double prefixes usually indicate an additional server/Blueprint mount. Root asset
requests indicate stale frontend files: rebuild/deploy assets and refresh caches.
HTTP external URLs indicate missing trusted proxy configuration or forwarded
scheme. 502 means check service status and loopback listener. 413 means compare
Nginx's upload limit with Flask's 100 MiB limit. Permission errors often involve
SQLite journals or the sibling backup workspace, not only the database file.

## Backups, upgrades and rollback

Use the existing encrypted installation backup workflow; store backups outside
this server and retain their passwords separately. Include data/session.key (or
the environment secret), protected environment file, release identifier and local
service/Nginx configuration. For a filesystem snapshot, stop MWS first and copy
the entire data directory consistently, including SQLite journals; do not copy a
live database file alone. DropZone can stay running throughout.

Before upgrading, create and verify a restorable backup, save the current release
and environment, then stop only `mws`. Install the reviewed new release, recreate
its virtual environment if its path changed, preserve `/var/lib/mws`, restart
MWS and run the checks above. For rollback, stop MWS and restore the previous code
and dependencies. If the intervening release migrated data, restore the matching
pre-upgrade data snapshot as well (this base-path change adds no schema migration).
Reapply ownership, start MWS, and verify. Nginx needs no reload unless its
configuration changed; validate before any reload.

## Return to root deployment

Set MWS_BASE_PATH empty and restart MWS. Mount it at `/` on a separate hostname or
HTTPS server block, using `proxy_pass http://127.0.0.1:8001/` and an empty forwarded
prefix. Do not take over DropZone's existing `/` on the shared host. Remove only
the MWS location blocks from that host if no longer needed, validate and reload
Nginx. Existing MWS sessions may need a fresh login after cookie path changes.

## Validation scope and references

Automated tests exercise real Flask handlers through the stripped-path WSGI
contract at root and multiple prefixes, including spoofed forwarded headers,
cookies, redirects, assets and uploads. The browser regression uses a local proxy
simulator; production `nginx -t`, TLS and Ubuntu service validation must be run on
the target host. This development environment does not include Nginx/systemd.

Proxy semantics: [Nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
Header trust: [Werkzeug ProxyFix](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/).
