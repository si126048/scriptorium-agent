import uuid
from pathlib import Path
from scriptorium.db import Store
from scriptorium.models import (
    ConsentScope, Participant, Project, ReviewDecision, ReviewRequest,
    RunState, ReviewStatus,
)
from scriptorium.rag import ingest
from scriptorium.workflow import Workflow


def _setup(tmp_path):
    db = str(tmp_path / f"test-{uuid.uuid4().hex}.sqlite")
    s = Store(db)
    s.create_project(Project(id="p"))
    s.put_participant(Participant(id="A", project_id="p", pseudonym="A",
                                  consent_scope=ConsentScope()))
    theory = tmp_path / "theory.md"
    theory.write_text("Repetition changes meaning across contexts.", encoding="utf-8")
    story = tmp_path / "story.txt"
    story.write_text("A door appears. A door appears again.", encoding="utf-8")
    ingest(s, str(theory), "p")
    d = ingest(s, str(story), "p", "A", ConsentScope())
    return s, d


def test_end_to_end_pipeline(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    assert r.state == RunState.NEEDS_HUMAN_REVIEW
    assert r.packet is not None
    assert len(r.packet.observations) >= 1
    assert len(r.packet.hypotheses) >= 1


def test_counterexample_assignment_per_hypothesis(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    for h in r.packet.hypotheses:
        assert len(h.counterexamples) >= 1
        assert any(h.id in ce for ce in h.counterexamples)




def test_idempotency(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r1 = f.run("p", "A", [d.id], "same-key")
    r2 = f.run("p", "A", [d.id], "same-key")
    assert r1.id == r2.id


def test_export_not_approved(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    try:
        f.export(r.id)
        assert False
    except PermissionError as e:
        assert str(e) == "NOT_APPROVED"


def test_review_approve_and_export(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.APPROVE))
    r2 = s.get_run(r.id)
    assert r2.state == RunState.APPROVED
    for h in r2.packet.hypotheses:
        assert h.status == ReviewStatus.APPROVED
    out = f.export(r.id)
    assert out["graph"]["edges"]
    assert out["packet"]["narrative_operators"]
    assert out["packet"]["narrative_operators"][0]["allowed"] is True


def test_review_reject(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.REJECT, reason="bad"))
    r2 = s.get_run(r.id)
    assert r2.state == RunState.FAILED
    assert "bad" in r2.packet.errors


def test_review_revise(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.REVISE, reason="needs work"))
    r2 = s.get_run(r.id)
    assert r2.state == RunState.REVISION_REQUIRED


def test_review_invalid_state(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.APPROVE))
    with pytest.raises(ValueError, match="INVALID_REVIEW_STATE"):
        f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.APPROVE))


def test_object_access_denied(tmp_path):
    s, d = _setup(tmp_path)
    s.put_participant(Participant(id="C", project_id="p", pseudonym="C",
                                  consent_scope=ConsentScope()))
    f = Workflow(s)
    try:
        f.run("p", "C", [d.id], "k")
        assert False
    except PermissionError as e:
        assert str(e) == "OBJECT_ACCESS_DENIED"


def test_audit_trail(tmp_path):
    s, d = _setup(tmp_path)
    f = Workflow(s)
    r = f.run("p", "A", [d.id], "k1")
    assert len(r.audit) >= 4
    states = [a["state"] for a in r.audit]
    assert RunState.INGESTED in states
    assert RunState.OBSERVED in states
    assert RunState.INTERPRETED in states
    assert RunState.CRITIQUED in states


import pytest
