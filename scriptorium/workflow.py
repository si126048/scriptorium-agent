from __future__ import annotations

import logging

from .annotation import CulturalAnnotator
from .db import Store, new_id
from .formal.prompts import FORMAL_CRITIC_SYSTEM, FORMAL_EVIDENCE_SYSTEM, FORMAL_INTERPRETER_SYSTEM
from .fuzzy import HallucinationGuard, MembershipFunction, aggregate_grounding
from .llm import FakeProvider
from .models import (
    AnalysisPacket,
    AnalysisRun,
    Counterexample,
    EvidenceSpan,
    GraphEdge,
    GraphNode,
    Hypothesis,
    NarrativeOperator,
    Observation,
    ReviewDecision,
    ReviewRequest,
    ReviewStatus,
    RunState,
)
from .rag import validate_span

logger = logging.getLogger(__name__)


def _coerce_str_list(values: list) -> list[str]:
    return [str(v) for v in values]


def _sanitize_observation(d: dict) -> dict:
    d = dict(d)
    if 'evidence_span_ids' not in d or not d['evidence_span_ids']:
        d['evidence_span_ids'] = []
    else:
        d['evidence_span_ids'] = _coerce_str_list(d['evidence_span_ids'])
    return d


def _sanitize_hypothesis(d: dict) -> dict:
    d = dict(d)
    for key in ('support_ids', 'concept_ids', 'theory_reference_ids', 'matheme_ids'):
        if key in d:
            d[key] = _coerce_str_list(d[key])
    if 'points_de_capiton' in d:
        d['points_de_capiton'] = [
            {**pc, 'fixation_span_ids': _coerce_str_list(pc.get('fixation_span_ids', []))}
            for pc in d['points_de_capiton']
        ]
    return d


