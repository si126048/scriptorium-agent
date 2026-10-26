# ruff: noqa: F811
import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_research_integration import research, client, imported  # noqa: F401
from test_research_experience import fake_model
from scriptorium.research import schema as db
from scriptorium.research.service import row, rows, ResearchError
from scriptorium.research.worker import run_one
from scriptorium.research import native_search, collection, automatic
from scriptorium.research.public_fetch import normalized_url, public_addresses, readable_html


@pytest.fixture(autouse=True)
def no_external_metadata(monkeypatch):
    monkeypatch.setattr('scriptorium.research.open_sources.discover',lambda *args:[])


def send(s,c,text='研究自由的制度条件',**extra):
    pid=s.create_project('tester','Auto')['id'];root=f'/api/v2/projects/{pid}'
    cid=c.post(root+'/conversations',json={}).json()['id']
    response=c.post(root+f'/conversations/{cid}/messages',json={'text':text,'tool':'auto',**extra},headers={'Idempotency-Key':'once'})
    assert response.status_code==202,response.text
    return pid,cid,response.json()


def test_greeting_and_help_need_no_material_or_provider(research,client,monkeypatch):
    forbidden=Mock(side_effect=AssertionError('No network for greeting'))
    monkeypatch.setattr(native_search,'discover',forbidden)
    pid,cid,job=send(research,client,'你好');run_one(research,job['id'])
    messages=client.get(f'/api/v2/projects/{pid}/conversations/{cid}/messages').json()
    assert len(messages)==2 and '你好' in messages[-1]['content']
    with research.engine.connect() as c:
        assert row(c,db.jobs,db.jobs.c.id==job['id'])['state']=='succeeded'
        assert rows(c,db.model_calls)==[]
    forbidden.assert_not_called()


def test_empty_project_collects_reads_and_reports_with_mocked_provider(research,client,monkeypatch):
    discover=Mock(return_value=[{'url':'https://example.org/article','title':'研究原文','provider':'qwen','provider_index':'1','snippet':'公开的简短摘要。'}])
    monkeypatch.setattr(native_search,'discover',discover)
    raw=('<html><title>研究原文</title><article><p>自由需要制度条件。'+('研究材料提供问题的背景与位置。'*8)+'</p></article></html>').encode()
    fetch=Mock(return_value=(raw,'text/html','https://example.org/article'));monkeypatch.setattr(collection,'fetch',fetch)
    def result(kwargs):
        user=json.loads(kwargs['messages'][-1]['content']);segment=user['materials'][0]
        return {'summary':'模拟解释','outcome':'context_candidate' if 'situating.v1' in kwargs['messages'][0]['content'] else 'undetermined',
            'findings':[{'title':'文本依据','text':'材料陈述了条件。','claim_type':'quotation','citations':[{'segment_id':segment['segment_id'],'exact_quote':'自由需要制度条件。'}]}]}
    fake_model(monkeypatch,result)
    pid,_cid,job=send(research,client,methods=['situating.v1']);assert run_one(research,job['id'])
    root=f'/api/v2/projects/{pid}'
    with research.engine.connect() as c:
        value=row(c,db.jobs,db.jobs.c.id==job['id']);assert value['state']=='succeeded',(value.get('error'),value.get('result'))
        assert value['result'].get('record_id'),value
    sources=client.get(root+'/sources').json()['items'];assert len(sources)==1 and sources[0]['availability']=='fulltext'
    assert sources[0]['read'] and sources[0]['used_in_report']
    assert client.get(root+'/materials/'+sources[0]['asset_id']+'/original').content==raw
    assert client.get(root+'/intakes').json()[0]['state']=='completed'
    assert client.post(root+'/sources/'+sources[0]['id']+'/actions',headers={'Idempotency-Key':'adopt'},json={
        'job_id':job['id'],'revision':sources[0]['revision'],'action':'adopt'}).status_code==200
    fetch.assert_called_once();discover.assert_called_once()
    assert not run_one(research,job['id'])
    aid=sources[0]['asset_id'];research.revoke(pid,'tester',aid)
    assert client.get(root+'/sources',params={'availability':'withdrawn'}).json()['items'][0]['availability']=='withdrawn'
    assert client.get(root+'/sources/'+sources[0]['id']+'/snapshot',params={'job_id':job['id']}).status_code==404


