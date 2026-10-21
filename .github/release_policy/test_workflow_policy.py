"""Regression guards for sync-only automatic paths and immutable promotion."""
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
CONFIG=json.loads(Path(__file__).with_name('config.json').read_text())

def workflow(name):return (ROOT/'.github/workflows'/name).read_text()
def events(name):return re.search(r"^'?on'?\s*:[\s\S]*?(?=^[A-Za-z][A-Za-z_-]*:)",workflow(name),re.M).group()

class WorkflowPolicyTests(unittest.TestCase):
    def test_release_callers_pass_only_required_read_permissions(self):
        # GitHub validates reusable-workflow permissions before evaluating job if.
        # Keep Actions access on the callers, not the source-sync workflow default.
        text = workflow('sync-upstream.yml')
        default = re.search(r'^permissions:\n((?:  [^\n]+\n)+)', text, re.M)
        self.assertIsNotNone(default)
        self.assertEqual(default.group(1), '  contents: read\n')
        jobs = dict(re.findall(
            r'^  ([a-zA-Z0-9_-]+):\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)',
            text.split('\njobs:\n', 1)[1], re.M | re.S))
        expected = (['build'] if CONFIG['upstream'].startswith('Titan-')
                    else ['build-main', 'build-sdk4'])
        callers = {name: body for name, body in jobs.items()
                   if 'uses: ./.github/workflows/release-build.yml' in body}
        self.assertEqual(set(callers), set(expected))
        for name, body in callers.items():
            with self.subTest(job=name):
                permissions = re.search(r'^    permissions:\n((?:      [^\n]+\n)+)', body, re.M)
                self.assertIsNotNone(permissions, 'caller must allow evidence artifact reads')
                self.assertEqual(permissions.group(1),
                                 '      contents: read\n      actions: read\n')
                dependency = 'sync' if name == 'build' else 'detect-' + name.removeprefix('build-')
                self.assertIn("if: needs." + dependency + ".outputs.build == 'true'", body)
        evidence = workflow('release-build.yml').split('  evidence:\n', 1)[1]
        self.assertIn('    permissions:\n      contents: read\n      actions: read\n', evidence)

    def test_native_workflows_have_no_automatic_entrypoint(self):
        for name in CONFIG['heavy_workflows']:
            with self.subTest(name=name):
                text=events(name)
                self.assertIn('workflow_dispatch:',text)
                for forbidden in ['push:','pull_request:','schedule:','workflow_run:','repository_dispatch:','release:']:
                    self.assertNotIn(forbidden,text)
    def test_release_builds_materialize_pinned_source(self):
        for name in CONFIG['automatic_workflows']:
            text=workflow(name)
            with self.subTest(name=name):
                self.assertIn('workflow_call:',text)
                self.assertIn('RELEASE_MANIFEST: ${{ inputs.release_manifest }}',text)
                self.assertIn('python3 .github/release_policy/policy.py materialize',text)
                self.assertIn('ref: ${{ inputs.source_ref || github.sha }}',text)
                self.assertIn('fetch-depth: 0',text)
    def test_daily_sync_default_manual_sync_and_no_cancel(self):
        text=workflow('sync-upstream.yml')
        self.assertIn('default: sync',text)
        self.assertIn("github.event_name == 'schedule' || inputs.action == 'check-releases'",text)
        self.assertIn('cancel-in-progress: false',text)
        self.assertNotIn('workflow_run:',text)
        self.assertNotIn('gh release',text)
    def test_exact_manual_promote_does_not_build(self):
        name='promote-release.yml' if CONFIG['upstream'].startswith('Titan-') else 'release.yml'
        text=workflow(name)
        self.assertIn('workflow_dispatch:',events(name))
        for command in ['cmake --build','dotnet build','materialize','--clobber']:
            self.assertNotIn(command,text)
        self.assertIn('ref: ${{ github.workflow_sha }}',text)
        self.assertIn('path: policy',text)
        self.assertIn('path: source',text)
        self.assertIn('candidate_run:',text)
        self.assertIn('source_sha:',text)
        text=workflow('verify-release-candidate.yml')
        self.assertIn('evidence.py verify',text)
        self.assertIn('exit 1',text)
    def test_ordinary_checks_are_lightweight(self):
        name='policy-checks.yml' if CONFIG['upstream'].startswith('Titan-') else 'release-checks.yml'
        text=workflow(name)
        self.assertIn('push:',events(name));self.assertIn('pull_request:',events(name))
        self.assertIn('.github/release_policy',text)
        for command in ['dotnet','cmake','conan','gh release']:
            self.assertNotIn(command,text)
    def test_titan_source_checks_use_candidate_not_base(self):
        if not CONFIG['upstream'].startswith('Titan-'):return
        text=workflow('sync-upstream.yml')
        self.assertIn('git checkout --detach "$SOURCE_SHA"',text)
        self.assertIn('scripts/localization/verify_zh_hans.py',text)
        native=workflow('main.yml')
        for required in ['test_windows.ps1','check_audit.py','test_msi.py','-Configuration Debug','receipt.py']:
            self.assertIn(required,native)
    def test_apbin_line_isolation_and_native_abi_checks(self):
        if not CONFIG['upstream'].startswith('ArduPilot/plotjuggler'):return
        text=workflow('sync-upstream.yml')
        for line in ['main','sdk4']:
            self.assertIn("if: needs.detect-"+line+".outputs.build == 'true'",text)
        guard=(ROOT/'scripts/sync_upstream.py').read_text()
        self.assertIn('Synchronization is restricted to the upstream-following main branch',guard)
        self.assertNotIn('  release:\n',workflow('build.yml'))
        sdk=workflow('sdk4.yml')
        for required in ['4d59e7de81455afe73a77051075e8fb4b9f6b0fd','-DPJ_WARNINGS_AS_ERRORS=ON','package-verify/','-fsanitize=address,undefined','receipt.py']:
            self.assertIn(required,sdk)
        self.assertIn('d115b540c4f2664259a594259b9e11595f0263fc',workflow('build.yml'))
    def test_baseline_ids_are_seeded_without_backfill(self):
        self.assertTrue(CONFIG['baseline'])
        for record in CONFIG['baseline'].values():
            self.assertIn(record['status'],['baseline','prerelease'])
            self.assertRegex(record['upstream_sha'],r'^[0-9a-f]{40}$')

if __name__=='__main__':unittest.main()
