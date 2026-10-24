# ruff: noqa: F811
"""Unified workflows against real PostgreSQL, with explicitly selected demo models."""

from test_research_integration import research, client, imported  # noqa: F401
from hermeneut.research import schema as db
from hermeneut.research.service import row
from hermeneut.research.service import rows
from hermeneut.research.worker import run_one


def test_coordinator_wait_does_not_exhaust_attempts_or_duplicate_results(research, client, monkeypatch):
    import sqlalchemy as sa
    from hermeneut.research import worker
    path, cid, aid = setup_workspace(research, client)
    job = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'waiting'},
        json={'text': '研究恢复', 'tool': 'research', 'asset_ids': [aid], 'provider_mode': 'demo',
              'methods': ['situating.v1']}).json()
    held = []
    real_run_one = worker.run_one

    def occupied_child(service, child_id):
        if not held:
            held.append(service.claim_job(child_id))
        return real_run_one(service, child_id)

    monkeypatch.setattr(worker, 'run_one', occupied_child)
    for _ in range(research.settings.max_attempts + 3):
        assert real_run_one(research, job['id'])
        with research.engine.begin() as c:
            waiting = row(c, db.jobs, db.jobs.c.id == job['id'])
            assert waiting['state'] == 'queued'
            assert waiting['attempts'] == 0  # yields do not spend the failure allowance
            assert waiting['lease_token'] is None
            assert research.claim_job(job['id']) is None  # delayed, no busy reclaim
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(lease_until=0))
    with research.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == held[0]['id']).values(lease_until=0))
    assert real_run_one(research, job['id'])
    with research.engine.connect() as c:
        completed = row(c, db.jobs, db.jobs.c.id == job['id'])
        assert completed['state'] == 'succeeded', completed
        rid = completed['result']['run_id']
        steps = rows(c, db.research_steps, db.research_steps.c.run_id == rid)
        reports = rows(c, db.records, db.records.c.project_id == job['project_id'])
        assert all(step['state'] == 'succeeded' for step in steps)
        assert len({step['result']['record_id'] for step in steps}) == len(steps)
        assert len([r for r in reports if r['payload'].get('run_id') == rid and r['kind'] == 'manuscript']) == 1
        assert not c.execute(sa.select(db.jobs.c.id).where(db.jobs.c.project_id == job['project_id'],
                            db.jobs.c.state == 'failed')).first()


def setup_workspace(research, client, text='自由需要物质条件。'):
    pid, aid, _ = imported(research, text)
    path = f'/api/v2/projects/{pid}'
    conv = client.post(path + '/conversations', json={'title': '自由研究'}).json()
    return path, conv['id'], aid


def test_conversation_persistence_isolation_and_archive(research, client):
    path, cid, _ = setup_workspace(research, client)
    result = client.put(path + '/conversations/' + cid, json={'revision': 1,
        'workspace': {'draft': '尚未发送', 'scroll': 70}})
    assert result.status_code == 200, result.text
    assert client.put(path + '/conversations/' + cid, json={'revision': 1, 'title': '覆盖'}).status_code == 409
    assert client.get(path + '/conversations').json()[0]['workspace']['draft'] == '尚未发送'
    other = research.create_project('tester', 'Other')['id']
    assert client.get(f'/api/v2/projects/{other}/conversations/{cid}/messages').status_code == 404
    client.put(path + '/conversations/' + cid, json={'revision': 2, 'archived': True})
    assert client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'a'},
        json={'text': '你好'}).status_code == 409


def test_chat_and_research_use_one_service(research, client):
    path, cid, aid = setup_workspace(research, client)
    endpoint = path + f'/conversations/{cid}/messages'
    body = {'text': '解释自由', 'tool': 'chat', 'asset_ids': [aid], 'provider_mode': 'demo'}
    first = client.post(endpoint, headers={'Idempotency-Key': 'chat'}, json=body)
    assert first.status_code == 202, first.text
    assert client.post(endpoint, headers={'Idempotency-Key': 'chat'}, json=body).json()['id'] == first.json()['id']
    run_one(research, first.json()['id'])
    assert len(client.get(endpoint).json()) == 2
    body.update(tool='research', methods=['situating.v1'])
    j = client.post(endpoint, headers={'Idempotency-Key': 'research'}, json=body).json()
    run_one(research, j['id'])
    with research.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == j['id'])
        assert job['state'] == 'succeeded', job
    run = client.get(path + '/research-runs').json()[0]
    assert run['state'] == 'completed_with_open_questions'
    detail = client.get(path + '/research-runs/' + run['id']).json()
    assert all(x['state'] == 'succeeded' for x in detail['steps'])
    assert len({x['step_key'] for x in detail['steps']}) == len(detail['steps'])


