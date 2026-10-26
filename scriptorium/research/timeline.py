"""Persistent user-visible activity; never stores private model reasoning."""
import hashlib
import sqlalchemy as sa
from pydantic import BaseModel, Field
from . import schema as db
from .events import emit
from .service import ResearchError, row


class TimelineBlock(BaseModel):
    id: str
    job_id: str
    project_id: str
    conversation_id: str
    block_key: str
    kind: str
    state: str
    generation: int
    revision: int
    payload: dict = Field(default_factory=dict)
    created_at: float
    updated_at: float


class ResearchTask(BaseModel):
    job_id: str
    state: str
    reason: str | None = None
    generation: int
    blocks: list[TimelineBlock]


class TimelineSnapshot(BaseModel):
    blocks: list[TimelineBlock]
    cursor: int


def put(c, s, job, key, kind, state, payload, *, delta=None):
    s.locked_job(c, job)
    old = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == key)
    turn = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == '__turn')
    generation = job.get('_timeline_generation') or (turn or {}).get('generation', 1)
    now = db.now()
    value = {'id': hashlib.sha256((job['id']+':'+key).encode()).hexdigest(), 'job_id': job['id'],
        'project_id': job['project_id'], 'conversation_id': job['payload']['conversation_id'],
        'block_key': key, 'kind': kind, 'state': state, 'generation': generation,
        'revision': (old or {}).get('revision', 0)+1, 'payload': payload,
        'created_at': (old or {}).get('created_at', now), 'updated_at': now}
    if old:
        c.execute(db.timeline_blocks.update().where(db.timeline_blocks.c.id == old['id']).values(**value))
    else:
        c.execute(db.timeline_blocks.insert().values(**value))
    public = {**value, 'payload': {k:v for k,v in payload.items() if not k.startswith('_')}}
    if delta is not None:public['payload']={k:v for k,v in public['payload'].items() if k!='text'}
    emit(c, job['project_id'], value['conversation_id'], 'timeline.block',
         {'job_id': job['id'], 'turn_id': job['id'], 'generation': generation, 'block': public,
          **({'delta': delta} if delta is not None else {})})
    return value


def start(s, job):
    if not job['payload'].get('conversation_id'):
        return
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload']['principal'], True)
        s.locked_job(c, job)
        old = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == '__turn')
        lease = hashlib.sha256(job['lease_token'].encode()).hexdigest()
        generation = (old or {}).get('generation', 0) + (not old or old['payload'].get('_lease') != lease)
        job['_timeline_generation'] = generation
        put(c, s, job, '__turn', 'turn', 'running', {'_lease': lease, 'title': '研究正在进行', 'phase': 'planning'})
        if not old:
            research = job['payload'].get('tool') in {'auto','research','theory'}
            put(c, s, job, 'opening', 'text', 'completed', {'text':
                '我会先检查已有材料，再寻找相关来源，按实际取得的原文形成解释并说明局限。' if research else ''})
            if research:
                put(c, s, job, 'plan', 'plan', 'running', {'title':'研究计划',
                    'items':['寻找与整理材料','阅读相关原文','形成解释并检验','整理回答和报告']})


def activity(s, job, key, title, state='running', **payload):
    if not job.get('_timeline_generation'):
        return
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload']['principal'], True)
        return put(c, s, job, key, 'activity', state, {'title':title, **payload})


def append(s, job, key, delta):
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload']['principal'], True)
        s.locked_job(c, job)
        old = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == key)
        text = (old or {}).get('payload', {}).get('text', '')
        offset = len(text)
        put(c, s, job, key, 'answer', 'streaming', {'text':text+delta, 'offset':offset+len(delta)},
            delta={'offset':offset,'text':delta})


