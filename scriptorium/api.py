from __future__ import annotations

import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import get_settings
from .concurrent import AnalysisTask, ConcurrentAnalyzer
from .db import Store
from .interview import InterviewManager
from .models import (
    ConsentScope,
    ErrorResponse,
    ErrorBody,
    Participant,
    Project,
    ReviewRequest,
    RunState,
)
from .rag import ingest, search
from .workflow import Workflow

app = FastAPI(title='Scriptorium', version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        'http://localhost:5173',
        'tauri://localhost',
        'https://tauri.localhost',
        'http://tauri.localhost',
        'null',
    ],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)

API_KEY = get_settings().api_key or None
security = HTTPBearer(auto_error=False)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not API_KEY:
        return
    if not credentials or credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


store = Store()
flow = Workflow(store)


class ProjectIn(BaseModel):
    id: str
    name: str = ''
    description: str = ''
    owner_id: str = 'local-user'
    policy_version: str = '1.0'


class ParticipantIn(BaseModel):
    id: str
    project_id: str
    pseudonym: str | None = None
    consent_scope: ConsentScope = ConsentScope()


class RunIn(BaseModel):
    project_id: str
    participant_id: str
    source_ids: list[str]
    mode: str = 'evidence_first'
    idempotency_key: str


class InterviewCreateIn(BaseModel):
    project_id: str
    participant_id: str
    config_id: str | None = None


class InterviewTurnIn(BaseModel):
    project_id: str
    participant_id: str
    question_id: str
    answer_text: str
    tags: list[str] = Field(default_factory=list)


class InterviewAccessIn(BaseModel):
    project_id: str
    participant_id: str


MAX_UPLOAD_BYTES = get_settings().max_upload_bytes
UPLOAD_SUFFIXES = {'.txt', '.md', '.pdf'}
UPLOAD_ROOT = Path(get_settings().storage_path).resolve()


def _ingest_upload(file: UploadFile, project_id: str, participant_id: str | None = None, consent=None):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise ValueError('UNSUPPORTED_SOURCE_TYPE')
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('SOURCE_TOO_LARGE')
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=UPLOAD_ROOT, suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            temp_path = Path(tmp.name)
        return ingest(store, str(temp_path), project_id, participant_id, consent)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def _interview_manager() -> InterviewManager:
    try:
        provider = _get_provider()
    except Exception:
        from .llm import FakeProvider
        provider = FakeProvider()
    return InterviewManager(store, provider)


