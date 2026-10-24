# ruff: noqa: F811
import json
from types import SimpleNamespace
import pytest
from test_research_integration import research, client, imported  # noqa: F401
from hermeneut.research import schema as db
from hermeneut.research.citations import align
from hermeneut.research.service import row, rows, ResearchError
from hermeneut.research.worker import run_one


def fake_model(monkeypatch, result, usage=123):
    def create(**kwargs):
        value = result(kwargs) if callable(result) else result
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)), finish_reason='stop')],
                               usage=SimpleNamespace(model_dump=lambda: {'total_tokens': usage}))
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only')
    monkeypatch.setattr('hermeneut.llm.QwenProvider', lambda **kwargs: SimpleNamespace(model='test-qwen', temperature=0,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))


def test_exact_quote_alignment_unicode_repetition_and_context():
    assert align('甲😀e\u0301乙', '😀e\u0301', 999, 1000) == (1, 4, 'unique_exact_quote')
    with pytest.raises(ResearchError, match='AMBIGUOUS'):
        align('甲自由乙自由丙', '自由')
    assert align('甲自由乙自由丙', '自由', prefix='乙')[0] == 4
    with pytest.raises(ResearchError, match='NOT_FOUND'):
        align('e\u0301', 'é')


def test_live_citation_corrected_and_usage_survives_validation_failure(research, client, monkeypatch):
    pid, _aid, segments = imported(research, '自由需要物质条件。')
    citation = {'segment_id': segments[0]['id'], 'start_codepoint': 999, 'end_codepoint': 1000, 'exact_quote': '自由'}
    fake_model(monkeypatch, {'summary': '有限解释', 'outcome': 'context_candidate',
        'findings': [{'title': '引文', 'text': '自由', 'claim_type': 'quotation', 'citations': [citation]}]})
    root = f'/api/v2/projects/{pid}'
    j = client.post(root + '/method-runs', headers={'Idempotency-Key': 'correct'}, json={
        'method_id': 'situating.v1', 'question': '问题', 'segment_ids': [segments[0]['id']]}).json()
    run_one(research, j['id'])
    with research.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == j['id'])
        assert job['state'] == 'succeeded', job
        result = row(c, db.records, db.records.c.id == job['result']['record_id'])
        assert result['payload']['citation_alignment'][0]['basis'] == 'unique_exact_quote'
    citation['exact_quote'] = '不存在的引文'
    j = client.post(root + '/method-runs', headers={'Idempotency-Key': 'bad'}, json={
        'method_id': 'situating.v1', 'question': '问题', 'segment_ids': [segments[0]['id']]}).json()
    run_one(research, j['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == j['id'])['state'] == 'awaiting_input'
        assert len(rows(c, db.model_calls, db.model_calls.c.job_id == j['id'])) == 2
    assert client.get(root + '/model-calls').json()['totals']['used_tokens'] == 369
    draft = client.get(root + '/citation-drafts').json()[0]
    resolved = client.post(root + f'/citation-drafts/{draft["id"]}/resolve', json={'revision': draft['revision'],
        'bindings': [{'index': 0, 'segment_id': segments[0]['id'], 'version_id': segments[0]['version_id'],
                      'start_codepoint': 0, 'end_codepoint': 2}]})
    assert resolved.status_code == 200, resolved.text
    monkeypatch.delenv('DASHSCOPE_API_KEY')
    run_one(research, j['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == j['id'])['state'] == 'succeeded'
        assert len(rows(c, db.model_calls, db.model_calls.c.job_id == j['id'])) == 2


def test_scope_is_frozen_and_editor_has_version_checks(research, client):
    pid, aid, segments = imported(research, '甲😀乙。\n\n另一段内容。')
    root = f'/api/v2/projects/{pid}'
    cid = client.post(root + '/conversations', json={}).json()['id']
    scope = [{'asset_id': aid, 'version_id': segments[0]['version_id'], 'segment_id': segments[0]['id'],
              'start_codepoint': 1, 'end_codepoint': 2, 'exact_quote': '😀'}]
    endpoint = root + f'/conversations/{cid}/messages'
    assert client.post(endpoint, headers={'Idempotency-Key': 'mixed'}, json={
        'text': 'Q', 'scope': scope, 'asset_ids': [aid]}).status_code == 422
    j = client.post(endpoint, headers={'Idempotency-Key': 'scope'}, json={
        'text': 'Q', 'scope': scope, 'provider_mode': 'demo'}).json()
    assert j['payload']['scope_snapshot'][0]['end'] == 2
    assert len(j['payload']['scope_snapshot']) == 1
    run_one(research, j['id'])
    snap = client.get(root + f'/conversations/{cid}/snapshot').json()
    assert len(snap['messages']) == 2 and snap['cursor'] > 0
    with research.engine.connect() as c:
        events = rows(c, db.conversation_events, db.conversation_events.c.conversation_id == cid)
        assert len({e['sequence'] for e in events}) == len(events)
    doc = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': '文稿'}]}]}
    r = client.post(root + '/records', json={'kind': 'manuscript', 'payload': {'title': '稿', 'editor_json': doc}}).json()
    assert r['payload']['text'].strip() == '文稿'
    endpoint = root + f'/artifacts/{r["id"]}/chapters/c1'
    chapter = client.put(endpoint, json={'payload': {'editor_json': doc}})
    assert chapter.status_code == 200, chapter.text
    assert client.put(endpoint, json={'revision': 99, 'payload': {'editor_json': doc}}).status_code == 409


def test_editor_rejects_executable_content(research, client):
    pid = research.create_project('tester', 'P')['id']
    r = client.post(f'/api/v2/projects/{pid}/records', json={'kind': 'manuscript', 'payload': {
        'editor_json': {'type': 'doc', 'content': [{'type': 'script', 'text': 'bad'}]}}})
    assert r.status_code == 422


def test_editor_citations_cannot_cross_projects_and_chapters_export(research, client):
    pid, _aid, segments = imported(research, '引用来源。')
    with research.engine.begin() as c:
        anchor = research.make_anchor(c, pid, segments[0]['id'], 0, 2, '引用')
    doc = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
        {'type': 'citation', 'attrs': {'anchorId': anchor['id']}}]}]}
    other = research.create_project('tester', 'other')['id']
    assert client.post(f'/api/v2/projects/{other}/records', json={
        'kind': 'manuscript', 'payload': {'editor_json': doc}}).status_code == 422
    root = f'/api/v2/projects/{pid}'
    record = client.post(root + '/records', json={'kind': 'manuscript', 'payload': {'text': '旧稿'}}).json()
    ch = client.put(root + f"/artifacts/{record['id']}/chapters/one", json={'payload': {
        'title': '第一章', 'editor_json': doc}})
    assert ch.status_code == 200, ch.text
    assert anchor['id'] in client.get(root + '/export').text
    assert client.get(root + '/export?format=json').json()['chapters'][0]['payload']['text']


