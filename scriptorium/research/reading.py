"""Version-pinned display windows; no full source text is transferred to page the reader."""
import sqlalchemy as sa
from . import schema as db
from .service import ResearchError, row


def read_page(s, pid, actor, aid, version_id=None, page=0, segment_id=None, start=None, end=None):
    with s.engine.connect() as c:
        s.access(c, pid, actor); s.asset(c, pid, aid)
        vid = version_id or s.latest_version_id(c, aid)
        version = row(c, db.versions, db.versions.c.id == vid, db.versions.c.asset_id == aid)
        if not version:
            raise ResearchError('TEXT_VERSION_NOT_FOUND', 404)
        manifest = [dict(r) for r in c.execute(sa.select(db.segments.c.id,
            sa.func.length(db.segments.c.text).label('length')).where(db.segments.c.version_id == vid)
            .order_by(db.segments.c.ordinal, db.segments.c.id)).mappings()]
        pages, batch, length = [], [], 0
        def flush():
            nonlocal batch, length
            if batch:
                pages.append(batch)
            batch, length = [], 0
        for item in manifest:
            size = item['length']
            if size > 6000:
                flush()
                for offset in range(0, size, 6000):
                    pages.append([{'id': item['id'], 'start': offset, 'end': min(size, offset + 6000)}])
            else:
                if length + size > 6000 or len(batch) >= 40:
                    flush()
                batch.append({'id': item['id'], 'start': 0, 'end': size}); length += size
        flush()
        if segment_id:
            found = next((i for i, group in enumerate(pages) if any(p['id'] == segment_id and
                p['start'] <= (start or 0) < p['end'] for p in group)), None)
            if found is None:
                raise ResearchError('READING_LOCATION_NOT_FOUND', 404)
            page = found
        if page < 0 or (pages and page >= len(pages)):
            raise ResearchError('READING_PAGE_NOT_FOUND', 404)
        parts = []
        for part in pages[page] if pages else []:
            finish = part['end']
            if part['id'] == segment_id and end is not None:
                size = next(m['length'] for m in manifest if m['id'] == segment_id)
                if end < (start or 0) or end > size:
                    raise ResearchError('INVALID_TEXT_RANGE', 422)
                finish = max(finish, end)
            segment = dict(c.execute(sa.select(*[col for col in db.segments.c if col.name != 'text'],
                sa.func.substr(db.segments.c.text, part['start'] + 1, finish - part['start']).label('text'))
                .where(db.segments.c.id == part['id'])).mappings().one())
            parts.append({'segment': segment, 'start': part['start'], 'end': finish, 'text': segment['text']})
        return {'version': version, 'page': page, 'total': len(pages), 'parts': parts,
            'total_segments': len(manifest), 'total_codepoints': sum(m['length'] for m in manifest)}
