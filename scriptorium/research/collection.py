"""Durable source collection with explicit availability and immutable per-run snapshots."""
import hashlib
import json
import re
import sqlalchemy as sa
from . import schema as db
from .service import ResearchError, row, rows
from .events import emit
from .public_fetch import normalized_url, fetch, readable_html, html_metadata

DEFAULT_LIMITS = {'requests':3,'sources':20,'fulltexts':10,'bytes':100*1024*1024,'metadata_requests':12}


def ensure_intake(s, job):
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload']['principal'], True); s.locked_job(c,job)
        value = row(c,db.intakes,db.intakes.c.job_id==job['id'])
        if value:
            return value
        value = {'job_id':job['id'],'project_id':job['project_id'],'conversation_id':job['payload']['conversation_id'],
            'state':'planning','revision':1,'payload':{'limits':dict(DEFAULT_LIMITS),'download_bytes':0},'created_at':db.now()}
        c.execute(db.intakes.insert().values(**value))
        return value


def checkpoint(s, job, state, **patch):
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        value = dict(c.execute(sa.select(db.intakes).where(db.intakes.c.job_id==job['id']).with_for_update()).mappings().one())
        payload = {**value['payload'],**patch}
        c.execute(db.intakes.update().where(db.intakes.c.job_id==job['id']).values(state=state,payload=payload,revision=value['revision']+1))
        emit(c,job['project_id'],job['payload']['conversation_id'],'research.phase',{'job_id':job['id'],'phase':state})
        if job.get('_timeline_generation'):
            from .timeline import put
            plan=row(c,db.timeline_blocks,db.timeline_blocks.c.job_id==job['id'],db.timeline_blocks.c.block_key=='plan')
            if plan:
                index={'planning':0,'discovering':0,'collecting':0,'reading':1,'analyzing':2}.get(state,plan['payload'].get('current_index',0))
                put(c,s,job,'plan','plan','waiting' if state=='awaiting_input' else 'running',{**plan['payload'],'current_index':index})
            titles={'discovering':'寻找公开来源','collecting':'获取与整理材料','reading':'阅读相关原文','analyzing':'分析与检验','awaiting_input':'等待研究决定'}
            for block in rows(c,db.timeline_blocks,db.timeline_blocks.c.job_id==job['id'],db.timeline_blocks.c.kind=='activity',db.timeline_blocks.c.state=='running'):
                if block['block_key'].startswith('phase:') and block['block_key']!='phase:'+state:
                    put(c,s,job,block['block_key'],'activity','completed',block['payload'])
            put(c,s,job,'phase:'+state,'activity','waiting' if state=='awaiting_input' else 'running',{'title':titles.get(state,state),'reason':patch.get('decision')})
        return payload


def check_owned(s, job):
    with s.engine.connect() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        policy=row(c,db.project_policies,db.project_policies.c.project_id==job['project_id'])
        if policy and (policy['payload'].get('allow_external') is False or policy['payload'].get('allow_web') is False):
            raise ResearchError('PROJECT_EXTERNAL_PROCESSING_DISABLED',403)