def finish(c, s, job, result):
    turn = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == '__turn')
    if not turn:
        return
    waiting = result.get('state') == 'awaiting_input'
    partial = result.get('state') in {'stopped','partial_completed'}
    for block in c.execute(sa.select(db.timeline_blocks).where(db.timeline_blocks.c.job_id==job['id'],db.timeline_blocks.c.state.in_(['running','streaming']))).mappings():
        if block['kind'] not in {'turn','answer'}:
            put(c,s,job,block['block_key'],block['kind'],'waiting' if waiting else 'interrupted' if partial else 'completed',block['payload'])
    if not waiting:
        answer = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id == job['id'], db.timeline_blocks.c.block_key == 'answer')
        text = result.get('text') or (answer or {}).get('payload', {}).get('text')
        if result.get('record_id'):
            record = row(c, db.records, db.records.c.id == result['record_id'])
            text = (record or {}).get('payload', {}).get('text') or text
        if text:
            put(c,s,job,'answer','answer','completed',{'text':text,'artifact_ids':result.get('artifact_ids') or ([result['record_id']] if result.get('record_id') else [])})
    put(c,s,job,'__turn','turn','waiting' if waiting else 'partial' if partial else 'completed',{
        **turn['payload'], 'title':'等待你的决定' if waiting else '研究已结束，阶段成果保留' if partial else '本轮已完成', 'result':result})
    plan = row(c, db.timeline_blocks, db.timeline_blocks.c.job_id==job['id'], db.timeline_blocks.c.block_key=='plan')
    if plan:
        put(c,s,job,'plan','plan','waiting' if waiting else 'interrupted' if partial else 'completed',plan['payload'])


def snapshot(c, s, pid, cid, principal):
    s.access(c, pid, principal)
    values = [dict(x) for x in c.execute(sa.select(db.timeline_blocks).where(
        db.timeline_blocks.c.project_id==pid, db.timeline_blocks.c.conversation_id==cid).order_by(
        db.timeline_blocks.c.created_at,db.timeline_blocks.c.id)).mappings()]
    for value in values:
        value['payload']={k:v for k,v in value['payload'].items() if not k.startswith('_')}
    return values


def task(c,s,pid,jid,principal):
    s.access(c,pid,principal)
    job=row(c,db.jobs,db.jobs.c.id==jid,db.jobs.c.project_id==pid)
    if not job:raise ResearchError('JOB_NOT_FOUND',404)
    values=[x for x in snapshot(c,s,pid,job['payload'].get('conversation_id'),principal) if x['job_id']==jid]
    turn=next((x for x in values if x['kind']=='turn'),None)
    state=job['state'] if job['state'] in {'failed','cancelled','cancel_requested'} else (turn or {}).get('state',job['state'])
    return {'job_id':jid,'state':state,'reason':job.get('error'),'generation':(turn or {}).get('generation',0),'blocks':values}


def close_waiting(c, s, pid, job_id):
    """An authorized decision closes a non-running turn without impersonating a lease."""
    job=row(c,db.jobs,db.jobs.c.id==job_id,db.jobs.c.project_id==pid)
    if not job or job['state'] not in {'succeeded','failed'}:raise ResearchError('RESEARCH_NOT_WAITING',409)
    result={**(job.get('result') or {}),'state':'partial_completed'}
    c.execute(db.jobs.update().where(db.jobs.c.id==job_id).values(state='succeeded',error=None,result=result))
    for block in c.execute(sa.select(db.timeline_blocks).where(db.timeline_blocks.c.job_id==job_id).with_for_update()).mappings():
        value={**block,'revision':block['revision']+1,'updated_at':db.now()}
        if block['kind']=='turn':value.update(state='partial',payload={'title':'研究已结束，阶段成果保留','result':result})
        elif block['state'] in {'waiting','running','streaming'}:value['state']='interrupted'
        else:continue
        c.execute(db.timeline_blocks.update().where(db.timeline_blocks.c.id==block['id']).values(**value))
        emit(c,pid,block['conversation_id'],'timeline.block',{'job_id':job_id,'generation':block['generation'],'block':{**value,'payload':{k:v for k,v in value['payload'].items() if not k.startswith('_')}}})
    intake=row(c,db.intakes,db.intakes.c.job_id==job_id)
    if intake:c.execute(db.intakes.update().where(db.intakes.c.job_id==job_id).values(state='completed',payload={**intake['payload'],'decision':None}))
