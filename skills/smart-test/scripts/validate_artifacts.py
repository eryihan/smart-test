#!/usr/bin/env python3
"""Validate the minimum traceability fields in Smart-Test JSON artifacts."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import emit, relative_file


KNOWN = ('business-oracle.json', 'effective-context.json', 'test-policy.json',
         'test-plan.json', 'status.json')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _list(value):
    return isinstance(value, list)


def _issue(issues, artifact, kind):
    issues.append({'artifact': artifact, 'type': kind})


def _validate_oracle(data, artifact, issues):
    records = []
    if isinstance(data, dict) and 'business_truth' in data:
        records.append(data)
    for key in ('entries', 'items', 'claims', 'oracle'):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
                else:
                    _issue(issues, artifact, 'ORACLE_ENTRY_INVALID')
    for item in records:
        if item.get('business_truth') is True:
            if not _text(item.get('source')):
                _issue(issues, artifact, 'BUSINESS_TRUTH_SOURCE_MISSING')
            if not _text(item.get('claim')):
                _issue(issues, artifact, 'BUSINESS_TRUTH_CLAIM_MISSING')


def _validate_plan(data, artifact, issues):
    plan = data.get('test_plan', data)
    if not isinstance(plan, dict):
        _issue(issues, artifact, 'TEST_PLAN_INVALID')
        return
    if 'items' not in plan:
        _issue(issues, artifact, 'TEST_PLAN_ITEMS_MISSING')
        return
    items = plan['items']
    if not _list(items):
        _issue(issues, artifact, 'TEST_PLAN_ITEMS_INVALID')
        return
    for item in items:
        if not isinstance(item, dict):
            _issue(issues, artifact, 'TEST_PLAN_ITEM_INVALID')
            continue
        if item.get('required') is not True:
            continue
        for key in ('id', 'target', 'risk', 'suite'):
            if not _text(item.get(key)):
                _issue(issues, artifact, 'REQUIRED_ITEM_' + key.upper() + '_MISSING')
        if not _list(item.get('assertions')) or not item['assertions']:
            _issue(issues, artifact, 'REQUIRED_ITEM_ASSERTIONS_MISSING')
        oracle = item.get('oracle')
        if not isinstance(oracle, dict):
            _issue(issues, artifact, 'REQUIRED_ITEM_ORACLE_MISSING')
        elif oracle.get('business_truth') is True:
            if not _text(oracle.get('source')):
                _issue(issues, artifact, 'REQUIRED_ITEM_ORACLE_SOURCE_MISSING')
            if not _text(oracle.get('claim')):
                _issue(issues, artifact, 'REQUIRED_ITEM_ORACLE_CLAIM_MISSING')


def _validate_context(data, artifact, issues):
    if not isinstance(data, dict):
        _issue(issues, artifact, 'ROOT_OBJECT_REQUIRED')
        return
    for key in ('directive_ids', 'decision_ids'):
        if key in data and (not _list(data[key]) or any(not _text(value) for value in data[key])):
            _issue(issues, artifact, key.upper() + '_INVALID')


def _validate_policy(data, artifact, issues):
    """Check the small, stable policy shape without imposing a full schema."""
    if not isinstance(data, dict):
        _issue(issues, artifact, 'ROOT_OBJECT_REQUIRED')
        return

    fields = {
        'required_suites', 'verification', 'environment', 'coverage',
        'production_code_modify', 'production_change_boundary',
    }
    if not fields.intersection(data):
        _issue(issues, artifact, 'POLICY_FIELDS_MISSING')

    suites = data.get('required_suites')
    if 'required_suites' in data:
        if not _list(suites):
            _issue(issues, artifact, 'REQUIRED_SUITES_INVALID')
        elif any(not (_text(item) or isinstance(item, dict)) for item in suites):
            _issue(issues, artifact, 'REQUIRED_SUITE_ENTRY_INVALID')

    for key in ('verification', 'environment', 'coverage', 'production_change_boundary'):
        if key in data and not isinstance(data[key], dict):
            _issue(issues, artifact, key.upper() + '_INVALID')

    if 'production_code_modify' in data and not isinstance(data['production_code_modify'], bool):
        _issue(issues, artifact, 'PRODUCTION_CODE_MODIFY_INVALID')

    coverage = data.get('coverage')
    if not isinstance(coverage, dict):
        return
    modes = {'UNSPECIFIED', 'REPORT_ONLY', 'OVERALL', 'INCREMENTAL', 'BOTH'}
    metrics = {'LINE', 'BRANCH', 'INSTRUCTION', 'METHOD', 'CLASS'}
    if 'mode' in coverage and (not isinstance(coverage['mode'], str) or coverage['mode'] not in modes):
        _issue(issues, artifact, 'COVERAGE_MODE_INVALID')
    if 'metric' in coverage and (not isinstance(coverage['metric'], str) or coverage['metric'] not in metrics):
        _issue(issues, artifact, 'COVERAGE_METRIC_INVALID')
    if 'threshold' in coverage:
        threshold = coverage['threshold']
        if (threshold is not None and
                (isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or
                 not 0 <= threshold <= 100)):
            _issue(issues, artifact, 'COVERAGE_THRESHOLD_INVALID')
    if 'scope' in coverage and not isinstance(coverage['scope'], dict):
        _issue(issues, artifact, 'COVERAGE_SCOPE_INVALID')
    if 'baseline' in coverage and coverage['baseline'] is not None and not _text(coverage['baseline']):
        _issue(issues, artifact, 'COVERAGE_BASELINE_INVALID')


def _validate_status(data, artifact, issues):
    if not isinstance(data, dict):
        _issue(issues, artifact, 'ROOT_OBJECT_REQUIRED')
        return
    if data.get('status') == 'PASS':
        if data.get('blocking_ids') or data.get('blockers'):
            _issue(issues, artifact, 'PASS_WITH_BLOCKERS')


def validate(root, required=()):
    root = Path(root).resolve()
    issues, checked, missing = [], [], []
    requested = list(required) if required else list(KNOWN)
    required_set = set(required)
    for name in requested:
        if name not in KNOWN:
            raise ValueError('unsupported artifact: ' + name)
        path = relative_file(root, '.smart-test/' + name)
        if not path.exists():
            missing.append(name)
            if name in required_set:
                _issue(issues, name, 'MISSING_REQUIRED_ARTIFACT')
            continue
        checked.append(name)
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            _issue(issues, name, 'INVALID_JSON')
            continue
        if isinstance(data, dict) and data.get('example_only') is True:
            _issue(issues, name, 'EXAMPLE_ARTIFACT')
        if not isinstance(data, dict):
            _issue(issues, name, 'ROOT_OBJECT_REQUIRED')
            continue
        if name == 'business-oracle.json':
            _validate_oracle(data, name, issues)
        elif name == 'test-plan.json':
            _validate_plan(data, name, issues)
        elif name == 'effective-context.json':
            _validate_context(data, name, issues)
        elif name == 'test-policy.json':
            _validate_policy(data, name, issues)
        elif name == 'status.json':
            _validate_status(data, name, issues)
    return {'status': 'VALID' if not issues else 'INVALID', 'checked': checked,
            'missing': missing, 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--require', dest='required', action='append', default=[],
                        help='require one known artifact; may be repeated')
    args = parser.parse_args()
    try:
        if not args.repo.is_dir():
            raise ValueError('repository does not exist')
        result = validate(args.repo, args.required)
        emit(result)
        return 0 if result['status'] == 'VALID' else 1
    except (ValueError, OSError, TypeError) as exc:
        emit({'error': str(exc)})
        return 2


if __name__ == '__main__':
    sys.exit(main())