def register(s, job, item):
    try:url=normalized_url(item['url'])
    except (ValueError,ResearchError):return None
    doi=item.get('doi') or (url.split('doi.org/',1)[1] if 'doi.org/' in url else '')
    doi=doi.strip().lower() if isinstance(doi,str) else ''
    doi=doi if re.fullmatch(r'10\.\d{4,9}/[^\s]+',doi) else ''
    identity=hashlib.sha256(('doi:'+doi if doi else normalized_url(url,canonical=True)).encode()).hexdigest()
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        c.execute(sa.select(db.projects.c.id).where(db.projects.c.id==job['project_id']).with_for_update())
        source=row(c,db.sources,db.sources.c.project_id==job['project_id'],db.sources.c.identity==identity)
        if not source:
            payload={**item,'url':url,'availability':'summary' if item.get('snippet') else 'discovered',
                'source_type':item.get('source_type') or ('academic' if doi else 'web'),'doi':doi,'asset_id':None,'read':False}
            source={'id':db.uid(),'project_id':job['project_id'],'identity':identity,'payload':payload,'revision':1,'created_at':db.now()}
            c.execute(db.sources.insert().values(**source))
        link=row(c,db.run_sources,db.run_sources.c.job_id==job['id'],db.run_sources.c.source_id==source['id'])
        if not link:
            snapshot_key,_=s.objects.put(json.dumps(item,ensure_ascii=False).encode())
            c.execute(db.run_sources.insert().values(job_id=job['id'],source_id=source['id'],revision=1,
                payload={**item,'snapshot_key':snapshot_key,'adopted':False,'excluded':False,'used_in_report':False,
                         'asset_id':source['payload'].get('asset_id'),'version_id':source['payload'].get('version_id'),'original_object_key':source['payload'].get('original_object_key'),'mime':source['payload'].get('source_mime'),'availability':source['payload'].get('availability','discovered'),'read':False}))
        for candidate in [*item.get('locations',[]),url][:3]:
            try:location_url=normalized_url(candidate)
            except (TypeError,ValueError,ResearchError):continue
            location_identity=hashlib.sha256(location_url.encode()).hexdigest()
            if not row(c,db.source_locations,db.source_locations.c.source_id==source['id'],db.source_locations.c.identity==location_identity):
                c.execute(db.source_locations.insert().values(id=db.uid(),source_id=source['id'],url=location_url,identity=location_identity,
                    payload={'provider':item.get('provider'),'version_status':item.get('version_status','unconfirmed'),'state':'discovered'},created_at=db.now()))
        emit(c,job['project_id'],job['payload']['conversation_id'],'source.discovered',{'job_id':job['id'],'source_id':source['id']})
        return source['id']


def source_query(pid,job_id=None,cid=None,source_id=None,q='',availability=None,source_type=None,adopted=None):
    query=sa.select(db.sources,db.run_sources.c.job_id,db.run_sources.c.payload.label('association'),
        db.run_sources.c.revision.label('association_revision'),db.jobs.c.payload.label('job_payload')).join(
        db.run_sources,db.run_sources.c.source_id==db.sources.c.id).join(db.jobs,db.jobs.c.id==db.run_sources.c.job_id).where(db.sources.c.project_id==pid)
    if job_id:query=query.where(db.run_sources.c.job_id==job_id)
    if cid:query=query.where(db.jobs.c.payload['conversation_id'].as_string()==cid)
    if source_id:query=query.where(db.sources.c.id==source_id)
    state=sa.func.coalesce(db.run_sources.c.payload['availability'].as_string(),db.sources.c.payload['availability'].as_string())
    query=query.where(state==availability if availability else state!='withdrawn')
    if source_type:query=query.where(db.sources.c.payload['source_type'].as_string()==source_type)
    if adopted is not None:query=query.where(db.run_sources.c.payload['adopted'].as_boolean()==adopted)
    if q:query=query.where(sa.or_(sa.func.lower(db.sources.c.payload['title'].as_string()).contains(q.lower(),autoescape=True),
        sa.func.lower(db.sources.c.payload['url'].as_string()).contains(q.lower(),autoescape=True)))
    if not job_id:
        ranked=query.add_columns(sa.func.row_number().over(partition_by=db.sources.c.id,order_by=[db.jobs.c.created_at.desc(),db.jobs.c.id.desc()]).label('_source_rank')).subquery()
        query=sa.select(*[col for col in ranked.c if col.name!='_source_rank']).where(ranked.c._source_rank==1)
    return query


def associated(s,pid,job_id=None,cid=None,source_id=None,limit=None,offset=0,**filters):
    with s.engine.connect() as c:
        query=source_query(pid,job_id,cid,source_id,**filters)
        query=query.order_by(*[query.selected_columns[name] for name in ('created_at','id','job_id')]).offset(offset)
        if limit is not None:query=query.limit(limit)
        return [dict(r) for r in c.execute(query).mappings()]


