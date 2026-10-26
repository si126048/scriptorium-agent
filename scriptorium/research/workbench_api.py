"""Typed workbench contracts: governance, personal state, reviews and safe editorial changes."""
import json
from typing import Literal
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field, ConfigDict
from . import schema as db
from .service import ResearchError, row, rows
from .governance import owner, audit
from .workspace import conversation
from .contracts import ReadingOut, CitationLabelOut, JobOut, ChapterOut


class ChapterOrderIn(BaseModel):
    chapters: list[dict[str, int | str]] = Field(max_length=1000)


class MemberIn(BaseModel):
    role: Literal['owner', 'editor', 'reviewer', 'reader']


class PolicyIn(BaseModel):
    revision: int = Field(ge=0)
    allow_external: bool = False
    allowed_hosts: list[str] = Field(default_factory=list, max_length=32)
    asset_ids: list[str] | None = None
    version_ids: list[str] | None = None
    token_budget: int = Field(default=40000, ge=1000, le=10000000)
    purpose: str = Field(default='项目研究', max_length=1000)


class WorkspaceIn(BaseModel):
    revision: int = Field(ge=0)
    payload: dict


class ClassificationIn(BaseModel):
    revision: int = Field(ge=1)
    sensitive: bool


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class CommentState(BaseModel):
    state: Literal['open', 'resolved']


class ProposalIn(BaseModel):
    chapter_id: str | None = None
    conversation_id: str | None = None
    base_revision: int = Field(ge=1)
    instruction: str = Field(min_length=1, max_length=5000)
    provider_mode: Literal['live', 'demo'] = 'live'


class ProposalDecision(BaseModel):
    action: Literal['accept', 'reject']


class RestoreIn(BaseModel):
    revision: int = Field(ge=1)
    source_revision: int = Field(ge=1)


class ExportIn(BaseModel):
    revision: int | None = Field(default=None, ge=1)
    conversation_id: str | None = None
    format: Literal['docx', 'md', 'html']
    locale: Literal['zh-CN', 'en-US'] = 'zh-CN'
    style: Literal['note', 'author-date'] = 'note'


class WorkspaceOut(BaseModel):
    revision: int
    payload: dict


class TaskOut(BaseModel):
    id: str
    kind: str
    state: str
    phase: str
    record_id: str | None = None
    conversation_id: str | None = None
    error: str | None = None
    actions: list[str]
    result: dict | None = None