def _interview_participant(project_id: str, participant_id: str):
    if not store.get_project(project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    participant = store.get_participant(project_id, participant_id)
    if not participant:
        raise HTTPException(404, 'PARTICIPANT_NOT_FOUND')
    if participant.withdrawn_at or not participant.consent_scope.is_active():
        raise HTTPException(403, 'PARTICIPANT_WITHDRAWN')
    return participant


def _err(status_code: int, code: str, msg: str):
    rid = 'req_' + uuid.uuid4().hex[:10]
    body = ErrorResponse(error=ErrorBody(code=code, message=msg, request_id=rid))
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.exception_handler(PermissionError)
async def perm_handler(request, exc):
    return _err(403, str(exc), '授权或对象访问被拒绝')


@app.get('/health')
def health():
    return {'status': 'ok'}


class ApiKeyIn(BaseModel):
    key: str


@app.post('/api/v1/config/api-key')
def update_api_key(x: ApiKeyIn):
    import os
    from .config import reset_settings
    os.environ['DASHSCOPE_API_KEY'] = x.key
    reset_settings()
    return {'ok': True}


class PersonaIn(BaseModel):
    project_id: str
    participant_id: str
    name: str = Field(min_length=1, max_length=120)
    avatar: str = ''
    model: str = 'qwen2.5:3b'
    mode: str = 'prompt'
    alpha: float = Field(default=0.8, ge=0.0, le=2.0)


class PersonaPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar: str | None = None
    model: str | None = None
    mode: str | None = None
    alpha: float | None = Field(default=None, ge=0.0, le=2.0)


class PersonaChatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = None


@app.get('/api/v1/topostyle/ollama/health', dependencies=[Depends(verify_api_key)])
def topostyle_ollama_health():
    from .topostyle.provider import OllamaProvider
    return OllamaProvider().health()


@app.post('/api/v1/personas', status_code=201, dependencies=[Depends(verify_api_key)])
def persona_create(x: PersonaIn):
    from .topostyle.service import create_persona
    try:
        return create_persona(store, **x.model_dump())
    except (ValueError, PermissionError) as exc:
        raise HTTPException(403 if isinstance(exc, PermissionError) else 422, str(exc))


@app.get('/api/v1/personas', dependencies=[Depends(verify_api_key)])
def persona_list(project_id: str, participant_id: str | None = None):
    return {'personas': store.list_personas(project_id, participant_id)}


@app.get('/api/v1/personas/{persona_id}', dependencies=[Depends(verify_api_key)])
def persona_get(persona_id: str):
    persona = store.get_persona(persona_id)
    if not persona:
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    return persona


@app.patch('/api/v1/personas/{persona_id}', dependencies=[Depends(verify_api_key)])
def persona_patch(persona_id: str, x: PersonaPatch):
    from .topostyle.service import ensure_consent
    persona = store.get_persona(persona_id)
    if not persona:
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    try:
        ensure_consent(store, persona)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    persona.update({k: v for k, v in x.model_dump().items() if v is not None})
    persona['updated_at'] = datetime.now(UTC).isoformat()
    return store.put_persona(persona)


@app.delete('/api/v1/personas/{persona_id}', status_code=204, dependencies=[Depends(verify_api_key)])
def persona_delete(persona_id: str):
    if not store.get_persona(persona_id):
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    store.delete_persona(persona_id)


@app.post('/api/v1/personas/{persona_id}/train', dependencies=[Depends(verify_api_key)])
def persona_train(persona_id: str):
    from .topostyle.service import train_persona
    try:
        return train_persona(store, persona_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc))


@app.get('/api/v1/personas/{persona_id}/artifacts', dependencies=[Depends(verify_api_key)])
def persona_artifacts(persona_id: str):
    if not store.get_persona(persona_id):
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    return {'artifacts': store.list_persona_artifacts(persona_id)}


@app.get('/api/v1/personas/{persona_id}/metrics', dependencies=[Depends(verify_api_key)])
def persona_metrics(persona_id: str, limit: int = 100):
    if not store.get_persona(persona_id):
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    return {'metrics': store.list_topology_metrics(persona_id, min(limit, 500))}


@app.post('/api/v1/personas/{persona_id}/withdraw', dependencies=[Depends(verify_api_key)])
def persona_withdraw(persona_id: str):
    persona = store.get_persona(persona_id)
    if not persona:
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    store.withdraw(persona['project_id'], persona['participant_id'])
    return {'persona_id': persona_id, 'state': 'WITHDRAWN'}


