# Offline MISP attribute-type catalog

`describeTypes.json` is the unmodified `pymisp/data/describeTypes.json` from
**PyMISP 2.5.34.4** (194 types). `SOURCE.json` records the source release and exact
file SHA-256. `LICENSE` retains the upstream BSD-2-Clause notice. These are MISP
attribute types, not MISP object templates or STIX object types. No runtime
PyMISP dependency or network fetch is needed.

To update, obtain an explicitly pinned official wheel on a connected build
machine, verify its publisher/hash against PyPI, then run the offline extractor:

```sh
python3 -m pip download --no-deps --only-binary=:all: pymisp==2.5.34.4 -d /tmp/mare-misp-catalog
python3 scripts/update_indicator_catalog.py /tmp/mare-misp-catalog/pymisp-2.5.34.4-py3-none-any.whl --expected-version 2.5.34.4
```

For a newer release, change both pinned versions. Review the JSON/source/license
diff. Review new entries' capabilities/help in `indicator_types.py`; new types
are storage-only until explicitly verified for export. Update catalog version/count
assertions and README, and run catalog, STIX, CSV, API, backup/sync and browser
regressions. Do not replace the definitions automatically during Flask startup.
