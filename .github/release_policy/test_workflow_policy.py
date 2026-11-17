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

    def test_sdk101_compatibility_is_manual_test_only(self):
        name='sdk101-compat.yml'
        self.assertIn('workflow_dispatch:',events(name))
        for forbidden in ['push:', 'pull_request:', 'schedule:']:
            self.assertNotIn(forbidden,events(name))
        text=workflow(name)
        for required in ['ffd749ab343c3211b5100f124f6c873667b82629',
                         'feature_floor_check.py', 'ardupilot_source_test',
                         '-fsanitize=address,undefined', 'contents: read']:
            self.assertIn(required,text)
        for forbidden in ['package_sdk4.py', 'receipt.py', 'gh release', 'contents: write']:
            self.assertNotIn(forbidden,text)
        dispatcher=workflow('sdk4.yml')
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.sdk101_compat",dispatcher)
        self.assertIn('if: ${{ !inputs.sdk101_compat && !inputs.sdk101_packages }}',dispatcher)
        self.assertIn('source_ref: 90afd65ca21c452d1c1ab87e19d4057f9dfe60e8',dispatcher)
        self.assertIn('ref: ${{ inputs.source_ref || github.sha }}',text)

    def test_published_sdk_packages_are_separate_from_source_builds(self):
        text=workflow('sdk101-packages.yml')
        self.assertIn('workflow_call:',events('sdk101-packages.yml'))
        for forbidden in ['push:', 'pull_request:', 'schedule:']:
            self.assertNotIn(forbidden,events('sdk101-packages.yml'))
        self.assertIn('if: github.event_name == \'workflow_dispatch\' && inputs.sdk101_packages && !inputs.sdk101_compat',workflow('sdk4.yml'))
        for required in ['ffd749ab343c3211b5100f124f6c873667b82629',
                         'verify_published_sdk4.py', 'sdk4/tests/published',
                         'published_1.2.0-pj4.rc.1 published_1.3.0-pj4.rc.1', 'contents: read']:
            self.assertIn(required,text)
        for forbidden in ['package_sdk4.py', 'receipt.py', 'gh release', 'contents: write', 'ardupilot_source_plugin --']:
            self.assertNotIn(forbidden,text)

if __name__=='__main__':unittest.main()
