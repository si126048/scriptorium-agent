from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger(__name__)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_single_analysis(store, provider, project_id: str, participant_id: str,
                                  source_ids: list[str], text: str = ''):
    """SSE generator wrapping the single-perspective Workflow."""
    from .workflow import Workflow
    from .rag import ingest_text

    idem = f'sse-{uuid.uuid4().hex[:12]}'

    if text and not source_ids:
        source_ids = ingest_text(store, text, project_id, participant_id)

    if not source_ids:
        yield sse_event('error', {'message': 'No source text provided'})
        return

    workflow = Workflow(store, provider)

    yield sse_event('stage', {'name': 'evidence', 'label': '识别话语模式', 'phase': 1, 'status': 'running'})

    try:
        run = workflow.run(project_id, participant_id, source_ids, idem)
    except Exception as exc:
        yield sse_event('error', {'message': f'Analysis failed: {exc}'})
        return

    packet = run.packet
    if not packet:
        yield sse_event('error', {'message': 'Analysis produced no results'})
        return

    for obs in (packet.observations or []):
        yield sse_event('observation', {
            'id': obs.id,
            'label': obs.label,
            'register': obs.rsi_register,
            'markers': obs.register_markers,
        })

    yield sse_event('stage', {'name': 'interpreter', 'label': '构建理论假设', 'phase': 2, 'status': 'running'})

    for hyp in (packet.hypotheses or []):
        yield sse_event('hypothesis', {
            'id': hyp.id,
            'concepts': hyp.concept_ids,
            'status': hyp.status,
            'discourse': hyp.discourse_type,
        })

    yield sse_event('stage', {'name': 'critic', 'label': '反例检验', 'phase': 3, 'status': 'running'})

    for hyp in (packet.hypotheses or []):
        for ce in (hyp.counterexamples or []):
            yield sse_event('counterexample', {
                'id': f'cc_{hyp.id}',
                'text': ce if isinstance(ce, str) else str(ce),
                'hypothesis_id': hyp.id,
            })

    yield sse_event('complete', {
        'run_id': run.id,
        'state': run.state,
        'summary': {
            'observations': len(packet.observations or []),
            'hypotheses': len(packet.hypotheses or []),
        },
    })


async def stream_dialectical_analysis(store, provider, project_id: str, participant_id: str,
                                      source_ids: list[str], text: str = '',
                                      perspective_ids: list[str] | None = None):
    """SSE generator wrapping the 4-phase DialecticalWorkflow."""
    from .dialectical import DialecticalWorkflow
    from .rag import ingest_text
    from .perspectives.registry import PerspectiveRegistry

    if perspective_ids is None:
        perspective_ids = ['lacan', 'deleuze']

    if text and not source_ids:
        source_ids = ingest_text(store, text, project_id, participant_id)

    if not source_ids:
        yield sse_event('error', {'message': 'No source text provided'})
        return

    registry = PerspectiveRegistry()
    try:
        perspectives = registry.load_many(perspective_ids)
    except KeyError as exc:
        yield sse_event('error', {'message': f'Unknown perspective: {exc}'})
        return

    idem = f'sse-dial-{uuid.uuid4().hex[:12]}'
    dw = DialecticalWorkflow(store, provider, perspectives)

    try:
        result = dw.run(project_id, participant_id, source_ids, idem)
    except Exception as exc:
        logger.exception('dialectical workflow failed')
        yield sse_event('error', {'message': f'Dialectical analysis failed: {exc}'})
        return

    yield sse_event('stage', {'name': 'phase1', 'label': '独立分析', 'phase': 1, 'status': 'done'})

    for pa in (result.phase1_analyses or []):
        for obs in (pa.observations or []):
            yield sse_event('observation', {
                'id': obs.id,
                'label': obs.label,
                'register': obs.rsi_register,
                'perspective': pa.perspective_id,
            })
        for hyp in (pa.hypotheses or []):
            yield sse_event('hypothesis', {
                'id': hyp.id,
                'concepts': hyp.concept_ids,
                'perspective': pa.perspective_id,
            })

    yield sse_event('stage', {'name': 'phase2', 'label': '交叉批判', 'phase': 2, 'status': 'done'})

    for cc in (result.phase2_cross_critiques or []):
        for ce in (cc.counterexamples or []):
            yield sse_event('counterexample', {
                'id': ce.id,
                'text': ce.text,
                'source': ce.source,
            })

    yield sse_event('stage', {'name': 'phase3', 'label': '综合', 'phase': 3, 'status': 'done'})

    syn = result.phase3_synthesis
    if syn:
        for conv in (syn.convergence or []):
            yield sse_event('synthesis', {
                'type': 'convergence',
                'finding': conv.get('finding', str(conv)) if isinstance(conv, dict) else str(conv),
            })
        for div in (syn.divergence or []):
            yield sse_event('synthesis', {
                'type': 'divergence',
                'topic': div.get('topic', str(div)) if isinstance(div, dict) else str(div),
            })

    yield sse_event('stage', {'name': 'phase4', 'label': '报告', 'phase': 4, 'status': 'running'})

    report = result.phase4_report
    if report:
        report_text = report if isinstance(report, str) else str(report)
        for i in range(0, len(report_text), 80):
            chunk = report_text[i:i + 80]
            yield sse_event('text', {'chunk': chunk})
    elif provider and hasattr(provider, 'generate_stream'):
        from .llm import DIALECTICAL_REPORT_SYSTEM
        syn_dict = syn.model_dump() if syn else {}
        user_content = f"综合分析结果：\n{json.dumps(syn_dict, ensure_ascii=False, indent=2)}\n\n请撰写完整的辩证分析报告。"
        try:
            for chunk in provider.generate_stream(DIALECTICAL_REPORT_SYSTEM, user_content):
                yield sse_event('text', {'chunk': chunk})
        except Exception as exc:
            yield sse_event('text', {'chunk': f'\n\n[报告生成失败: {exc}]'})
    else:
        yield sse_event('text', {'chunk': '辩证分析完成（无 API key，报告生成跳过）'})

    yield sse_event('complete', {'phase': 4, 'status': 'done'})