class ProposalOut(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    project_id: str
    record_id: str
    base_revision: int
    author: str
    state: str
    payload: dict
    created_at: float


def install(app, service, identity):
    router = APIRouter(prefix='/api/v2/projects/{project_id}')

    @router.get('/materials/{aid}/reading', response_model=ReadingOut)
    def reading(project_id: str, aid: str, version_id: str | None = None, page: int = Query(default=0, ge=0),
                segment_id: str | None = None, start: int | None = Query(default=None, ge=0),
                end: int | None = Query(default=None, ge=0), actor=Depends(identity), s=Depends(service)):
        from .reading import read_page
        return read_page(s, project_id, actor, aid, version_id, page, segment_id, start, end)

    @router.get('/citation-labels', response_model=list[CitationLabelOut])
    def citation_labels(project_id: str, ids: str = Query(max_length=14000), actor=Depends(identity), s=Depends(service)):
        selected = list(dict.fromkeys(ids.split(',')))
        if len(selected) > 200:
            raise ResearchError('TOO_MANY_CITATIONS', 422)
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            s.validate_evidence(c, project_id, {'evidence_ids': selected})
            result = []
            for aid in selected:
                anchor = row(c, db.anchors, db.anchors.c.project_id == project_id, db.anchors.c.id == aid)
                segment = row(c, db.segments, db.segments.c.id == anchor['segment_id'])
                asset = s.asset(c, project_id, segment['asset_id'])
                title = str(asset['metadata'].get('title') or asset['name'])[:45]
                location = '摘要快照' if asset['metadata'].get('source_quality') == 'search_excerpt' else ('网页快照' if asset['metadata'].get('source_url') and asset['metadata'].get('source_mime')!='application/pdf' else ('文件页 '+segment['page_label'] if segment['page_label'] else None))
                label = ' · '.join(str(x) for x in [asset['metadata'].get('author'), title, location] if x)
                result.append({'anchor_id': aid, 'label': label, 'version_id': segment['version_id']})
            return result

    @router.post('/artifacts/{rid}/chapters/order', response_model=list[ChapterOut])
    def order_chapters(project_id: str, rid: str, body: ChapterOrderIn, actor=Depends(identity), s=Depends(service)):
        from .manuscripts import save_chapter
        with s.engine.begin() as c:
            s.access(c, project_id, actor, True)
            artifact(c, s, project_id, rid)
            existing = rows(c, db.document_chapters, db.document_chapters.c.project_id == project_id, db.document_chapters.c.record_id == rid)
            supplied = [item.get('id') for item in body.chapters]
            if len(set(supplied)) != len(supplied) or set(supplied) != {item['id'] for item in existing}:
                raise ResearchError('CHAPTER_SET_CHANGED', 409)
            by_id = {item['id']: item for item in existing}
            result = []
            for ordinal, item in enumerate(body.chapters):
                old = by_id[item['id']]
                if old['revision'] != item.get('revision'):
                    raise ResearchError('REVISION_CONFLICT', 409)
                result.append(save_chapter(s, c, project_id, rid, old['id'], old['revision'], ordinal, old['payload']))
            return result

    @router.get('/membership')
    def membership(project_id: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            return row(c, db.members, db.members.c.project_id == project_id, db.members.c.user_id == actor)

    @router.get('/members')
    def members(project_id: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            return rows(c, db.members, db.members.c.project_id == project_id)

    @router.put('/members/{uid}')
    def set_member(project_id: str, uid: str, body: MemberIn, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            owner(s, c, project_id, actor)
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
            old = row(c, db.members, db.members.c.project_id == project_id, db.members.c.user_id == uid)
            owners = rows(c, db.members, db.members.c.project_id == project_id, db.members.c.role == 'owner')
            if old and old['role'] == 'owner' and body.role != 'owner' and len(owners) <= 1:
                raise ResearchError('LAST_OWNER_REQUIRED', 409)
            from sqlalchemy.dialects.postgresql import insert
            c.execute(insert(db.members).values(project_id=project_id, user_id=uid, role=body.role).on_conflict_do_update(
                index_elements=['project_id', 'user_id'], set_={'role': body.role}))
            audit(c, project_id, actor, 'member.role_changed', uid, {'role': body.role})
        return {'user_id': uid, 'role': body.role}

    @router.delete('/members/{uid}')
    def remove_member(project_id: str, uid: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            owner(s, c, project_id, actor)
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
            member = row(c, db.members, db.members.c.project_id == project_id, db.members.c.user_id == uid)
            if member and member['role'] == 'owner' and len(rows(c, db.members, db.members.c.project_id == project_id, db.members.c.role == 'owner')) == 1:
                raise ResearchError('LAST_OWNER_REQUIRED', 409)
            c.execute(db.members.delete().where(db.members.c.project_id == project_id, db.members.c.user_id == uid))
            audit(c, project_id, actor, 'member.removed', uid)
        return {'removed': True}

    @router.get('/policy')
    def policy(project_id: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            found = row(c, db.project_policies, db.project_policies.c.project_id == project_id)
            return found or {'project_id': project_id, 'revision': 0, 'payload': {'allow_external': False, 'allowed_hosts': [], 'token_budget': 40000}}

    @router.put('/policy')
    def save_policy(project_id: str, body: PolicyIn, actor=Depends(identity), s=Depends(service)):
        import re
        if any(not re.fullmatch(r'[a-zA-Z0-9.-]+', h) for h in body.allowed_hosts):
            raise ResearchError('INVALID_ENDPOINT_HOST', 422)
        if body.allow_external and not body.allowed_hosts:
            raise ResearchError('AUTHORIZED_ENDPOINTS_REQUIRED', 422)
        with s.engine.begin() as c:
            owner(s, c, project_id, actor)
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
            old = row(c, db.project_policies, db.project_policies.c.project_id == project_id)
            if (old or {}).get('revision', 0) != body.revision:
                raise ResearchError('REVISION_CONFLICT', 409)
            for aid in body.asset_ids or []:
                s.asset(c, project_id, aid)
            for vid in body.version_ids or []:
                version=row(c,db.versions,db.versions.c.id==vid)
                if not version or not row(c,db.assets,db.assets.c.id==version['asset_id'],db.assets.c.project_id==project_id):
                    raise ResearchError('SCOPE_VERSION_MISMATCH',422)
            payload = body.model_dump(exclude={'revision'})
            from sqlalchemy.dialects.postgresql import insert
            c.execute(insert(db.project_policies).values(project_id=project_id, revision=body.revision + 1, payload=payload).on_conflict_do_update(
                index_elements=['project_id'], set_={'revision': body.revision + 1, 'payload': payload}))
            audit(c, project_id, actor, 'policy.changed', project_id, {'revision': body.revision + 1})
        return {'revision': body.revision + 1, 'payload': payload}

    @router.put('/materials/{aid}/classification')
    def classify(project_id: str, aid: str, body: ClassificationIn, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            owner(s,c,project_id,actor)
            old=s.asset(c,project_id,aid)
            if old['revision']!=body.revision:
                raise ResearchError('REVISION_CONFLICT',409)
            c.execute(db.assets.update().where(db.assets.c.id==aid).values(metadata={**old['metadata'],'sensitive':body.sensitive},revision=body.revision+1))
            c.execute(db.outbox.insert().values(id=db.uid(),project_id=project_id,asset_id=aid,revision=body.revision+1,done=False,attempts=0,created_at=db.now()))
            audit(c,project_id,actor,'material.classified',aid,{'sensitive':body.sensitive})
        return {'revision':body.revision+1,'sensitive':body.sensitive}

    @router.get('/audit')
    def history(project_id: str, limit: int = 50, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            owner(s, c, project_id, actor)
            return [dict(r) for r in c.execute(sa.select(db.audit).where(db.audit.c.project_id == project_id)
                .order_by(db.audit.c.created_at.desc()).limit(max(1, min(limit, 200)))).mappings()]

    @router.get('/conversations/{cid}/workspace', response_model=WorkspaceOut)
    def workspace(project_id: str, cid: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor); old = conversation(s, c, project_id, cid)
            found = row(c, db.workspaces, db.workspaces.c.project_id == project_id,
                db.workspaces.c.user_id == actor, db.workspaces.c.conversation_id == cid)
            project = row(c, db.projects, db.projects.c.id == project_id)
            return found or {'revision': 0, 'payload': old['workspace'] if project['owner_id'] == actor else {}}

    @router.put('/conversations/{cid}/workspace', response_model=WorkspaceOut)
    def save_workspace(project_id: str, cid: str, body: WorkspaceIn, actor=Depends(identity), s=Depends(service)):
        if len(json.dumps(body.payload)) > 250000:
            raise ResearchError('WORKSPACE_TOO_LARGE', 413)
        with s.engine.begin() as c:
            s.access(c, project_id, actor); conversation(s, c, project_id, cid)
            c.execute(sa.select(db.conversations.c.id).where(db.conversations.c.id == cid).with_for_update())
            old = row(c, db.workspaces, db.workspaces.c.project_id == project_id, db.workspaces.c.user_id == actor, db.workspaces.c.conversation_id == cid)
            if (old or {}).get('revision', 0) != body.revision:
                raise ResearchError('REVISION_CONFLICT', 409)
            from sqlalchemy.dialects.postgresql import insert
            c.execute(insert(db.workspaces).values(project_id=project_id, user_id=actor, conversation_id=cid,
                revision=body.revision + 1, payload=body.payload).on_conflict_do_update(
                index_elements=['project_id', 'user_id', 'conversation_id'], set_={'revision': body.revision + 1, 'payload': body.payload}))
        return {'revision': body.revision + 1, 'payload': body.payload}

    @router.get('/tasks', response_model=list[TaskOut])
    def tasks(project_id: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            columns = [db.jobs.c.id, db.jobs.c.kind, db.jobs.c.state, db.jobs.c.error, db.jobs.c.result,
                db.jobs.c.payload['conversation_id'].as_string().label('conversation_id'),
                db.jobs.c.payload['record_id'].as_string().label('record_id')]
            found = c.execute(sa.select(*columns).where(db.jobs.c.project_id == project_id).order_by(
                sa.case((db.jobs.c.state.in_(['queued', 'running', 'cancel_requested']), 0), else_=1),
                db.jobs.c.created_at.desc()).limit(250)).mappings()
            return [{**r, 'phase': r['kind'], 'actions': ['cancel'] if r['state'] in {'queued', 'running'}
                else ['retry'] if r['state'] == 'failed' else []} for r in found]

    def artifact(c, s, pid, rid):
        record = row(c, db.records, db.records.c.id == rid, db.records.c.project_id == pid)
        if not record:
            raise ResearchError('ARTIFACT_NOT_FOUND', 404)
        s.validate_evidence(c, pid, record['payload'])
        return record

    @router.get('/artifacts/{rid}/comments')
    def comments(project_id: str, rid: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor); artifact(c, s, project_id, rid)
            return rows(c, db.comments, db.comments.c.record_id == rid, db.comments.c.project_id == project_id)

    @router.post('/artifacts/{rid}/comments', status_code=201)
    def add_comment(project_id: str, rid: str, body: CommentIn, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor); artifact(c, s, project_id, rid)
            member = row(c, db.members, db.members.c.project_id == project_id, db.members.c.user_id == actor)
            if member['role'] == 'reader':
                raise ResearchError('REVIEW_PERMISSION_REQUIRED', 403)
            item = {'id': db.uid(), 'project_id': project_id, 'record_id': rid, 'author': actor, 'text': body.text, 'state': 'open', 'created_at': db.now()}
            c.execute(db.comments.insert().values(**item)); audit(c, project_id, actor, 'comment.created', rid)
            return item

    @router.put('/comments/{comment_id}')
    def resolve_comment(project_id: str, comment_id: str, body: CommentState, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor)
            item = row(c, db.comments, db.comments.c.id == comment_id, db.comments.c.project_id == project_id)
            if not item:
                raise ResearchError('COMMENT_NOT_FOUND', 404)
            if actor != item['author']:
                s.access(c, project_id, actor, True)
            c.execute(db.comments.update().where(db.comments.c.id == comment_id).values(state=body.state))
            audit(c, project_id, actor, 'comment.' + body.state, comment_id)
        return {'state': body.state}

    @router.post('/artifacts/{rid}/restore')
    def restore(project_id: str, rid: str, body: RestoreIn, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor, True); record = artifact(c, s, project_id, rid)
            old = row(c, db.record_history, db.record_history.c.record_id == rid, db.record_history.c.revision == body.source_revision)
            if not old:
                raise ResearchError('REVISION_NOT_FOUND', 404)
            result = s.put_record(c, project_id, record['kind'], old['payload'], rid, body.revision)
            audit(c, project_id, actor, 'artifact.restored', rid, {'from_revision': body.source_revision})
            return result

    @router.get('/artifacts/{rid}/change-proposals', response_model=list[ProposalOut])
    def proposals(project_id: str, rid: str, actor=Depends(identity), s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c, project_id, actor); artifact(c, s, project_id, rid)
            return rows(c, db.change_proposals, db.change_proposals.c.record_id == rid, db.change_proposals.c.project_id == project_id)

    @router.post('/artifacts/{rid}/change-proposals', status_code=202, response_model=JobOut)
    def suggest(project_id: str, rid: str, body: ProposalIn, idempotency_key: str | None = Header(default=None), actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor, True); record = artifact(c, s, project_id, rid)
            if body.conversation_id:
                conversation(s, c, project_id, body.conversation_id)
            target = record
            if body.chapter_id:
                from .manuscripts import chapter
                target = chapter(s, c, project_id, rid, body.chapter_id)
            if target['revision'] != body.base_revision:
                raise ResearchError('REVISION_CONFLICT', 409)
            from .documents import citation_ids
            aids=set(target['payload'].get('asset_ids', []))
            for anchor_id in set(target['payload'].get('evidence_ids', []) + citation_ids(target['payload'].get('editor_json'))):
                anchor=row(c,db.anchors,db.anchors.c.id==anchor_id,db.anchors.c.project_id==project_id)
                segment=row(c,db.segments,db.segments.c.id==anchor['segment_id']) if anchor else None
                if segment:aids.add(segment['asset_id'])
            return s.enqueue(c, project_id, 'edit', {'record_id': rid, 'base_revision': body.base_revision,
                'instruction': body.instruction, 'chapter_id': body.chapter_id, 'principal': actor, 'provider_mode': body.provider_mode,
                'conversation_id': body.conversation_id, 'asset_ids': sorted(aids)}, idempotency_key or db.uid())

    @router.post('/change-proposals/{proposal_id}', response_model=ProposalOut)
    def decide_proposal(project_id: str, proposal_id: str, body: ProposalDecision, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor, True)
            item = c.execute(sa.select(db.change_proposals).where(db.change_proposals.c.id == proposal_id,
                db.change_proposals.c.project_id == project_id).with_for_update()).mappings().first()
            if not item:
                raise ResearchError('PROPOSAL_NOT_FOUND', 404)
            if item['state'] != 'pending':
                raise ResearchError('PROPOSAL_ALREADY_RESOLVED', 409)
            record = artifact(c, s, project_id, item['record_id'])
            if body.action == 'accept':
                chapter_id = item['payload'].get('chapter_id')
                if chapter_id:
                    from .manuscripts import chapter, save_chapter
                    old = chapter(s, c, project_id, record['id'], chapter_id)
                    save_chapter(s, c, project_id, record['id'], chapter_id, item['base_revision'],
                        old['ordinal'], {**old['payload'], **item['payload']['proposed']})
                else:
                    s.put_record(c, project_id, record['kind'], {**record['payload'], **item['payload']['proposed'],
                        'status': 'researcher_revision', 'author_id': actor}, record['id'], item['base_revision'])
            state = 'accepted' if body.action == 'accept' else 'rejected'
            c.execute(db.change_proposals.update().where(db.change_proposals.c.id == proposal_id).values(state=state))
            audit(c, project_id, actor, 'proposal.' + state, proposal_id)
            return {**item, 'state': state}

    @router.post('/artifacts/{rid}/exports', status_code=202, response_model=JobOut)
    def export(project_id: str, rid: str, body: ExportIn, idempotency_key: str | None = Header(default=None), actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c, project_id, actor)
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == project_id).with_for_update())
            if idempotency_key:
                previous = row(c, db.jobs, db.jobs.c.project_id == project_id, db.jobs.c.kind == 'export', db.jobs.c.idem == idempotency_key)
                if previous:
                    if any(previous['payload'].get(k) != v for k, v in {**body.model_dump(exclude_none=True), 'record_id': rid}.items()):
                        raise ResearchError('IDEMPOTENCY_CONFLICT', 409)
                    return previous
            from .manuscripts import export_snapshot
            if body.conversation_id:
                conversation(s, c, project_id, body.conversation_id)
            snapshot = export_snapshot(s, c, project_id, rid, body.revision)
            return s.enqueue(c, project_id, 'export', {**body.model_dump(), 'record_id': rid, 'principal': actor,
                'snapshot': snapshot, 'asset_ids': [a['id'] for a in snapshot['assets']]}, idempotency_key or db.uid())

    @router.get('/exports/{jid}/download')
    def download(project_id: str, jid: str, actor=Depends(identity), s=Depends(service)):
        from fastapi.responses import Response
        with s.engine.connect() as c:
            s.access(c, project_id, actor)
            job = row(c, db.jobs, db.jobs.c.id == jid, db.jobs.c.project_id == project_id, db.jobs.c.kind == 'export')
            if not job or job['state'] != 'succeeded':
                raise ResearchError('EXPORT_NOT_READY', 409)
            artifact(c, s, project_id, job['payload']['record_id'])
            for item in ([job['payload']['snapshot']['record'], *job['payload']['snapshot']['chapters']] if job['payload'].get('snapshot') else []):
                s.validate_evidence(c, project_id, item['payload'])
            result = job['result']
        mime = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'html': 'text/html', 'md': 'text/markdown'}[result['format']]
        return Response(s.objects.read(result['object_key']), media_type=mime,
            headers={'Content-Disposition': 'attachment; filename=' + result['filename'], 'Cache-Control': 'no-store'})

    app.include_router(router)
