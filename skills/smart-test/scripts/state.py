#!/usr/bin/env python3
"""Transactional decision ledger. Authorization evidence is supplied by the Agent."""
import argparse
import copy
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import atomic_json, digest, emit, relative_file

SCHEMA = 1
LEVELS = {'REQUIRED', 'PREFERRED', 'ADVISORY'}
LIFECYCLES = {'PROJECT', 'SESSION', 'CHANGE', 'PHASE', 'ONE_TIME'}
CATEGORIES = {'business', 'technical', 'scope', 'execution', 'preference'}


def now():
    return datetime.now(timezone.utc).isoformat()


def initial():
    return {'schema_version': SCHEMA, 'revision': 0, 'directives': [], 'decisions': [], 'events': []}


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be a nonempty string')


def string_list(value, label, required=False):
    if not isinstance(value, list) or (required and not value) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(label + ' must be a list of nonempty strings')


def event(state, action, **data):
    state['events'].append(dict(action=action, at=now(), **data))


def find(state, bucket, identity):
    for item in state[bucket]:
        if item['id'] == identity:
            return item
    raise ValueError('unknown ' + bucket + ' id: ' + identity)


def invalidate(state, topics=(), ids=(), reason='assumptions changed', kind='semantic'):
    affected = set(ids)
    for decision in state['decisions']:
        if set(decision['topics']) & set(topics):
            affected.add(decision['id'])
    while True:
        expanded = affected | {d['id'] for d in state['decisions'] if set(d['depends_on']) & affected}
        if expanded == affected:
            break
        affected = expanded
    changed = []
    for decision in state['decisions']:
        if decision['id'] not in affected:
            continue
        # A later constraint change must not be downgraded to a file-only review.
        upgrade = (decision['status'] == 'INVALIDATED' and kind == 'semantic'
                   and decision.get('invalidation_kind') == 'evidence')
        if decision['status'] in {'EFFECTIVE', 'PROPOSED'} or upgrade:
            decision['status'] = 'INVALIDATED'
            decision['invalidation_reason'] = reason
            decision['invalidation_kind'] = kind
            changed.append(decision['id'])
    if changed:
        event(state, 'INVALIDATE', decisions=sorted(changed), reason=reason, kind=kind)
    return sorted(changed)


def fingerprints(root, paths):
    result = {}
    for name in paths:
        path = relative_file(root, name)
        result[name] = digest(path) if path.is_file() else None
    return result


def reconcile(state, root):
    stale = []
    for decision in state['decisions']:
        if decision['status'] not in {'EFFECTIVE', 'PROPOSED'}:
            continue
        expected = decision['evidence_fingerprints']
        if fingerprints(root, expected) != expected:
            stale.append(decision['id'])
    return invalidate(state, ids=stale, reason='evidence file added, changed or deleted', kind='evidence')


def validate_directive(item):
    for key in ('id', 'statement', 'source'):
        nonempty(item.get(key), key)
    if item.get('category') not in CATEGORIES or item.get('level') not in LEVELS:
        raise ValueError('invalid directive category or level')
    if item.get('lifecycle') not in LIFECYCLES:
        raise ValueError('invalid directive lifecycle')
    string_list(item.get('topics'), 'topics', True)
    scope = item.get('scope')
    if not isinstance(scope, dict) or set(scope) - {'module', 'path', 'test_type', 'phase'}:
        raise ValueError('scope must contain only module/path/test_type/phase lists')
    for value in scope.values():
        string_list(value, 'scope value', True)
    binding = item.get('binding', {})
    if not isinstance(binding, dict):
        raise ValueError('binding must be an object')
    key = {'SESSION': 'session', 'CHANGE': 'change', 'PHASE': 'phase', 'ONE_TIME': 'session'}.get(item['lifecycle'])
    if key:
        nonempty(binding.get(key), 'binding.' + key)
    if item.get('status', 'ACTIVE') not in {'ACTIVE', 'DISABLED'}:
        raise ValueError('directive status must be ACTIVE or DISABLED')


def _values(value):
    if value is None:
        return None
    return value if isinstance(value, list) else [value]


def _scope_match(item, module=None, path=None, test_type=None, phase=None):
    context = {'module': _values(module), 'path': _values(path),
               'test_type': _values(test_type), 'phase': _values(phase)}
    excluded, unresolved = [], []
    for key, patterns in item.get('scope', {}).items():
        values = context[key]
        if not values:
            unresolved.append(key)
            continue
        if not any(fnmatchcase(str(value), str(pattern)) for value in values for pattern in patterns):
            excluded.append(key)
    if excluded:
        return 'OUT_OF_SCOPE', excluded
    if unresolved:
        return 'UNRESOLVED', unresolved
    return 'APPLIES', []