def test_long_material_budget_decision_and_resume(research, client):
    path, cid, aid = setup_workspace(research, client, '自由😀e\u0301' * 2200)
    j = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'long'},
        json={'text': '分析全部材料', 'tool': 'research', 'asset_ids': [aid], 'provider_mode': 'demo',
              'methods': ['situating.v1'], 'token_budget': 10000}).json()
    run_one(research, j['id'])
    run = client.get(path + '/research-runs').json()[0]
    assert run['state'] == 'awaiting_input'
    assert sum(w['end']-w['start'] for w in run['scope']) == len('自由😀e\u0301' * 2200)
    d = client.get(path + '/decisions').json()[0]
    resumed = client.post(path + '/decisions/' + d['id'], json={'accept': True, 'additional_tokens': 50000})
    assert resumed.status_code == 200, resumed.text
    run_one(research, resumed.json()['id'])
    detail = client.get(path + '/research-runs/' + run['id']).json()
    assert detail['state'] == 'completed_with_open_questions', detail
    assert client.post(path + '/decisions/' + d['id'], json={'accept': True}).status_code == 409


def test_interview_pause_resume_and_material(research, client):
    path, cid, _ = setup_workspace(research, client)
    p = client.post(path + '/participants', json={'pseudonym': '甲', 'material_collection': True,
        'profile_analysis': True, 'agent_simulation': True})
    assert p.status_code == 201, p.text
    result = client.post(path + '/interviews', json={'participant_id': p.json()['id'], 'conversation_id': cid})
    assert result.status_code == 201, result.text
    iv = result.json()
    iid = iv['id']
    assert client.post(path + f'/interviews/{iid}/pause').status_code == 200
    assert client.post(path + f'/interviews/{iid}/resume').status_code == 200
    for _ in range(10):
        iv = client.get(path + '/interviews/' + iid).json()
        if not iv.get('current_question'):
            break
        response = client.post(path + f'/interviews/{iid}/turns', json={
            'question_id': iv['current_question']['id'], 'answer_text': '这是回答'})
        assert response.status_code == 200, response.text
    complete = client.post(path + f'/interviews/{iid}/complete')
    assert complete.status_code == 200, complete.text
    run_one(research, complete.json()['job_id'])
    mats = client.get(path + '/materials').json()
    assert any(m['metadata'].get('interview_id') == iid and m['status'] == 'ready' for m in mats)
    assert client.post(path + f'/interviews/{iid}/complete').json() == complete.json()
    assert client.post(path + '/participants/' + p.json()['id'] + '/withdraw').status_code == 200
    assert client.post(path + '/personas', json={'participant_id': p.json()['id'], 'name': '模拟'}).status_code == 403
    assert any(m['status'] == 'ready' and not m['metadata'].get('interview_id') for m in client.get(path + '/materials').json())


def test_theory_compatibility_and_persona_continue(research, client, monkeypatch):
    import numpy as np
    from hermeneut.research.legacy_store import PostgresStore
    import hermeneut.topostyle.provider as module
    import hermeneut.topostyle.service as training
    class LocalTestModel:
        def __init__(self, **kwargs):
            pass
        def embed(self, texts):
            return np.arange(len(texts)*12).reshape(len(texts),12).tolist()
        def generate_structured(self, *args):
            return {'core':'学习','expression':'解释','evidence':'自由'}
        def generate(self, messages):
            return '模拟表达，仅供测试'
    monkeypatch.setattr(module, 'OllamaProvider', LocalTestModel)
    monkeypatch.setattr(training, 'OllamaProvider', LocalTestModel)
    path,cid,aid = setup_workspace(research,client)
    pid = path.split('/')[-1]
    person = client.post(path+'/participants',json={'pseudonym':'甲','material_collection':True,
        'agent_simulation':True,'profile_analysis':True}).json()
    j = research.import_material(pid,'tester','另一个独立材料。'.encode(),'other.txt','other')
    run_one(research,j['id'])
    assert client.post(path+f'/participants/{person["id"]}/materials',json={
        'asset_ids':[aid,j['payload']['asset_id']]}).status_code==200
    p=client.post(path+'/personas',json={'participant_id':person['id'],'name':'模拟甲'}).json()
    j=client.post(path+f'/personas/{p["id"]}/train').json()
    research.process_job(research.claim_job(j['id']))
    with research.engine.connect() as c:
        job=row(c,db.jobs,db.jobs.c.id==j['id'])
        assert job['state']=='succeeded',job
    for i in range(2):
        j=client.post(path+f'/conversations/{cid}/messages',headers={'Idempotency-Key':f'persona-{i}'},
            json={'tool':'persona','persona_id':p['id'],'text':'请回应'}).json()
        run_one(research,j['id'])
    assert len(PostgresStore(research,pid,'tester').list_messages(cid))==4
    assert client.get('/api/v1/personas/'+p['id']).json()['id']==p['id']
    j=client.post(path+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'theory'},
        json={'tool':'theory','text':'比较理论','asset_ids':[aid],'provider_mode':'demo'}).json()
    run_one(research,j['id'])
    with research.engine.connect() as c:
        assert row(c,db.jobs,db.jobs.c.id==j['id'])['state']=='succeeded'
    assert client.get('/api/v1/projects').json()['projects']
    j=client.post(path+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'subject'},json={
        'text':'分析主体','tool':'subject','participant_id':person['id'],'asset_ids':[aid],'provider_mode':'demo'}).json()
    research.process_job(research.claim_job(j['id']))
    assert client.post(path+f'/participants/{person["id"]}/withdraw').status_code==200
    assert not PostgresStore(research,pid,'tester').list_personas(pid)


