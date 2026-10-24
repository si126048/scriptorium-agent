"""Persistent conversations, one-command research submissions, and checkpointed runs."""
from __future__ import annotations


import sqlalchemy as sa

from . import schema as db
from .service import ResearchError, row, rows
from .texts import quote_hash


def conversation(s, c, pid, cid):
    value = row(c, db.conversations, db.conversations.c.id == cid, db.conversations.c.project_id == pid)
    if not value:
        raise ResearchError('CONVERSATION_NOT_FOUND', 404)
    return value


def create_conversation(s, pid, principal, title='新研究'):
    result = {'id': db.uid(), 'project_id': pid, 'title': title, 'archived': False, 'revision': 1,
                  'workspace': {}, 'created_at': db.now()}
    with s.engine.begin() as c:
        s.access(c, pid, principal, True)
        c.execute(db.conversations.insert().values(**result))
    return result


def add_message(c, pid, cid, role, content, artifact_ids=None, metadata=None, identifier=None):
    item = {'id': identifier or db.uid(), 'project_id': pid, 'conversation_id': cid, 'role': role,
        'content': content, 'artifact_ids': artifact_ids or [], 'metadata': metadata or {}, 'created_at': db.now()}
    c.execute(db.messages.insert().values(**item))
    from .events import emit
    emit(c, pid, cid, 'message.created', {'message': item})
    return item


def submit(s, pid, principal, cid, body, idem):
    from .scopes import freeze
    snapshot = freeze(s, pid, principal, body)
    with s.engine.begin() as c:
        s.access(c, pid, principal, True)
        conv = conversation(s, c, pid, cid)
        if conv['archived']:
            raise ResearchError('CONVERSATION_ARCHIVED', 409)
        asset_ids = body.get('asset_ids', [])
        segment_ids = body.get('segment_ids', [])
        if not snapshot and body['tool'] in {'research', 'theory', 'subject'}:
            raise ResearchError('SELECT_RESEARCH_MATERIALS', 422)
        for aid in asset_ids:
            s.asset(c, pid, aid)
        for sid in segment_ids:
            item = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == pid)
            if not item:
                raise ResearchError('SEGMENT_NOT_FOUND', 404)
            s.asset(c, pid, item['asset_id'])
        request = {**body, 'scope_snapshot': snapshot, 'asset_ids': list(dict.fromkeys(w['asset_id'] for w in snapshot)),
                   'conversation_id': cid, 'principal': principal}
        job = s.enqueue(c, pid, 'workspace', request, idem)
        message_id = quote_hash(f'{pid}:{cid}:{job["id"]}:user')
        if not row(c, db.messages, db.messages.c.id == message_id):
            add_message(c, pid, cid, 'user', body['text'], metadata={'job_id': job['id'],
                'asset_ids': request['asset_ids'], 'tool': body['tool'], 'persona_id': body.get('persona_id'),
                'participant_id': body.get('participant_id')}, identifier=message_id)
        return job


def source_segments(s, pid, principal, body):
    selected = {}
    if 'scope_snapshot' in body:
        result = []
        with s.engine.connect() as c:
            s.access(c, pid, principal)
            for window in body['scope_snapshot']:
                segment = row(c, db.segments, db.segments.c.id == window['segment_id'],
                              db.segments.c.project_id == pid, db.segments.c.version_id == window['version_id'])
                if not segment:
                    raise ResearchError('SOURCE_NO_LONGER_AVAILABLE')
                s.asset(c, pid, segment['asset_id'])
                result.append({**segment, 'text': segment['text'][window['start']:window['end']],
                               'source_offset': window['start']})
        return result
    with s.engine.connect() as c:
        for sid in body.get('segment_ids', []):
            item = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == pid)
            if not item:
                raise ResearchError('SOURCE_NO_LONGER_AVAILABLE')
            s.asset(c, pid, item['asset_id'])
            selected[sid] = item
    for aid in body.get('asset_ids', []):
        for item in s.get_segments(pid, principal, aid)['segments']:
            selected[item['id']] = item
    return list(selected.values())


