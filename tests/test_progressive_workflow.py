"""Regression checks for optional artifacts and evidence-only decision review."""
import argparse
import copy
import json
import subprocess
import sys
import unittest

import test_helpers as helpers
from state import apply, initial
from validate_artifacts import validate


class EvidenceReviewTests(helpers.Workspace):
    def setUp(self):
        super().setUp()
        self.state = initial()
        self.put('pom.xml', '<project/>')

    def action(self, command, payload=None, **kwargs):
        return apply(self.state, self.root, argparse.Namespace(command=command, **kwargs), payload)

    def approve(self, identity='unit', dependencies=()):
        self.action('propose', {'id': identity, 'kind': 'strategy', 'summary': 'Reuse JUnit',
                               'topics': ['unit'], 'evidence_paths': ['pom.xml'],
                               'depends_on': list(dependencies)})
        self.action('resolve', id=identity, action='confirm', source='user', evidence='User authorized existing unit strategy')

    def test_review_preserves_authorization_and_version_but_records_new_evidence(self):
        self.approve()
        before = copy.deepcopy(self.state['decisions'][0])
        self.put('pom.xml', '<project><!-- comment only --></project>')
        self.action('reconcile')
        self.assertEqual(self.state['decisions'][0]['status'], 'INVALIDATED')
        result = self.action('revalidate', id='unit', evidence='Diff only adds a comment; strategy and authorization unchanged')
        after = result['decision']
        self.assertEqual(after['status'], 'EFFECTIVE')
        self.assertEqual(after['approval'], before['approval'])
        self.assertEqual(after['version'], before['version'])
        self.assertNotEqual(after['evidence_fingerprints'], before['evidence_fingerprints'])
        self.assertEqual(self.state['events'][-1]['previous']['evidence_fingerprints'], before['evidence_fingerprints'])
        self.assertFalse(self.action('reconcile')['invalidated'])

    def test_dependencies_must_be_reviewed_first(self):
        self.approve()
        self.approve('ci', ['unit'])
        self.put('pom.xml', '<project><!-- comment --></project>')
        with self.assertRaises(ValueError):
            self.action('revalidate', id='ci', evidence='Reviewed')
        self.action('revalidate', id='unit', evidence='Same strategy and authorization')
        self.action('revalidate', id='ci', evidence='CI command and authorization unchanged')
        self.assertTrue(all(d['status'] == 'EFFECTIVE' for d in self.state['decisions']))

    def test_cli_review_dry_run_does_not_persist_or_create_lock(self):
        self.approve()
        ledger = self.put('.smart-test/state.json', json.dumps(self.state))
        before = ledger.read_bytes()
        self.put('pom.xml', '<project><!-- comment only --></project>')
        command = [sys.executable, str(helpers.SCRIPTS / 'state.py'), '--repo', str(self.root)]
        review = ['revalidate', '--id', 'unit', '--evidence', 'Compared diff; only a comment, same strategy and authorization']
        result = json.loads(subprocess.check_output(command + ['--dry-run'] + review))
        self.assertFalse(result['persisted'])
        self.assertEqual(ledger.read_bytes(), before)
        self.assertFalse((self.root / '.smart-test/state.lock').exists())
        result = json.loads(subprocess.check_output(command + review))
        self.assertTrue(result['persisted'])
        stored = json.loads(ledger.read_text())['decisions'][0]
        self.assertEqual(stored['status'], 'EFFECTIVE')
        self.assertEqual(stored['approval'], self.state['decisions'][0]['approval'])
        self.assertNotEqual(stored['evidence_fingerprints'], self.state['decisions'][0]['evidence_fingerprints'])
        self.assertFalse((self.root / '.smart-test/state.lock').exists())

    def test_constraint_change_cannot_be_revalidated_after_file_change(self):
        self.approve()
        self.approve('ci', ['unit'])
        self.put('pom.xml', '<project><!-- comment --></project>')
        self.action('reconcile')
        self.action('invalidate', topics=['unit'], reason='User changed the allowed test framework')
        for decision in self.state['decisions']:
            self.assertEqual(decision['invalidation_kind'], 'semantic')
            with self.assertRaises(ValueError):
                self.action('revalidate', id=decision['id'], evidence='File still looks similar')

    def test_review_cannot_approve_pending_rejected_or_legacy_invalidated_decisions(self):
        for status in ('PROPOSED', 'REJECTED', 'INVALIDATED'):
            with self.subTest(status=status):
                self.state = initial()
                self.approve()
                item = self.state['decisions'][0]
                item['status'] = status
                item.pop('invalidation_kind', None)
                with self.assertRaises(ValueError):
                    self.action('revalidate', id='unit', evidence='Not new authorization')
        self.state = initial()
        self.approve()
        self.state['decisions'][0].pop('approval')
        self.put('pom.xml', '<changed/>')
        with self.assertRaises(ValueError):
            self.action('revalidate', id='unit', evidence='No prior authorization')


