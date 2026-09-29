#!/usr/bin/env python3
"""Validate the minimum traceability fields in smart_test JSON artifacts."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from catalog import VALIDATED_ARTIFACTS
from common import emit, relative_file

KNOWN = VALIDATED_ARTIFACTS


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _list(value):
    return isinstance(value, list)


def _issue(issues, artifact, kind):
    issues.append({'artifact': artifact, 'type': kind})


def _oracle_record(item, artifact, issues, prefix='ORACLE'):
    if item.get('status') == 'UNKNOWN':
        if not _text(item.get('reason')):
            _issue(issues, artifact, prefix + '_UNKNOWN_REASON_MISSING')
        if 'business_truth' in item:
            _issue(issues, artifact, prefix + '_UNKNOWN_WITH_TRUTH')
        return
    if type(item.get('business_truth')) is not bool:
        _issue(issues, artifact, prefix + '_TRUTH_INVALID')
    label = ('BUSINESS_TRUTH' if item.get('business_truth') is True else prefix)
    if prefix == 'REQUIRED_ITEM_ORACLE':
        label = prefix
    for key in ('source', 'claim'):
        if not _text(item.get(key)):
            _issue(issues, artifact, label + '_' + key.upper() + '_MISSING')


def _validate_oracle(data, artifact, issues):
    records = []
    if 'business_truth' in data or data.get('status') == 'UNKNOWN':
        records.append(data)
    for key in ('entries', 'items', 'claims', 'oracle'):
        value = data.get(key) if isinstance(data, dict) else None
        if key in data and not isinstance(value, list):
            _issue(issues, artifact, 'ORACLE_ENTRIES_INVALID')
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
                else:
                    _issue(issues, artifact, 'ORACLE_ENTRY_INVALID')
    if not records:
        _issue(issues, artifact, 'ORACLE_ENTRIES_MISSING')
    for item in records:
        _oracle_record(item, artifact, issues)


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
        if type(item.get('required')) is not bool:
            _issue(issues, artifact, 'TEST_PLAN_REQUIRED_INVALID')
        if item.get('required') is not True:
            continue
        for key in ('id', 'target', 'risk', 'suite'):
            if not _text(item.get(key)):
                _issue(issues, artifact, 'REQUIRED_ITEM_' + key.upper() + '_MISSING')
        blocked = (item.get('status') == 'BLOCKED' and _list(item.get('blocking_ids'))
                   and bool(item['blocking_ids']) and all(_text(v) for v in item['blocking_ids']))
        if 'blocking_ids' in item and (not _list(item['blocking_ids'])
                                       or any(not _text(v) for v in item['blocking_ids'])):
            _issue(issues, artifact, 'PLAN_BLOCKING_IDS_INVALID')
        if item.get('status') in {'PASS', 'READY'} and item.get('blocking_ids'):
            _issue(issues, artifact, 'PLAN_READY_WITH_BLOCKERS')
        if not _list(item.get('assertions')) or (not item['assertions'] and not blocked):
            _issue(issues, artifact, 'REQUIRED_ITEM_ASSERTIONS_MISSING')
        elif any(not _text(value) for value in item['assertions']):
            _issue(issues, artifact, 'REQUIRED_ITEM_ASSERTIONS_INVALID')
        oracle = item.get('oracle')
        if not isinstance(oracle, dict):
            _issue(issues, artifact, 'REQUIRED_ITEM_ORACLE_MISSING')
        else:
            _oracle_record(oracle, artifact, issues, 'REQUIRED_ITEM_ORACLE')
            if oracle.get('status') == 'UNKNOWN' and not blocked:
                _issue(issues, artifact, 'UNKNOWN_ORACLE_REQUIRES_BLOCKED_ITEM')


def _validate_context(data, artifact, issues, root):
    data = data.get('effective_context', data)
    if not isinstance(data, dict):
        _issue(issues, artifact, 'ROOT_OBJECT_REQUIRED')
        return
    if not {'directive_ids', 'decision_ids', 'scope', 'constraints', 'conflicts', 'unresolved'}.intersection(data):
        _issue(issues, artifact, 'CONTEXT_FIELDS_MISSING')
    for key in ('scope', 'constraints'):
        if key in data and not isinstance(data[key], dict):
            _issue(issues, artifact, key.upper() + '_INVALID')
    for key in ('conflicts', 'unresolved'):
        if key in data and not _list(data[key]):
            _issue(issues, artifact, key.upper() + '_INVALID')
    references = {}
    for key in ('directive_ids', 'decision_ids'):
        if key in data and (not _list(data[key]) or any(not _text(value) for value in data[key])):
            _issue(issues, artifact, key.upper() + '_INVALID')
        elif data.get(key):
            references[key] = data[key]
    if not references:
        return
    try:
        state_path = relative_file(root, '.smart-test/state.json', must_exist=True)
        state = json.loads(state_path.read_text())
        if not isinstance(state, dict) or state.get('schema_version') != 1 or state.get('example_only'):
            raise ValueError('invalid ledger')
        from state import reconcile
        reconcile(state, root)  # read-only freshness check; never persist validation
        for key, ids in references.items():
            bucket, status = ('directives', 'ACTIVE') if key == 'directive_ids' else ('decisions', 'EFFECTIVE')
            records = {item['id']: item for item in state[bucket]}
            for identity in ids:
                if identity not in records:
                    _issue(issues, artifact, key.upper() + '_UNKNOWN_REFERENCE')
                elif records[identity].get('status') != status:
                    _issue(issues, artifact, key.upper() + '_INACTIVE_REFERENCE')
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        _issue(issues, artifact, 'REFERENCED_STATE_MISSING_OR_INVALID')


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
        elif any(not (_text(item) or (isinstance(item, dict) and _text(item.get('suite')))) for item in suites):
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
    allowed = {'NOT_STARTED', 'PROPOSED', 'READY', 'PARTIAL', 'BLOCKED', 'FAILED',
               'PASS', 'STALE', 'NOT_VERIFIED', 'UNKNOWN', 'NOT_APPLICABLE', 'NOT_RUN'}
    children = []
    if 'stages' in data:
        if not isinstance(data['stages'], dict) or not data['stages']:
            _issue(issues, artifact, 'STATUS_STAGES_INVALID')
        else:
            children = list(data['stages'].values())
    else:
        # Legacy per-phase objects at the root remain supported.
        children = [value for value in data.values()
                    if isinstance(value, dict) and ('status' in value or 'blocking_ids' in value)]
    status = data.get('status')
    if status is not None and (not isinstance(status, str) or status not in allowed):
        _issue(issues, artifact, 'STATUS_INVALID')
    if status is None and not children:
        _issue(issues, artifact, 'STATUS_MISSING')
    has_blockers = False
    for key in ('blocking_ids', 'blockers'):
        if key in data and not _list(data[key]):
            _issue(issues, artifact, key.upper() + '_INVALID')
        has_blockers = has_blockers or bool(data.get(key))
    if status == 'PASS' and has_blockers:
        _issue(issues, artifact, 'PASS_WITH_BLOCKERS')
    unfinished = status not in {None, 'PASS', 'NOT_APPLICABLE'} if isinstance(status, (str, type(None))) else True
    for child in children:
        if not isinstance(child, dict):
            _issue(issues, artifact, 'STATUS_STAGE_INVALID')
            unfinished = True
            continue
        child_unfinished = _validate_status(child, artifact, issues)
        if status == 'PASS' and child_unfinished:
            _issue(issues, artifact, 'PASS_WITH_BLOCKERS')
        unfinished = unfinished or child_unfinished
    return unfinished or has_blockers


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
            _validate_context(data, name, issues, root)
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
