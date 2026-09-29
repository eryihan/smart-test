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


def _records(data, keys):
    records = []
    if isinstance(data, dict) and 'business_truth' in data:
        records.append(data)
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _issue(issues, artifact, kind):
    issues.append({'artifact': artifact, 'type': kind})


def _validate_oracle(data, artifact, issues):
    for item in _records(data, ('entries', 'items', 'claims', 'oracle')):
        if item.get('business_truth') is True:
            if not _text(item.get('source')):
                _issue(issues, artifact, 'BUSINESS_TRUTH_SOURCE_MISSING')
            if not _text(item.get('claim')):
                _issue(issues, artifact, 'BUSINESS_TRUTH_CLAIM_MISSING')


def _validate_plan(data, artifact, issues):
    plan = data.get('test_plan', data) if isinstance(data, dict) else {}
    items = plan.get('items', []) if isinstance(plan, dict) else []
    if not _list(items):
        _issue(issues, artifact, 'TEST_PLAN_ITEMS_INVALID')
        return
    for item in items:
        if not isinstance(item, dict) or item.get('required') is not True:
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


def _validate_status(data, artifact, issues):
    if not isinstance(data, dict):
        _issue(issues, artifact, 'ROOT_OBJECT_REQUIRED')
        return
    if data.get('status') == 'PASS':
        blockers = data.get('blocking_ids', data.get('blockers', []))
        if blockers:
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
        if name == 'business-oracle.json':
            _validate_oracle(data, name, issues)
        elif name == 'test-plan.json':
            _validate_plan(data, name, issues)
        elif name == 'effective-context.json':
            _validate_context(data, name, issues)
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