def test_unsupported_network_pauses_and_can_end(research,client,monkeypatch):
    monkeypatch.setattr(native_search,'discover',Mock(side_effect=ResearchError('NATIVE_SEARCH_UNSUPPORTED',422)))
    pid,_cid,job=send(research,client);run_one(research,job['id']);root=f'/api/v2/projects/{pid}'
    intake=client.get(root+'/intakes').json()[0];assert intake['state']=='awaiting_input'
    assert client.post(root+'/intakes/'+job['id']+'/decisions',json={'revision':intake['revision'],'action':'stop'}).status_code==200
    run_one(research,job['id']);assert client.get(root+'/intakes').json()[0]['state']=='completed'
    other=research.create_project('other','Private')['id']
    assert client.get(f'/api/v2/projects/{other}/sources').status_code==404


def test_explicit_scope_never_uses_web(research,client,monkeypatch):
    pid,aid,_segments=imported(research)
    root=f'/api/v2/projects/{pid}';cid=client.post(root+'/conversations',json={}).json()['id']
    spy=Mock(side_effect=AssertionError('No web for explicit scope'));monkeypatch.setattr(native_search,'discover',spy)
    job=client.post(root+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'scope'},json={
        'text':'仅根据这些材料研究自由','tool':'auto','provider_mode':'demo','asset_ids':[aid],'methods':['situating.v1']}).json()
    run_one(research,job['id']);spy.assert_not_called()
    assert client.get(root+'/intakes').json()[0]['state']=='completed'


def test_native_discovery_accounts_usage_even_without_sources(research,client,monkeypatch):
    _pid,_cid,submitted=send(research,client)
    job=research.claim_job(submitted['id'])
    cfg={'id':'qwen','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','model':'qwen-plus','ready':True}
    monkeypatch.setattr(native_search,'provider_config',lambda:cfg)
    monkeypatch.setattr(native_search,'key_for',lambda _: 'fake-key')
    payload={'usage':{'input_tokens':10,'output_tokens':5,'plugins':{'search':{'count':1}}},'output':{'search_info':{'search_results':[]}}}
    response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    transport=SimpleNamespace(post=Mock(return_value=response),__enter__=lambda self:self,__exit__=lambda *a:None)
    class Connection:
        def __enter__(self):return transport
        def __exit__(self,*args):return None
    monkeypatch.setattr(native_search.httpx,'Client',lambda **kw:Connection())
    assert native_search.discover(research,job,'问题')==[]
    with research.engine.connect() as c:
        assert rows(c,db.model_calls)[0]['usage']['total_tokens']==15
        assert rows(c,db.discovery_calls)[0]['state']=='returned'
    options=transport.post.call_args.kwargs['json']['parameters'];assert options['enable_search'] and options['search_options']['enable_source']
    assert not native_search.capabilities({**cfg,'base_url':'https://untrusted.example/v1'})['web_search']


def test_public_fetch_boundaries_and_html(monkeypatch):
    for url in ['file:///etc/passwd','https://user:pass@example.org/','http://example.org:55433/']:
        with pytest.raises((ResearchError,ValueError)):normalized_url(url)
    for address in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1','224.0.0.1']:
        monkeypatch.setattr(socket,'getaddrinfo',lambda *a,address=address,**kw:[(None,None,None,None,(address,80))])
        with pytest.raises(ResearchError,match='PRIVATE'):public_addresses('public.example',80)
    _,text=readable_html(('<html><script>stolen()</script><nav>menu</nav><article><p>'+('可读取的文本。'*20)+'</p></article></html>').encode())
    assert 'stolen' not in text and 'menu' not in text
    with pytest.raises(ResearchError,match='RESTRICTED'):readable_html(b'<html><input type="password"><p>Please login.</p></html>')
    with pytest.raises(ResearchError,match='RESTRICTED'):readable_html(b'<html><script type="application/ld+json">{"isAccessibleForFree":false}</script><article>Restricted text</article></html>')


def test_intent_router_does_not_treat_greetings_as_research():
    assert automatic.route('你好！')=='greeting'
    assert automatic.route('开始研究')=='clarify'
    assert automatic.route('比较两种关于自由的理论')=='research'
    assert automatic.route('What does freedom mean?')=='chat'
    assert automatic.route('帮我找自由概念的相关资料')=='research'