def update_source(s, job, sid, changes, link_changes=None):
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        value=c.execute(sa.select(db.sources).where(db.sources.c.id==sid,db.sources.c.project_id==job['project_id']).with_for_update()).mappings().first()
        if not value:raise ResearchError('SOURCE_NOT_FOUND',404)
        if value['payload'].get('availability')=='withdrawn':raise ResearchError('SOURCE_WITHDRAWN',404)
        if changes.get('asset_id'):s.asset(c,job['project_id'],changes['asset_id'])
        if changes.get('availability')=='fulltext':changes={**changes,'error':None}
        c.execute(db.sources.update().where(db.sources.c.id==sid).values(payload={**value['payload'],**changes},revision=value['revision']+1))
        root_id=job['payload'].get('collection_job_id') or job['id']
        link=row(c,db.run_sources,db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid)
        if 'error' in changes:link_changes={**(link_changes or {}),'error':changes['error']}
        if 'availability' in changes:
            link_changes={**(link_changes or {}),'availability':changes['availability']}
        if link_changes and link:
            c.execute(db.run_sources.update().where(db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid)
                .values(payload={**link['payload'],**link_changes},revision=link['revision']+1))
        emit(c,job['project_id'],job['payload']['conversation_id'],'source.updated',{'job_id':root_id,'source_id':sid})


