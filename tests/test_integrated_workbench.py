# ruff: noqa: F811
from dataclasses import replace
import json
import test_research_integration  # noqa: F401 — module-level importorskip('sqlalchemy') guards this file
import sqlalchemy as sa
from fastapi.testclient import TestClient
from test_research_integration import research, client, imported  # noqa: F401
from test_research_experience import fake_model
from scriptorium.research import schema as db
from scriptorium.research.api import create_app
from scriptorium.research.service import row, rows
from scriptorium.research.worker import run_one


def as_user(s, uid):
    c = TestClient(create_app(replace(s.settings, principal=uid), s.engine))
    c.headers['Authorization'] = 'Bearer test-key'
    return c


def test_roles_personal_workspace_and_audit(research, client):
    pid = research.create_project('tester', '团队项目')['id']; root = f'/api/v2/projects/{pid}'
    cid = client.post(root + '/conversations', json={}).json()['id']
    assert client.delete(root + '/members/tester').status_code == 409
    assert client.put(root + '/members/reader', json={'role': 'reader'}).status_code == 200
    assert client.put(root + '/members/reviewer', json={'role': 'reviewer'}).status_code == 200
    assert client.put(root + f'/conversations/{cid}/workspace', json={'revision': 0, 'payload': {'draft': 'private owner draft'}}).status_code == 200
    with as_user(research, 'reader') as reader:
        assert reader.get(root + '/records').status_code == 200
        assert reader.post(root + '/records', json={'kind': 'manuscript', 'payload': {'text': 'no'}}).status_code == 404
        assert reader.put(root + '/policy', json={'revision': 0}).status_code == 403
        assert reader.get(root + f'/conversations/{cid}/workspace').json()['payload'] == {}
        assert reader.put(root + f'/conversations/{cid}/workspace', json={'revision': 0, 'payload': {'draft': 'my view'}}).status_code == 200
        assert reader.put(root + f'/conversations/{cid}/workspace', json={'revision': 0, 'payload': {}}).status_code == 409
    assert client.get(root + f'/conversations/{cid}/workspace').json()['payload']['draft'] == 'private owner draft'
    assert client.get(root + '/audit').json()
    assert client.delete(root + '/members/reader').status_code == 200
    with as_user(research, 'reader') as reader:
        assert reader.get(root + '/records').status_code == 404


