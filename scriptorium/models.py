from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class RunState(StrEnum):
    CREATED = 'CREATED'
    INGESTED = 'INGESTED'
    OBSERVED = 'OBSERVED'
    INTERPRETED = 'INTERPRETED'
    CRITIQUED = 'CRITIQUED'
    NEEDS_HUMAN_REVIEW = 'NEEDS_HUMAN_REVIEW'
    APPROVED = 'APPROVED'
    COMPILED = 'COMPILED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    REVISION_REQUIRED = 'REVISION_REQUIRED'


class ReviewStatus(StrEnum):
    PROVISIONAL = 'provisional'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    NEEDS_REVISION = 'needs_revision'


class ReviewDecision(StrEnum):
    APPROVE = 'approve'
    REJECT = 'reject'
    REVISE = 'revise'


class ConsentScope(BaseModel):
    withdrawn_at: str | None = None
    expires_at: str | None = None

    def is_active(self) -> bool:
        if self.withdrawn_at:
            return False
        if not self.expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return expiry > datetime.now(UTC)
        except ValueError:
            return False


class Project(BaseModel):
    id: str
    name: str = ''
    description: str = ''
    policy_version: str = '1.0'
    owner_id: str = 'local-user'
    created_at: str = ''


class Participant(BaseModel):
    id: str
    project_id: str
    pseudonym: str
    consent_scope: ConsentScope
    withdrawn_at: str | None = None
    created_at: str = ''


class InterviewState(StrEnum):
    CREATED = 'CREATED'
    IN_PROGRESS = 'IN_PROGRESS'
    PAUSED = 'PAUSED'
    COMPLETED = 'COMPLETED'
    WITHDRAWN = 'WITHDRAWN'


class InterviewQuestion(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=2000)
    stage: str = 'default'
    module_id: str = 'core'
    module_title: str = '访谈'
    context_hint: str = ''
    required: bool = True
    allow_followup: bool = True


class InterviewConfig(BaseModel):
    config_id: str
    version: str = '1.0'
    title: str = '研究访谈'
    research_goal: str = ''
    questions: list[InterviewQuestion] = Field(min_length=1)
    max_primary_questions: int = Field(default=8, ge=1, le=8)
    max_followups: int = Field(default=6, ge=0, le=6)

    @model_validator(mode='after')
    def validate_questions(self):
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError('DUPLICATE_INTERVIEW_QUESTION_ID')
        if len(self.questions) > self.max_primary_questions:
            raise ValueError('INTERVIEW_QUESTION_LIMIT_EXCEEDED')
        return self


class InterviewTurn(BaseModel):
    question_id: str
    question_text: str
    answer_text: str = Field(min_length=1, max_length=20000)
    kind: str = 'primary'
    parent_question_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    asked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    answered_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @model_validator(mode='after')
    def validate_kind(self):
        if self.kind not in {'primary', 'followup'}:
            raise ValueError('INVALID_INTERVIEW_TURN_KIND')
        if self.kind == 'followup' and not self.parent_question_id:
            raise ValueError('FOLLOWUP_PARENT_REQUIRED')
        return self


class InterviewSession(BaseModel):
    id: str
    project_id: str
    participant_id: str
    config_id: str
    state: InterviewState = InterviewState.CREATED
    current_question_id: str | None = None
    current_question_text: str | None = None
    current_question_kind: str = 'primary'
    current_parent_question_id: str | None = None
    primary_index: int = 0
    followup_count: int = 0
    turns: list[InterviewTurn] = Field(default_factory=list)
    source_id: str | None = None
    run_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    audit: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SourceDocument(BaseModel):
    id: str
    project_id: str
    participant_id: str | None = None
    origin: str
    type: str
    checksum: str
    text: str
    consent_scope: ConsentScope = Field(default_factory=ConsentScope)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSpan(BaseModel):
    id: str
    document_id: str
    char_start: int
    char_end: int
    excerpt: str
    excerpt_hash: str

    @model_validator(mode='after')
    def _validate_offsets(self):
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError('invalid char offsets')
        if not self.excerpt.strip():
            raise ValueError('empty excerpt')
        return self


class ConceptCard(BaseModel):
    id: str
    canonical_name: str
    definition: str
    theoretical_period: str = 'unspecified'
    source_span_ids: list[str] = Field(default_factory=list)
    review_status: str = 'draft'


class Observation(BaseModel):
    id: str
    label: str
    evidence_span_ids: list[str]
    rsi_register: str | None = Field(default=None, alias='register')
    register_markers: list[str] = Field(default_factory=list)


class Counterexample(BaseModel):
    id: str
    text: str
    evidence_span_ids: list[str] = Field(default_factory=list)
    disconfirmation_score: float = 0.0
    source: str = 'llm'

    @model_validator(mode='after')
    def _validate_score(self):
        if not 0.0 <= self.disconfirmation_score <= 1.0:
            raise ValueError('disconfirmation_score must be in [0, 1]')
        if self.source not in {'llm', 'human', 'cross_critique'}:
            raise ValueError("source must be 'llm', 'human', or 'cross_critique'")
        return self

    def __contains__(self, value: str) -> bool:
        return value in self.text or value in self.id


