import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('receipt', Path(__file__).with_name('receipt.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
SHA = 'a' * 40
REPO = 'owner/repo'

def run(**changes):
    data = {'id': 123, 'run_attempt': 1, 'head_sha': SHA, 'head_branch': 'main',
            'path': '.github/workflows/build.yml', 'status': 'completed',
            'conclusion': 'success', 'event': 'workflow_dispatch', 'repository': {'full_name': REPO}}
    data.update(changes); return data

class ReceiptTests(unittest.TestCase):
    def test_manual_success_is_accepted(self):
        r.validate_run(run(), REPO, SHA, 'main', '.github/workflows/build.yml')

    def test_pr_push_other_repo_or_wrong_sha_are_rejected(self):
        for change in [{'event': 'pull_request'}, {'event': 'push'}, {'event': 'schedule'},
                       {'conclusion': 'failure'}, {'head_sha': 'b'*40},
                       {'repository': {'full_name': 'foreign/repo'}}, {'head_branch': 'topic'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                r.validate_run(run(**change), REPO, SHA, 'main', '.github/workflows/build.yml')

    def test_digest_source_attempt_and_target_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'native.dll').write_bytes(b'original tested bytes')
            record = {'schema': 1, 'repository': REPO, 'source_sha': SHA, 'run_id': '123',
                      'run_attempt': '1', 'event': 'workflow_dispatch', 'target': 'windows',
                      'workflow_sha': SHA, 'workflow_ref': REPO+'/.github/workflows/build.yml@refs/heads/main',
                      'files': r.files(root)}
            (root/'provenance.json').write_text(json.dumps(record))
            r.verify(root, run(), SHA, 'windows')
            for field in ['source_sha', 'run_id', 'run_attempt', 'target', 'workflow_sha']:
                changed=dict(record); changed[field]='wrong'; (root/'provenance.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError): r.verify(root,run(),SHA,'windows')
            (root/'provenance.json').write_text(json.dumps(record)); (root/'native.dll').write_bytes(b'rebuilt')
            with self.assertRaises(ValueError): r.verify(root,run(),SHA,'windows')

if __name__ == '__main__': unittest.main()