def test_proposal_accept_reject_and_stale_revision(research, client):
    pid = research.create_project('tester', '稿件')['id']; root = f'/api/v2/projects/{pid}'
    doc = {'type': 'doc', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': '原文😀'}]}]}
    record = client.post(root + '/records', json={'kind': 'manuscript', 'payload': {'title': '稿', 'editor_json': doc}}).json()
    endpoint = root + f"/artifacts/{record['id']}/change-proposals"
    def propose(revision):
        r = client.post(endpoint, json={'base_revision': revision, 'instruction': '改善表述', 'provider_mode': 'demo'})
        assert r.status_code == 202, r.text
        run_one(research, r.json()['id'])
        proposals = client.get(endpoint).json()
        return next(p for p in proposals if p['id'] == r.json()['id'])
    p = propose(1)
    assert client.get(root + f"/artifacts/{record['id']}").json()['revision'] == 1
    assert client.post(root + '/change-proposals/' + p['id'], json={'action': 'accept'}).status_code == 200
    assert client.get(root + f"/artifacts/{record['id']}").json()['revision'] == 2
    stale = propose(2)
    new = client.put(root + f"/records/{record['id']}", json={'kind': 'manuscript', 'revision': 2, 'payload': {'text': '人工新稿'}})
    assert new.status_code == 200
    assert client.post(root + '/change-proposals/' + stale['id'], json={'action': 'accept'}).status_code == 409
    assert client.post(root + '/change-proposals/' + stale['id'], json={'action': 'reject'}).status_code == 200
    restore = client.post(root + f"/artifacts/{record['id']}/restore", json={'revision': 3, 'source_revision': 1})
    assert restore.status_code == 200, restore.text
    assert '原文' in restore.json()['payload']['text']


def test_external_policy_blocks_before_transport_and_reservation(research, client, monkeypatch):
    pid, _aid, segments = imported(research, '材料原文。'); root = f'/api/v2/projects/{pid}'
    r = client.put(root + '/policy', json={'revision': 0, 'allow_external': False})
    assert r.status_code == 200, r.text
    fake_model(monkeypatch, {'summary': '不应调用', 'outcome': 'context_candidate'})
    job = client.post(root + '/method-runs', headers={'Idempotency-Key': 'policy-block'}, json={
        'method_id': 'situating.v1', 'question': '问题', 'segment_ids': [segments[0]['id']]}).json()
    run_one(research, job['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == job['id'])['error'] == 'PROJECT_EXTERNAL_PROCESSING_DISABLED'
        assert not rows(c, db.model_calls, db.model_calls.c.project_id == pid)
    assert client.put(root + '/policy', json={'revision': 0}).status_code == 409


def test_reviewers_comment_but_cannot_edit(research, client):
    pid = research.create_project('tester', '评议')['id']; root = f'/api/v2/projects/{pid}'
    record = client.post(root + '/records', json={'kind': 'manuscript', 'payload': {'text': '稿件'}}).json()
    client.put(root + '/members/reviewer', json={'role': 'reviewer'})
    with as_user(research, 'reviewer') as reviewer:
        assert reviewer.post(root + f"/artifacts/{record['id']}/comments", json={'text': '建议补充出处'}).status_code == 201
        assert reviewer.post(root + f"/artifacts/{record['id']}/change-proposals", json={'base_revision': 1, 'instruction': 'x'}).status_code == 404


def test_new_tables_backup_restore(research, client, tmp_path):
    from scriptorium.research.backup import backup, restore
    pid = research.create_project('tester', '备份')['id']; root = f'/api/v2/projects/{pid}'
    client.put(root + '/members/reader', json={'role': 'reader'})
    from scriptorium.research import collection
    cid = client.post(root + '/conversations', json={}).json()['id']
    submitted = client.post(root + f'/conversations/{cid}/messages', headers={'Idempotency-Key':'backup-source'},
        json={'text':'研究备份','tool':'auto'}).json()
    job = research.claim_job(submitted['id']); collection.ensure_intake(research,job)
    sid = collection.register(research,job,{'url':'https://example.org/backup','title':'Backup source','snippet':'A real stored fixture excerpt.'})
    with research.engine.begin() as c: research.finish(c,job,{'state':'fixture'})
    destination = tmp_path / 'backup'; backup(research, destination)
    manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema'] == 'research_0007'
    assert manifest['tables']['r_sources']['rows']==1 and manifest['objects']
    assert 'r_audit' in manifest['tables'] and 'r_workspaces' in manifest['tables']
    from scriptorium.research.service import ResearchService
    name = 'restore_' + db.uid()
    with research.engine.begin() as c:
        c.execute(sa.text('CREATE SCHEMA ' + name))
    restored = sa.create_engine(research.settings.database_url, connect_args={'options': '-csearch_path=' + name})
    try:
        db.metadata.create_all(restored); target = ResearchService(restored, replace(research.settings, object_root=tmp_path/'restored-objects'))
        restore(target, destination)
        with restored.connect() as c:
            assert len(rows(c, db.members, db.members.c.project_id == pid)) == 2
            assert rows(c, db.audit, db.audit.c.project_id == pid)
            link=row(c,db.run_sources,db.run_sources.c.source_id==sid)
            assert b'example.org/backup' in target.objects.read(link['payload']['snapshot_key'])
    finally:
        restored.dispose()
        with research.engine.begin() as c:
            c.execute(sa.text('DROP SCHEMA ' + name + ' CASCADE'))


def test_export_docx_footnote_citation_and_chapter(research, client, monkeypatch):
    import io, zipfile
    from pathlib import Path
    binary = Path('desktop-build/pandoc/3.12.1/pandoc.exe').resolve()
    assert binary.is_file(), 'Prepare the pinned export runtime before this integration test'
    monkeypatch.setattr('scriptorium.research.exporting.ensure_pandoc', lambda: binary)
    pid, aid, segments = imported(research, '原文提供支持。')
    with research.engine.begin() as c:
        c.execute(db.assets.update().where(db.assets.c.id==aid).values(metadata={'title':'版本研究','author':'研究者','publication_date':'2020'}))
        anchor=research.make_anchor(c,pid,segments[0]['id'],0,2,'原文')
    root=f'/api/v2/projects/{pid}'
    editor={'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'一个有出处的论点'},
        {'type':'citation','attrs':{'anchorId':anchor['id']}},{'type':'footnote','attrs':{'text':'补充说明。'}}]}]}
    r=client.post(root+'/records',json={'kind':'manuscript','payload':{'title':'中英文研究','editor_json':editor}}).json()
    client.put(root+f"/artifacts/{r['id']}/chapters/one",json={'payload':{'title':'第二章','editor_json':{'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'章节内容'}]}]}}})
    for fmt,locale,style in [('docx','zh-CN','note'),('html','en-US','author-date')]:
        j=client.post(root+f"/artifacts/{r['id']}/exports",json={'format':fmt,'locale':locale,'style':style}).json()
        run_one(research,j['id'])
        with research.engine.connect() as c:
            job=row(c,db.jobs,db.jobs.c.id==j['id']);assert job['state']=='succeeded',job
        exported=client.get(root+f"/exports/{j['id']}/download");assert exported.status_code==200
        if fmt=='docx':
            with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
                assert '章节内容' in z.read('word/document.xml').decode()
                notes=z.read('word/footnotes.xml').decode();assert '补充说明' in notes and '版本研究' in notes
        else:
            assert '章节内容' in exported.text and '版本研究' in exported.text


def test_oidc_login_session_origin_and_admin_boundary(research, client, monkeypatch):
    import time
    from types import SimpleNamespace
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    monkeypatch.setenv('SCRIPTORIUM_OIDC_ISSUER','https://identity.example/realms/research')
    monkeypatch.setenv('SCRIPTORIUM_OIDC_CLIENT_ID','scriptorium')
    monkeypatch.setenv('SCRIPTORIUM_PUBLIC_URL','https://research.example')
    monkeypatch.setenv('SCRIPTORIUM_COOKIE_SECURE','0')
    cfg={'issuer':'https://identity.example/realms/research','authorization_endpoint':'https://identity.example/auth','token_endpoint':'https://identity.example/token','jwks_uri':'https://identity.example/keys'}
    monkeypatch.setattr('scriptorium.research.auth.metadata',lambda:cfg)
    assert client.get('/api/v2/projects').status_code==401
    login=client.get('/api/v2/auth/login',follow_redirects=False);assert login.status_code==307
    from urllib.parse import urlsplit,parse_qs
    state=parse_qs(urlsplit(login.headers['location']).query)['state'][0]
    with research.engine.connect() as c:
        flow=row(c,db.users,db.users.c.id=='flow:'+state)
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    token=jwt.encode({'iss':cfg['issuer'],'sub':'researcher','aud':'scriptorium','exp':int(time.time())+300,'nonce':json.loads(flow['name'])['nonce'],'name':'研究成员'},private,algorithm='RS256')
    class Http:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def post(self,*args,**kwargs):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'id_token':token})
    monkeypatch.setattr('scriptorium.research.auth.httpx.Client',lambda **kwargs:Http())
    monkeypatch.setattr('scriptorium.research.auth.jwt.PyJWKClient',lambda url:SimpleNamespace(get_signing_key_from_jwt=lambda token:SimpleNamespace(key=private.public_key())))
    callback=client.get('/api/v2/auth/callback',params={'state':state,'code':'one-use-code'},follow_redirects=False)
    assert callback.status_code==307,callback.text
    status=client.get('/api/v2/auth/session').json();assert status['authenticated'] and status['name']=='研究成员'
    assert client.post('/api/v2/projects',json={'name':'Blocked CSRF'}).status_code==403
    create=client.post('/api/v2/projects',json={'name':'团队项目'},headers={'Origin':'https://research.example'})
    assert create.status_code==201,create.text
    assert client.put('/api/v2/system/model',json={'provider':'qwen'},headers={'Origin':'https://research.example'}).status_code==403
    assert client.get('/api/v2/auth/callback',params={'state':state,'code':'again'},follow_redirects=False).status_code==401
    logout=client.post('/api/v2/auth/logout',headers={'Origin':'https://research.example'})
    assert logout.status_code==200 and logout.json()['logged_out']
    assert client.get('/api/v2/auth/session').json()['authenticated'] is False


def test_classification_version_policy_and_chapter_history(research, client):
    pid, aid, segments = imported(research, '来源😀'); root = f'/api/v2/projects/{pid}'
    version = segments[0]['version_id']
    asset = client.get(root + '/materials').json()[0]
    assert client.put(root + f'/materials/{aid}/classification', json={'revision': asset['revision'], 'sensitive': True}).status_code == 200
    assert client.put(root + '/policy', json={'revision': 0, 'allow_external': True, 'allowed_hosts': ['api.example.org'], 'asset_ids': [aid], 'version_ids': ['missing']}).status_code == 422
    policy = client.put(root + '/policy', json={'revision': 0, 'allow_external': True, 'allowed_hosts': ['api.example.org'], 'asset_ids': [aid], 'version_ids': [version]})
    assert policy.status_code == 200
    from types import SimpleNamespace
    from scriptorium.research.calls import reserve, synchronous_job
    from scriptorium.research.service import ResearchError
    import pytest
    with pytest.raises(ResearchError, match='SENSITIVE_MATERIAL_EXTERNAL_PROCESSING_DISABLED'):
        reserve(research, synchronous_job(research, pid, 'tester', 'chat', [aid]), SimpleNamespace(model='fake', base_url='https://api.example.org/v1'), [], 10)
    manuscript = client.post(root+'/records', json={'kind': 'manuscript', 'payload': {'title': '稿', 'text': ''}}).json()
    path=root+f"/artifacts/{manuscript['id']}/chapters/chapter-one"
    doc={'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'旧章'}]}]}
    assert client.put(path, json={'payload': {'title': '第一章', 'editor_json': doc}}).status_code == 200
    doc['content'][0]['content'][0]['text']='新章'
    assert client.put(path, json={'revision': 1, 'payload': {'title': '第一章', 'editor_json': doc}}).status_code == 200
    old=client.get(path+'/history').json()
    assert len(old)==1 and old[0]['revision']==1 and '旧章' in old[0]['payload']['text']


def test_ollama_stream_is_accounted_even_when_interrupted(research):
    from contextlib import contextmanager
    from scriptorium.topostyle.provider import OllamaProvider
    from scriptorium.research.calls import accounted_ollama, synchronous_job
    pid=research.create_project('tester','stream')['id']
    class Response:
        def raise_for_status(self): pass
        def iter_lines(self):
            yield json.dumps({'message': {'content': '你好'}})
            yield json.dumps({'done': True,'prompt_eval_count': 12,'eval_count': 4})
    @contextmanager
    def fake(*args, **kwargs): yield Response()
    provider=OllamaProvider(); provider.stream_transport=fake
    accounted_ollama(research,synchronous_job(research,pid,'tester','persona'),provider)
    assert ''.join(provider.generate([{'role':'user','content':'hello'}],stream=True))=='你好'
    stream=provider.generate([{'role':'user','content':'hello'}],stream=True)
    assert next(stream)=='你好'; stream.close()
    with research.engine.connect() as c:
        calls=rows(c,db.model_calls,db.model_calls.c.project_id==pid)
        assert sorted(x['state'] for x in calls)==['returned','unknown']
        assert next(x for x in calls if x['state']=='returned')['usage']['total_tokens']==16
        assert next(x for x in calls if x['state']=='unknown')['reserved_tokens']>0
