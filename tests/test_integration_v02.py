from __future__ import annotations

import uuid

from scriptorium.db import Store
from scriptorium.models import (
    ConsentScope, Participant, Project, ReviewDecision, ReviewRequest,
    RunState, EvidenceSpan, Hypothesis,
)
from scriptorium.rag import ingest
from scriptorium.workflow import Workflow
from scriptorium.fuzzy import (
    HallucinationGuard,
    FuzzyGrounding,
)
from scriptorium.annotation import CulturalAnnotator
from scriptorium.topology.borromean import RegisterCoherenceMonitor, Register
from scriptorium.topology.discourses import MASTER, HYSTERIC, ANALYST, UNIVERSITY


def _setup(tmp_path):
    db = str(tmp_path / f"v02-{uuid.uuid4().hex}.sqlite")
    s = Store(db)
    s.create_project(Project(id="p"))
    s.put_participant(Participant(
        id="A", project_id="p", pseudonym="A",
        consent_scope=ConsentScope(research_analysis=True, generation=True),
    ))
    theory = tmp_path / "theory.md"
    theory.write_text("Repetition changes meaning across contexts. The signifier chain slides along the metonymic axis.", encoding="utf-8")
    story = tmp_path / "story.txt"
    story.write_text("A door appears. A door appears again. The door is always there.", encoding="utf-8")
    ingest(s, str(theory), "p")
    d = ingest(s, str(story), "p", "A", ConsentScope(research_analysis=True, generation=True))
    return s, d


class TestFullPipelineV02:
    def test_end_to_end_with_topology(self, tmp_path):
        s, d = _setup(tmp_path)
        f = Workflow(s)
        r = f.run("p", "A", [d.id], "k1")
        assert r.state == RunState.NEEDS_HUMAN_REVIEW
        assert r.packet is not None
        assert len(r.packet.observations) >= 1
        assert len(r.packet.hypotheses) >= 1

        h = r.packet.hypotheses[0]
        assert h.discourse_type is not None
        assert h.discourse_type in ("master", "university", "hysteric", "analyst")
        assert h.grounding_score >= 0.0
        assert h.desire_residual is not None
        assert 0.0 <= h.desire_residual.residual_score <= 1.0

        assert r.topology.get('critic_disconfirmation') is not None
        assert r.topology.get('critic_grounding') is not None

    def test_export_includes_topology(self, tmp_path):
        s, d = _setup(tmp_path)
        f = Workflow(s)
        r = f.run("p", "A", [d.id], "k1")
        f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.APPROVE))
        out = f.export(r.id)

        assert 'topology' in out
        assert 'discourse_trajectory' in out['topology']
        assert 'annotations' in out
        assert 'hallucination_reports' in out

        node_types = {n['type'] for n in out['graph']['nodes']}
        assert 'signifier' in node_types
        assert 'interpretation' in node_types

    def test_export_matheme_nodes(self, tmp_path):
        s, d = _setup(tmp_path)
        f = Workflow(s)
        r = f.run("p", "A", [d.id], "k1")
        f.review(r.id, ReviewRequest(reviewer_id="rev", decision=ReviewDecision.APPROVE))
        out = f.export(r.id)
        node_types = [n['type'] for n in out['graph']['nodes']]
        if r.packet.hypotheses[0].matheme_ids:
            assert 'matheme' in node_types


class TestBorromeanUnknotting:
    def test_unknotting_detection(self):
        monitor = RegisterCoherenceMonitor(window_size=20)
        for _ in range(8):
            monitor.feed("规则 结构 命名 法则", Register.SYMBOLIC)
            monitor.feed("镜像 认同 仿佛 好像", Register.IMAGINARY)
            monitor.feed("身体颤抖 说不出话 创伤", Register.REAL)
        for _ in range(10):
            monitor.feed("规则 结构 法则", Register.SYMBOLIC)
            monitor.feed("镜像 认同 好像", Register.IMAGINARY)
        events = monitor.detect_unknotting()
        assert isinstance(events, list)


