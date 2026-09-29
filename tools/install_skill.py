#!/usr/bin/env python3
"""Install the same skill directory into Codex or Claude Code without dependencies."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

SOURCE = Path(__file__).resolve().parents[1] / 'skills' / 'smart-test'


def contents(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('refusing a symlink inside skill: ' + str(path))
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} or path.name == '.DS_Store':
            continue
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def install(parent, replace=False, dry_run=False):
    source_files = contents(SOURCE)
    if 'SKILL.md' not in source_files:
        raise ValueError('source skill is missing SKILL.md')
    target = parent.expanduser().absolute() / 'smart-test'
    if target.is_symlink():
        raise ValueError('destination is a symlink; choose an explicit installation directory')
    if target.exists():
        if not target.is_dir():
            raise ValueError('destination exists and is not a directory')
        if contents(target) == source_files:
            return {'status': 'UNCHANGED', 'path': str(target)}
        if not replace:
            raise ValueError('different skill already exists; use --replace to preserve it as a backup before updating')
    if dry_run:
        return {'status': 'DRY_RUN', 'path': str(target), 'files': len(source_files), 'replace': target.exists()}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.smart-test-install-', dir=str(target.parent)))
    backup = None
    try:
        for relative in source_files:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, destination)
        if contents(temporary) != source_files:
            raise ValueError('installation copy did not match source checksums')
        if target.exists():
            if not replace or target.is_symlink():
                raise ValueError('destination changed during install; inspect it before retrying')
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            # Backups live outside the discovery directory, avoiding duplicate skills.
            backup_parent = target.parent.parent / 'smart-test-install-backups'
            backup_parent.mkdir(parents=True, exist_ok=True)
            backup = backup_parent / ('smart-test-' + stamp + '-' + uuid.uuid4().hex[:8])
            target.rename(backup)
        try:
            temporary.rename(target)
        except OSError:
            if backup:
                backup.rename(target)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {'status': 'INSTALLED', 'path': str(target), 'backup': str(backup) if backup else None,
            'files': len(source_files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=['codex', 'claude'], required=True)
    parser.add_argument('--scope', choices=['user', 'project'], default='user')
    parser.add_argument('--project', type=Path, help='required for project scope')
    parser.add_argument('--dest', type=Path, help='override the parent skills directory')
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.dest:
            parent = args.dest
        elif args.scope == 'project':
            if not args.project or not args.project.is_dir():
                raise ValueError('project scope requires an existing --project directory')
            parent = args.project / ('.agents' if args.host == 'codex' else '.claude') / 'skills'
        else:
            parent = Path.home() / ('.codex' if args.host == 'codex' else '.claude') / 'skills'
        print(json.dumps(install(parent, args.replace, args.dry_run), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