def test_research_cancel_and_checkpoint_retry(research, client):
    path,cid,aid=setup_workspace(research,client)
    j=client.post(path+f'/conversations/{cid}/messages',headers={'Idempotency-Key':'pause'},json={
        'text':'研究','tool':'research','asset_ids':[aid],'provider_mode':'demo','token_budget':10000}).json()
    # Force the budget checkpoint before any model work.
    with research.engine.begin() as c:
        payload={**j['payload'],'token_budget':1}
        c.execute(db.jobs.update().where(db.jobs.c.id==j['id']).values(payload=payload))
    run_one(research,j['id'])
    run=client.get(path+'/research-runs').json()[0]
    assert client.post(path+f'/research-runs/{run["id"]}/cancel').status_code==200
    assert client.get(path+f'/research-runs/{run["id"]}').json()['state']=='cancelled'


def test_stale_worker_releases_new_job_kind_instead_of_failing(research, client):
    """GAP-02: a worker from an older build must not destroy a job kind it does not know."""
    path, cid, aid = setup_workspace(research, client)
    j = client.post(path + f'/conversations/{cid}/messages', headers={'Idempotency-Key': 'stale'}, json={
        'text': '研究', 'tool': 'research', 'asset_ids': [aid], 'provider_mode': 'demo'}).json()
    # A worker built before `workspace` existed only claims the kinds it knows.
    assert research.claim_job(j['id'], kinds={'import'}) is None
    assert run_one(research, j['id'], kinds={'import'}) is False
    # Simulate a newer build's kind, then a stale worker that is somehow handed the job.
    with research.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(kind='future_kind'))
    skip = set()
    assert run_one(research, j['id'], kinds={'future_kind'}, skip=skip) is True
    assert skip == {'future_kind'}
    with research.engine.connect() as c:
        stale = row(c, db.jobs, db.jobs.c.id == j['id'])
        events = [e for e in rows(c, db.events, db.events.c.job_id == j['id'])
                  if e['data'].get('reason') == 'UNSUPPORTED_JOB_KIND']
    assert stale['state'] == 'queued' and stale['attempts'] == 0 and stale['error'] is None, stale
    assert len(events) == 1
    # The job is still a normal task: a current worker finishes it and the research run survives.
    with research.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(kind='workspace'))
    run_one(research, j['id'])
    with research.engine.connect() as c:
        assert row(c, db.jobs, db.jobs.c.id == j['id'])['state'] == 'succeeded'
    assert client.get(path + '/research-runs').json()


def test_system_status_reports_build_and_queue(research, client):
    path, _cid, _aid = setup_workspace(research, client)
    health = client.get('/health').json()
    assert health['job_kinds'] == sorted(health['job_kinds']) and 'workspace' in health['job_kinds']
    status = client.get('/api/v2/system/status').json()
    assert set(status['supported_job_kinds']) == set(health['job_kinds'])
    assert status['job_states']['queued'] >= 0 and status['stale_leases'] == 0
    assert status['unknown_kind_jobs'] == []
    with research.engine.begin() as c:
        c.execute(db.jobs.insert().values(id='unknown-kind-job', project_id=path.split('/')[-1],
            kind='from_the_future', idem='future', request_hash='x', payload={}, state='queued',
            attempts=0, created_at=db.now()))
    listed = client.get('/api/v2/system/status').json()
    assert [x['kind'] for x in listed['unknown_kind_jobs']] == ['from_the_future']