def active_directives(state, session=None, change=None, phase=None, module=None, path=None, test_type=None):
    context = {'session': session, 'change': change, 'phase': phase}
    scoped = any(value is not None for value in (module, path, test_type, phase))
    active, inactive, excluded, unresolved = [], [], [], []
    for item in state['directives']:
        key = {'SESSION': 'session', 'CHANGE': 'change', 'PHASE': 'phase', 'ONE_TIME': 'session'}.get(item['lifecycle'])
        matched = item['status'] == 'ACTIVE' and (key is None or (context[key] and item['binding'][key] == context[key]))
        if not matched:
            inactive.append(item)
            continue
        if scoped:
            result, fields = _scope_match(item, module, path, test_type, phase)
            if result == 'OUT_OF_SCOPE':
                excluded.append({'id': item['id'], 'fields': fields})
                continue
            if result == 'UNRESOLVED':
                unresolved.append({'id': item['id'], 'fields': fields})
                continue
        active.append(item)
    return {'active_directives': active, 'inactive_ids': [d['id'] for d in inactive],
            'excluded_directives': excluded, 'unresolved_directives': unresolved,
            'scope_context': {'module': _values(module), 'path': _values(path),
                              'test_type': _values(test_type), 'phase': _values(phase)},
            'scope_note': 'Exact scope fields are matched by the script when context is supplied; semantic mapping and a merged Effective Context remain the Agent responsibility.'}