class Hypothesis(BaseModel):
    id: str
    concept_ids: list[str]
    support_ids: list[str]
    alternatives: list[str]
    counterexamples: list[Counterexample] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PROVISIONAL
    theory_reference_ids: list[str] = Field(default_factory=list)
    discourse_type: str | None = None
    desire_residual: DesireResidual | None = None
    points_de_capiton: list[PointDeCapiton] = Field(default_factory=list)
    matheme_ids: list[str] = Field(default_factory=list)
    grounding_score: float = 0.0
    fuzzy_groundings: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def _coerce_counterexamples(cls, values):
        if isinstance(values, dict) and 'counterexamples' in values:
            values = dict(values)
            values['counterexamples'] = [
                item if isinstance(item, dict) else {
                    'id': f"ce_{values.get('id', 'hyp')}_{index + 1}",
                    'text': str(item), 'source': 'llm'
                }
                for index, item in enumerate(values['counterexamples'])
            ]
        return values


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    source_ids: list[str] = Field(default_factory=list)
    status: str = 'provisional'


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    evidence_span_ids: list[str]
    weight: float | None = None


class NarrativeOperator(BaseModel):
    id: str
    operator: str
    source_finding_ids: list[str]
    allowed: bool = False
    use_cases: list[str] = Field(default_factory=list)
    counterexamples: list[Counterexample] = Field(default_factory=list)
    approval_state: str = 'provisional'


class PointDeCapiton(BaseModel):
    id: str
    signifier: str
    fixation_span_ids: list[str] = Field(default_factory=list)
    duration: int = 0
    centrality: float = 0.0

    @field_validator('duration', mode='before')
    @classmethod
    def _coerce_duration(cls, v):
        if isinstance(v, float):
            return int(v)
        return v


class DesireResidual(BaseModel):
    demand_surface: str
    need_object: str | None = None
    residual_score: float = 0.0

    @model_validator(mode='after')
    def _validate_residual_range(self):
        if not (0.0 <= self.residual_score <= 1.0):
            raise ValueError(f'residual_score must be in [0, 1], got {self.residual_score}')
        return self


class CulturalAnnotation(BaseModel):
    id: str
    span_id: str
    entity_name: str
    entity_type: str
    confidence: float = 1.0
    context_brief: str = ''
    source: str = 'gazetteer'

    @model_validator(mode='after')
    def _validate_confidence(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f'confidence must be in [0, 1], got {self.confidence}')
        return self


class AnalysisPacket(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    run_id: str
    participant_id: str
    state: RunState
    observations: list[Observation] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    narrative_operators: list[NarrativeOperator] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    cultural_annotations: list[CulturalAnnotation] = Field(default_factory=list)
    hallucination_reports: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisRun(BaseModel):
    id: str
    project_id: str
    participant_id: str
    source_ids: list[str]
    state: RunState
    idempotency_key: str
    packet: AnalysisPacket | None = None
    audit: list[dict[str, Any]] = Field(default_factory=list)
    topology: dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    reviewer_id: str
    decision: ReviewDecision
    reason: str = ''


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class PerspectiveConfig(BaseModel):
    id: str
    name: str
    concept_inventory: list[str] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)
    vocabulary: dict[str, str] = Field(default_factory=dict)
    evidence_prompt_variant: str | None = None
    interpreter_prompt_variant: str | None = None
    critique_prompt_variant: str | None = None


class PerspectiveAnalysis(BaseModel):
    perspective_id: str
    observations: list[Observation] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    grounding_summary: dict[str, Any] = Field(default_factory=dict)


class CrossCritique(BaseModel):
    source_perspective_id: str
    target_perspective_id: str
    counterexamples: list[Counterexample] = Field(default_factory=list)
    blind_spot_alerts: list[str] = Field(default_factory=list)
    epistemic_gaps: list[str] = Field(default_factory=list)
    page_references: list[dict[str, Any]] = Field(default_factory=list)


class SynthesisReport(BaseModel):
    convergence: list[dict[str, Any]] = Field(default_factory=list)
    divergence: list[dict[str, Any]] = Field(default_factory=list)
    unique_insights: list[dict[str, Any]] = Field(default_factory=list)
    meta_critique: list[str] = Field(default_factory=list)
    recommended_hypotheses: list[str] = Field(default_factory=list)


class DialecticalResult(BaseModel):
    run_id: str
    perspective_ids: list[str]
    phase1_analyses: list[PerspectiveAnalysis] = Field(default_factory=list)
    phase2_cross_critiques: list[CrossCritique] = Field(default_factory=list)
    phase3_synthesis: SynthesisReport | None = None
    phase4_report: str | None = None


class PageEvidenceSpan(BaseModel):
    id: str
    doc_id: str
    page_number: int
    char_start: int = 0
    char_end: int = 0
    excerpt: str = ''
    excerpt_hash: str = ''
    outline_path: list[str] = Field(default_factory=list)