def test_ocr_creates_immutable_quality_version(research, client):
    import pymupdf
    with pymupdf.open() as pdf:
        page=pdf.new_page()
        page.insert_text((72,72),'Original source for OCR version testing.')
        raw=pdf.tobytes()
    pid=research.create_project('tester','PDF')['id']
    j=research.import_material(pid,'tester',raw,'source.pdf','pdf')
    run_one(research,j['id'])
    aid=j['payload']['asset_id']
    before=research.get_segments(pid,'tester',aid)['version']['id']
    response=client.post(f'/api/v2/projects/{pid}/materials/{aid}/ocr')
    assert response.status_code==202,response.text
    research.process_job(research.claim_job(response.json()['id']))
    after=research.get_segments(pid,'tester',aid)
    assert after['version']['id']!=before
    assert after['version']['quality']['review_state']=='unreviewed'
    assert research.get_segments(pid,'tester',aid,before)['segments']
    material=next(m for m in research.list_materials(pid,'tester') if m['id']==aid)
    assert material['metadata']['ocr']['state']=='succeeded'
    assert material['metadata']['ocr']['version_id']==after['version']['id']


def test_blank_pdf_page_is_reported_not_silently_dropped(research, client):
    """MAT-05: an empty page must be listed in the version quality instead of vanishing."""
    import pymupdf
    with pymupdf.open() as pdf:
        first = pdf.new_page()
        first.insert_text((72, 72), 'Page one carries extractable text.')
        pdf.new_page()
        raw = pdf.tobytes()
    pid = research.create_project('tester', 'Blank page')['id']
    j = research.import_material(pid, 'tester', raw, 'pages.pdf', 'pages')
    run_one(research, j['id'])
    aid = j['payload']['asset_id']
    version = research.get_segments(pid, 'tester', aid)['version']
    assert version['quality']['empty_pages'] == [2]
    assert {segment['page_label'] for segment in research.get_segments(pid, 'tester', aid)['segments']} == {'1'}
    # OCR keeps the same page sequence and reports the page it could not read.
    response = client.post(f'/api/v2/projects/{pid}/materials/{aid}/ocr')
    assert response.status_code == 202, response.text
    run_one(research, response.json()['id'])
    ocr_version = research.get_segments(pid, 'tester', aid)['version']
    assert ocr_version['id'] != version['id']
    assert ocr_version['quality']['empty_pages'] == [2]
    assert ocr_version['quality']['page_labels_are_printed'] is False
    assert ocr_version['quality']['review_state'] == 'unreviewed'
    assert research.get_segments(pid, 'tester', aid, version['id'])['segments']


def test_scanned_pdf_ocr_failure_is_explicit_and_keeps_original(research, client):
    """MAT-05: a scanned page without an OCR engine fails loudly; the original is untouched."""
    import pymupdf
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(pymupdf.Rect(60, 60, 320, 140), color=(0, 0, 0), fill=(0.65, 0.65, 0.65))
        raw = pdf.tobytes()
    pid = research.create_project('tester', 'Scanned')['id']
    j = research.import_material(pid, 'tester', raw, 'scan.pdf', 'scan')
    run_one(research, j['id'])
    aid = j['payload']['asset_id']
    with research.engine.connect() as c:
        imported_job = row(c, db.jobs, db.jobs.c.id == j['id'])
    assert imported_job['state'] == 'failed'
    assert imported_job['error'] == 'NO_EXTRACTABLE_TEXT'
    assert client.get(f'/api/v2/projects/{pid}/materials/{aid}/original').status_code == 200
    response = client.post(f'/api/v2/projects/{pid}/materials/{aid}/ocr')
    assert response.status_code == 202, response.text
    run_one(research, response.json()['id'])
    with research.engine.connect() as c:
        ocr_job = row(c, db.jobs, db.jobs.c.id == response.json()['id'])
    assert ocr_job['state'] == 'failed'
    assert ocr_job['error'] in {'OCR_ENGINE_OR_LANGUAGE_UNAVAILABLE', 'OCR_NO_TEXT'}, ocr_job
    material = next(m for m in research.list_materials(pid, 'tester') if m['id'] == aid)
    assert material['status'] == 'error' and material['versions'] == []
    assert material['metadata']['ocr']['state'] == 'failed'
    assert material['metadata']['ocr']['error'] == ocr_job['error']
    # The retained original is still downloadable after the failed attempt.
    assert client.get(f'/api/v2/projects/{pid}/materials/{aid}/original').status_code == 200


