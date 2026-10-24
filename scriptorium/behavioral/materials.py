"""Multi-source material registration and evidence span extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .chat_parser import load_normalized_messages, read_text
from .models import SOURCE_TYPES, EvidenceSpan, MaterialSource


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _stable_id(prefix: str, source_id: str, index: int, text: str) -> str:
    raw = f'{source_id}:{index}:{text}'.encode()
    return f'{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}'


def _check_path(path: Path, root: Path | None) -> Path:
    resolved = path.resolve()
    if root is not None and root.resolve() not in resolved.parents:
        raise ValueError('SOURCE_PATH_OUTSIDE_ROOT')
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    return resolved


def _plain_spans(source: MaterialSource, text: str) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    cursor = 0
    for index, line in enumerate(text.splitlines()):
        start = text.find(line, cursor)
        end = start + len(line)
        cursor = end
        if not line.strip():
            continue
        spans.append(EvidenceSpan(
            span_id=_stable_id('span', source.source_id, index, line),
            source_id=source.source_id, participant_id=source.participant_id,
            text=line, start_offset=start, end_offset=end,
            scene=source.metadata.get('scene') or source.context,
            tags=list(source.metadata.get('tags', [])),
        ))
    return spans


def _chat_spans(source: MaterialSource, path: Path) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for item in load_normalized_messages(
        path, source.source_id, source.participant_id,
        source.metadata.get('default_sender'), source.metadata.get('scene') or source.context,
    ):
        spans.append(EvidenceSpan(
            span_id=f"span_{item['message_id'][4:]}",
            source_id=source.source_id, participant_id=source.participant_id,
            text=item['content'], start_offset=item['char_start'],
            end_offset=item['char_end'], message_id=item['message_id'],
            speaker=item.get('sender_raw'), timestamp=item.get('timestamp'),
            scene=source.metadata.get('scene') or source.context,
            tags=list(source.metadata.get('tags', [])),
        ))
    return spans


def _interview_spans(source: MaterialSource, payload: dict[str, Any]) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    turns = payload.get('turns')
    if not isinstance(turns, list):
        raise ValueError('INTERVIEW_TURNS_REQUIRED')
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError('INVALID_INTERVIEW_TURN')
        answer = turn.get('answer_text', turn.get('answer', turn.get('text')))
        if not isinstance(answer, str) or not answer.strip():
            # Existing interview exports may already contain span IDs. Those are
            # accepted only when the caller provides an external answer file.
            if turn.get('answer_span_ids'):
                continue
            raise ValueError(f'INTERVIEW_ANSWER_REQUIRED:{index}')
        question_id = str(turn.get('question_id', f'q_{index + 1}'))
        tags = [str(x) for x in turn.get('tags', [])]
        spans.append(EvidenceSpan(
            span_id=_stable_id('span', source.source_id, index, answer),
            source_id=source.source_id, participant_id=source.participant_id,
            text=answer, start_offset=0, end_offset=len(answer),
            speaker=source.metadata.get('speaker') or 'participant',
            scene=source.context or 'interview', question_id=question_id,
            tags=tags,
        ))
    return spans


def load_materials(config_path: str | Path, *, root: str | Path | None = None,
                   participant_id: str | None = None) -> tuple[list[MaterialSource], list[EvidenceSpan]]:
    """Load a sources manifest and return validated sources and evidence spans."""
    config_file = Path(config_path).resolve()
    payload = json.loads(config_file.read_text(encoding='utf-8'))
    entries = payload.get('sources') if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries:
        raise ValueError('SOURCES_REQUIRED')
    root_path = Path(root).resolve() if root else config_file.parent
    sources: list[MaterialSource] = []
    spans: list[EvidenceSpan] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError('INVALID_SOURCE_ENTRY')
        sid = str(raw.get('source_id') or raw.get('id') or '')
        pid = str(raw.get('participant_id') or '')
        stype = str(raw.get('source_type') or raw.get('type') or '')
        if not sid or not pid or not stype:
            raise ValueError('SOURCE_ID_PARTICIPANT_AND_TYPE_REQUIRED')
        if sid in seen:
            raise ValueError(f'DUPLICATE_SOURCE_ID:{sid}')
        seen.add(sid)
        if participant_id and pid != participant_id:
            continue
        if stype not in SOURCE_TYPES:
            raise ValueError(f'INVALID_SOURCE_TYPE:{stype}')
        raw_path = Path(raw.get('path', ''))
        if not raw_path.is_absolute():
            raw_path = config_file.parent / raw_path
        path = _check_path(raw_path, root_path)
        text = read_text(path)
        source = MaterialSource(
            source_id=sid, participant_id=pid, source_type=stype,
            path=str(path), checksum=_digest(text), context=raw.get('context'),
            collected_at=raw.get('collected_at'),
            consent_scope=dict(raw.get('consent_scope') or {}),
            metadata=dict(raw.get('metadata') or {}),
        )
        sources.append(source)
        if stype == 'chat':
            spans.extend(_chat_spans(source, path))
        elif stype == 'interview' and path.suffix.lower() == '.json':
            spans.extend(_interview_spans(source, json.loads(text)))
        else:
            spans.extend(_plain_spans(source, text))
    if participant_id and not sources:
        raise ValueError(f'PARTICIPANT_SOURCES_NOT_FOUND:{participant_id}')
    return sources, spans


def validate_span_references(claims: list[Any], spans: list[EvidenceSpan], participant_id: str) -> None:
    allowed = {span.span_id for span in spans if span.participant_id == participant_id}
    for claim in claims:
        if not set(claim.evidence_span_ids) <= allowed:
            raise ValueError(f'INVALID_EVIDENCE_REFERENCE:{claim.claim_id}')