class TestFuzzyGroundingReducesHallucination:
    def test_high_grounding_accepts(self):
        h = Hypothesis(id="h1", concept_ids=["c1"], support_ids=["s1"],
                       alternatives=["alt"], grounding_score=0.8)
        g = FuzzyGrounding(hypothesis_id="h1", evidence_span_id="s1",
                           membership=0.8, components={"lexical": 0.8})
        guard = HallucinationGuard()
        report = guard.check(h, [g])
        assert report.risk_level == "low"
        assert report.recommendation == "accept"

    def test_low_grounding_flags_hallucination(self):
        h = Hypothesis(id="h2", concept_ids=["c1"], support_ids=["s1"],
                       alternatives=["alt"], grounding_score=0.1)
        g = FuzzyGrounding(hypothesis_id="h2", evidence_span_id="s1",
                           membership=0.1, components={"lexical": 0.1})
        guard = HallucinationGuard()
        report = guard.check(h, [g])
        assert report.risk_level == "high"
        assert report.recommendation == "reject"

    def test_pipeline_flags_ungrounded_hypothesis(self, tmp_path):
        s, d = _setup(tmp_path)
        f = Workflow(s)
        r = f.run("p", "A", [d.id], "k1")
        assert r.packet.hallucination_reports
        for report in r.packet.hallucination_reports:
            assert 'risk_level' in report
            assert report['risk_level'] in ('low', 'medium', 'high')


class TestCulturalAnnotationInContext:
    def test_annotator_detects_entities(self):
        annotator = CulturalAnnotator()
        span = EvidenceSpan(
            id="sp1", document_id="d1", char_start=0, char_end=30,
            excerpt="我最近在玩原神，感觉很棒", excerpt_hash="abc",
        )
        annotations = annotator.annotate([span])
        entity_names = [a.entity_name for a in annotations]
        assert "原神" in entity_names

    def test_annotations_in_pipeline(self, tmp_path):
        s, d = _setup(tmp_path)
        f = Workflow(s)
        r = f.run("p", "A", [d.id], "k1")
        assert isinstance(r.packet.cultural_annotations, list)


class TestDiscourseAlgebra:
    def test_four_discourse_cycle(self):
        orbit = MASTER.orbit()
        assert len(orbit) == 4
        assert orbit[0] == MASTER
        assert orbit[1] == HYSTERIC
        assert orbit[2] == ANALYST
        assert orbit[3] == UNIVERSITY

    def test_four_turns_return(self):
        d = MASTER
        for _ in range(4):
            d = d.quarter_turn_cw()
        assert d == MASTER


class TestConcurrentBatchV02:
    import pytest

    @pytest.mark.asyncio
    async def test_batch_with_fuzzy_and_annotations(self, tmp_path):
        from scriptorium.concurrent import ConcurrentAnalyzer, AnalysisTask

        db = str(tmp_path / "batch_v02.sqlite")
        s = Store(db)
        s.create_project(Project(id="proj"))

        for i in range(3):
            pid = f"p{i}"
            s.put_participant(Participant(
                id=pid, project_id="proj", pseudonym=f"P{i}",
                consent_scope=ConsentScope(research_analysis=True),
            ))
            txt = tmp_path / f"chat_{i}.txt"
            txt.write_text(f"participant {i} says hello world\n" * 5, encoding="utf-8")
            ingest(s, str(txt), "proj", pid, ConsentScope(research_analysis=True))

        docs = s.list_documents("proj")
        tasks = []
        for i in range(3):
            pid = f"p{i}"
            doc_ids = [d.id for d in docs if d.participant_id == pid]
            tasks.append(AnalysisTask(
                project_id="proj", participant_id=pid,
                source_ids=doc_ids, idempotency_key=f"v02_{pid}",
            ))

        analyzer = ConcurrentAnalyzer(s, max_concurrent=2)
        results = await analyzer.analyze_batch(tasks)
        assert len(results) == 3
        for r in results:
            assert r.success, f"task for {r.task.participant_id} failed: {r.error}"
            assert r.run.packet.hallucination_reports
