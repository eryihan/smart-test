"""Exercise the lightweight path without any project-registration fixtures."""
import json
from pathlib import Path
import subprocess
import sys

from test_helpers import Workspace, SCRIPTS
from execute import execute
from collect_reports import read_reports
from inspect_repo import inspect, query_result


class StandaloneTests(Workspace):
    def spec(self, xml='<testsuite><testcase classname="Order" name="reject"/></testsuite>', **extra):
        code = ('from pathlib import Path; p=Path("target/TEST-Order.xml"); '
                'p.parent.mkdir(parents=True,exist_ok=True); p.write_text(' + repr(xml) + ')')
        return dict(argv=[sys.executable, '-c', code], summary='Order boundary',
                    reports=['target/TEST-*.xml'], **extra)

    def test_execution_needs_no_policy_or_record_and_leaves_no_management_files(self):
        result = execute(self.root, self.spec())
        self.assertEqual(result['counts']['tests'], 1)
        self.assertEqual(result['evidence_status'], 'EVIDENCE_PASS')
        self.assertIsNone(result['manifest'])
        self.assertNotIn('policy', result['execution']['runs'][0])
        self.assertFalse((self.root / '.smart-test').exists())

    def test_unrelated_project_files_are_not_consumed_or_modified(self):
        self.put('.smart-test/local-settings.json', 'independent settings')
        self.put('.smart-test/cache.json', 'independent cache')
        before = {p.name: p.read_bytes() for p in (self.root / '.smart-test').iterdir()}
        execute(self.root, self.spec())
        after = {p.name: p.read_bytes() for p in (self.root / '.smart-test').iterdir()}
        self.assertEqual(before, after)

    def test_saved_evidence_is_independent_and_survives_report_overwrite(self):
        result = execute(self.root, self.spec(), save_evidence=True)
        manifest = json.loads((self.root / result['manifest']).read_text())
        report = next(self.root.glob(manifest['runs'][0]['reports'][0]['pattern']))
        original = report.read_bytes()
        execute(self.root, self.spec('<testsuite/>'))
        self.assertEqual(report.read_bytes(), original)
        self.assertEqual({p.name for p in (self.root / '.smart-test').iterdir()}, {'runs'})

    def test_native_failure_and_timeout_are_observed_without_registration(self):
        for code, expected, termination in [('raise SystemExit(7)', 7, None),
                                             ('import time; time.sleep(60)', 124, 'TIMEOUT')]:
            with self.subTest(code=code):
                result = execute(self.root, dict(argv=[sys.executable, '-c', code],
                                 summary='Compile', kind='compile', reports=[], timeout_seconds=.05))
                self.assertEqual(result['exit_code'], expected)
                self.assertEqual(result['termination'], termination)
                self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
        self.assertFalse((self.root / '.smart-test').exists())

    def test_stale_zero_skipped_failed_and_missing_identity_never_pass(self):
        cases = [('<testsuite/>', {}),
                 ('<testsuite><testcase name="x"><skipped/></testcase></testsuite>', {}),
                 ('<testsuite><testcase name="x"><failure/></testcase></testsuite>', {}),
                 ('<testsuite><testcase classname="Other" name="x"/></testsuite>',
                  {'reports': [{'pattern': 'target/TEST-*.xml', 'expected_test_ids': ['Order#reject']}]})]
        for xml, extra in cases:
            with self.subTest(xml=xml):
                spec = self.spec(xml)
                spec.update(extra)
                self.assertEqual(execute(self.root, spec)['evidence_status'], 'NOT_VERIFIED')
        self.put('target/TEST-Order.xml', '<testsuite><testcase name="old"/></testsuite>')
        self.assertEqual(execute(self.root, dict(argv=[sys.executable, '-c', 'pass'],
                         summary='No tests', reports=['target/TEST-*.xml']))['evidence_status'], 'NOT_VERIFIED')

    def test_referenced_source_change_blocks_execution_evidence(self):
        self.put('source.txt', 'before')
        result = execute(self.root, dict(argv=[sys.executable, '-c',
                         'from pathlib import Path; Path("source.txt").write_text("after")'],
                         summary='Compile', kind='compile', reports=[], evidence_paths=['source.txt']))
        self.assertTrue(result['evidence_changed_during_execution'])
        self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')

    def test_unsafe_report_created_by_command_keeps_actual_exit_and_cannot_pass(self):
        self.put('private.xml', 'sensitive payload')
        for saved in (False, True):
            with self.subTest(saved=saved):
                script = ('from pathlib import Path; p=Path("target/TEST-link.xml"); '
                          'p.parent.mkdir(exist_ok=True); p.unlink(missing_ok=True); '
                          'p.symlink_to("../private.xml"); raise SystemExit(7)')
                result = execute(self.root, dict(argv=[sys.executable, '-c', script],
                                 summary='Unsafe generated report', reports=['target/TEST-*.xml']),
                                 save_evidence=saved)
                self.assertEqual(result['exit_code'], 7)
                self.assertEqual(result['evidence_status'], 'NOT_VERIFIED')
                self.assertNotIn('sensitive payload', json.dumps(result))
        result = read_reports(self.root, ['target/TEST-*.xml'])
        self.assertEqual(result['report_integrity'], 'INVALID')
        self.assertIn('UNSAFE_OR_MISSING_REPORT', {issue['type'] for issue in result['issues']})

    def test_bad_report_path_or_existing_lock_prevents_native_execution(self):
        spec = dict(argv=[sys.executable, '-c', 'from pathlib import Path; Path("ran").touch()'],
                    summary='Test', reports=['../outside.xml'])
        with self.assertRaises(ValueError):
            execute(self.root, spec)
        self.put('.smart-test/execution.lock', 'other writer')
        spec['reports'] = ['target/TEST-*.xml']
        with self.assertRaises(ValueError):
            execute(self.root, spec)
        self.assertFalse((self.root / 'ran').exists())
        self.assertEqual((self.root / '.smart-test/execution.lock').read_text(), 'other writer')

    def test_unsupported_execution_fields_prevent_native_execution(self):
        spec = dict(argv=[sys.executable, '-c', 'from pathlib import Path; Path("ran").touch()'],
                    summary='Unit only', kind='compile', reports=[],
                    unsupported_field={'unit': 'PASS', 'integration': 'NOT_RUN'})
        with self.assertRaises(ValueError):
            execute(self.root, spec)
        self.assertFalse((self.root / 'ran').exists())
        self.assertFalse((self.root / '.smart-test').exists())

    def test_direct_cli_keeps_native_argv_and_needs_no_input_file(self):
        spec = self.spec()
        result = subprocess.run([sys.executable, str(SCRIPTS / 'execute.py'), '--repo', str(self.root),
                                 '--report', 'target/TEST-*.xml', '--'] + spec['argv'],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['execution']['runs'][0]['argv'], spec['argv'])
        self.assertFalse((self.root / '.smart-test').exists())

    def test_report_only_read_is_read_only_and_cannot_claim_fresh_execution(self):
        self.put('target/TEST-Order.xml', '<testsuite><testcase classname="Order" name="reject"/></testsuite>')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = read_reports(self.root, ['target/TEST-*.xml'])
        self.assertEqual(result['report_integrity'], 'VALID')
        self.assertEqual(result['status'], 'NOT_VERIFIED')
        self.assertEqual(result['freshness'], 'UNKNOWN')
        self.assertEqual(result['reports'][0]['executed_test_ids'], ['Order#reject'])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_report_only_missing_malformed_and_duplicate_inputs_are_visible(self):
        self.put('target/TEST-bad.xml', '<broken')
        result = read_reports(self.root, ['target/TEST-*.xml', 'target/TEST-*.xml', 'missing/*.xml'])
        kinds = {issue['type'] for issue in result['issues']}
        self.assertTrue({'MALFORMED_REPORT', 'DUPLICATE_REPORT', 'REPORTS_MISSING', 'ZERO_TESTS'} <= kinds)

    def test_scoped_inspection_keeps_build_hints_without_reading_other_sources(self):
        self.put('pom.xml', '<project><artifactId>demo</artifactId></project>')
        self.put('order/src/main/java/Order.java', 'class Order {}')
        self.put('other/src/main/java/Other.java', 'class Other {}')
        result = inspect(self.root, paths=['order'])
        self.assertEqual(result['production_sources'], ['order/src/main/java/Order.java'])
        self.assertIn('pom.xml', result['build_files'])
        self.assertNotIn('other/src/main/java/Other.java', result['fingerprints'])
        compact = query_result(result, 'overview')
        self.assertEqual(compact['source_count'], 1)
        self.assertNotIn('fingerprints', compact)
        with self.assertRaises(ValueError):
            inspect(self.root, paths=['../outside'])

    def test_test_listing_explicitly_reports_omitted_paths(self):
        for index in range(101):
            self.put('src/test/java/Test' + str(index) + '.java', 'class Test {}')
        result = query_result(inspect(self.root), 'tests')
        self.assertEqual(result['test_source_count'], 101)
        self.assertEqual(len(result['test_sources']), 100)
        self.assertEqual(result['paths_omitted'], 1)
