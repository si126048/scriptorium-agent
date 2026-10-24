"""Deterministic digest of the working tree for acceptance records.

The acceptance document requires identifying the *actual* verified version, not only a Git
HEAD that may predate uncommitted work. This prints a stable SHA-256 over the relative path and
content hash of every source file that makes up the build, so two runs can be compared.

Usage:
    python scripts/worktree-digest.py [--root .] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

# Build inputs only. Generated artefacts, temporary services, caches, and local databases are
# excluded on purpose: they change without changing what is being accepted.
SKIP_TOP = {'build', 'tmp', 'output', 'data', '.git', '.pytest_cache', '.ruff_cache', '.test-tmp', 'node_modules',
            '.api', '.e2e', 'desktop-build'}
SKIP_DIRS = {'__pycache__', '.mypy_cache', 'node_modules', 'dist', '.vite', '.venv', '.uv-cache',
             '.tmp', 'artifacts', '.pytest_cache', '.ruff_cache', 'target', 'gen', 'site-packages'}
# Build outputs are produced from the sources above; hashing them would make the digest depend on
# whatever was compiled last (and on 100+ MB sidecar binaries). They are ignored as a path prefix.
SKIP_PREFIX = ('src-tauri/bin/',)
SKIP_SUFFIX = {'.pyc', '.pyo', '.sqlite', '.db', '.log', '.tsbuildinfo'}


def digest(root: Path):
    entries = []
    for folder, directories, files in os.walk(root):
        relative_folder = Path(folder).relative_to(root)
        if relative_folder.parts and relative_folder.parts[0] in SKIP_TOP:
            directories[:] = []
            continue
        directories[:] = sorted(d for d in directories
                                if d not in SKIP_DIRS and not d.startswith('.venv'))
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root)
            if path.suffix in SKIP_SUFFIX or relative.as_posix() == '.env':
                continue
            if relative.as_posix().startswith(SKIP_PREFIX):
                continue
            entries.append([relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    entries.sort()

    def combine(rows):
        overall = hashlib.sha256()
        for name, value in rows:
            overall.update(f'{name}\0{value}\n'.encode())
        return overall.hexdigest()

    # Documentation is split out so the identified build stays stable while records are updated.
    code = [row for row in entries if not row[0].startswith(('docs/', 'README'))]
    return {'files': len(entries), 'digest': combine(entries),
            'code_files': len(code), 'code_digest': combine(code),
            'root': str(root)}


def git(*args, root: Path):
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                              timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = digest(root)
    result['git_head'] = git('rev-parse', 'HEAD', root=root)
    result['git_dirty_files'] = len([line for line in git('status', '--porcelain', root=root).splitlines() if line])
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.json else None))


if __name__ == '__main__':
    main()
