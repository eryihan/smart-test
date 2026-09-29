#!/usr/bin/env python3
"""Build a reproducible, portable skill zip and its SHA-256 checksum."""
import hashlib
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'skills' / 'smart-test'
    destination = root / 'dist'
    destination.mkdir(exist_ok=True)
    archive = destination / 'smart-test.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('symlinks are not allowed in the package')
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} or path.name == '.DS_Store':
                continue
            info = zipfile.ZipInfo('smart-test/' + path.relative_to(source).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n')
    print(str(archive))
    print(checksum)


if __name__ == '__main__':
    main()
