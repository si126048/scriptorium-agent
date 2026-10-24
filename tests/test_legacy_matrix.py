# ruff: noqa: F811
"""Legacy capability matrix: the old workflows must run on the unified project store.

These cover OLD-01…OLD-06 at the API level: interview state, single/dialectical perspective
analysis, subject-analysis consent, persona training/withdrawal, historical review/export and the
v1 compatibility surface. Demo providers are used explicitly; no claim is made about model quality.
"""
from __future__ import annotations

from test_research_integration import research, client, imported  # noqa: F401
from scriptorium.research import schema as db
from scriptorium.research.service import row, rows
from scriptorium.research.worker import run_one


def project_with_material(research, client, text='自由需要物质条件。'):
    pid, aid, segments = imported(research, text)
    conv = client.post(f'/api/v2/projects/{pid}/conversations', json={'title': '旧业务矩阵'}).json()
    return f'/api/v2/projects/{pid}', pid, conv['id'], aid, segments


def consenting_participant(client, path, **permissions):
    payload = {'pseudonym': '甲', 'material_collection': True, 'profile_analysis': True,
               'agent_simulation': True, **permissions}
    response = client.post(path + '/participants', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_old01_interview_state_survives_and_material_is_linked(research, client):
    path, _pid, cid, _aid, _segments = project_with_material(research, client)
    person = consenting_participant(client, path)
    created = client.post(path + '/interviews', json={'participant_id': person['id'],
        'conversation_id': cid, 'provider_mode': 'demo'})
    assert created.status_code == 201, created.text
    iid = created.json()['id']
    assert client.post(path + f'/interviews/{iid}/pause').json()['state'] in {'PAUSED', 'Paused', 'paused'}
    # State is read back from storage, not from process memory.
    assert client.get(path + f'/interviews/{iid}').json()['state'].upper() == 'PAUSED'
    assert client.post(path + f'/interviews/{iid}/resume').status_code == 200
    for _ in range(12):
        current = client.get(path + f'/interviews/{iid}').json()
        if not current.get('current_question'):
            break
        answer = client.post(path + f'/interviews/{iid}/turns', json={
            'question_id': current['current_question']['id'], 'answer_text': '回答内容'})
        assert answer.status_code == 200, answer.text
    finished = client.post(path + f'/interviews/{iid}/complete')
    assert finished.status_code == 200, finished.text
    run_one(research, finished.json()['job_id'])
    # A repeated completion must reuse the existing import job instead of importing twice.
    assert client.post(path + f'/interviews/{iid}/complete').json()['job_id'] == finished.json()['job_id']
    materials = client.get(path + '/materials').json()
    assert len([m for m in materials if m['metadata'].get('interview_id') == iid]) == 1


def test_old02_single_and_dialectical_perspectives_are_saved(research, client):
    path, _pid, cid, aid, _segments = project_with_material(research, client, '制度要求说明理由，却禁止申辩。')
    single = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'one-view'},
        json={'text': '单视角分析', 'tool': 'theory', 'asset_ids': [aid], 'provider_mode': 'demo',
              'perspective_ids': ['lacan']})
    assert single.status_code == 202, single.text
    run_one(research, single.json()['id'])
    dialectical = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'two-views'},
        json={'text': '辩证分析', 'tool': 'theory', 'asset_ids': [aid], 'provider_mode': 'demo',
              'perspective_ids': ['lacan', 'deleuze']})
    assert dialectical.status_code == 202, dialectical.text
    run_one(research, dialectical.json()['id'])
    with research.engine.connect() as c:
        for job_id in (single.json()['id'], dialectical.json()['id']):
            assert row(c, db.jobs, db.jobs.c.id == job_id)['state'] == 'succeeded'
    records = [r for r in client.get(path + '/records').json() if r['kind'] == 'method_report']
    assert len(records) == 2
    assert all(r['payload']['provider_mode'] == 'demo' for r in records)
    # The dialectical path keeps its own phase structure rather than reusing the single-view packet.
    dialectical_record = next(r for r in records if 'phase1_analyses' in (r['payload'].get('legacy_result') or {}))
    assert dialectical_record['payload']['legacy_result']['phase1_analyses']


