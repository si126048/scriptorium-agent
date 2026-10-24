import pytest
from pydantic import ValidationError
from scriptorium.models import (
    ConsentScope, EvidenceSpan, RunState, ReviewStatus, ReviewDecision,
    Project, Observation, Hypothesis,
    AnalysisPacket, AnalysisRun, ErrorBody, ErrorResponse,
)
from scriptorium.db import checksum


def test_consent_defaults():
    cs = ConsentScope()
    assert cs.withdrawn_at is None
    assert cs.expires_at is None


def test_consent_withdrawal():
    cs = ConsentScope(withdrawn_at='2026-01-01T00:00:00Z')
    assert cs.withdrawn_at == '2026-01-01T00:00:00Z'


def test_run_state_enum_values():
    assert RunState.CREATED == "CREATED"
    assert RunState.NEEDS_HUMAN_REVIEW == "NEEDS_HUMAN_REVIEW"
    assert RunState.APPROVED == "APPROVED"
    assert RunState.COMPILED == "COMPILED"
    assert RunState.FAILED == "FAILED"


def test_review_decision_values():
    assert ReviewDecision.APPROVE == "approve"
    assert ReviewDecision.REJECT == "reject"
    assert ReviewDecision.REVISE == "revise"


def test_review_status_values():
    assert ReviewStatus.PROVISIONAL == "provisional"
    assert ReviewStatus.APPROVED == "approved"


def test_evidence_span_valid():
    sp = EvidenceSpan(id="s1", document_id="d1", char_start=0, char_end=5,
                      excerpt="hello", excerpt_hash=checksum("hello"))
    assert sp.id == "s1"
    assert sp.char_start == 0
    assert sp.char_end == 5


def test_evidence_span_empty_excerpt_rejected():
    with pytest.raises(ValidationError, match="empty excerpt"):
        EvidenceSpan(id="s1", document_id="d1", char_start=0, char_end=3,
                     excerpt="   ", excerpt_hash="x")


def test_evidence_span_invalid_offsets_rejected():
    with pytest.raises(ValidationError, match="invalid char offsets"):
        EvidenceSpan(id="s1", document_id="d1", char_start=5, char_end=3,
                     excerpt="hello", excerpt_hash="x")


def test_evidence_span_zero_width_rejected():
    with pytest.raises(ValidationError, match="invalid char offsets"):
        EvidenceSpan(id="s1", document_id="d1", char_start=3, char_end=3,
                     excerpt="hello", excerpt_hash="x")


def test_evidence_span_negative_start_rejected():
    with pytest.raises(ValidationError, match="invalid char offsets"):
        EvidenceSpan(id="s1", document_id="d1", char_start=-1, char_end=5,
                     excerpt="hello", excerpt_hash="x")


def test_project_defaults():
    p = Project(id="p1")
    assert p.policy_version == "1.0"
    assert p.owner_id == "local-user"


def test_observation_model():
    o = Observation(id="o1", label="test", evidence_span_ids=["s1", "s2"])
    assert len(o.evidence_span_ids) == 2


def test_hypothesis_defaults():
    h = Hypothesis(id="h1", concept_ids=["c1"], support_ids=["o1"],
                   alternatives=["alt1"])
    assert h.counterexamples == []
    assert h.status == ReviewStatus.PROVISIONAL
    assert h.theory_reference_ids == []


def test_analysis_packet_state_coercion():
    pkt = AnalysisPacket(run_id="r1", participant_id="A",
                         state=RunState.NEEDS_HUMAN_REVIEW)
    assert pkt.state == "NEEDS_HUMAN_REVIEW"
    assert pkt.observations == []
    assert pkt.hypotheses == []
    assert pkt.errors == []


def test_analysis_run_defaults():
    r = AnalysisRun(id="r1", project_id="p", participant_id="A",
                    source_ids=["d1"], state=RunState.CREATED, idempotency_key="k")
    assert r.packet is None
    assert r.audit == []


def test_error_response_model():
    err = ErrorResponse(error=ErrorBody(code="NOT_FOUND", message="missing", request_id="req1"))
    assert err.error.code == "NOT_FOUND"
