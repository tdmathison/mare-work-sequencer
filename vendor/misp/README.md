# Offline MISP attribute-type catalog

`describeTypes.json` is the unmodified `pymisp/data/describeTypes.json` from
**PyMISP 2.5.34.4** (194 types). `SOURCE.json` records the source release and exact
file SHA-256. `LICENSE` retains the upstream BSD-2-Clause notice. These are MISP
attribute types, not MISP object templates or STIX object types. Runtime conversion uses pinned PyMISP/misp-stix dependencies. No catalog/converter network fetch is needed during Flask startup or requests.

To update, obtain an explicitly pinned official wheel on a connected build
machine, verify its publisher/hash against PyPI, then run the offline extractor:

```sh
python3 -m pip download --no-deps --only-binary=:all: pymisp==2.5.34.4 -d /tmp/mare-misp-catalog
python3 scripts/update_indicator_catalog.py /tmp/mare-misp-catalog/pymisp-2.5.34.4-py3-none-any.whl --expected-version 2.5.34.4
```

For a newer release, change both pinned versions. Review the JSON/source/license
diff and keep the PyMISP runtime pin consistent. Review capabilities/help in `indicator_types.py` and the converter pin/profile in `stix21-capabilities.json`; add each new type to the actual importer round-trip fixture before claiming export support. Update catalog version/count
assertions and README, and run catalog, STIX, CSV, API, backup/sync and browser
regressions. Do not replace the definitions automatically during Flask startup.

`stix21-capabilities.json` records 68 verified native detection-pattern shapes,
two intent-constrained descriptive mappings, the former 165-type gap and exact
upstream limitations. Other valid non-binary attributes use the official contextual
writer. The mandatory fixture in `tests/fixtures/misp_indicator_attributes.json`
covers all 192 non-binary types, not just schema validity. Converter/model/fallback
protected hooks in `misp_indicator_export.py` are coupled to misp-stix 2026.10.12.
Test type/value/comment/UUID/intent retention and no omission on every update.