def apply(state, root, args, payload=None):
    if args.command in {'directive', 'propose'} and not isinstance(payload, dict):
        raise ValueError('input must be a JSON object')
    changed_by_evidence = reconcile(state, root)
    command = args.command
    if command in {'init', 'status', 'reconcile'}:
        return {'state': state, 'invalidated': changed_by_evidence}
    if command == 'context':
        return active_directives(state, args.session, args.change, args.phase,
                                 getattr(args, 'module', None), getattr(args, 'path', None),
                                 getattr(args, 'test_type', None))
    if command == 'directive':
        item = copy.deepcopy(payload)
        validate_directive(item)
        item.setdefault('status', 'ACTIVE')
        item.setdefault('binding', {})
        old = next((x for x in state['directives'] if x['id'] == item['id']), None)
        if old == item:
            return {'directive': old, 'invalidated': changed_by_evidence}
        if old:
            state['directives'].remove(old)
        state['directives'].append(item)
        event(state, 'DIRECTIVE', id=item['id'], previous=old, value=item)
        affected = invalidate(state, topics=set(item['topics']) | set((old or {}).get('topics', [])),
                              reason='directive changed: ' + item['id'])
        return {'directive': item, 'invalidated': sorted(set(affected + changed_by_evidence))}
    if command == 'consume':
        item = find(state, 'directives', args.id)
        if item['lifecycle'] != 'ONE_TIME' or item['status'] != 'ACTIVE':
            raise ValueError('only an active ONE_TIME directive may be consumed')
        nonempty(args.evidence, 'evidence')
        item['status'] = 'CONSUMED'
        event(state, 'CONSUME', id=item['id'], evidence=args.evidence)
        return {'directive': item, 'invalidated': invalidate(state, topics=item['topics'], reason='one-time directive consumed')}
    if command == 'propose':
        for key in ('id', 'kind', 'summary'):
            nonempty(payload.get(key), key)
        string_list(payload.get('topics'), 'topics', True)
        string_list(payload.get('evidence_paths'), 'evidence_paths')
        string_list(payload.get('depends_on'), 'depends_on')
        if payload['id'] in payload['depends_on']:
            raise ValueError('a proposal cannot depend on itself')
        for dep in payload['depends_on']:
            if find(state, 'decisions', dep)['status'] != 'EFFECTIVE':
                raise ValueError('dependency is not EFFECTIVE: ' + dep)
        pending, visited = list(payload['depends_on']), set()
        while pending:
            dep = pending.pop()
            if dep == payload['id']:
                raise ValueError('decision dependencies would form a cycle')
            if dep not in visited:
                visited.add(dep)
                pending.extend(find(state, 'decisions', dep)['depends_on'])
        old = next((x for x in state['decisions'] if x['id'] == payload['id']), None)
        if old and all(old.get(k) == v for k, v in payload.items()) and old['status'] in {'PROPOSED', 'EFFECTIVE'}:
            return {'decision': old, 'invalidated': changed_by_evidence}
        if old:
            invalidate(state, ids=[old['id']], reason='proposal revised')
            state['decisions'].remove(old)
        item = {k: copy.deepcopy(payload[k]) for k in ('id', 'kind', 'summary', 'topics', 'evidence_paths', 'depends_on')}
        # Inputs cannot smuggle an approval, an effective status, or stored fingerprints.
        item.update(status='PROPOSED', version=(old or {}).get('version', 0) + 1,
                    evidence_fingerprints=fingerprints(root, item['evidence_paths']))
        state['decisions'].append(item)
        event(state, 'PROPOSE', id=item['id'], previous=old, value=copy.deepcopy(item))
        return {'decision': item, 'invalidated': changed_by_evidence}
    if command == 'resolve':
        item = find(state, 'decisions', args.id)
        nonempty(args.evidence, 'approval evidence')
        if item['status'] != 'PROPOSED':
            raise ValueError('only a current PROPOSED decision may be resolved; revise invalidated/rejected proposals first')
        if args.action == 'confirm':
            for dep in item['depends_on']:
                if find(state, 'decisions', dep)['status'] != 'EFFECTIVE':
                    raise ValueError('dependency no longer effective: ' + dep)
            item['status'] = 'EFFECTIVE'
            item['approval'] = {'type': args.source, 'evidence': args.evidence, 'at': now()}
        else:
            item['status'] = 'REJECTED' if args.action == 'reject' else 'REVISED'
            item['resolution'] = {'action': args.action, 'evidence': args.evidence, 'at': now()}
        event(state, 'RESOLVE', id=item['id'], action_taken=args.action, evidence=args.evidence)
        return {'decision': item, 'invalidated': changed_by_evidence}
    if command == 'revalidate':
        item = find(state, 'decisions', args.id)
        nonempty(args.evidence, 'review evidence')
        if (item['status'] != 'INVALIDATED' or item.get('invalidation_kind') != 'evidence'
                or not item.get('approval')):
            raise ValueError('only a previously approved, evidence-invalidated decision may be revalidated')
        for dep in item['depends_on']:
            if find(state, 'decisions', dep)['status'] != 'EFFECTIVE':
                raise ValueError('review dependencies first: ' + dep)
        previous = copy.deepcopy(item)
        item['evidence_fingerprints'] = fingerprints(root, item['evidence_paths'])
        item['status'] = 'EFFECTIVE'
        item.pop('invalidation_kind', None)
        item.pop('invalidation_reason', None)
        item['review'] = {'evidence': args.evidence, 'at': now()}
        event(state, 'REVALIDATE', id=item['id'], previous=previous, value=copy.deepcopy(item))
        return {'decision': item, 'invalidated': changed_by_evidence}
    if command == 'invalidate':
        return {'invalidated': invalidate(state, topics=args.topics, reason=args.reason)}
    raise ValueError('unknown command')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', help='compute changes without creating files or locks')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'status', 'reconcile'):
        sub.add_parser(command)
    for command in ('directive', 'propose'):
        p = sub.add_parser(command)
        p.add_argument('--input', type=Path, required=True)
    p = sub.add_parser('resolve')
    p.add_argument('--id', required=True)
    p.add_argument('--action', required=True, choices=['confirm', 'modify', 'reject'])
    p.add_argument('--source', choices=['user', 'human-directive', 'policy'], default='user')
    p.add_argument('--evidence', required=True, help='reference to actual user authorization or covering policy')
    p = sub.add_parser('revalidate', help='record review of unchanged decision semantics and authorization after file changes')
    p.add_argument('--id', required=True)
    p.add_argument('--evidence', required=True, help='reference to the comparison proving the existing decision and authorization still apply')
    p = sub.add_parser('invalidate')
    p.add_argument('--topics', required=True, nargs='+')
    p.add_argument('--reason', required=True)
    p = sub.add_parser('context')
    for name in ('session', 'change', 'phase'):
        p.add_argument('--' + name)
    for name in ('module', 'path', 'test-type'):
        p.add_argument('--' + name, dest=name.replace('-', '_'), action='append')
    p = sub.add_parser('consume')
    p.add_argument('--id', required=True)
    p.add_argument('--evidence', required=True)
    args = parser.parse_args()
    lock = None
    acquired = False
    try:
        root = args.repo.resolve()
        if not root.is_dir():
            raise ValueError('repository does not exist')
        path = relative_file(root, '.smart-test/state.json')
        lock = relative_file(root, '.smart-test/state.lock')
        write = not args.dry_run and args.command not in {'status', 'context'}
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                raise ValueError('state is locked; check the other process before removing a stale lock')
            acquired = True
            with os.fdopen(fd, 'w') as stream:
                stream.write(str(os.getpid()))
        state = json.loads(path.read_text()) if path.exists() else initial()
        if state.get('schema_version') != SCHEMA:
            raise ValueError('unsupported ledger schema version')
        before = copy.deepcopy(state)
        payload = json.loads(args.input.read_text()) if hasattr(args, 'input') else None
        result = apply(state, root, args, payload)
        if write and (not path.exists() or state != before):
            state['revision'] += 1
            atomic_json(path, state)
        result['persisted'] = write
        result['dry_run'] = args.dry_run
        emit(result)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        emit({'error': str(exc)})
        return 2
    finally:
        if acquired:
            lock.unlink()
    return 0


if __name__ == '__main__':
    sys.exit(main())
