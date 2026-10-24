"""Multi-source subject-structure artifact builder."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .inference import infer_relationship_claims, infer_structural_claims_full
from .materials import load_materials, validate_span_references
from .models import (
    ConsentPolicy,
    CrossSourceFinding,
    ProfileArtifact,
    StructuralClaim,
)
from .text_analysis import (
    build_relation_graph,
    detect_transform_candidates,
    extract_interaction_events,
    stable_expression_candidates,
)


class SubjectProfiler:
    def __init__(self, sources_config: str | Path, *, root: str | Path | None = None,
                 consent: ConsentPolicy | dict | None = None):
        self.sources_config = Path(sources_config)
        self.root = Path(root) if root else None
        self.consent = consent if isinstance(consent, ConsentPolicy) else ConsentPolicy.model_validate(
            consent or {}
        )

    def build(self, participant_id: str, provider=None, *, with_relations: bool = True,
              batch_size: int = 80, aliases: dict[str, list[str]] | None = None,
              registered_materials=None) -> ProfileArtifact:
        if not self.consent.is_active():
            raise PermissionError('PROFILE_CONSENT_REQUIRED')
        sources, spans = (registered_materials if registered_materials is not None else
                          load_materials(self.sources_config, root=self.root, participant_id=participant_id))
        for source in sources:
            scope = source.consent_scope
            if scope.get('withdrawn_at'):
                raise PermissionError(f'SOURCE_WITHDRAWN:{source.source_id}')
        source_profiles = self._source_profiles(sources, spans)
        messages = [{
            'message_id': s.message_id or s.span_id.replace('span_', 'msg_'),
            'source_id': s.source_id, 'participant_id': s.participant_id,
            'sender_id': s.speaker or s.participant_id, 'sender_raw': s.speaker,
            'timestamp': s.timestamp, 'raw_text': s.text, 'normalized_text': s.text,
            'message_index': i, 'index': i, 'content': s.text, 'scene': s.scene,
            'mention_targets': re.findall(r'@([^\s@：:，,。！？!?]+)', s.text),
        } for i, s in enumerate(spans)]
        transforms = detect_transform_candidates(messages)
        lexical_motifs = stable_expression_candidates(transforms, messages)
        events = extract_interaction_events(messages, aliases=aliases or {})
        relation_claims = []
        relation_warnings = []
        observed = {
            'material_count': len(sources),
            'span_count': len(spans),
            'source_types': sorted({s.source_type for s in sources}),
            'total_characters': sum(len(s.text) for s in spans),
            'warnings': ['observations describe source behavior and are not personality diagnoses'],
        }
        claims: list[StructuralClaim] = []
        analysis_batches: list[dict] = []
        warnings = list(observed['warnings'])
        if provider is not None:
            try:
                claims, analysis_batches = infer_structural_claims_full(provider, [
                    {'span_id': s.span_id, 'source_id': s.source_id, 'participant_id': s.participant_id,
                     'text': s.text, 'source_type': next(x.source_type for x in sources if x.source_id == s.source_id),
                     'scene': s.scene, 'question_id': s.question_id, 'tags': s.tags}
                    for s in spans
                ], batch_size=batch_size)
                validate_span_references(claims, spans, participant_id)
            except Exception as exc:
                warnings.append(f'inference_failed:{type(exc).__name__}')
            if with_relations and events:
                try:
                    relation_claims = infer_relationship_claims(
                        provider, [e.model_dump() for e in events],
                        [s.model_dump() for s in spans],
                    )
                except Exception as exc:
                    relation_warnings.append(f'relation_inference_failed:{type(exc).__name__}')
        else:
            warnings.append('DASHSCOPE_API_KEY not set, structural extraction skipped')
        warnings.extend(relation_warnings)
        graph = build_relation_graph(events, relation_claims)
        findings = self._cross_source_findings(claims)
        approved = [c for c in claims if c.status == 'approved']
        return ProfileArtifact(
            profile_id=f'subject_{participant_id}', participant_id=participant_id,
            pseudonym=participant_id, created_at=datetime.now(UTC).isoformat(),
            schema_version='1.1',
            source_manifest=[{
                'source_id': s.source_id, 'path': s.path, 'checksum': s.checksum,
                'message_count': sum(1 for span in spans if span.source_id == s.source_id),
                'time_range': None, 'format': Path(s.path).suffix.lower().lstrip('.') or 'plain',
            } for s in sources],
            consent=self.consent, observed_style=observed,
            source_profiles=source_profiles, structural_claims=claims,
            cross_source_findings=findings,
            lexical_motifs=lexical_motifs,
            parody_variants=transforms,
            interaction_events=events,
            relationship_claims=relation_claims,
            relation_graph=graph,
            analysis_batches=analysis_batches,
            quality_metrics={
                'full_coverage': True,
                'transform_candidate_count': len(transforms),
                'interaction_event_count': len(events),
                'relationship_claim_count': len(relation_claims),
            },
            generation_policy={
                'subject_constraints': [c.claim_id for c in approved],
                'approved_claims_only': True,
                'raw_text_in_prompt': False,
            },
            quality={'sample_size': len(spans), 'coverage': 1.0 if spans else 0.0, 'warnings': warnings},
            review_state='approved' if claims and len(approved) == len(claims) else 'candidate',
        )

    @staticmethod
    def _source_profiles(sources, spans) -> dict[str, dict[str, Any]]:
        result = {}
        for source in sources:
            own = [s for s in spans if s.source_id == source.source_id]
            lengths = [len(s.text) for s in own]
            result[source.source_id] = {
                'source_type': source.source_type,
                'context': source.context,
                'span_count': len(own),
                'character_count': sum(lengths),
                'avg_span_length': round(sum(lengths) / len(lengths), 2) if lengths else 0.0,
                'question_ids': sorted({s.question_id for s in own if s.question_id}),
                'tags': dict(Counter(tag for s in own for tag in s.tags)),
            }
        return result

    @staticmethod
    def _cross_source_findings(claims: list[StructuralClaim]) -> list[CrossSourceFinding]:
        by_dimension: dict[str, list[StructuralClaim]] = {}
        for claim in claims:
            by_dimension.setdefault(claim.dimension, []).append(claim)
        findings: list[CrossSourceFinding] = []
        for dimension, items in by_dimension.items():
            source_types = set(t for item in items for t in item.source_types)
            if len(items) >= 2 and len(source_types) >= 2:
                findings.append(CrossSourceFinding(
                    finding_id=f'finding_{dimension}', type='consistent',
                    claim_ids=[item.claim_id for item in items],
                    evidence_span_ids=[sid for item in items for sid in item.evidence_span_ids],
                    text=f'多个材料来源均产生了 {dimension} 候选，需要人工确认是否为跨场景一致结构。',
                    confidence=min(item.confidence for item in items), status='candidate',
                ))
        return findings

    @staticmethod
    def apply_review(artifact: ProfileArtifact, review: dict[str, Any]) -> ProfileArtifact:
        if review.get('participant_id') != artifact.participant_id:
            raise ValueError('REVIEW_PARTICIPANT_MISMATCH')
        by_id = {claim.claim_id: claim for claim in artifact.structural_claims}
        for decision in review.get('decisions', []):
            claim = by_id.get(decision.get('claim_id'))
            if claim is None:
                raise ValueError(f'CLAIM_NOT_FOUND:{decision.get("claim_id")}')
            status = decision.get('status')
            if status not in {'approved', 'rejected', 'needs_revision'}:
                raise ValueError(f'INVALID_REVIEW_STATUS:{status}')
            claim.status = status
            claim.reviewer_id = decision.get('reviewer_id')
            claim.review_reason = decision.get('reason')
            claim.source = 'human'
        approved = [c.claim_id for c in artifact.structural_claims if c.status == 'approved']
        artifact.generation_policy['subject_constraints'] = approved
        artifact.review_state = 'approved' if artifact.structural_claims and len(approved) == len(artifact.structural_claims) else 'candidate'
        return artifact
