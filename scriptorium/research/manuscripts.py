"""Shared, revision-checked manuscript use cases for HTTP and background workers."""
import copy
import sqlalchemy as sa
from . import schema as db
from .service import ResearchError, row, rows


def chapter(s, c, pid, rid, identifier):
    value = row(c, db.document_chapters, db.document_chapters.c.project_id == pid,
        db.document_chapters.c.record_id == rid, db.document_chapters.c.id == identifier)
    if not value:
        raise ResearchError('CHAPTER_NOT_FOUND', 404)
    s.validate_evidence(c, pid, value['payload'])
    return value


def save_chapter(s, c, pid, rid, identifier, revision, ordinal, payload):
    from .documents import validate_editor, markdown
    import json
    payload = copy.deepcopy(payload)
    validate_editor(payload.get('editor_json'))
    payload['text'] = markdown(payload['editor_json'])
    if len(json.dumps(payload)) > 500000:
        raise ResearchError('CHAPTER_TOO_LARGE', 413)
    record = row(c, db.records, db.records.c.id == rid, db.records.c.project_id == pid)
    if not record:
        raise ResearchError('ARTIFACT_NOT_FOUND', 404)
    s.validate_evidence(c, pid, payload)
    old = row(c, db.document_chapters, db.document_chapters.c.id == identifier)
    if old and (old['project_id'] != pid or old['record_id'] != rid):
        raise ResearchError('CHAPTER_NOT_FOUND', 404)
    if (old and old['revision'] != revision) or (not old and revision is not None):
        raise ResearchError('REVISION_CONFLICT', 409)
    value = {'id': identifier, 'project_id': pid, 'record_id': rid, 'ordinal': ordinal,
        'revision': old['revision'] + 1 if old else 1, 'payload': payload,
        'created_at': old['created_at'] if old else db.now()}
    if old:
        s.put_record(c, pid, 'review', {'title': '文稿章节修订记录', 'text': '',
            'source_record_ids': [rid], 'chapter_id': identifier, 'previous_chapter': old})
        c.execute(db.document_chapters.update().where(db.document_chapters.c.id == identifier).values(**value))
    else:
        c.execute(db.document_chapters.insert().values(**value))
    return value


def export_snapshot(s, c, pid, rid, revision=None):
    # Serialize with every manuscript/chapter edit without requiring export write privileges.
    c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == pid).with_for_update())
    record = row(c, db.records, db.records.c.id == rid, db.records.c.project_id == pid)
    if not record:
        raise ResearchError('ARTIFACT_NOT_FOUND', 404)
    if revision is not None and revision != record['revision']:
        raise ResearchError('REVISION_CONFLICT', 409)
    chapters = [dict(r) for r in c.execute(sa.select(db.document_chapters).where(
        db.document_chapters.c.record_id == rid, db.document_chapters.c.project_id == pid)
        .order_by(db.document_chapters.c.ordinal, db.document_chapters.c.id)).mappings()]
    for item in [record, *chapters]:
        s.validate_evidence(c, pid, item['payload'])
    from .documents import citation_ids
    aids = set()
    for item in [record, *chapters]:
        payload = item['payload']
        aids.update(payload.get('asset_ids', []))
        ids = set(payload.get('evidence_ids', []) + citation_ids(payload.get('editor_json')))
        for anchor in rows(c, db.anchors, db.anchors.c.project_id == pid, db.anchors.c.id.in_(ids)):
            segment = row(c, db.segments, db.segments.c.id == anchor['segment_id'], db.segments.c.project_id == pid)
            if segment:
                aids.add(segment['asset_id'])
    return copy.deepcopy({'record': record, 'chapters': chapters,
        'assets': [s.asset(c, pid, aid) for aid in sorted(aids)]})
