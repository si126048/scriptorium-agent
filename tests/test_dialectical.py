import uuid
from scriptorium.db import Store
from scriptorium.models import (
    ConsentScope, Participant, Project,
)
from scriptorium.rag import ingest
from scriptorium.llm import FakeProvider
from scriptorium.dialectical import DialecticalWorkflow
from scriptorium.perspectives.registry import PerspectiveRegistry


def _setup(tmp_path):
    db = str(tmp_path / f"test-{uuid.uuid4().hex}.sqlite")
    s = Store(db)
    s.create_project(Project(id="p"))
    s.put_participant(Participant(id="A", project_id="p", pseudonym="A",
                                  consent_scope=ConsentScope()))
    theory = tmp_path / "theory.md"
    theory.write_text("Repetition changes meaning across contexts.", encoding="utf-8")
    story = tmp_path / "story.txt"
    story.write_text("A door appears. A door appears again.", encoding="utf-8")
    ingest(s, str(theory), "p")
    d = ingest(s, str(story), "p", "A", ConsentScope())
    return s, d


def test_dialectical_two_perspectives(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem1")
    assert result.run_id
    assert len(result.perspective_ids) == 2
    assert 'lacan' in result.perspective_ids
    assert 'deleuze' in result.perspective_ids


def test_phase1_produces_analyses(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem2")
    assert len(result.phase1_analyses) == 2
    for analysis in result.phase1_analyses:
        assert analysis.perspective_id in ('lacan', 'deleuze')
        assert len(analysis.observations) >= 1
        assert len(analysis.hypotheses) >= 1


def test_phase2_cross_critiques(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem3")
    assert len(result.phase2_cross_critiques) == 2
    source_target_pairs = {(c.source_perspective_id, c.target_perspective_id) for c in result.phase2_cross_critiques}
    assert ('lacan', 'deleuze') in source_target_pairs
    assert ('deleuze', 'lacan') in source_target_pairs


def test_phase3_synthesis(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem4")
    assert result.phase3_synthesis is not None
    assert hasattr(result.phase3_synthesis, 'convergence')
    assert hasattr(result.phase3_synthesis, 'divergence')
    assert hasattr(result.phase3_synthesis, 'recommended_hypotheses')


def test_phase4_report_optional(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result_no_report = dw.run("p", "A", [d.id], "idem5a", generate_report=False)
    assert result_no_report.phase4_report is None
    result_with_report = dw.run("p", "A", [d.id], "idem5b", generate_report=True)
    assert result_with_report.phase4_report is not None
    assert len(result_with_report.phase4_report) > 0


def test_single_perspective_no_cross_critique(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem6")
    assert len(result.perspective_ids) == 1
    assert len(result.phase1_analyses) == 1
    assert len(result.phase2_cross_critiques) == 0


def test_unknown_source_raises(tmp_path):
    s, _d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    try:
        dw.run("p", "A", ["nonexistent_id"], "idem7")
        assert False, 'expected PermissionError'
    except PermissionError:
        pass


def test_dialectical_result_serializable(tmp_path):
    s, d = _setup(tmp_path)
    provider = FakeProvider()
    reg = PerspectiveRegistry()
    perspectives = reg.load_many(['lacan', 'deleuze'])
    dw = DialecticalWorkflow(s, provider, perspectives)
    result = dw.run("p", "A", [d.id], "idem8")
    data = result.model_dump(mode='json')
    assert data['run_id']
    assert len(data['perspective_ids']) == 2
    assert len(data['phase1_analyses']) == 2
    assert len(data['phase2_cross_critiques']) == 2
