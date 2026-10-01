"""Execution failure observations must survive interruption and evidence loss."""
import json
import sys
from unittest.mock import patch

from test_helpers import Workspace
from execute import execute


class ExecuteTests(Workspace):
    def setUp(self):
        super().setUp()
        self.put('docs/testing.md', '# Testing\nUse native commands.\n')
        self.put('src/order.py', 'amount = 1\n')

    def spec(self, code, **extra):
        return dict(argv=[sys.executable, '-c', code], summary='Native execution',
                    evidence_paths=['src/order.py', 'docs/testing.md'],
                    kind='compile', reports=[], **extra)

    def test_keyboard_interrupt_retains_manifest_and_releases_lock(self):
        with patch('execute.subprocess.Popen') as spawn:
            process = spawn.return_value
            process.pid = 99999999
            process.wait.side_effect = [KeyboardInterrupt(), 0]
            result = execute(self.root, self.spec('pass'), save_evidence=True)
        self.assertEqual(result['termination'], 'INTERRUPTED')
        self.assertEqual(result['exit_code'], 130)
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
        self.assertTrue((self.root / result['manifest']).exists())
        self.assertFalse((self.root / '.smart-test/execution.lock').exists())

    def test_source_deleted_during_run_still_retains_execution(self):
        result = execute(self.root, self.spec('from pathlib import Path; Path("src/order.py").unlink()'),
                         save_evidence=True)
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
        run = json.loads((self.root / result['manifest']).read_text())['runs'][0]
        self.assertIsNone(run['evidence_after']['src/order.py'])
        self.assertTrue(result['evidence_changed_during_execution'])

    def test_compilation_facts_do_not_claim_tests_ran(self):
        result = execute(self.root, self.spec('pass'))
        self.assertEqual(result['evidence_status'], 'EVIDENCE_PASS')
        self.assertEqual(result['counts']['tests'], 0)
        self.assertEqual(result['execution']['runs'][0]['kind'], 'compile')
        self.assertFalse((self.root / '.smart-test').exists())

    def test_start_failure_is_a_launcher_result(self):
        spec = self.spec('pass')
        spec['argv'] = ['nonexistent-smart-test-native-command']
        result = execute(self.root, spec, save_evidence=True)
        run = json.loads((self.root / result['manifest']).read_text())['runs'][0]
        self.assertEqual(result['termination'], 'START_FAILED')
        self.assertEqual(result['exit_code'], 127)
        self.assertEqual(run['exit_code_source'], 'execution_helper')
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')

    def test_deleted_rule_file_does_not_discard_execution_failure(self):
        spec = self.spec('from pathlib import Path; Path("docs/testing.md").unlink(); raise SystemExit(3)')
        result = execute(self.root, spec, save_evidence=True)
        self.assertEqual(result['exit_code'], 3)
        manifest = json.loads((self.root / result['manifest']).read_text())
        self.assertEqual(manifest['runs'][0]['exit_code'], 3)
        self.assertIsNone(manifest['runs'][0]['evidence_after']['docs/testing.md'])
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