def windows(segments, max_chars=4500):
    # No content loss: every code point is assigned to a window in the immutable source.
    result = []
    for segment in segments:
        for start in range(0, len(segment['text']), max_chars):
            offset = segment.get('source_offset', 0)
            result.append({'segment_id': segment['id'], 'start': offset + start,
                           'end': offset + min(len(segment['text']), start + max_chars),
                           'version_id': segment['version_id'], 'asset_id': segment['asset_id']})
    return result


def evidence_batches(scope, maximum=9000):
    """Preserve complete windows and compare different sources within each bounded call."""
    groups, batch, size = [], [], 0
    for window in scope:
        length = window['end'] - window['start']
        if batch and (size + length > maximum or window['segment_id'] in {w['segment_id'] for w in batch}):
            groups.append(batch)
            batch, size = [], 0
        batch.append(window)
        size += length
    if batch:
        groups.append(batch)
    return groups


def run_research(s, job):
    from .worker import run_one
    pid, payload = job['project_id'], job['payload']
    principal, cid = payload['principal'], payload['conversation_id']
    with s.engine.connect() as c:
        existing = next((r for r in rows(c, db.research_runs, db.research_runs.c.conversation_id == cid)
                         if r['settings'].get('origin_job_id') == job['id']), None)
    rid = payload.get('resume_run_id') or (existing or {}).get('id')
    if not rid:
        segments = source_segments(s, pid, principal, payload)
        scope = windows(segments)
        if not scope:
            raise ResearchError('NO_RESEARCH_TEXT')
        rid = db.uid()
        methods = payload.get('methods') or ['situating.v1', 'immanent_critique.v1', 'parallax.v1']
        with s.engine.begin() as c:
            s.access(c, pid, principal, True)
            s.locked_job(c, job)
            settings = {'origin_job_id': job['id'], 'token_budget': payload.get('token_budget', 40000),
                'max_nodes': 6, 'max_rounds': 2, 'nodes': [], 'provider_mode': payload.get('provider_mode', 'live')}
            c.execute(db.research_runs.insert().values(id=rid, project_id=pid, conversation_id=cid,
                question=payload['text'], state='running', scope=scope, settings=settings,
                used_tokens=0, reserved_tokens=0, created_at=db.now()))
            phases = []
            if 'situating.v1' in methods:
                phases.extend(('situating.v1', [window]) for window in scope)
            for method in [m for m in methods if m != 'situating.v1'] + ['review.v1']:
                phases.extend((method, batch) for batch in evidence_batches(scope))
            for i, (method, batch) in enumerate(phases):
                    c.execute(db.research_steps.insert().values(id=db.uid(), run_id=rid,
                        step_key=f'root/{i:05d}/0', state='queued',
                        payload={'window': batch[0], 'windows': batch, 'method_id': method, 'round': 0}, created_at=db.now()))
    while True:
        with s.engine.begin() as c:
            s.access(c, pid, principal, True)
            s.locked_job(c, job)
            run = row(c, db.research_runs, db.research_runs.c.id == rid, db.research_runs.c.project_id == pid)
            if run['state'] == 'cancelled':
                raise ResearchError('RESEARCH_CANCELLED')
            s.access(c, pid, principal)
            step = c.execute(sa.select(db.research_steps).where(db.research_steps.c.run_id == rid,
                db.research_steps.c.state != 'succeeded').order_by(db.research_steps.c.step_key).limit(1)).mappings().first()
            if not step:
                artifacts = [r['result']['record_id'] for r in rows(c, db.research_steps,
                    db.research_steps.c.run_id == rid) if r.get('result') and r['result'].get('record_id')]
                reports = [row(c, db.records, db.records.c.id == aid, db.records.c.project_id == pid) for aid in artifacts]
                reports = [r for r in reports if r]
                evidence = list(dict.fromkeys(e for r in reports for e in r['payload'].get('evidence_ids', [])))
                from .reports import assemble
                composed = assemble(run['question'], reports, rows(c, db.research_steps,
                    db.research_steps.c.run_id == rid), run['settings']['provider_mode'])
                report = s.put_record(c, pid, 'manuscript', {'title': '研究报告 · ' + run['question'][:40],
                    **composed,
                    'evidence_ids': evidence, 'source_record_ids': artifacts,
                    'asset_ids': list({w['asset_id'] for w in run['scope']}), 'provider_mode': run['settings']['provider_mode'],
                    'coverage': [{**w, 'state': 'processed'} for w in run['scope']],
                    'open_questions': [q for r in reports for q in r['payload'].get('open_questions', [])],
                    'status': 'candidate', 'run_id': rid})
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='completed_with_open_questions'))
                add_message(c, pid, cid, 'assistant', '研究已完成。报告保留证据、材料覆盖和未决问题。', [report['id']],
                    {'run_id': rid, 'provider_mode': run['settings']['provider_mode']})
                s.finish(c, job, {'run_id': rid, 'record_id': report['id']})
                return
            p = step['payload']
            window = p['window']
            batch = p.get('windows') or [window]
            segment = row(c, db.segments, db.segments.c.id == window['segment_id'])
            if not segment:
                raise ResearchError('SOURCE_NO_LONGER_AVAILABLE')
            s.asset(c, pid, segment['asset_id'])
            estimate = 8000 + sum((w['end'] - w['start']) * 4 for w in batch)
            child_id = (step['result'] or {}).get('job_id')
            if not child_id:
                if run['used_tokens'] + estimate > run['settings']['token_budget']:
                    decision = {'id': db.uid(), 'run_id': rid, 'project_id': pid, 'kind': 'budget', 'state': 'pending',
                        'payload': {'question': '继续处理需要追加研究预算。', 'suggested_tokens': estimate,
                                 'completed_steps': len(rows(c, db.research_steps, db.research_steps.c.run_id == rid,
                                     db.research_steps.c.state == 'succeeded'))}, 'answer': None, 'created_at': db.now()}
                    c.execute(db.decisions.insert().values(**decision))
                    c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='awaiting_input'))
                    add_message(c, pid, cid, 'assistant', '已保留目前结果。继续研究前，请决定是否追加预算。',
                        metadata={'decision_id': decision['id'], 'run_id': rid})
                    s.finish(c, job, {'run_id': rid, 'state': 'awaiting_input'})
                    return
                prior = [r['result']['record_id'] for r in rows(c, db.research_steps, db.research_steps.c.run_id == rid,
                    db.research_steps.c.state == 'succeeded') if r.get('result') and r['result'].get('record_id')]
                child = s.enqueue(c, pid, 'method', {'method_id': p['method_id'], 'question': p.get('question', run['question']),
                    'segment_ids': list(dict.fromkeys(w['segment_id'] for w in batch)), 'windows': batch, 'prior_artifact_ids': prior,
                    'provider_mode': run['settings']['provider_mode'], 'max_input_chars': 12000,
                    'max_output_tokens': 3000, 'run_id': rid, 'principal': principal,
                    'asset_ids': list({w['asset_id'] for w in run['scope']}), 'conversation_id': cid,
                    'premise': p.get('premise')}, f'{rid}-{step["id"]}')
                child_id = child['id']
                c.execute(db.research_steps.update().where(db.research_steps.c.id == step['id']).values(
                    state='running', result={'job_id': child_id, 'reservation': estimate}))
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(reserved_tokens=estimate))
                s.event(c, job['id'], {'state': 'running', 'phase': p['method_id'], 'run_id': rid, 'window': window})
        run_one(s, child_id)
        with s.engine.begin() as c:
            s.locked_job(c, job)
            child = row(c, db.jobs, db.jobs.c.id == child_id)
            if child['state'] == 'awaiting_input':
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='awaiting_input'))
                add_message(c, pid, cid, 'assistant', '有引文需要核验。已保存研究检查点，请在文档区处理后继续。',
                            metadata={'run_id': rid, 'citation_job_id': child_id})
                s.finish(c, job, {'run_id': rid, 'state': 'awaiting_input'})
                return
            if child.get('error') == 'CALL_BUDGET_REQUIRED':
                did = db.uid()
                c.execute(db.decisions.insert().values(id=did, run_id=rid, project_id=pid, kind='budget',
                    state='pending', payload={'question': '完整提示与修正调用需要追加预算。',
                    'suggested_tokens': max(40000, estimate)}, answer=None, created_at=db.now()))
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='awaiting_input'))
                add_message(c, pid, cid, 'assistant', '已保存进度，需要确认额外调用预算。', metadata={'decision_id': did})
                s.finish(c, job, {'run_id': rid, 'state': 'awaiting_input'})
                return
            if child['state'] in {'queued', 'running'}:
                # Another worker owns the child. Release this coordinator rather than busy wait.
                s.defer_job(c, job)
                return
            if child['state'] != 'succeeded':
                raise ResearchError(child.get('error') or 'RESEARCH_STEP_FAILED')
            current_step = row(c, db.research_steps, db.research_steps.c.id == step['id'])
            if current_step['state'] == 'succeeded':
                continue
            artifact = row(c, db.records, db.records.c.id == child['result']['record_id'])
            usage = artifact['payload'].get('usage') or {}
            cost = 0 if run['settings']['provider_mode'] == 'demo' else usage.get('total_tokens') or estimate
            c.execute(db.research_steps.update().where(db.research_steps.c.id == step['id']).values(
                state='succeeded', result={**child['result'], 'job_id': child_id, 'charged_tokens': cost}))
            from .calls import usage_totals
            totals = usage_totals(c, rid)
            c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(
                used_tokens=totals['used_tokens'], reserved_tokens=totals['reserved_tokens']))
            if (p['method_id'] == 'review.v1' and p['round'] < run['settings']['max_rounds']
                    and artifact['payload'].get('review_action') == 'revise'
                    and any(f.get('evidence_ids') for f in artifact['payload'].get('findings', []))):
                key = step['step_key'] + f'/revision-{p["round"] + 1}'
                for phase, method in [('0', 'revision.v1'), ('1', 'review.v1')]:
                    c.execute(db.research_steps.insert().values(id=db.uid(), run_id=rid, step_key=key + '/' + phase,
                        state='queued', payload={**p, 'method_id': method, 'round': p['round'] + 1}, created_at=db.now()))
            add_message(c, pid, cid, 'assistant', f'{artifact["payload"].get("title", "分析")}已保存。',
                        [artifact['id']], {'run_id': rid, 'provider_mode': run['settings']['provider_mode']})
            for proposal in artifact['payload'].get('proposals', []) if p['method_id'] == 'review.v1' else []:
                key = quote_hash(proposal['question'].strip() + '\n' + proposal['premise'].strip())
                known = {x['payload'].get('proposal_key') for x in rows(c, db.decisions, db.decisions.c.run_id == rid)}
                if key in known or len(run['settings']['nodes']) >= run['settings']['max_nodes'] - 1:
                    continue
                did = db.uid()
                c.execute(db.decisions.insert().values(id=did, run_id=rid, project_id=pid,
                    kind=proposal['kind'], state='pending', payload={**proposal, 'proposal_key': key},
                    answer=None, created_at=db.now()))
                c.execute(db.research_runs.update().where(db.research_runs.c.id == rid).values(state='awaiting_input'))
                add_message(c, pid, cid, 'assistant', '审查提出了一个需要你决定的研究方向。',
                            metadata={'decision_id': did, 'run_id': rid})
                s.finish(c, job, {'run_id': rid, 'state': 'awaiting_input'})
                return


def execute_workspace(s, job):
    body, pid = job['payload'], job['project_id']
    if body['tool'] == 'research' or body.get('resume_run_id'):
        return run_research(s, job)
    if body['tool'] == 'ask':
        from .ask import execute as execute_ask
        return execute_ask(s, job)
    from .capabilities import execute_capability
    result = execute_capability(s, pid, body['principal'], body, job=job)
    with s.engine.begin() as c:
        s.access(c, pid, body['principal'], True)
        s.locked_job(c, job)
        for aid in body.get('asset_ids', []):
            s.asset(c, pid, aid)
        if body['tool'] == 'persona':
            persona = row(c, db.entities, db.entities.c.project_id == pid,
                db.entities.c.kind == 'persona', db.entities.c.external_id == body.get('persona_id'))
            if not persona:
                raise ResearchError('PERSONA_NO_LONGER_AVAILABLE')
        add_message(c, pid, body['conversation_id'], 'assistant', result.get('text', '已完成'),
            result.get('artifact_ids', []), {**result.get('metadata', {}), 'job_id': job['id']})
        s.finish(c, job, result)
