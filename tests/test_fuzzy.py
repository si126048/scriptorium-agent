from __future__ import annotations

import pytest

from scriptorium.fuzzy import (
    FuzzyGrounding, MembershipFunction, aggregate_grounding,
    HallucinationGuard, HallucinationReport,
    t_norm, t_conorm, fuzzy_complement, alpha_cut,
)
from scriptorium.models import Hypothesis, EvidenceSpan, Observation


def _span(sid: str, text: str) -> EvidenceSpan:
    return EvidenceSpan(id=sid, document_id="d1", char_start=0, char_end=len(text),
                        excerpt=text, excerpt_hash="h" + sid)


def _hyp(hid: str, concepts: list[str], support: list[str],
         counterexamples: list[str] | None = None) -> Hypothesis:
    return Hypothesis(id=hid, concept_ids=concepts, support_ids=support,
                      alternatives=[], counterexamples=counterexamples or [])


def _obs(oid: str, label: str, span_ids: list[str]) -> Observation:
    return Observation(id=oid, label=label, evidence_span_ids=span_ids)


class TestFuzzyOperations:
    def test_t_norm(self):
        assert t_norm(0.3, 0.7) == 0.3
        assert t_norm(0.0, 1.0) == 0.0
        assert t_norm(1.0, 1.0) == 1.0

    def test_t_conorm(self):
        assert t_conorm(0.3, 0.7) == pytest.approx(0.79)
        assert t_conorm(0.0, 0.0) == 0.0
        assert t_conorm(1.0, 0.5) == 1.0

    def test_complement(self):
        assert fuzzy_complement(0.3) == pytest.approx(0.7)
        assert fuzzy_complement(0.0) == 1.0
        assert fuzzy_complement(1.0) == 0.0

    def test_alpha_cut(self):
        gs = [
            FuzzyGrounding("h1", "s1", 0.8),
            FuzzyGrounding("h1", "s2", 0.3),
            FuzzyGrounding("h1", "s3", 0.6),
        ]
        result = alpha_cut(gs, 0.5)
        assert len(result) == 2
        assert all(g.membership >= 0.5 for g in result)


class TestFuzzyGrounding:
    def test_valid_membership(self):
        g = FuzzyGrounding("h1", "s1", 0.5, {"lexical": 0.6})
        assert g.membership == 0.5

    def test_invalid_membership(self):
        with pytest.raises(ValueError, match="membership"):
            FuzzyGrounding("h1", "s1", 1.5)


class TestMembershipFunction:
    def test_lexical_overlap(self):
        mf = MembershipFunction()
        hyp = _hyp("h1", ["mirror stage"], ["s1"])
        span = _span("s1", "the mirror stage is a core lacanian concept")
        obs = [_obs("o1", "mirror stage", ["s1"])]
        g = mf.compute(hyp, span, obs)
        assert g.components["lexical"] > 0

    def test_no_overlap(self):
        mf = MembershipFunction()
        hyp = _hyp("h1", ["量子力学"], ["s1"])
        span = _span("s1", "今天天气很好")
        obs = [_obs("o1", "天气", ["s2"])]
        g = mf.compute(hyp, span, obs)
        assert g.membership < 0.3

    def test_proximity_boost(self):
        mf = MembershipFunction()
        hyp = _hyp("h1", ["大他者"], ["s1"])
        span = _span("s1", "大他者的凝视")
        obs = [_obs("o1", "大他者", ["s1"])]
        g = mf.compute(hyp, span, obs)
        assert g.components["proximity"] == 1.0

    def test_membership_range(self):
        mf = MembershipFunction()
        hyp = _hyp("h1", ["test"], ["s1"])
        span = _span("s1", "test data")
        obs = []
        g = mf.compute(hyp, span, obs)
        assert 0.0 <= g.membership <= 1.0

    def test_minimal_overlap(self):
        mf = MembershipFunction()
        hyp = _hyp("h1", ["quantum physics"], ["s1"])
        span = _span("s1", "just some unrelated text here")
        obs = []
        g = mf.compute(hyp, span, obs)
        assert g.membership < 0.2


class TestAggregateGrounding:
    def test_single_grounding(self):
        gs = [FuzzyGrounding("h1", "s1", 0.8)]
        assert aggregate_grounding(gs, []) == pytest.approx(0.8)

    def test_multiple_groundings_union(self):
        gs = [
            FuzzyGrounding("h1", "s1", 0.6),
            FuzzyGrounding("h1", "s2", 0.7),
        ]
        result = aggregate_grounding(gs, [])
        expected = 0.6 + 0.7 - 0.6 * 0.7
        assert result == pytest.approx(round(expected, 4))

    def test_with_counterexample(self):
        gs = [FuzzyGrounding("h1", "s1", 0.8)]
        cs = [FuzzyGrounding("h1", "s2", 0.5)]
        result = aggregate_grounding(gs, cs)
        assert result < 0.8
        assert result == pytest.approx(round(0.8 * (1 - 0.5), 4))

    def test_empty_groundings(self):
        assert aggregate_grounding([], []) == 0.0

    def test_strong_counterexample_reduces_to_near_zero(self):
        gs = [FuzzyGrounding("h1", "s1", 0.5)]
        cs = [FuzzyGrounding("h1", "s2", 0.95)]
        result = aggregate_grounding(gs, cs)
        assert result < 0.1


class TestHallucinationGuard:
    def test_low_risk(self):
        guard = HallucinationGuard()
        hyp = _hyp("h1", ["concept1"], ["s1"])
        hyp.grounding_score = 0.8
        gs = [FuzzyGrounding("h1", "s1", 0.8)]
        report = guard.check(hyp, gs)
        assert report.risk_level == "low"
        assert report.recommendation == "accept"

    def test_medium_risk(self):
        guard = HallucinationGuard()
        hyp = _hyp("h1", ["concept1"], ["s1"])
        hyp.grounding_score = 0.4
        gs = [FuzzyGrounding("h1", "s1", 0.4)]
        report = guard.check(hyp, gs)
        assert report.risk_level == "medium"
        assert report.recommendation == "revise"

    def test_high_risk(self):
        guard = HallucinationGuard()
        hyp = _hyp("h1", ["concept1"], ["s1"])
        hyp.grounding_score = 0.1
        gs = [FuzzyGrounding("h1", "s1", 0.1)]
        report = guard.check(hyp, gs)
        assert report.risk_level == "high"
        assert report.recommendation == "reject"

    def test_ungrounded_claims(self):
        guard = HallucinationGuard()
        hyp = _hyp("h1", ["grounded_concept", "ungrounded_concept"], ["s1"])
        hyp.grounding_score = 0.2
        gs = [FuzzyGrounding("h1", "s1", 0.1)]
        report = guard.check(hyp, gs)
        assert len(report.ungrounded_claims) > 0

    def test_report_to_dict(self):
        report = HallucinationReport(
            hypothesis_id="h1", grounding_score=0.5,
            risk_level="medium", ungrounded_claims=["x"], recommendation="revise"
        )
        d = report.to_dict()
        assert d["hypothesis_id"] == "h1"
        assert d["risk_level"] == "medium"