def test_old03_subject_analysis_requires_participant_authorization(research, client):
    path, _pid, cid, aid, _segments = project_with_material(research, client, '我总是先道歉再表达。')
    no_profile = consenting_participant(client, path, profile_analysis=False)
    refused = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'subject-refused'},
        json={'text': '做主体分析', 'tool': 'subject', 'participant_id': no_profile['id'],
              'asset_ids': [aid], 'provider_mode': 'demo'})
    assert refused.status_code == 403 and refused.json()['detail'] == 'PARTICIPANT_CONSENT_REQUIRED'
    allowed = consenting_participant(client, path, pseudonym='乙')
    # Material must belong to the analyzed participant before the profile can use it.
    assert client.post(path + f'/participants/{allowed["id"]}/materials',
                       json={'asset_ids': [aid]}).status_code == 200
    accepted = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'subject-ok'},
        json={'text': '做主体分析', 'tool': 'subject', 'participant_id': allowed['id'],
              'asset_ids': [aid], 'provider_mode': 'demo'})
    assert accepted.status_code == 202, accepted.text
    run_one(research, accepted.json()['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == accepted.json()['id'])['state'] == 'succeeded'


def test_old04_persona_withdrawal_blocks_late_work(research, client, monkeypatch):
    import numpy as np
    import scriptorium.topostyle.provider as module
    import scriptorium.topostyle.service as training

    class LocalTestModel:
        def __init__(self, **kwargs):
            pass

        def embed(self, texts):
            return np.arange(len(texts) * 8).reshape(len(texts), 8).tolist()

        def generate_structured(self, *args):
            return {'core': '学习', 'expression': '解释', 'evidence': '自由'}

        def generate(self, messages):
            return '模拟表达，仅供测试'

    monkeypatch.setattr(module, 'OllamaProvider', LocalTestModel)
    monkeypatch.setattr(training, 'OllamaProvider', LocalTestModel)
    path, _pid, cid, aid, _segments = project_with_material(research, client)
    person = consenting_participant(client, path)
    assert client.post(path + f'/participants/{person["id"]}/materials',
                       json={'asset_ids': [aid]}).status_code == 200
    persona = client.post(path + '/personas', json={'participant_id': person['id'], 'name': '模拟甲'}).json()
    job = client.post(path + f'/personas/{persona["id"]}/train').json()
    run_one(research, job['id'])
    conversation = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'persona-1'},
        json={'tool': 'persona', 'persona_id': persona['id'], 'text': '请回应'}).json()
    run_one(research, conversation['id'])
    # Withdrawal must block a *new* reply before it is produced, not only hide history.
    assert client.post(path + f'/participants/{person["id"]}/withdraw').status_code == 200
    late = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'persona-2'},
        json={'tool': 'persona', 'persona_id': persona['id'], 'text': '继续'})
    assert late.status_code in {403, 404}, late.text
    assert client.get(path + '/personas').json() == []


def test_old05_historical_artifact_review_export_and_reimport(research, client):
    path, pid, _cid, aid, _segments = project_with_material(research, client, '原文引用应当可以定位。')
    person = consenting_participant(client, path)
    assert client.post(path + f'/participants/{person["id"]}/materials',
                       json={'asset_ids': [aid]}).status_code == 200
    created = client.post('/api/v1/analysis-runs', json={'project_id': pid, 'participant_id': person['id'],
        'source_ids': [aid], 'idempotency_key': 'legacy-run-1', 'provider_mode': 'demo'})
    assert created.status_code == 202, created.text
    run_id = created.json()['run_id']
    artifact = client.post(path + f'/analysis-runs/{run_id}/artifact')
    assert artifact.status_code == 201, artifact.text
    record = artifact.json()
    assert record['payload']['legacy_run_id'] == run_id
    # The historical result is transcribed with its original business state, never regenerated.
    original = client.get(f'/api/v1/analysis-runs/{run_id}').json()
    assert record['payload']['status'] == original['state']
    assert client.post(path + f'/analysis-runs/{run_id}/reviews',
                       json={'decision': 'approve', 'reason': '验收复核'}).status_code == 200
    exported = client.get(path + f'/analysis-runs/{run_id}/export')
    assert exported.status_code == 200 and exported.json()['graph'] is not None
    history = {'format': 'scriptorium-browser-history.v1', 'tasks': [
        {'id': 'legacy-task', 'name': '旧会话', 'messages': [{'role': 'user', 'content': '旧消息'}]}]}
    first = client.post(path + '/history-import', json=history)
    second = client.post(path + '/history-import', json=history)
    # Re-importing the same snapshot is idempotent: it must not duplicate tasks or messages.
    assert first.json()['imported'] == 1 and second.json()['imported'] == 0
    with research.engine.connect() as c:
        legacy = rows(c, db.legacy, db.legacy.c.project_id == pid, db.legacy.c.table_name == 'browser_tasks')
    assert len(legacy) == 1


def test_old06_v1_and_v2_share_project_state(research, client):
    project = client.post('/api/v1/projects', json={'name': '兼容项目'}).json()
    pid = project['id']
    listed = {p['id'] for p in client.get('/api/v2/projects').json()}
    assert pid in listed
    upload = client.post('/api/v1/theory/sources', data={'project_id': pid},
                         files={'file': ('theory.md', '理论文本可用于比较。'.encode(), 'text/markdown')})
    assert upload.status_code == 202, upload.text
    run_one(research, upload.json()['id'])
    materials = client.get(f'/api/v2/projects/{pid}/materials').json()
    assert len(materials) == 1 and materials[0]['metadata']['purpose'] == 'theory'
    # v1 chat must never guess a project from a hidden default.
    assert client.post('/api/v1/chat/analyze', json={'text': '没有项目'}).status_code == 422
    perspectives = client.get('/api/v1/perspectives').json()['perspectives']
    assert {p['id'] for p in perspectives} >= {'lacan', 'deleuze'}
