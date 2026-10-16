#!/usr/bin/env python3
"""Refresh the bundled catalog from a locally downloaded, version-pinned PyMISP wheel.

This maintenance command reads JSON/license/metadata only; it never installs or
executes the wheel and does not make network requests. Flask never invokes it.
"""
import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel',type=Path)
    parser.add_argument('--expected-version',required=True)
    parser.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1]/'vendor/misp')
    args=parser.parse_args()
    with zipfile.ZipFile(args.wheel) as wheel:
        names=wheel.namelist()
        metadata=next(name for name in names if name.endswith('.dist-info/METADATA'))
        info=Parser().parsestr(wheel.read(metadata).decode())
        if info['Name'].lower()!='pymisp' or info['Version']!=args.expected_version:
            parser.error('Expected the specified PyMISP release; wheel metadata does not match.')
        raw=wheel.read('pymisp/data/describeTypes.json')
        data=json.loads(raw)['result']
        if not isinstance(data['types'],list) or len(set(data['types']))!=len(data['types']) or any(not isinstance(name,str) or name not in data['sane_defaults'] for name in data['types']):
            parser.error('Invalid attribute catalog; no files changed.')
        license_name=next(name for name in names if name.endswith(('.dist-info/licenses/LICENSE','.dist-info/LICENSE')))
        license_data=wheel.read(license_name)
    source=dict(package='pymisp',version=args.expected_version,
                source=f'https://pypi.org/project/pymisp/{args.expected_version}/',
                path='pymisp/data/describeTypes.json',sha256=hashlib.sha256(raw).hexdigest())
    args.destination.mkdir(parents=True,exist_ok=True)
    (args.destination/'describeTypes.json').write_bytes(raw)
    (args.destination/'LICENSE').write_bytes(license_data)
    (args.destination/'SOURCE.json').write_text(json.dumps(source,indent=2)+'\n')
    print(f'Prepared {len(data["types"])} types from PyMISP {args.expected_version}; review capability coverage and run indicator tests.')


if __name__=='__main__':main()
