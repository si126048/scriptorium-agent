# ruff: noqa: F811
import pytest
from test_research_integration import research, client  # noqa: F401
from test_automatic_research import send
from scriptorium.research import schema as db, timeline, collection, automatic
from scriptorium.research.service import row, rows, ResearchError
from scriptorium.research.worker import run_one


def seeded_run(s, client, mode='auto'):
    pid, cid, job = send(s, client, network_mode='off', review_mode=mode, provider_mode='demo')
    imported = s.import_material(pid, 'tester', '自由需要制度条件。'.encode(), 'scope.txt', db.uid())
    assert run_one(s, imported['id'])
    with s.engine.connect() as c:
        segment = rows(c, db.segments, db.segments.c.asset_id == imported['payload']['asset_id'])[0]
    window = {'asset_id': segment['asset_id'], 'version_id': segment['version_id'],
              'segment_id': segment['id'], 'start': 0, 'end': len(segment['text'])}
    rid = db.uid()
    with s.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
            payload={**job['payload'], 'scope_snapshot': [window]}))
        c.execute(db.research_runs.insert().values(id=rid, project_id=pid, conversation_id=cid,
            question='研究自由的制度条件', state='running', scope=[window],
            settings={'origin_job_id': job['id'], 'token_budget': 100, 'review_mode': mode,
                      'provider_mode': 'demo', 'max_nodes': 6, 'max_rounds': 2,
                      'nodes': ['final_answer'], 'writer_reservation': 6000},
            used_tokens=0, reserved_tokens=0, created_at=db.now()))
        c.execute(db.research_steps.insert().values(id=db.uid(), run_id=rid, step_key='root/00000/0',
            state='queued', payload={'window': window, 'windows': [window],
                                    'method_id': 'situating.v1', 'round': 0}, created_at=db.now()))
    return pid, cid, job, rid


def test_worker_auto_budget_partial_and_continue_same_turn(research, client):
    pid, _cid, submitted, rid = seeded_run(research, client)
    assert run_one(research, submitted['id'])
    root = f'/api/v2/projects/{pid}'
    task = client.get(root + '/research-tasks/' + submitted['id']).json()
    assert task['state'] == 'partial'
    assert task['blocks'][-1]['state'] != 'waiting'
    with research.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == submitted['id'])
        assert job['state'] == 'succeeded' and job['result']['state'] == 'partial_completed'
        assert row(c, db.research_runs, db.research_runs.c.id == rid)['state'] == 'partial_completed'
        assert not rows(c, db.decisions, db.decisions.c.run_id == rid)
    before_ids = {b['id'] for b in task['blocks']}
    intake = client.get(root + '/intakes').json()[0]
    assert intake['state'] == 'completed' and intake['decision'] == 'AUTO_BUDGET_PARTIAL'
    response = client.post(root + f'/intakes/{submitted["id"]}/decisions',
                           json={'revision': intake['revision'], 'action': 'continue'})
    assert response.status_code == 200, response.text
    # Replaying the same revision must not add another 40k or duplicate work.
    assert client.post(root + f'/intakes/{submitted["id"]}/decisions',
                       json={'revision': intake['revision'], 'action': 'continue'}).status_code == 409
    assert run_one(research, submitted['id'])
    resumed = client.get(root + '/research-tasks/' + submitted['id']).json()
    assert resumed['state'] == 'completed'
    assert before_ids <= {b['id'] for b in resumed['blocks']}
    assert resumed['generation'] > task['generation']
    with research.engine.connect() as c:
        assert row(c, db.research_runs, db.research_runs.c.id == rid)['settings']['token_budget'] == 40100
        reports = [r for r in rows(c, db.records, db.records.c.project_id == pid)
                   if r['kind'] == 'manuscript']
        assert len(reports) == 1
        assert not rows(c, db.model_calls, db.model_calls.c.project_id == pid)


def test_review_budget_still_waits_for_explicit_decision(research, client):
    pid, _cid, submitted, rid = seeded_run(research, client, 'review')
    assert run_one(research, submitted['id'])
    task = client.get(f'/api/v2/projects/{pid}/research-tasks/{submitted["id"]}').json()
    assert task['state'] == 'waiting'
    with research.engine.connect() as c:
        decisions = rows(c, db.decisions, db.decisions.c.run_id == rid)
        assert len(decisions) == 1 and decisions[0]['kind'] == 'budget'


def test_review_mode_reaches_the_method_worker(research, client):
    pid, _cid, submitted, rid = seeded_run(research, client, 'review')
    with research.engine.begin() as c:
        run = row(c, db.research_runs, db.research_runs.c.id == rid)
        c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(
            settings={**run['settings'], 'token_budget': 40000}))
    assert run_one(research, submitted['id'])
    with research.engine.connect() as c:
        children = [j for j in rows(c, db.jobs, db.jobs.c.project_id == pid) if j['kind'] == 'method']
        assert children and all(j['payload']['review_mode'] == 'review' for j in children)


def test_partial_commit_is_atomic_and_fenced(research, client, monkeypatch):
    _pid, _cid, submitted, rid = seeded_run(research, client)
    job = research.claim_job(submitted['id'])
    timeline.start(research, job)
    collection.ensure_intake(research, job)
    def fail(*args, **kwargs):
        raise RuntimeError('timeline write interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(timeline, 'put', fail)
        with pytest.raises(RuntimeError, match='timeline write interrupted'):
            automatic.budget_partial(research, job)
    with research.engine.connect() as c:
        assert row(c, db.research_runs, db.research_runs.c.id == rid)['state'] == 'running'
        assert row(c, db.intakes, db.intakes.c.job_id == job['id'])['state'] == 'planning'
        assert not rows(c, db.messages, db.messages.c.role == 'assistant')
    with research.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(lease_until=0))
    with pytest.raises(ResearchError, match='JOB_NO_LONGER_OWNED'):
        automatic.budget_partial(research, job)