@app.post('/api/v1/personas/{persona_id}/chat', dependencies=[Depends(verify_api_key)])
def persona_chat(persona_id: str, x: PersonaChatIn):
    from .topostyle.provider import OllamaProvider
    from .topostyle.service import ensure_consent, prompt_context
    persona = store.get_persona(persona_id)
    if not persona:
        raise HTTPException(404, 'PERSONA_NOT_FOUND')
    try:
        ensure_consent(store, persona)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    artifacts = store.list_persona_artifacts(persona_id)
    if not artifacts:
        raise HTTPException(409, 'PERSONA_NOT_TRAINED')
    artifact = artifacts[0]
    conversation_id = x.conversation_id or f'conv_{uuid.uuid4().hex[:12]}'
    if not store.get_conversation(conversation_id):
        timestamp = datetime.now(UTC).isoformat()
        store.put_conversation({'id': conversation_id, 'persona_id': persona_id, 'created_at': timestamp, 'updated_at': timestamp})
    store.put_message({
        'id': f'msg_{uuid.uuid4().hex[:12]}', 'conversation_id': conversation_id,
        'role': 'user', 'content': x.prompt, 'created_at': datetime.now(UTC).isoformat(),
    })

    def events():
        yield f"event: metadata\ndata: {json.dumps({'persona_id': persona_id, 'conversation_id': conversation_id, 'ai_generated': True}, ensure_ascii=False)}\n\n"
        try:
            provider = OllamaProvider(model=persona['model'])
            chunks = provider.generate(prompt_context(artifact, x.prompt), stream=True)
            answer = ''
            for chunk in chunks:
                answer += chunk
                yield f"event: text\ndata: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            store.put_message({
                'id': f'msg_{uuid.uuid4().hex[:12]}', 'conversation_id': conversation_id,
                'role': 'assistant', 'content': answer, 'created_at': datetime.now(UTC).isoformat(), 'ai_generated': True,
            })
            style_similarity = None
            try:
                vector = provider.embed([answer])[0]
                reference = artifact.get('data', {}).get('embeddings', [])
                if reference and vector:
                    import numpy as np
                    mean = np.mean(reference, axis=0)
                    norm_a = np.linalg.norm(vector)
                    norm_b = np.linalg.norm(mean)
                    style_similarity = float(np.dot(vector, mean) / max(norm_a * norm_b, 1e-8))
            except Exception:
                yield f"event: warning\ndata: {json.dumps({'code': 'STYLE_METRIC_UNAVAILABLE'}, ensure_ascii=False)}\n\n"
            metric = {
                'id': f'metric_{uuid.uuid4().hex[:12]}', 'persona_id': persona_id,
                'conversation_id': conversation_id, 'topology_distance': None,
                'style_similarity': style_similarity, 'drift': 'topology_pending',
                'created_at': datetime.now(UTC).isoformat(),
            }
            store.put_topology_metric(metric)
            yield f"event: metric\ndata: {json.dumps(metric, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete', 'ai_generated': True}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'code': 'PERSONA_CHAT_FAILED', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


_static_dir = Path(__file__).parent.parent / 'web' / 'dist'
_legacy_static = Path(__file__).parent / 'static'
if not _static_dir.exists():
    _static_dir = _legacy_static
if _static_dir.exists():
    app.mount('/static', StaticFiles(directory=str(_static_dir)), name='static')
    _assets_dir = _static_dir / 'assets'
    if _assets_dir.exists():
        app.mount('/assets', StaticFiles(directory=str(_assets_dir)), name='assets')


@app.get('/')
def spa_index():
    idx = _static_dir / 'index.html'
    if idx.exists():
        return FileResponse(idx)
    return JSONResponse({'service': 'Scriptorium', 'version': __version__})


@app.post('/api/v1/projects', status_code=201, dependencies=[Depends(verify_api_key)])
def project(x: ProjectIn):
    if store.get_project(x.id):
        raise HTTPException(400, 'PROJECT_EXISTS')
    from datetime import UTC, datetime
    return store.create_project(Project(
        id=x.id, name=x.name, description=x.description,
        owner_id=x.owner_id, policy_version=x.policy_version,
        created_at=datetime.now(UTC).isoformat(),
    )).model_dump()


@app.get('/api/v1/projects', dependencies=[Depends(verify_api_key)])
def list_projects():
    return {'projects': [p.model_dump() for p in store.list_projects()]}


@app.get('/api/v1/projects/{project_id}', dependencies=[Depends(verify_api_key)])
def get_project(project_id: str):
    p = store.get_project(project_id)
    if not p:
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    return p.model_dump()


