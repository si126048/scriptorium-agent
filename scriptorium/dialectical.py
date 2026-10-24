"""Dialectical multi-perspective analysis workflow.

Orchestrates four phases:
1. Independent analysis from each perspective
2. Cross-critique between perspectives
3. Synthesis of convergence, divergence, and unique insights
4. Optional comprehensive report generation
"""
from __future__ import annotations

import logging

from .db import Store, new_id
from .models import (
    Counterexample,
    CrossCritique,
    DialecticalResult,
    Hypothesis,
    Observation,
    PerspectiveAnalysis,
    PerspectiveConfig,
    SynthesisReport,
)
from .workflow import Workflow

logger = logging.getLogger(__name__)


class DialecticalWorkflow:
    def __init__(self, store: Store, provider, perspectives: list[PerspectiveConfig]):
        self.store = store
        self.provider = provider
        self.perspectives = perspectives
        self._workflow = Workflow(store, provider)

    def run(self, project_id: str, participant_id: str,
            source_ids: list[str], idem: str,
            generate_report: bool = False) -> DialecticalResult:
        run_id = new_id('dial')
        logger.info("dialectical run=%s perspectives=%s", run_id, [p.id for p in self.perspectives])

        p = self.store.get_participant(project_id, participant_id)
        if not p or p.withdrawn_at or not p.consent_scope.is_active():
            raise PermissionError('PARTICIPANT_WITHDRAWN')

        docs = [self.store.get_document(x) for x in source_ids]
        if any(not d or d.participant_id != participant_id or d.project_id != project_id for d in docs):
            raise PermissionError('OBJECT_ACCESS_DENIED')

        spans = self._workflow._collect_evidence(docs)
        span_ids = [s.id for s in spans]
        spans_text = '\n\n'.join(f'[span_id={s.id}]\n{s.excerpt}' for s in spans[:50])

        phase1 = self._phase1_independent(spans, span_ids, spans_text)
        phase2 = self._phase2_cross_critique(phase1, span_ids)
        phase3 = self._phase3_synthesis(phase1, phase2)
        phase4 = self._phase4_report(phase3) if generate_report else None

        return DialecticalResult(
            run_id=run_id,
            perspective_ids=[p.id for p in self.perspectives],
            phase1_analyses=phase1,
            phase2_cross_critiques=phase2,
            phase3_synthesis=phase3,
            phase4_report=phase4,
        )

    def _phase1_independent(self, spans, span_ids: list[str], spans_text: str) -> list[PerspectiveAnalysis]:
        analyses = []
        for perspective in self.perspectives:
            logger.info("phase 1: perspective=%s", perspective.id)
            obs = self._perspective_observe(perspective, spans, span_ids, spans_text)
            hyps = self._perspective_interpret(perspective, obs)
            analyses.append(PerspectiveAnalysis(
                perspective_id=perspective.id,
                observations=obs,
                hypotheses=hyps,
            ))
        return analyses

    def _perspective_observe(self, perspective: PerspectiveConfig,
                             spans, span_ids: list[str], spans_text: str) -> list[Observation]:
        payload = {
            'span_ids': span_ids,
            'spans_text': spans_text,
        }
        result = self.provider.generate_structured(
            '', payload, Observation,
            {'stage': 'dialectical_evidence', 'perspective_id': perspective.id,
             'perspective_config': perspective.model_dump()},
        )
        observations = []
        allowed = set(span_ids)
        for index, raw in enumerate(result.get('observations', [])):
            try:
                obs = Observation.model_validate({
                    **raw,
                    'id': raw.get('id', f'{perspective.id}_obs_{index + 1}'),
                })
                if set(obs.evidence_span_ids) <= allowed:
                    observations.append(obs)
            except Exception as exc:
                logger.warning("skipping invalid observation %d from %s: %s", index, perspective.id, exc)
        return observations

    def _perspective_interpret(self, perspective: PerspectiveConfig,
                               observations: list[Observation]) -> list[Hypothesis]:
        obs_labels = [{'id': o.id, 'label': o.label, 'register': o.rsi_register} for o in observations]
        payload = {
            'observation_ids': [o.id for o in observations],
            'observation_labels': obs_labels,
        }
        result = self.provider.generate_structured(
            '', payload, Hypothesis,
            {'stage': 'dialectical_interpreter', 'perspective_id': perspective.id,
             'perspective_config': perspective.model_dump()},
        )
        obs_ids = {o.id for o in observations}
        hypotheses = []
        for index, raw in enumerate(result.get('hypotheses', [])):
            try:
                hyp = Hypothesis.model_validate({
                    **raw,
                    'id': raw.get('id', f'{perspective.id}_hyp_{index + 1}'),
                    'status': raw.get('status', 'provisional'),
                })
                if set(hyp.support_ids) <= obs_ids:
                    hypotheses.append(hyp)
            except Exception as exc:
                logger.warning("skipping invalid hypothesis %d from %s: %s", index, perspective.id, exc)
        return hypotheses

    def _phase2_cross_critique(self, analyses: list[PerspectiveAnalysis],
                               span_ids: list[str]) -> list[CrossCritique]:
        if len(self.perspectives) < 2:
            return []
        critiques = []
        for i, source_persp in enumerate(self.perspectives):
            target_idx = (i + 1) % len(self.perspectives)
            target_persp = self.perspectives[target_idx]
            target_analysis = next((a for a in analyses if a.perspective_id == target_persp.id), None)
            if not target_analysis:
                continue
            logger.info("phase 2: %s critiques %s", source_persp.id, target_persp.id)
            critique = self._single_cross_critique(source_persp, target_analysis, span_ids)
            critiques.append(critique)
        return critiques

    def _single_cross_critique(self, source: PerspectiveConfig,
                               target: PerspectiveAnalysis,
                               span_ids: list[str]) -> CrossCritique:
        payload = {
            'target_analysis': {
                'perspective_id': target.perspective_id,
                'observations': [o.model_dump(mode='json') for o in target.observations],
                'hypotheses': [h.model_dump(mode='json') for h in target.hypotheses],
            },
        }
        result = self.provider.generate_structured(
            '', payload, dict,
            {'stage': 'cross_critique', 'perspective_id': source.id,
             'perspective_config': source.model_dump()},
        )
        counterexamples = []
        for index, raw in enumerate(result.get('counterexamples', [])):
            try:
                ce = Counterexample.model_validate({
                    **raw,
                    'id': raw.get('id', f'cc_{source.id}_{index + 1}'),
                    'source': 'cross_critique',
                })
                counterexamples.append(ce)
            except Exception as exc:
                logger.warning('skipping invalid cross-critique counterexample %d from %s: %s', index, source.id, exc)
        return CrossCritique(
            source_perspective_id=source.id,
            target_perspective_id=target.perspective_id,
            counterexamples=counterexamples,
            blind_spot_alerts=result.get('blind_spot_alerts', []),
            epistemic_gaps=result.get('epistemic_gaps', []),
        )

    def _phase3_synthesis(self, analyses: list[PerspectiveAnalysis],
                          critiques: list[CrossCritique]) -> SynthesisReport:
        logger.info("phase 3: synthesis")
        payload = {
            'perspective_ids': [p.id for p in self.perspectives],
            'analyses': {a.perspective_id: {
                'observations': len(a.observations),
                'hypotheses': [h.model_dump(mode='json') for h in a.hypotheses],
            } for a in analyses},
            'cross_critiques': [{
                'source': c.source_perspective_id,
                'target': c.target_perspective_id,
                'alerts': c.blind_spot_alerts,
                'gaps': c.epistemic_gaps,
            } for c in critiques],
        }
        result = self.provider.generate_structured(
            '', payload, SynthesisReport,
            {'stage': 'dialectical_synthesis'},
        )
        return SynthesisReport.model_validate(result)

    def _phase4_report(self, synthesis: SynthesisReport) -> str:
        logger.info("phase 4: report generation")
        payload = {
            'synthesis': synthesis.model_dump(mode='json'),
        }
        result = self.provider.generate_structured(
            '', payload, dict,
            {'stage': 'dialectical_report'},
        )
        return result.get('report', '')