def test_cli_doctor_and_verify_anchors_report(research, client, monkeypatch, capsys, tmp_path):
    """ENG-10 / GAP-05: operators need a build/queue view and a full anchor re-check."""
    import json
    from urllib.parse import quote
    import sqlalchemy as sa
    from hermeneut.research import cli as research_cli
    with research.engine.connect() as connection:
        schema = connection.execute(sa.text('select current_schema()')).scalar()
    url = research.engine.url.render_as_string(hide_password=False)
    monkeypatch.setenv('HERMENEUT_DATABASE_URL', f'{url}?options={quote("-csearch_path=" + schema)}')
    monkeypatch.setenv('HERMENEUT_OBJECT_ROOT', str(tmp_path / 'objects'))
    path, _cid, aid = setup_workspace(research, client, '原文引文需要定位。')
    segments = research.get_segments(path.split('/')[-1], 'tester', aid)['segments']
    text = segments[0]['text']
    anchor = client.post(path + '/anchors', json={'segment_id': segments[0]['id'], 'start_codepoint': 0,
        'end_codepoint': 2, 'exact_quote': text[:2]}).json()
    monkeypatch.setattr('sys.argv', ['cli', 'doctor'])
    research_cli.main()
    doctor = json.loads(capsys.readouterr().out)
    assert 'workspace' in doctor['supported_job_kinds']
    assert doctor['object_backend'] == 'filesystem' and doctor['elasticsearch_url']
    assert doctor['schema_revision'] is None or str(doctor['schema_revision']).endswith('0003')
    report = tmp_path / 'anchors.json'
    monkeypatch.setattr('sys.argv', ['cli', 'verify-anchors', '--report', str(report)])
    research_cli.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary['anchors_total'] == 1 and summary['located'] == 1 and summary['problem_count'] == 0
    # A stored offset that no longer matches the immutable text must be reported, not trusted.
    with research.engine.begin() as c:
        c.execute(db.anchors.update().where(db.anchors.c.id == anchor['id']).values(exact_quote='错位引文'))
    research_cli.main()
    problems = json.loads(report.read_text(encoding='utf-8'))
    assert problems['problem_count'] == 1 and problems['located'] == 0
    assert problems['problems'][0]['reason'] == 'QUOTE_MISMATCH'


def test_backup_keeps_conversations_entities_and_decisions(research,client,tmp_path):
    from hermeneut.research.backup import backup
    import json
    path,_cid,_=setup_workspace(research,client)
    client.post(path+'/participants',json={'pseudonym':'备份','material_collection':True})
    destination=tmp_path/'archive'
    backup(research,destination)
    manifest=json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema']=='research_0004'
    assert manifest['tables']['r_conversations']['rows']==1
    assert manifest['tables']['r_entities']['rows']==1


def test_migration_mixed_consent_and_retained_json_original(research,tmp_path):
    import sqlite3
    import json
    from hermeneut.research.migration import migrate
    source=tmp_path/'legacy.db'
    original=tmp_path/'interview.json'
    original.write_text('{"old":"export"}',encoding='utf-8')
    with sqlite3.connect(source) as c:
        for table in ['projects','participants','documents']:
            c.execute(f'CREATE TABLE {table} (id TEXT, data TEXT)')
        c.execute('INSERT INTO projects VALUES (?,?)',('p',json.dumps({'id':'p','name':'混合授权'})))
        for who,withdrawn in [('valid',None),('withdrawn','2020-01-01T00:00:00Z')]:
            value={'id':who,'project_id':'p','pseudonym':who,'consent_scope':{},'withdrawn_at':withdrawn}
            c.execute('INSERT INTO participants VALUES (?,?)',(who,json.dumps(value)))
            text='已授权的访谈内容。' if who=='valid' else '已撤回的内容。'
            doc={'id':who+'-doc','project_id':'p','participant_id':who,'text':text,'origin':str(original)}
            c.execute('INSERT INTO documents VALUES (?,?)',(doc['id'],json.dumps(doc)))
    r=migrate(research,source,'tester',apply=True,source_roots=[tmp_path])
    pid=r['project_map']['p']
    materials=research.list_materials(pid,'tester')
    assert len(materials)==1
    assert research.objects.read(materials[0]['object_key'])==original.read_bytes()
    assert research.get_segments(pid,'tester',materials[0]['id'])['segments'][0]['text']=='已授权的访谈内容。'
    assert any(x['reason']=='PARTICIPANT_CONSENT_INACTIVE' for x in r['exceptions'])
    again=migrate(research,source,'tester',apply=True,source_roots=[tmp_path])
    assert again['already_present']==r['source_rows']
    assert again['operational_entities']==0
