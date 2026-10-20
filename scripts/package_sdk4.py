#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Package the already-built SDK4 shared library with its required sidecars."""
import argparse
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate_built_manifest(source, built):
    # SDK 0.34.1 adds these reviewed ABI-family fields at configure time.
    expected = dict(source, abi_major=5, family='data_source')
    if built != expected:
        raise ValueError('Built manifest differs from the source plus reviewed SDK ABI fields')


def package(build, platform, out, verify_dir):
    version = (ROOT / 'VERSION').read_text().strip()
    manifest = json.loads((ROOT / 'sdk4/manifest.json').read_text())
    if manifest.get('license') != 'LGPL-3.0-only':
        raise ValueError('Source manifest must retain the reviewed upstream LGPLv3 scope')
    if manifest['version'] != version:
        raise ValueError('Source manifest/release version mismatch')
    library = 'ardupilot_source_plugin.dll' if platform == 'windows' else 'libardupilot_source_plugin.so'
    sidecar = 'ardupilot_source_plugin.pjmanifest.json'
    files = {library: build / library, sidecar: build / sidecar,
             'README.md': ROOT / 'sdk4/README.md',
             'licenses/LICENSE': ROOT / 'sdk4/LICENSE',
             'licenses/COPYING.GPL3': ROOT / 'sdk4/COPYING.GPL3',
             'licenses/LICENSE.APACHE2': ROOT / 'sdk4/LICENSE.APACHE2',
             'licenses/UPSTREAM.md': ROOT / 'sdk4/UPSTREAM.md'}
    for notice in sorted((ROOT / 'sdk4/licenses').glob('*.txt')):
        files['licenses/third-party/' + notice.name] = notice
    if len([name for name in files if name.startswith('licenses/third-party/')]) != 4:
        raise ValueError('SDK/dependency copyright notices are incomplete')
    validate_built_manifest(manifest, json.loads(files[sidecar].read_text()))
    source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    provenance = {'repository': 'https://github.com/reliable-ly0411/plotjuggler-apbin-plugins',
                  'source_commit': source_sha,
                  'upstream_repository': 'https://github.com/ArduPilot/plotjuggler-apbin-plugins',
                  'upstream_commit': '3e2f9253adc2d41e17b2f0fec74f4b2487c42fb0',
                  'upstream_release_tag': 'v1.1.0',
                  'upstream_release_commit': '399136d91394fc838e813147438e822d8418233c',
                  'plugin_version': version, 'platform': platform,
                  'plugin_license': 'LGPL-3.0-only',
                  'architecture': 'x86_64', 'sdk_version': '0.34.1',
                  'sdk_commit': '4d59e7de81455afe73a77051075e8fb4b9f6b0fd',
                  'boot_abi': 5, 'data_source_protocol': 4}
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'ardupilot_source_plugin-v{version}-sdk0.34.1-{platform}-x86_64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in sorted(files.items()):
            z.writestr(name, path.read_bytes())
        z.writestr('SOURCE.json', json.dumps(provenance, indent=2) + '\n')
    # This exact final archive is unpacked for the native ABI test; publication
    # promotes it without rebuilding, re-signing, or repacking.
    with zipfile.ZipFile(archive) as z:
        z.extractall(verify_dir)
    for name, path in files.items():
        if (verify_dir / name).read_bytes() != path.read_bytes():
            raise ValueError('ZIP roundtrip changed ' + name)
    print(archive)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--platform', choices=['windows', 'linux-ubuntu22.04'], required=True)
    p.add_argument('--out', type=Path, default=Path('dist'))
    p.add_argument('--verify-dir', type=Path, default=Path('package-verify'))
    a = p.parse_args()
    package(a.build, a.platform, a.out, a.verify_dir)
