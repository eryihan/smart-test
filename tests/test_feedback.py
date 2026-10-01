"""Feedback only exports allowlisted run facts and never reads project documents."""
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
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def export(self, **extra):
        options = dict(repo=self.repo, output=self.output, host='codex', workflow='check',
                       feedback_type='FALSE_PASS', host_version='1.2.3')
        options.update(extra)
        return exporter.export_feedback(**options)

    def read(self, name):
        return json.loads((self.output / name).read_text())

    def fixture(self):
        return self.put('.smart-test/runs/private-run/manifest.json', {
            'runs': [{'kind': 'test', 'exit_code': 0, 'argv': ['SECRET_ARG'],
                      'reports': [{'pattern': 'private/reports.xml'}]}],
            'required_run_ids': ['private-run'], 'blockers': ['private reason']})

    def test_exported_files_version_and_run_facts(self):
        self.fixture()
        self.assertEqual(self.export()['status'], 'EXPORTED')
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {'metadata.json', 'feedback.json', 'execution-summary.json'})
        metadata = self.read('metadata.json')
        self.assertEqual(metadata['smart_test_version'], PACKAGE_VERSION)
        self.assertEqual(metadata['workflow'], 'check')
        self.assertEqual(metadata['host_version'], '1.2.3')
        self.assertIn('+00:00', metadata['timestamp'])
        summary = self.read('execution-summary.json')['manifests'][0]['summary']
        self.assertEqual(summary['required_run_count'], 1)
        self.assertEqual(summary['blocker_count'], 1)
        self.assertEqual(summary['runs'][0]['exit_code'], 0)
        self.assertEqual(summary['runs'][0]['report_group_count'], 1)
        self.assertEqual(self.read('feedback.json')['root_cause'], 'UNKNOWN')

    def test_no_private_arguments_ids_prose_or_invalid_enums_are_exported(self):
        secrets = ['TOKEN_VALUE', 'password=abc', 'alice@corp.example', '张三', 'jdbc:mysql://internal/db']
        self.put('.smart-test/runs/private-run/manifest.json', {
            'status': secrets[0], 'blockers': secrets, 'logs': secrets,
            'counts': {'tests': True, 'failed': float('inf')},
            'runs': [{'id': 'private-run', 'kind': secrets[2], 'argv': secrets,
                      'exit_code': secrets[1], 'reports': [{'pattern': secrets[4]}]}]})
        self.export()
        combined = ''.join(p.read_text() for p in self.output.iterdir())
        for secret in secrets + ['private-run']:
            self.assertNotIn(secret, combined)
        summary = self.read('execution-summary.json')['manifests'][0]['summary']
        self.assertIsNone(summary['status'])
        self.assertIsNone(summary['counts']['tests'])
        self.assertIsNone(summary['counts']['failed'])
        self.assertIsNone(summary['runs'][0]['kind'])
        self.assertIsNone(summary['runs'][0]['exit_code'])

    def test_only_selected_manifest_is_read(self):
        self.fixture()
        self.put('.smart-test/runs/unrelated/manifest.json', 'invalid')
        files = ['docs/testing.md', 'docs/testing-work.md', '.env', 'src/App.java', '.git/config', 'dump.sql']
        for name in files:
            self.put(name, 'PRIVATE_CONTENT')
        original = exporter.read_json
        def read(root, name):
            if Path(root) == self.repo and name != '.smart-test/runs/private-run/manifest.json':
                raise AssertionError('unrelated project input read')
            return original(root, name)
        with patch.object(exporter, 'read_json', side_effect=read):
            self.export(run_ids=['private-run'])
        self.assertNotIn('PRIVATE_CONTENT', ''.join(p.read_text() for p in self.output.iterdir()))

    def test_missing_runs_need_no_project_artifacts(self):
        self.export(host_version=None, run_ids=['missing-run'])
        self.assertEqual(self.read('execution-summary.json')['manifests'][0]['input_state'], 'MISSING')
        self.assertIsNone(self.read('metadata.json')['host_version'])
        self.assertFalse((self.repo / '.smart-test').exists())

    def test_recent_runs_and_omissions(self):
        for index in range(exporter.MAX_RUN_FILES + 1):
            self.put('.smart-test/runs/%03d/manifest.json' % index,
                     {'runs': [{'kind': 'test', 'exit_code': index}]})
        self.export()
        result = self.read('execution-summary.json')
        self.assertEqual(result['runs_omitted'], 1)
        self.assertEqual(result['manifests'][0]['summary']['runs'][0]['exit_code'], exporter.MAX_RUN_FILES)

    def test_invalid_run_selection_rejected_before_writing(self):
        for ids in ([], ['../outside'], ['same', 'same'], [{}], ['one'] * 101):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.export(run_ids=ids)
        self.assertFalse(self.output.exists())

    def test_project_contents_and_mtimes_unchanged(self):
        self.fixture()
        self.put('src/App.java', 'class App {}')
        def snapshot():
            return {p.relative_to(self.repo): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.repo.rglob('*') if p.is_file()}
        before = snapshot()
        self.export()
        self.assertEqual(before, snapshot())

    def test_private_output_permissions(self):
        self.output = self.base / 'exports/session/feedback'
        self.export()
        if os.name == 'posix':
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.output.iterdir()))

    def test_existing_output_preserved(self):
        self.output.mkdir()
        keep = self.output / 'keep'
        keep.write_text('user data')
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual(keep.read_text(), 'user data')

    def test_output_inside_project_or_traversal_rejected(self):
        for output in (self.repo, self.repo / 'feedback', self.base / 'sub/../escape'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.export(output=output)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_output_symlink_rejected(self):
        link = self.base / 'link'
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.export(output=link / 'feedback')

    def test_run_manifest_and_parent_symlinks_rejected(self):
        manifest = self.fixture()
        manifest.unlink()
        manifest.symlink_to(self.put('secret.json', {'token': 'private'}))
        with self.assertRaises(ValueError):
            self.export()
        self.assertFalse(self.output.exists())
        shutil.rmtree(self.repo / '.smart-test')
        (self.repo / '.smart-test').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.export()

    def test_malformed_oversized_and_nonobject_manifests_are_marked(self):
        for identity, content in [('bad', '{PRIVATE_JSON'), ('root', []),
                                  ('large', 'x' * (exporter.MAX_BYTES + 1))]:
            self.put('.smart-test/runs/' + identity + '/manifest.json', content)
        self.export(run_ids=['bad', 'root', 'large'])
        states = [m['input_state'] for m in self.read('execution-summary.json')['manifests']]
        self.assertEqual(states, ['INVALID_JSON', 'INVALID_ROOT', 'OMITTED_TOO_LARGE'])
        self.assertNotIn('PRIVATE_JSON', ''.join(p.read_text() for p in self.output.iterdir()))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_nonregular_manifest_rejected_without_reading(self):
        directory = self.repo / '.smart-test/runs/run'
        directory.mkdir(parents=True)
        os.mkfifo(directory / 'manifest.json')
        with self.assertRaises(ValueError):
            self.export()

    def test_no_commands_or_network(self):
        self.fixture()
        with patch.object(subprocess, 'run', side_effect=AssertionError('command')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('command')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network')):
            self.export()

    def test_unknown_metadata_rejected(self):
        for options in ({'host': 'internal'}, {'workflow': 'verify'}, {'feedback_type': 'secret'},
                        {'host_version': '1.2.3 internal'}, {'host_version': 'https://internal'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.export(**options)
        self.assertFalse(self.output.exists())

    def test_cli_errors_do_not_echo_private_arguments(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'export_feedback.py'),
                                 '--host', 'PRIVATE_TOKEN_VALUE'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('PRIVATE_TOKEN_VALUE', result.stdout + result.stderr)

    def test_cli_path_errors_are_redacted(self):
        (self.repo / '.smart-test').symlink_to(self.base / 'secret-account', target_is_directory=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'export_feedback.py'), '--repo', str(self.repo),
                                 '--host', 'codex', '--workflow', 'check', '--output', str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'ERROR')
        self.assertNotIn('secret-account', result.stdout + result.stderr)
        self.assertNotIn(str(self.repo), result.stdout + result.stderr)

    def test_failed_write_removes_partial_bundle(self):
        with patch.object(exporter.json, 'dump', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                self.export()
        self.assertFalse(self.output.exists())

    def test_versions_match_plugin_and_standalone_has_no_claimed_commit(self):
        package = json.loads((ROOT / 'skills/smart-test/version.json').read_text())
        plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())
        self.assertEqual(package['smart_test_version'], plugin['version'])
        standalone = self.base / 'standalone'
        (standalone / 'scripts').mkdir(parents=True)
        (standalone / 'version.json').write_text(json.dumps(package))
        with patch.object(exporter, '__file__', str(standalone / 'scripts/export_feedback.py')):
            self.assertIsNone(exporter.version_context()['smart_test_commit'])

    def test_installed_exporter_needs_no_plugin_or_git(self):
        self.fixture()
        installed = self.base / 'installation/smart-test'
        shutil.copytree(ROOT / 'skills/smart-test', installed, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        command = [sys.executable, str(installed / 'scripts/export_feedback.py'), '--repo', str(self.repo),
                   '--output', str(self.output), '--host', 'other', '--workflow', 'update']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(len(list(self.output.iterdir())), 3)
        self.assertEqual(self.read('metadata.json')['smart_test_version'], PACKAGE_VERSION)
        self.assertIsNone(self.read('metadata.json')['smart_test_commit'])
