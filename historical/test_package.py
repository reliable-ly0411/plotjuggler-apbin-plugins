import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('package', Path(__file__).with_name('package.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_tooling_source_uses_exact_event_commit(self):
        with patch.dict('os.environ', {'GITHUB_SHA': 'a'*40}):
            self.assertEqual(m.tooling_source(), 'a'*40)
        with patch.dict('os.environ', {'GITHUB_SHA': 'main'}):
            with self.assertRaises(ValueError):m.tooling_source()
    def test_host_cache_identity(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'PJ_INSTALL':tmp}):
            p=Path(tmp)/'.apbin-host-source.json'
            good={'repository':'PlotJuggler/PlotJuggler','tag':'3.9.2','commit':'d115b540c4f2664259a594259b9e11595f0263fc'}
            p.write_text(json.dumps(good));self.assertEqual(m.host_source(),good)
            good['commit']='b'*40;p.write_text(json.dumps(good))
            with self.assertRaises(ValueError):m.host_source()
    def test_original_asset_names(self):
        for variant in ('no_units', 'with_units'):
            self.assertEqual(m.asset_name('v1.0.0', 'ubuntu-22.04', variant), f'libDataAPBin_{variant}_v1.0.0.so')
            self.assertEqual(m.asset_name('v1.1.0', 'ubuntu-22.04', variant), f'libDataAPBin_{variant}.so')
        self.assertEqual(m.asset_name('v1.1.0', 'windows-2022', 'no_units'), 'DataAPBin_no_units.dll')
    def test_unsupported_matrix_rejected(self):
        for args in [('v1.0.0', 'windows-2022', 'no_units'), ('v1.1.0', 'windows-2022', 'with_units'), ('v1.2.0', 'ubuntu-22.04', 'no_units'), ('v1.1.0', 'macos', 'no_units'), ('v1.1.0', 'ubuntu-22.04', 'with_units_rcou')]:
            with self.assertRaises(ValueError): m.asset_name(*args)
if __name__ == '__main__': unittest.main()
