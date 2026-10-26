# ruff: noqa: F811, RUF059, SIM117
from unittest.mock import Mock
import pytest
from test_research_integration import research,client,imported  # noqa: F401
from test_automatic_research import send
from scriptorium.research import schema as db,timeline,collection,automatic,open_sources
from scriptorium.research.service import row,rows,ResearchError
from scriptorium.research.final_writer import document


def test_expired_owner_cannot_finish_or_append(research,client):
    pid,cid,submitted=send(research,client,'你好');old=research.claim_job(submitted['id']);timeline.start(research,old)
    with research.engine.begin() as c:c.execute(db.jobs.update().where(db.jobs.c.id==old['id']).values(lease_until=0))
    new=research.claim_job(old['id']);timeline.start(research,new)
    with pytest.raises(ResearchError,match='JOB_NO_LONGER_OWNED'):
        with research.engine.begin() as c:research.finish(c,old,{'text':'stale'})
    with pytest.raises(ResearchError,match='JOB_NO_LONGER_OWNED'):timeline.append(research,old,'answer','stale')
    with pytest.raises(ResearchError,match='JOB_NO_LONGER_OWNED'):research.heartbeat(old)
    research.fail(old,ResearchError('STALE'))
    with research.engine.connect() as c:assert row(c,db.jobs,db.jobs.c.id==new['id'])['state']=='running'


def test_unicode_delta_snapshot_and_completion_are_one_block(research,client):
    pid,cid,submitted=send(research,client,'你好');job=research.claim_job(submitted['id']);timeline.start(research,job)
    timeline.append(research,job,'answer','甲😀e\u0301');timeline.append(research,job,'answer','乙')
    snapshot=client.get(f'/api/v2/projects/{pid}/conversations/{cid}/snapshot').json()
    answer=next(b for b in snapshot['blocks'] if b['block_key']=='answer');assert answer['payload']['text']=='甲😀e\u0301乙'
    with research.engine.connect() as c:
        events=rows(c,db.conversation_events,db.conversation_events.c.type=='timeline.block')
        deltas=[e['payload']['delta'] for e in events if 'delta' in e['payload']]
        assert deltas[-1]['offset']==4
    with research.engine.begin() as c:research.finish(c,job,{'text':'甲😀e\u0301乙'})
    task=client.get(f'/api/v2/projects/{pid}/research-tasks/{job["id"]}').json()
    assert task['state']=='completed'
    assert len([b for b in task['blocks'] if b['block_key']=='answer'])==1
    assert next(b for b in task['blocks'] if b['block_key']=='answer')['id']==answer['id']


def test_waiting_is_successful_execution_and_resume_keeps_identity(research,client):
    pid,cid,submitted=send(research,client);job=research.claim_job(submitted['id']);timeline.start(research,job);collection.ensure_intake(research,job)
    automatic.pause(research,job,'NO_READABLE_SOURCES')
    task=client.get(f'/api/v2/projects/{pid}/research-tasks/{job["id"]}').json();assert task['state']=='waiting'
    with research.engine.connect() as c:assert row(c,db.jobs,db.jobs.c.id==job['id'])['state']=='succeeded'
    intake=client.get(f'/api/v2/projects/{pid}/intakes').json()[0]
    response=client.post(f'/api/v2/projects/{pid}/intakes/{job["id"]}/decisions',json={'revision':intake['revision'],'action':'use_collected'})
    assert response.status_code==200
    resumed=research.claim_job(job['id']);timeline.start(research,resumed)
    next_task=client.get(f'/api/v2/projects/{pid}/research-tasks/{job["id"]}').json()
    assert next_task['generation']>task['generation']
    assert {b['id'] for b in next_task['blocks']}=={b['id'] for b in task['blocks']}


def test_two_locations_keep_restriction_and_use_public_alternative(research,client,monkeypatch):
    pid,cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    sid=collection.register(research,job,{'url':'https://example.org/publisher','title':'Alternative',
        'locations':['https://example.org/restricted','https://example.org/open']})
    text=('<article><p>'+('公开的替代版本提供可读取的研究文本。'*20)+'</p></article>').encode()
    def fetch(url,*args):
        if 'restricted' in url:raise ResearchError('SOURCE_ACCESS_RESTRICTED',403)
        return text,'text/html',url
    mocked=Mock(side_effect=fetch);monkeypatch.setattr(collection,'fetch',mocked)
    collection.acquire(research,job,sid)
    source=client.get(f'/api/v2/projects/{pid}/sources/{sid}?job_id={job["id"]}').json()
    assert source['availability']=='fulltext'
    assert len(source['attempts'])==2 and source['attempts'][0]['availability']=='restricted'
    collection.acquire(research,job,sid);assert mocked.call_count==2


