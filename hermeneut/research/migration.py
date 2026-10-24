"""Read-only SQLite snapshot inventory and idempotent, accountable legacy import."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from bisect import bisect_right
from pathlib import Path

import sqlalchemy as sa

from . import schema as db
from .service import ResearchError, row, rows
from .texts import quote_hash
from .worker import run_one

KNOWN = {'projects', 'participants', 'documents', 'spans', 'concepts', 'runs', 'interview_sessions',
         'personas', 'persona_artifacts', 'conversations', 'conversation_messages', 'topology_metrics',
         'doc_store', 'doc_pages'}


def stable(*parts):
    return hashlib.sha256(json.dumps([str(p) for p in parts], ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def snapshot(path: Path):
    path = path.resolve(strict=True)
    # SQLite backup reads a consistent view including committed WAL, without copying live files.
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        target = sqlite3.connect(':memory:')
        source.backup(target)
    target.row_factory = sqlite3.Row
    tables = [r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    content = {}
    for name in sorted(set(tables) & KNOWN):
        quoted = '"' + name.replace('"', '""') + '"'
        content[name] = [dict(r) for r in target.execute(f'SELECT * FROM {quoted}')]
    target.close()
    source_id = stable(str(path).casefold())
    fingerprint = stable(json.dumps(content, ensure_ascii=False, sort_keys=True, default=str))
    return source_id, fingerprint, content


def decoded(record):
    if 'data' in record:
        try:
            data = json.loads(record['data'])
            if isinstance(data, dict):
                return {**record, **data}
        except (TypeError, ValueError):
            pass
    return dict(record)


def migrate(service, source_path: Path, principal: str, *, apply=False, source_roots=()):
    source_id, fingerprint, content = snapshot(source_path)
    report = {'source_id': source_id, 'snapshot_sha256': fingerprint, 'dry_run': not apply,
              'tables': {name: len(data) for name, data in content.items()},
              'preserved': 0, 'already_present': 0, 'materials': [], 'exceptions': [],
              'project_map': {}, 'anchors_migrated': 0}
    if not apply:
        report['note'] = 'Read-only snapshot; no target database or object writes. FTS indexes are rebuildable.'
        return report
    if service is None:
        raise ValueError('SERVICE_REQUIRED_FOR_APPLY')
    source_projects = {str(decoded(p)['id']): decoded(p) for p in content.get('projects', [])}
    for table, records in content.items():
        for record in records:
            p = decoded(record).get('project_id')
            if p:
                source_projects.setdefault(str(p), {'id': str(p), 'name': str(p)})
    source_projects['unassigned'] = {'id': 'unassigned', 'name': '旧材料：归属待确认'}
    for old, p in source_projects.items():
        pid = stable(source_id, 'project', old)
        report['project_map'][old] = pid
        with service.engine.connect() as c:
            existing = row(c, db.projects, db.projects.c.id == pid)
        if not existing:
            service.create_project(principal, p.get('name') or old,
                p.get('description') or 'Migrated legacy project', pid)
        else:
            with service.engine.connect() as c:
                service.access(c, pid, principal, True)

    people = {(str(p.get('project_id')), str(p.get('id'))): p
              for r in content.get('participants', []) if (p := decoded(r))}
    person_of = {str(p.get('id')): p for p in [decoded(r) for r in content.get('personas', [])]}
    conv_of = {str(p.get('id')): p for p in [decoded(r) for r in content.get('conversations', [])]}
    document_of = {str(p.get('id')): p for p in [decoded(r) for r in content.get('documents', [])]}

    def project_for(table, data):
        if table == 'projects':
            return str(data['id'])
        if data.get('project_id'):
            return str(data['project_id'])
        if table == 'spans':
            owner = document_of.get(str(data.get('document_id')), {})
            return str(owner.get('project_id', 'unassigned'))
        if data.get('persona_id'):
            return str(person_of.get(str(data['persona_id']), {}).get('project_id', 'unassigned'))
        if data.get('conversation_id'):
            conv = conv_of.get(str(data['conversation_id']), {})
            return str(conv.get('project_id') or person_of.get(str(conv.get('persona_id')), {}).get('project_id', 'unassigned'))
        return 'unassigned'

    # Expired/withdrawn identities are tombstoned; derived sensitive data is not resurrected.
    from hermeneut.models import ConsentScope
    blocked_people = set()
    for (pid, person_id), person in people.items():
        consent = person.get('consent_scope') or {}
        if person.get('withdrawn_at') or not ConsentScope.model_validate(consent).is_active():
            blocked_people.add((pid, person_id))

    def is_blocked(table, data):
        if table == 'projects':
            return False
        pid = project_for(table, data)
        participant_id = data.get('participant_id')
        if table == 'participants':
            participant_id = data.get('id')
        if table == 'spans':
            participant_id = document_of.get(str(data.get('document_id')), {}).get('participant_id')
        if data.get('persona_id'):
            participant_id = person_of.get(str(data['persona_id']), {}).get('participant_id')
        if data.get('conversation_id'):
            conv = conv_of.get(str(data['conversation_id']), {})
            participant_id = person_of.get(str(conv.get('persona_id')), {}).get('participant_id')
        return participant_id is not None and (str(pid), str(participant_id)) in blocked_people

    def key_for(table, record):
        if record.get('id'):
            key = str(record['id'])
        elif table == 'doc_store':
            key = str(record['doc_id'])
        elif table == 'doc_pages':
            key = f'{record["doc_id"]}:{record["page_number"]}'
        else:
            key = stable(json.dumps(record, sort_keys=True))
        return json.dumps([record.get('project_id'), key], ensure_ascii=False) if table == 'participants' else key

    # Bound transactions and queries per 500 rows, not per individual evidence span.
    for table, raw_records in content.items():
        for offset in range(0, len(raw_records), 500):
            batch = []
            for record in raw_records[offset:offset + 500]:
                data = decoded(record)
                old_project = project_for(table, data)
                pid = report['project_map'].get(old_project, report['project_map']['unassigned'])
                key = key_for(table, record)
                suppressed = is_blocked(table, data)
                batch.append({'id': stable(source_id, table, key), 'project_id': pid, 'source': source_id,
                    'table_name': table, 'legacy_key': key, 'payload': {} if suppressed else record,
                    'status': 'consent_blocked' if suppressed else 'preserved'})
                if suppressed:
                    report['exceptions'].append({'table': table, 'key': key,
                        'reason': 'PARTICIPANT_CONSENT_INACTIVE'})
            with service.engine.begin() as c:
                # Lock source projects in stable order to serialize reruns without row-by-row round trips.
                for pid in sorted({r['project_id'] for r in batch}):
                    service.access(c, pid, principal, True)
                    c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == pid).with_for_update())
                existing = {r['id']: r for r in rows(c, db.legacy, db.legacy.c.id.in_([r['id'] for r in batch]))}
                pending = []
                for record in batch:
                    prior = existing.get(record['id'])
                    if prior:
                        report['already_present'] += 1
                        if prior['payload'] != record['payload']:
                            report['exceptions'].append({'table': table, 'key': record['legacy_key'],
                                'reason': 'SOURCE_CHANGED_OR_REDACTED'})
                    else:
                        pending.append(record)
                if pending:
                    c.execute(db.legacy.insert(), pending)
                    report['preserved'] += len(pending)

    material_map = {}
    for table in ('documents', 'doc_store'):
        for record in content.get(table, []):
            data = decoded(record)
            old_project = project_for(table, data)
            pid = report['project_map'].get(old_project, report['project_map']['unassigned'])
            old_key = key_for(table, record)
            lid = stable(source_id, table, old_key)
            # Conservative suppression: a mixed-consent legacy project requires explicit curation.
            suppressed = is_blocked(table, data)
            if suppressed:
                continue
            raw, name, origin_status = None, None, 'original_missing'
            origin = data.get('origin') or data.get('origin_path')
            if origin:
                candidate = Path(origin).resolve()
                if (any(candidate.is_relative_to(Path(root).resolve()) for root in source_roots)
                        and candidate.is_file() and candidate.stat().st_size <= service.settings.max_upload_bytes):
                    raw, name, origin_status = candidate.read_bytes(), candidate.name, 'original_preserved'
            if raw is None:
                if table == 'documents' and data.get('text'):
                    raw, name = data['text'].encode('utf-8'), f'legacy-{old_key}.txt'
                elif table == 'doc_store':
                    pages = sorted((r for r in content.get('doc_pages', []) if r['doc_id'] == data['doc_id']),
                                   key=lambda r: r['page_number'])
                    if pages:
                        raw = '\f'.join(p['text'] for p in pages).encode('utf-8')
                        name = f'legacy-{data["doc_id"]}.txt'
            if raw is None:
                report['exceptions'].append({'table': table, 'key': old_key, 'reason': 'NO_ORIGINAL_OR_TEXT'})
                continue
            try:
                additional = {}
                if Path(name).suffix.lower() not in {'.txt', '.md', '.pdf', '.xml', '.tei'} and data.get('text'):
                    additional['legacy_transcription'] = data['text']
                j = service.import_material(pid, principal, raw, name,
                    f'legacy-{lid}', {'legacy_id': old_key, 'source_id': source_id,
                                      'origin_status': origin_status, 'bibliography_status': 'unknown',
                                      'participant_id': data.get('participant_id'), **additional})
                run_one(service, j['id'])
                with service.engine.connect() as c:
                    completed = row(c, db.jobs, db.jobs.c.id == j['id'])
                aid = j['payload']['asset_id']
                material_map[old_key] = (pid, aid)
                report['materials'].append({'legacy_id': old_key, 'asset_id': aid,
                    'status': completed['state'], 'origin_status': origin_status})
                if completed['state'] != 'succeeded':
                    report['exceptions'].append({'table': table, 'key': old_key,
                        'reason': completed.get('error') or completed['state']})
            except (ResearchError, ValueError) as exc:
                report['exceptions'].append({'table': table, 'key': old_key, 'reason': str(exc).split(':')[0]})

    # Reuse segment projections; trust old offsets only when checked against the actual old text.
    cache, quote_cache = {}, {}
    with service.engine.connect() as c:
        mappings = {r['id']: r['status'] for r in rows(c, db.legacy,
            db.legacy.c.source == source_id, db.legacy.c.table_name == 'spans')}
        for old_key, (pid, aid) in material_map.items():
            segs = sorted(rows(c, db.segments, db.segments.c.asset_id == aid), key=lambda s: s['ordinal'])
            original_text = document_of.get(old_key, {}).get('text', '')
            offsets, cursor = [], 0
            for segment in segs:
                found = original_text.find(segment['text'], cursor) if original_text else -1
                if found < 0:
                    offsets = []
                    break
                offsets.append(found)
                cursor = found + len(segment['text'])
            cache[aid] = (segs, original_text, offsets)
    pending_anchors, pending_maps = [], []

    def flush_anchors():
        if not pending_anchors:
            return
        with service.engine.begin() as c:
            for aid in sorted({a for _, a in material_map.values()}):
                c.execute(sa.select(db.assets.c.id).where(db.assets.c.id == aid).with_for_update())
                a = row(c, db.assets, db.assets.c.id == aid)
                if a['status'] == 'revoked':
                    raise ResearchError('MATERIAL_REVOKED_DURING_MIGRATION')
            c.execute(db.anchors.insert(), pending_anchors)
            c.execute(db.legacy.update().where(db.legacy.c.id == sa.bindparam('legacy_id'))
                .values(status=sa.bindparam('mapped_status')), pending_maps)
        pending_anchors.clear()
        pending_maps.clear()

    for raw_span in content.get('spans', []):
        span = decoded(raw_span)
        target = material_map.get(str(span.get('document_id')))
        quote = span.get('excerpt', '')
        lid = stable(source_id, 'spans', str(span['id']))
        if not target or not quote or mappings.get(lid, '').startswith('anchor:'):
            continue
        pid, aid = target
        segs, old_text, offsets = cache[aid]
        matches = []
        start, end = span.get('char_start', -1), span.get('char_end', -1)
        if offsets and isinstance(start, int) and isinstance(end, int) and old_text[start:end] == quote:
            index = bisect_right(offsets, start) - 1
            if index >= 0:
                local = start - offsets[index]
                if segs[index]['text'][local:local + len(quote)] == quote:
                    matches = [(segs[index], local)]
        if not matches:
            key = (aid, quote)
            if key not in quote_cache:
                found_matches = []
                for segment in segs:
                    cursor = 0
                    while (found := segment['text'].find(quote, cursor)) >= 0:
                        found_matches.append((segment, found))
                        cursor = found + 1
                        if len(found_matches) > 1:
                            break
                    if len(found_matches) > 1:
                        break
                quote_cache[key] = found_matches
            matches = quote_cache[key]
        if len(matches) == 1:
            segment, start = matches[0]
            anchor_id = stable(source_id, 'anchor', span['id'])
            pending_anchors.append({'id': anchor_id, 'project_id': pid, 'segment_id': segment['id'],
                'start_codepoint': start, 'end_codepoint': start + len(quote),
                'exact_quote': quote, 'quote_sha256': quote_hash(quote)})
            pending_maps.append({'legacy_id': lid, 'mapped_status': f'anchor:{anchor_id}'})
            report['anchors_migrated'] += 1
            if len(pending_anchors) >= 500:
                flush_anchors()
        else:
            report['exceptions'].append({'table': 'spans', 'key': str(span['id']),
                'reason': 'AMBIGUOUS_OR_MISSING_QUOTE'})
    flush_anchors()
    # Promote preserved snapshots to operational entities, retaining originals for audit.
    kinds = {'participants': 'participant', 'documents': 'document', 'spans': 'span', 'concepts': 'concept',
        'runs': 'analysis_run', 'interview_sessions': 'interview', 'personas': 'persona',
        'persona_artifacts': 'persona_artifact', 'conversations': 'persona_conversation',
        'conversation_messages': 'persona_message', 'topology_metrics': 'metric'}
    report['operational_entities'] = 0
    for table, kind in kinds.items():
        source_records = content.get(table, [])
        for offset in range(0, len(source_records), 500):
            batch = []
            for original in source_records[offset:offset + 500]:
                data = decoded(original)
                if is_blocked(table, data):
                    continue
                if isinstance(data.get('data'), str):
                    data.pop('data')
                old_project = project_for(table, data)
                pid = report['project_map'].get(old_project, report['project_map']['unassigned'])
                data['project_id'] = pid
                if kind == 'participant':
                    data.setdefault('permissions', {'material_collection': True, 'profile_analysis': False, 'agent_simulation': False})
                if kind == 'document' and str(data['id']) in material_map:
                    data['metadata'] = {**data.get('metadata', {}), 'asset_id': material_map[str(data['id'])][1]}
                identifier = stable(source_id, 'entity', table, key_for(table, original))
                batch.append({'id': identifier, 'project_id': pid, 'kind': kind, 'external_id': str(data['id']),
                    'payload': data, 'revision': 1, 'created_at': db.now()})
            if batch:
                with service.engine.begin() as c:
                    existing = set(c.execute(sa.select(db.entities.c.id).where(db.entities.c.id.in_(
                        [x['id'] for x in batch]))).scalars())
                    pending = [x for x in batch if x['id'] not in existing]
                    if pending:
                        c.execute(db.entities.insert(), pending)
                        report['operational_entities'] += len(pending)
    from .workspace import add_message
    for old_id, value in conv_of.items():
        if is_blocked('conversations', value):
            continue
        old_pid = project_for('conversations', value)
        pid = report['project_map'].get(old_pid, report['project_map']['unassigned'])
        conv_id = stable(source_id, 'conversation', old_id)
        with service.engine.begin() as c:
            if not row(c, db.conversations, db.conversations.c.id == conv_id):
                c.execute(db.conversations.insert().values(id=conv_id, project_id=pid,
                    title=value.get('title') or '风格模拟历史对话', archived=False, revision=1,
                    workspace={}, created_at=db.now()))
            for message in (decoded(m) for m in content.get('conversation_messages', [])):
                if message.get('conversation_id') != old_id:
                    continue
                mid = stable(source_id, 'message', message['id'])
                if not row(c, db.messages, db.messages.c.id == mid):
                    add_message(c, pid, conv_id, message.get('role', 'assistant'), message.get('content', ''),
                        metadata={'persona_id': value.get('persona_id'), 'legacy': True,
                                  'ai_generated': message.get('ai_generated', False)}, identifier=mid)
    report['accounted_source_rows'] = report['preserved'] + report['already_present']
    report['source_rows'] = sum(report['tables'].values())
    return report
