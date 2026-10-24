from scriptorium.models import PerspectiveConfig
from scriptorium.perspectives.registry import PerspectiveRegistry, get_perspective, list_perspectives
from scriptorium.perspectives.prompts import build_perspective_prompts


def test_registry_loads_builtins():
    reg = PerspectiveRegistry()
    ids = {p.id for p in reg.list_all()}
    assert 'lacan' in ids
    assert 'deleuze' in ids


def test_get_perspective_found():
    p = get_perspective('lacan')
    assert p is not None
    assert p.name
    assert len(p.concept_inventory) > 0


def test_get_perspective_missing():
    assert get_perspective('nonexistent') is None


def test_load_many_ok():
    reg = PerspectiveRegistry()
    configs = reg.load_many(['lacan', 'deleuze'])
    assert len(configs) == 2
    assert {c.id for c in configs} == {'lacan', 'deleuze'}


def test_load_many_unknown_raises():
    reg = PerspectiveRegistry()
    try:
        reg.load_many(['lacan', 'bogus'])
        assert False, 'expected KeyError'
    except KeyError as exc:
        assert 'bogus' in str(exc)


def test_lacanian_concepts():
    p = get_perspective('lacan')
    assert 'objet_a' in p.concept_inventory
    assert 'four_discourses' in p.concept_inventory
    assert len(p.blind_spots) >= 1
    assert len(p.vocabulary) >= 1


def test_deleuzian_concepts():
    p = get_perspective('deleuze')
    assert 'assemblage' in p.concept_inventory
    assert 'rhizome' in p.concept_inventory
    assert 'deterritorialization' in p.concept_inventory
    assert 'desiring_machine' in p.concept_inventory
    assert 'lines_of_flight' in p.concept_inventory
    assert len(p.blind_spots) >= 2


def test_deleuzian_has_prompt_variants():
    p = get_perspective('deleuze')
    assert p.evidence_prompt_variant is not None
    assert p.interpreter_prompt_variant is not None
    assert p.critique_prompt_variant is not None
    assert 'assemblage' in p.evidence_prompt_variant.lower() or '装配' in p.evidence_prompt_variant
    assert '连接' in p.evidence_prompt_variant or 'connection' in p.evidence_prompt_variant.lower()


def test_lacanian_no_prompt_variants():
    p = get_perspective('lacan')
    assert p.evidence_prompt_variant is None
    assert p.interpreter_prompt_variant is None
    assert p.critique_prompt_variant is None


def test_build_prompts_uses_formal_for_deleuze():
    p = get_perspective('deleuze')
    evidence_prompt = build_perspective_prompts(p, 'evidence')
    assert 'Deleuzian empiricist' in evidence_prompt or 'assemblage' in evidence_prompt.lower()
    assert 'Notation:' in evidence_prompt


def test_build_prompts_prepends_framing_for_lacan():
    p = get_perspective('lacan')
    evidence_prompt = build_perspective_prompts(p, 'evidence')
    assert '拉康' in evidence_prompt or 'Lacan' in evidence_prompt
    assert '能指' in evidence_prompt or 'signifier' in evidence_prompt.lower()


def test_build_prompts_unknown_stage_returns_empty():
    p = get_perspective('lacan')
    assert build_perspective_prompts(p, 'nonexistent') == ''


def test_register_custom_perspective():
    reg = PerspectiveRegistry()
    custom = PerspectiveConfig(id='test_custom', name='Test', concept_inventory=['a', 'b'])
    reg.register(custom)
    assert reg.get('test_custom') is custom


def test_list_perspectives_returns_all():
    all_p = list_perspectives()
    assert len(all_p) >= 2
    ids = {p.id for p in all_p}
    assert 'lacan' in ids
    assert 'deleuze' in ids