def test_open_metadata_cache_and_auth_failure_are_bounded(research,client,monkeypatch):
    import httpx
    pid,cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    real=httpx.Client;calls=[]
    def respond(req):
        calls.append(str(req.url))
        if req.url.host=='api.openalex.org':return httpx.Response(401)
        return httpx.Response(200,json={'message':{'items':[{'DOI':'10.1234/test','title':['Example work'],'URL':'https://doi.org/10.1234/test'}]}})
    monkeypatch.setattr(open_sources.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(respond)))
    assert len(open_sources.request(research,job,'crossref','q'))==1
    assert len(open_sources.request(research,job,'crossref','q'))==1
    assert open_sources.request(research,job,'openalex','q')==[]
    assert len(calls)==2


def test_middle_text_can_be_selected_and_unknown_writer_refs_rejected(research,client):
    pid,aid,segments=imported(research,'开篇材料。'*1100+'独特的制度裂隙证据。'*150+'结尾材料。'*1100)
    root=f'/api/v2/projects/{pid}';cid=client.post(root+'/conversations',json={}).json()['id']
    submitted=client.post(root+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'middle'},json={'text':'研究独特的制度裂隙证据','tool':'auto','provider_mode':'demo'}).json()
    job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    scope=automatic.automatic_scope(research,job,automatic.windows(segments))
    assert any(w['start']>=4000 for w in scope)
    with pytest.raises(ResearchError,match='CITATION_INVALID'):document('错误 [[source:invented]]',[])
    assert document('正确 [[source:a]]',['a'])['evidence_ids']==['a']


def test_revocation_redacts_streamed_private_material(research,client):
    pid,aid,segments=imported(research,'不应在撤回后保留的私人材料。')
    root=f'/api/v2/projects/{pid}';cid=client.post(root+'/conversations',json={}).json()['id']
    submitted=client.post(root+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'private'},json={'text':'研究这份材料','tool':'auto','asset_ids':[aid]}).json()
    job=research.claim_job(submitted['id']);timeline.start(research,job);timeline.append(research,job,'answer','私人材料中的秘密摘录')
    research.revoke(pid,'tester',aid)
    snapshot=client.get(root+f'/conversations/{cid}/snapshot').json()
    assert '秘密摘录' not in str(snapshot['blocks'])
    with research.engine.connect() as c:
        events=rows(c,db.conversation_events,db.conversation_events.c.conversation_id==cid)
        assert '秘密摘录' not in str(events)


def test_lost_owned_lease_requeues_instead_of_creating_false_failure(research,client):
    pid,cid,submitted=send(research,client,'你好');job=research.claim_job(submitted['id'])
    research.fail(job,ResearchError('JOB_NO_LONGER_OWNED'))
    with research.engine.connect() as c:
        current=row(c,db.jobs,db.jobs.c.id==job['id'])
        assert current['state']=='queued' and current['error'] is None and current['lease_token'] is None


def test_old_waiting_result_cannot_override_failed_or_requeued_state(research,client):
    pid,cid,submitted=send(research,client);job=research.claim_job(submitted['id']);timeline.start(research,job);collection.ensure_intake(research,job)
    automatic.pause(research,job,'NO_READABLE_SOURCES')
    with research.engine.begin() as c:c.execute(db.jobs.update().where(db.jobs.c.id==job['id']).values(state='failed',error='JOB_NO_LONGER_OWNED'))
    root=f'/api/v2/projects/{pid}'
    assert client.get(root+'/intakes').json()[0]['state']=='failed'
    assert client.post(root+'/jobs/'+job['id']+'/retry').status_code==200
    assert client.get(root+'/intakes').json()[0]['state']=='planning'


@pytest.mark.parametrize('accept',[True,False])
def test_budget_decision_stays_in_original_turn(research,client,accept):
    pid,aid,segments=imported(research,'用于预算恢复检查的原文。'*450)
    root=f'/api/v2/projects/{pid}';cid=client.post(root+'/conversations',json={}).json()['id']
    submitted=client.post(root+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'budget-turn'},json={'text':'研究这份原文','tool':'research','asset_ids':[aid],'token_budget':10000,'provider_mode':'demo','methods':['situating.v1']}).json()
    from scriptorium.research.worker import run_one
    run_one(research,submitted['id'])
    decision=client.get(root+'/decisions').json()[0]
    response=client.post(root+'/decisions/'+decision['id'],json={'accept':accept,'additional_tokens':100000})
    assert response.status_code==200,response.text
    if accept:
        assert response.json()['id']==submitted['id'];run_one(research,submitted['id'])
    task=client.get(root+'/research-tasks/'+submitted['id']).json()
    assert task['state']==('completed' if accept else 'partial'),task
    with research.engine.connect() as c:
        assert len(rows(c,db.jobs,db.jobs.c.project_id==pid,db.jobs.c.kind=='workspace'))==1
