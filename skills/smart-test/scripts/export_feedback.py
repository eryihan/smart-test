#!/usr/bin/env python3
"""Export a local, allowlisted feedback summary; never copy raw project artifacts."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import uuid

sys.dont_write_bytecode = True
from common import emit, relative_file, safe_name

WORKFLOWS = {'help', 'init', 'scan', 'changes', 'check', 'pipeline'}
HOSTS = {'codex', 'claude-code', 'unknown'}
FEEDBACK_TYPES = {'FALSE_PASS', 'FALSE_BLOCKED', 'WRONG_STRATEGY', 'WRONG_SCOPE',
                  'ORACLE_ERROR', 'DIRECTIVE_IGNORED', 'MISSING_CAPABILITY',
                  'UX_CONFUSION', 'PERFORMANCE', 'OTHER'}
STATUSES = {'NOT_STARTED', 'PROPOSED', 'READY', 'PARTIAL', 'BLOCKED', 'FAILED',
            'PASS', 'STALE', 'NOT_VERIFIED', 'UNKNOWN', 'NOT_APPLICABLE',
            'NOT_RUN', 'EVIDENCE_PASS', 'VALID', 'INVALID', 'DISCOVERED'}
SUITES = {'unit', 'slice', 'integration', 'contract', 'e2e', 'critical-flow'}
SIGNALS = {'spring-boot', 'mybatis', 'jpa', 'mysql', 'postgresql', 'h2', 'redis',
           'kafka', 'rocketmq', 'rabbitmq', 'flyway', 'liquibase', 'security',
           'http-client', 'rpc', 'junit5', 'junit4', 'testng', 'mockito', 'assertj',
           'spring-test', 'testcontainers', 'jacoco', 'pact', 'pitest', 'surefire',
           'failsafe', 'transaction', 'authorization', 'concurrency',
           'sql-mapping', 'database-migration'}
ARTIFACTS = ('project-profile.json', 'effective-context.json', 'business-oracle.json',
             'test-policy.json', 'test-plan.json', 'status.json')
MAX_BYTES = 2_000_000
MAX_ITEMS = 1000
MAX_RUN_FILES = 100


def enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) else []


def selected(values, allowed):
    return sorted({v for v in values if isinstance(v, str) and v in allowed})


def number(value, low=0, high=1_000_000_000):
    return value if type(value) in (int, float) and low <= value <= high else None


def count(value):
    return len(value) if isinstance(value, (list, dict)) else None


def present(value):
    return isinstance(value, str) and bool(value.strip())


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


def coverage(data):
    data = obj(data)
    return {
        'mode': enum(data.get('mode'), {'UNSPECIFIED', 'REPORT_ONLY', 'OVERALL', 'INCREMENTAL', 'BOTH'}),
        'metric': enum(data.get('metric'), {'LINE', 'BRANCH', 'INSTRUCTION', 'METHOD', 'CLASS'}),
        'threshold': number(data.get('threshold'), high=100),
        'baseline_present': present(data.get('baseline')),
        'scope_type': enum(obj(data.get('scope')).get('type'), {'REPOSITORY', 'MODULE', 'PATH'}),
    }


def summarize(name, data):
    result = {'status': enum(data.get('status'), STATUSES),
              'example_only': data.get('example_only') is True}
    if name == 'project-profile.json':
        signals = data.get('signals', [])
        result.update(signals=selected(signals if isinstance(signals, (dict, list)) else [], SIGNALS),
                      module_count=count(data.get('modules')))
    elif name == 'effective-context.json':
        data = obj(data.get('effective_context', data))
        result.update(directive_count=count(data.get('directive_ids')),
                      decision_count=count(data.get('decision_ids')),
                      conflict_count=count(data.get('conflicts')),
                      unresolved_count=count(data.get('unresolved')))
        constraints = obj(data.get('constraints'))
        result['constraints'] = {k: constraints[k] for k in ('docker_allowed', 'production_code_modify')
                                 if type(constraints.get(k)) is bool}
    elif name == 'business-oracle.json':
        entries = [data] if 'business_truth' in data else []
        for key in ('entries', 'items', 'claims', 'oracle'):
            entries.extend(v for v in rows(data.get(key)) if isinstance(v, dict))
        result.update(entry_count=len(entries),
                      business_truth_count=sum(e.get('business_truth') is True for e in entries),
                      characterization_count=sum(e.get('business_truth') is False for e in entries),
                      missing_source_count=sum(e.get('business_truth') is True and not present(e.get('source')) for e in entries),
                      missing_claim_count=sum(e.get('business_truth') is True and not present(e.get('claim')) for e in entries))
    elif name == 'test-policy.json':
        result['required_suites'] = selected(
            [s.get('suite') if isinstance(s, dict) else s for s in rows(data.get('required_suites'))], SUITES)
        result['coverage'] = coverage(data.get('coverage'))
        if type(data.get('production_code_modify')) is bool:
            result['production_code_modify'] = data['production_code_modify']
    elif name == 'test-plan.json':
        items = rows(obj(data.get('test_plan', data)).get('items'))
        result['item_count'] = len(items)
        result['items'] = [
            {'item': i + 1, 'required': item.get('required') is True,
             'risk': enum(item.get('risk'), {'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'}),
             'suite': enum(item.get('suite'), SUITES),
             'assertion_count': count(item.get('assertions')),
             'oracle_present': isinstance(item.get('oracle'), dict),
             'business_truth': obj(item.get('oracle')).get('business_truth') is True}
            for i, item in enumerate(items[:MAX_ITEMS]) if isinstance(item, dict)]
    elif name == 'status.json':
        result.update(blocking_count=count(data.get('blocking_ids')),
                      blocker_count=count(data.get('blockers')))
    return result


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


def change_summary(evidence):
    risks = {}
    for record in rows(evidence.get('risk_indicators')):
        if isinstance(record, dict) and isinstance(record.get('path'), str):
            risks[record['path']] = selected(rows(record.get('indicators')), SIGNALS)
    files = rows(obj(evidence.get('change')).get('files'))
    output = []
    for record in files[:MAX_ITEMS]:
        if not isinstance(record, dict) or not isinstance(record.get('path'), str):
            continue
        raw = record['path']
        path = PurePosixPath(raw)
        if path.is_absolute() or '..' in path.parts or '\\' in raw or ':' in raw or not path.parts:
            raise ValueError('unsafe change path')
        if not safe_name(raw):
            continue
        extension = path.suffix if path.suffix in {'.java', '.kt', '.xml', '.sql', '.gradle', '.kts', '.yml', '.yaml', '.properties'} else '.file'
        # Never retain module, package, class, author or original filename text.
        category = next((c for c in ('src/main/java', 'src/test/java', 'src/main/resources', 'src/test/resources')
                         if tuple(c.split('/')) in
                         [path.parts[i:i + 3] for i in range(len(path.parts) - 2)]), 'files')
        change = {'A': 'added', '?': 'untracked', 'M': 'modified', 'D': 'deleted', 'R': 'renamed',
                  'added': 'added', 'untracked': 'untracked', 'modified': 'modified', 'deleted': 'deleted', 'renamed': 'renamed'}
        kind = record.get('change_type', record.get('status'))
        output.append({'path': category + '/file-' + str(len(output) + 1).zfill(4) + extension,
                       'change_type': change.get(kind) if isinstance(kind, str) else None,
                       'risk_signals': sorted(set(risks.get(raw, [])) |
                                              set(selected(rows(record.get('risk_signals')), SIGNALS)))})
    return {'reported_file_count': len(files), 'files': output,
            'paths': 'GENERATED_ALIASES', 'source': 'EXISTING_REPOSITORY_EVIDENCE_ONLY'}


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


def export_feedback(repo, output, host, workflow, feedback_type='OTHER', host_version=None):
    if host not in HOSTS or workflow not in WORKFLOWS or feedback_type not in FEEDBACK_TYPES:
        raise ValueError('invalid metadata enum')
    if host_version is not None and (not isinstance(host_version, str) or
                                    not re.fullmatch(r'\d{1,4}(?:\.\d{1,4}){1,3}', host_version)):
        raise ValueError('host version must be numeric; omit unknown versions')
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
    for name in ARTIFACTS:
        data, state = read_json(root, '.smart-test/' + name)
        bundle[name] = {'input_state': state, 'summary': summarize(name, data) if state == 'READ' else {}}
    data, state = read_json(root, '.smart-test/repository-evidence.json')
    bundle['sanitized-change-summary.json'] = {'input_state': state, 'summary': change_summary(data)}
    data, state = read_json(root, '.smart-test/execution-summary.json')
    execution = {'input_state': state, 'summary': run_summary(data), 'manifests': []}
    runs = relative_file(root, '.smart-test/runs')
    if runs.exists():
        if not runs.is_dir():
            raise ValueError('invalid runs directory')
        directories = sorted(runs.iterdir())
        execution['run_directory_count'] = len(directories)
        for directory in directories[:MAX_RUN_FILES]:
            if directory.is_symlink():
                raise ValueError('run symlink forbidden')
            if directory.is_dir():
                data, state = read_json(root, '.smart-test/runs/' + directory.name + '/manifest.json')
                execution['manifests'].append({'input_state': state, 'summary': run_summary(data)})
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
    args = parser.parse_args()
    try:
        emit(export_feedback(args.repo, args.output, args.host, args.workflow, args.feedback_type, args.host_version))
        return 0
    except (ValueError, OSError, TypeError, RecursionError):
        # Exceptions can include project paths or attacker-controlled JSON. Never echo them.
        emit({'status': 'ERROR', 'error': 'Export refused. Check paths, permissions and metadata; no raw diagnostic data exported.'})
        return 2


if __name__ == '__main__':
    sys.exit(main())
