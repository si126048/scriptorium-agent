"""Project-scoped source provenance and explicit collection decisions."""
from typing import Literal
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import schema as db
from .service import ResearchError, row, rows
from . import collection
from .events import emit


class SourceOut(BaseModel):
    id:str; job_id:str; revision:int; title:str; url:str; source_type:str; availability:str
    snippet:str=''; asset_id:str|None=None; version_id:str|None=None
    adopted:bool=False; excluded:bool=False; read:bool=False; used_in_report:bool=False
    retrieved_at:float|None=None; error:str|None=None; provider:str|None=None; snapshot_key:str|None=None
    bibliography:dict[str,str]=Field(default_factory=dict)
    conversation_id:str|None=None
    original_format:str|None=None
    locations:list[dict]=Field(default_factory=list)
    attempts:list[dict]=Field(default_factory=list)
    version_status:str="unconfirmed"


class SourcePageOut(BaseModel):
    items:list[SourceOut]
    total:int
    next_offset:int|None=None


class IntakeOut(BaseModel):
    job_id:str; state:str; revision:int; question:str; phase:str
    decision:str|None=None; limits:dict[str,int]; downloaded_bytes:int; reserved_bytes:int=0; source_count:int; read_count:int=0; fulltext_count:int=0; research_run_id:str|None=None
    used_tokens:int=0; reserved_tokens:int=0; discovery_requests:int=0


class SourceAction(BaseModel):
    job_id:str
    revision:int=Field(ge=1)
    action:Literal['adopt','unadopt','exclude','include','fetch']


class IntakeAction(BaseModel):
    revision:int=Field(ge=1)
    action:Literal['continue','use_collected','use_project','stop','resume']


