"""Freeze the legacy SQLite source into a reproducible, read-only migration snapshot.

The live file may have uncheckpointed WAL frames and may still be written by an old entry point,
so the snapshot is taken through SQLite's backup API from a read-only connection instead of a
plain file copy. The result records SHA-256 and per-table row counts, and is made read-only on
disk so a later `--apply` cannot silently run against the live database.

    python scripts/snapshot-source.py --source data/lacan.db --out output/migration-freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def table_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        names = [row[0] for row in connection.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        return {name: connection.execute(f'select count(*) from "{name}"').fetchone()[0] for name in names}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='data/lacan.db', type=Path)
    parser.add_argument('--out', default='output/migration-freeze', type=Path)
    parser.add_argument('--label', default='')
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    label = (args.label + '-' if args.label else '') + source.stem
    destination = args.out / f'{label}-{stamp}.db'

    # Consistent snapshot including committed WAL, without opening the source for writing.
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as live, sqlite3.connect(str(destination)) as copy:
        live.backup(copy)
    destination.chmod(stat.S_IREAD)

    counts = table_counts(destination.resolve())
    record = {
        'source': str(source),
        'source_sha256': sha256(source),
        'source_bytes': source.stat().st_size,
        'snapshot': str(destination),
        'snapshot_sha256': sha256(destination),
        'snapshot_bytes': destination.stat().st_size,
        'read_only': not bool(destination.stat().st_mode & stat.S_IWRITE),
        'created_at': datetime.now(UTC).isoformat(),
        'tables': counts,
        'row_total': sum(counts.values()),
        'note': 'Frozen copy for migration rehearsals. Never run --apply against the live source.',
    }
    record_path = args.out / f'{destination.name}.snapshot.json'
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({**record, 'record': str(record_path)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
