from __future__ import annotations

import logging
import re
from pathlib import Path

from .credentials import redact_credentials
from .db import Store, checksum, new_id
from .models import ConsentScope, EvidenceSpan, SourceDocument

logger = logging.getLogger(__name__)
MAX_SPAN_CHARS = 2000

_CHAT_PATTERNS = [
    re.compile(r'^\[?\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?\]?\s*.+[:：]'),
    re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\s*[-—]?\s*.+[:：]'),
    re.compile(r'^.+?[\s(]\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?[)]?\s*[:：]'),
]


def _is_chat_format(text: str) -> bool:
    lines = [l for l in text.split('\n') if l.strip()]
    if len(lines) < 3:
        return False
    matches = sum(1 for l in lines[:20] if any(p.match(l.strip()) for p in _CHAT_PATTERNS))
    return matches >= len(lines[:20]) * 0.5


def _split_chat_messages(text: str) -> list[tuple[int, int, str]]:
    segments: list[tuple[int, int, str]] = []
    lines = text.split('\n')
    pos = 0
    current_start: int | None = None
    current_lines: list[str] = []
    for line in lines:
        line_end = pos + len(line) + 1
        is_msg_start = any(p.match(line.strip()) for p in _CHAT_PATTERNS) if line.strip() else False
        if is_msg_start and current_lines:
            merged = '\n'.join(current_lines).strip()
            if merged:
                segments.append((current_start, current_start + len('\n'.join(current_lines)), merged))
            current_lines = []
            current_start = None
        if is_msg_start or current_start is None and line.strip():
            current_start = pos
        if line.strip():
            current_lines.append(line)
        pos = line_end
    if current_lines and current_start is not None:
        merged = '\n'.join(current_lines).strip()
        if merged:
            segments.append((current_start, current_start + len('\n'.join(current_lines)), merged))
    return segments


def _split_paragraphs(text: str) -> list[tuple[int, int, str]]:
    segments: list[tuple[int, int, str]] = []
    for para in re.finditer(r'[^\n]+(?:\n|$)', text):
        start, end = para.start(), para.end()
        excerpt = text[start:end].strip()
        if excerpt:
            segments.append((start, end, excerpt))
    return segments


def read_source(path: str):
    p=Path(path); suffix=p.suffix.lower()
    if suffix in ('.txt', '.md', '.json'): return p.read_text(encoding='utf-8')
    if suffix=='.pdf':
        try:
            from pypdf import PdfReader
            return '\n'.join(page.extract_text() or '' for page in PdfReader(str(p)).pages)
        except Exception as e: raise ValueError(f'PDF_TEXT_EXTRACTION_FAILED: {e}')
    raise ValueError('UNSUPPORTED_SOURCE_TYPE')


def ingest(store: Store, path: str, project_id: str, participant_id: str|None=None, consent=None):
    text=read_source(path); kind=Path(path).suffix.lower().lstrip('.')
    if not text.strip(): raise ValueError('EMPTY_SOURCE')
    cs=checksum(text)
    if hasattr(store, 'find_document_by_checksum'):
        known = store.find_document_by_checksum(project_id, cs)
        existing = {'data': known.model_dump_json()} if known else None
    else:
        existing=store.conn.execute("SELECT data FROM documents WHERE project_id=? AND json_extract(data,'$.checksum')=?",(project_id,cs)).fetchone()
    if existing: return SourceDocument.model_validate_json(existing['data'])
    d=SourceDocument(id=new_id('doc'),project_id=project_id,participant_id=participant_id,origin=str(Path(path).resolve()),type=kind,checksum=cs,text=text,consent_scope=consent or ConsentScope())
    store.put_document(d)
    if _is_chat_format(text):
        paragraphs = _split_chat_messages(text)
        logger.debug("chat format detected for %s, %d messages", d.id, len(paragraphs))
    else:
        paragraphs = _split_paragraphs(text)
    spans = []
    for start, end, excerpt in paragraphs:
        if len(excerpt) <= MAX_SPAN_CHARS:
            spans.append(EvidenceSpan(id=new_id('span'),document_id=d.id,char_start=start,char_end=end,excerpt=excerpt,excerpt_hash=checksum(excerpt)))
        else:
            for chunk_start in range(start, end, MAX_SPAN_CHARS - 200):
                chunk_end = min(chunk_start + MAX_SPAN_CHARS, end)
                chunk = text[chunk_start:chunk_end].strip()
                if chunk:
                    spans.append(EvidenceSpan(id=new_id('span'),document_id=d.id,char_start=chunk_start,char_end=chunk_end,excerpt=chunk,excerpt_hash=checksum(chunk)))
    store.put_spans(spans)
    logger.info("ingested %s: %d spans from %d chars", d.id, len(spans), len(text))
    return d