def install(app,service,identity):
    router=APIRouter(prefix='/api/v2/projects/{project_id}')

    @app.get('/api/v2/system/model/capabilities')
    def model_capabilities(principal=Depends(identity)):
        from .native_search import capabilities
        return capabilities()

    @router.get('/sources',response_model=SourcePageOut)
    def sources(project_id:str,conversation_id:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200),q:str=Query('',max_length=500),availability:str|None=None,source_type:str|None=None,adopted:bool|None=None,principal=Depends(identity),s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c,project_id,principal)
            filters={'q':q,'availability':availability,'source_type':source_type,'adopted':adopted}
            query=collection.source_query(project_id,cid=conversation_id,**filters)
            total=c.execute(sa.select(sa.func.count()).select_from(query.subquery())).scalar()
        items=collection.list_sources(s,project_id,principal,conversation_id,offset,limit,**filters)
        return {'items':items,'total':total,'next_offset':offset+len(items) if offset+len(items)<total else None}

    @router.get('/sources/{sid}',response_model=SourceOut)
    def detail(project_id:str,sid:str,job_id:str,principal=Depends(identity),s=Depends(service)):
        value=next((x for x in collection.list_sources(s,project_id,principal,source_id=sid,job_id=job_id) if x['id']==sid and x['job_id']==job_id),None)
        if not value:raise ResearchError('SOURCE_NOT_FOUND',404)
        with s.engine.connect() as c:
            value['locations']=[{'id':x['id'],'url':x['url'],**x['payload']} for x in rows(c,db.source_locations,db.source_locations.c.source_id==sid)]
            value['attempts']=[{'id':x['id'],'state':x['state'],'created_at':x['created_at'],**{k:v for k,v in x['payload'].items() if k!='original_object_key'}} for x in rows(c,db.acquisition_attempts,db.acquisition_attempts.c.source_id==sid,db.acquisition_attempts.c.job_id==job_id)]
        return value

    @router.get('/sources/{sid}/snapshot')
    def snapshot(project_id:str,sid:str,job_id:str,principal=Depends(identity),s=Depends(service)):
        value=detail(project_id,sid,job_id,principal,s)
        if value['availability']=='withdrawn':raise ResearchError('SOURCE_WITHDRAWN',404)
        if not value.get('snapshot_key'):raise ResearchError('SOURCE_SNAPSHOT_NOT_FOUND',404)
        import json
        return json.loads(s.objects.read(value['snapshot_key']))

    @router.get('/sources/{sid}/original')
    def original(project_id:str,sid:str,job_id:str,principal=Depends(identity),s=Depends(service)):
        value=detail(project_id,sid,job_id,principal,s)
        if value['availability']=='withdrawn':raise ResearchError('SOURCE_WITHDRAWN',404)
        with s.engine.connect() as c:
            link=row(c,db.run_sources,db.run_sources.c.job_id==job_id,db.run_sources.c.source_id==sid)
            key=link['payload'].get('original_object_key') if link else None
        if not key:raise ResearchError('SOURCE_ORIGINAL_UNAVAILABLE',404)
        return Response(s.objects.read(key),media_type='application/octet-stream',headers={
            'Content-Disposition':'attachment; filename="source-snapshot.'+(value.get('original_format') or 'bin')+'"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @router.post('/sources/{sid}/actions')
    def action(project_id:str,sid:str,body:SourceAction,idempotency_key:str=Header(min_length=1,max_length=128),
               principal=Depends(identity),s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c,project_id,principal,True)
            source=row(c,db.sources,db.sources.c.id==sid,db.sources.c.project_id==project_id)
            job=row(c,db.jobs,db.jobs.c.id==body.job_id,db.jobs.c.project_id==project_id)
            if not source or not job:raise ResearchError('SOURCE_NOT_FOUND',404)
            c.execute(sa.select(db.sources.c.id).where(db.sources.c.id==sid).with_for_update())
            link=row(c,db.run_sources,db.run_sources.c.source_id==sid,db.run_sources.c.job_id==body.job_id)
            if not link:raise ResearchError('SOURCE_NOT_FOUND',404)
            if source['payload'].get('availability')=='withdrawn':raise ResearchError('SOURCE_WITHDRAWN',404)
            if link['payload'].get('asset_id'):s.asset(c,project_id,link['payload']['asset_id'])
            if body.action=='fetch':
                if job['state'] in {'queued','running'}:raise ResearchError('SOURCE_COLLECTION_IN_PROGRESS',409)
                queued=s.enqueue(c,project_id,'source_fetch',{'principal':principal,'source_id':sid,
                    'collection_job_id':body.job_id,'conversation_id':job['payload']['conversation_id'],'retry_source':True},idempotency_key)
                if link['payload'].get('fetch_job_id')==queued['id']:return queued
                if link['revision']!=body.revision:raise ResearchError('REVISION_CONFLICT',409)
                c.execute(db.run_sources.update().where(db.run_sources.c.source_id==sid,db.run_sources.c.job_id==body.job_id)
                    .values(payload={**link['payload'],'fetch_job_id':queued['id'],'availability':'fetching'},revision=link['revision']+1))
                c.execute(db.sources.update().where(db.sources.c.id==sid).values(payload={**source['payload'],'availability':'fetching'},revision=source['revision']+1))
                emit(c,project_id,job['payload']['conversation_id'],'source.updated',{'job_id':body.job_id,'source_id':sid})
                return queued
            if link['revision']!=body.revision:raise ResearchError('REVISION_CONFLICT',409)
            patch={'adopted':body.action=='adopt'} if body.action in {'adopt','unadopt'} else {'excluded':body.action=='exclude'}
            c.execute(db.run_sources.update().where(db.run_sources.c.source_id==sid,db.run_sources.c.job_id==body.job_id)
                .values(payload={**link['payload'],**patch},revision=link['revision']+1))
            emit(c,project_id,job['payload']['conversation_id'],'source.updated',{'job_id':body.job_id,'source_id':sid})
        return {'state':'updated'}

    @router.get('/intakes',response_model=list[IntakeOut])
    def intakes(project_id:str,conversation_id:str|None=None,principal=Depends(identity),s=Depends(service)):
        with s.engine.connect() as c:
            s.access(c,project_id,principal)
            query=sa.select(db.intakes,db.jobs.c.payload.label('job_payload'),db.jobs.c.state.label('job_state'),db.jobs.c.result.label('job_result')).join(db.jobs,db.jobs.c.id==db.intakes.c.job_id).where(db.intakes.c.project_id==project_id)
            if conversation_id:query=query.where(db.intakes.c.conversation_id==conversation_id)
            result=[]
            for value in c.execute(query.order_by(db.intakes.c.created_at.desc()).limit(80)).mappings():
                p=value['payload']
                state=value['job_state'] if value['job_state'] in {'cancelled','cancel_requested','failed'} else value['state']
                if value['job_state']=='queued':state='planning'
                if value['job_state']=='running' and state in {'completed','awaiting_input'}:state='analyzing'
                if value['job_state']=='succeeded':
                    if (value['job_result'] or {}).get('state')=='awaiting_input':state='awaiting_input'
                    if (value['job_result'] or {}).get('record_id'):state='completed'
                linked=rows(c,db.run_sources,db.run_sources.c.job_id==value['job_id'])
                held=sum(x['payload'].get('unknown_download_bytes',0)+(x['payload'].get('download_reserved',0) if 'download_bytes' not in x['payload'] else 0) for x in linked)
                run_id=p.get('research_run_id')
                calls=rows(c,db.model_calls,sa.or_(db.model_calls.c.job_id==value['job_id'],db.model_calls.c.run_id==run_id) if run_id else db.model_calls.c.job_id==value['job_id'])
                result.append({'used_tokens':sum((x['usage'] or {}).get('total_tokens',0) for x in calls),
                    'reserved_tokens':sum(x['reserved_tokens'] for x in calls if x['state'] in {'reserved','unknown'}),
                    'discovery_requests':len(rows(c,db.discovery_calls,db.discovery_calls.c.job_id==value['job_id'])),
                    'job_id':value['job_id'],'state':state,'revision':value['revision'],
                    'phase':state,'question':value['job_payload'].get('text',''),'decision':p.get('decision'),
                    'limits':p['limits'],'downloaded_bytes':max(0,p.get('download_bytes',0)-held),'reserved_bytes':held,'research_run_id':p.get('research_run_id'),
                    'source_count':len(linked),'read_count':sum(bool(x['payload'].get('read')) for x in linked),'fulltext_count':sum(x['payload'].get('availability')=='fulltext' for x in linked)})
            return result

    @router.post('/intakes/{job_id}/decisions')
    def decide(project_id:str,job_id:str,body:IntakeAction,principal=Depends(identity),s=Depends(service)):
        with s.engine.begin() as c:
            s.access(c,project_id,principal,True)
            value=c.execute(sa.select(db.intakes).where(db.intakes.c.job_id==job_id,db.intakes.c.project_id==project_id).with_for_update()).mappings().first()
            if not value:raise ResearchError('RESEARCH_NOT_FOUND',404)
            job=row(c,db.jobs,db.jobs.c.id==job_id)
            if value['revision']!=body.revision:raise ResearchError('REVISION_CONFLICT',409)
            p=dict(value['payload'])
            if body.action=='resume':
                if job['state'] not in {'failed','cancelled'}:raise ResearchError('RESEARCH_NOT_RESUMABLE',409)
                for run in rows(c,db.research_runs,db.research_runs.c.project_id==project_id):
                    if run['settings'].get('origin_job_id')!=job_id:continue
                    c.execute(db.research_runs.update().where(db.research_runs.c.id==run['id']).values(state='running'))
                    for step in rows(c,db.research_steps,db.research_steps.c.run_id==run['id'],db.research_steps.c.state!='succeeded'):
                        child_id=(step['result'] or {}).get('job_id')
                        if child_id:c.execute(db.jobs.update().where(db.jobs.c.id==child_id,db.jobs.c.state.in_(['failed','cancelled'])).values(state='queued',attempts=0,lease_until=None,lease_token=None,error=None))
            else:
                if value['state']!='awaiting_input':raise ResearchError('REVISION_CONFLICT',409)
                if p.get('research_run_id') and not p.get('decision'):raise ResearchError('USE_RESEARCH_DECISION',409)
                if job['state'] in {'running','queued','cancel_requested','cancelled'}:raise ResearchError('RESEARCH_NOT_RESUMABLE',409)
            payload={**job['payload'],'principal':principal,'writer_retry':body.action in {'continue','resume'}}
            if body.action=='continue':
                p['limits']={k:p['limits'][k]+v for k,v in collection.DEFAULT_LIMITS.items()}
                payload['token_budget']=min(1000000,payload.get('_auto_total_budget',payload.get('token_budget',40000))+40000)
                payload['_auto_total_budget']=payload['token_budget']
                p.update(discovered=bool(p.get('scope')),use_collected=bool(p.get('scope')))
                for call in rows(c,db.discovery_calls,db.discovery_calls.c.job_id==job_id):
                    c.execute(db.discovery_calls.update().where(db.discovery_calls.c.id==call['id']).values(payload={**call['payload'],'retry_authorized':True}))
            elif body.action=='stop':p['stop']=True
            elif body.action!='resume':p[body.action]=True
            c.execute(db.intakes.update().where(db.intakes.c.job_id==job_id).values(payload={**p,'decision':None},state='planning',revision=value['revision']+1))
            c.execute(db.jobs.update().where(db.jobs.c.id==job_id).values(payload=payload,state='queued',error=None,lease_token=None,lease_until=None,attempts=0))
            emit(c,project_id,value['conversation_id'],'research.phase',{'job_id':job_id,'phase':'planning'})
        return {'state':'queued'}

    app.include_router(router)
