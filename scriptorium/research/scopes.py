"""Freeze material versions and exact code-point ranges at submission."""
from . import schema as db
from .service import ResearchError, row


def freeze(service, pid, principal, body):
    explicit = body.get('scope')
    if explicit is not None and (body.get('asset_ids') or body.get('segment_ids')):
        raise ResearchError('SCOPE_FIELDS_ARE_MUTUALLY_EXCLUSIVE', 422)
    requests = explicit if explicit is not None else ([{'asset_id': aid} for aid in body.get('asset_ids', [])]
        + [{'segment_id': sid} for sid in body.get('segment_ids', [])])
    result = []
    with service.engine.connect() as c:
        service.access(c, pid, principal)
        for item in requests:
            sid = item.get('segment_id')
            if sid:
                segment = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == pid)
                if not segment or (item.get('asset_id') and item['asset_id'] != segment['asset_id']):
                    raise ResearchError('SEGMENT_NOT_FOUND', 404)
                service.asset(c, pid, segment['asset_id'])
                if item.get('version_id') and item['version_id'] != segment['version_id']:
                    raise ResearchError('SCOPE_VERSION_MISMATCH', 422)
                segments = [segment]
            else:
                if not item.get('asset_id'):
                    raise ResearchError('SCOPE_MATERIAL_REQUIRED', 422)
                if 'start_codepoint' in item or 'end_codepoint' in item:
                    raise ResearchError('SCOPE_RANGE_REQUIRES_SEGMENT', 422)
                segments = service.get_segments(pid, principal, item['asset_id'], item.get('version_id'))['segments']
            for segment in segments:
                start, end = item.get('start_codepoint', 0), item.get('end_codepoint', len(segment['text']))
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(segment['text']):
                    raise ResearchError('INVALID_SCOPE_RANGE', 422)
                if item.get('exact_quote') is not None and segment['text'][start:end] != item['exact_quote']:
                    raise ResearchError('SCOPE_QUOTE_MISMATCH', 422)
                window = {'asset_id': segment['asset_id'], 'version_id': segment['version_id'],
                          'segment_id': segment['id'], 'start': start, 'end': end}
                if window not in result:
                    result.append(window)
    return result
