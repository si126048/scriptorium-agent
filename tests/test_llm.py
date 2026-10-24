import pytest
from scriptorium.llm import FakeProvider, QwenProvider
from scriptorium.formal.prompts import FORMAL_EVIDENCE_SYSTEM, FORMAL_INTERPRETER_SYSTEM, FORMAL_CRITIC_SYSTEM
from scriptorium.models import Observation, Hypothesis


def test_fake_provider_evidence_stage():
    fp = FakeProvider()
    result = fp.generate_structured(
        FORMAL_EVIDENCE_SYSTEM,
        {"span_ids": ["s1", "s2"], "spans_text": "text"},
        Observation,
        {"stage": "evidence"},
    )
    assert "observations" in result
    assert len(result["observations"]) == 1
    assert result["observations"][0]["evidence_span_ids"] == ["s1"]


def test_fake_provider_interpreter_stage():
    fp = FakeProvider()
    result = fp.generate_structured(
        FORMAL_INTERPRETER_SYSTEM,
        {"observation_ids": ["o1"], "theory_reference_ids": ["t1"],
         "observation_labels": ["label1"]},
        Hypothesis,
        {"stage": "interpreter"},
    )
    assert "hypotheses" in result
    assert len(result["hypotheses"]) == 1
    assert result["hypotheses"][0]["theory_reference_ids"] == ["t1"]


def test_fake_provider_critic_stage_per_hypothesis():
    fp = FakeProvider()
    result = fp.generate_structured(
        FORMAL_CRITIC_SYSTEM,
        {"hypothesis_ids": ["h1", "h2"], "observation_ids": ["o1"],
         "observation_labels": ["l1"]},
        dict,
        {"stage": "critic"},
    )
    assert "counterexamples_by_hypothesis" in result
    assert "h1" in result["counterexamples_by_hypothesis"]
    assert "h2" in result["counterexamples_by_hypothesis"]
    assert len(result["counterexamples_by_hypothesis"]["h1"]) >= 1
    assert len(result["counterexamples_by_hypothesis"]["h2"]) >= 1


def test_fake_provider_unknown_stage():
    fp = FakeProvider()
    with pytest.raises(ValueError, match="UNKNOWN_STAGE"):
        fp.generate_structured("prompt", {}, dict, {"stage": "nonexistent"})


def test_qwen_provider_empty_key_rejected():
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        QwenProvider(api_key="")


def test_qwen_provider_empty_env_rejected(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        QwenProvider()


def test_prompt_constants_non_empty():
    assert len(FORMAL_EVIDENCE_SYSTEM) > 100
    assert len(FORMAL_INTERPRETER_SYSTEM) > 100
    assert len(FORMAL_CRITIC_SYSTEM) > 100
    assert "Lacan" in FORMAL_EVIDENCE_SYSTEM
    assert "discourse" in FORMAL_INTERPRETER_SYSTEM.lower()
    assert "counterexample" in FORMAL_CRITIC_SYSTEM.lower()
