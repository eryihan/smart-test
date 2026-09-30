import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/smart-test/scripts'
sys.path.insert(0, str(SCRIPTS))
import export_feedback as exporter
PACKAGE_VERSION = json.loads((ROOT / 'skills/smart-test/version.json').read_text())['smart_test_version']


class FeedbackExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'project'
        self.repo.mkdir()
        self.output = self.base / 'feedback'

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, value):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value))
        return p

    def export(self, **kwargs):
        options = dict(repo=self.repo, output=self.output, host='codex', workflow='changes',
                       feedback_type='WRONG_STRATEGY', host_version='1.2.3')
        options.update(kwargs)
        return exporter.export_feedback(**options)

    def read(self, name):
        return json.loads((self.output / name).read_text())

    def fixture(self):
        artifacts = {
            'project-profile.json': {'signals': {'mybatis': ['company/path'], 'mysql': []}, 'modules': ['private']},
            'effective-context.json': {'directive_ids': ['private-id'], 'constraints': {'docker_allowed': False}},
            'business-oracle.json': {'entries': [{'business_truth': True, 'source': 'internal/PRD', 'claim': 'private rule'}]},
            'test-policy.json': {'required_suites': ['unit', {'suite': 'integration'}], 'coverage': {'mode': 'UNSPECIFIED'}},
            'test-plan.json': {'items': [{'required': True, 'risk': 'HIGH', 'suite': 'unit',
                                        'oracle': {'business_truth': True}, 'assertions': ['private assertion']}]},
            'status.json': {'status': 'BLOCKED', 'blocking_ids': ['private-id']},
            'repository-evidence.json': {
                'change': {'files': [{'path': 'private-module/src/main/resources/private/Mapper.xml', 'status': 'M'}]},
                'risk_indicators': [{'path': 'private-module/src/main/resources/private/Mapper.xml', 'indicators': ['sql-mapping', 'mysql']}]},
            'execution-summary.json': {'status': 'NOT_VERIFIED', 'counts': {'tests': 3, 'failed': 0},
                                       'runs': [{'kind': 'test', 'exit_code': 0}]},
            'runs/private-run/manifest.json': {'runs': [{'kind': 'test', 'exit_code': 0, 'argv': ['SECRET_ARG']}], 'required_run_ids': ['private-run']},
        }
        for name, value in artifacts.items():
            self.put('.smart-test/' + name, value)
        return artifacts

    def test_normal_export_and_version_context(self):
        self.fixture()
        self.assertEqual(self.export()['status'], 'EXPORTED')
        self.assertEqual(len(list(self.output.iterdir())), 10)
        metadata = self.read('metadata.json')
        self.assertEqual(metadata['smart_test_version'], PACKAGE_VERSION)
        self.assertEqual(metadata['workflow'], 'changes')
        self.assertEqual(metadata['host'], 'codex')
        self.assertEqual(metadata['host_version'], '1.2.3')
        self.assertIn('smart_test_commit', metadata)
        self.assertIn('+00:00', metadata['timestamp'])
        self.assertEqual(self.read('test-policy.json')['summary']['required_suites'], ['integration', 'unit'])
        self.assertEqual(self.read('status.json')['summary']['status'], 'BLOCKED')
        self.assertEqual(self.read('execution-summary.json')['summary']['counts']['tests'], 3)
        self.assertEqual(len(self.read('execution-summary.json')['manifests']), 1)
        change = self.read('sanitized-change-summary.json')['summary']['files'][0]
        self.assertEqual(change, {'path': 'src/main/resources/file-0001.xml', 'change_type': 'modified',
                                  'risk_signals': ['mysql', 'sql-mapping']})
        feedback = self.read('feedback.json')
        self.assertEqual(feedback['root_cause'], 'UNKNOWN')
        self.assertIsNone(feedback['expected_behavior'])

    def test_nested_stage_statuses_are_exported_without_names_or_blocker_text(self):
        self.put('.smart-test/status.json', {'status': 'PARTIAL', 'stages': {
            'private-unit-stage': {'status': 'PASS', 'blocking_ids': []},
            'private-db-stage': {'status': 'BLOCKED', 'blockers': ['secret-db-location'],
                                 'stages': {'private-child': {'status': 'NOT_RUN'}}},
        }})
        self.export()
        summary = self.read('status.json')['summary']
        self.assertEqual(summary['status'], 'PARTIAL')
        self.assertEqual([s['status'] for s in summary['stages']], ['PASS', 'BLOCKED', 'NOT_RUN'])
        self.assertEqual(summary['stages'][1]['blocker_count'], 1)
        text = (self.output / 'status.json').read_text()
        self.assertNotIn('private-', text)
        self.assertNotIn('secret-db-location', text)

    def test_legacy_stage_summary_and_stage_limit(self):
        summary = exporter.summarize('status.json', {'verification': {'status': 'PASS'}})
        self.assertEqual(summary['stages'][0]['status'], 'PASS')
        data = {'stages': {str(i): {'status': 'NOT_RUN'} for i in range(exporter.MAX_ITEMS + 2)}}
        summary = exporter.summarize('status.json', data)
        self.assertEqual(len(summary['stages']), exporter.MAX_ITEMS)
        self.assertEqual(summary['stage_count'], exporter.MAX_ITEMS + 2)

    def test_missing_artifacts_still_produce_explicit_empty_summaries(self):
        self.export(host_version=None)
        for name in exporter.ARTIFACTS:
            self.assertEqual(self.read(name), {'input_state': 'MISSING', 'summary': {}})
        self.assertIsNone(self.read('metadata.json')['host_version'])
        self.assertFalse((self.repo / '.smart-test').exists())

    def test_secrets_personal_information_and_internal_urls_are_never_copied(self):
        artifacts = self.fixture()
        secrets = ['tok_SUPER_SECRET', 'password=abc123', 'Cookie: session=x',
                   'https://git.corp.example/team/private.git', 'jdbc:mysql://db.internal/production',
                   'alice@corp.example', '张三', 'account-private-993', '10.12.34.56']
        for name, value in artifacts.items():
            value['password'] = secrets[1]
            value['token'] = secrets[0]
            value['cookie'] = secrets[2]
            value['nested'] = {'logs': secrets, 'environment': secrets, 'diff': '\n'.join(secrets)}
            self.put('.smart-test/' + name, value)
        # Untrusted text inside recognized fields must also be dropped, not just unknown keys.
        self.put('.smart-test/test-plan.json', {'items': [{'id': secrets[0], 'target': secrets[3],
                  'risk': secrets[1], 'suite': secrets[2], 'assertions': secrets,
                  'oracle': {'business_truth': True, 'source': secrets[4], 'claim': secrets[5]}}]})
        self.put('.smart-test/status.json', {'status': secrets[0], 'blocking_ids': secrets})
        self.put('.smart-test/test-policy.json', {'required_suites': secrets,
                  'coverage': {'mode': secrets[0], 'metric': secrets[1], 'threshold': secrets[2], 'baseline': secrets[3]}})
        self.export()
        combined = ''.join(p.read_text() for p in self.output.iterdir())
        for secret in secrets + ['SECRET_ARG', 'private-module', 'private-run', 'private-id']:
            self.assertNotIn(secret, combined)

    def test_env_source_database_and_full_diff_are_not_read_or_exported(self):
        self.fixture()
        paths = ['.env', '.env.local', 'src/main/java/Customer.java', 'dump.sql', '.git/config', 'full.patch']
        for name in paths:
            self.put(name, 'RAW_PRIVATE_CONTENT=' + name)
        self.put('.smart-test/repository-evidence.json', {
            'source': 'class Secret { String token = "RAW_PRIVATE_CONTENT"; }',
            'diff': 'diff --git a/Secret.java b/Secret.java\n+RAW_PRIVATE_CONTENT',
            'change': {'files': [{'path': '.env', 'status': 'M'}, {'path': 'src/main/java/Customer.java', 'status': 'M'}]}})
        original_open = Path.open
        def guarded_open(p, *args, **kwargs):
            if p in [self.repo / name for name in paths]:
                raise AssertionError('raw project file must not be opened')
            return original_open(p, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            self.export()
        text = ''.join(p.read_text() for p in self.output.iterdir())
        self.assertNotIn('RAW_PRIVATE_CONTENT', text)
        self.assertNotIn('Customer.java', text)
        self.assertNotIn('.env', text)
        self.assertEqual(len(self.read('sanitized-change-summary.json')['summary']['files']), 1)

    def test_project_files_contents_and_mtimes_are_unchanged(self):
        self.fixture()
        self.put('src/main/java/App.java', 'class App {}')
        def snapshot():
            return {str(p.relative_to(self.repo)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.repo.rglob('*') if p.is_file()}
        before = snapshot()
        self.export()
        self.assertEqual(before, snapshot())

    def test_creates_nested_private_output_directory(self):
        self.output = self.base / 'exports/session/feedback'
        self.export()
        self.assertTrue(self.output.is_dir())
        if os.name == 'posix':
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.output.iterdir()))

    def test_existing_output_is_not_overwritten(self):
        self.output.mkdir()
        keep = self.output / 'keep'
        keep.write_text('user data')
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual(keep.read_text(), 'user data')

    def test_output_within_project_is_rejected(self):
        for path in (self.repo, self.repo / 'feedback', self.repo / '.smart-test/export'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.export(output=path)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_output_traversal_and_symlink_are_rejected(self):
        with self.assertRaises(ValueError):
            self.export(output=self.base / 'sub/../escape')
        link = self.base / 'link'
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.export(output=link / 'feedback')
        self.assertFalse(self.output.exists())

    def test_change_path_escape_is_rejected_before_output(self):
        for path in ('../secret', '/etc/passwd', 'C:\\secret', 'src/../../secret'):
            with self.subTest(path=path):
                self.put('.smart-test/repository-evidence.json', {'change': {'files': [{'path': path}]}})
                with self.assertRaises(ValueError):
                    self.export()
                self.assertFalse(self.output.exists())

    def test_artifact_and_runs_symlinks_are_rejected(self):
        secret = self.put('secret.json', '{"token":"secret"}')
        artifact = self.repo / '.smart-test'
        artifact.mkdir()
        link = artifact / 'status.json'
        link.symlink_to(secret)
        with self.assertRaises(ValueError):
            self.export()
        link.unlink()
        (artifact / 'runs').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.export()
        self.assertFalse(self.output.exists())

    def test_symlinked_artifact_parent_is_rejected(self):
        (self.repo / '.smart-test').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.export()

    def test_malformed_oversized_and_nonobject_artifacts_are_marked(self):
        self.put('.smart-test/status.json', '{password:PRIVATE_INVALID_JSON')
        self.put('.smart-test/test-policy.json', [])
        self.put('.smart-test/project-profile.json', 'x' * (exporter.MAX_BYTES + 1))
        self.export()
        self.assertEqual(self.read('status.json')['input_state'], 'INVALID_JSON')
        self.assertEqual(self.read('test-policy.json')['input_state'], 'INVALID_ROOT')
        self.assertEqual(self.read('project-profile.json')['input_state'], 'OMITTED_TOO_LARGE')
        self.assertNotIn('PRIVATE_INVALID_JSON', ''.join(p.read_text() for p in self.output.iterdir()))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_nonregular_artifact_rejected_without_reading(self):
        (self.repo / '.smart-test').mkdir()
        os.mkfifo(self.repo / '.smart-test/status.json')
        with self.assertRaises(ValueError):
            self.export()

    def test_no_commands_or_network_are_used(self):
        self.fixture()
        with patch.object(subprocess, 'run', side_effect=AssertionError('command')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('command')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network')):
            self.export()

    def test_unknown_metadata_and_arbitrary_host_version_rejected(self):
        for options in ({'host': 'corp.internal'}, {'workflow': 'verify'}, {'feedback_type': 'secret'},
                        {'host_version': '1.2.3 internal-user'}, {'host_version': 'https://internal'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.export(**options)
        self.assertFalse(self.output.exists())

    def test_cli_requires_output_and_redacts_errors(self):
        command = [sys.executable, str(SCRIPTS / 'export_feedback.py'), '--repo', str(self.repo),
                   '--host', 'codex', '--workflow', 'changes']
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        (self.repo / '.smart-test').symlink_to(self.base / 'secret-account', target_is_directory=True)
        result = subprocess.run(command + ['--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'ERROR')
        self.assertNotIn('secret-account', result.stdout + result.stderr)
        self.assertNotIn(str(self.repo), result.stdout + result.stderr)

    def test_cli_unknown_arguments_do_not_echo_secrets(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'export_feedback.py'),
                                 '--host', 'PRIVATE_TOKEN_VALUE'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('PRIVATE_TOKEN_VALUE', result.stdout + result.stderr)

    def test_failed_write_removes_partial_bundle(self):
        with patch.object(exporter.json, 'dump', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                self.export()
        self.assertFalse(self.output.exists())

    def test_invalid_numeric_and_enum_values_are_not_exported(self):
        self.put('.smart-test/test-policy.json', {'required_suites': [{'suite': ['secret']}],
                  'coverage': {'mode': ['secret'], 'metric': {'token': 'secret'}, 'threshold': float('nan')}})
        self.put('.smart-test/execution-summary.json', {'counts': {'tests': True, 'failed': float('inf')}})
        self.export()
        self.assertIsNone(self.read('test-policy.json')['summary']['coverage']['threshold'])
        self.assertIsNone(self.read('execution-summary.json')['summary']['counts']['tests'])
        self.assertIsNone(self.read('execution-summary.json')['summary']['counts']['failed'])

    def test_version_is_shipped_and_matches_plugin(self):
        package = json.loads((ROOT / 'skills/smart-test/version.json').read_text())
        plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())
        self.assertEqual(package['smart_test_version'], plugin['version'])
        standalone = self.base / 'standalone'
        standalone.mkdir()
        (standalone / 'scripts').mkdir()
        (standalone / 'version.json').write_text(json.dumps(package))
        with patch.object(exporter, '__file__', str(standalone / 'scripts/export_feedback.py')):
            version = exporter.version_context()
        self.assertEqual(version['smart_test_version'], PACKAGE_VERSION)
        self.assertIsNone(version['smart_test_commit'])

    def test_standalone_install_exports_without_plugin_or_git(self):
        self.fixture()
        installed = self.base / 'installation/smart-test'
        shutil.copytree(ROOT / 'skills/smart-test', installed,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        result = subprocess.run([sys.executable, str(installed / 'scripts/export_feedback.py'),
                                 '--repo', str(self.repo), '--output', str(self.output),
                                 '--host', 'claude-code', '--workflow', 'check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.read('metadata.json')['smart_test_version'], PACKAGE_VERSION)
        self.assertIsNone(self.read('metadata.json')['smart_test_commit'])
        self.assertEqual(self.read('metadata.json')['host'], 'claude-code')
        self.assertFalse(list(installed.rglob('__pycache__')))


    def test_other_agent_can_report_an_update_problem(self):
        self.export(host='other', workflow='update')
        metadata = self.read('metadata.json')
        self.assertEqual(metadata['host'], 'other')
        self.assertEqual(metadata['workflow'], 'update')

if __name__ == '__main__':
    unittest.main()
