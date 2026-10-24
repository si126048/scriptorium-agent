"""Output models for behavioral profiling."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

SOURCE_TYPES = {'chat', 'interview', 'writing', 'observation'}
STRUCTURAL_DIMENSIONS = {
    'discourse_position', 'big_other', 'demand_desire', 'repeated_signifier',
    'capiton_point', 'fantasy_structure', 'symptom_repetition', 'jouissance',
    'four_discourse', 'rsi_relation', 'narrative_conflict',
}
CLAIM_STATUSES = {'candidate', 'approved', 'rejected', 'needs_revision'}
TRANSFORM_TYPES = {
    'parody', 'homophone', 'character_substitution', 'punctuation_play',
    'reduplication', 'template_variation', 'quote_or_meme', 'code_switch',
    'emoji_substitution', 'unknown_variant',
}
INTERACTION_TYPES = {
    'mention', 'reply', 'quote', 'question_to', 'request_to', 'tease',
    'agreement', 'disagreement', 'correction', 'co_creation',
    'narrative_assignment', 'unknown',
}
RELATION_TYPES = {
    'coordination', 'playful_teasing', 'repeated_request', 'correction',
    'conflict', 'support', 'narrative_co_creation', 'attention_pattern',
    'role_assignment', 'uncertain',
}


class BehavioralProfile(BaseModel):
    """Behavioral style profile for one participant."""

    pseudonym: str

    total_messages: int = 0
    avg_msg_length: float = 0.0
    median_msg_length: float = 0.0
    short_msg_ratio: float = 0.0
    media_ratio: float = 0.0
    emoji_density: float = 0.0

    top_bigrams: list[tuple[str, int]] = Field(default_factory=list)
    signature_phrases: list[str] = Field(default_factory=list)
    unique_expressions: list[str] = Field(default_factory=list)

    top_punctuation: dict[str, float] = Field(default_factory=dict)
    question_ratio: float = 0.0
    exclamation_ratio: float = 0.0
    repeated_punct_ratio: float = 0.0

    opening_patterns: list[str] = Field(default_factory=list)
    closing_patterns: list[str] = Field(default_factory=list)
    bracket_insertions: list[str] = Field(default_factory=list)
    modal_particles: dict[str, int] = Field(default_factory=dict)
    onomatopoeia: list[str] = Field(default_factory=list)

    mention_targets: dict[str, int] = Field(default_factory=dict)
    quote_reply_ratio: float = 0.0
    pure_media_ratio: float = 0.0

    peak_hours: list[int] = Field(default_factory=list)
    burst_ratio: float = 0.0

    style_tags: list[str] = Field(default_factory=list)


class StructuralSummary(BaseModel):
    """Summary from scriptorium structural analysis."""

    discourse_trajectory: list[str] = Field(default_factory=list)
    dominant_discourse: str = ""
    capiton_signifiers: list[str] = Field(default_factory=list)
    desire_direction: str = ""
    hallucination_risk: str = ""


class DistillationCard(BaseModel):
    """Full distillation card combining behavioral + structural layers."""

    pseudonym: str
    behavioral: dict = Field(default_factory=dict)
    structural: StructuralSummary | None = None


class ConsentPolicy(BaseModel):
    withdrawn_at: str | None = None
    expires_at: str | None = None

    def is_active(self) -> bool:
        if self.withdrawn_at:
            return False
        if not self.expires_at:
            return True
        try:
            value = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value > datetime.now(UTC)
        except ValueError:
            return False


class SourceManifest(BaseModel):
    source_id: str
    path: str
    checksum: str
    message_count: int
    time_range: tuple[str, str] | None = None
    format: str = 'plain'


class MaterialSource(BaseModel):
    """A consented input source used for multi-source subject analysis."""

    source_id: str
    participant_id: str
    source_type: str
    path: str
    checksum: str
    context: str | None = None
    collected_at: str | None = None
    consent_scope: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @field_validator('source_type')
    @classmethod
    def valid_source_type(cls, value: str) -> str:
        if value not in SOURCE_TYPES:
            raise ValueError(f'INVALID_SOURCE_TYPE:{value}')
        return value


class EvidenceSpan(BaseModel):
    span_id: str
    source_id: str
    participant_id: str
    text: str
    start_offset: int = 0
    end_offset: int = 0
    speaker: str | None = None
    scene: str | None = None
    timestamp: str | None = None
    message_id: str | None = None
    question_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class MessageRecord(BaseModel):
    """Lossless, serializable chat message record used by the text pipeline."""
    message_id: str
    source_id: str
    participant_id: str
    sender_id: str | None = None
    sender_raw: str | None = None
    timestamp: str | None = None
    raw_text: str
    normalized_text: str
    message_index: int
    char_start: int = 0
    char_end: int = 0
    reply_to_message_id: str | None = None
    quote_message_id: str | None = None
    mention_targets: list[str] = Field(default_factory=list)
    scene: str | None = None
    transform_annotations: list[str] = Field(default_factory=list)


class ConversationWindow(BaseModel):
    window_id: str
    source_id: str
    participant_ids: list[str] = Field(default_factory=list)
    start_message_id: str | None = None
    end_message_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    messages: list[MessageRecord] = Field(default_factory=list)
    scene: str | None = None


class TransformAnnotation(BaseModel):
    annotation_id: str
    message_id: str
    raw_form: str
    canonical_form: str
    transform_type: str
    confidence: float = 0.0
    evidence_span_ids: list[str] = Field(default_factory=list)
    status: str = 'candidate'

    @field_validator('transform_type')
    @classmethod
    def valid_transform_type(cls, value: str) -> str:
        if value not in TRANSFORM_TYPES:
            raise ValueError(f'INVALID_TRANSFORM_TYPE:{value}')
        return value

    @field_validator('confidence')
    @classmethod
    def valid_transform_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError('confidence must be in [0, 1]')
        return value


class InteractionEvent(BaseModel):
    event_id: str
    source_id: str
    window_id: str | None = None
    actor_id: str
    target_id: str
    action_type: str
    message_ids: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(default_factory=list)
    timestamp: str | None = None
    scene: str | None = None
    confidence: float = 0.0

    @field_validator('action_type')
    @classmethod
    def valid_action_type(cls, value: str) -> str:
        if value not in INTERACTION_TYPES:
            raise ValueError(f'INVALID_INTERACTION_TYPE:{value}')
        return value


class RelationshipClaim(BaseModel):
    claim_id: str
    actor_id: str
    target_id: str
    relation_type: str
    direction: str = 'directed'
    text: str
    evidence_span_ids: list[str] = Field(default_factory=list)
    interaction_event_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[str] = Field(default_factory=list)
    time_range: tuple[str, str] | None = None
    scene_range: list[str] = Field(default_factory=list)
    status: str = 'candidate'

    @field_validator('relation_type')
    @classmethod
    def valid_relation_type(cls, value: str) -> str:
        if value not in RELATION_TYPES:
            raise ValueError(f'INVALID_RELATION_TYPE:{value}')
        return value

    @field_validator('direction')
    @classmethod
    def valid_direction(cls, value: str) -> str:
        if value not in {'directed', 'reciprocal', 'unknown'}:
            raise ValueError(f'INVALID_RELATION_DIRECTION:{value}')
        return value

    @field_validator('confidence')
    @classmethod
    def valid_relation_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError('confidence must be in [0, 1]')
        return value

    @field_validator('status')
    @classmethod
    def valid_relation_status(cls, value: str) -> str:
        if value not in CLAIM_STATUSES:
            raise ValueError(f'INVALID_CLAIM_STATUS:{value}')
        return value


class RelationGraph(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    directed_edges: list[dict] = Field(default_factory=list)
    interaction_counts: dict[str, int] = Field(default_factory=dict)
    scene_variants: dict[str, list[str]] = Field(default_factory=dict)
    temporal_changes: list[dict] = Field(default_factory=list)
    evidence_index: dict[str, list[str]] = Field(default_factory=dict)


class StructuralClaim(BaseModel):
    claim_id: str
    dimension: str
    text: str
    evidence_span_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[str] = Field(default_factory=list)
    status: str = 'candidate'
    source: str = 'qwen'
    reviewer_id: str | None = None
    review_reason: str | None = None
    created_at: str | None = None

    @field_validator('source_types')
    @classmethod
    def valid_source_types(cls, values: list[str]) -> list[str]:
        invalid = set(values) - SOURCE_TYPES
        if invalid:
            raise ValueError(f'INVALID_SOURCE_TYPE:{sorted(invalid)[0]}')
        return values

    @field_validator('dimension')
    @classmethod
    def valid_dimension(cls, value: str) -> str:
        if value not in STRUCTURAL_DIMENSIONS:
            raise ValueError(f'INVALID_STRUCTURAL_DIMENSION:{value}')
        return value

    @field_validator('status')
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in CLAIM_STATUSES:
            raise ValueError(f'INVALID_CLAIM_STATUS:{value}')
        return value

    @field_validator('confidence')
    @classmethod
    def valid_structural_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError('confidence must be in [0, 1]')
        return value


class CrossSourceFinding(BaseModel):
    finding_id: str
    type: str
    claim_ids: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(default_factory=list)
    text: str
    confidence: float = 0.0
    status: str = 'candidate'

    @field_validator('type')
    @classmethod
    def valid_finding_type(cls, value: str) -> str:
        if value not in {'consistent', 'context_shift', 'contradiction', 'insufficient_evidence'}:
            raise ValueError(f'INVALID_CROSS_SOURCE_TYPE:{value}')
        return value

    @field_validator('confidence')
    @classmethod
    def valid_finding_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError('confidence must be in [0, 1]')
        return value


class EvidenceClaim(BaseModel):
    id: str
    text: str
    evidence_span_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[str] = Field(default_factory=list)
    status: str = 'candidate'
    source: str = 'qwen'

    @field_validator('confidence')
    @classmethod
    def valid_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError('confidence must be in [0, 1]')
        return value


class ProfileArtifact(BaseModel):
    profile_id: str
    participant_id: str
    pseudonym: str
    schema_version: str = '1.1'
    created_at: str
    source_manifest: list[SourceManifest] = Field(default_factory=list)
    consent: ConsentPolicy
    observed_style: dict = Field(default_factory=dict)
    source_profiles: dict[str, dict] = Field(default_factory=dict)
    structural_claims: list[StructuralClaim] = Field(default_factory=list)
    cross_source_findings: list[CrossSourceFinding] = Field(default_factory=list)
    lexical_motifs: list[dict] = Field(default_factory=list)
    parody_variants: list[TransformAnnotation] = Field(default_factory=list)
    interaction_events: list[InteractionEvent] = Field(default_factory=list)
    relationship_claims: list[RelationshipClaim] = Field(default_factory=list)
    relation_graph: RelationGraph = Field(default_factory=RelationGraph)
    analysis_batches: list[dict] = Field(default_factory=list)
    quality_metrics: dict = Field(default_factory=dict)
    topics: list[EvidenceClaim] = Field(default_factory=list)
    episodes: list[EvidenceClaim] = Field(default_factory=list)
    relationships: list[EvidenceClaim] = Field(default_factory=list)
    inferred_traits: list[EvidenceClaim] = Field(default_factory=list)
    generation_policy: dict = Field(default_factory=dict)
    quality: dict = Field(default_factory=dict)
    review_state: str = 'candidate'
