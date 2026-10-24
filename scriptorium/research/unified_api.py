from __future__ import annotations

import json
from functools import wraps
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from . import schema as db
from .legacy_store import PostgresStore
from .service import ResearchError, row, rows
from .workspace import add_message, conversation, create_conversation, submit


class ConversationIn(BaseModel):
    title: str = Field(default='新研究', min_length=1, max_length=200)


class ConversationUpdate(BaseModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None
    workspace: dict | None = None


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    tool: Literal['ask', 'chat', 'research', 'theory', 'subject', 'persona'] = 'ask'
    asset_ids: list[str] = Field(default_factory=list, max_length=100)
    segment_ids: list[str] = Field(default_factory=list, max_length=2000)
    scope: list[dict] | None = Field(default=None, max_length=2000)
    provider_mode: Literal['live', 'demo'] = 'live'
    participant_id: str | None = None
    persona_id: str | None = None
    perspective_ids: list[str] = Field(default_factory=lambda: ['lacan', 'deleuze'])
    methods: list[Literal['situating.v1', 'immanent_critique.v1', 'parallax.v1']] = Field(default_factory=list)
    token_budget: int = Field(default=40000, ge=10000, le=1000000)


class DecisionIn(BaseModel):
    accept: bool
    additional_tokens: int = Field(default=40000, ge=0, le=1000000)


class ParticipantIn(BaseModel):
    pseudonym: str = Field(min_length=1, max_length=200)
    material_collection: bool = False
    profile_analysis: bool = False
    agent_simulation: bool = False
    expires_at: str | None = None


class InterviewIn(BaseModel):
    participant_id: str
    conversation_id: str
    config_id: str | None = None
    provider_mode: Literal['live', 'demo'] = 'live'


class TurnIn(BaseModel):
    question_id: str
    answer_text: str = Field(min_length=1, max_length=20000)


class PersonaIn(BaseModel):
    participant_id: str
    name: str = Field(min_length=1, max_length=200)


class BindIn(BaseModel):
    asset_ids: list[str]


def require_consent(store, participant_id, scope):
    p = store.get_participant(store.project_id, participant_id)
    raw = store.get('participant', participant_id)
    if not p or p.withdrawn_at or not p.consent_scope.is_active() or not (raw or {}).get('permissions', {}).get(scope):
        raise ResearchError('PARTICIPANT_CONSENT_REQUIRED', 403)
    return p


def install(app, service, identity):
    router = APIRouter(prefix='/api/v2/projects/{project_id}')

    def serialized_interview(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            s, iid = kwargs['s'], kwargs['iid']
            # Advisory lock spans the legacy state machine's individual store transactions.
            with s.engine.connect() as lock:
                key = 'interview:' + kwargs['project_id'] + ':' + iid
                lock.execute(sa.text('SELECT pg_advisory_lock(hashtextextended(:key, 0))'), {'key': key})
                try:
                    return fn(*args, **kwargs)
                finally:
                    lock.execute(sa.text('SELECT pg_advisory_unlock(hashtextextended(:key, 0))'), {'key': key})
        return wrapped

    def store_for(s, pid, principal):
        return PostgresStore(s, pid, principal)

    @router.get('/conversations')
    def conversations(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            return [dict(x) for x in c.execute(sa.select(db.conversations).where(
                db.conversations.c.project_id == project_id).order_by(db.conversations.c.created_at.desc())).mappings()]

    @router.post('/conversations', status_code=201)
    def new_conversation(project_id: str, body: ConversationIn, principal=Depends(identity), s=Depends(service)):
        return create_conversation(s, project_id, principal, body.title)

    @router.put('/conversations/{cid}')
    def update_conversation(project_id: str, cid: str, body: ConversationUpdate,
                            principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            old = conversation(s, c, project_id, cid)
            values = body.model_dump(exclude_none=True, exclude={'revision'})
            if len(json.dumps(values)) > 100000:
                raise ResearchError('WORKSPACE_TOO_LARGE', 413)
            if body.revision != old['revision']:
                raise ResearchError('REVISION_CONFLICT', 409)
            c.execute(db.conversations.update().where(db.conversations.c.id == cid).values(**values, revision=old['revision'] + 1))
            return {**old, **values, 'revision': old['revision'] + 1}

    @router.get('/conversations/{cid}/messages')
    def messages(project_id: str, cid: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            conversation(s, c, project_id, cid)
            return [dict(x) for x in c.execute(sa.select(db.messages).where(db.messages.c.conversation_id == cid)
                .order_by(db.messages.c.created_at, db.messages.c.id)).mappings()]

    @router.post('/conversations/{cid}/messages', status_code=202)
    def send(project_id: str, cid: str, body: SendIn, idempotency_key: str = Header(min_length=1, max_length=128),
             principal=Depends(identity), s=Depends(service)):
        if body.tool in {'subject', 'persona'}:
            store = store_for(s, project_id, principal)
            participant_id = body.participant_id
            if body.tool == 'persona':
                p = store.get_persona(body.persona_id or '')
                participant_id = (p or {}).get('participant_id')
            require_consent(store, participant_id, 'profile_analysis' if body.tool == 'subject' else 'agent_simulation')
        return submit(s, project_id, principal, cid, body.model_dump(), idempotency_key)

    @router.get('/research-runs')
    def research_runs(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            return rows(c, db.research_runs, db.research_runs.c.project_id == project_id)

    @router.get('/research-runs/{rid}')
    def research_run(project_id: str, rid: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            run = row(c, db.research_runs, db.research_runs.c.id == rid, db.research_runs.c.project_id == project_id)
            if not run:
                raise ResearchError('RUN_NOT_FOUND', 404)
            return {**run, 'steps': rows(c, db.research_steps, db.research_steps.c.run_id == rid)}

    @router.post('/research-runs/{rid}/cancel')
    def cancel_research(project_id: str, rid: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            run = row(c, db.research_runs, db.research_runs.c.id == rid, db.research_runs.c.project_id == project_id)
            if not run:
                raise ResearchError('RUN_NOT_FOUND', 404)
            for j in rows(c, db.jobs, db.jobs.c.project_id == project_id):
                if (j['payload'].get('resume_run_id') == rid or j['id'] == run['settings'].get('origin_job_id')
                        or j['idem'].startswith(rid + '-')) and j['state'] in {'queued', 'running'}:
                    c.execute(db.jobs.update().where(db.jobs.c.id == j['id']).values(state='cancel_requested'))
            c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='cancelled', reserved_tokens=0))
            c.execute(db.decisions.update().where(db.decisions.c.run_id == rid).values(state='cancelled'))
            return {'state': 'cancelled'}

    @router.get('/decisions')
    def decisions(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            return rows(c, db.decisions, db.decisions.c.project_id == project_id, db.decisions.c.state == 'pending')

    @router.post('/decisions/{did}')
    def answer_decision(project_id: str, did: str, body: DecisionIn, principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            d = row(c, db.decisions, db.decisions.c.id == did, db.decisions.c.project_id == project_id)
            if not d or d['state'] != 'pending':
                raise ResearchError('DECISION_ALREADY_ANSWERED', 409)
            run = row(c, db.research_runs, db.research_runs.c.id == d['run_id'])
            settings = run['settings']
            c.execute(db.decisions.update().where(db.decisions.c.id == did).values(state='answered', answer=body.model_dump()))
            if not body.accept:
                if d['kind'] == 'budget':
                    c.execute(db.research_runs.update().where(db.research_runs.c.id == run['id']).values(state='completed_with_open_questions'))
                    add_message(c, project_id, run['conversation_id'], 'assistant', '研究在当前范围结束，已有产物和未处理材料均保留。')
                    return {'state': 'completed_with_open_questions'}
            elif d['kind'] == 'budget':
                if body.additional_tokens <= 0:
                    raise ResearchError('ADDITIONAL_BUDGET_REQUIRED', 422)
                settings = {**settings, 'token_budget': settings['token_budget'] + body.additional_tokens}
                for child in rows(c, db.jobs, db.jobs.c.project_id == project_id):
                    if child['payload'].get('run_id') == run['id'] and child.get('error') == 'CALL_BUDGET_REQUIRED':
                        c.execute(db.jobs.update().where(db.jobs.c.id == child['id']).values(
                            state='queued', attempts=0, error=None, lease_until=None, lease_token=None))
            elif d['kind'] == 'reframe':
                settings = {**settings, 'original_question': settings.get('original_question', run['question'])}
                c.execute(db.research_runs.update().where(db.research_runs.c.id == run['id']).values(question=d['payload']['question']))
            elif d['kind'] == 'branch':
                if len(settings['nodes']) >= settings['max_nodes'] - 1:
                    raise ResearchError('NODE_LIMIT_REACHED', 409)
                settings = {**settings, 'nodes': [*settings['nodes'], d['payload']['proposal_key']]}
                branch = s.put_record(c, project_id, 'branch', {'title': d['payload']['question'],
                    'text': d['payload']['premise'], 'run_id': run['id'], 'status': 'researcher_accepted'})
                for i, window in enumerate(run['scope']):
                    for phase, method in enumerate(['situating.v1', 'immanent_critique.v1', 'parallax.v1', 'review.v1']):
                        c.execute(db.research_steps.insert().values(id=db.uid(), run_id=run['id'],
                            step_key=f'branch/{branch["id"]}/{i:05d}/{phase}/0', state='queued',
                            payload={'window': window, 'method_id': method, 'round': 0,
                                     'question': d['payload']['question'], 'premise': d['payload']['premise']}, created_at=db.now()))
            c.execute(db.research_runs.update().where(db.research_runs.c.id == run['id']).values(settings=settings, state='running'))
            return s.enqueue(c, project_id, 'workspace', {'tool': 'research', 'text': run['question'],
                'principal': principal, 'conversation_id': run['conversation_id'], 'resume_run_id': run['id']}, f'resume-{did}')

    @router.get('/artifacts/{aid}')
    def artifact(project_id: str, aid: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            value = row(c, db.records, db.records.c.id == aid, db.records.c.project_id == project_id)
            if not value:
                raise ResearchError('ARTIFACT_NOT_FOUND', 404)
            s.validate_evidence(c, project_id, value['payload'])
            return value

    @router.get('/participants')
    def participants(project_id: str, principal=Depends(identity), s=Depends(service)):
        return store_for(s, project_id, principal).all('participant')

    @router.post('/materials/{asset_id}/ocr', status_code=202)
    def ocr(project_id: str, asset_id: str, language: str = 'chi_sim+eng', engine: str = 'auto',
            principal=Depends(identity), s=Depends(service)):
        import re
        from .texts import OCR_ENGINES
        if not re.fullmatch(r'[a-z_+]{1,100}', language):
            raise ResearchError('INVALID_OCR_LANGUAGE', 422)
        if engine not in OCR_ENGINES:
            raise ResearchError('INVALID_OCR_ENGINE', 422)
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            a = s.asset(c, project_id, asset_id)
            if not a['name'].lower().endswith('.pdf'):
                raise ResearchError('OCR_REQUIRES_PDF', 422)
            return s.enqueue(c, project_id, 'ocr',
                             {'asset_id': asset_id, 'language': language, 'engine': engine}, db.uid())

    @router.get('/analysis-runs')
    def old_analyses(project_id: str, principal=Depends(identity), s=Depends(service)):
        return store_for(s, project_id, principal).all('analysis_run')

    @router.get('/analysis-runs/{run_id}')
    def old_analysis(project_id: str, run_id: str, principal=Depends(identity), s=Depends(service)):
        value = store_for(s, project_id, principal).get('analysis_run', run_id)
        if not value:
            raise ResearchError('RUN_NOT_FOUND', 404)
        return value

    @router.get('/analysis-runs/{run_id}/export')
    def old_analysis_export(project_id: str, run_id: str, principal=Depends(identity), s=Depends(service)):
        from scriptorium.workflow import Workflow
        return Workflow(PostgresStore(s, project_id, principal, corpus=True)).export(run_id)

    @router.post('/analysis-runs/{run_id}/artifact', status_code=201)
    def analysis_artifact(project_id: str, run_id: str, principal=Depends(identity), s=Depends(service)):
        result = store_for(s, project_id, principal).get('analysis_run', run_id)
        if not result:
            raise ResearchError('RUN_NOT_FOUND', 404)
        packet = result.get('packet') or {}
        lines = []
        evidence = []
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            for old in rows(c, db.records, db.records.c.project_id == project_id):
                if old['payload'].get('legacy_run_id') == run_id:
                    return old
            for group, label in [('observations', '材料观察'), ('hypotheses', '解释假说'),
                                 ('narrative_operators', '论证组织')]:
                for item in packet.get(group, []):
                    text = item.get('description') or item.get('claim') or item.get('statement') or item.get('text') or item.get('label')
                    if text:
                        lines.extend([f'### {label}', str(text)])
                    for sid in item.get('evidence_span_ids', []):
                        link = row(c, db.legacy, db.legacy.c.project_id == project_id,
                                   db.legacy.c.table_name == 'spans', db.legacy.c.legacy_key == sid)
                        if link and link['status'].startswith('anchor:'):
                            aid = link['status'][7:]
                            if row(c, db.anchors, db.anchors.c.id == aid):
                                evidence.append(aid)
            return s.put_record(c, project_id, 'method_report', {'title': '历史分析 · ' + run_id[:18],
                'text': '\n\n'.join(lines) or '历史记录未形成可阅读结论；保留原有业务状态，可继续评议与导出。',
                'evidence_ids': list(dict.fromkeys(evidence)), 'legacy_run_id': run_id,
                'status': result.get('state', 'historical'), 'provider_mode': 'human',
                'coverage_note': '历史结果原样转录，未重新生成；未定位的引用不标为已核验。'})

    @router.get('/personas/{persona_id}/artifacts')
    def persona_artifacts(project_id: str, persona_id: str, principal=Depends(identity), s=Depends(service)):
        store = store_for(s, project_id, principal)
        persona = store.get_persona(persona_id)
        if not persona:
            raise ResearchError('PERSONA_NOT_FOUND', 404)
        require_consent(store, persona['participant_id'], 'agent_simulation')
        return store.list_persona_artifacts(persona_id)

    def save_participant(pid, principal, s, body, participant_id=None):
        from scriptorium.models import Participant, ConsentScope
        if not body.material_collection:
            raise ResearchError('COLLECTION_CONSENT_REQUIRED', 422)
        p = Participant(id=participant_id or db.uid(), project_id=pid, pseudonym=body.pseudonym,
                        consent_scope=ConsentScope(expires_at=body.expires_at))
        value = {**p.model_dump(mode='json'), 'permissions': {
            'material_collection': body.material_collection, 'profile_analysis': body.profile_analysis,
            'agent_simulation': body.agent_simulation}}
        store_for(s, pid, principal).put('participant', value)
        return value

    @router.post('/participants', status_code=201)
    def new_participant(project_id: str, body: ParticipantIn, principal=Depends(identity), s=Depends(service)):
        return save_participant(project_id, principal, s, body)

    @router.put('/participants/{participant_id}')
    def participant_consent(project_id: str, participant_id: str, body: ParticipantIn,
                            principal=Depends(identity), s=Depends(service)):
        if not store_for(s, project_id, principal).get_participant(project_id, participant_id):
            raise ResearchError('PARTICIPANT_NOT_FOUND', 404)
        return save_participant(project_id, principal, s, body, participant_id)

    @router.post('/participants/{participant_id}/materials')
    def bind_material(project_id: str, participant_id: str, body: BindIn,
                      principal=Depends(identity), s=Depends(service)):
        require_consent(store_for(s, project_id, principal), participant_id, 'material_collection')
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            for aid in body.asset_ids:
                a = s.asset(c, project_id, aid)
                if a['metadata'].get('participant_id') not in {None, participant_id}:
                    raise ResearchError('MATERIAL_ALREADY_ASSIGNED', 409)
                c.execute(db.assets.update().where(db.assets.c.id == aid).values(
                    metadata={**a['metadata'], 'participant_id': participant_id}))
        return {'assigned': len(body.asset_ids)}

    @router.post('/participants/{participant_id}/withdraw')
    def withdraw(project_id: str, participant_id: str, principal=Depends(identity), s=Depends(service)):
        from datetime import UTC, datetime
        store = store_for(s, project_id, principal)
        p = store.get('participant', participant_id)
        if not p:
            raise ResearchError('PARTICIPANT_NOT_FOUND', 404)
        p.update(withdrawn_at=datetime.now(UTC).isoformat(), permissions={})
        p['consent_scope']['withdrawn_at'] = p['withdrawn_at']
        store.put('participant', p)
        for a in s.list_materials(project_id, principal):
            if a['metadata'].get('participant_id') == participant_id:
                s.revoke(project_id, principal, a['id'])
        for persona in store.list_personas(project_id, participant_id):
            store.delete_persona(persona['id'])
        for interview in store.all('interview'):
            if interview['participant_id'] == participant_id:
                interview.update(state='WITHDRAWN', turns=[], current_question_id=None, current_question_text=None)
                store.put('interview', interview)
        return {'state': 'withdrawn'}

    def interview_manager(s, pid, principal, mode='live'):
        from scriptorium.interview import InterviewManager
        from .capabilities import provider
        class FixedQuestions:
            def generate_structured(self, *args):
                return {'should_follow_up': False, 'question_text': '', 'reason': 'Fixed questions only', 'tags': []}
        import os
        p = provider(mode) if mode == 'demo' or os.getenv('DASHSCOPE_API_KEY') else FixedQuestions()
        return InterviewManager(store_for(s, pid, principal), p)

    @router.get('/interviews')
    def interviews(project_id: str, principal=Depends(identity), s=Depends(service)):
        return store_for(s, project_id, principal).all('interview')

    @router.post('/interviews', status_code=201)
    def new_interview(project_id: str, body: InterviewIn, principal=Depends(identity), s=Depends(service)):
        require_consent(store_for(s, project_id, principal), body.participant_id, 'material_collection')
        with s.engine.connect() as c:
            conversation(s, c, project_id, body.conversation_id)
        manager = interview_manager(s, project_id, principal, body.provider_mode)
        session, _ = manager.create(project_id, body.participant_id, body.config_id)
        manager.store.put('interview_settings', {'id': session.id, 'conversation_id': body.conversation_id, 'provider_mode': body.provider_mode})
        view = manager.view(session.id, project_id, body.participant_id)
        with s.engine.begin() as c:
            add_message(c, project_id, body.conversation_id, 'assistant', view['current_question']['text'],
                        metadata={'interview_id': session.id, 'question_id': view['current_question']['id']})
        return view

    def get_interview(s, pid, principal, iid):
        store = store_for(s, pid, principal)
        session = store.get_interview_session(iid, pid)
        if not session:
            raise ResearchError('INTERVIEW_NOT_FOUND', 404)
        require_consent(store, session.participant_id, 'material_collection')
        settings = store.get('interview_settings', iid) or {}
        return interview_manager(s, pid, principal, settings.get('provider_mode', 'live')), session, settings

    @router.get('/interviews/{iid}')
    def interview(project_id: str, iid: str, principal=Depends(identity), s=Depends(service)):
        m, session, settings = get_interview(s, project_id, principal, iid)
        return {**m.view(iid, project_id, session.participant_id), 'conversation_id': settings.get('conversation_id')}

    @router.post('/interviews/{iid}/turns')
    @serialized_interview
    def turn(project_id: str, iid: str, body: TurnIn, principal=Depends(identity), s=Depends(service)):
        m, session, settings = get_interview(s, project_id, principal, iid)
        result = m.submit(iid, project_id, session.participant_id, body.question_id, body.answer_text)
        if settings.get('conversation_id'):
            with s.engine.begin() as c:
                add_message(c, project_id, settings['conversation_id'], 'user', body.answer_text, metadata={'interview_id': iid})
                add_message(c, project_id, settings['conversation_id'], 'assistant',
                    (result.get('current_question') or {}).get('text') or '访谈问题已完成，可以生成研究材料。',
                    metadata={'interview_id': iid})
        return result

    @router.post('/interviews/{iid}/{action}')
    @serialized_interview
    def interview_action(project_id: str, iid: str, action: Literal['pause', 'resume', 'complete', 'withdraw', 'reset'],
                         principal=Depends(identity), s=Depends(service)):
        m, session, settings = get_interview(s, project_id, principal, iid)
        if action == 'complete':
            if session.state.value == 'COMPLETED' and settings.get('material_job_id'):
                return {'job_id': settings['material_job_id']}
            _, result = m.complete(iid, project_id, session.participant_id)
            text = '\n\n'.join(f'问：{t["question_text"]}\n答：{t["answer_text"]}' for t in result['turns'])
            j = s.import_material(project_id, principal, text.encode('utf-8'), f'interview-{iid}.md', iid,
                                  {'participant_id': session.participant_id, 'interview_id': iid})
            m.store.put('interview_settings', {'id': iid, **settings, 'material_job_id': j['id']})
            return {'job_id': j['id']}
        if action == 'reset':
            _, fresh = m.reset(iid, project_id, session.participant_id)
            m.store.put('interview_settings', {**settings, 'id': fresh.id})
            return m.view(fresh.id, project_id, session.participant_id)
        return getattr(m, action)(iid, project_id, session.participant_id)

    @router.get('/personas')
    def personas(project_id: str, principal=Depends(identity), s=Depends(service)):
        return store_for(s, project_id, principal).list_personas(project_id)

    @router.post('/personas', status_code=201)
    def new_persona(project_id: str, body: PersonaIn, principal=Depends(identity), s=Depends(service)):
        from scriptorium.topostyle.service import create_persona
        store = store_for(s, project_id, principal)
        require_consent(store, body.participant_id, 'agent_simulation')
        return create_persona(store, project_id, body.participant_id, body.name)

    @router.post('/personas/{persona_id}/train', status_code=202)
    def train(project_id: str, persona_id: str, principal=Depends(identity), s=Depends(service)):
        store = store_for(s, project_id, principal)
        persona = store.get_persona(persona_id)
        if not persona:
            raise ResearchError('PERSONA_NOT_FOUND', 404)
        require_consent(store, persona['participant_id'], 'agent_simulation')
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            return s.enqueue(c, project_id, 'persona_train', {'persona_id': persona_id, 'principal': principal}, db.uid())

    @router.delete('/personas/{persona_id}')
    def delete_persona(project_id: str, persona_id: str, principal=Depends(identity), s=Depends(service)):
        store_for(s, project_id, principal).delete_persona(persona_id)
        return {'state': 'deleted'}

    @router.get('/perspectives')
    def perspectives(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
        from scriptorium.perspectives import list_perspectives
        return [p.model_dump(mode='json') for p in list_perspectives()]

    @router.post('/analysis-runs/{run_id}/reviews')
    def review(project_id: str, run_id: str, body: dict, principal=Depends(identity), s=Depends(service)):
        from scriptorium.workflow import Workflow
        from scriptorium.models import ReviewRequest
        store = PostgresStore(s, project_id, principal, corpus=True)
        return Workflow(store).review(run_id, ReviewRequest.model_validate({**body, 'reviewer_id': principal})).model_dump(mode='json')

    app.include_router(router)
