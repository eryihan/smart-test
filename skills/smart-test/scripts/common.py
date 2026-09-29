"""Small, dependency-free utilities shared by Smart-Test helpers."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

EXCLUDED = {'.git', '.smart-test', '.agents', '.claude', '.codex', '.gradle',
            '.idea', 'node_modules', 'target', 'build', 'dist', '__pycache__', '.venv'}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_file(root, name, must_exist=False):
    """Reject traversal and symlinks, including symlinked parent directories."""
    root = Path(root).resolve()
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('expected a repository-relative path')
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('symlink paths are not supported: ' + str(rel))
    if must_exist and not cursor.is_file():
        raise ValueError('file does not exist: ' + str(rel))
    return cursor


def git(root, *args):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode:
        # Do not echo arbitrary command stderr (it may contain remote credentials).
        raise ValueError('git command failed: ' + args[0])
    return result.stdout


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.smart-test-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_name(name):
    """Skip common credential artifacts entirely, including tracked ones."""
    p = Path(name)
    return not (any(part in EXCLUDED for part in p.parts)
                or p.name.startswith('.env')
                or p.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.jks'}
                or re.search(r'(^|[._-])(credentials?|secrets?)([._-]|$)', p.name, re.I))
