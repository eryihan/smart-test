import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
import unittest

from test_helpers import Workspace, SCRIPTS
sys.path.insert(0, str(SCRIPTS))
from project import adopt, begin, checkpoint, detach, record_path, status, writing


class ProjectTests(Workspace):
    def policy(self):
        return self.put('docs/testing.md', '# 测试规范\nUT 用原生命令；数据库测试使用隔离实例。\n')

    def managed(self, workflow='scan'):
        self.policy()
        return begin(self.root, workflow, 'order module', 'docs/testing.md', 'Reviewed existing project rules')

    def entry(self, **kwargs):
        return dict(stage='discovery', status='COMPLETED', summary='Checked order rules and existing tests', **kwargs)

    def manifest(self, failed=False):
        report = self.put('target/reports/TEST-Order.xml',
                          '<testsuite><testcase classname="Order" name="reject">' +
                          ('<failure message="fixture failure"/>' if failed else '') + '</testcase></testsuite>')
        stamp = report.stat().st_mtime
        def at(value):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        data = {'schema_version': 1, 'required_run_ids': ['unit'], 'runs': [{
            'id': 'unit', 'argv': ['native-test', 'Order'], 'started_at': at(stamp - 1),
            'finished_at': at(stamp + 1), 'exit_code': 1 if failed else 0,
            'reports': [{'pattern': 'target/reports/TEST-Order.xml', 'required': True}],
        }]}
        self.put('.smart-test/runs/unit/manifest.json', json.dumps(data))
        return '.smart-test/runs/unit/manifest.json', report

    def verified(self, failed=False):
        record = self.managed('check')
        self.put('src/Order.java', 'class Order {}')
        manifest, report = self.manifest(failed)
        checkpoint(self.root, record['id'], dict(stage='verification', status='COMPLETED',
                   summary='Actual fixture execution result', verification='FAILED' if failed else 'PASS',
                   evidence_paths=['src/Order.java'], run_manifests=[manifest]))
        return record, report

    def test_status_is_read_only_before_and_after_adoption(self):
        self.assertEqual(status(self.root)['management'], 'UNMANAGED')
        self.assertFalse((self.root / '.smart-test').exists())
        self.managed()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        status(self.root)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root / '.smart-test/project.lock').exists())

    def test_adoption_keeps_the_existing_policy_and_is_idempotent(self):
        original = self.policy().read_bytes()
        first = adopt(self.root, 'docs/testing.md', 'Review')
        second = adopt(self.root, 'docs/testing.md', 'Repeated review')
        self.assertEqual(first, second)
        self.assertEqual(self.policy().read_bytes(), original)
        self.assertEqual(first['policy']['path'], 'docs/testing.md')

    def test_changed_policy_requires_review_and_preserves_history(self):
        self.managed()
        self.put('docs/testing.md', '# 测试规范\nIT 为必需套件。\n')
        self.assertTrue(status(self.root)['policy_review_required'])
        with self.assertRaises(ValueError):
            begin(self.root, 'changes', 'order')
        reviewed = adopt(self.root, 'docs/testing.md', 'Integration is now required')
        self.assertEqual(len(reviewed['events']), 2)
        begin(self.root, 'changes', 'order')

    def test_scan_has_durable_findings_without_claiming_test_execution(self):
        record = self.managed()
        self.put('src/Order.java', 'class Order {}')
        fid = record['id'] + ':F01'
        checkpoint(self.root, record['id'], self.entry(evidence_paths=['src/Order.java'], findings=[
            {'id': fid, 'summary': 'Missing negative amount assertion', 'status': 'OPEN'}]))
        result = status(self.root)
        self.assertEqual(result['records'][0]['status'], 'COMPLETED')
        self.assertEqual(result['records'][0]['current_verification'], 'NOT_RUN')
        self.assertEqual(result['open_findings'][0]['id'], fid)
        self.assertFalse((self.root / '.smart-test/runs').exists())

    def test_followup_can_resolve_a_finding_with_current_evidence(self):
        record = self.managed()
        fid = record['id'] + ':F01'
        checkpoint(self.root, record['id'], self.entry(findings=[
            {'id': fid, 'summary': 'Missing assertion', 'status': 'OPEN'}]))
        followup = begin(self.root, 'changes', 'order')
        self.put('src/OrderTest.java', 'class OrderTest {}')
        checkpoint(self.root, followup['id'], self.entry(evidence_paths=['src/OrderTest.java'], findings=[
            {'id': fid, 'summary': 'Reinspection found the existing assertion; the original finding was incorrect', 'status': 'RESOLVED'}]))
        self.assertEqual(status(self.root)['open_findings'], [])
        saved = json.loads(record_path(self.root, record['id']).read_text())
        self.assertEqual(saved['events'][0]['findings'][0]['status'], 'OPEN')

    def test_unknown_finding_and_resolution_without_evidence_are_rejected(self):
        record = self.managed()
        for fid in ['missing:F01', record['id'] + ':F01']:
            with self.subTest(fid=fid), self.assertRaises(ValueError):
                checkpoint(self.root, record['id'], self.entry(findings=[
                    {'id': fid, 'summary': 'Resolve', 'status': 'RESOLVED'}]))

    def test_interrupted_work_and_partial_results_remain_visible(self):
        record = self.managed()
        self.assertEqual(status(self.root)['records'][0]['status'], 'IN_PROGRESS')
        checkpoint(self.root, record['id'], dict(stage='discovery', status='PARTIAL',
                   summary='Only order checked', next_step='Review payment module'))
        self.assertEqual(status(self.root)['records'][0]['next_step'], 'Review payment module')

    def test_pass_requires_real_manifest_and_code_evidence(self):
        record = self.managed('check')
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], self.entry(verification='PASS'))
        self.assertEqual(json.loads(record_path(self.root, record['id']).read_text())['revision'], 0)

    def test_failed_execution_cannot_be_recorded_as_pass(self):
        record = self.managed('check')
        manifest, _ = self.manifest(True)
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], self.entry(verification='PASS',
                       evidence_paths=['docs/testing.md'], run_manifests=[manifest]))

    def test_source_change_marks_verification_stale_but_keeps_history(self):
        self.verified()
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'PASS')
        self.put('src/Order.java', 'class Order { int changed; }')
        item = status(self.root)['records'][0]
        self.assertEqual(item['recorded_verification'], 'PASS')
        self.assertEqual(item['current_verification'], 'STALE')

    def test_report_overwrite_is_detected_even_with_same_counts_and_mtime(self):
        _, report = self.verified()
        stamp = report.stat().st_mtime_ns
        report.write_text('<testsuite><testcase classname="Other" name="reject"/></testsuite>')
        os.utime(report, ns=(stamp, stamp))
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'STALE')

    def test_scan_evidence_changes_are_visible_without_inventing_execution(self):
        record = self.managed()
        self.put('src/Order.java', 'class Order {}')
        checkpoint(self.root, record['id'], self.entry(evidence_paths=['src/Order.java']))
        self.put('src/Order.java', 'class Order { int changed; }')
        item = status(self.root)['records'][0]
        self.assertEqual(item['work_evidence_changed'], ['src/Order.java'])
        self.assertEqual(item['current_verification'], 'NOT_RUN')

    def test_recently_resumed_task_is_listed_first(self):
        old = self.managed()
        newer = begin(self.root, 'check', 'order smoke')
        checkpoint(self.root, newer['id'], self.entry())
        checkpoint(self.root, old['id'], self.entry())
        self.assertEqual(status(self.root)['records'][0]['id'], old['id'])

    def test_unreadable_record_does_not_hide_other_work_or_trigger_a_repair(self):
        record = self.managed()
        checkpoint(self.root, record['id'], self.entry())
        broken = self.put('.smart-test/records/broken.json', '{truncated')
        result = status(self.root)
        self.assertEqual(result['record_count'], 1)
        self.assertEqual(result['records'][0]['id'], record['id'])
        self.assertEqual(result['unreadable_records'], ['.smart-test/records/broken.json'])
        self.assertEqual(broken.read_text(), '{truncated')

    def test_unchanged_failed_execution_remains_failed(self):
        self.verified(True)
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'FAILED')

    def test_revision_guard_and_lock_do_not_overwrite_other_work(self):
        record = self.managed()
        checkpoint(self.root, record['id'], self.entry(), expected_revision=0)
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], self.entry(), expected_revision=0)
        lock = self.put('.smart-test/project.lock', 'other writer')
        with self.assertRaises(ValueError):
            with writing(self.root):
                self.fail('must not acquire another writer lock')
        self.assertEqual(lock.read_text(), 'other writer')

    def test_paths_cannot_escape_or_follow_symlinks(self):
        self.policy()
        with self.assertRaises(ValueError):
            adopt(self.root, '../testing.md', 'Review')
        (self.root / 'linked.md').symlink_to(self.root / 'docs/testing.md')
        with self.assertRaises(ValueError):
            adopt(self.root, 'linked.md', 'Review')
        with self.assertRaises(ValueError):
            record_path(self.root, '../outside')

    def test_handover_preserves_assets_and_allows_re_adoption(self):
        self.managed()
        self.put('pom.xml', '<project/>')
        self.put('src/test/OrderTest.java', 'class OrderTest {}')
        record = begin(self.root, 'uninstall', 'current project handover')
        with self.assertRaises(ValueError):
            detach(self.root, record['id'], 'docs/testing.md', 'Release')
        checkpoint(self.root, record['id'], dict(stage='handover', status='COMPLETED',
                   summary='Native commands and outstanding findings documented',
                   evidence_paths=['docs/testing.md', 'pom.xml']))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        detach(self.root, record['id'], 'docs/testing.md', 'Team maintains native testing assets')
        self.assertEqual(status(self.root)['management'], 'RELEASED')
        for name, content in before.items():
            if name != Path('.smart-test/project.json'):
                self.assertEqual((self.root / name).read_bytes(), content)
        with self.assertRaises(ValueError):
            begin(self.root, 'changes', 'order')
        adopt(self.root, 'docs/testing.md', 'Review team changes and resume maintenance')
        self.assertEqual(status(self.root)['management'], 'MANAGED')
        self.assertEqual(status(self.root)['record_count'], 2)

    def test_handover_cannot_release_a_changed_or_unreferenced_document(self):
        record = self.managed('uninstall')
        self.put('docs/handover.md', '# Handover\nNative commands and pending work.\n')
        checkpoint(self.root, record['id'], dict(stage='handover', status='COMPLETED',
                   summary='Handover prepared', evidence_paths=['docs/testing.md']))
        with self.assertRaises(ValueError):
            detach(self.root, record['id'], 'docs/handover.md', 'Release')
        checkpoint(self.root, record['id'], dict(stage='handover', status='COMPLETED',
                   summary='Handover reviewed', evidence_paths=['docs/handover.md']))
        self.put('docs/handover.md', '# Handover\nChanged after review.\n')
        with self.assertRaises(ValueError):
            detach(self.root, record['id'], 'docs/handover.md', 'Release')
        self.assertEqual(status(self.root)['management'], 'MANAGED')

    def test_cli_status_on_unmanaged_repo_is_read_only(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'project.py'), '--repo', str(self.root),
                                 'status'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['management'], 'UNMANAGED')
        self.assertFalse((self.root / '.smart-test').exists())


    def test_later_unrun_verification_supersedes_an_earlier_pass(self):
        record, _ = self.verified()
        checkpoint(self.root, record['id'], dict(stage='verification', status='BLOCKED',
                   summary='Required integration execution blocked by unavailable isolated database',
                   verification='NOT_RUN'))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'NOT_RUN')
        self.assertEqual(row['status'], 'BLOCKED')
        saved = json.loads(record_path(self.root, record['id']).read_text())
        self.assertEqual(saved['events'][0]['verification'], 'PASS')

    def test_required_suites_keep_individual_results_and_missing_execution(self):
        record = self.managed('check')
        self.put('src/Order.java', 'class Order {}')
        manifest, _ = self.manifest()
        checkpoint(self.root, record['id'], dict(stage='verification', status='PARTIAL',
                   summary='Unit tests passed; transaction validation remains required', check_id='unit',
                   required_checks=['unit', 'integration'], verification='PASS',
                   evidence_paths=['src/Order.java'], run_manifests=[manifest]))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'NOT_RUN')
        checks = {c['id']: c for c in row['checks']}
        self.assertEqual(checks['unit']['current_verification'], 'PASS')
        self.assertEqual(checks['integration']['current_verification'], 'NOT_RUN')
        checkpoint(self.root, record['id'], dict(stage='verification', status='BLOCKED',
                   summary='Isolated database unavailable', check_id='integration', verification='NOT_RUN'))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'NOT_RUN')
        self.assertEqual(row['checks'][0]['current_verification'], 'PASS')

    def test_design_progress_does_not_erase_existing_verification(self):
        record, _ = self.verified()
        checkpoint(self.root, record['id'], dict(stage='design', status='IN_PROGRESS',
                   summary='Review additional boundary cases'))
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'PASS')

    def test_reviewed_policy_and_rerun_use_new_policy_without_rewriting_history(self):
        record, _ = self.verified()
        original = json.loads(record_path(self.root, record['id']).read_text())['events'][0]
        self.put('docs/testing.md', '# Testing policy\nReviewed revised testing command.\n')
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'STALE')
        manifest, _ = self.manifest()
        entry = dict(stage='verification', status='COMPLETED', summary='Rerun under reviewed policy',
                     verification='PASS', evidence_paths=['src/Order.java'], run_manifests=[manifest])
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], entry)
        adopt(self.root, 'docs/testing.md', 'Reviewed revised testing command and scope')
        checkpoint(self.root, record['id'], entry)
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'PASS')
        self.assertFalse(row['policy_changed'])
        self.assertEqual(json.loads(record_path(self.root, record['id']).read_text())['events'][0], original)

    def test_compile_success_is_build_pass_and_not_test_pass(self):
        record = self.managed('check')
        self.put('src/Order.java', 'class Order {}')
        stamp = datetime.now(timezone.utc).isoformat()
        manifest = '.smart-test/runs/compile/manifest.json'
        self.put(manifest, json.dumps({'schema_version': 1, 'required_run_ids': ['compile'], 'runs': [{
            'id': 'compile', 'kind': 'compile', 'argv': ['native-build', 'test-compile'],
            'started_at': stamp, 'finished_at': stamp, 'exit_code': 0, 'reports': []}]}))
        entry = dict(stage='verification', status='PARTIAL', summary='Compilation succeeded; tests not run',
                     verification='PASS', evidence_paths=['src/Order.java'], run_manifests=[manifest])
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], entry)
        checkpoint(self.root, record['id'], dict(entry, check_id='compile', verification_kind='build'))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'NOT_RUN')
        self.assertEqual(row['checks'][0]['current_verification'], 'PASS')
        self.assertEqual(row['checks'][0]['kind'], 'build')

    def test_optional_suite_failure_is_visible_without_replacing_required_scope(self):
        record, _ = self.verified()
        checkpoint(self.root, record['id'], dict(stage='verification', status='PARTIAL',
                   summary='Optional diagnostic failed', check_id='diagnostic', verification='FAILED',
                   required_checks=['overall']))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'PASS')
        self.assertEqual(row['checks'][1]['current_verification'], 'FAILED')
        self.assertFalse(row['checks'][1]['required'])


    def test_old_build_evidence_does_not_mark_fresh_required_tests_as_changed(self):
        record, _ = self.verified()
        checkpoint(self.root, record['id'], dict(stage='verification', status='PARTIAL',
                   summary='Optional build observation', check_id='compile', verification_kind='build',
                   verification='NOT_VERIFIED', required_checks=['overall']))
        self.put('docs/testing.md', '# Reviewed revised policy\nBoth scopes unchanged.\n')
        adopt(self.root, 'docs/testing.md', 'Reviewed policy wording')
        manifest, _ = self.manifest()
        checkpoint(self.root, record['id'], dict(stage='verification', status='COMPLETED',
                   summary='Fresh required test result', verification='PASS',
                   evidence_paths=['src/Order.java'], run_manifests=[manifest]))
        row = status(self.root)['records'][0]
        self.assertEqual(row['current_verification'], 'PASS')
        self.assertFalse(row['policy_changed'])
        self.assertTrue(next(c for c in row['checks'] if c['id'] == 'compile')['policy_changed'])


    def test_an_unrun_required_test_cannot_be_reclassified_as_build(self):
        record = self.managed('check')
        checkpoint(self.root, record['id'], dict(stage='verification', status='BLOCKED',
                   summary='Required unit suite has not run', check_id='unit', required_checks=['unit']))
        with self.assertRaises(ValueError):
            checkpoint(self.root, record['id'], dict(stage='verification', status='PARTIAL',
                       summary='Build observation must have a separate id', check_id='unit', verification_kind='build'))
        self.assertEqual(status(self.root)['records'][0]['checks'][0]['kind'], 'test')
        self.assertEqual(status(self.root)['records'][0]['current_verification'], 'NOT_RUN')
