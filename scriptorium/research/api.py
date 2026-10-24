"""Independent v2 API; importing it does not open or mutate the legacy database."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import schema as db
from .config import ResearchSettings
from .methods import PROTOCOLS
from .service import ResearchError, ResearchService, SUPPORTED_JOB_KINDS, row, rows

from .contracts import ProjectOut, RecordOut, MaterialOut, AnchorOut, JobOut

SERVICE_VERSION = '4.0.0-dev'

KINDS = Literal['question', 'annotation', 'concept', 'context', 'claim', 'position', 'criterion',
    'difficulty', 'transition', 'standpoint', 'appearance', 'shift', 'parallax', 'branch',
    'objection', 'response', 'manuscript', 'review', 'method_report', 'research_answer']


class ModelKeyIn(BaseModel):
    key: str | None = Field(default=None, max_length=1024)
    provider: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=10000)


class AnchorIn(BaseModel):
    segment_id: str
    start_codepoint: int = Field(ge=0)
    end_codepoint: int = Field(gt=0)
    exact_quote: str = Field(min_length=1, max_length=100000)


class PayloadShape(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: str = Field(default='', max_length=1000)
    text: str = Field(default='', max_length=100000)
    status: str = Field(default='draft', max_length=96)
    provider_mode: Literal['live', 'demo', 'human'] = 'human'
    evidence_ids: list[str] = Field(default_factory=list, max_length=200)
    source_record_ids: list[str] = Field(default_factory=list, max_length=200)
    dimensions: dict[str, str] = Field(default_factory=dict)
    findings: list[dict] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    coverage: list[dict] = Field(default_factory=list)


class RecordIn(BaseModel):
    kind: KINDS
    payload: dict
    revision: int | None = Field(default=None, ge=1)

    @field_validator('payload')
    @classmethod
    def validate_payload(cls, value):
        PayloadShape.model_validate(value)
        for finding in value.get('findings', []):
            if not isinstance(finding.get('title'), str) or not isinstance(finding.get('text'), str):
                raise ValueError('INVALID_FINDING')
            if not isinstance(finding.get('evidence_ids', []), list):
                raise ValueError('INVALID_FINDING_EVIDENCE')
        return value


class RevisionIn(BaseModel):
    revision: int = Field(ge=1)
    tei: str = Field(min_length=1, max_length=10000000)


class BibliographyIn(BaseModel):
    revision: int = Field(ge=1)
    metadata: dict[str, str]

    @field_validator('metadata')
    @classmethod
    def bibliography_fields(cls, value):
        allowed = {'title', 'author', 'translator', 'language', 'publication_date', 'edition_description', 'source_note', 'purpose'}
        if set(value) - allowed or any(len(v) > 2000 for v in value.values()):
            raise ValueError('INVALID_BIBLIOGRAPHY')
        return value


class MethodIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    method_id: Literal['situating.v1', 'immanent_critique.v1', 'parallax.v1']
    question: str = Field(min_length=1, max_length=10000)
    segment_ids: list[str] = Field(min_length=1, max_length=200)
    provider_mode: Literal['live', 'demo'] = 'live'
    max_input_chars: int = Field(default=30000, ge=100, le=60000)
    max_output_tokens: int = Field(default=4000, ge=256, le=8000)


def create_app(settings=None, engine=None):
    settings = settings or ResearchSettings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        owned = engine is None
        db_engine = engine or db.engine_for(settings.database_url)
        app.state.research = ResearchService(db_engine, settings)
        try:
            yield
        finally:
            if owned:
                db_engine.dispose()

    app = FastAPI(title='Scriptorium Research', version=SERVICE_VERSION, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
        allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
        allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key', 'Last-Event-ID'], allow_credentials=True)

    @app.exception_handler(ResearchError)
    async def research_error(request, exc):
        return JSONResponse({'detail': exc.code}, status_code=exc.status)

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse({'detail': str(exc).split(':')[0][:128]}, status_code=422)

    def service(request: Request):
        return request.app.state.research

    def identity(request: Request, authorization: str = Header(default='')):
        from .auth import principal as authenticate
        actor = authenticate(request, settings, request.app.state.research, authorization)
        if actor:
            request.state.principal = actor
            return actor
        if settings.api_key:
            if not secrets.compare_digest(authorization, f'Bearer {settings.api_key}'):
                raise HTTPException(401, 'Invalid research API key')
        else:
            if request.client is None or request.client.host not in {'127.0.0.1', '::1', 'localhost', 'testclient'}:
                raise HTTPException(403, 'Remote access requires SCRIPTORIUM_RESEARCH_API_KEY')
            origin = request.headers.get('origin')
            own_origin = str(request.base_url).rstrip('/') if request.url.hostname in {'127.0.0.1', 'localhost', '::1'} else ''
            if origin and origin.rstrip('/') not in {*settings.allowed_origins, own_origin}:
                raise HTTPException(403, 'Origin not allowed')
        # Identity is server configured; an arbitrary client header cannot impersonate a member.
        request.state.principal = settings.principal
        return settings.principal

    def admin(principal=Depends(identity)):
        from .governance import administrator
        if not administrator(principal, settings):
            raise ResearchError('SYSTEM_ADMIN_REQUIRED', 403)
        return principal

    @app.middleware('http')
    async def audit_write(request, call_next):
        response = await call_next(request)
        actor = getattr(request.state, 'principal', None)
        parts = request.url.path.split('/')
        if actor and request.method not in {'GET', 'HEAD', 'OPTIONS'} and response.status_code < 400 and len(parts) > 4 and parts[1:4] == ['api', 'v2', 'projects']:
            from .governance import audit
            with request.app.state.research.engine.begin() as c:
                audit(c, parts[4], actor, 'http.' + request.method.lower(), parts[-1][:128], {'path': request.url.path[:500]})
        return response

    @app.get('/health')
    def health(s=Depends(service)):
        with s.engine.connect() as c:
            c.execute(sa.select(db.projects.c.id).limit(1))
        # Kind list lets an operator compare API and Worker builds before queueing new work.
        return {'status': 'ok', 'service': 'research', 'version': SERVICE_VERSION,
                'search': 'enabled' if str(s.settings.elasticsearch_url or '').strip() else 'disabled',
                'job_kinds': sorted(SUPPORTED_JOB_KINDS)}

    @app.get('/api/v2/system/status')
    def system_status(principal=Depends(identity), s=Depends(service)):
        return {'service': 'research', 'version': SERVICE_VERSION, 'principal': principal,
                **s.queue_status()}

    @app.get('/api/v2/system/model')
    def model_status(principal=Depends(identity)):
        """Provider catalogue and key state. Secrets are never returned, only their source."""
        from .providers import public
        from .governance import administrator
        return {**public(), 'editable': administrator(principal, settings)}

    @app.put('/api/v2/system/model')
    def model_config(body: ModelKeyIn, principal=Depends(admin)):
        from . import providers
        provider_id = body.provider or providers.active_id()
        if body.key:
            providers.save_key(provider_id, body.key)
        return providers.update(provider=provider_id, base_url=body.base_url, model=body.model)

    @app.delete('/api/v2/system/model')
    def model_delete(provider: str | None = None, principal=Depends(admin)):
        from . import providers
        return providers.delete_key(provider or providers.active_id())

    @app.post('/api/v2/system/model/test')
    def model_test(provider: str | None = None, principal=Depends(admin)):
        from . import providers
        return providers.probe(provider)

    @app.get('/api/v2/methods')
    def methods(principal=Depends(identity)):
        return PROTOCOLS

    @app.get('/api/v2/projects', response_model=list[ProjectOut])
    def projects(principal=Depends(identity), s=Depends(service)):
        return s.list_projects(principal)

    @app.post('/api/v2/projects', status_code=201, response_model=ProjectOut)
    def create_project(body: ProjectIn, principal=Depends(identity), s=Depends(service)):
        return s.create_project(principal, body.name, body.description)

    prefix = '/api/v2/projects/{project_id}'

    @app.post(prefix + '/imports', status_code=202, response_model=JobOut, response_model_exclude_unset=True)
    async def import_material(project_id: str, file: UploadFile = File(...),
        idempotency_key: str = Header(min_length=1, max_length=128), principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal, True)
        raw = await file.read(settings.max_upload_bytes + 1)
        return s.import_material(project_id, principal, raw, file.filename or 'material.txt', idempotency_key)

    @app.get(prefix + '/materials', response_model=list[MaterialOut], response_model_exclude_unset=True)
    def materials(project_id: str, principal=Depends(identity), s=Depends(service)):
        return s.list_materials(project_id, principal)

    @app.get(prefix + '/materials/{asset_id}/segments')
    def segments(project_id: str, asset_id: str, version_id: str | None = None,
                 principal=Depends(identity), s=Depends(service)):
        return s.get_segments(project_id, principal, asset_id, version_id)

    @app.put(prefix + '/materials/{asset_id}/bibliography')
    def bibliography(project_id: str, asset_id: str, body: BibliographyIn,
                     principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            c.execute(sa.select(db.assets.c.id).where(db.assets.c.id == asset_id).with_for_update())
            a = s.asset(c, project_id, asset_id)
            if a['revision'] != body.revision:
                raise ResearchError('REVISION_CONFLICT', 409)
            metadata = {**a['metadata'], **body.metadata, 'bibliography_responsibility': principal}
            c.execute(db.assets.update().where(db.assets.c.id == asset_id).values(metadata=metadata, revision=a['revision'] + 1))
            edition = row(c, db.editions, db.editions.c.id == a['edition_id'])
            c.execute(db.editions.update().where(db.editions.c.id == a['edition_id']).values(
                metadata={**edition['metadata'], **body.metadata, 'responsibility': principal}))
            if body.metadata.get('title'):
                c.execute(db.works.update().where(db.works.c.id == edition['work_id']).values(title=body.metadata['title']))
            c.execute(db.outbox.insert().values(id=db.uid(), project_id=project_id, asset_id=asset_id,
                revision=a['revision'] + 1, done=False, attempts=0, created_at=db.now()))
        return {'revision': a['revision'] + 1, 'metadata': metadata}

    @app.get(prefix + '/materials/{asset_id}/original')
    def original(project_id: str, asset_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            a = s.asset(c, project_id, asset_id)
            raw = s.objects.read(a['object_key'])
        return Response(raw, media_type='application/octet-stream', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + __import__('urllib.parse', fromlist=['quote']).quote(a['name']),
            'Cache-Control': 'no-store'})

    @app.get(prefix + '/materials/{asset_id}/tei')
    def tei(project_id: str, asset_id: str, version_id: str | None = None,
            principal=Depends(identity), s=Depends(service)):
        result = s.get_segments(project_id, principal, asset_id, version_id)
        return Response(s.objects.read(result['version']['object_key']), media_type='application/xml',
                        headers={'Cache-Control': 'no-store'})

    @app.post(prefix + '/materials/{asset_id}/revisions', status_code=201)
    def revision(project_id: str, asset_id: str, body: RevisionIn, principal=Depends(identity), s=Depends(service)):
        return {'version_id': s.revise_text(project_id, principal, asset_id, body.tei.encode('utf-8'), body.revision)}

    @app.delete(prefix + '/materials/{asset_id}')
    def revoke(project_id: str, asset_id: str, principal=Depends(identity), s=Depends(service)):
        s.revoke(project_id, principal, asset_id)
        return {'status': 'revoked', 'physical_cleanup': 'run gc after retention; backups follow documented retention'}

    @app.post(prefix + '/anchors', status_code=201, response_model=AnchorOut)
    def anchor(project_id: str, body: AnchorIn, principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            return s.make_anchor(c, project_id, body.segment_id,
                                 body.start_codepoint, body.end_codepoint, body.exact_quote)

    @app.get(prefix + '/anchors/{anchor_id}')
    def locate(project_id: str, anchor_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            a = row(c, db.anchors, db.anchors.c.id == anchor_id, db.anchors.c.project_id == project_id)
            if not a:
                raise ResearchError('ANCHOR_NOT_FOUND', 404)
            segment = row(c, db.segments, db.segments.c.id == a['segment_id'])
            s.asset(c, project_id, segment['asset_id'])
            return {**a, 'segment': segment}

    @app.get(prefix + '/records', response_model=list[RecordOut], response_model_exclude_unset=True)
    def records(project_id: str, kind: KINDS | None = None, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            filters = [db.records.c.project_id == project_id]
            if kind:
                filters.append(db.records.c.kind == kind)
            return rows(c, db.records, *filters)

    def save(project_id, body, principal, s, record_id=None):
        if len(json.dumps(body.payload)) > 200000:
            raise ResearchError('RECORD_TOO_LARGE', 413)
        if not isinstance(body.payload.get('text', ''), str) or not isinstance(body.payload.get('evidence_ids', []), list):
            raise ResearchError('INVALID_RECORD_PAYLOAD', 422)
        payload = {**body.payload, 'author_id': principal}
        if payload.get('editor_json') is not None:
            from .documents import validate_editor, markdown
            validate_editor(payload['editor_json'])
            payload['text'] = markdown(payload['editor_json'])
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            if record_id and body.revision is None:
                raise ResearchError('REVISION_REQUIRED', 422)
            return s.put_record(c, project_id, body.kind, payload, record_id, body.revision)

    @app.post(prefix + '/records', status_code=201, response_model=RecordOut, response_model_exclude_unset=True)
    def new_record(project_id: str, body: RecordIn, principal=Depends(identity), s=Depends(service)):
        return save(project_id, body, principal, s)

    @app.put(prefix + '/records/{record_id}', response_model=RecordOut, response_model_exclude_unset=True)
    def update_record(project_id: str, record_id: str, body: RecordIn, principal=Depends(identity), s=Depends(service)):
        return save(project_id, body, principal, s, record_id)

    @app.get(prefix + '/records/{record_id}/history')
    def history(project_id: str, record_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            if not row(c, db.records, db.records.c.id == record_id, db.records.c.project_id == project_id):
                raise ResearchError('RECORD_NOT_FOUND', 404)
            return rows(c, db.record_history, db.record_history.c.record_id == record_id)

    @app.post(prefix + '/method-runs', status_code=202)
    def method_run(project_id: str, body: MethodIn, idempotency_key: str = Header(min_length=1, max_length=128),
                   principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            for sid in body.segment_ids:
                segment = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == project_id)
                if not segment:
                    raise ResearchError('SEGMENT_NOT_FOUND', 404)
                s.asset(c, project_id, segment['asset_id'])
            return s.enqueue(c, project_id, 'method', body.model_dump(), idempotency_key)

    @app.get(prefix + '/jobs')
    def jobs(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            return [dict(r) for r in c.execute(sa.select(db.jobs).where(db.jobs.c.project_id == project_id)
                .order_by(db.jobs.c.created_at.desc()).limit(100)).mappings()]

    @app.get(prefix + '/jobs/{job_id}', response_model=JobOut, response_model_exclude_unset=True)
    def get_job(project_id: str, job_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            j = row(c, db.jobs, db.jobs.c.id == job_id, db.jobs.c.project_id == project_id)
            if not j:
                raise ResearchError('JOB_NOT_FOUND', 404)
            return j

    @app.post(prefix + '/jobs/{job_id}/cancel')
    def cancel(project_id: str, job_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            c.execute(sa.select(db.jobs.c.id).where(db.jobs.c.id == job_id).with_for_update())
            j = row(c, db.jobs, db.jobs.c.id == job_id, db.jobs.c.project_id == project_id)
            if not j:
                raise ResearchError('JOB_NOT_FOUND', 404)
            if j['state'] not in {'succeeded', 'failed', 'cancelled'}:
                state = 'cancelled' if j['state'] == 'queued' else 'cancel_requested'
                c.execute(db.jobs.update().where(db.jobs.c.id == job_id).values(state=state))
                s.event(c, job_id, {'state': state})
        return {'status': 'cancel_requested'}

    @app.post(prefix + '/jobs/{job_id}/retry')
    def retry(project_id: str, job_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            j = row(c, db.jobs, db.jobs.c.id == job_id, db.jobs.c.project_id == project_id)
            if not j or j['state'] != 'failed':
                raise ResearchError('FAILED_JOB_REQUIRED', 409)
            if j['kind'] == 'import':
                s.asset(c, project_id, j['payload']['asset_id'])
            c.execute(db.jobs.update().where(db.jobs.c.id == job_id).values(
                state='queued', attempts=0, lease_until=None, lease_token=None, error=None))
            s.event(c, job_id, {'state': 'queued', 'reason': 'manual_retry'})
        return {'status': 'queued'}

    @app.get(prefix + '/jobs/{job_id}/events')
    async def job_events(project_id: str, job_id: str, request: Request,
        last_event_id: str = Header(default=''), principal=Depends(identity), s=Depends(service)):
        get_job(project_id, job_id, principal, s)
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            prior = row(c, db.events, db.events.c.id == last_event_id, db.events.c.job_id == job_id) if last_event_id else None
        cursor = (prior['created_at'], prior['id']) if prior else (0, '')

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                with s.engine.connect() as c:
                    s.access(c, project_id, principal)
                    result = c.execute(sa.select(db.events).where(db.events.c.job_id == job_id,
                        sa.or_(db.events.c.created_at > cursor[0], sa.and_(db.events.c.created_at == cursor[0],
                        db.events.c.id > cursor[1]))).order_by(db.events.c.created_at, db.events.c.id)).mappings().all()
                    state = row(c, db.jobs, db.jobs.c.id == job_id)['state']
                for event in result:
                    cursor = (event['created_at'], event['id'])
                    yield f'id: {event["id"]}\nevent: progress\ndata: {json.dumps(event["data"], ensure_ascii=False)}\n\n'
                if state in {'succeeded', 'failed', 'cancelled'}:
                    break
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})

    @app.get(prefix + '/search')
    def search(project_id: str, q: str, asset_id: str | None = None, version_id: str | None = None,
               author: str | None = None, year_from: int | None = None, year_to: int | None = None,
               purpose: str | None = None,
               principal=Depends(identity), s=Depends(service)):
        from .search import enabled as search_enabled, search as execute_search
        if not search_enabled(s):
            raise ResearchError('SEARCH_DISABLED', 503)
        if not q.strip() or len(q) > 1000:
            raise ResearchError('INVALID_QUERY', 422)
        return execute_search(s, project_id, principal, q, asset_id, version_id, author, year_from, year_to, purpose)

    @app.get(prefix + '/legacy')
    def legacy(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            return rows(c, db.legacy, db.legacy.c.project_id == project_id)

    @app.post(prefix + '/history-import', status_code=201)
    async def history_import(project_id: str, request: Request, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal, True)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > settings.max_upload_bytes:
                raise ResearchError('HISTORY_TOO_LARGE', 413)
        try:
            content = json.loads(raw)
            tasks = content['tasks']
            if content.get('format') != 'scriptorium-browser-history.v1' or not isinstance(tasks, list):
                raise ValueError()
            if any(not isinstance(t, dict) or not isinstance(t.get('id'), str) or
                   not isinstance(t.get('messages'), list) for t in tasks):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ResearchError('INVALID_HISTORY_FORMAT', 422) from None
        digest = hashlib.sha256(raw).hexdigest()
        imported = 0
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
            for task in tasks:
                identifier = hashlib.sha256(f'{project_id}:browser:{task["id"]}:{digest}'.encode()).hexdigest()
                if row(c, db.legacy, db.legacy.c.id == identifier):
                    continue
                c.execute(db.legacy.insert().values(id=identifier, project_id=project_id, source=digest,
                    table_name='browser_tasks', legacy_key=task['id'], payload=task, status='preserved'))
                from .workspace import add_message
                conversation_id = hashlib.sha256(f'{project_id}:browser:{task["id"]}'.encode()).hexdigest()
                if not row(c, db.conversations, db.conversations.c.id == conversation_id):
                    c.execute(db.conversations.insert().values(id=conversation_id, project_id=project_id,
                        title=str(task.get('name') or '历史研究')[:200], archived=False, revision=1,
                        workspace={}, created_at=db.now()))
                for i, message in enumerate(task['messages']):
                    mid = hashlib.sha256(f'{conversation_id}:{message.get("id", i)}'.encode()).hexdigest()
                    if not row(c, db.messages, db.messages.c.id == mid):
                        add_message(c, project_id, conversation_id,
                            'assistant' if message.get('role') == 'assistant' else 'user', str(message.get('content', '')),
                            metadata={'legacy': True, 'source_sha256': digest}, identifier=mid)
                imported += 1
        return {'imported': imported, 'source_sha256': digest, 'source_retained': True}

    @app.get(prefix + '/graph/{graph_type}')
    def graph(project_id: str, graph_type: Literal['research', 'concept'], principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            kinds = ['question', 'branch'] if graph_type == 'research' else ['position', 'difficulty', 'transition']
            nodes = rows(c, db.records, db.records.c.project_id == project_id, db.records.c.kind.in_(kinds))
        edges = []
        for node in nodes:
            p = node['payload']
            if p.get('parent_id'):
                edges.append({'from': p['parent_id'], 'to': node['id'], 'type': 'branch'})
            if p.get('from_id') and p.get('to_id'):
                edges.append({'from': p['from_id'], 'to': p['to_id'], 'type': node['kind'], 'record_id': node['id']})
        return {'type': graph_type, 'nodes': nodes, 'edges': edges}

    @app.get(prefix + '/export')
    def export(project_id: str, format: Literal['json', 'md', 'tei'] = 'md', principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            p = s.access(c, project_id, principal)
            items = rows(c, db.records, db.records.c.project_id == project_id)
            evidence = rows(c, db.anchors, db.anchors.c.project_id == project_id)
            materials = rows(c, db.assets, db.assets.c.project_id == project_id, db.assets.c.status != 'revoked')
            segment_data = rows(c, db.segments, db.segments.c.project_id == project_id)
            chapters = list(c.execute(sa.select(db.document_chapters).where(
                db.document_chapters.c.project_id == project_id).order_by(db.document_chapters.c.ordinal)).mappings())
            chapters = [dict(ch) for ch in chapters]
            for chapter in chapters:
                s.validate_evidence(c, project_id, chapter['payload'])
        data = {'format': 'scriptorium-research.v1', 'project': p, 'records': items, 'anchors': evidence,
                'materials': materials, 'segments': segment_data, 'chapters': chapters, 'exported_at': db.now()}
        if format == 'json':
            return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type='application/json',
                headers={'Content-Disposition': 'attachment; filename=research.json', 'Cache-Control': 'no-store'})
        if format == 'tei':
            # Exchange annotation document; it does not claim to be the source TEI itself.
            from lxml import etree as ET
            from .texts import XML_ID, build_tei, project_tei, tag
            root = ET.fromstring(build_tei(['Annotation exchange manifest; source TEI retained separately.'], p['name']))
            stand = ET.SubElement(root, tag('standOff'))
            group = ET.SubElement(stand, tag('spanGrp'), type='evidence')
            by_segment = {segment['id']: segment for segment in segment_data}
            for a in evidence:
                segment = by_segment[a['segment_id']]
                ET.SubElement(group, tag('span'), {XML_ID: 'a_' + a['id'],
                    'corresp': f'urn:scriptorium:text:{segment["version_id"]}#{segment["xml_id"]}',
                    'n': f'{a["start_codepoint"]}:{a["end_codepoint"]}'}).text = a['exact_quote']
            for record in items:
                ET.SubElement(stand, tag('note'), type=record['kind'], target=' '.join(
                    f'#a_{aid}' for aid in record['payload'].get('evidence_ids', []))).text = json.dumps(record, ensure_ascii=False)
            encoded = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
            project_tei(encoded)
            return Response(encoded, media_type='application/xml',
                headers={'Content-Disposition': 'attachment; filename=annotations.xml', 'Cache-Control': 'no-store'})
        lines = [f'# {p["name"]}', '', '> AI候选和演示结果不能作为已核验结论；引文存在与论证支持分别评议。', '']
        for r in items:
            payload = r['payload']
            lines.extend([f'## {payload.get("title", r["kind"])}', '',
                f'类型：{r["kind"]}；版本：{r["revision"]}；状态：{payload.get("status", "draft")}；模式：{payload.get("provider_mode", "human")}',
                '', payload.get('text', ''), ''])
            for chapter in chapters:
                if chapter['record_id'] == r['id']:
                    lines.extend(['', '### ' + chapter['payload'].get('title', '章节'), '',
                                  chapter['payload'].get('text', ''), ''])
            if payload.get('dimensions'):
                lines.extend([f'- {key}：{value}' for key, value in payload['dimensions'].items()])
            for finding in payload.get('findings', []):
                lines.extend(['', f'### {finding["title"]}', '', finding['text']])
            if payload.get('coverage'):
                lines.extend(['', '材料覆盖：', json.dumps(payload['coverage'], ensure_ascii=False)])
            if payload.get('open_questions'):
                lines.extend(['', '未决问题：', *['- ' + q for q in payload['open_questions']]])
            lines.extend(['', '证据：' + ', '.join(payload.get('evidence_ids', [])), ''])
        lines.extend(['## 原文证据', ''])
        by_segment = {s['id']: s for s in segment_data}
        for a in evidence:
            segment = by_segment[a['segment_id']]
            lines.extend([f'- {a["id"]} | version={segment["version_id"]} | {segment["xml_id"]} '
                f'| page={segment["page_label"]} | [{a["start_codepoint"]},{a["end_codepoint"]})',
                '', '> ' + a['exact_quote'].replace('\n', '\n> '), ''])
        return Response('\n'.join(lines), media_type='text/markdown; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=research.md', 'Cache-Control': 'no-store'})

    from .auth import install as install_auth
    install_auth(app, service, identity)
    from .workbench_api import install as install_workbench
    install_workbench(app, service, identity)
    from .unified_api import install
    install(app, service, identity)
    from .experience_api import install as install_experience
    install_experience(app, service, identity)
    from .compat_api import install as install_compat
    install_compat(app, service, identity)

    dist = Path(__file__).resolve().parents[1] / 'static'
    web_dist = Path(__file__).resolve().parents[2] / 'web' / 'dist'
    if web_dist.exists():
        dist = web_dist
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='research-assets')
    if (dist / 'index.html').exists():
        @app.get('/')
        def index():
            return FileResponse(dist / 'index.html')
    return app


app = create_app()