def acquire_one(s, job, sid):
    root_id=job['payload'].get('collection_job_id') or job['id']
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        source=c.execute(sa.select(db.sources).where(db.sources.c.id==sid,db.sources.c.project_id==job['project_id']).with_for_update()).mappings().first()
        link=row(c,db.run_sources,db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid)
        if not source or not link:raise ResearchError('SOURCE_NOT_FOUND',404)
        payload={**source['payload'],**({'url':job['_fetch_url']} if job.get('_fetch_url') else {})};saved=link['payload']
        if payload.get('availability')=='withdrawn':raise ResearchError('SOURCE_WITHDRAWN',404)
        if saved.get('excluded'):return
        if saved.get('asset_id'):
            existing=s.asset(c,job['project_id'],saved['asset_id'])
            if existing['metadata'].get('source_quality')!='search_excerpt':return
        owner=saved.get('fetch_job_id')
        if owner and owner!=job['id']:
            other=row(c,db.jobs,db.jobs.c.id==owner)
            if other and other['state'] in {'queued','running'}:raise ResearchError('SOURCE_IMPORT_PENDING',409)
        pending=row(c,db.jobs,db.jobs.c.id==saved['import_job_id']) if saved.get('import_job_id') else None
        cached=saved.get('original_object_key') if saved.get('mime') else None
        if not pending and not cached:
            if saved.get('fetch_attempt_job_id')==job['id'] and not job.get('_alternative_location'):raise ResearchError('SOURCE_FETCH_INTERRUPTED',409)
            if saved.get('fetch_attempted') and not job['payload'].get('retry_source') and not job.get('_alternative_location'):return
            intake=dict(c.execute(sa.select(db.intakes).where(db.intakes.c.job_id==root_id).with_for_update()).mappings().one())
            links=rows(c,db.run_sources,db.run_sources.c.job_id==root_id);limits=intake['payload']['limits']
            if not saved.get('fetch_attempted') and sum(bool(x['payload'].get('fetch_attempted')) for x in links)>=limits['fulltexts']:raise ResearchError('COLLECTION_SOURCE_LIMIT',409)
            remaining=limits['bytes']-intake['payload'].get('download_bytes',0)
            if remaining<=0:raise ResearchError('COLLECTION_DOWNLOAD_LIMIT',409)
            reserved=min(20*1024*1024,remaining)
            unknown=saved.get('unknown_download_bytes',0)+(saved.get('download_reserved',0) if saved.get('fetch_attempted') and 'download_bytes' not in saved else 0)
            c.execute(db.intakes.update().where(db.intakes.c.job_id==root_id).values(payload={**intake['payload'],'download_bytes':intake['payload'].get('download_bytes',0)+reserved}))
            c.execute(db.run_sources.update().where(db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid).values(payload={**saved,'fetch_attempted':True,'fetch_attempt_job_id':job['id'],'download_reserved':reserved,'unknown_download_bytes':unknown}))
    if not pending:
        try:
            if cached:
                raw=s.objects.read(cached);raw_key=cached;raw_hash=hashlib.sha256(raw).hexdigest()
                mime=saved['mime'];url=saved.get('final_url') or payload['url'];retrieved=saved.get('retrieved_at') or db.now()
            else:
                check_owned(s,job);update_source(s,job,sid,{'availability':'fetching'})
                raw,mime,url=fetch(payload['url'],lambda:check_owned(s,job),reserved)
                raw_key,raw_hash=s.objects.put(raw);retrieved=db.now()
                with s.engine.begin() as c:
                    s.locked_job(c,job)
                    current=dict(c.execute(sa.select(db.intakes).where(db.intakes.c.job_id==root_id).with_for_update()).mappings().one())
                    c.execute(db.intakes.update().where(db.intakes.c.job_id==root_id).values(payload={**current['payload'],'download_bytes':current['payload'].get('download_bytes',0)-reserved+len(raw)}))
                update_source(s,job,sid,{}, {'original_object_key':raw_key,'download_bytes':len(raw),'mime':mime,'final_url':url,'retrieved_at':retrieved})
            title=payload['title'];content=raw;bibliography={}
            if mime in {'text/html','application/xhtml+xml'}:
                bibliography=html_metadata(raw);page_title,text=readable_html(raw);title=page_title or title;content=text.encode('utf-8')
            metadata={'title':title,'purpose':'research','source_id':sid,'source_url':url,'source_quality':'fulltext','source_mime':mime,
                'original_object_key':raw_key,'original_sha256':raw_hash,'retrieved_at':retrieved,**bibliography}
            digest=hashlib.sha256(content).hexdigest()
            with s.engine.connect() as c:
                duplicate=row(c,db.assets,db.assets.c.project_id==job['project_id'],db.assets.c.sha256==digest,db.assets.c.status=='ready')
            if duplicate:
                text=s.get_segments(job['project_id'],job['payload']['principal'],duplicate['id'])
                update_source(s,job,sid,{'title':title,'asset_id':duplicate['id'],'availability':'fulltext','original_object_key':raw_key,'source_mime':mime},
                    {'asset_id':duplicate['id'],'version_id':text['version']['id'],'availability':'fulltext','original_object_key':raw_key})
                return
            pending=s.import_material(job['project_id'],job['payload']['principal'],content,'source-'+sid+('.pdf' if mime=='application/pdf' else '.txt'),'source-'+sid+'-'+raw_hash,metadata)
            update_source(s,job,sid,{'title':title,**bibliography,'source_type':'academic' if bibliography.get('doi') or bibliography.get('journal') else payload.get('source_type','web'),
                'original_object_key':raw_key,'source_mime':mime,'sha256':raw_hash,'retrieved_at':retrieved},{'import_job_id':pending['id']})
        except ResearchError as exc:
            if exc.code in {'JOB_NO_LONGER_OWNED','PROJECT_EXTERNAL_PROCESSING_DISABLED','SOURCE_WITHDRAWN'}:raise
            update_source(s,job,sid,{'availability':'restricted' if exc.status in {401,402,403} else 'failed','error':exc.code});return
        except Exception:
            update_source(s,job,sid,{'availability':'failed','error':'SOURCE_FETCH_FAILED'});return
    from .worker import run_one
    if pending['state'] not in {'succeeded','failed','cancelled'}:run_one(s,pending['id'])
    with s.engine.connect() as c:pending=row(c,db.jobs,db.jobs.c.id==pending['id'])
    if pending['state'] in {'queued','running'}:raise ResearchError('SOURCE_IMPORT_PENDING',409)
    if pending['state']!='succeeded':update_source(s,job,sid,{'availability':'failed','error':'SOURCE_IMPORT_FAILED'});return
    aid=pending['payload']['asset_id'];text=s.get_segments(job['project_id'],job['payload']['principal'],aid)
    available=bool(text['segments']);vid=text['version']['id'] if text.get('version') else None
    update_source(s,job,sid,{'availability':'fulltext' if available else 'original_only','asset_id':aid,'version_id':vid},
        {'asset_id':aid,'version_id':vid,'availability':'fulltext' if available else 'original_only'})


