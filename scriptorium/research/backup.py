"""Consistent logical archive with content hashes; restore only into an empty research schema."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import sqlalchemy as sa

from . import schema as db
from .storage import FileObjects


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(service, destination: Path):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    archive_objects = FileObjects(destination / 'objects')
    manifest = {'format': 'scriptorium-backup.v1', 'schema': 'research_0004',
                'created_at': db.now(), 'tables': {}, 'objects': []}
    with service.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c, c.begin():
        names = ', '.join(table.name for table in db.metadata.sorted_tables)
        c.execute(sa.text(f'LOCK TABLE {names} IN SHARE MODE'))
        keys = set()
        for table in db.metadata.sorted_tables:
            target = destination / f'{table.name}.jsonl'
            count = 0
            query = sa.select(table)
            if 'created_at' in table.c:
                query = query.order_by(table.c.created_at)
            with target.open('w', encoding='utf-8', newline='\n') as handle:
                for value in c.execute(query).mappings():
                    data = dict(value)
                    if table in (db.assets, db.versions) and data.get('object_key'):
                        keys.add(data['object_key'])
                    handle.write(json.dumps(data, ensure_ascii=False) + '\n')
                    count += 1
            manifest['tables'][table.name] = {'rows': count, 'sha256': file_hash(target)}
        for key in sorted(keys):
            archive_objects.put(service.objects.read(key))
            manifest['objects'].append(key)
        ledger = service.objects.root / 'withdrawals.jsonl'
        if ledger.exists():
            target = destination / 'withdrawals.jsonl'
            target.write_bytes(ledger.read_bytes())
            manifest['withdrawal_ledger_sha256'] = file_hash(target)
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'destination': str(destination), 'tables': len(manifest['tables']), 'objects': len(keys)}


def restore(service, source: Path, withdrawal_ledger: Path | None = None):
    source = source.resolve(strict=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 'scriptorium-backup.v1' or manifest.get('schema') not in {'research_0002', 'research_0003', 'research_0004'}:
        raise ValueError('UNSUPPORTED_BACKUP')
    expected = {t.name for t in db.metadata.sorted_tables}
    v3_tables = expected - {'r_model_calls', 'r_method_drafts', 'r_conversation_events', 'r_document_chapters'}
    older_tables = v3_tables - {'r_conversations', 'r_messages', 'r_entities', 'r_research_runs', 'r_research_steps', 'r_decisions'}
    if set(manifest['tables']) not in (expected, v3_tables, older_tables):
        raise ValueError('BACKUP_TABLE_SET_MISMATCH')
    for name in manifest['tables']:
        path = source / f'{name}.jsonl'
        if not path.resolve().is_relative_to(source) or file_hash(path) != manifest['tables'][name]['sha256']:
            raise ValueError('BACKUP_CHECKSUM_MISMATCH')
    ledgers = [service.objects.root / 'withdrawals.jsonl']
    if manifest.get('withdrawal_ledger_sha256'):
        archived_ledger = source / 'withdrawals.jsonl'
        if file_hash(archived_ledger) != manifest['withdrawal_ledger_sha256']:
            raise ValueError('BACKUP_LEDGER_CHECKSUM_MISMATCH')
        ledgers.append(archived_ledger)
    if withdrawal_ledger:
        ledgers.append(withdrawal_ledger.resolve(strict=True))
    withdrawals = set()
    for ledger in ledgers:
        if ledger.exists():
            for line in ledger.read_text(encoding='utf-8').splitlines():
                value = json.loads(line)
                withdrawals.add((str(value['project_id']), str(value['asset_id'])))
    archive_objects = FileObjects(source / 'objects')
    with service.engine.begin() as c:
        names = ', '.join(sorted(expected))
        c.execute(sa.text(f'LOCK TABLE {names} IN EXCLUSIVE MODE'))
        for table in db.metadata.sorted_tables:
            if c.execute(sa.select(sa.func.count()).select_from(table)).scalar():
                raise ValueError('RESTORE_REQUIRES_EMPTY_RESEARCH_SCHEMA')
        for key in manifest['objects']:
            restored_key, _ = service.objects.put(archive_objects.read(key))
            if restored_key != key:
                raise ValueError('BACKUP_OBJECT_KEY_MISMATCH')
        for table in db.metadata.sorted_tables:
            if table.name not in manifest['tables']:
                continue
            batch, count = [], 0
            with (source / f'{table.name}.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    value = json.loads(line)
                    if table is db.jobs and value['state'] in {'running', 'cancel_requested'}:
                        value.update(state='queued' if value['state'] == 'running' else 'cancelled',
                                     lease_until=None, lease_token=None)
                    if table is db.outbox:
                        value.update(done=False, attempts=0, error=None)
                    batch.append(value)
                    count += 1
                    if len(batch) == 500:
                        c.execute(table.insert(), batch)
                        batch.clear()
            if batch:
                c.execute(table.insert(), batch)
            if count != manifest['tables'][table.name]['rows']:
                raise ValueError('BACKUP_ROW_COUNT_MISMATCH')
    replayed = 0
    for pid, aid in sorted(withdrawals):
        with service.engine.connect() as c:
            p = c.execute(sa.select(db.projects).where(db.projects.c.id == pid)).mappings().first()
            a = c.execute(sa.select(db.assets).where(db.assets.c.id == aid, db.assets.c.project_id == pid)).mappings().first()
        if p and a:
            service.revoke(pid, p['owner_id'], aid)
            replayed += 1
    return {'status': 'restored', 'reindex_required': True, 'withdrawals_replayed': replayed}
