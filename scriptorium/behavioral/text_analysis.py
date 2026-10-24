"""Deterministic text-layer analysis primitives.

These functions deliberately produce candidates. They never infer a psychological
relationship from frequency alone; model review and human approval remain separate.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from .models import (
    ConversationWindow,
    InteractionEvent,
    MessageRecord,
    RelationGraph,
    TransformAnnotation,
)

_PUNCT = re.compile(r"([!?！？。．…])\1+")
_HOMO = re.compile(r"(?P<a>[\u4e00-\u9fff])(?P<b>[a-zA-Z0-9])")
_MEDIA = re.compile(r"\[(?:图片|表情|语音|视频|文件|转账)[^\]]*\]")


def _id(prefix: str, *parts: object) -> str:
    raw = '|'.join(str(p) for p in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}'


def canonicalize_text(text: str) -> str:
    """Conservative retrieval normalization; raw text is never changed."""
    value = text.strip().lower()
    value = re.sub(r'[！!]{2,}', '！', value)
    value = re.sub(r'[？?]{2,}', '？', value)
    value = re.sub(r'([哈嘿呵啊])\1{2,}', r'\1\1', value)
    value = re.sub(r'\s+', ' ', value)
    return value


def detect_transform_candidates(messages: Iterable[dict[str, Any]]) -> list[TransformAnnotation]:
    """Find explainable variants with rules, leaving semantic judgment to review."""
    output: list[TransformAnnotation] = []
    for msg in messages:
        raw = str(msg.get('raw_text', msg.get('content', '')))
        canonical = canonicalize_text(raw)
        kinds: list[str] = []
        if _PUNCT.search(raw): kinds.append('punctuation_play')
        if re.search(r'(.)\1{2,}', raw): kinds.append('reduplication')
        if re.search(r'[A-Za-z]\d|\d[A-Za-z]|[\u4e00-\u9fff][A-Za-z]', raw): kinds.append('code_switch')
        if _MEDIA.search(raw): kinds.append('emoji_substitution')
        if re.search(r'(?:哈哈|呵呵|好家伙|不是我说|笑死).{0,2}(?:哈哈|呵呵|笑死)', raw):
            kinds.append('template_variation')
        if not kinds and canonical != raw.lower(): kinds.append('unknown_variant')
        for kind in kinds:
            output.append(TransformAnnotation(
                annotation_id=_id('transform', msg.get('message_id'), kind),
                message_id=str(msg.get('message_id')),
                raw_form=raw, canonical_form=canonical, transform_type=kind,
                confidence=0.55 if kind != 'unknown_variant' else 0.35,
                evidence_span_ids=[f"span_{str(msg.get('message_id'))[4:]}"] if str(msg.get('message_id')).startswith('msg_') else [],
            ))
    return output


def make_windows(messages: list[dict[str, Any]], batch_size: int = 80, overlap: int = 8) -> list[ConversationWindow]:
    """Create full-coverage overlapping windows; no prefix truncation."""
    if batch_size <= 0: raise ValueError('BATCH_SIZE_MUST_BE_POSITIVE')
    records = [MessageRecord.model_validate({
        **m, 'raw_text': m.get('raw_text', m.get('content', '')),
        'normalized_text': m.get('normalized_text', m.get('content', '')),
        'message_index': m.get('message_index', m.get('index', i)),
    }) for i, m in enumerate(messages)]
    step = max(1, batch_size - max(0, overlap))
    windows: list[ConversationWindow] = []
    for start in range(0, len(records), step):
        chunk = records[start:start + batch_size]
        if not chunk: break
        windows.append(ConversationWindow(
            window_id=_id('window', chunk[0].source_id, chunk[0].message_id, chunk[-1].message_id),
            source_id=chunk[0].source_id,
            participant_ids=sorted({x.participant_id for x in chunk} | {x.sender_id for x in chunk if x.sender_id}),
            start_message_id=chunk[0].message_id, end_message_id=chunk[-1].message_id,
            start_time=chunk[0].timestamp, end_time=chunk[-1].timestamp,
            messages=chunk, scene=chunk[0].scene,
        ))
        if start + batch_size >= len(records): break
    return windows


def extract_interaction_events(messages: list[dict[str, Any]], aliases: dict[str, list[str]] | None = None) -> list[InteractionEvent]:
    aliases = aliases or {}
    lookup = {a: pid for pid, vals in aliases.items() for a in [pid, *vals]}
    events: list[InteractionEvent] = []
    for msg in messages:
        actor = str(msg.get('sender_id') or msg.get('sender_raw') or msg.get('participant_id') or 'unknown')
        text = str(msg.get('raw_text', msg.get('content', '')))
        targets = list(msg.get('mention_targets') or [])
        for target_raw in targets:
            target = lookup.get(target_raw, target_raw)
            if target == actor: continue
            events.append(InteractionEvent(
                event_id=_id('event', msg.get('message_id'), actor, target, 'mention'),
                source_id=str(msg.get('source_id')), actor_id=actor, target_id=target,
                action_type='mention', message_ids=[str(msg.get('message_id'))],
                evidence_span_ids=[f"span_{str(msg.get('message_id'))[4:]}"], timestamp=msg.get('timestamp'),
                scene=msg.get('scene'), confidence=0.95,
            ))
        for field, action in (('reply_to_message_id', 'reply'), ('quote_message_id', 'quote')):
            target = msg.get(field)
            if target:
                events.append(InteractionEvent(
                    event_id=_id('event', msg.get('message_id'), actor, target, action),
                    source_id=str(msg.get('source_id')), actor_id=actor, target_id=str(target),
                    action_type=action, message_ids=[str(msg.get('message_id'))],
                    evidence_span_ids=[f"span_{str(msg.get('message_id'))[4:]}"], timestamp=msg.get('timestamp'),
                    scene=msg.get('scene'), confidence=0.8,
                ))
        if text.startswith(('问', '请', '能否', '可以')) and targets:
            target = lookup.get(targets[0], targets[0])
            events.append(InteractionEvent(
                event_id=_id('event', msg.get('message_id'), actor, target, 'request_to'),
                source_id=str(msg.get('source_id')), actor_id=actor, target_id=target,
                action_type='request_to', message_ids=[str(msg.get('message_id'))],
                evidence_span_ids=[f"span_{str(msg.get('message_id'))[4:]}"], timestamp=msg.get('timestamp'),
                scene=msg.get('scene'), confidence=0.65,
            ))
    return events


def build_relation_graph(events: list[InteractionEvent], claims: list[Any] = None) -> RelationGraph:
    claims = claims or []
    nodes = sorted({x for e in events for x in (e.actor_id, e.target_id)})
    counts = Counter(f'{e.actor_id}->{e.target_id}' for e in events)
    scenes: dict[str, set[str]] = defaultdict(set)
    evidence: dict[str, list[str]] = defaultdict(list)
    for event in events:
        key = f'{event.actor_id}->{event.target_id}'
        if event.scene: scenes[key].add(event.scene)
        evidence[key].extend(event.evidence_span_ids)
    edges = []
    for key, count in counts.items():
        actor, target = key.split('->', 1)
        edges.append({'actor_id': actor, 'target_id': target, 'event_count': count,
                      'status': 'candidate', 'evidence_span_ids': sorted(set(evidence[key]))})
    for claim in claims:
        key = f'{claim.actor_id}->{claim.target_id}'
        for edge in edges:
            if f"{edge['actor_id']}->{edge['target_id']}" == key:
                edge.setdefault('relationship_claims', []).append(claim.claim_id)
    return RelationGraph(nodes=nodes, directed_edges=edges,
                         interaction_counts=dict(counts),
                         scene_variants={k: sorted(v) for k, v in scenes.items()},
                         evidence_index={k: sorted(set(v)) for k, v in evidence.items()})


def stable_expression_candidates(annotations: list[TransformAnnotation], messages: list[dict[str, Any]], min_windows: int = 2) -> list[dict[str, Any]]:
    """Only promote variants spread across windows/scenes; single memes remain candidates."""
    by_form: dict[str, list[TransformAnnotation]] = defaultdict(list)
    for a in annotations: by_form[a.canonical_form].append(a)
    index = {m.get('message_id'): m for m in messages}
    result = []
    for form, items in by_form.items():
        windows = set()
        for a in items:
            if a.message_id not in index: continue
            msg = index[a.message_id]
            timestamp = msg.get('timestamp')
            # Calendar-day buckets prevent a long single event from looking stable.
            windows.add(str(timestamp)[:10] if timestamp else int(msg.get('message_index', 0)) // 80)
        scenes = {index[a.message_id].get('scene') for a in items if a.message_id in index and index[a.message_id].get('scene')}
        stable = len(windows) >= min_windows or len(scenes) >= min_windows or len(items) >= 3
        result.append({'canonical_form': form, 'raw_examples': [a.raw_form for a in items[:5]],
                       'contexts': sorted(scenes), 'time_dispersion': len(windows),
                       'scene_dispersion': len(scenes), 'stable': stable,
                       'confidence': max(a.confidence for a in items),
                       'evidence_span_ids': sorted({sid for a in items for sid in a.evidence_span_ids})})
    return result