def schedule_fetch(s,job,sid):
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        link=row(c,db.run_sources,db.run_sources.c.job_id==job['id'],db.run_sources.c.source_id==sid)
        if link['payload'].get('availability') in {'fulltext','original_only'}:return
        child=s.enqueue(c,job['project_id'],'source_fetch',{'source_id':sid,'collection_job_id':job['id'],
            'conversation_id':job['payload']['conversation_id'],'principal':job['payload']['principal']},'collect-'+job['id']+'-'+sid)
        c.execute(db.run_sources.update().where(db.run_sources.c.job_id==job['id'],db.run_sources.c.source_id==sid)
            .values(payload={**link['payload'],'fetch_job_id':child['id']}))
    from .worker import run_one
    if child['state'] in {'queued','running'}:run_one(s,child['id'])
    with s.engine.connect() as c:current=row(c,db.jobs,db.jobs.c.id==child['id'])
    if current['state'] in {'running','queued'}:raise ResearchError('SOURCE_IMPORT_PENDING',409)
    if current['state'] in {'cancelled','cancel_requested'}:raise ResearchError('SOURCE_FETCH_INTERRUPTED',409)


def acquire(s,job,sid):
    root_id=job['payload'].get('collection_job_id') or job['id']
    with s.engine.connect() as c:
        source=row(c,db.sources,db.sources.c.id==sid,db.sources.c.project_id==job['project_id'])
        locations=rows(c,db.source_locations,db.source_locations.c.source_id==sid)
    if not source:raise ResearchError('SOURCE_NOT_FOUND',404)
    if source['payload'].get('metadata_only'):return
    if not locations:return acquire_one(s,job,sid)
    for location in locations[:3]:
        with s.engine.begin() as c:
            s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
            link=row(c,db.run_sources,db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid)
            if link['payload'].get('availability') in {'fulltext','original_only'}:return
            attempts=rows(c,db.acquisition_attempts,db.acquisition_attempts.c.job_id==root_id,db.acquisition_attempts.c.source_id==sid)
            prior=next((a for a in attempts if a['location_id']==location['id']),None)
            if prior and prior['state'] not in {'returned'} and not job['payload'].get('retry_source'):continue
            if len(attempts)>=3 and not job['payload'].get('retry_source'):return
            aid=db.uid()
            c.execute(db.acquisition_attempts.insert().values(id=aid,job_id=root_id,source_id=sid,location_id=location['id'],
                state='requested',payload={'url':location['url'],'generation':job.get('_timeline_generation')},created_at=db.now()))
        # A previously committed original/import is resumed before changing URL.
        if not link['payload'].get('original_object_key'):
            child={**job,'_fetch_url':location['url'],'_alternative_location':bool(attempts)}
        else:child=job
        acquire_one(s,child,sid)
        with s.engine.begin() as c:
            s.locked_job(c,job)
            current=row(c,db.run_sources,db.run_sources.c.job_id==root_id,db.run_sources.c.source_id==sid)['payload']
            state=current.get('availability','failed')
            c.execute(db.acquisition_attempts.update().where(db.acquisition_attempts.c.id==aid).values(state='returned',
                payload={'url':location['url'],'availability':state,'error':current.get('error'),'bytes':current.get('download_bytes'),'original_object_key':current.get('original_object_key')}))
            c.execute(db.source_locations.update().where(db.source_locations.c.id==location['id']).values(payload={**location['payload'],'state':state}))
        if state in {'fulltext','original_only'}:return
        if current.get('original_object_key') and current.get('error') in {'SOURCE_FETCH_FAILED','SOURCE_IMPORT_FAILED'}:return
        # Preserve earlier raw objects in attempts, but let the next legal location be fetched.
        update_source(s,job,sid,{}, {'original_object_key':None,'mime':None,'import_job_id':None})


