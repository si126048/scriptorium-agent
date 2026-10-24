# ruff: noqa: F811
"""Ask-first research: a question typed into the composer retrieves, answers and cites by itself."""
from __future__ import annotations

import json
from types import SimpleNamespace

from test_research_integration import research, client, imported  # noqa: F401
from scriptorium.research import schema as db
from scriptorium.research.service import row, rows
from scriptorium.research.worker import run_one


def new_conversation(client, pid, title='提问'):
    response = client.post(f'/api/v2/projects/{pid}/conversations', json={'title': title})
    assert response.status_code == 201, response.text
    return response.json()['id']


def ask(client, pid, cid, text, key, **extra):
    response = client.post(f'/api/v2/projects/{pid}/conversations/{cid}/messages',
                           headers={'Idempotency-Key': key},
                           json={'text': text, 'tool': 'ask', 'provider_mode': 'demo', **extra})
    assert response.status_code == 202, response.text
    return response.json()['id']


def answer_record(client, pid, job_id):
    with client.app.state.research.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == job_id)
    assert job['state'] == 'succeeded', job
    record = client.get(f'/api/v2/projects/{pid}/artifacts/{job["result"]["record_id"]}').json()
    assert record['kind'] == 'research_answer'
    return record


def test_question_without_selection_is_researched_automatically(research, client):
    pid, _aid, _segments = imported(research, '自由需要物质条件。制度要求说明理由。')
    conversation = new_conversation(client, pid)
    job = ask(client, pid, conversation, '材料里“自由”是在什么意义上使用的？', 'ask-auto')
    run_one(research, job)
    record = answer_record(client, pid, job)
    payload = record['payload']
    # The agent picked a scope itself and disclosed how it did so.
    assert payload['scope'], payload
    assert payload['plan']['retrieval'] in {'search', 'material_scan'}
    assert payload['coverage'] and all(item['status'] in {'read', 'unread'} for item in payload['coverage'])
    assert payload['provider_mode'] == 'demo' and payload['insufficient'] is True
    messages = client.get(f'/api/v2/projects/{pid}/conversations/{conversation}/messages').json()
    assert [m['role'] for m in messages] == ['user', 'assistant']
    assert messages[-1]['artifact_ids'] == [record['id']]
    assert messages[-1]['metadata']['artifact_kind'] == 'research_answer'


def test_selection_narrows_the_scope_instead_of_searching(research, client):
    pid, aid, segments = imported(research, '第一份材料：自由需要条件。')
    conversation = new_conversation(client, pid)
    job = ask(client, pid, conversation, '只依据这份材料回答', 'ask-explicit', asset_ids=[aid])
    run_one(research, job)
    payload = answer_record(client, pid, job)['payload']
    assert payload['plan']['retrieval'] == 'explicit'
    assert {window['asset_id'] for window in payload['scope']} == {aid}
    assert {window['segment_id'] for window in payload['scope']} == {s['id'] for s in segments}


def test_empty_project_gives_a_clear_error_not_a_fake_answer(research, client):
    pid = research.create_project('tester', '空项目')['id']
    conversation = new_conversation(client, pid)
    job = ask(client, pid, conversation, '这里有什么材料？', 'ask-empty')
    run_one(research, job)
    with research.engine.connect() as c:
        stored = row(c, db.jobs, db.jobs.c.id == job)
    assert stored['state'] == 'failed'
    assert stored['error'] == 'NO_MATERIALS_FOR_QUESTION'
    assert client.get(f'/api/v2/projects/{pid}/records').json() == []


def test_live_ask_without_model_fails_instead_of_returning_demo(research, client, monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    monkeypatch.delenv('SCRIPTORIUM_LOCAL_RUNTIME_ROOT', raising=False)
    pid, _aid, _segments = imported(research, '自由需要条件。')
    conversation = new_conversation(client, pid)
    response = client.post(f'/api/v2/projects/{pid}/conversations/{conversation}/messages',
                           headers={'Idempotency-Key': 'ask-live'},
                           json={'text': '回答这个问题', 'tool': 'ask', 'provider_mode': 'live'})
    assert response.status_code == 202, response.text
    run_one(research, response.json()['id'])
    with research.engine.connect() as c:
        stored = row(c, db.jobs, db.jobs.c.id == response.json()['id'])
    assert stored['state'] == 'failed'
    assert stored['error'] == 'MODEL_NOT_CONFIGURED'


def test_answer_citations_become_anchors_and_scope_can_be_deepened(research, client, monkeypatch):
    text = '制度要求说明理由，却禁止据理申辩。'
    pid, _aid, segments = imported(research, text)
    segment = segments[0]
    citation = {'segment_id': segment['id'], 'start_codepoint': 0, 'end_codepoint': len(segment['text']),
                'exact_quote': segment['text']}
    model_result = {'answer': '制度同时要求说明理由与禁止申辩。', 'insufficient': False,
                    'citations': [citation],
                    'findings': [{'claim': '两项规定互相牵制', 'citations': [citation]}],
                    'open_questions': ['起草者是否意识到这一张力？'],
                    'followups': ['把这段材料展开为内在批判？']}
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_result)),
                                                       finish_reason='stop')],
                               usage=SimpleNamespace(model_dump=lambda: {'total_tokens': 120}))

    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setattr('scriptorium.llm.QwenProvider', lambda **kwargs: SimpleNamespace(
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        model='test-model', temperature=0))
    conversation = new_conversation(client, pid)
    response = client.post(f'/api/v2/projects/{pid}/conversations/{conversation}/messages',
                           headers={'Idempotency-Key': 'ask-live-ok'},
                           json={'text': '这组规定有什么问题？', 'tool': 'ask', 'provider_mode': 'live'})
    run_one(research, response.json()['id'])
    record = answer_record(client, pid, response.json()['id'])
    payload = record['payload']
    assert payload['provider_mode'] == 'live' and payload['model'] == 'test-model'
    assert payload['evidence_ids'] and payload['usage'] == {'total_tokens': 120}
    # Every quote is an exact anchor that resolves to the right immutable text.
    for anchor_id in payload['evidence_ids']:
        anchor = client.get(f'/api/v2/projects/{pid}/anchors/{anchor_id}').json()
        assert anchor['segment']['text'][anchor['start_codepoint']:anchor['end_codepoint']] == anchor['exact_quote']
        assert anchor['exact_quote'] == segment['text']
    with research.engine.connect() as c:
        calls_logged = rows(c, db.model_calls, db.model_calls.c.project_id == pid)
    assert len(calls_logged) == 1 and calls_logged[0]['state'] == 'returned'
    assert '材料' in calls[0]['messages'][0]['content']
    # One click deepens into the existing multi-method pipeline over the same frozen scope.
    deep = client.post(f'/api/v2/projects/{pid}/conversations/{conversation}/messages',
                       headers={'Idempotency-Key': 'ask-deepen'},
                       json={'text': payload['question'], 'tool': 'research', 'scope': payload['scope'],
                             'provider_mode': 'demo', 'methods': ['situating.v1']})
    assert deep.status_code == 202, deep.text
    run_one(research, deep.json()['id'])
    with research.engine.connect() as c:
        run = rows(c, db.research_runs, db.research_runs.c.project_id == pid)[-1]
    expected = [{'segment_id': w['segment_id'], 'asset_id': w['asset_id'], 'version_id': w['version_id'],
                 'start': w['start_codepoint'], 'end': w['end_codepoint']} for w in payload['scope']]
    assert run['scope'] == expected
