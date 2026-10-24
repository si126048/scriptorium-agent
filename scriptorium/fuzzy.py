from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EvidenceSpan, Hypothesis, Observation


@dataclass
class FuzzyGrounding:
    hypothesis_id: str
    evidence_span_id: str
    membership: float
    components: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.membership <= 1.0):
            raise ValueError(f"membership must be in [0, 1], got {self.membership}")


def t_norm(a: float, b: float) -> float:
    return min(a, b)


def t_conorm(a: float, b: float) -> float:
    return a + b - a * b


def fuzzy_complement(a: float) -> float:
    return 1.0 - a


def alpha_cut(values: list[FuzzyGrounding], alpha: float) -> list[FuzzyGrounding]:
    return [v for v in values if v.membership >= alpha]


class MembershipFunction:
    WEIGHTS = {
        "lexical": 0.5,
        "proximity": 0.3,
        "temporal": 0.2,
    }

    def compute(self, hypothesis: Hypothesis, span: EvidenceSpan,
                observations: list[Observation]) -> FuzzyGrounding:
        lex = self._lexical_overlap(hypothesis, span)
        prox = self._structural_proximity(hypothesis, span, observations)
        temp = self._temporal_coherence(hypothesis, span, observations)

        components = {"lexical": lex, "proximity": prox, "temporal": temp}
        membership = (
            self.WEIGHTS["lexical"] * lex
            + self.WEIGHTS["proximity"] * prox
            + self.WEIGHTS["temporal"] * temp
        )
        return FuzzyGrounding(
            hypothesis_id=hypothesis.id,
            evidence_span_id=span.id,
            membership=round(membership, 4),
            components={k: round(v, 4) for k, v in components.items()},
        )

    def _lexical_overlap(self, hypothesis: Hypothesis, span: EvidenceSpan) -> float:
        span_tokens = set(self._tokenize(span.excerpt))
        if not span_tokens:
            return 0.0
        concept_tokens = set()
        for cid in hypothesis.concept_ids:
            concept_tokens.update(self._tokenize(cid))
        if not concept_tokens:
            return 0.1
        overlap = len(span_tokens & concept_tokens)
        return min(overlap / max(len(concept_tokens), 1), 1.0)

    def _structural_proximity(self, hypothesis: Hypothesis, span: EvidenceSpan,
                              observations: list[Observation]) -> float:
        for obs in observations:
            if span.id in obs.evidence_span_ids:
                if any(cid in obs.label for cid in hypothesis.concept_ids):
                    return 1.0
                return 0.6
        return 0.1

    def _temporal_coherence(self, hypothesis: Hypothesis, span: EvidenceSpan,
                            observations: list[Observation]) -> float:
        related_span_ids = set()
        for obs in observations:
            if any(cid in obs.label for cid in hypothesis.concept_ids):
                related_span_ids.update(obs.evidence_span_ids)
        if span.id in related_span_ids:
            return 0.9
        if related_span_ids:
            return 0.3
        return 0.1

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r'[\w\u4e00-\u9fff]+', text.lower())


def aggregate_grounding(groundings: list[FuzzyGrounding],
                        counterexamples: list[FuzzyGrounding]) -> float:
    if not groundings:
        return 0.0
    union_score = 0.0
    for g in groundings:
        union_score = t_conorm(union_score, g.membership)
    union_score = min(union_score, 1.0)
    if not counterexamples:
        return round(union_score, 4)
    max_disconfirm = max(c.membership for c in counterexamples)
    final = union_score * fuzzy_complement(max_disconfirm)
    return round(final, 4)


@dataclass
class HallucinationReport:
    hypothesis_id: str
    grounding_score: float
    risk_level: str
    ungrounded_claims: list[str]
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "grounding_score": self.grounding_score,
            "risk_level": self.risk_level,
            "ungrounded_claims": self.ungrounded_claims,
            "recommendation": self.recommendation,
        }


class HallucinationGuard:
    def __init__(self, low_threshold: float = 0.3, high_threshold: float = 0.5):
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold

    def check(self, hypothesis: Hypothesis,
              groundings: list[FuzzyGrounding]) -> HallucinationReport:
        score = hypothesis.grounding_score
        if score >= self.high_threshold:
            return HallucinationReport(
                hypothesis_id=hypothesis.id,
                grounding_score=score,
                risk_level="low",
                ungrounded_claims=[],
                recommendation="accept",
            )
        if score >= self.low_threshold:
            ungrounded = self._find_ungrounded(hypothesis, groundings)
            return HallucinationReport(
                hypothesis_id=hypothesis.id,
                grounding_score=score,
                risk_level="medium",
                ungrounded_claims=ungrounded,
                recommendation="revise",
            )
        ungrounded = self._find_ungrounded(hypothesis, groundings)
        return HallucinationReport(
            hypothesis_id=hypothesis.id,
            grounding_score=score,
            risk_level="high",
            ungrounded_claims=ungrounded,
            recommendation="reject",
        )

    def _find_ungrounded(self, hypothesis: Hypothesis,
                         groundings: list[FuzzyGrounding]) -> list[str]:
        grounded_concepts = set()
        for g in groundings:
            if g.membership >= self.low_threshold:
                grounded_concepts.update(hypothesis.concept_ids)
        ungrounded = [cid for cid in hypothesis.concept_ids if cid not in grounded_concepts]
        return ungrounded