def test_download_checkpoint_retries_without_refetch_or_duplicate_material(research,client,monkeypatch):
    monkeypatch.setattr(native_search,'discover',Mock(return_value=[{'url':'https://example.org/cache','title':'Cache source'}]))
    raw=('<article><p>'+('可恢复的原文材料。'*20)+'</p></article>').encode()
    fetch=Mock(return_value=(raw,'text/html','https://example.org/cache'));monkeypatch.setattr(collection,'fetch',fetch)
    original=research.import_material
    monkeypatch.setattr(research,'import_material',Mock(side_effect=RuntimeError('simulated interruption before import')))
    pid,_cid,job=send(research,client);run_one(research,job['id']);root=f'/api/v2/projects/{pid}'
    source=client.get(root+'/sources').json()['items'][0];assert source['availability']=='failed'
    monkeypatch.setattr(research,'import_material',original)
    response=client.post(root+'/sources/'+source['id']+'/actions',headers={'Idempotency-Key':'recover'},json={
        'job_id':job['id'],'revision':source['revision'],'action':'fetch'})
    assert response.status_code==200,response.text
    retry=response.json();run_one(research,retry['id'])
    assert client.get(root+'/sources').json()['items'][0]['availability']=='fulltext'
    assert len(client.get(root+'/materials').json())==1
    fetch.assert_called_once()
    assert not run_one(research,retry['id'])


def test_candidate_limit_and_paged_source_search(research,client,monkeypatch):
    pid,cid,submitted=send(research,client);job=research.claim_job(submitted['id'])
    collection.ensure_intake(research,job)
    for i in range(5):collection.register(research,job,{'url':f'https://example.org/paper-{i}','title':f'Paper {i}'})
    root=f'/api/v2/projects/{pid}'
    page=client.get(root+'/sources',params={'limit':2,'conversation_id':cid}).json()
    assert len(page['items'])==2 and page['total']==5 and page['next_offset']==2
    found=client.get(root+'/sources',params={'q':'Paper 4'}).json();assert found['total']==1
    again=client.post(root+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'second-research'},json={'text':'继续研究资料','tool':'auto'}).json()
    newer=research.claim_job(again['id']);collection.ensure_intake(research,newer)
    collection.register(research,newer,{'url':'https://example.org/paper-0?utm_source=again','title':'Paper 0'})
    merged=client.get(root+'/sources').json();assert merged['total']==5
    assert len({item['id'] for item in merged['items']})==5
    with research.engine.begin() as c:
        current=row(c,db.intakes,db.intakes.c.job_id==job['id']);p={**current['payload'],'limits':{**current['payload']['limits'],'fulltexts':0}}
        c.execute(db.intakes.update().where(db.intakes.c.job_id==job['id']).values(payload=p))
    network=Mock(side_effect=AssertionError('No download past budget'));monkeypatch.setattr(collection,'fetch',network)
    with pytest.raises(ResearchError,match='COLLECTION_SOURCE_LIMIT'):collection.acquire(research,job,page['items'][0]['id'])
    network.assert_not_called()


def test_cancel_blocks_source_commit(research,client,monkeypatch):
    pid,_cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    sid=collection.register(research,job,{'url':'https://example.org/cancel','title':'Cancelled source'})
    def cancelled(url,check,maximum):
        with research.engine.begin() as c:c.execute(db.jobs.update().where(db.jobs.c.id==job['id']).values(state='cancel_requested'))
        check();raise AssertionError('Cancelled request must not commit')
    monkeypatch.setattr(collection,'fetch',cancelled)
    with pytest.raises(ResearchError,match='JOB_NO_LONGER_OWNED'):collection.acquire(research,job,sid)
    assert research.list_materials(pid,'tester')==[]


def test_summary_can_be_upgraded_to_fulltext(research,client,monkeypatch):
    pid,_cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    sid=collection.register(research,job,{'url':'https://example.org/excerpt','title':'摘要来源','snippet':'供应商实际返回的摘要。'})
    source=collection.associated(research,pid,job['id'])[0];collection.materialize_excerpt(research,job,source)
    before=collection.list_sources(research,pid,'tester')[0];assert before['availability']=='summary'
    with research.engine.begin() as c:research.finish(c,job,{'state':'awaiting_input'})
    raw=('<article><p>'+('现在取得可以读取的完整正文。'*15)+'</p></article>').encode()
    network=Mock(return_value=(raw,'text/html','https://example.org/excerpt'));monkeypatch.setattr(collection,'fetch',network)
    retry=client.post(f'/api/v2/projects/{pid}/sources/{sid}/actions',headers={'Idempotency-Key':'upgrade'},json={
        'job_id':job['id'],'revision':before['revision'],'action':'fetch'}).json()
    run_one(research,retry['id']);after=collection.list_sources(research,pid,'tester')[0]
    assert after['availability']=='fulltext' and after['asset_id']!=before['asset_id']
    assert research.get_segments(pid,'tester',before['asset_id'],before['version_id'])['segments']
    network.assert_called_once()


