#!/usr/bin/env python3
"""Run an authorized native command and attach its observed evidence to a work record."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
from collect_reports import collect
from common import atomic_json, emit, relative_file
from project import checkpoint, fingerprints, head, load, policy, record_path, text, writing, PROJECT


@contextmanager
def execution_lock(root):
    lock = relative_file(root, '.smart-test/execution.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('another native command is running; inspect execution.lock before retrying')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def validate(root, identity, spec):
    load(record_path(root, identity))
    if not isinstance(spec, dict) or set(spec) - {
            'argv', 'summary', 'evidence_paths', 'check_id', 'required_checks', 'kind', 'reports', 'timeout_seconds'}:
        raise ValueError('unsupported execution input fields')
    argv = spec.get('argv')
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise ValueError('argv must be a nonempty string array')
    text(spec.get('summary'), 'summary')
    text(spec.get('check_id', 'overall'), 'check id')
    kind = spec.get('kind', 'test')
    if kind not in {'test', 'build', 'compile'}:
        raise ValueError('kind must be test, build or compile')
    timeout = spec.get('timeout_seconds', 600)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
        raise ValueError('timeout_seconds must be positive and at most 86400')
    reports = spec.get('reports', [])
    if not isinstance(reports, list) or (kind == 'test' and not reports):
        raise ValueError('test execution requires explicit JUnit report patterns')
    for pattern in reports:
        text(pattern, 'report pattern')
        relative_file(root, pattern)
        if not pattern.endswith('.xml'):
            raise ValueError('report patterns must select JUnit XML')
    if len(set(reports)) != len(reports):
        raise ValueError('duplicate report patterns')
    required = spec.get('required_checks')
    if required is not None and (not isinstance(required, list) or not required or
            any(not isinstance(c, str) or not c.strip() for c in required) or len(set(required)) != len(required)):
        raise ValueError('required_checks must contain unique nonempty check ids')
    registry = load(relative_file(root, PROJECT, must_exist=True))
    if policy(root, registry['policy']['path']) != registry['policy']:
        raise ValueError('review the current testing policy before execution')
    return fingerprints(root, spec.get('evidence_paths', []))


def stop(process):
    # Stop the process group on POSIX so a timed-out Maven/Gradle child cannot keep running.
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def execute(root, identity, spec):
    root = Path(root).resolve()
    before = validate(root, identity, spec)
    observed_policy = load(relative_file(root, PROJECT, must_exist=True))['policy']
    check_id = spec.get('check_id', 'overall')
    kind = spec.get('kind', 'test')
    metadata = {'check_id': check_id, 'verification_kind': 'test' if kind == 'test' else 'build'}
    if 'required_checks' in spec:
        metadata['required_checks'] = spec['required_checks']
    with execution_lock(root):
        with writing(root):
            checkpoint(root, identity, dict(metadata, stage='verification', status='IN_PROGRESS',
                       summary='Starting native command: ' + spec['summary'],
                       evidence_paths=spec.get('evidence_paths', [])))
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
        folder = relative_file(root, '.smart-test/runs/' + run_id)
        folder.mkdir(mode=0o700, parents=True)
        started = datetime.now(timezone.utc)
        observed_head = head(root)
        process, termination = None, None
        try:
            process = subprocess.Popen(spec['argv'], cwd=root, start_new_session=os.name == 'posix')
            code = process.wait(timeout=spec.get('timeout_seconds', 600))
        except subprocess.TimeoutExpired:
            stop(process)
            code, termination = 124, 'TIMEOUT'
        except KeyboardInterrupt:
            if process is not None:
                stop(process)
            code, termination = 130, 'INTERRUPTED'
        except OSError:
            code, termination = 127, 'START_FAILED'
        finished = datetime.now(timezone.utc)
        groups, seen, blockers = [], set(), []
        for index, pattern in enumerate(spec.get('reports', [])):
            target = folder / ('reports-' + str(index))
            target.mkdir(mode=0o700)
            for source in sorted(root.glob(pattern)):
                name = source.relative_to(root).as_posix()
                try:
                    source = relative_file(root, name, must_exist=True)
                except (ValueError, OSError):
                    blockers.append({'type': 'UNSAFE_OR_MISSING_REPORT'})
                    continue
                if name in seen:
                    continue
                seen.add(name)
                try:
                    if started.timestamp() <= source.stat().st_mtime <= finished.timestamp():
                        snapshot = target / (str(len(seen)) + '-' + source.name)
                        shutil.copy2(source, snapshot)
                        snapshot.chmod(0o600)
                except OSError:
                    blockers.append({'type': 'REPORT_COPY_FAILED'})
            groups.append({'pattern': target.relative_to(root).as_posix() + '/*.xml', 'required': True})
        after = {}
        remaining = []
        for name in spec.get('evidence_paths', []):
            try:
                after.update(fingerprints(root, [name]))
                remaining.append(name)
            except (ValueError, OSError):
                after[name] = None
                blockers.append({'type': 'EVIDENCE_REMOVED_OR_UNREADABLE'})
        if before != after:
            blockers.append({'type': 'EVIDENCE_CHANGED_DURING_EXECUTION'})
        run = {'id': run_id, 'kind': kind, 'argv': spec['argv'], 'cwd': '.',
               'started_at': started.isoformat(), 'finished_at': finished.isoformat(),
               'exit_code': code, 'reports': groups, 'git_head': observed_head,
               'policy': observed_policy, 'evidence_before': before, 'evidence_after': after,
               'exit_code_source': 'native_process' if not termination else 'execution_helper'}
        if termination:
            run['termination'] = termination
        manifest = {'schema_version': 1, 'required_run_ids': [run_id], 'runs': [run], 'blockers': blockers}
        name = (folder / 'manifest.json').relative_to(root).as_posix()
        atomic_json(root / name, manifest)
        result = collect(root, manifest)
        # Successful execution still needs assertion, scope and applicable quality-gate review.
        with writing(root):
            checkpoint(root, identity, dict(metadata, stage='verification',
                       status='PARTIAL' if code == 0 else 'FAILED', summary=spec['summary'],
                       verification='NOT_VERIFIED' if code == 0 else 'FAILED',
                       evidence_paths=remaining, run_manifests=[name]))
        return {'manifest': name, 'exit_code': code, 'termination': termination,
                'evidence_status': result['status'], 'counts': result['counts'],
                'evidence_changed_during_execution': before != run['evidence_after']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.repo, args.id, json.loads(args.input.read_text(encoding='utf-8')))
        emit(result)
        return 0 if result['exit_code'] == 0 and result['evidence_status'] == 'EVIDENCE_PASS' else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'status': 'ERROR', 'error': str(exc)})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
