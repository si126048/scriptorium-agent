from __future__ import annotations

import textwrap

from ..models import PerspectiveConfig

_STAGE_MAP = {
    'evidence': 'evidence_prompt_variant',
    'interpreter': 'interpreter_prompt_variant',
    'critic': 'critique_prompt_variant',
}

_FORMAL_LACAN = {
    'evidence': 'FORMAL_EVIDENCE_SYSTEM',
    'interpreter': 'FORMAL_INTERPRETER_SYSTEM',
    'critic': 'FORMAL_CRITIC_SYSTEM',
}

_FORMAL_DELEUZE = {
    'evidence': 'FORMAL_DELEUZE_EVIDENCE',
    'interpreter': 'FORMAL_DELEUZE_INTERPRETER',
    'critic': 'FORMAL_DELEUZE_CRITIQUE',
}


def build_perspective_prompts(config: PerspectiveConfig, stage: str) -> str:
    if config.id == 'deleuze' and stage in _FORMAL_DELEUZE:
        from ..formal import prompts as fp
        base = getattr(fp, _FORMAL_DELEUZE[stage])
        framing = _perspective_framing(config)
        return framing + '\n\n' + base

    if config.id == 'lacan' and stage in _FORMAL_LACAN:
        from ..formal import prompts as fp
        base = getattr(fp, _FORMAL_LACAN[stage])
        framing = _perspective_framing(config)
        return framing + '\n\n' + base

    variant_attr = _STAGE_MAP.get(stage)
    if variant_attr:
        variant = getattr(config, variant_attr, None)
        if variant:
            return variant

    from ..formal.prompts import FORMAL_CRITIC_SYSTEM, FORMAL_EVIDENCE_SYSTEM, FORMAL_INTERPRETER_SYSTEM
    base_prompts = {
        'evidence': FORMAL_EVIDENCE_SYSTEM,
        'interpreter': FORMAL_INTERPRETER_SYSTEM,
        'critic': FORMAL_CRITIC_SYSTEM,
    }
    base = base_prompts.get(stage, '')
    if not base:
        return ''

    framing = _perspective_framing(config)
    return framing + '\n\n' + base


def _perspective_framing(config: PerspectiveConfig) -> str:
    parts = [f'你现在从 {config.name} 视角进行分析。']
    if config.concept_inventory:
        concepts = ', '.join(config.concept_inventory)
        parts.append(f'你的核心概念工具箱：{concepts}。')
    if config.vocabulary:
        vocab_lines = '\n'.join(f'  - {k}: {v}' for k, v in list(config.vocabulary.items())[:8])
        parts.append(f'关键术语：\n{vocab_lines}')
    if config.blind_spots:
        spots = '; '.join(config.blind_spots[:4])
        parts.append(f'注意该视角的系统性盲区：{spots}')
    return textwrap.dedent('\n'.join(parts))
