"""v1 adapters. Never import the legacy API (its module opens SQLite at import time)."""
import json

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse

from . import schema as db
from .legacy_store import PostgresStore
from .service import ResearchError


def install(app, service, identity):
    router = APIRouter(prefix='/api/v1')

    async def forward(request, method, path, body=None):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://internal') as client:
            result = await client.request(method, '/api/v2' + path, json=body,
                headers={'Idempotency-Key': request.headers.get('idempotency-key', db.uid()), **{k: v for k, v in request.headers.items() if k.lower() == 'authorization'}})
        return JSONResponse(result.json(), status_code=result.status_code)

    def resolve(s, principal, identifier, kind):
        with s.engine.connect() as c:
            pids = set(c.execute(sa.select(db.entities.c.project_id).join(db.members,
                db.members.c.project_id == db.entities.c.project_id).where(db.members.c.user_id == principal,
                db.entities.c.kind == kind, db.entities.c.external_id == identifier)).scalars())
        if len(pids) != 1:
            raise ResearchError('RESOURCE_NOT_FOUND_OR_AMBIGUOUS', 404)
        return pids.pop()

    @router.get('/projects')
    def projects(principal=Depends(identity), s=Depends(service)):
        return {'projects': s.list_projects(principal)}

    @router.post('/projects', status_code=201)
    def create_project(body: dict, principal=Depends(identity), s=Depends(service)):
        return s.create_project(principal, body['name'], body.get('description', ''))

    @router.get('/projects/{pid}')
    def project(pid: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            return s.access(c, pid, principal)

    @router.get('/projects/{pid}/participants')
    def participants(pid: str, principal=Depends(identity), s=Depends(service)):
        return {'participants': PostgresStore(s, pid, principal).all('participant')}

    @router.post('/participants', status_code=201)
    def participant(body: dict, principal=Depends(identity), s=Depends(service)):
        from hermeneut.models import Participant
        p = Participant.model_validate(body)
        value = p.model_dump(mode='json')
        scope = p.consent_scope
        value['permissions'] = body.get('permissions') or {'material_collection': scope.is_active(),
            'profile_analysis': False, 'agent_simulation': False}
        PostgresStore(s, p.project_id, principal).put('participant', value)
        return value

    @router.post('/participants/{participant_id}/withdraw', status_code=202)
    async def withdraw(participant_id: str, project_id: str, request: Request, principal=Depends(identity)):
        return await forward(request, 'POST', f'/projects/{project_id}/participants/{participant_id}/withdraw')

    @router.post('/interviews', status_code=201)
    async def interview(body: dict, request: Request, principal=Depends(identity), s=Depends(service)):
        from .workspace import create_conversation
        pid = body['project_id']
        cid = body.get('conversation_id') or create_conversation(s, pid, principal, '研究访谈')['id']
        result = await forward(request, 'POST', f'/projects/{pid}/interviews', {**body, 'conversation_id': cid})
        if result.status_code < 300:
            result.body = json.dumps({'session': json.loads(result.body)}, ensure_ascii=False).encode()
            result.headers['content-length'] = str(len(result.body))
        return result

    @router.api_route('/interviews/{iid}', methods=['GET'])
    async def get_interview(iid: str, project_id: str, request: Request, principal=Depends(identity)):
        return await forward(request, 'GET', f'/projects/{project_id}/interviews/{iid}')

    @router.post('/interviews/{iid}/{action}')
    async def interview_action(iid: str, action: str, body: dict, request: Request, principal=Depends(identity)):
        return await forward(request, 'POST', f'/projects/{body["project_id"]}/interviews/{iid}/{action}', body)

    @router.get('/personas')
    async def personas(project_id: str, request: Request, principal=Depends(identity)):
        return await forward(request, 'GET', f'/projects/{project_id}/personas')

    @router.post('/personas', status_code=201)
    async def persona(body: dict, request: Request, principal=Depends(identity)):
        return await forward(request, 'POST', f'/projects/{body["project_id"]}/personas', body)

    @router.get('/personas/{identifier}')
    def get_persona(identifier: str, principal=Depends(identity), s=Depends(service)):
        return PostgresStore(s, resolve(s, principal, identifier, 'persona'), principal).get_persona(identifier)

    @router.api_route('/personas/{identifier}/{action}', methods=['GET', 'POST'])
    async def persona_action(identifier: str, action: str, request: Request,
                             principal=Depends(identity), s=Depends(service)):
        pid = resolve(s, principal, identifier, 'persona')
        if action == 'metrics':
            return PostgresStore(s, pid, principal).list_topology_metrics(identifier)
        return await forward(request, request.method, f'/projects/{pid}/personas/{identifier}/{action}')

    @router.delete('/personas/{identifier}')
    async def delete_persona(identifier: str, request: Request, principal=Depends(identity), s=Depends(service)):
        pid = resolve(s, principal, identifier, 'persona')
        return await forward(request, 'DELETE', f'/projects/{pid}/personas/{identifier}')

    @router.post('/analysis-runs', status_code=202)
    def analysis(body: dict, principal=Depends(identity), s=Depends(service)):
        from hermeneut.workflow import Workflow
        from .capabilities import provider
        store = PostgresStore(s, body['project_id'], principal)
        from .unified_api import require_consent
        require_consent(store, body['participant_id'], 'profile_analysis')
        run = Workflow(store, provider(body.get('provider_mode', 'live'))).run(body['project_id'],
            body['participant_id'], body['source_ids'], body['idempotency_key'])
        return {'run_id': run.id, 'state': run.state}

    @router.get('/analysis-runs/{identifier}')
    def get_analysis(identifier: str, principal=Depends(identity), s=Depends(service)):
        return PostgresStore(s, resolve(s, principal, identifier, 'analysis_run'), principal).get('analysis_run', identifier)

    @router.api_route('/analysis-runs/{identifier}/{action}', methods=['GET', 'POST'])
    async def analysis_action(identifier: str, action: str, request: Request,
                              principal=Depends(identity), s=Depends(service)):
        pid = resolve(s, principal, identifier, 'analysis_run')
        if action in {'packet', 'graph'}:
            from hermeneut.workflow import Workflow
            return Workflow(PostgresStore(s, pid, principal, corpus=True)).export(identifier)[action]
        return await forward(request, request.method, f'/projects/{pid}/analysis-runs/{identifier}/{action}',
                             await request.json() if request.method == 'POST' else None)

    @router.get('/theory/search')
    async def search(project_id: str, q: str, request: Request, principal=Depends(identity)):
        from urllib.parse import urlencode
        return await forward(request, 'GET', f'/projects/{project_id}/search?' + urlencode({'q': q}))

    @router.post('/theory/sources', status_code=202)
    async def theory_source(project_id: str = Form(...), file: UploadFile = File(...),
                            principal=Depends(identity), s=Depends(service)):
        raw = await file.read(s.settings.max_upload_bytes + 1)
        return s.import_material(project_id, principal, raw, file.filename or 'source.txt', db.uid(), {'purpose': 'theory'})

    @router.post('/participants/{participant_id}/sources', status_code=202)
    async def participant_source(participant_id: str, project_id: str = Form(...), file: UploadFile = File(...),
                                 principal=Depends(identity), s=Depends(service)):
        from .unified_api import require_consent
        require_consent(PostgresStore(s, project_id, principal), participant_id, 'material_collection')
        raw = await file.read(s.settings.max_upload_bytes + 1)
        return s.import_material(project_id, principal, raw, file.filename or 'source.txt', db.uid(),
                                 {'participant_id': participant_id})

    @router.post('/chat/{action}')
    async def chat(action: str, body: dict, request: Request, principal=Depends(identity), s=Depends(service)):
        from .workspace import create_conversation
        pid = body.get('project_id')
        if not pid:
            raise ResearchError('EXPLICIT_PROJECT_REQUIRED', 422)
        cid = body.get('conversation_id') or create_conversation(s, pid, principal, '研究对话')['id']
        return await forward(request, 'POST', f'/projects/{pid}/conversations/{cid}/messages', {
            'text': body.get('text') or body.get('message') or body.get('question') or '',
            'tool': 'theory' if action in {'analyze', 'dialectical'} else 'chat',
            'asset_ids': body.get('asset_ids') or body.get('source_ids') or [],
            'provider_mode': body.get('provider_mode', 'live')})

    @router.get('/perspectives')
    def perspectives(principal=Depends(identity)):
        from hermeneut.perspectives import list_perspectives
        return {'perspectives': [p.model_dump(mode='json') for p in list_perspectives()]}

    app.include_router(router)