def test_redirect_target_and_stream_size_are_rechecked(monkeypatch):
    import httpx
    from scriptorium.research import public_fetch
    real_client=httpx.Client
    monkeypatch.setattr(public_fetch,'public_addresses',lambda *args:['93.184.216.34'])
    seen=[]
    def redirect(request):
        seen.append(str(request.url));return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    monkeypatch.setattr(public_fetch.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(redirect)))
    with pytest.raises(ResearchError,match='PRIVATE'):public_fetch.fetch('https://example.org/')
    assert len(seen)==1
    monkeypatch.setattr(public_fetch.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-type':'text/plain'},content=b'x'*101))))
    with pytest.raises(ResearchError,match='DOWNLOAD_LIMIT'):public_fetch.fetch('https://example.org/',maximum=100)


def test_cancelled_collection_resumes_without_redownloading(research,client,monkeypatch):
    pid,_cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    sid=collection.register(research,job,{'url':'https://example.org/resume','title':'恢复原件'})
    raw=('<article><p>'+('这份已保存的材料可在恢复后继续使用。'*15)+'</p></article>').encode()
    fetch=Mock(return_value=(raw,'text/html','https://example.org/resume'));monkeypatch.setattr(collection,'fetch',fetch)
    collection.acquire(research,job,sid);collection.checkpoint(research,job,'reading',discovered=True)
    with research.engine.begin() as c:c.execute(db.jobs.update().where(db.jobs.c.id==job['id']).values(state='cancel_requested'))
    research.fail(job,ResearchError('JOB_NO_LONGER_OWNED'))
    root=f'/api/v2/projects/{pid}';intake=client.get(root+'/intakes').json()[0];assert intake['state']=='cancelled'
    response=client.post(root+'/intakes/'+job['id']+'/decisions',json={'revision':intake['revision'],'action':'resume'})
    assert response.status_code==200,response.text
    resumed=research.claim_job(job['id']);collection.acquire(research,resumed,sid);fetch.assert_called_once()


def test_web_policy_blocks_discovery_before_transport(research,client,monkeypatch):
    pid,_cid,submitted=send(research,client);job=research.claim_job(submitted['id'])
    with research.engine.begin() as c:c.execute(db.project_policies.insert().values(project_id=pid,revision=1,payload={'allow_web':False}))
    forbidden=Mock(side_effect=AssertionError('Policy must block HTTP'))
    monkeypatch.setattr(native_search.httpx,'Client',forbidden)
    with pytest.raises(ResearchError,match='PROJECT_EXTERNAL_PROCESSING_DISABLED'):native_search.discover(research,job,'问题')
    forbidden.assert_not_called()


def test_failed_fetch_reservation_remains_unknown_after_retry(research,client,monkeypatch):
    pid,_cid,submitted=send(research,client);job=research.claim_job(submitted['id']);collection.ensure_intake(research,job)
    sid=collection.register(research,job,{'url':'https://example.org/unknown','title':'Unknown download'})
    monkeypatch.setattr(collection,'fetch',Mock(side_effect=RuntimeError('network response lost')))
    collection.acquire(research,job,sid)
    with research.engine.begin() as c:research.finish(c,job,{'state':'awaiting_input'})
    before=collection.list_sources(research,pid,'tester')[0]
    raw=('<article><p>'+('原件现在可获取。'*20)+'</p></article>').encode()
    monkeypatch.setattr(collection,'fetch',Mock(return_value=(raw,'text/html','https://example.org/unknown')))
    root=f'/api/v2/projects/{pid}'
    retry=client.post(root+'/sources/'+sid+'/actions',headers={'Idempotency-Key':'retry-unknown'},json={
        'job_id':job['id'],'revision':before['revision'],'action':'fetch'}).json();run_one(research,retry['id'])
    intake=client.get(root+'/intakes').json()[0]
    assert intake['downloaded_bytes']==len(raw) and intake['reserved_bytes']==20*1024*1024


def test_material_metadata_cannot_point_original_at_another_object(research,client):
    pid,aid,_segments=imported(research,'属于当前材料的原文。')
    foreign,_digest=research.objects.put(b'private object outside material')
    with research.engine.begin() as c:
        a=row(c,db.assets,db.assets.c.id==aid)
        c.execute(db.assets.update().where(db.assets.c.id==aid).values(metadata={**a['metadata'],'original_object_key':foreign}))
    response=client.get(f'/api/v2/projects/{pid}/materials/{aid}/original')
    assert response.status_code==200 and response.content!=b'private object outside material'
