from __future__ import annotations

import pytest

from scriptorium.topology.borromean import (
    Register, RegisterCoherenceMonitor, RSI_MARKERS,
)
from scriptorium.topology.mathemes import (
    Matheme, MathemeKind, MathemeRelation, MATHEME_DEFAULT_REGISTERS,
)
from scriptorium.topology.discourses import (
    TermKind,
    MASTER, UNIVERSITY, HYSTERIC, ANALYST,
    DISCOURSE_ROTATION, identify_discourse,
)


class TestMathemeKind:
    def test_all_kinds_exist(self):
        assert MathemeKind.S == "S"
        assert MathemeKind.s == "s"
        assert MathemeKind.S_A == "S(A)"
        assert MathemeKind.a == "a"
        assert MathemeKind.diamond == "◇"
        assert MathemeKind.barred == "$"

    def test_default_registers(self):
        assert MATHEME_DEFAULT_REGISTERS[MathemeKind.S] == Register.SYMBOLIC
        assert MATHEME_DEFAULT_REGISTERS[MathemeKind.a] == Register.REAL
        assert MATHEME_DEFAULT_REGISTERS[MathemeKind.s] == Register.IMAGINARY


class TestMatheme:
    def test_creation(self):
        m = Matheme(id="m1", kind=MathemeKind.S, register=Register.SYMBOLIC,
                    label="phallus", valence=0.8, anchor_span_ids=["s1"])
        assert m.id == "m1"
        assert m.presence()
        assert not m.absence()
        assert m.anchor_span_ids == ["s1"]

    def test_frozen(self):
        m = Matheme(id="m1", kind=MathemeKind.S, register=Register.SYMBOLIC, label="x")
        with pytest.raises(AttributeError):
            m.valence = 0.5

    def test_valence_range(self):
        with pytest.raises(ValueError, match="valence"):
            Matheme(id="m1", kind=MathemeKind.a, register=Register.REAL,
                    label="x", valence=1.5)
        with pytest.raises(ValueError, match="valence"):
            Matheme(id="m1", kind=MathemeKind.a, register=Register.REAL,
                    label="x", valence=-1.5)

    def test_boundary_valences(self):
        m_pos = Matheme(id="m1", kind=MathemeKind.S, register=Register.SYMBOLIC,
                        label="x", valence=1.0)
        assert m_pos.presence()
        m_neg = Matheme(id="m2", kind=MathemeKind.S, register=Register.SYMBOLIC,
                        label="x", valence=-1.0)
        assert m_neg.absence()
        m_zero = Matheme(id="m3", kind=MathemeKind.S, register=Register.SYMBOLIC,
                         label="x", valence=0.0)
        assert not m_zero.presence()
        assert not m_zero.absence()


class TestMathemeRelation:
    def test_valid_relations(self):
        for rel in ["metaphor", "metonymy", "resistance", "fantasy", "phantom"]:
            r = MathemeRelation(source_id="a", target_id="b", relation=rel, weight=0.5)
            assert r.relation == rel

    def test_invalid_relation(self):
        with pytest.raises(ValueError, match="unknown relation"):
            MathemeRelation(source_id="a", target_id="b", relation="invalid")

    def test_weight_range(self):
        with pytest.raises(ValueError, match="weight"):
            MathemeRelation(source_id="a", target_id="b", relation="metaphor", weight=1.5)
        with pytest.raises(ValueError, match="weight"):
            MathemeRelation(source_id="a", target_id="b", relation="metaphor", weight=-0.1)

    def test_reversed(self):
        r = MathemeRelation(source_id="a", target_id="b", relation="metaphor", weight=0.7)
        rev = r.reversed()
        assert rev.source_id == "b"
        assert rev.target_id == "a"
        assert rev.relation == "metaphor"
        assert rev.weight == 0.7

    def test_frozen(self):
        r = MathemeRelation(source_id="a", target_id="b", relation="metonymy")
        with pytest.raises(AttributeError):
            r.weight = 0.3

    def test_metaphor_metonymy_non_commutative(self):
        r1 = MathemeRelation(source_id="S1", target_id="S2", relation="metaphor")
        r2 = MathemeRelation(source_id="S2", target_id="s1", relation="metonymy")
        assert r1.relation != r2.relation
        assert r1.reversed().relation == r1.relation


