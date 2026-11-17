#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-only
"""Download immutable Windows release bytes and their pinned ABI test sources."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request
import zipfile

REPOSITORY = 'https://github.com/reliable-ly0411/plotjuggler-apbin-plugins'
PACKAGES = {
    '1.2.0-pj4.rc.1': {
        'size': 178930,
        'sha256': '213fcaa87b30a46aa304a7ebcf4ef28fba27bee25e621504e45ee24f105ab0a5',
        'source_commit': '0cc7cc10a25af3cb2ab122861b9be4fc01c99da5',
        'test_commit': '0cc7cc10a25af3cb2ab122861b9be4fc01c99da5',
        'test_sha256': '1f0b260719dcc4be64a3c3e982c5ad124c540b7e38f42cbfa5d4ce4cfc51e2f9',
    },
    '1.3.0-pj4.rc.1': {
        'size': 179286,
        'sha256': '9a6497066589dcd7aa6558e8f81a905573fc0af1be4859ed62f47895ad49e7e0',
        'source_commit': '55f75c4214deabda952b9114c7cb4c3005593158',
        'test_commit': '90afd65ca21c452d1c1ab87e19d4057f9dfe60e8',
        'test_sha256': '45d09798d6c811f85916ffebe79dd526927ef8d4780fcd7786033c592ff30bda',
    },
}


def checked_file(url, path, digest, offline, size=None):
    if not offline:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest or (size is not None and len(data) != size):
        raise ValueError(f'Original bytes do not match pinned digest/size: {path}')
    return data


def prepare(root, offline=False):
    evidence = []
    for version, expected in PACKAGES.items():
        folder = root / version
        folder.mkdir(parents=True, exist_ok=True)
        filename = f'ardupilot_source_plugin-v{version}-sdk0.34.1-windows-x86_64.zip'
        url = f'{REPOSITORY}/releases/download/v{version}/{filename}'
        data = checked_file(url, folder / filename, expected['sha256'], offline, expected['size'])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                path = PurePosixPath(entry.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                        or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError(f'Unsafe archive member: {entry.filename}')
            source = json.loads(archive.read('SOURCE.json'))
            manifest = json.loads(archive.read('ardupilot_source_plugin.pjmanifest.json'))
            if (source['source_commit'] != expected['source_commit']
                    or source['plugin_version'] != version or source['sdk_version'] != '0.34.1'
                    or source['sdk_commit'] != '4d59e7de81455afe73a77051075e8fb4b9f6b0fd'
                    or source['boot_abi'] != 5 or source['data_source_protocol'] != 4
                    or manifest['id'] != 'ardupilot-dataflash' or manifest['version'] != version
                    or manifest['abi_major'] != 5 or manifest['min_sdk_required'] != '0.34.1'
                    or manifest['license'] != 'LGPL-3.0-only'):
                raise ValueError(f'Unexpected source/ABI/license metadata: {version}')
            archive.extractall(folder / 'extracted')
        test_url = ('https://raw.githubusercontent.com/reliable-ly0411/plotjuggler-apbin-plugins/'
                    + expected['test_commit'] + '/sdk4/tests/source_test.cpp')
        checked_file(test_url, folder / 'source_test.cpp', expected['test_sha256'], offline)
        evidence.append(dict(version=version, url=url, **expected, manifest=manifest, source=source))
        print(f'PASS original package: {version}, {expected["size"]} bytes, SHA256 {expected["sha256"]}')
    (root / 'verified-packages.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--offline', action='store_true', help='Verify previously downloaded exact files')
    args = parser.parse_args()
    prepare(args.out, args.offline)
