# SPDX-License-Identifier: LGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTest(unittest.TestCase):
    def test_checked_in_metadata(self):
        release.validate_config(ROOT)

    def test_semver_rejects_leading_zero_and_unordered_suffix(self):
        for good in ['1.2.0', '2.0.0-rc.1']:
            self.assertIsNotNone(release.SEMVER.fullmatch(good))
        for bad in ['01.2.0', '2.0.0-rc.01', '2.0', '2.0.0-rc1', 'v1.2.0']:
            self.assertIsNone(release.SEMVER.fullmatch(bad))

    def test_main_exact_six_variants_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'downloads'
            for platform, ext in [('ubuntu-22.04', 'so'), ('windows-2022', 'dll')]:
                for variant in ['plain', 'units', 'units-rcou']:
                    folder = source / f'DataAPBin-{platform}-{variant}' / 'bin'
                    folder.mkdir(parents=True)
                    (folder / f'DataAPBin.{ext}').write_bytes(f'{platform}/{variant}'.encode())
            config = {'line': 'main'}
            assets = root / 'assets'
            hashes = release.collect(config, source, assets)
            self.assertEqual(6, len(hashes))
            self.assertEqual(7, len(list(assets.iterdir())))
            self.assertEqual(b'windows-2022/units-rcou', (assets / 'DataAPBin_with_units_rcou.dll').read_bytes())
            self.assertEqual(b'ubuntu-22.04/plain', (assets / 'libDataAPBin_no_units.so').read_bytes())
            self.assertEqual(6, len((assets / 'SHA256SUMS').read_text().splitlines()))

    def test_main_missing_variant_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                release.collect({'line': 'main'}, Path(d) / 'none', Path(d) / 'assets')

    def test_sdk_packages_are_promoted_without_repacking(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'downloads'
            source.mkdir()
            config = {'line': 'sdk4', 'version': '2.0.0-rc.1'}
            for name in release.expected_assets(config):
                with zipfile.ZipFile(source / name, 'w') as archive:
                    archive.writestr('ardupilot_source_plugin.pjmanifest.json', json.dumps({'version': '2.0.0-rc.1', 'license': 'LGPL-3.0-only'}))
                    archive.writestr('libardupilot_source_plugin.so', b'unchanged tested binary')
            hashes = release.collect(config, source, root / 'assets')
            self.assertEqual(2, len(hashes))
            for name, digest in hashes.items():
                self.assertEqual(digest, release.digest(source / name))

    def test_sdk_manifest_version_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'downloads'
            source.mkdir()
            config = {'line': 'sdk4', 'version': '2.0.0-rc.1'}
            for name in release.expected_assets(config):
                with zipfile.ZipFile(source / name, 'w') as archive:
                    archive.writestr('plugin.pjmanifest.json', json.dumps({'version': '1.0.0-dev.1', 'license': 'LGPL-3.0-only'}))
            with self.assertRaisesRegex(ValueError, 'manifest'):
                release.collect(config, source, root / 'assets')

    def test_sdk_manifest_unverified_later_version_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'downloads'
            source.mkdir()
            config = {'line': 'sdk4', 'version': '2.0.0-rc.1'}
            for name in release.expected_assets(config):
                with zipfile.ZipFile(source / name, 'w') as archive:
                    archive.writestr('plugin.pjmanifest.json', json.dumps({
                        'version': '2.0.0-rc.1', 'license': 'LGPL-3.0-or-later'}))
            with self.assertRaisesRegex(ValueError, 'LGPLv3 scope'):
                release.collect(config, source, root / 'assets')

    def test_built_sdk_manifest_includes_generated_abi_fields(self):
        spec = importlib.util.spec_from_file_location('package_sdk4', ROOT / 'scripts/package_sdk4.py')
        pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack)
        source = json.loads((ROOT / 'sdk4/manifest.json').read_text())
        pack.validate_built_manifest(source, dict(source, abi_major=5, family='data_source'))
        for wrong in [dict(source), dict(source, abi_major=6, family='data_source'),
                      dict(source, abi_major=5, family='parser'),
                      dict(source, abi_major=5, family='data_source', license='LGPL-3.0-or-later'),
                      dict(source, abi_major=5, family='data_source', version='1.0.0-dev.1')]:
            with self.assertRaisesRegex(ValueError, 'reviewed SDK ABI fields'):
                pack.validate_built_manifest(source, wrong)

    def test_metadata_detects_version_disagreement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copy(ROOT / 'release.json', root / 'release.json')
            (root / 'VERSION').write_text('99.0.0\n')
            with self.assertRaisesRegex(ValueError, 'same valid release version'):
                release.validate_config(root)


if __name__ == '__main__':
    unittest.main()
