import json
from pathlib import Path
import sys
from unittest.mock import patch

from test_helpers import Workspace, SCRIPTS
sys.path.insert(0, str(SCRIPTS))
from execute import execute
from project import begin, checkpoint, record_path, status


class ExecuteTests(Workspace):
    def setUp(self):
        super().setUp()
        self.put('docs/testing.md', '# Testing\nUse native commands and isolated fixtures.\n')
        self.put('src/order.py', 'amount = 1\n')
        self.record = begin(self.root, 'check', 'order boundary', 'docs/testing.md', 'Reviewed native testing')

    def spec(self, code=None, **kwargs):
        if code is None:
            code = ('from pathlib import Path; p=Path("target/reports/TEST-Order.xml"); '
                    'p.parent.mkdir(parents=True,exist_ok=True); '
                    'p.write_text(\'<testsuite><testcase classname="Order" name="reject"/></testsuite>\')')
        return dict(argv=[sys.executable, '-c', code], summary='Native boundary execution',
                    evidence_paths=['src/order.py', 'docs/testing.md'],
                    reports=['target/reports/TEST-*.xml'], **kwargs)

    def test_real_execution_is_attached_and_report_overwrite_preserves_prior_snapshot(self):
        first = execute(self.root, self.record['id'], self.spec())
        self.assertEqual(first['evidence_status'], 'EVIDENCE_PASS')
        self.assertEqual(first['counts']['tests'], 1)
        saved = json.loads(record_path(self.root, self.record['id']).read_text())
        old_report = next(iter(saved['events'][-1]['execution'][0]['reports']))
        original = (self.root / old_report).read_bytes()
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'NOT_VERIFIED')
        second = execute(self.root, self.record['id'], self.spec())
        self.assertNotEqual(first['manifest'], second['manifest'])
        self.assertEqual((self.root / old_report).read_bytes(), original)
        checkpoint(self.root, self.record['id'], dict(stage='verification', status='COMPLETED',
                   summary='Assertions and required scope reviewed', verification='PASS',
                   evidence_paths=['src/order.py', 'docs/testing.md'], run_manifests=[second['manifest']]))
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'PASS')

    def test_native_failure_keeps_exit_code_and_failed_record(self):
        result = execute(self.root, self.record['id'], self.spec('raise SystemExit(7)'))
        self.assertEqual(result['exit_code'], 7)
        run = json.loads((self.root / result['manifest']).read_text())['runs'][0]
        self.assertEqual(run['exit_code_source'], 'native_process')
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'FAILED')
        self.assertFalse((self.root / '.smart-test/execution.lock').exists())

    def test_old_reports_and_zero_tests_cannot_supply_fresh_execution_evidence(self):
        self.put('target/reports/TEST-Order.xml', '<testsuite><testcase name="old"/></testsuite>')
        result = execute(self.root, self.record['id'], self.spec('pass'))
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
        self.assertEqual(result['counts']['tests'], 0)

    def test_timeout_is_recorded_and_command_is_stopped(self):
        result = execute(self.root, self.record['id'], self.spec('import time; time.sleep(60)', timeout_seconds=.05))
        self.assertEqual(result['termination'], 'TIMEOUT')
        self.assertEqual(result['exit_code'], 124)
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'FAILED')

    def test_keyboard_interrupt_retains_manifest_and_releases_locks(self):
        with patch('execute.subprocess.Popen') as spawn:
            process = spawn.return_value
            process.pid = 99999999
            process.wait.side_effect = [KeyboardInterrupt(), 0]
            result = execute(self.root, self.record['id'], self.spec())
        self.assertEqual(result['termination'], 'INTERRUPTED')
        self.assertTrue((self.root / result['manifest']).exists())
        self.assertFalse((self.root / '.smart-test/project.lock').exists())
        self.assertFalse((self.root / '.smart-test/execution.lock').exists())

    def test_source_changed_during_run_blocks_evidence_pass(self):
        spec = self.spec('from pathlib import Path; Path("src/order.py").write_text("amount=2")', kind='compile')
        spec['reports'] = []
        result = execute(self.root, self.record['id'], spec)
        self.assertTrue(result['evidence_changed_during_execution'])
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')

    def test_source_deleted_during_run_still_retains_execution(self):
        result = execute(self.root, self.record['id'], self.spec('from pathlib import Path; Path("src/order.py").unlink()', kind='compile'))
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
        self.assertEqual(json.loads(record_path(self.root, self.record['id']).read_text())['events'][-1]['execution'][0]['manifest'], result['manifest'])

    def test_norm_changed_during_run_retains_observation_without_adopting_it(self):
        result = execute(self.root, self.record['id'], self.spec('from pathlib import Path; Path("docs/testing.md").write_text("# Changed policy")', kind='compile'))
        row = status(self.root)['records'][0]
        self.assertTrue(row['checks'][0]['policy_changed'])
        self.assertTrue(status(self.root)['policy_review_required'])
        self.assertEqual(row['checks'][0]['current_verification'], 'STALE')
        self.assertTrue((self.root / result['manifest']).exists())

    def test_bad_input_and_an_existing_execution_lock_prevent_execution(self):
        marker = self.root / 'executed'
        spec = self.spec('from pathlib import Path; Path("executed").touch()')
        bad = dict(spec, reports=['../outside.xml'])
        with self.assertRaises(ValueError):
            execute(self.root, self.record['id'], bad)
        self.put('.smart-test/execution.lock', 'other writer')
        with self.assertRaises(ValueError):
            execute(self.root, self.record['id'], spec)
        self.assertFalse(marker.exists())
        self.assertEqual((self.root / '.smart-test/execution.lock').read_text(), 'other writer')


    def test_compilation_is_collected_without_claiming_tests_ran(self):
        spec = self.spec('pass', kind='compile')
        spec['reports'] = []
        result = execute(self.root, self.record['id'], spec)
        self.assertEqual(result['evidence_status'], 'EVIDENCE_PASS')
        self.assertEqual(result['counts']['tests'], 0)
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'NOT_RUN')

    def test_start_failure_preserves_launcher_result_and_does_not_claim_native_exit(self):
        spec = self.spec()
        spec['argv'] = ['nonexistent-smart-test-native-command']
        result = execute(self.root, self.record['id'], spec)
        run = json.loads((self.root / result['manifest']).read_text())['runs'][0]
        self.assertEqual(result['termination'], 'START_FAILED')
        self.assertEqual(run['exit_code_source'], 'execution_helper')
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'FAILED')

    def test_report_identity_constraints_are_carried_into_manifest(self):
        spec = self.spec()
        spec['reports'] = [{'pattern': 'target/reports/TEST-*.xml', 'expected_test_ids': ['Order#boundary'],
                            'min_tests': 1, 'allow_skipped': False}]
        result = execute(self.root, self.record['id'], spec)
        manifest = json.loads((self.root / result['manifest']).read_text())
        group = manifest['runs'][0]['reports'][0]
        self.assertEqual(group['expected_test_ids'], ['Order#boundary'])
        self.assertEqual(group['min_tests'], 1)
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')

    def test_old_run_cannot_be_promoted_to_pass_after_policy_review(self):
        result = execute(self.root, self.record['id'], self.spec())
        self.put('docs/testing.md', '# Testing\nIntegration is now required.\n')
        from project import adopt
        adopt(self.root, 'docs/testing.md', 'Reviewed integration requirement')
        with self.assertRaises(ValueError):
            checkpoint(self.root, self.record['id'], dict(
                stage='verification', status='COMPLETED', summary='Old run under old policy',
                verification='PASS', evidence_paths=['src/order.py', 'docs/testing.md'],
                run_manifests=[result['manifest']]))


    def test_relabeling_an_old_run_cannot_pass_after_source_changes(self):
        result = execute(self.root, self.record['id'], self.spec())
        self.put('src/order.py', 'amount = 2\n')
        with self.assertRaises(ValueError):
            checkpoint(self.root, self.record['id'], dict(stage='verification', status='COMPLETED',
                       summary='Old report cannot verify revised source', verification='PASS',
                       evidence_paths=['src/order.py'], run_manifests=[result['manifest']]))
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'STALE')

    def test_deleted_policy_does_not_discard_an_actual_execution_failure(self):
        spec = self.spec('from pathlib import Path; Path("docs/testing.md").unlink(); raise SystemExit(3)')
        result = execute(self.root, self.record['id'], spec)
        self.assertEqual(result['exit_code'], 3)
        self.assertEqual(json.loads(record_path(self.root, self.record['id']).read_text())['events'][-1]['execution'][0]['manifest'], result['manifest'])
        self.assertTrue(status(self.root)['policy_review_required'])