class TestDiscourse:
    def test_quarter_turn_master_to_hysteric(self):
        assert MASTER.quarter_turn_cw() == HYSTERIC

    def test_quarter_turn_hysteric_to_analyst(self):
        assert HYSTERIC.quarter_turn_cw() == ANALYST

    def test_quarter_turn_analyst_to_university(self):
        assert ANALYST.quarter_turn_cw() == UNIVERSITY

    def test_quarter_turn_university_to_master(self):
        assert UNIVERSITY.quarter_turn_cw() == MASTER

    def test_four_turns_return_to_self(self):
        d = MASTER
        for _ in range(4):
            d = d.quarter_turn_cw()
        assert d == MASTER

    def test_orbit_length(self):
        orbit = MASTER.orbit()
        assert len(orbit) == 4
        assert orbit[0] == MASTER
        assert orbit[1] == HYSTERIC
        assert orbit[2] == ANALYST
        assert orbit[3] == UNIVERSITY

    def test_orbit_all_unique(self):
        orbit = MASTER.orbit()
        assert len(set(orbit)) == 4

    def test_ccw_is_inverse_of_cw(self):
        assert MASTER.quarter_turn_cw().quarter_turn_ccw() == MASTER

    def test_discourse_rotation_list(self):
        assert DISCOURSE_ROTATION == [MASTER, HYSTERIC, ANALYST, UNIVERSITY]

    def test_identify_discourse(self):
        assert identify_discourse(TermKind.S1, TermKind.S2, TermKind.barred, TermKind.a) == MASTER
        assert identify_discourse(TermKind.barred, TermKind.S1, TermKind.a, TermKind.S2) == HYSTERIC

    def test_identify_unknown_discourse(self):
        result = identify_discourse(TermKind.S1, TermKind.S1, TermKind.S1, TermKind.S1)
        assert result is None

    def test_named_discourses(self):
        assert MASTER.name == "master"
        assert HYSTERIC.name == "hysteric"
        assert ANALYST.name == "analyst"
        assert UNIVERSITY.name == "university"

    def test_frozen(self):
        with pytest.raises(AttributeError):
            MASTER.agent = TermKind.a


class TestRegister:
    def test_values(self):
        assert Register.REAL == "R"
        assert Register.SYMBOLIC == "S"
        assert Register.IMAGINARY == "I"

    def test_markers_non_empty(self):
        for reg in Register:
            assert len(RSI_MARKERS[reg]) > 0


class TestRegisterCoherenceMonitor:
    def test_feed_single_register(self):
        mon = RegisterCoherenceMonitor(window_size=5)
        hits = mon.feed("the symbolic law and structure", Register.SYMBOLIC)
        assert len(hits[Register.SYMBOLIC]) > 0

    def test_feed_detects_markers(self):
        mon = RegisterCoherenceMonitor()
        hits_r = mon.feed("身体颤抖 说不出话 创伤", Register.REAL)
        assert len(hits_r[Register.REAL]) > 0
        hits_s = mon.feed("大他者的法则与命名", Register.SYMBOLIC)
        assert len(hits_s[Register.SYMBOLIC]) > 0

    def test_coherence_scores_shape(self):
        mon = RegisterCoherenceMonitor(window_size=3)
        mon.feed("test text")
        scores = mon.coherence_scores()
        assert len(scores) == 3
        assert (Register.REAL, Register.SYMBOLIC) in scores
        assert (Register.SYMBOLIC, Register.IMAGINARY) in scores
        assert (Register.REAL, Register.IMAGINARY) in scores

    def test_window_sliding(self):
        mon = RegisterCoherenceMonitor(window_size=2)
        mon.feed("symbolic law structure father")
        mon.feed("mirror image reflection")
        mon.feed("body trembles pain")
        assert len(mon._windows) == 2

    def test_unknotting_detection(self):
        mon = RegisterCoherenceMonitor(window_size=5)
        for _ in range(3):
            mon.feed("law structure symbolic father name signifier rule")
            mon.feed("mirror image reflection imaginary like")
        for _ in range(3):
            mon.feed("body trembles pain cannot speak trauma real")
        events = mon.detect_unknotting()
        assert isinstance(events, list)

    def test_no_unknotting_with_coherent_input(self):
        mon = RegisterCoherenceMonitor(window_size=5)
        for _ in range(5):
            mon.feed("law symbolic structure father mirror image body real")
        events = mon.detect_unknotting()
        assert len(events) == 0

    def test_empty_coherence(self):
        mon = RegisterCoherenceMonitor()
        scores = mon.coherence_scores()
        for v in scores.values():
            assert v == 0.0
