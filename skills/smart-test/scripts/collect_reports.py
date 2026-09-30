#!/usr/bin/env python3
"""Check fresh JUnit XML against an observed execution manifest; never execute tests."""
import argparse
from datetime import datetime
import glob
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
from common import emit, relative_file


def timestamp(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('timestamps require an explicit timezone')
    return date.timestamp()


def parse_report(path):
    data = path.read_bytes()
    if len(data) > 20_000_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('oversized report or XML declarations are not supported')
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag not in {'testsuite', 'testsuites'}:
        raise ValueError('not a JUnit XML report')
    cases = list(root.iter('testcase'))
    counts = {'tests': len(cases), 'failed': 0, 'errors': 0, 'skipped': 0}
    identities = []
    for case in cases:
        if case.find('skipped') is None:
            identities.append(case.get('classname', '') + '#' + case.get('name', ''))
        counts['failed'] += case.find('failure') is not None
        counts['errors'] += case.find('error') is not None
        counts['skipped'] += case.find('skipped') is not None
    # Suite-level failures (e.g. discovery failures) can exist without testcase nodes.
    declared = {'tests': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    for suite in root.iter('testsuite'):
        if suite.find('testsuite') is not None:
            continue  # avoid double-counting nested suite totals
        for key, attr in [('tests', 'tests'), ('failed', 'failures'), ('errors', 'errors'), ('skipped', 'skipped')]:
            value = int(suite.get(attr, 0))
            if value < 0:
                raise ValueError('negative test counts')
            declared[key] += value
    counts['failed'] = max(counts['failed'], declared['failed'])
    counts['errors'] = max(counts['errors'], declared['errors'])
    counts['skipped'] = max(counts['skipped'], declared['skipped'])
    return counts, identities, declared['tests'] > counts['tests']


def collect(root, manifest):
    if not isinstance(manifest, dict) or manifest.get('example_only'):
        raise ValueError('use an actual execution manifest, not a format example')
    if manifest.get('schema_version') != 1:
        raise ValueError('unsupported manifest schema')
    runs = manifest.get('runs')
    required = manifest.get('required_run_ids')
    if not isinstance(runs, list) or not runs or not isinstance(required, list) or not required:
        raise ValueError('runs and required_run_ids must be nonempty lists')
    identities = [run['id'] for run in runs]
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate run ids')
    issues = []
    totals = {'tests': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    if set(required) - set(identities):
        issues.append({'type': 'REQUIRED_RUN_MISSING', 'runs': sorted(set(required) - set(identities))})
    results = []
    required_test_runs = set()
    seen = set()
    for run in runs:
        kind = run.get('kind', 'test')
        if not isinstance(kind, str) or not kind:
            raise ValueError('run kind must be a nonempty string')
        requires_test_report = run.get('requires_test_report', kind == 'test')
        if not isinstance(requires_test_report, bool):
            raise ValueError('requires_test_report must be a boolean')
        argv = run.get('argv')
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
            raise ValueError('argv must be the observed command as a string array')
        if not isinstance(run.get('exit_code'), int) or isinstance(run['exit_code'], bool):
            raise ValueError('exit_code must be an observed integer')
        start, end = timestamp(run['started_at']), timestamp(run['finished_at'])
        if end < start:
            raise ValueError('finished_at precedes started_at')
        if run['exit_code'] != 0:
            issues.append({'type': 'COMMAND_FAILED', 'run': run['id'], 'exit_code': run['exit_code']})
        groups = run.get('reports', [])
        if run['id'] in required and requires_test_report:
            required_test_runs.add(run['id'])
        if run['id'] in required and requires_test_report and not any(g.get('required') is True for g in groups):
            issues.append({'type': 'NO_REQUIRED_REPORT_GROUP', 'run': run['id']})
        group_results = []
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError('report group must be an object')
            allowed = {'pattern', 'required', 'min_tests', 'allow_skipped', 'expected_test_ids'}
            if set(group) - allowed:
                raise ValueError('unsupported report group fields')
            pattern = group.get('pattern')
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError('report pattern must be a nonempty string')
            relative_file(root, pattern)
            required_group = group.get('required', False)
            if not isinstance(required_group, bool):
                raise ValueError('report required must be boolean')
            allow_skipped = group.get('allow_skipped', False)
            if not isinstance(allow_skipped, bool):
                raise ValueError('allow_skipped must be boolean')
            minimum = group.get('min_tests', 1)
            if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
                raise ValueError('min_tests must be a positive integer')
            expected = group.get('expected_test_ids', [])
            if (not isinstance(expected, list)
                    or any(not isinstance(item, str) or not item.strip() for item in expected)
                    or len(set(expected)) != len(expected)):
                raise ValueError('expected_test_ids must be unique nonempty strings')
            counts = dict.fromkeys(totals, 0)
            test_names = set()
            paths = []
            for name in sorted(glob.glob(str(root / pattern), recursive=True)):
                rel = str(Path(name).relative_to(root))
                path = relative_file(root, rel, must_exist=True)
                if path in seen:
                    issues.append({'type': 'DUPLICATE_REPORT', 'path': rel})
                    continue
                seen.add(path)
                paths.append(rel)
                if not start <= path.stat().st_mtime <= end:
                    issues.append({'type': 'STALE_OR_OUTSIDE_RUN_REPORT', 'path': rel, 'run': run['id']})
                    continue
                try:
                    result, names, incomplete = parse_report(path)
                except (ET.ParseError, ValueError, OSError):
                    issues.append({'type': 'MALFORMED_REPORT', 'path': rel})
                    continue
                if incomplete:
                    issues.append({'type': 'INCOMPLETE_TESTCASE_EVIDENCE', 'path': rel})
                for key in counts:
                    counts[key] += result[key]
                test_names.update(names)
            if required_group:
                executed = counts['tests'] - counts['skipped']
                if executed < minimum:
                    issues.append({'type': 'REQUIRED_TESTS_MISSING', 'run': run['id'], 'pattern': pattern})
                if counts['skipped'] and not allow_skipped:
                    issues.append({'type': 'REQUIRED_TESTS_SKIPPED', 'run': run['id'], 'pattern': pattern})
                missing = sorted(set(expected) - test_names)
                if missing:
                    issues.append({'type': 'EXPECTED_TEST_IDS_MISSING', 'tests': missing})
            for key in totals:
                totals[key] += counts[key]
            group_results.append({'pattern': pattern, 'required': required_group,
                                  'counts': counts, 'paths': paths})
        results.append({'id': run['id'], 'kind': kind, 'requires_test_report': requires_test_report,
                        'exit_code': run['exit_code'], 'duration_seconds': end - start,
                        'groups': group_results})
    if totals['failed'] or totals['errors']:
        issues.append({'type': 'TEST_FAILURES'})
    if required_test_runs and totals['tests'] == 0:
        issues.append({'type': 'ZERO_TESTS'})
    # Do not copy blocker prose or command arguments that may contain credentials.
    blockers = manifest.get('blockers', [])
    if not isinstance(blockers, list):
        raise ValueError('blockers must be a list')
    if blockers:
        issues.append({'type': 'UNRESOLVED_BLOCKERS', 'count': len(blockers)})
    return {'schema_version': 1, 'status': 'EVIDENCE_PASS' if not issues else 'NOT_VERIFIED',
            'counts': totals, 'runs': results, 'issues': issues,
            'scope': 'Execution evidence only. Agent must also verify oracle, risk coverage, quality and CI prerequisites.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.repo.is_dir():
            raise ValueError('repository does not exist')
        result = collect(args.repo.resolve(), json.loads(args.manifest.read_text()))
        emit(result)
        return 0 if result['status'] == 'EVIDENCE_PASS' else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'error': str(exc)})
        return 2


if __name__ == '__main__':
    sys.exit(main())
