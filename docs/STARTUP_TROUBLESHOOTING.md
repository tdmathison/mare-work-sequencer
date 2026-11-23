# Startup, Python environments and importlib_resources

MWS supports Python 3.10+ and uses Flask/WSGI. Its application object is `app:app`
in the repository's `app.py`. `app.main:app` addresses a package/module structure
that this repository does not have. The root and `sdk/` pyproject.toml files package
the standalone Python SDK; installing that SDK alone does not install MWS server
dependencies. Install the server's `requirements.txt`.

## Normal local startup

Run these commands from the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app create-admin
.venv/bin/python -m flask --app app run --host 127.0.0.1 --port 8000
```

Use `python3.10` or a newer supported interpreter instead of `python3.11` when
appropriate. Explicit `.venv/bin/python` paths avoid accidentally using a globally
installed `pip`, `flask` or `uvicorn`. Existing data and accounts do not need to be
recreated, and an existing installation does not need another create-admin run.

For optional Uvicorn use:

```bash
.venv/bin/python -m pip install 'uvicorn==0.38.0'
.venv/bin/python -m uvicorn app:app --interface wsgi --host 127.0.0.1 --port 8000
```

The explicit WSGI interface is required because the app is not ASGI. Uvicorn's
native WSGI middleware is deprecated; use Flask for local development and the
existing Gunicorn deployment for production. Uvicorn is not a required MWS
server dependency. If desired, add `--reload` to the development command only.
Use loopback for local verification; keep production behind the configured proxy.

## Why the reported files() exception occurred

The reported macOS Python 3.11 installation reproduced this exact chain:

```text
misp_stix_converter -> STIX dependencies -> setuptools -> pycountry
    -> importlib_resources.files(...) -> AttributeError
