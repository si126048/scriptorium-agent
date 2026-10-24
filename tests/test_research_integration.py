"""Set HERMENEUT_TEST_DATABASE_URL to a disposable PostgreSQL database.

Tests create and drop an isolated PostgreSQL schema. Elasticsearch tests additionally need
HERMENEUT_TEST_ELASTICSEARCH_URL pointing at a disposable local node.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace

import pytest

sa = pytest.importorskip('sqlalchemy')
pytest.importorskip('psycopg')

from fastapi.testclient import TestClient
from hermeneut.research import schema as db
from hermeneut.research.api import create_app
from hermeneut.research.config import ResearchSettings
from hermeneut.research.migration import migrate
from hermeneut.research.service import ResearchError, ResearchService, row, rows
from hermeneut.research.texts import build_tei
from hermeneut.research.worker import run_one


@pytest.fixture
def research(tmp_path):
    url = os.getenv('HERMENEUT_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Real PostgreSQL integration requires HERMENEUT_TEST_DATABASE_URL')
    name = 'test_research_' + db.uid()
    base = db.engine_for(url)
    with base.begin() as c:
        c.execute(sa.text(f'CREATE SCHEMA {name}'))
    engine = sa.create_engine(url, connect_args={'options': f'-csearch_path={name}'})
    db.metadata.create_all(engine)
    settings = replace(ResearchSettings.from_env(), database_url=url, object_root=tmp_path / 'objects',
                       elasticsearch_url=os.getenv('HERMENEUT_TEST_ELASTICSEARCH_URL', 'http://127.0.0.1:59200'),
                       api_key='test-key', principal='tester')
    service = ResearchService(engine, settings)
    try:
        yield service
    finally:
        engine.dispose()
        with base.begin() as c:
            c.execute(sa.text(f'DROP SCHEMA {name} CASCADE'))
        base.dispose()


@pytest.fixture
def client(research):
    with TestClient(create_app(research.settings, research.engine)) as c:
        c.headers['Authorization'] = 'Bearer test-key'
        yield c


def imported(s, text='甲😀e\u0301乙\n\n自由需要条件。'):
    project = s.create_project('tester', 'Research')
    j = s.import_material(project['id'], 'tester', text.encode('utf-8'), 'sample.txt', db.uid())
    assert run_one(s, j['id'])
    with s.engine.connect() as c:
        job = row(c, db.jobs, db.jobs.c.id == j['id'])
    assert job['state'] == 'succeeded', job.get('error')
    aid = j['payload']['asset_id']
    return project['id'], aid, s.get_segments(project['id'], 'tester', aid)['segments']


def test_import_idempotency_and_immutable_versions(research):
    s = research
    pid = s.create_project('tester', 'P')['id']
    first = s.import_material(pid, 'tester', b'original', 'a.txt', 'same')
    assert s.import_material(pid, 'tester', b'original', 'a.txt', 'same')['id'] == first['id']
    with pytest.raises(ResearchError, match='IDEMPOTENCY_CONFLICT'):
        s.import_material(pid, 'tester', b'changed', 'a.txt', 'same')
    run_one(s, first['id'])
    a = s.list_materials(pid, 'tester')[0]
    old = s.get_segments(pid, 'tester', a['id'])
    with s.engine.begin() as c:
        anchor = s.make_anchor(c, pid, old['segments'][0]['id'], 0, 8, 'original')
    s.revise_text(pid, 'tester', a['id'], build_tei(['changed'], 'A'), a['revision'])
    assert s.get_segments(pid, 'tester', a['id'], old['version']['id'])['segments'][0]['text'] == 'original'
    with s.engine.connect() as c:
        assert row(c, db.anchors, db.anchors.c.id == anchor['id'])['exact_quote'] == 'original'
    with pytest.raises(ResearchError, match='REVISION_CONFLICT'):
        s.revise_text(pid, 'tester', a['id'], build_tei(['again'], 'A'), a['revision'])


def test_codepoint_anchor_scope_and_revision_conflict(research, client):
    pid, _aid, segments = imported(research)
    path = f'/api/v2/projects/{pid}'
    anchor = client.post(path + '/anchors', json={'segment_id': segments[0]['id'],
        'start_codepoint': 1, 'end_codepoint': 4, 'exact_quote': '😀e\u0301'})
    assert anchor.status_code == 201, anchor.text
    bad = client.post(path + '/anchors', json={'segment_id': segments[0]['id'],
        'start_codepoint': 1, 'end_codepoint': 5, 'exact_quote': '😀e\u0301'})
    assert bad.status_code == 422
    payload = {'kind': 'annotation', 'payload': {'title': 'Note', 'text': 'My interpretation',
               'evidence_ids': [anchor.json()['id']]}}
    record = client.post(path + '/records', json=payload).json()
    payload['revision'] = 1
    assert client.put(path + '/records/' + record['id'], json=payload).status_code == 200
    assert client.put(path + '/records/' + record['id'], json=payload).status_code == 409
    assert len(client.get(path + '/records/' + record['id'] + '/history').json()) == 1
    with research.engine.begin() as c:
        c.execute(db.members.delete().where(db.members.c.project_id == pid))
    assert client.get(path + '/materials').status_code == 404
    assert client.get(path + '/anchors/' + anchor.json()['id']).status_code == 404


def test_lease_recovery_and_stale_worker_cannot_commit(research):
    s = research
    pid = s.create_project('tester', 'P')['id']
    j = s.import_material(pid, 'tester', b'text', 'a.txt', 'lease')
    old = s.claim_job(j['id'])
    with s.engine.begin() as c:
        c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(lease_until=0))
    new = s.claim_job(j['id'])
    assert old['lease_token'] != new['lease_token']
    with pytest.raises(ResearchError, match='JOB_NO_LONGER_OWNED'):
        s.process_job(old)
    s.process_job(new)
    assert len(s.list_materials(pid, 'tester')[0]['versions']) == 1


def test_cancelled_job_is_not_processed(research, client):
    s = research
    pid = s.create_project('tester', 'P')['id']
    j = s.import_material(pid, 'tester', b'text', 'a.txt', 'cancel')
    assert client.post(f'/api/v2/projects/{pid}/jobs/{j["id"]}/cancel').status_code == 200
    assert not run_one(s, j['id'])
    assert not s.list_materials(pid, 'tester')[0]['versions']


def test_demo_methods_have_provenance_no_automatic_transition(research, client):
    pid, _, segments = imported(research)
    path = f'/api/v2/projects/{pid}'
    for method in ('situating.v1', 'immanent_critique.v1', 'parallax.v1'):
        result = client.post(path + '/method-runs', headers={'Idempotency-Key': method}, json={
            'method_id': method, 'question': 'How is freedom used?', 'segment_ids': [s['id'] for s in segments],
            'provider_mode': 'demo'})
        assert result.status_code == 202, result.text
        run_one(research, result.json()['id'])
    records = client.get(path + '/records').json()
    assert len(records) == 3
    assert all(r['payload']['provider_mode'] == 'demo' for r in records)
    assert not any(r['kind'] == 'transition' for r in records)
    assert all(r['payload']['coverage'] for r in records)
    exported = client.get(path + '/export?format=md')
    assert exported.status_code == 200
    assert 'demo' in exported.text


def test_no_model_does_not_fallback_to_demo(research, client, monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    pid, _, segments = imported(research)
    result = client.post(f'/api/v2/projects/{pid}/method-runs', headers={'Idempotency-Key': 'live'}, json={
        'method_id': 'situating.v1', 'question': 'Question', 'segment_ids': [segments[0]['id']]})
    run_one(research, result.json()['id'])
    job = client.get(f'/api/v2/projects/{pid}/jobs/{result.json()["id"]}').json()
    assert job['state'] == 'failed'
    assert job['error'] == 'MODEL_NOT_CONFIGURED'


def test_withdrawal_removes_derived_history_and_stops_jobs(research, client):
    pid, aid, segments = imported(research, 'sensitive source')
    path = f'/api/v2/projects/{pid}'
    anchor = client.post(path + '/anchors', json={'segment_id': segments[0]['id'],
        'start_codepoint': 0, 'end_codepoint': 9, 'exact_quote': 'sensitive'}).json()
    r = client.post(path + '/records', json={'kind': 'annotation',
        'payload': {'text': 'derived', 'evidence_ids': [anchor['id']]}}).json()
    client.put(path + '/records/' + r['id'], json={'kind': 'annotation', 'revision': 1,
        'payload': {'text': 'modified without citation'}})
    pending = client.post(path + '/method-runs', headers={'Idempotency-Key': 'pending'}, json={
        'method_id': 'situating.v1', 'question': 'Q', 'segment_ids': [segments[0]['id']], 'provider_mode': 'demo'})
    assert client.delete(path + '/materials/' + aid).status_code == 200
    assert client.get(path + '/materials/' + aid + '/original').status_code == 404
    assert client.get(path + '/anchors/' + anchor['id']).status_code == 404
    assert client.get(path + '/records').json() == []
    # A queued snapshot must not resurrect withdrawn source data even if claimed later.
    run_one(research, pending.json()['id'])
    assert client.get(path + '/records').json() == []


def test_browser_history_import_idempotency_and_scope(research, client):
    pid = research.create_project('tester', 'P')['id']
    data = {'format': 'hermeneut-browser-history.v1', 'tasks': [
        {'id': 'task-1', 'messages': [{'role': 'user', 'content': 'old chat'}]}]}
    path = f'/api/v2/projects/{pid}'
    assert client.post(path + '/history-import', json=data).json()['imported'] == 1
    assert client.post(path + '/history-import', json=data).json()['imported'] == 0
    assert client.get(path + '/legacy').json()[0]['payload']['messages'][0]['content'] == 'old chat'
    assert client.post(path + '/history-import', json={'tasks': []}).status_code == 422


def test_full_legacy_project_migration_and_repeat(research, tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as c:
        c.executescript('CREATE TABLE projects(id TEXT,data TEXT); CREATE TABLE documents(id TEXT,project_id TEXT,data TEXT);'
            'CREATE TABLE spans(id TEXT,document_id TEXT,data TEXT); CREATE TABLE runs(id TEXT,project_id TEXT,data TEXT);'
            'CREATE TABLE personas(id TEXT,project_id TEXT,data TEXT);')
        c.execute('INSERT INTO projects VALUES(?,?)', ('old', json.dumps({'id': 'old', 'name': 'Legacy'})))
        c.execute('INSERT INTO documents VALUES(?,?,?)', ('doc', 'old', json.dumps({'text': 'unique quote', 'origin': 'missing.txt'})))
        c.execute('INSERT INTO spans VALUES(?,?,?)', ('span', 'doc', json.dumps({'excerpt': 'unique quote', 'char_start': 99})))
        c.execute('INSERT INTO runs VALUES(?,?,?)', ('run', 'old', json.dumps({'state': 'APPROVED'})))
        c.execute('INSERT INTO personas VALUES(?,?,?)', ('persona', 'old', json.dumps({'name': 'Existing'})))
    before = source.read_bytes()
    preview = migrate(None, source, 'tester')
    assert preview['dry_run']
    report = migrate(research, source, 'tester', apply=True)
    assert report['source_rows'] == report['accounted_source_rows'] == 5
    assert report['anchors_migrated'] == 1
    assert report['materials'][0]['status'] == 'succeeded'
    again = migrate(research, source, 'tester', apply=True)
    assert again['preserved'] == 0
    assert source.read_bytes() == before
    pid = report['project_map']['old']
    assert len(research.list_materials(pid, 'tester')) == 1
    with research.engine.connect() as c:
        assert len(rows(c, db.legacy, db.legacy.c.project_id == pid)) == 5


def test_unjustified_transition_rejected(research, client):
    pid = research.create_project('tester', 'P')['id']
    result = client.post(f'/api/v2/projects/{pid}/records', json={
        'kind': 'transition', 'payload': {'text': 'A more comprehensive synthesis'}})
    assert result.status_code == 422
    result = client.post(f'/api/v2/projects/{pid}/records', json={
        'kind': 'parallax', 'payload': {'status': 'candidate_gap', 'text': 'They disagree'}})
    assert result.status_code == 422


def test_real_elasticsearch_index_rebuild_and_revoke(research, client):
    if not os.getenv('HERMENEUT_TEST_ELASTICSEARCH_URL'):
        pytest.skip('Real Elasticsearch integration requires HERMENEUT_TEST_ELASTICSEARCH_URL')
    from hermeneut.research.search import ALIAS, client as es_client, rebuild, search, sync_one
    pid, aid, _ = imported(research, '自由需要条件。')
    assert sync_one(research)
    with es_client(research) as es:
        es.indices.refresh(index=ALIAS)
    assert search(research, pid, 'tester', '自由')['items']
    rebuild(research)
    assert search(research, pid, 'tester', '自由')['items']
    research.revoke(pid, 'tester', aid)
    # Immediate database check blocks stale index results, before async cleanup.
    assert search(research, pid, 'tester', '自由')['items'] == []
    assert sync_one(research)


def test_sse_resume_does_not_rerun_job(research, client):
    pid, _, _ = imported(research)
    with research.engine.connect() as c:
        job = rows(c, db.jobs, db.jobs.c.project_id == pid)[0]
        events = rows(c, db.events, db.events.c.job_id == job['id'])
    ordered = sorted(events, key=lambda x: (x['created_at'], x['id']))
    result = client.get(f'/api/v2/projects/{pid}/jobs/{job["id"]}/events',
        headers={'Last-Event-ID': ordered[-1]['id']})
    assert result.status_code == 200
    assert result.text == ''


def test_cross_project_evidence_is_rejected(research, client):
    _pid, _, segments = imported(research, 'source')
    other = research.create_project('tester', 'Other')['id']
    r = client.post(f'/api/v2/projects/{other}/anchors', json={'segment_id': segments[0]['id'],
        'start_codepoint': 0, 'end_codepoint': 6, 'exact_quote': 'source'})
    assert r.status_code == 404


def test_migration_repeated_quotes_require_verified_offsets(research, tmp_path):
    source = tmp_path / 'repeat.db'
    text = 'repeat\n\nrepeat'
    with sqlite3.connect(source) as c:
        c.executescript('CREATE TABLE projects(id TEXT,data TEXT); CREATE TABLE documents(id TEXT,project_id TEXT,data TEXT);'
            'CREATE TABLE spans(id TEXT,document_id TEXT,data TEXT);')
        c.execute('INSERT INTO projects VALUES(?,?)', ('p', '{}'))
        c.execute('INSERT INTO documents VALUES(?,?,?)', ('d', 'p', json.dumps({'text': text})))
        c.execute('INSERT INTO spans VALUES(?,?,?)', ('good', 'd', json.dumps({'excerpt': 'repeat', 'char_start': 8, 'char_end': 14})))
        c.execute('INSERT INTO spans VALUES(?,?,?)', ('ambiguous', 'd', json.dumps({'excerpt': 'repeat', 'char_start': 99, 'char_end': 105})))
    r = migrate(research, source, 'tester', apply=True)
    assert r['anchors_migrated'] == 1
    assert any(e['key'] == 'ambiguous' and e['reason'] == 'AMBIGUOUS_OR_MISSING_QUOTE' for e in r['exceptions'])


def test_valid_model_transition_creates_reviewable_graph(research, client, monkeypatch):
    from types import SimpleNamespace
    pid, _, segments = imported(research, 'A requires B but excludes B.')
    s = segments[0]
    citation = {'segment_id': s['id'], 'start_codepoint': 0, 'end_codepoint': len(s['text']), 'exact_quote': s['text']}
    result = {'summary': 'Candidate only', 'outcome': 'transition_candidate', 'immanent': {
        'position': 'A excludes B', 'criterion': 'A must realize its conditions', 'criterion_basis': 'reconstructed',
        'difficulty': 'A requires the B it excludes', 'difficulty_type': 'internal', 'citations': [citation],
        'proposed_position': 'A mediated by B', 'retained': 'A', 'negated': 'exclusion of B',
        'transition_reason': 'The stated condition must be accounted for'}}
    def create(**kwargs):
        assert '不可信' in kwargs['messages'][0]['content']
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setattr('hermeneut.llm.QwenProvider', lambda **kwargs: SimpleNamespace(
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), model='test-model', temperature=0))
    r = client.post(f'/api/v2/projects/{pid}/method-runs', headers={'Idempotency-Key': 'grounded'}, json={
        'method_id': 'immanent_critique.v1', 'question': 'Q', 'segment_ids': [s['id']]})
    run_one(research, r.json()['id'])
    with research.engine.connect() as c:
        j = row(c, db.jobs, db.jobs.c.id == r.json()['id'])
    assert j['state'] == 'succeeded', j['error']
    graph = client.get(f'/api/v2/projects/{pid}/graph/concept').json()
    assert any(edge['type'] == 'transition' for edge in graph['edges'])
    records = client.get(f'/api/v2/projects/{pid}/records').json()
    assert len([r for r in records if r['kind'] == 'transition']) == 1
    assert len([r for r in records if r['kind'] == 'position']) == 2


def test_revoked_import_key_cannot_republish_original(research):
    s = research
    pid = s.create_project('tester', 'P')['id']
    j = s.import_material(pid, 'tester', b'text', 'a.txt', 'one')
    run_one(s, j['id'])
    s.revoke(pid, 'tester', j['payload']['asset_id'])
    with pytest.raises(ResearchError, match='IDEMPOTENCY_KEY_RETIRED'):
        s.import_material(pid, 'tester', b'text', 'a.txt', 'one')
    assert s.list_materials(pid, 'tester') == []


def test_backup_restore_integrity_and_nonempty_refusal(research, tmp_path):
    from hermeneut.research.backup import backup, restore
    s = research
    pid, aid, _ = imported(s, 'archive source')
    destination = tmp_path / 'archive'
    backup(s, destination)
    with pytest.raises(ValueError, match='EMPTY_RESEARCH_SCHEMA'):
        restore(s, destination)
    # Isolate restore in a second disposable schema in the same test database.
    name = 'restore_' + db.uid()
    base = db.engine_for(s.settings.database_url)
    with base.begin() as c:
        c.execute(sa.text(f'CREATE SCHEMA {name}'))
    engine = sa.create_engine(s.settings.database_url, connect_args={'options': f'-csearch_path={name}'})
    db.metadata.create_all(engine)
    target = ResearchService(engine, replace(s.settings, object_root=tmp_path / 'restored-objects'))
    try:
        assert restore(target, destination)['status'] == 'restored'
        assert target.get_segments(pid, 'tester', aid)['segments'][0]['text'] == 'archive source'
        assert target.list_projects('tester')[0]['id'] == pid
        path = destination / 'r_projects.jsonl'
        path.write_text('tampered', encoding='utf-8')
        with pytest.raises(ValueError, match='CHECKSUM'):
            restore(target, destination)
    finally:
        engine.dispose()
        with base.begin() as c:
            c.execute(sa.text(f'DROP SCHEMA {name} CASCADE'))
        base.dispose()


def test_annotation_tei_export_matches_project_schema(research, client):
    from hermeneut.research.texts import project_tei
    pid, _, _ = imported(research)
    r = client.get(f'/api/v2/projects/{pid}/export?format=tei')
    assert r.status_code == 200
    assert project_tei(r.content)


def test_legacy_preservation_is_batched(research, tmp_path):
    source = tmp_path / 'batch.db'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE spans(id TEXT,document_id TEXT,data TEXT)')
        c.executemany('INSERT INTO spans VALUES(?,?,?)', [(str(i), 'missing', '{}') for i in range(1201)])
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    sa.event.listen(research.engine, 'before_cursor_execute', count)
    try:
        result = migrate(research, source, 'tester', apply=True)
        assert result['accounted_source_rows'] == 1201
        assert len(statements) < 50
    finally:
        sa.event.remove(research.engine, 'before_cursor_execute', count)


def test_bibliography_changes_do_not_rewrite_text_versions(research, client):
    pid, aid, _ = imported(research)
    a = research.list_materials(pid, 'tester')[0]
    path = f'/api/v2/projects/{pid}/materials/{aid}/bibliography'
    body = {'revision': a['revision'], 'metadata': {'title': 'Corrected title', 'translator': 'Researcher'}}
    assert client.put(path, json=body).status_code == 200
    assert client.put(path, json=body).status_code == 409
    updated = research.list_materials(pid, 'tester')[0]
    assert updated['versions'] == a['versions']
    assert updated['metadata']['title'] == 'Corrected title'


def test_restore_replays_withdrawal_after_old_backup(research, tmp_path):
    from hermeneut.research.backup import backup, restore
    s = research
    pid, aid, _ = imported(s, 'revoked private source')
    archive = tmp_path / 'before-withdrawal'
    backup(s, archive)
    s.revoke(pid, 'tester', aid)
    # Simulate loss of research tables while the independent deletion ledger survives.
    with s.engine.begin() as c:
        for table in reversed(db.metadata.sorted_tables):
            c.execute(table.delete())
    result = restore(s, archive)
    assert result['withdrawals_replayed'] == 1
    assert s.list_materials(pid, 'tester') == []
    with s.engine.connect() as c:
        assert not list(c.execute(db.segments.select()).mappings())
