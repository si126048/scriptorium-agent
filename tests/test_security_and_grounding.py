from pathlib import Path


from scriptorium.db import Store
from scriptorium.models import ConsentScope, Participant, Project
from scriptorium.rag import ingest, search
from scriptorium.workflow import Workflow


def _setup(tmp_path: Path):
    store = Store(str(tmp_path / 'security.sqlite'))
    store.create_project(Project(id='p'))
    store.put_participant(Participant(
        id='A', project_id='p', pseudonym='A',
        consent_scope=ConsentScope(),
    ))
    source = tmp_path / 'story.txt'
    source.write_text('A door appears.\nA door appears again.', encoding='utf-8')
    document = ingest(store, str(source), 'p', 'A', ConsentScope())
    return store, document


def test_grounding_expands_observations_to_spans(tmp_path):
    store, document = _setup(tmp_path)
    run = Workflow(store).run('p', 'A', [document.id], 'grounding')
    hypothesis = run.packet.hypotheses[0]
    assert hypothesis.support_ids == ['obs_1']
    assert hypothesis.fuzzy_groundings
    assert hypothesis.grounding_score > 0


def test_withdrawal_deletes_participant_data_and_runs(tmp_path):
    store, document = _setup(tmp_path)
    run = Workflow(store).run('p', 'A', [document.id], 'withdrawal')
    store.withdraw('p', 'A')
    assert store.get_document(document.id) is None
    assert store.get_run(run.id) is None
    assert store.list_spans_for_document(document.id) == []


def test_fts_query_treats_syntax_as_text(tmp_path):
    store, _ = _setup(tmp_path)
    assert search(store, '"unclosed (query') == []