def materialize_excerpt(s, job, item):
    """Store only actual provider excerpts, always labelled; never synthesize source text."""
    link=item['association'];data=item['payload']
    if link.get('asset_id') or not link.get('snippet') or link.get('excluded'):return
    content=('【搜索摘要，非原文全文】\n'+link['snippet']).encode('utf-8')
    pending=s.import_material(job['project_id'],job['payload']['principal'],content,'excerpt-'+item['id']+'.txt',
        'excerpt-'+item['id']+'-'+hashlib.sha256(content).hexdigest(),{'title':data['title']+'（搜索摘要）',
            'purpose':'research','source_id':item['id'],'source_url':data['url'],'source_quality':'search_excerpt','source_mime':'text/plain'})
    from .worker import run_one
    run_one(s,pending['id'])
    with s.engine.connect() as c:value=row(c,db.jobs,db.jobs.c.id==pending['id'])
    if value['state']=='succeeded':
        aid=pending['payload']['asset_id'];text=s.get_segments(job['project_id'],job['payload']['principal'],aid)
        update_source(s,job,item['id'],{}, {'asset_id':aid,'version_id':text['version']['id'],'availability':'summary','read':False})


def list_sources(s,pid,actor,cid=None,offset=0,limit=100,source_id=None,job_id=None,**filters):
    with s.engine.connect() as c:s.access(c,pid,actor)
    result=[]
    for source in associated(s,pid,job_id,cid,source_id,limit,offset,**filters):
        if cid and source['job_payload'].get('conversation_id')!=cid:continue
        link=source['association'];p=source['payload'];aid=link.get('asset_id')
        if link.get('availability')=='fetching' and link.get('fetch_job_id'):
            with s.engine.connect() as c: helper=row(c,db.jobs,db.jobs.c.id==link['fetch_job_id'])
            if helper and helper['state'] in {'failed','cancelled'}:
                link={**link,'availability':'failed'};p={**p,'error':helper.get('error') or 'SOURCE_FETCH_INTERRUPTED'}
        if aid:
            with s.engine.connect() as c:
                a=row(c,db.assets,db.assets.c.id==aid)
                if not a or a['status']=='revoked':
                    p={'title':'已撤回来源','url':'','availability':'withdrawn'};link={};aid=None
                else:s.asset(c,pid,aid)
        result.append({'id':source['id'],'job_id':source['job_id'],'revision':source['association_revision'],
            'title':p.get('title','来源'),'url':p.get('url',''),'source_type':p.get('source_type','web'),
            'availability':link.get('availability') or p.get('availability','discovered'),
            'snippet':link.get('snippet','')[:1000], 'asset_id':aid,'version_id':link.get('version_id'),
            'adopted':link.get('adopted',False),'excluded':link.get('excluded',False),'read':link.get('read',False),
            'used_in_report':link.get('used_in_report',False),'retrieved_at':p.get('retrieved_at'),
            'error':link.get('error',p.get('error')),'provider':link.get('provider'),'snapshot_key':link.get('snapshot_key'),
            'conversation_id':source['job_payload'].get('conversation_id'),'version_status':p.get('version_status','unconfirmed'),
            'original_format':({'text/html':'html','application/xhtml+xml':'html','application/pdf':'pdf'}.get(link.get('mime'),'txt') if link.get('original_object_key') else None),
            'bibliography':{k:str(p[k]) for k in ('author','publication_date','doi','journal') if p.get(k)}})
    return result
