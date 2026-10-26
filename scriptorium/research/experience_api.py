"""Unified streaming, usage, citation recovery and versioned chapter editing."""
import asyncio
import json
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from . import schema as db
from .service import ResearchError, row, rows
from .workspace import conversation
from .contracts import ChapterOut
from .timeline import TimelineSnapshot, ResearchTask


class CitationResolution(BaseModel):
    revision: int
    discard: bool = False
    bindings: list[dict] = Field(default_factory=list, max_length=100)


class ChapterIn(BaseModel):
    revision: int | None = None
    ordinal: int = 0
    payload: dict


def install(app, service, identity):
    router = APIRouter(prefix='/api/v2/projects/{project_id}')

    @router.get('/conversations/{cid}/snapshot')
    def snapshot(project_id: str, cid: str, principal=Depends(identity), s=Depends(service), limit: int = 80):
        with s.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c, c.begin():
            s.access(c, project_id, principal)
            conv = conversation(s, c, project_id, cid)
            personal = row(c, db.workspaces, db.workspaces.c.project_id == project_id, db.workspaces.c.user_id == principal, db.workspaces.c.conversation_id == cid)
            project = row(c, db.projects, db.projects.c.id == project_id)
            conv = {**conv, 'workspace': personal['payload'] if personal else (conv['workspace'] if project['owner_id'] == principal else {})}
            messages = [dict(m) for m in c.execute(sa.select(db.messages).where(db.messages.c.conversation_id == cid)
                .order_by(db.messages.c.created_at.desc(), db.messages.c.id.desc()).limit(max(1,min(limit,200)))).mappings()]
            messages.reverse()
            cursor = c.execute(sa.select(sa.func.coalesce(sa.func.max(db.conversation_events.c.sequence), 0))
                .where(db.conversation_events.c.conversation_id == cid)).scalar()
            active = {j['id'] for j in c.execute(sa.select(db.jobs).where(db.jobs.c.project_id == project_id,
                db.jobs.c.state.in_(['queued', 'running']))).mappings() if j['payload'].get('conversation_id') == cid}
            drafts = {}
            for event in c.execute(sa.select(db.conversation_events).where(
                    db.conversation_events.c.conversation_id == cid, db.conversation_events.c.type == 'message.delta')
                    .order_by(db.conversation_events.c.sequence)).mappings():
                jid = event['payload'].get('job_id')
                if jid in active:
                    drafts[jid] = drafts.get(jid, '') + event['payload'].get('text', '')
            from .timeline import snapshot as timeline_snapshot
            return {'conversation': conv, 'messages': messages, 'cursor': cursor, 'drafts': drafts,
                    'blocks': timeline_snapshot(c,s,project_id,cid,principal)}

    @router.get('/conversations/{cid}/events')
    async def stream(project_id: str, cid: str, request: Request, after: int = 0,
                     last_event_id: str = Header(default=''), principal=Depends(identity), s=Depends(service)):
        snapshot(project_id, cid, principal, s)
        try:
            cursor = max(after, int(last_event_id or 0))
        except ValueError:
            raise ResearchError('INVALID_EVENT_CURSOR', 422) from None
        async def events():
            nonlocal cursor
            while not await request.is_disconnected():
                with s.engine.connect() as c:
                    s.access(c, project_id, principal)
                    batch = list(c.execute(sa.select(db.conversation_events).where(
                        db.conversation_events.c.conversation_id == cid, db.conversation_events.c.sequence > cursor)
                        .order_by(db.conversation_events.c.sequence).limit(100)).mappings())
                for event in batch:
                    cursor = event['sequence']
                    yield f'id: {cursor}\nevent: update\ndata: {json.dumps(dict(event), ensure_ascii=False)}\n\n'
                if not batch:
                    yield ': heartbeat\n\n'
                    await asyncio.sleep(1)
        return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})

    @router.get('/conversations/{cid}/timeline', response_model=TimelineSnapshot)
    def timeline(project_id: str, cid: str, principal=Depends(identity), s=Depends(service)):
        return snapshot(project_id,cid,principal,s)

    @router.get('/research-tasks/{jid}', response_model=ResearchTask)
    def research_task(project_id: str, jid: str, principal=Depends(identity), s=Depends(service)):
        from .timeline import task
        with s.engine.connect() as c:
            return task(c,s,project_id,jid,principal)

    @router.get('/model-calls')
    def calls(project_id: str, run_id: str | None = None, summary: bool = False, principal=Depends(identity), s=Depends(service)):
        from .calls import usage_totals
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            if run_id and not row(c, db.research_runs, db.research_runs.c.id == run_id,
                                  db.research_runs.c.project_id == project_id):
                raise ResearchError('RUN_NOT_FOUND', 404)
            if summary:
                filters = [db.model_calls.c.project_id == project_id]
                if run_id:
                    filters.append(db.model_calls.c.run_id == run_id)
                totals = c.execute(sa.select(sa.func.coalesce(sa.func.sum(db.model_calls.c.usage['total_tokens'].as_integer()), 0).label('used_tokens'),
                    sa.func.coalesce(sa.func.sum(sa.case((db.model_calls.c.state == 'unknown', 1), else_=0)), 0).label('unknown_calls'))
                    .where(*filters)).mappings().one()
                return {'items': [], 'totals': dict(totals)}
            items = rows(c, db.model_calls, db.model_calls.c.project_id == project_id)
            if run_id:
                items = [r for r in items if r['run_id'] == run_id]
            return {'items': items, 'totals': usage_totals(c, run_id) if run_id else {
                'used_tokens': sum((i['usage'] or {}).get('total_tokens', 0) for i in items),
                'unknown_calls': sum(i['state'] == 'unknown' for i in items)}}

    @router.get('/citation-drafts')
    def drafts(project_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            result = rows(c, db.method_drafts, db.method_drafts.c.project_id == project_id,
                          db.method_drafts.c.state == 'pending')
            for draft in result:
                job = row(c, db.jobs, db.jobs.c.id == draft['job_id'])
                draft['conversation_id'] = job['payload'].get('conversation_id') if job else None
                for aid in draft['payload'].get('source_assets', []):
                    s.asset(c, project_id, aid)
            return result

    @router.post('/citation-drafts/{did}/resolve')
    def resolve(project_id: str, did: str, body: CitationResolution,
                principal=Depends(identity), s=Depends(service)):
        from .methods import MethodResult
        from .citations import citation_objects, validate_citations
        from .events import emit
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            draft = row(c, db.method_drafts, db.method_drafts.c.id == did, db.method_drafts.c.project_id == project_id)
            if not draft:
                raise ResearchError('DRAFT_NOT_FOUND', 404)
            if draft['revision'] != body.revision or draft['state'] != 'pending':
                raise ResearchError('REVISION_CONFLICT', 409)
            job = row(c, db.jobs, db.jobs.c.id == draft['job_id'])
            payload = draft['payload']
            for aid in payload['source_assets']:
                s.asset(c, project_id, aid)
            if body.discard:
                result = MethodResult(summary='研究者未采用本次未核验解释。', findings=[], outcome='undetermined',
                    open_questions=['该步骤的原解释未通过引文核验，不能作为有效结论。'])
            else:
                result = MethodResult.model_validate(payload.get('result') or {})
                citations = list(citation_objects(result))
                for binding in body.bindings:
                    index = binding.get('index', -1)
                    if not isinstance(index, int) or not 0 <= index < len(citations):
                        raise ResearchError('INVALID_CITATION_INDEX', 422)
                    segment = row(c, db.segments, db.segments.c.id == binding.get('segment_id'),
                        db.segments.c.project_id == project_id, db.segments.c.version_id == binding.get('version_id'))
                    if not segment:
                        raise ResearchError('SCOPE_VERSION_MISMATCH', 422)
                    if segment['id'] not in payload['segment_ids']:
                        raise ResearchError('CITATION_OUTSIDE_READ_WINDOW', 422)
                    start, end = binding.get('start_codepoint'), binding.get('end_codepoint')
                    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(segment['text']):
                        raise ResearchError('INVALID_SCOPE_RANGE', 422)
                    window = next((w for w in job['payload'].get('windows', []) if w['segment_id'] == segment['id']
                                   and w['start'] <= start < end <= w['end']), None)
                    if job['payload'].get('windows') and not window:
                        raise ResearchError('CITATION_OUTSIDE_READ_WINDOW', 422)
                    citations[index].segment_id = segment['id']
                    citations[index].exact_quote = segment['text'][start:end]
                    citations[index].start_codepoint = start - (window or {}).get('start', 0)
                    citations[index].end_codepoint = end - (window or {}).get('start', 0)
            readable = []
            for sid in payload['segment_ids']:
                segment = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == project_id)
                if not segment:
                    raise ResearchError('SOURCE_NO_LONGER_AVAILABLE')
                window = next((w for w in job['payload'].get('windows', []) if w['segment_id'] == sid), None)
                start, end = (window['start'], window['end']) if window else (0, len(segment['text']))
                readable.append({**segment, 'text': segment['text'][start:end], 'source_offset': start})
            try:
                validate_citations(result, readable)
            except ResearchError as exc:
                if body.discard:
                    raise
                c.execute(db.method_drafts.update().where(db.method_drafts.c.id == did).values(
                    payload={**payload, 'result': result.model_dump(), 'researcher': principal, 'error': exc.code},
                    revision=draft['revision'] + 1))
                return {'state': 'pending', 'error': exc.code, 'revision': draft['revision'] + 1}
            c.execute(db.method_drafts.update().where(db.method_drafts.c.id == did).values(
                state='resolved', payload={**payload, 'result': result.model_dump(), 'researcher': principal,
                    'discarded': body.discard}, revision=draft['revision'] + 1))
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(state='queued', attempts=0,
                error=None, lease_until=None, lease_token=None))
            rid = job['payload'].get('run_id')
            if rid:
                run = row(c, db.research_runs, db.research_runs.c.id == rid)
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='running'))
                coordinators = rows(c, db.jobs, db.jobs.c.project_id == project_id, db.jobs.c.kind == 'workspace')
                for parent in coordinators:
                    if parent['id'] == run['settings']['origin_job_id'] or parent['payload'].get('resume_run_id') == rid:
                        c.execute(db.jobs.update().where(db.jobs.c.id == parent['id']).values(state='queued',
                            attempts=0, error=None, lease_until=None, lease_token=None))
            emit(c, project_id, job['payload'].get('conversation_id'), 'citation.resolved', {'draft_id': did})
        return {'state': 'queued'}

    @router.get('/artifacts/{record_id}/chapters', response_model=list[ChapterOut])
    def chapters(project_id: str, record_id: str, principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            r = row(c, db.records, db.records.c.id == record_id, db.records.c.project_id == project_id)
            if not r:
                raise ResearchError('ARTIFACT_NOT_FOUND', 404)
            s.validate_evidence(c, project_id, r['payload'])
            return [dict(x) for x in c.execute(sa.select(db.document_chapters).where(
                db.document_chapters.c.record_id == record_id).order_by(db.document_chapters.c.ordinal)).mappings()]

    @router.get('/artifacts/{record_id}/chapters/{chapter_id}/history')
    def chapter_history(project_id: str, record_id: str, chapter_id: str,
                        principal=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, principal)
            chapter = row(c, db.document_chapters, db.document_chapters.c.id == chapter_id,
                db.document_chapters.c.record_id == record_id, db.document_chapters.c.project_id == project_id)
            if not chapter:
                raise ResearchError('CHAPTER_NOT_FOUND', 404)
            s.validate_evidence(c, project_id, chapter['payload'])
            versions = [r['payload']['previous_chapter'] for r in rows(c, db.records,
                db.records.c.project_id == project_id, db.records.c.kind == 'review')
                if r['payload'].get('chapter_id') == chapter_id and r['payload'].get('previous_chapter')]
            return sorted(versions, key=lambda r: r['revision'], reverse=True)

    @router.put('/artifacts/{record_id}/chapters/{chapter_id}', response_model=ChapterOut)
    def save_chapter(project_id: str, record_id: str, chapter_id: str, body: ChapterIn,
                     principal=Depends(identity), s=Depends(service)):
        from .manuscripts import save_chapter as apply
        with s.engine.begin() as c:
            s.access(c, project_id, principal, True)
            return apply(s, c, project_id, record_id, chapter_id, body.revision, body.ordinal, body.payload)

    app.include_router(router)