def test_unknown_usage_is_held_and_snapshot_recovers_partial_text(research, client, monkeypatch):
    from hermeneut.research.events import emit
    pid, _aid, segments = imported(research, '原文。')
    root = f'/api/v2/projects/{pid}'
    cid = client.post(root + '/conversations', json={}).json()['id']
    j = client.post(root + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'partial'},
        json={'text': '问题', 'provider_mode': 'live'}).json()
    with research.engine.begin() as c:
        emit(c, pid, cid, 'message.delta', {'job_id': j['id'], 'text': '已生成但尚未完成', 'draft': True})
    snap = client.get(root + f'/conversations/{cid}/snapshot').json()
    assert snap['drafts'][j['id']] == '已生成但尚未完成'
    fake_model(monkeypatch, {})
    def failing(**kwargs):
        raise TimeoutError('transport lost')
    monkeypatch.setattr('hermeneut.llm.QwenProvider', lambda **kwargs: SimpleNamespace(model='test', temperature=0,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=failing)))))
    job = client.post(root + '/method-runs', headers={'Idempotency-Key': 'unknown'}, json={
        'method_id': 'situating.v1', 'question': '问题', 'segment_ids': [segments[0]['id']]}).json()
    run_one(research, job['id'])
    with research.engine.connect() as c:
        call = rows(c, db.model_calls, db.model_calls.c.job_id == job['id'])[0]
        assert call['state'] == 'unknown' and call['usage'] is None and call['reserved_tokens'] > 0
        assert not rows(c, db.records, db.records.c.project_id == pid)
