#!/usr/bin/env python3
"""Maintain project testing ownership and work records without executing tests."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.dont_write_bytecode = True
from catalog import WORKFLOWS
from collect_reports import collect
from common import atomic_json, digest, emit, git, relative_file

SCHEMA = 1
PROJECT = '.smart-test/project.json'
RECORDS = '.smart-test/records'
WORK = {'init', 'scan', 'changes', 'check', 'pipeline', 'uninstall'}
STAGES = {'discovery', 'design', 'implementation', 'verification', 'handover', 'installation'}
PROGRESS = {'IN_PROGRESS', 'COMPLETED', 'PARTIAL', 'BLOCKED', 'FAILED'}
VERIFICATION = {'NOT_RUN', 'PASS', 'PARTIAL', 'FAILED', 'NOT_VERIFIED'}


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be a nonempty string')
    return value


def load(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA:
        raise ValueError('unsupported project or record format')
    return value


def policy(root, name):
    root = Path(root).resolve()
    path = relative_file(root, name, must_exist=True)
    if path.suffix.lower() != '.md' or not path.read_text(encoding='utf-8').strip():
        raise ValueError('testing policy must be a nonempty Markdown file')
    return {'path': path.relative_to(root).as_posix(), 'sha256': digest(path)}


def record_path(root, identity):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', identity):
        raise ValueError('invalid record id')
    return relative_file(root, RECORDS + '/' + identity + '.json')


def head(root):
    try:
        return git(root, 'rev-parse', 'HEAD').decode().strip()
    except (ValueError, OSError):
        return None


def version():
    return json.loads((Path(__file__).resolve().parents[1] / 'version.json').read_text())['smart_test_version']


@contextmanager
def writing(root):
    lock = relative_file(root, '.smart-test/project.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('project is locked; inspect the other writer before retrying')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def adopt(root, name, reason):
    selected = policy(root, name)
    text(reason, 'review reason')
    path = relative_file(root, PROJECT)
    data = load(path) if path.exists() else {
        'schema_version': SCHEMA, 'revision': 0, 'events': [],
    }
    if data.get('management') == 'MANAGED' and data.get('policy') == selected:
        return data
    data['events'].append({'at': now(), 'action': 'ADOPT' if not data.get('policy') else 'REVIEW',
                           'previous_policy': data.get('policy'), 'policy': selected, 'reason': reason})
    data.update(management='MANAGED', policy=selected, revision=data['revision'] + 1)
    atomic_json(path, data)
    return data


def begin(root, workflow, scope, name=None, reason=None):
    if workflow not in WORK:
        raise ValueError('this workflow does not create a project work record')
    text(scope, 'scope')
    path = relative_file(root, PROJECT)
    data = load(path) if path.exists() else None
    if name:
        data = adopt(root, name, reason)
    if not data or data.get('management') != 'MANAGED':
        raise ValueError('review the project testing policy and provide --policy and --reason')
    if policy(root, data['policy']['path']) != data['policy']:
        raise ValueError('testing policy changed; review it with adopt before starting work')
    identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
    record = {'schema_version': SCHEMA, 'id': identity, 'workflow': workflow, 'scope': scope,
              'created_at': now(), 'skill_version': version(), 'policy': data['policy'],
              'git_head': head(root), 'revision': 0, 'events': []}
    atomic_json(record_path(root, identity), record)
    return record


def fingerprints(root, names):
    root = Path(root).resolve()
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError('evidence_paths must be a string array')
    result = {}
    for name in names:
        path = relative_file(root, name, must_exist=True)
        result[path.relative_to(root).as_posix()] = digest(path)
    return result


def checkpoint(root, identity, entry, expected_revision=None):
    path = record_path(root, identity)
    record = load(path)
    if expected_revision is not None and record['revision'] != expected_revision:
        raise ValueError('record changed; reread it before appending')
    if not isinstance(entry, dict) or set(entry) - {
        'stage', 'status', 'summary', 'next_step', 'evidence_paths', 'run_manifests', 'verification', 'findings',
        'check_id', 'verification_kind', 'required_checks',
    }:
        raise ValueError('unsupported work record fields')
    stage, progress = entry.get('stage'), entry.get('status', 'IN_PROGRESS')
    if stage not in STAGES or progress not in PROGRESS:
        raise ValueError('invalid stage or work status')
    text(entry.get('summary'), 'summary')
    if 'next_step' in entry:
        text(entry['next_step'], 'next_step')
    verified = entry.get('verification', 'NOT_RUN')
    if verified not in VERIFICATION:
        raise ValueError('invalid verification result')
    is_check = stage == 'verification' or verified != 'NOT_RUN' or 'check_id' in entry
    check_id = text(entry.get('check_id', 'overall'), 'check id')
    kind = entry.get('verification_kind', 'test')
    if kind not in {'test', 'build'}:
        raise ValueError('verification_kind must be test or build')
    if is_check:
        previous = [e for e in record['events'] if
                    (e.get('stage') == 'verification' or e['verification'] != 'NOT_RUN' or 'check_id' in e)
                    and e.get('check_id', 'overall') == check_id]
        if previous and previous[-1].get('verification_kind', 'test') != kind:
            raise ValueError('a check cannot change between test and build; use a distinct check id')
    required = entry.get('required_checks')
    if required is not None and (not isinstance(required, list) or not required or
            any(not isinstance(c, str) or not c.strip() for c in required) or len(set(required)) != len(required)):
        raise ValueError('required_checks must be a nonempty array of unique check ids')
    registry = load(relative_file(root, PROJECT, must_exist=True))
    if is_check and verified == 'PASS' and policy(root, registry['policy']['path']) != registry['policy']:
        raise ValueError('review the current testing policy before recording verification')
    manifests = entry.get('run_manifests', [])
    if not isinstance(manifests, list) or any(not isinstance(n, str) for n in manifests):
        raise ValueError('run_manifests must be a string array')
    evidence = fingerprints(root, entry.get('evidence_paths', []))
    execution = []
    for name in manifests:
        manifest_path = relative_file(root, name, must_exist=True)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        result = collect(root, manifest)
        code_evidence = [run['evidence_after'] for run in manifest['runs'] if 'evidence_after' in run]
        for observed in code_evidence:
            if not isinstance(observed, dict):
                raise ValueError('invalid execution code evidence')
        observed_changes = [p for observed in code_evidence for p in changed(root, observed)]
        report_paths = [p for run in result['runs'] for group in run['groups'] for p in group['paths']]
        reports = {p: {'sha256': digest(relative_file(root, p, must_exist=True)),
                       'mtime_ns': relative_file(root, p).stat().st_mtime_ns} for p in report_paths}
        execution.append({'manifest': name, 'sha256': digest(manifest_path),
                          'status': 'NOT_VERIFIED' if observed_changes else result['status'],
                          'counts': result['counts'], 'reports': reports, 'code_evidence': code_evidence,
                          'kinds': [run['kind'] for run in result['runs']],
                          'executed_tests': sum(g['counts']['tests'] - g['counts']['skipped']
                              for run in result['runs'] if run['kind'] == 'test' for g in run['groups'])})
    if verified == 'PASS' and (not evidence or not execution or
                               any(r['status'] != 'EVIDENCE_PASS' for r in execution)):
        raise ValueError('PASS requires code evidence and valid execution manifests')
    if verified == 'PASS' and kind == 'test' and not any(
            r['executed_tests'] > 0 for r in execution):
        raise ValueError('test PASS requires executed test cases; compilation is build evidence only')
    findings = entry.get('findings', [])
    if not isinstance(findings, list):
        raise ValueError('findings must be an array')
    seen = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError('invalid finding')
        fid = text(finding.get('id'), 'finding id')
        text(finding.get('summary'), 'finding summary')
        if finding.get('status') not in {'OPEN', 'BLOCKED', 'RESOLVED'} or fid in seen:
            raise ValueError('invalid or duplicate finding status/id')
        if finding['status'] == 'RESOLVED' and not evidence:
            raise ValueError('resolving a finding requires current evidence')
        seen.add(fid)
        # A new finding belongs to this record; later records may update its id.
        if not fid.startswith(identity + ':'):
            matches = [r for r in read_records(root) if any(
                f.get('id') == fid for e in r['events'] for f in e.get('findings', []))]
            if not matches:
                raise ValueError('finding update must reference an existing finding')
    event = {'at': now(), 'stage': stage, 'status': progress, 'summary': entry['summary'],
             'verification': verified, 'evidence': evidence, 'execution': execution,
             'findings': findings, 'git_head': head(root)}
    if is_check:
        event.update(check_id=check_id, verification_kind=kind, policy=registry['policy'])
    if required is not None:
        event['required_checks'] = required
    if 'next_step' in entry:
        event['next_step'] = entry['next_step']
    record['events'].append(event)
    record['revision'] += 1
    atomic_json(path, record)
    return record


def read_records(root, unreadable=None):
    root = Path(root).resolve()
    directory = relative_file(root, RECORDS)
    if not directory.exists():
        return []
    records = []
    for path in sorted(directory.glob('*.json')):
        name = path.relative_to(root).as_posix()
        try:
            record = load(relative_file(root, name, must_exist=True))
            if (record.get('id') != path.stem or record.get('workflow') not in WORK or
                    not isinstance(record.get('events'), list)):
                raise ValueError('invalid record identity, workflow or events')
            text(record.get('created_at'), 'record timestamp')
            text(record.get('scope'), 'record scope')
            text(record['policy']['path'], 'record policy path')
            text(record['policy']['sha256'], 'record policy fingerprint')
            for event in record['events']:
                text(event['at'], 'event timestamp')
                if event['status'] not in PROGRESS or event['verification'] not in VERIFICATION:
                    raise ValueError('invalid record status')
                if event.get('verification_kind', 'test') not in {'test', 'build'}:
                    raise ValueError('invalid verification kind')
                if 'check_id' in event:
                    text(event['check_id'], 'check id')
                if 'required_checks' in event:
                    required = event['required_checks']
                    if (not isinstance(required, list) or not required or
                            any(not isinstance(c, str) or not c.strip() for c in required) or
                            len(set(required)) != len(required)):
                        raise ValueError('invalid required checks')
                if 'policy' in event:
                    text(event['policy']['path'], 'event policy path')
                    text(event['policy']['sha256'], 'event policy fingerprint')
                if not isinstance(event.get('evidence', {}), dict):
                    raise ValueError('invalid record evidence')
            records.append(record)
        except (ValueError, OSError, KeyError, TypeError):
            if unreadable is None:
                raise ValueError('unreadable work record: ' + name)
            unreadable.append(name)
    return records


def changed(root, expected):
    return [name for name, sha in expected.items()
            if not relative_file(root, name).is_file() or digest(relative_file(root, name)) != sha]


def aggregate(results):
    # Test readiness covers only required test checks; build results are reported separately.
    if not results:
        return 'NOT_RUN'
    for value in ('FAILED', 'STALE', 'NOT_VERIFIED', 'PARTIAL', 'NOT_RUN'):
        if value in results:
            return value
    return 'PASS'


def status(root, limit=10):
    path = relative_file(root, PROJECT)
    data = load(path) if path.exists() else None
    policy_changed = bool(data and changed(root, {data['policy']['path']: data['policy']['sha256']}))
    output, findings = [], {}
    unreadable = []
    records = sorted(read_records(root, unreadable), key=lambda r: (r['created_at'], r['id']))
    updates = sorted(((e['at'], r['id'], i, e) for r in records for i, e in enumerate(r['events'])),
                     key=lambda item: item[:3])
    for _, rid, _, event in updates:
        for finding in event.get('findings', []):
            findings[finding['id']] = dict(finding, record=rid)
    for record in records:
        events = record['events']
        last = events[-1] if events else {}
        work_evidence = {}
        for event in events:
            work_evidence.update(event.get('evidence', {}))
        work_changes = changed(root, work_evidence)
        latest, required = {}, None
        for event in events:
            if 'required_checks' in event:
                required = event['required_checks']
            if event.get('stage') == 'verification' or event['verification'] != 'NOT_RUN' or 'check_id' in event:
                latest[event.get('check_id', 'overall')] = event
        # Missing required checks remain visible rather than inheriting another suite's PASS.
        required = required if required is not None else list(latest)
        check_rows = []
        for check_id in dict.fromkeys(list(latest) + required):
            check = latest.get(check_id, {})
            changes = changed(root, check.get('evidence', {}))
            for run in check.get('execution', []):
                changes.extend(changed(root, {run['manifest']: run['sha256']}))
                for observed in run.get('code_evidence', []):
                    changes.extend(changed(root, observed))
                for name, report in run.get('reports', {}).items():
                    p = relative_file(root, name)
                    if (not p.is_file() or digest(p) != report['sha256'] or
                            p.stat().st_mtime_ns != report['mtime_ns']):
                        changes.append(name)
            historical = check.get('verification', 'NOT_RUN')
            old_policy = check.get('policy', record['policy'])
            rule_change = bool(changed(root, {old_policy['path']: old_policy['sha256']}) or
                               (data and old_policy['path'] != data['policy']['path']))
            stale = bool(changes or rule_change)
            check_rows.append({'id': check_id, 'kind': check.get('verification_kind', 'test'),
                               'required': check_id in required, 'recorded_verification': historical,
                               'current_verification': 'STALE' if stale and historical != 'NOT_RUN' else historical,
                               'evidence_changed': sorted(set(changes)), 'policy_changed': rule_change})
        test_checks = [c for c in check_rows if c['required'] and c['kind'] == 'test']
        historical = aggregate([c['recorded_verification'] for c in test_checks])
        current = aggregate([c['current_verification'] for c in test_checks])
        changes = [p for c in test_checks for p in c['evidence_changed']]
        rule_change = any(c['policy_changed'] for c in test_checks)
        output.append({'id': record['id'], 'workflow': record['workflow'], 'scope': record['scope'],
                       'status': last.get('status', 'IN_PROGRESS'), 'summary': last.get('summary'),
                       'next_step': last.get('next_step'), 'recorded_verification': historical,
                       'current_verification': current, 'checks': check_rows,
                       'evidence_changed': sorted(set(changes)), 'policy_changed': rule_change,
                       'work_evidence_changed': work_changes,
                       'updated_at': last.get('at', record['created_at']),
                       'path': RECORDS + '/' + record['id'] + '.json'})
    output.sort(key=lambda item: (item['updated_at'], item['id']))
    return {'schema_version': SCHEMA, 'management': data['management'] if data else 'UNMANAGED',
            'policy': data.get('policy') if data else None, 'policy_review_required': policy_changed,
            'record_count': len(records), 'records': output[-limit:][::-1],
            'unreadable_records': unreadable,
            'open_findings': [f for f in findings.values() if f['status'] != 'RESOLVED'],
            'scope': 'Recorded project work only; no tests or environment probes executed.'}


def detach(root, identity, handover, reason):
    text(reason, 'handover reason')
    path = relative_file(root, PROJECT)
    data = load(path)
    if policy(root, data['policy']['path']) != data['policy']:
        raise ValueError('review the current testing policy before detaching')
    handover_file = relative_file(root, handover, must_exist=True)
    if handover_file.suffix.lower() != '.md' or not handover_file.read_text(encoding='utf-8').strip():
        raise ValueError('handover must be a nonempty project Markdown document')
    record = load(record_path(root, identity))
    last = record['events'][-1] if record['events'] else {}
    if record['workflow'] != 'uninstall' or last.get('stage') != 'handover' or last.get('status') != 'COMPLETED':
        raise ValueError('complete the uninstall handover record before detaching')
    handover_name = handover_file.relative_to(Path(root).resolve()).as_posix()
    if last.get('evidence', {}).get(handover_name) != digest(handover_file):
        raise ValueError('handover document must match the completed handover evidence')
    if data['management'] == 'RELEASED':
        return data
    data['events'].append({'at': now(), 'action': 'DETACH', 'record': identity,
                           'handover': handover, 'sha256': digest(handover_file), 'reason': reason})
    data.update(management='RELEASED', revision=data['revision'] + 1)
    atomic_json(path, data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('adopt')
    p.add_argument('--policy', required=True)
    p.add_argument('--reason', required=True)
    p = sub.add_parser('begin')
    p.add_argument('--workflow', choices=WORKFLOWS, required=True)
    p.add_argument('--scope', required=True)
    p.add_argument('--policy')
    p.add_argument('--reason')
    p = sub.add_parser('record')
    p.add_argument('--id', required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--expected-revision', type=int)
    p = sub.add_parser('status')
    p.add_argument('--limit', type=int, default=10)
    p = sub.add_parser('detach')
    p.add_argument('--id', required=True)
    p.add_argument('--handover', required=True)
    p.add_argument('--reason', required=True)
    args = parser.parse_args()
    try:
        root = args.repo.resolve()
        if not root.is_dir():
            raise ValueError('project directory does not exist')
        if args.command == 'status':
            if args.limit < 1:
                raise ValueError('limit must be positive')
            result = status(root, args.limit)
        else:
            with writing(root):
                if args.command == 'adopt':
                    result = adopt(root, args.policy, args.reason)
                elif args.command == 'begin':
                    result = begin(root, args.workflow, args.scope, args.policy, args.reason)
                elif args.command == 'record':
                    result = checkpoint(root, args.id, json.loads(args.input.read_text(encoding='utf-8')),
                                        args.expected_revision)
                else:
                    result = detach(root, args.id, args.handover, args.reason)
        emit(result)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'error': str(exc)})
        return 2


if __name__ == '__main__':
    sys.exit(main())