```

The global `uvicorn` script used the global Python interpreter, outside the MWS
virtual environment. That global environment had no installed `importlib-resources`
distribution. Importing setuptools extended sys.path with its `_vendor` directory,
which contained an orphan `importlib_resources/` directory holding only
`__pycache__`. It was not listed among setuptools' installed distribution files.
Python imported that directory as a namespace package: `__file__` was None, the
loader was NamespaceLoader, and there were no exported functions, including files.

pycountry 24.6.1 prefers any importable `importlib_resources` module. It falls back
to Python's working standard-library `importlib.resources` only when importing the
backport raises ModuleNotFoundError. A successfully imported empty namespace does
not trigger that fallback, so Python 3.11's stdlib implementation did not help.
`pip check` reported no dependency problems because pycountry declares the backport
only for Python <3.9; it cannot diagnose this orphan directory/import-order issue.

The MWS .venv contained a complete importlib-resources 7.1.0 distribution and the
converter imported correctly there. No repository-local shadow module was found.
This was a wrong-environment plus stale-vendor-namespace problem, not evidence
that the project .venv's installed backport was outdated or corrupted. Other
machines with the same exception should inspect their actual module paths rather
than assume the same origin.

MWS now explicitly requires `importlib-resources>=5.13`, unconditionally. A real
installed package wins over this empty vendor namespace. This lower bound follows
the compatible backport family already required by pycountry on older Python
(>5.12.0). It supports MWS's Python 3.10 minimum; pip selects releases compatible
with the chosen interpreter. No third-party source changes, converter monkeypatches
or indicator export changes are needed.

## Diagnose and repair the intended environment

```bash
.venv/bin/python -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
.venv/bin/python -m pip show importlib-resources pycountry misp-stix setuptools
.venv/bin/python -m pip check
.venv/bin/python -c "import importlib_resources; print(importlib_resources.__file__); print(importlib_resources.files('pycountry'))"
.venv/bin/python -c "from misp_stix_converter import MISPtoSTIX21Parser; print(MISPtoSTIX21Parser.__name__)"
```

Install the corrected requirements in that same environment:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

If the real installed backport itself is damaged, reinstall only that package:

```bash
.venv/bin/python -m pip install --upgrade --force-reinstall --no-cache-dir 'importlib-resources>=5.13'
```

If the resolved module path points to a local `importlib_resources.py` or a local
directory of that name, rename the unintended shadow module before retrying.
Do not edit pycountry or setuptools source, remove resources from a shared global
installation, or run sudo pip as an application repair.

## Clean environment without deleting data or the old venv

Retain the old environment while verifying a replacement:

```bash
python3.11 -m venv .venv-clean
.venv-clean/bin/python -m pip install --upgrade pip
.venv-clean/bin/python -m pip install -r requirements.txt
.venv-clean/bin/python -m pip check
.venv-clean/bin/python -c "import importlib_resources; print(importlib_resources.files('pycountry'))"
.venv-clean/bin/python -c "from misp_stix_converter import MISPtoSTIX21Parser; print(MISPtoSTIX21Parser.__name__)"
.venv-clean/bin/python -m flask --app app run --host 127.0.0.1 --port 8000
```

Use the intended MARE_DATA_DIR for an existing installation. For a smoke test that
must not touch existing application data, set MARE_DATA_DIR to an empty temporary
directory. Stop the smoke-test server when finished. If using optional Uvicorn,
install it with `.venv-clean/bin/python -m pip install 'uvicorn==0.38.0'` and start
it with `.venv-clean/bin/python -m uvicorn app:app --interface wsgi --host 127.0.0.1 --port 8000`.
Update your IDE interpreter and run configuration to the verified environment.
Do not move a venv between paths; recreate it at its final path before deployment.

## Package versions observed during diagnosis

| Package | Project .venv | Global Python used by bare uvicorn |
|---|---|---|
| Python | 3.11.5 | 3.11.5 |
| importlib-resources | 7.1.0 (working) | Not installed; orphan namespace found during converter import |
| pycountry | 24.6.1 | 24.6.1 |
| misp-stix | 2026.10.12 | 2026.10.12 |
| pymisp | 2.5.34.4 | 2.5.34.4 |
| setuptools | 84.0.0 | 84.2.1 |
| uvicorn | Not installed | 0.38.0 |

misp-stix requires Python >=3.10,<4, pycountry >=24.6.1,<25 and setuptools >=83.
pycountry requires Python >=3.8 and declares importlib-resources >5.12.0 only for
Python <3.9. The SDK continues to require Python >=3.10 and has no backend package
dependency changes. Python versions other than 3.11 were not available locally
for execution testing.

References: [importlib_resources history](https://importlib-resources.readthedocs.io/en/latest/history.html)
(documents the files API and release Python requirements). The dependency markers
and runner behavior above were also inspected directly in the installed package
metadata/source.

## Validation executed for this fix

A fresh disposable Python **3.11.5** venv installed the complete server requirements,
optional Uvicorn **0.38.0**, and the requirement's minimum backport version
**5.13.0**. It resolved pycountry **24.6.1**, misp-stix **2026.10.12**, PyMISP
**2.5.34.4**, and setuptools **84.2.1**. `python -m pip check` passed both in this
clean venv and the existing project venv.

Executed import checks in both environments:

```bash
python -c "import importlib_resources; print(importlib_resources.files('pycountry'))"
python -c "from misp_stix_converter import MISPtoSTIX21Parser; print(MISPtoSTIX21Parser.__name__)"
```

Both imports passed with backport 7.1.0 in the project venv and 5.13.0 in the clean
venv. The original `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
was also executed in the clean venv and failed as expected with
`Could not import module "app.main"`, independently confirming the wrong entry
point after resolving the dependency import problem.

The corrected command was actually launched in the clean venv with temporary
MARE_DATA_DIR, on loopback port 8000:

```bash
python -m uvicorn app:app --interface wsgi --host 127.0.0.1 --port 8000
```

Startup succeeded. HTTP checks returned login 200, root 302 followed by login 200,
static CSS 200, and unauthenticated API 401. The server was shut down after the
probe. Its expected `ASGI 'lifespan' protocol appears unsupported` message reflects
the WSGI application's lack of ASGI lifespan handling, not a startup failure.

The existing indicator suite was executed with the fresh converter environment
selected for optional official round trips:

```bash
MARE_MISP_PYTHON=/tmp/mws-resources-validation/bin/python .venv/bin/python -m pytest -q tests/test_indicators.py tests/test_indicator_bulk.py tests/test_indicator_catalog.py tests/test_indicator_stix.py tests/test_indicator_export_coverage.py --disable-warnings
```

Result: **150 passed**. Before enabling that optional environment, the same suite
had **147 passed, 3 skipped**. No converter implementation, Case Impact source,
SDK dependency manifest, global Python package source, or application entry-point
shim was changed. The validation venv is disposable; use your own venv path when
repeating the checks. Only Python 3.11.5 was executed; compatibility with other
supported versions follows the existing project and dependency Python requirements
and was not execution-tested here.
