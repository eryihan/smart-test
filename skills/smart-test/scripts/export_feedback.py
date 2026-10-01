#!/usr/bin/env python3
"""Export a local, allowlisted feedback summary; never copy raw project artifacts."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import uuid

sys.dont_write_bytecode = True
from catalog import FEEDBACK_TYPES, HOSTS, STATUSES, WORKFLOWS
from common import emit, relative_file
MAX_BYTES = 2_000_000
MAX_ITEMS = 1000
MAX_RUN_FILES = 100


def enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) else []


def number(value, low=0, high=1_000_000_000):
    return value if type(value) in (int, float) and low <= value <= high else None


def count(value):
    return len(value) if isinstance(value, (list, dict)) else None


def read_json(root, name):
    path = relative_file(root, name)
    if not path.exists():
        return {}, 'MISSING'
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('non-regular input')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return {}, 'OMITTED_TOO_LARGE'
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return {}, 'INVALID_JSON'
    if not isinstance(data, dict):
        return {}, 'INVALID_ROOT'
    return data, 'READ'


def run_summary(data):
    result = {'status': enum(data.get('status'), STATUSES),
              'blocker_count': count(data.get('blockers')),
              'required_run_count': count(data.get('required_run_ids'))}
    result['counts'] = {k: number(obj(data.get('counts')).get(k))
                        for k in ('tests', 'failed', 'errors', 'skipped')}
    runs = rows(data.get('runs'))
    result['run_count'] = len(runs)
    result['runs'] = []
    for run in runs[:MAX_ITEMS]:
        if not isinstance(run, dict):
            continue
        entry = {'kind': enum(run.get('kind'), {'compile', 'build', 'test'}),
                 'exit_code': number(run.get('exit_code'), low=-255, high=255),
                 'report_group_count': count(run.get('reports', run.get('groups')))}
        if type(run.get('requires_test_report')) is bool:
            entry['requires_test_report'] = run['requires_test_report']
        result['runs'].append(entry)
    return result


def version_context():
    skill = Path(__file__).resolve().parents[1]
    data, state = read_json(skill, 'version.json')
    version = data.get('smart_test_version')
    if state != 'READ' or not isinstance(version, str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', version):
        raise ValueError('missing skill version metadata')
    commit = data.get('smart_test_commit')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        commit = None
    # Only the skill's own checkout, never the target Java repository or its remotes.
    source = 'bundled' if commit else 'unavailable'
    checkout = skill.parent.parent
    if (commit is None and skill == checkout / 'skills/smart-test' and
            (checkout / '.claude-plugin/plugin.json').is_file() and (checkout / '.git').is_dir()):
        try:
            head = relative_file(checkout, '.git/HEAD').read_text().strip()
            if head.startswith('ref: refs/heads/'):
                head = relative_file(checkout, '.git/' + head[5:]).read_text().strip()
            if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', head):
                commit, source = head, 'skill-checkout-head'
        except (OSError, ValueError):
            pass
    return {'smart_test_version': version, 'smart_test_commit': commit,
            'commit_source': source,
            'commit_note': 'Checkout HEAD does not prove an unmodified installation.'}


def export_feedback(repo, output, host, workflow, feedback_type='OTHER', host_version=None,
                    run_ids=None):
    if host not in HOSTS or workflow not in WORKFLOWS or feedback_type not in FEEDBACK_TYPES:
        raise ValueError('invalid metadata enum')
    if host_version is not None and (not isinstance(host_version, str) or
                                    not re.fullmatch(r'\d{1,4}(?:\.\d{1,4}){1,3}', host_version)):
        raise ValueError('host version must be numeric; omit unknown versions')
    if run_ids is not None and (not isinstance(run_ids, list) or not run_ids or
            len(run_ids) > MAX_RUN_FILES or
            any(not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', identity)
                for identity in run_ids) or len(set(run_ids)) != len(run_ids)):
        raise ValueError('invalid run selection')
    root = Path(repo).resolve()
    if not root.is_dir():
        raise ValueError('repository missing')
    output = Path(output).expanduser()
    if '..' in output.parts:
        raise ValueError('output traversal forbidden')
    output = output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('output symlink forbidden')
    output = output.resolve()
    if output == root or root in output.parents:
        raise ValueError('output must be outside target repository')
    if output.exists():
        raise ValueError('output must be a new directory')

    stamp = datetime.now(timezone.utc)
    metadata = dict(version_context(), schema_version=1, host=host, host_version=host_version,
                    workflow=workflow, timestamp=stamp.isoformat(),
                    export_format='ALLOWLISTED_SUMMARIES_ONLY', max_items=MAX_ITEMS,
                    max_run_files=MAX_RUN_FILES)
    feedback = {k: metadata[k] for k in ('smart_test_version', 'host', 'workflow')}
    feedback.update(id='FB-' + stamp.strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:12],
                    date=stamp.date().isoformat(), feedback_type=feedback_type,
                    scenario=None, actual_behavior=None, expected_behavior=None,
                    root_cause='UNKNOWN', fix=None, regression_case=None, status='OPEN')
    bundle = {'metadata.json': metadata, 'feedback.json': feedback}
    execution = {'manifests': []}
    runs = relative_file(root, '.smart-test/runs')
    if runs.exists():
        if not runs.is_dir():
            raise ValueError('invalid runs directory')
        directories = ([runs / identity for identity in run_ids] if run_ids is not None
                       else sorted(runs.iterdir(), reverse=True))
        execution['run_directory_count'] = len(directories)
        execution['runs_omitted'] = max(0, len(directories) - MAX_RUN_FILES)
        for directory in directories[:MAX_RUN_FILES]:
            if directory.is_symlink():
                raise ValueError('run symlink forbidden')
            if directory.is_dir() or run_ids is not None:
                data, state = read_json(root, '.smart-test/runs/' + directory.name + '/manifest.json')
                execution['manifests'].append({'input_state': state, 'summary': run_summary(data)})
    elif run_ids is not None:
        execution['manifests'] = [{'input_state': 'MISSING', 'summary': run_summary({})} for _ in run_ids]
    bundle['execution-summary.json'] = execution

    # Read/sanitize every input before creating output. Never merge or overwrite a bundle.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    try:
        for name, content in bundle.items():
            with (output / name).open('x', encoding='utf-8') as stream:
                os.chmod(stream.name, 0o600)
                json.dump(content, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
    except BaseException:
        shutil.rmtree(output)
        raise
    return {'status': 'EXPORTED', 'files': sorted(bundle), 'feedback_id': feedback['id']}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        emit({'status': 'ERROR', 'error': 'Invalid arguments. Use --help for supported options.'})
        self.exit(2)


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='new directory outside the target repository')
    parser.add_argument('--host', required=True, choices=sorted(HOSTS))
    parser.add_argument('--host-version', help='numeric version supplied by the caller; never probes the host')
    parser.add_argument('--workflow', required=True, choices=sorted(WORKFLOWS))
    parser.add_argument('--feedback-type', default='OTHER', choices=sorted(FEEDBACK_TYPES))
    parser.add_argument('--run', action='append', help='export only this saved run; may be repeated')
    args = parser.parse_args()
    try:
        emit(export_feedback(args.repo, args.output, args.host, args.workflow, args.feedback_type,
                             args.host_version, args.run))
        return 0
    except (ValueError, OSError, TypeError, RecursionError):
        # Exceptions can include project paths or attacker-controlled JSON. Never echo them.
        emit({'status': 'ERROR', 'error': 'Export refused. Check paths, permissions and metadata; no raw diagnostic data exported.'})
        return 2


if __name__ == '__main__':
    sys.exit(main())