def ingest_text(store: Store, text: str, project_id: str, participant_id: str | None = None) -> list[str]:
    """Ingest raw text directly (not from a file). Returns list of source_ids."""
    text = text.strip()
    if not text:
        return []
    cs = checksum(text)
    if hasattr(store, 'find_document_by_checksum'):
        known = store.find_document_by_checksum(project_id, cs)
        existing = {'data': known.model_dump_json()} if known else None
    else:
        existing = store.conn.execute(
            "SELECT data FROM documents WHERE project_id=? AND json_extract(data,'$.checksum')=?",
            (project_id, cs),
        ).fetchone()
    if existing:
        return [SourceDocument.model_validate_json(existing['data']).id]
    d = SourceDocument(
        id=new_id('doc'), project_id=project_id, participant_id=participant_id,
        origin='chat-input', type='txt', checksum=cs, text=text,
        consent_scope=ConsentScope(),
    )
    store.put_document(d)
    paragraphs = _split_chat_messages(text) if _is_chat_format(text) else _split_paragraphs(text)
    spans = []
    for start, end, excerpt in paragraphs:
        if len(excerpt) <= MAX_SPAN_CHARS:
            spans.append(EvidenceSpan(
                id=new_id('span'), document_id=d.id, char_start=start, char_end=end,
                excerpt=excerpt, excerpt_hash=checksum(excerpt),
            ))
        else:
            for chunk_start in range(start, end, MAX_SPAN_CHARS - 200):
                chunk_end = min(chunk_start + MAX_SPAN_CHARS, end)
                chunk = text[chunk_start:chunk_end].strip()
                if chunk:
                    spans.append(EvidenceSpan(
                        id=new_id('span'), document_id=d.id, char_start=chunk_start,
                        char_end=chunk_end, excerpt=chunk, excerpt_hash=checksum(chunk),
                    ))
    store.put_spans(spans)
    return [d.id]


def search(store: Store, q: str, project_id: str | None = None, limit: int = 5) -> list[dict]:
    if hasattr(store, 'search_materials'):
        return store.search_materials(q, project_id, limit)
    q = q.strip()
    if not q:
        return []
    # Treat user input as terms rather than raw FTS5 syntax.
    safe_query = ' '.join(f'"{term.replace(chr(34), "")}"' for term in q.split())
    
    if project_id:
        rows = store.conn.execute(
            "SELECT d.data, snippet(document_fts, 1, '**', '**', '...', 32) as snip "
            "FROM document_fts JOIN documents d ON d.id = document_fts.document_id "
            "WHERE document_fts MATCH ? AND d.project_id = ? LIMIT ?", 
            (safe_query, project_id, max(1, min(limit, 100)))
        ).fetchall()
    else:
        rows = store.conn.execute(
            "SELECT d.data, snippet(document_fts, 1, '**', '**', '...', 32) as snip "
            "FROM document_fts JOIN documents d ON d.id = document_fts.document_id "
            "WHERE document_fts MATCH ? LIMIT ?", 
            (safe_query, max(1, min(limit, 100)))
        ).fetchall()
    
    out = []
    for r in rows:
        d = SourceDocument.model_validate_json(r['data'])
        snip = r['snip'] or ''
        pos = d.text.lower().find(q.lower())
        if pos < 0:
            pos = max(0, d.text.lower().find(snip[:20].lower())) if snip else 0
        excerpt = d.text[max(0, pos - 120):pos + len(q) + 120]
        out.append({
            'document_id': d.id,
            'citation_id': f'{d.id}:{pos}',
            'excerpt': redact_credentials(excerpt),
            'snippet': redact_credentials(snip),
            'char_start': pos,
            'char_end': min(len(d.text), pos + len(q)),
            'checksum': d.checksum,
        })
    return out

def validate_span(store,span_id):
    s=store.get_span(span_id)
    if not s:return False
    d=store.get_document(s.document_id)
    return bool(d and d.text[s.char_start:s.char_end].strip()==s.excerpt.strip() and checksum(s.excerpt)==s.excerpt_hash)
