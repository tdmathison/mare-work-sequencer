#!/usr/bin/env python3
"""Install a checksum-pinned official production bundle; never run at app startup."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

VERSION = '11.5.0'
COMMIT = '8cd426dd4f40f1423912d5fad91b578a86a65112'
SHA256 = 'f6478925d3eaa16ec08626a85f5b85eed10d531a5e18700615fed7ecb024cccf'
URL = f'https://github.com/gchq/CyberChef/releases/download/v{VERSION}/CyberChef_{COMMIT}.zip'
ROOT = Path(__file__).resolve().parents[1]


def install(archive, destination):
    digest = hashlib.sha256()
    with archive.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            digest.update(chunk)
    digest = digest.hexdigest()
    if digest != SHA256:
        raise ValueError('CyberChef archive checksum does not match the pinned release')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)/'dist'
        staging.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (staging/member.filename).resolve()
                if not target.is_relative_to(staging.resolve()) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe archive path')
            bundle.extractall(staging)
        entry = staging/f'CyberChef_v{VERSION}.html'
        if not entry.is_file() or not (staging/'assets/main.js').is_file():
            raise ValueError('Unexpected CyberChef release layout')
        entry.rename(staging/'index.html')
        # Preserve the upstream Download CyberChef control with a local copy.
        shutil.copyfile(archive, staging/f'CyberChef_{COMMIT}.zip')
        # Keep upstream distribution intact except for the entry point filename.
        # Theme injection happens only in the authenticated Flask HTML response.
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    print(f'Installed CyberChef {VERSION} at {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use a previously downloaded ZIP (offline installation)')
    parser.add_argument('--destination', type=Path, default=ROOT/'vendor/cyberchef/dist')
    args = parser.parse_args()
    if args.archive:
        install(args.archive, args.destination.resolve())
    else:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)/'cyberchef.zip'
            print(f'Downloading {URL}')
            urllib.request.urlretrieve(URL, archive)
            install(archive, args.destination.resolve())


if __name__ == '__main__':
    main()