class Workflow:
    def __init__(self, store: Store, provider=None):
        self.store = store
        self.provider = provider or FakeProvider()

    def _set(self, r: AnalysisRun, state: RunState, reason: str, actor: str = 'system') -> None:
        r.state = state
        self.store.audit(r, actor, reason)
        logger.info("run=%s state=%s reason=%s", r.id, state, reason)

    def run(self, project_id: str, participant_id: str, source_ids: list[str], idem: str) -> AnalysisRun:
        existing = self.store.get_run_by_idem(project_id, idem)
        if existing and sorted(existing.source_ids) != sorted(source_ids):
            raise ValueError('IDEMPOTENCY_SOURCE_MISMATCH')
        if existing:
            return existing

        p = self.store.get_participant(project_id, participant_id)
        if not p or p.withdrawn_at or not p.consent_scope.is_active():
            raise PermissionError('PARTICIPANT_WITHDRAWN')

        docs = [self.store.get_document(x) for x in source_ids]
        if any(not d or d.participant_id != participant_id or d.project_id != project_id for d in docs):
            raise PermissionError('OBJECT_ACCESS_DENIED')

        r = AnalysisRun(
            id=new_id('run'), project_id=project_id, participant_id=participant_id,
            source_ids=source_ids, state=RunState.CREATED, idempotency_key=idem,
        )
        created = self.store.create_run_atomic(r)
        if created.id != r.id:
            return created
        self._set(r, RunState.INGESTED, 'audit complete')

        spans = self._collect_evidence(docs)
        obs = self._observe(r, spans)
        self._validate_observations(obs, {s.id for s in spans})
        annotations = self._annotate(spans)
        hyps = self._interpret(r, obs, project_id, annotations)
        self._validate_hypotheses(hyps, obs, project_id)
        hyps = self._critique(r, obs, hyps)
        return self._finalize(r, participant_id, obs, hyps, spans, annotations)

    @staticmethod
    def _validate_observations(observations: list[Observation], span_ids: set[str]) -> None:
        for observation in observations:
            valid_spans = set(observation.evidence_span_ids) & span_ids
            if valid_spans != set(observation.evidence_span_ids):
                observation.evidence_span_ids = list(valid_spans)

    def _validate_hypotheses(self, hypotheses: list[Hypothesis], observations: list[Observation], project_id: str) -> None:
        observation_ids = {o.id for o in observations}
        theory_ids = {s.id for s in self.store.list_theory_spans(project_id)}
        valid_discourses = {'master', 'university', 'hysteric', 'analyst', None}
        for hypothesis in hypotheses:
            valid_supports = set(hypothesis.support_ids) & observation_ids
            if valid_supports != set(hypothesis.support_ids):
                hypothesis.support_ids = list(valid_supports)
                hypothesis.status = ReviewStatus.NEEDS_REVISION
            valid_theory = set(hypothesis.theory_reference_ids) & theory_ids
            if valid_theory != set(hypothesis.theory_reference_ids):
                hypothesis.theory_reference_ids = list(valid_theory)
            if hypothesis.discourse_type not in valid_discourses:
                hypothesis.discourse_type = None
            if not hypothesis.support_ids:
                hypothesis.status = ReviewStatus.NEEDS_REVISION

    def _collect_evidence(self, docs: list, max_spans: int = 200, max_chars: int = 50000) -> list[EvidenceSpan]:
        spans: list[EvidenceSpan] = []
        total_chars = 0
        for d in docs:
            doc_spans = self.store.list_spans_for_document(d.id)
            for s in doc_spans:
                if len(spans) >= max_spans or total_chars >= max_chars:
                    break
                if validate_span(self.store, s.id):
                    spans.append(s)
                    total_chars += len(s.excerpt)
            if len(spans) >= max_spans or total_chars >= max_chars:
                break
        logger.info("evidence: collected %d valid spans (%d chars)", len(spans), total_chars)
        return spans

    def _observe(self, r: AnalysisRun, spans: list[EvidenceSpan]) -> list[Observation]:
        sample = spans[:50]
        spans_text = '\n\n'.join(f'[span_id={s.id}]\n{s.excerpt}' for s in sample)
        ev = self.provider.generate_structured(
            FORMAL_EVIDENCE_SYSTEM,
            {'span_ids': [s.id for s in spans], 'spans_text': spans_text},
            Observation, {'stage': 'evidence'},
        )
        obs = [Observation.model_validate(_sanitize_observation(x)) for x in ev['observations']]
        self._set(r, RunState.OBSERVED, 'evidence spans validated')
        logger.info("observations: %d", len(obs))
        return obs

    def _annotate(self, spans: list[EvidenceSpan]) -> list:
        try:
            annotator = CulturalAnnotator()
            return annotator.annotate(spans)
        except Exception:
            logger.warning("cultural annotation failed, continuing without annotations")
            return []

    def _interpret(self, r: AnalysisRun, obs: list[Observation], project_id: str,
                   annotations: list | None = None) -> list[Hypothesis]:
        theory_spans = self.store.list_theory_spans(project_id)
        theory_refs = [s.id for s in theory_spans]
        theory_text = '\n'.join(s.excerpt for s in theory_spans)
        annotation_context = ""
        if annotations:
            annotation_context = "\n".join(
                f"[{a.entity_name}] ({a.entity_type}): {a.context_brief}"
                for a in annotations
            )
        hyp = self.provider.generate_structured(
            FORMAL_INTERPRETER_SYSTEM,
            {
                'observation_ids': [o.id for o in obs],
                'theory_reference_ids': theory_refs,
                'observation_labels': [o.label for o in obs],
                'theory_text': theory_text,
                'cultural_annotations': annotation_context,
            },
            Hypothesis, {'stage': 'interpreter'},
        )
        hyps = [Hypothesis.model_validate(_sanitize_hypothesis(x)) for x in hyp['hypotheses']]
        self._set(r, RunState.INTERPRETED, 'structured hypotheses generated')
        logger.info("hypotheses: %d", len(hyps))
        return hyps

    def _critique(self, r: AnalysisRun, obs: list[Observation], hyps: list[Hypothesis]) -> list[Hypothesis]:
        hyps_summary = [{'id': h.id, 'concept_ids': h.concept_ids, 'alternatives': h.alternatives} for h in hyps]
        crit = self.provider.generate_structured(
            FORMAL_CRITIC_SYSTEM,
            {
                'observation_ids': [o.id for o in obs],
                'observation_labels': [o.label for o in obs],
                'hypotheses_summary': hyps_summary,
                'hypothesis_ids': [h.id for h in hyps],
            },
            dict, {'stage': 'critic'},
        )
        crit_by_hyp = crit.get('counterexamples_by_hypothesis', {})
        for h in hyps:
            for index, item in enumerate(crit_by_hyp.get(h.id, crit.get('counterexamples', []))):
                if isinstance(item, dict):
                    payload = dict(item)
                    payload.setdefault('id', f'ce_{h.id}_{index + 1}')
                    h.counterexamples.append(Counterexample.model_validate(payload))
                else:
                    h.counterexamples.append(Counterexample(
                        id=f'ce_{h.id}_{index + 1}', text=str(item), source='llm'))
        r.topology['critic_disconfirmation'] = crit.get('fuzzy_disconfirmation_by_hypothesis', {})
        r.topology['critic_grounding'] = crit.get('grounding_assessment_by_hypothesis', {})
        r.topology['critic_ungrounded'] = crit.get('ungrounded_claims_by_hypothesis', {})
        self._set(r, RunState.CRITIQUED, 'independent counterexample pass complete')
        return hyps

    def _finalize(self, r: AnalysisRun, participant_id: str, obs: list[Observation],
                  hyps: list[Hypothesis], spans: list[EvidenceSpan],
                  annotations: list | None = None) -> AnalysisRun:
        mf = MembershipFunction()
        guard = HallucinationGuard()
        hallucination_reports = []
        obs_by_id = {o.id: o for o in obs}
        span_by_id = {s.id: s for s in spans}

        for h in hyps:
            supported_span_ids: list[str] = []
            for sid in h.support_ids:
                if sid in span_by_id:
                    supported_span_ids.append(sid)
                elif sid in obs_by_id:
                    supported_span_ids.extend(
                        eid for eid in obs_by_id[sid].evidence_span_ids if eid in span_by_id
                    )
            groundings = [mf.compute(h, span_by_id[sid], obs) for sid in supported_span_ids]
            counter_span_ids = {
                span_id for counterexample in h.counterexamples
                for span_id in counterexample.evidence_span_ids if span_id in span_by_id
            }
            counter_groundings = [mf.compute(h, span_by_id[sid], obs) for sid in counter_span_ids]
            h.grounding_score = aggregate_grounding(groundings, counter_groundings)
            h.fuzzy_groundings = [
                {"span_id": g.evidence_span_id, "membership": g.membership, "components": g.components}
                for g in groundings
            ]
            report = guard.check(h, groundings)
            hallucination_reports.append(report.to_dict())
            if report.risk_level == "high":
                h.status = ReviewStatus.NEEDS_REVISION
                logger.warning("hypothesis %s flagged high hallucination risk (score=%.3f)", h.id, h.grounding_score)

        packet = AnalysisPacket(
            run_id=r.id, participant_id=participant_id,
            state=RunState.NEEDS_HUMAN_REVIEW, observations=obs, hypotheses=hyps,
            hallucination_reports=hallucination_reports,
            cultural_annotations=annotations or [],
        )
        r.packet = packet
        r.topology['computed'] = {
            'evidence_span_count': len(spans),
            'observation_count': len(obs),
            'hypothesis_count': len(hyps),
            'grounded_hypothesis_ids': [h.id for h in hyps if h.grounding_score > 0],
        }
        r.topology['model_proposed'] = {
            'discourse_types': {h.id: h.discourse_type for h in hyps},
            'matheme_ids': {h.id: h.matheme_ids for h in hyps},
        }
        self._set(r, RunState.NEEDS_HUMAN_REVIEW, 'awaiting human review')
        return r

    def review(self, rid: str, req: ReviewRequest) -> AnalysisRun:
        r = self.store.get_run(rid)
        if not r:
            raise KeyError('RUN_NOT_FOUND')
        if r.state != RunState.NEEDS_HUMAN_REVIEW:
            raise ValueError('INVALID_REVIEW_STATE')
        if req.decision == ReviewDecision.APPROVE:
            r.state = RunState.APPROVED
            r.packet.state = RunState.APPROVED
            for h in r.packet.hypotheses:
                h.status = ReviewStatus.APPROVED
        elif req.decision == ReviewDecision.REVISE:
            r.state = RunState.REVISION_REQUIRED
            r.packet.state = RunState.REVISION_REQUIRED
        else:
            r.state = RunState.FAILED
            r.packet.state = RunState.FAILED
            r.packet.errors.append(req.reason or 'rejected')
        self.store.audit(r, req.reviewer_id, req.reason or req.decision.value)
        logger.info("review: run=%s decision=%s", rid, req.decision.value)
        return r

    def export(self, rid: str) -> dict:
        r = self.store.get_run(rid)
        if not r:
            raise KeyError('RUN_NOT_FOUND')
        if r.state not in (RunState.APPROVED, RunState.COMPILED):
            raise PermissionError('NOT_APPROVED')
        p = self.store.get_participant(r.project_id, r.participant_id)
        if not p or p.withdrawn_at or p.consent_scope.withdrawn_at:
            raise PermissionError('PARTICIPANT_WITHDRAWN')
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        ops: list[NarrativeOperator] = []
        obs_by_id = {o.id: o for o in r.packet.observations}
        for o in r.packet.observations:
            nodes.append(GraphNode(id=o.id, type='signifier', label=o.label, source_ids=o.evidence_span_ids, status='approved'))
        discourse_trajectory = []
        for h in r.packet.hypotheses:
            nodes.append(GraphNode(id=h.id, type='interpretation', label=h.id, source_ids=h.support_ids, status='approved'))
            if h.discourse_type:
                discourse_trajectory.append(h.discourse_type)
            for mid in h.matheme_ids:
                nodes.append(GraphNode(id=mid, type='matheme', label=mid, status='approved'))
                edges.append(GraphEdge(id=new_id('edge'), source=mid, target=h.id, type='matheme', evidence_span_ids=[]))
            for pc in h.points_de_capiton:
                nodes.append(GraphNode(id=pc.id, type='capiton_point', label=pc.signifier, source_ids=pc.fixation_span_ids, status='approved'))
                edges.append(GraphEdge(id=new_id('edge'), source=pc.id, target=h.id, type='capiton', evidence_span_ids=pc.fixation_span_ids))
            for sid in h.support_ids:
                evidence = obs_by_id.get(sid).evidence_span_ids if obs_by_id.get(sid) else []
                if evidence:
                    edges.append(GraphEdge(id=new_id('edge'), source=sid, target=h.id, type='hypothesis', evidence_span_ids=evidence))
            ops.append(NarrativeOperator(
                id=new_id('op'), operator='REPETITION', source_finding_ids=[h.id],
                allowed=True, use_cases=['在有跨情境证据时重现叙事关系'],
                counterexamples=h.counterexamples, approval_state='approved',
            ))
        prev_disc = None
        for dt in discourse_trajectory:
            if prev_disc and prev_disc != dt:
                edges.append(GraphEdge(id=new_id('edge'), source=prev_disc, target=dt, type='discourse_rotation', evidence_span_ids=[]))
            prev_disc = dt
        r.packet.narrative_operators = ops
        r.state = RunState.COMPILED
        r.packet.state = RunState.COMPILED
        self.store.put_run(r)
        logger.info("export: run=%s compiled", rid)
        topology = dict(r.topology)
        topology['discourse_trajectory'] = discourse_trajectory
        topology['capiton_points'] = [
            pc.model_dump() for h in r.packet.hypotheses for pc in h.points_de_capiton
        ]
        return {
            'run_id': rid,
            'packet': r.packet.model_dump(mode='json'),
            'graph': {'nodes': [n.model_dump() for n in nodes], 'edges': [e.model_dump() for e in edges]},
            'topology': topology,
            'annotations': [a.model_dump(mode='json') for a in r.packet.cultural_annotations],
            'hallucination_reports': r.packet.hallucination_reports,
        }