@app.delete('/api/v1/projects/{project_id}', status_code=204, dependencies=[Depends(verify_api_key)])
def delete_project(project_id: str):
    if project_id == 'default':
        raise HTTPException(400, 'CANNOT_DELETE_DEFAULT_PROJECT')
    if not store.delete_project(project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')


@app.get('/api/v1/projects/{project_id}/participants', dependencies=[Depends(verify_api_key)])
def list_participants(project_id: str):
    if not store.get_project(project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    return {'participants': [p.model_dump() for p in store.list_participants(project_id)]}


@app.delete('/api/v1/projects/{project_id}/participants/{participant_id}', status_code=204,
            dependencies=[Depends(verify_api_key)])
def delete_participant(project_id: str, participant_id: str):
    if not store.delete_participant(project_id, participant_id):
        raise HTTPException(404, 'PARTICIPANT_NOT_FOUND')


@app.post('/api/v1/theory/sources', status_code=202, dependencies=[Depends(verify_api_key)])
def theory(project_id: str = Form(...), file: UploadFile = File(...)):
    if not store.get_project(project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    try:
        return _ingest_upload(file, project_id).model_dump(exclude={'text', 'origin'})
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/v1/theory/search', dependencies=[Depends(verify_api_key)])
def theory_search(project_id: str, q: str, limit: int = 5):
    if not store.get_project(project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    return {'items': search(store, q, project_id, min(limit, 5))}


@app.post('/api/v1/participants', status_code=201, dependencies=[Depends(verify_api_key)])
def participant(x: ParticipantIn):
    if not store.get_project(x.project_id):
        raise HTTPException(404, 'PROJECT_NOT_FOUND')
    return store.put_participant(Participant(
        id=x.id, project_id=x.project_id, pseudonym=x.pseudonym or x.id, consent_scope=x.consent_scope,
    )).model_dump()


@app.post('/api/v1/participants/{pid}/sources', status_code=202, dependencies=[Depends(verify_api_key)])
def source(pid: str, project_id: str = Form(...), file: UploadFile = File(...)):
    p = store.get_participant(project_id, pid)
    if not p:
        raise HTTPException(404, 'PARTICIPANT_NOT_FOUND')
    if p.withdrawn_at or not p.consent_scope.is_active():
        raise HTTPException(403, 'PARTICIPANT_WITHDRAWN')
    try:
        return _ingest_upload(file, project_id, pid, p.consent_scope).model_dump(exclude={'text', 'origin'})
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post('/api/v1/interviews', status_code=201, dependencies=[Depends(verify_api_key)])
def create_interview(x: InterviewCreateIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        manager = _interview_manager()
        session, config = manager.create(x.project_id, x.participant_id, x.config_id)
        return {'session': manager.view(session.id, x.project_id, x.participant_id),
                'config': config.model_dump(mode='json')}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))


@app.get('/api/v1/interviews/{session_id}', dependencies=[Depends(verify_api_key)])
def get_interview(session_id: str, project_id: str, participant_id: str):
    _interview_participant(project_id, participant_id)
    try:
        return _interview_manager().view(session_id, project_id, participant_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/turns', dependencies=[Depends(verify_api_key)])
def interview_turn(session_id: str, x: InterviewTurnIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        return _interview_manager().submit(
            session_id, x.project_id, x.participant_id, x.question_id, x.answer_text, x.tags,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/pause', dependencies=[Depends(verify_api_key)])
def pause_interview(session_id: str, x: InterviewAccessIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        return _interview_manager().pause(session_id, x.project_id, x.participant_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/resume', dependencies=[Depends(verify_api_key)])
def resume_interview(session_id: str, x: InterviewAccessIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        return _interview_manager().resume(session_id, x.project_id, x.participant_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/complete', dependencies=[Depends(verify_api_key)])
def complete_interview(session_id: str, x: InterviewAccessIn):
    participant = _interview_participant(x.project_id, x.participant_id)
    manager = _interview_manager()
    try:
        session, payload = manager.complete(session_id, x.project_id, x.participant_id)
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        artifact_path = UPLOAD_ROOT / f'{session.id}.json'
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        doc = ingest(store, str(artifact_path), x.project_id, x.participant_id, participant.consent_scope)
        run = flow.run(x.project_id, x.participant_id, [doc.id], f'interview_{session.id}')
        session.source_id = doc.id
        session.run_id = run.id
        session.audit.append({'event': 'completed', 'artifact_path': str(artifact_path), 'timestamp': datetime.now(UTC).isoformat()})
        store.put_interview_session(session)
        return {'session': manager.view(session.id, x.project_id, x.participant_id),
                'source_id': doc.id, 'run_id': run.id, 'state': run.state}
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/withdraw', dependencies=[Depends(verify_api_key)])
def withdraw_interview(session_id: str, x: InterviewAccessIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        return _interview_manager().withdraw(session_id, x.project_id, x.participant_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/interviews/{session_id}/reset', dependencies=[Depends(verify_api_key)])
def reset_interview(session_id: str, x: InterviewAccessIn):
    _interview_participant(x.project_id, x.participant_id)
    try:
        manager = _interview_manager()
        previous, fresh = manager.reset(session_id, x.project_id, x.participant_id)
        return {
            'previous_session_id': previous.id,
            'session': manager.view(fresh.id, x.project_id, x.participant_id),
        }
    except (KeyError, ValueError) as exc:
        raise HTTPException(404 if isinstance(exc, KeyError) else 422, str(exc))


@app.post('/api/v1/analysis-runs', status_code=202, dependencies=[Depends(verify_api_key)])
def analysis(x: RunIn):
    try:
        r = flow.run(x.project_id, x.participant_id, x.source_ids, x.idempotency_key)
        return {'run_id': r.id, 'state': r.state}
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/v1/analysis-runs/{rid}', dependencies=[Depends(verify_api_key)])
def run(rid: str):
    result = store.get_run(rid)
    if not result:
        raise HTTPException(404, 'RUN_NOT_FOUND')
    return result.model_dump(mode='json')


@app.post('/api/v1/analysis-runs/{rid}/reviews', dependencies=[Depends(verify_api_key)])
def review(rid: str, x: ReviewRequest):
    return flow.review(rid, x).model_dump(mode='json')


@app.get('/api/v1/analysis-runs/{rid}/packet', dependencies=[Depends(verify_api_key)])
def packet(rid: str):
    r = store.get_run(rid)
    if not r:
        raise HTTPException(404, 'RUN_NOT_FOUND')
    if not r.packet or r.state not in (RunState.APPROVED, RunState.COMPILED, RunState.NEEDS_HUMAN_REVIEW):
        raise HTTPException(409, 'NOT_APPROVED')
    return r.packet.model_dump(mode='json')


@app.get('/api/v1/analysis-runs/{rid}/graph', dependencies=[Depends(verify_api_key)])
def graph(rid: str):
    try:
        return flow.export(rid)['graph']
    except PermissionError as e:
        raise HTTPException(409, str(e))


@app.post('/api/v1/participants/{pid}/withdraw', status_code=202, dependencies=[Depends(verify_api_key)])
def withdraw(pid: str, project_id: str):
    p = store.withdraw(project_id, pid)
    if not p:
        raise HTTPException(404, 'PARTICIPANT_NOT_FOUND')
    return {'participant_id': pid, 'state': 'WITHDRAWAL_REQUESTED'}


class BatchTaskIn(BaseModel):
    project_id: str
    participant_id: str
    source_ids: list[str]
    idempotency_key: str


class BatchIn(BaseModel):
    tasks: list[BatchTaskIn]
    max_concurrent: int = Field(default=4, ge=1, le=16)


@app.post('/api/v1/analysis-runs/batch', status_code=202, dependencies=[Depends(verify_api_key)])
async def batch_analysis(x: BatchIn):
    provider = _get_provider()
    analyzer = ConcurrentAnalyzer(store, provider=provider, max_concurrent=x.max_concurrent)
    atasks = [AnalysisTask(
        project_id=t.project_id, participant_id=t.participant_id,
        source_ids=t.source_ids, idempotency_key=t.idempotency_key,
    ) for t in x.tasks]
    results = await analyzer.analyze_batch(atasks)
    return {'results': [{'participant_id': r.task.participant_id, 'run_id': r.run.id if r.run else None, 'state': r.run.state if r.run else None, 'error': r.error} for r in results]}


def _get_provider():
    cfg = get_settings()
    if cfg.mock or not cfg.dashscope_api_key:
        from .llm import FakeProvider
        return FakeProvider()
    from .llm import QwenProvider
    return QwenProvider()


class DialecticalRunIn(BaseModel):
    project_id: str
    participant_id: str
    source_ids: list[str]
    perspective_ids: list[str]
    idempotency_key: str
    generate_report: bool = False


@app.post('/api/v1/dialectical/run', status_code=202, dependencies=[Depends(verify_api_key)])
def dialectical_run(x: DialecticalRunIn):
    try:
        from .dialectical import DialecticalWorkflow
        from .perspectives import PerspectiveRegistry
        registry = PerspectiveRegistry()
        perspectives = registry.load_many(x.perspective_ids)
        provider = _get_provider()
        dw = DialecticalWorkflow(store, provider, perspectives)
        result = dw.run(x.project_id, x.participant_id, x.source_ids, x.idempotency_key,
                        generate_report=x.generate_report)
        return result.model_dump(mode='json')
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.get('/api/v1/perspectives', dependencies=[Depends(verify_api_key)])
def list_perspectives_api():
    from .perspectives import list_perspectives
    return {'perspectives': [{'id': p.id, 'name': p.name, 'concepts': p.concept_inventory,
                              'blind_spots': p.blind_spots} for p in list_perspectives()]}


def _ensure_chat_context(project_id: str, participant_id: str) -> None:
    if not project_id:
        return
    if not store.get_project(project_id):
        store.create_project(Project(id=project_id, owner_id='chat-ui'))
    if participant_id and not store.get_participant(project_id, participant_id):
        store.put_participant(Participant(
            id=participant_id, project_id=project_id,
            pseudonym=participant_id, consent_scope=ConsentScope(),
        ))


class ChatAnalyzeIn(BaseModel):
    text: str = ''
    source_ids: list[str] = Field(default_factory=list)
    project_id: str = 'default'
    participant_id: str = 'anonymous'


@app.post('/api/v1/chat/analyze', dependencies=[Depends(verify_api_key)])
async def chat_analyze_stream(x: ChatAnalyzeIn):
    from .stream import stream_single_analysis
    _ensure_chat_context(x.project_id, x.participant_id)
    provider = _get_provider()
    return StreamingResponse(
        stream_single_analysis(store, provider, x.project_id, x.participant_id, x.source_ids, x.text),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


class ChatDialecticalIn(BaseModel):
    text: str = ''
    source_ids: list[str] = Field(default_factory=list)
    project_id: str = 'default'
    participant_id: str = 'anonymous'
    perspective_ids: list[str] = Field(default_factory=lambda: ['lacan', 'deleuze'])


@app.post('/api/v1/chat/dialectical', dependencies=[Depends(verify_api_key)])
async def chat_dialectical_stream(x: ChatDialecticalIn):
    from .stream import stream_dialectical_analysis
    _ensure_chat_context(x.project_id, x.participant_id)
    provider = _get_provider()
    return StreamingResponse(
        stream_dialectical_analysis(store, provider, x.project_id, x.participant_id, x.source_ids, x.text, x.perspective_ids),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


SCRIPTORIUM_SYSTEM_PROMPT = """你是 Scriptorium Agent，一个专注于话语分析的专业助手。你的核心能力包括：

**理论框架**
- 拉康精神分析：能指链、想象界/象征界/实在界(RSI)、对象a、四种话语、镜像阶段、缝合点(points de capiton)
- 德勒兹哲学：机器、装配体(assemblage)、根茎、解域/再域化、欲望机器、无器官身体、差异与重复

**工作方式**
1. 当用户分享文本或经历时，你能识别其中的话语模式、主体位置、欲望结构
2. 你能用专业但不晦涩的语言解释分析结果
3. 你会在适当时候使用形式化记号（如 $ ◇ a, S(Ⱥ)）来精确表达
4. 你尊重来访者的独特性，不做病理化判断

**对话风格**
- 专业但温和，像一位经验丰富的分析家
- 避免空洞的安慰，倾向于提出有启发性的问题
- 当话题超出话语分析范畴时，坦诚说明并简要回应
- 回复简洁有力，一般不超过3段"""


class ChatCompletionIn(BaseModel):
    messages: list[dict[str, str]]
    model: str = 'default'


@app.post('/api/v1/chat/completions', dependencies=[Depends(verify_api_key)])
async def chat_completions_stream(x: ChatCompletionIn):
    provider = _get_provider()
    if not provider or not hasattr(provider, 'client'):
        async def error_gen():
            yield f"event: error\ndata: {json.dumps({'message': 'LLM provider not configured'})}\n\n"
        return StreamingResponse(error_gen(), media_type='text/event-stream')

    messages = [{'role': 'system', 'content': SCRIPTORIUM_SYSTEM_PROMPT}] + x.messages

    async def stream_chat():
        try:
            resp = provider.client.chat.completions.create(
                model=provider.model,
                messages=messages,
                temperature=provider.temperature,
                stream=True,
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"event: text\ndata: {json.dumps({'chunk': chunk.choices[0].delta.content}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        stream_chat(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
