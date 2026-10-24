import json

from scriptorium.behavioral.materials import load_materials
from scriptorium.db import Store
from scriptorium.interview import InterviewManager, load_config
from scriptorium.llm import FakeProvider
from scriptorium.models import ConsentScope, Participant, Project


def _manager(tmp_path):
    store = Store(str(tmp_path / 'interview.sqlite'))
    store.create_project(Project(id='project'))
    store.put_participant(Participant(
        id='participant', project_id='project', pseudonym='P', consent_scope=ConsentScope(),
    ))
    return store, InterviewManager(store, FakeProvider())


def test_interview_follows_up_then_advances_and_survives_pause(tmp_path):
    _store, manager = _manager(tmp_path)
    session, config = manager.create('project', 'participant')
    assert session.current_question_id == config.questions[0].id

    view = manager.submit(session.id, 'project', 'participant', 'Q1', '这是一个足够长的回答，用于触发澄清追问。')
    assert view['current_question']['kind'] == 'followup'
    followup_id = view['current_question']['id']
    view = manager.submit(session.id, 'project', 'participant', followup_id, '补充说明')
    assert view['current_question']['id'] == 'Q2'

    manager.pause(session.id, 'project', 'participant')
    try:
        manager.submit(session.id, 'project', 'participant', 'Q2', '暂停期间不应写入')
    except ValueError as exc:
        assert str(exc) == 'INTERVIEW_PAUSED'
    else:
        raise AssertionError('paused interviews must reject turns')
    assert manager.resume(session.id, 'project', 'participant')['state'] == 'IN_PROGRESS'


def test_interview_export_is_compatible_with_material_loader(tmp_path):
    _store, manager = _manager(tmp_path)
    session, _ = manager.create('project', 'participant')
    for question_id, answer in [('Q1', '回答一'), ('Q2', '回答二'), ('Q3', '回答三'), ('Q4', '回答四')]:
        manager.submit(session.id, 'project', 'participant', question_id, answer)
    session, payload = manager.complete(session.id, 'project', 'participant')
    artifact = tmp_path / 'interview.json'
    artifact.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    manifest.write_text(json.dumps({'sources': [{
        'source_id': 'session_source', 'participant_id': 'participant',
        'source_type': 'interview', 'path': artifact.name,
    }]}, ensure_ascii=False), encoding='utf-8')
    sources, spans = load_materials(manifest)
    assert session.state.value == 'COMPLETED'
    assert sources[0].source_type == 'interview'
    assert len(spans) == 4


def test_stale_question_and_withdrawal_are_rejected(tmp_path):
    _store, manager = _manager(tmp_path)
    session, _ = manager.create('project', 'participant')
    try:
        manager.submit(session.id, 'project', 'participant', 'Q2', '错误问题')
    except ValueError as exc:
        assert str(exc) == 'STALE_INTERVIEW_QUESTION'
    else:
        raise AssertionError('stale question must be rejected')
    withdrawn = manager.withdraw(session.id, 'project', 'participant')
    assert withdrawn['state'] == 'WITHDRAWN'
    try:
        manager.submit(session.id, 'project', 'participant', 'Q1', '不应写入')
    except ValueError as exc:
        assert str(exc) == 'INTERVIEW_NOT_ACTIVE'
    else:
        raise AssertionError('withdrawn interviews must reject turns')


def test_missing_custom_config_fails_and_default_is_available(tmp_path, monkeypatch):
    monkeypatch.setenv('LACAN_INTERVIEW_CONFIG_DIR', str(tmp_path))
    assert load_config('any-project').config_id == 'default-research-v1'
    try:
        load_config('any-project', 'missing-config')
    except ValueError as exc:
        assert str(exc) == 'INTERVIEW_CONFIG_NOT_FOUND'
    else:
        raise AssertionError('missing explicit config must fail')


def test_reset_starts_fresh_session_and_clears_active_answers(tmp_path):
    store, manager = _manager(tmp_path)
    session, _ = manager.create('project', 'participant')
    manager.submit(session.id, 'project', 'participant', 'Q1', '当前访谈回答')
    previous, fresh = manager.reset(session.id, 'project', 'participant')
    assert previous.id == session.id
    assert previous.state.value == 'WITHDRAWN'
    assert previous.turns == []
    assert fresh.id != previous.id
    assert fresh.state.value == 'CREATED'
    assert fresh.current_question_id == 'Q1'
    assert store.get_interview_session(previous.id, 'project', 'participant').turns == []