class FocusedArtifactTests(helpers.Workspace):
    def put_json(self, name, data):
        return self.put('.smart-test/' + name, json.dumps(data))

    def plan_item(self):
        return {'id': 'T-1', 'target': 'Payment#pay', 'risk': 'HIGH', 'suite': 'unit',
                'required': True, 'assertions': ['Reject negative amount'],
                'oracle': {'business_truth': True, 'source': 'docs/rules.md', 'claim': 'Reject negative amount'}}

    def test_local_plan_does_not_require_unrelated_governance(self):
        self.put_json('test-plan.json', {'items': [self.plan_item()]})
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'VALID')
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')))
        self.assertFalse((self.root / '.smart-test/state.json').exists())

    def test_empty_oracles_null_assertions_and_nonboolean_required_are_invalid(self):
        for key, value in [('oracle', {}), ('assertions', [None]), ('assertions', [' ']),
                           ('required', 'true'), ('required', 1)]:
            with self.subTest(key=key, value=value):
                item = self.plan_item()
                item[key] = value
                self.put_json('test-plan.json', {'items': [item]})
                self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'INVALID')
        for oracle in ({}, {'entries': []}, {'entries': {}}, {'entries': [{}]}):
            self.put_json('business-oracle.json', oracle)
            self.assertEqual(validate(self.root, ['business-oracle.json'])['status'], 'INVALID')

    def test_characterization_keeps_observation_source_and_claim(self):
        item = self.plan_item()
        item['oracle'] = {'business_truth': False, 'type': 'current_behavior',
                          'source': 'LegacyFormatter.java at inspected revision', 'claim': 'Observed empty string for null'}
        self.put_json('test-plan.json', {'items': [item]})
        self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'VALID')
        del item['oracle']['source']
        self.put_json('test-plan.json', {'items': [item]})
        self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'INVALID')

    def test_unknown_oracle_can_be_delivered_only_as_explicitly_blocked_item(self):
        item = self.plan_item()
        item.update(oracle={'status': 'UNKNOWN', 'reason': 'No confirmed rounding rule'},
                    status='BLOCKED', blocking_ids=['RULE-1'], assertions=[])
        self.put_json('test-plan.json', {'items': [item]})
        self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'VALID')
        for status in ('READY', 'PASS', None):
            item['status'] = status
            self.put_json('test-plan.json', {'items': [item]})
            self.assertEqual(validate(self.root, ['test-plan.json'])['status'], 'INVALID')
        self.put_json('business-oracle.json', {'status': 'UNKNOWN', 'reason': 'Missing business rule'})
        self.assertEqual(validate(self.root, ['business-oracle.json'])['status'], 'VALID')

    def test_nested_and_legacy_statuses_do_not_hide_blockers(self):
        bad = [
            {'stages': {'verification': {'status': 'PASS', 'blocking_ids': ['DB-1']}}},
            {'verification': {'status': 'PASS', 'blockers': ['DB-1']}},
            {'status': 'PASS', 'stages': {'unit': {'status': 'PASS'}, 'integration': {'status': 'BLOCKED'}}},
            {'status': 'PASS', 'stages': {'integration': {'status': 'NOT_RUN'}}},
            {'status': 'PASS', 'blockers': 'wrong type'}, {}, {'stages': {'unit': 'PASS'}},
            {'status': []}, {'status': 'PASS', 'stages': {'unit': {}}},
        ]
        for data in bad:
            with self.subTest(data=data):
                self.put_json('status.json', data)
                self.assertEqual(validate(self.root, ['status.json'])['status'], 'INVALID')
        for data in [
            {'status': 'PARTIAL', 'stages': {'unit': {'status': 'PASS'}, 'integration': {'status': 'BLOCKED', 'blocking_ids': ['DB-1']}}},
            {'stages': {'unit': {'status': 'PASS'}, 'integration': {'status': 'NOT_RUN'}}},
            {'status': 'PASS', 'stages': {'unit': {'status': 'PASS'}, 'coverage': {'status': 'NOT_APPLICABLE'}}},
        ]:
            self.put_json('status.json', data)
            self.assertEqual(validate(self.root, ['status.json'])['status'], 'VALID')

    def test_context_without_ids_needs_no_ledger_but_dangling_ids_fail(self):
        self.put_json('effective-context.json', {'constraints': {'docker_allowed': False}})
        self.assertEqual(validate(self.root, ['effective-context.json'])['status'], 'VALID')
        self.put_json('effective-context.json', {'decision_ids': ['missing']})
        self.assertEqual(validate(self.root, ['effective-context.json'])['status'], 'INVALID')
        self.put_json('state.json', initial())
        self.assertEqual(validate(self.root, ['effective-context.json'])['status'], 'INVALID')

    def test_context_checks_current_decision_evidence_without_writing_ledger(self):
        state = initial()
        self.put('pom.xml', '<project/>')
        apply(state, self.root, argparse.Namespace(command='propose'), {
            'id': 'unit', 'kind': 'strategy', 'summary': 'JUnit', 'topics': ['unit'],
            'evidence_paths': ['pom.xml'], 'depends_on': []})
        apply(state, self.root, argparse.Namespace(command='resolve', id='unit', action='confirm',
                                                   source='user', evidence='Actual authorization'))
        ledger = self.put_json('state.json', state)
        self.put_json('effective-context.json', {'effective_context': {'decision_ids': ['unit']}})
        self.assertEqual(validate(self.root, ['effective-context.json'])['status'], 'VALID')
        before = ledger.read_bytes()
        self.put('pom.xml', '<changed/>')
        self.assertEqual(validate(self.root, ['effective-context.json'])['status'], 'INVALID')
        self.assertEqual(ledger.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
