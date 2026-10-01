#!/usr/bin/env python3
"""Collect native command and report facts, with optional execution snapshots."""
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
from common import atomic_json, digest, emit, git, relative_file


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be a nonempty string')
    return value


def fingerprints(root, names):
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise ValueError('evidence_paths must be a string array')
    return {name: digest(relative_file(root, name, must_exist=True)) for name in names}


def head(root):
    try:
        return git(root, 'rev-parse', 'HEAD').decode().strip()
    except (ValueError, OSError):
        return None


REPORT_GROUP_FIELDS = {'pattern', 'required', 'min_tests', 'allow_skipped', 'expected_test_ids'}


def normalize_reports(root, reports, kind):
    """Validate and normalize report groups before execution.

    A string remains a supported shorthand for a required XML group. Mapping
    form carries the same identity and skip constraints that collect_reports
    enforces, so the execution path cannot silently discard them.
    """
    if not isinstance(reports, list) or (kind == 'test' and not reports):
        raise ValueError('test execution requires explicit JUnit report patterns')
    normalized = []
    seen = set()
    for value in reports:
        group = ({'pattern': value, 'required': True} if isinstance(value, str)
                 else dict(value) if isinstance(value, dict) else None)
        if group is None or set(group) - REPORT_GROUP_FIELDS:
            raise ValueError('report groups must be XML pattern strings or supported mappings')
        pattern = group.get('pattern')
        text(pattern, 'report pattern')
        relative_file(root, pattern)
        if not pattern.endswith('.xml'):
            raise ValueError('report patterns must select JUnit XML')
        if pattern in seen:
            raise ValueError('duplicate report patterns')
        seen.add(pattern)
        required = group.get('required', True)
        if not isinstance(required, bool):
            raise ValueError('report required must be boolean')
        minimum = group.get('min_tests', 1)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
            raise ValueError('min_tests must be a positive integer')
        allow_skipped = group.get('allow_skipped', False)
        if not isinstance(allow_skipped, bool):
            raise ValueError('allow_skipped must be boolean')
        expected = group.get('expected_test_ids', [])
        if (not isinstance(expected, list) or any(not isinstance(item, str) or not item.strip() for item in expected)
                or len(set(expected)) != len(expected)):
            raise ValueError('expected_test_ids must be unique nonempty strings')
        normalized.append({'pattern': pattern, 'required': required, 'min_tests': minimum,
                           'allow_skipped': allow_skipped, 'expected_test_ids': expected})
    return normalized


@contextmanager
def execution_lock(root):
    lock = relative_file(root, '.smart-test/execution.lock')
    created = not lock.parent.exists()
    lock.parent.mkdir(parents=True, exist_ok=True)
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
        if created:
            try:
                lock.parent.rmdir()
            except OSError:
                pass  # Saved evidence or another writer still needs the directory.


def validate(root, spec):
    if not root.is_dir():
        raise ValueError('project directory does not exist')
    if not isinstance(spec, dict) or set(spec) - {
            'argv', 'summary', 'evidence_paths', 'kind', 'reports', 'timeout_seconds'}:
        raise ValueError('unsupported execution input fields')
    argv = spec.get('argv')
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise ValueError('argv must be a nonempty string array')
    text(spec.get('summary'), 'summary')
    kind = spec.get('kind', 'test')
    if kind not in {'test', 'build', 'compile'}:
        raise ValueError('kind must be test, build or compile')
    timeout = spec.get('timeout_seconds', 600)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
        raise ValueError('timeout_seconds must be positive and at most 86400')
    normalize_reports(root, spec.get('reports', []), kind)
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


def execute(root, spec, save_evidence=False):
    root = Path(root).resolve()
    before = validate(root, spec)
    report_groups = normalize_reports(root, spec.get('reports', []), spec.get('kind', 'test'))
    if not isinstance(save_evidence, bool):
        raise ValueError('save_evidence must be boolean')
    kind = spec.get('kind', 'test')
    with execution_lock(root):
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
        folder = relative_file(root, '.smart-test/runs/' + run_id) if save_evidence else None
        if folder is not None:
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
        for index, requested in enumerate(report_groups):
            pattern = requested['pattern']
            if folder is None:
                groups.append(dict(requested))
                continue
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
            group = dict(requested)
            group['pattern'] = target.relative_to(root).as_posix() + '/*.xml'
            groups.append(group)
        after = {}
        for name in spec.get('evidence_paths', []):
            try:
                after.update(fingerprints(root, [name]))
            except (ValueError, OSError):
                after[name] = None
                blockers.append({'type': 'EVIDENCE_REMOVED_OR_UNREADABLE'})
        if before != after:
            blockers.append({'type': 'EVIDENCE_CHANGED_DURING_EXECUTION'})
        run = {'id': run_id, 'kind': kind, 'argv': spec['argv'], 'cwd': '.',
               'started_at': started.isoformat(), 'finished_at': finished.isoformat(),
               'exit_code': code, 'reports': groups, 'git_head': observed_head,
               'evidence_before': before, 'evidence_after': after,
               'exit_code_source': 'native_process' if not termination else 'execution_helper'}
        if termination:
            run['termination'] = termination
        manifest = {'schema_version': 1, 'required_run_ids': [run_id], 'runs': [run], 'blockers': blockers}
        name = (folder / 'manifest.json').relative_to(root).as_posix() if folder is not None else None
        if name is not None:
            atomic_json(root / name, manifest)
        result = collect(root, manifest)
        # Successful execution still needs assertion, scope and applicable quality-gate review.
        return {'manifest': name, 'exit_code': code, 'termination': termination,
                'evidence_status': result['status'], 'counts': result['counts'],
                'issues': result['issues'], 'execution': manifest,
                'scope': result['scope'],
                'evidence_changed_during_execution': before != run['evidence_after']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--input', type=Path, help='advanced execution input with grouped report constraints')
    parser.add_argument('--kind', choices=['test', 'compile', 'build'])
    parser.add_argument('--report', action='append', help='exact JUnit pattern; repeat for required groups')
    parser.add_argument('--evidence', action='append', help='referenced source/configuration path to check for changes')
    parser.add_argument('--timeout', type=float)
    parser.add_argument('--save-evidence', action='store_true')
    parser.add_argument('argv', nargs=argparse.REMAINDER, help='native command after --')
    args = parser.parse_args()
    try:
        if args.input:
            if args.argv or args.kind or args.report or args.evidence or args.timeout is not None:
                raise ValueError('--input cannot be combined with native command options')
            spec = json.loads(args.input.read_text(encoding='utf-8'))
        else:
            spec = {'argv': args.argv[1:] if args.argv[:1] == ['--'] else args.argv,
                    'summary': 'Native command', 'kind': args.kind or 'test',
                    'reports': args.report or [], 'evidence_paths': args.evidence or [],
                    'timeout_seconds': args.timeout if args.timeout is not None else 600}
        result = execute(args.repo, spec, args.save_evidence)
        emit(result)
        return 0 if result['exit_code'] == 0 and result['evidence_status'] == 'EVIDENCE_PASS' else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'status': 'ERROR', 'error': str(exc)})
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
