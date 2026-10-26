"""Provider calls are committed independently from research artifact validation."""
import json
import time
import os
import sqlalchemy as sa
from types import SimpleNamespace
from . import schema as db
from .service import ResearchError, rows


def usage_totals(c, run_id):
    calls = rows(c, db.model_calls, db.model_calls.c.run_id == run_id)
    known = sum((x['usage'] or {}).get('total_tokens', 0) for x in calls)
    held = sum(x['reserved_tokens'] for x in calls if x['state'] in {'reserved', 'unknown'})
    return {'used_tokens': known, 'reserved_tokens': held,
            'unknown_calls': sum(x['state'] == 'unknown' for x in calls), 'calls': len(calls)}


def reserve(s, job, provider, messages, output_tokens, run_id=None):
    identifier = db.uid()
    estimate = len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + output_tokens
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload'].get('principal', s.settings.principal), True)
        if not job.get('_synchronous'):
            s.locked_job(c, job)
        c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == job['project_id']).with_for_update())
        from .governance import check_egress, audit
        source_assets = check_egress(s, c, job, provider, estimate)
        validation_limit = os.getenv('SCRIPTORIUM_VALIDATION_TOKEN_LIMIT')
        if validation_limit:
            # A dedicated validation schema is used for the entire paid evaluation batch.
            c.execute(sa.text('LOCK TABLE r_model_calls IN SHARE ROW EXCLUSIVE MODE'))
            all_calls = rows(c, db.model_calls)
            committed = sum((x['usage'] or {}).get('total_tokens', 0) for x in all_calls)
            uncertain = sum(x['reserved_tokens'] for x in all_calls if x['state'] in {'reserved', 'unknown'})
            if committed + uncertain + estimate > int(validation_limit):
                raise ResearchError('VALIDATION_BUDGET_REQUIRED', 409)
        if run_id:
            run = c.execute(sa.select(db.research_runs).where(
                db.research_runs.c.id == run_id).with_for_update()).mappings().first()
            totals = usage_totals(c, run_id)
            if not run or totals['used_tokens'] + totals['reserved_tokens'] + estimate > run['settings']['token_budget'] - (run['settings'].get('writer_reservation',0) if job['kind']=='method' else 0):
                raise ResearchError('CALL_BUDGET_REQUIRED', 409)
        if job['payload'].get('tool') == 'auto' and not run_id:
            c.execute(sa.select(db.projects.c.id).where(db.projects.c.id == job['project_id']).with_for_update())
            existing = rows(c, db.model_calls, db.model_calls.c.job_id == job['id'])
            spent = sum((v['usage'] or {}).get('total_tokens', 0) +
                (v['reserved_tokens'] if v['state'] in {'reserved', 'unknown'} else 0) for v in existing)
            if spent + estimate > job['payload'].get('_auto_total_budget', job['payload'].get('token_budget', 40000)):
                raise ResearchError('CALL_BUDGET_REQUIRED', 409)
        c.execute(db.model_calls.insert().values(id=identifier, project_id=job['project_id'], job_id=job['id'],
            run_id=run_id, model=provider.model, state='reserved', reserved_tokens=estimate,
            source_assets=source_assets, created_at=db.now()))
        audit(c, job['project_id'], job['payload'].get('principal', s.settings.principal), 'model.reserved', identifier, {'model': provider.model, 'reserved_tokens': estimate})
    return identifier


def complete(s, job, provider, messages, output_tokens, response_format=None, run_id=None, on_text=None):
    identifier = reserve(s, job, provider, messages, output_tokens, run_id)
    try:
        options = {'response_format': response_format} if response_format else {}
        if on_text:
            options.update(stream=True, stream_options={'include_usage': True})
        response = provider.client.chat.completions.create(model=provider.model, messages=messages,
            temperature=provider.temperature, max_tokens=output_tokens, **options)
        if on_text:
            stream = response
            full, pending, last, usage = '', '', time.monotonic(), None
            finish_reason = None
            try:
                for chunk in stream:
                    usage = getattr(chunk, 'usage', None) or usage
                    if chunk.choices:finish_reason=getattr(chunk.choices[0],'finish_reason',None) or finish_reason
                    delta = (getattr(chunk.choices[0].delta, 'content', '') or '') if chunk.choices else ''
                    full += delta
                    pending += delta
                    if pending and (len(pending) >= 80 or time.monotonic() - last >= .15):
                        on_text(pending)
                        pending, last = '', time.monotonic()
                if pending:
                    on_text(pending)
                response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=full),finish_reason=finish_reason)], usage=usage)
            finally:
                stream.close()
    except Exception as exc:
        # A lost response can still have incurred provider usage. Do not count it as zero.
        with s.engine.begin() as c:
            c.execute(db.model_calls.update().where(db.model_calls.c.id == identifier).values(
                state='unknown', error=type(exc).__name__[:128], finished_at=db.now()))
            reconcile(c, run_id)
        raise ResearchError('MODEL_REQUEST_FAILED_USAGE_UNKNOWN', 502) from None
    usage = getattr(response, 'usage', None)
    usage = usage.model_dump() if usage is not None else None
    with s.engine.begin() as c:
        c.execute(db.model_calls.update().where(db.model_calls.c.id == identifier).values(
            state='returned' if usage else 'unknown', usage=usage, finished_at=db.now()))
        reconcile(c, run_id)
    return response, usage, identifier


def reconcile(c, run_id):
    if run_id:
        totals = usage_totals(c, run_id)
        c.execute(db.research_runs.update().where(db.research_runs.c.id == run_id).values(
            used_tokens=totals['used_tokens'], reserved_tokens=totals['reserved_tokens']))


def accounted_provider(service, job, provider):
    """Keep inherited prompt algorithms while recording every transport request."""
    if not job or not hasattr(provider, '_call'):
        return provider
    def call(system, user_content):
        response, _, _ = complete(service, job, provider, [
            {'role': 'system', 'content': system}, {'role': 'user', 'content': user_content}],
            4000, {'type': 'json_object'}, job['payload'].get('run_id'))
        if getattr(response.choices[0], 'finish_reason', None) == 'length':
            raise ResearchError('MODEL_OUTPUT_TRUNCATED', 422)
        try:
            return json.loads(response.choices[0].message.content)
        except (TypeError, ValueError):
            raise ResearchError('MODEL_STRUCTURE_INVALID', 422) from None
    provider._call = call
    return provider


def synchronous_job(s, pid, principal, kind, asset_ids=None):
    return {'id': 'sync-' + db.uid(), 'project_id': pid, '_synchronous': True,
            'payload': {'principal': principal, 'kind': kind, 'asset_ids': asset_ids or []}}


def accounted_ollama(s, job, provider):
    raw = provider.transport
    def transport(url, **kwargs):
        payload = kwargs.get('json', {})
        active = SimpleNamespace(model=payload.get('model', provider.model), base_url=provider.base_url)
        identifier = reserve(s, job, active, payload.get('messages') or [{'role': 'user', 'content': payload.get('prompt', '')}], 4000)
        try:
            response = raw(url, **kwargs); response.raise_for_status(); data = response.json()
            known = data.get('prompt_eval_count') is not None or data.get('eval_count') is not None
            usage = {'total_tokens': data.get('prompt_eval_count', 0) + data.get('eval_count', 0)} if known else None
            with s.engine.begin() as c:
                c.execute(db.model_calls.update().where(db.model_calls.c.id == identifier).values(
                    state='returned' if known else 'unknown', usage=usage, finished_at=db.now()))
            return response
        except Exception as exc:
            with s.engine.begin() as c:
                c.execute(db.model_calls.update().where(db.model_calls.c.id == identifier).values(
                    state='unknown', error=type(exc).__name__[:128], finished_at=db.now()))
            raise
    from contextlib import contextmanager
    raw_stream = provider.stream_transport
    @contextmanager
    def stream_transport(method, url, **kwargs):
        payload = kwargs.get('json', {})
        active = SimpleNamespace(model=payload.get('model', provider.model), base_url=provider.base_url)
        identifier = reserve(s, job, active, payload.get('messages', []), 4000)
        usage = None
        class AccountedResponse:
            def __init__(self, response):
                self.response = response
            def raise_for_status(self):
                return self.response.raise_for_status()
            def iter_lines(self):
                nonlocal usage
                for line in self.response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if data.get('done') and ('prompt_eval_count' in data or 'eval_count' in data):
                            usage = {'total_tokens': data.get('prompt_eval_count', 0) + data.get('eval_count', 0)}
                    yield line
        try:
            with raw_stream(method, url, **kwargs) as response:
                yield AccountedResponse(response)
        finally:
            with s.engine.begin() as c:
                c.execute(db.model_calls.update().where(db.model_calls.c.id == identifier).values(
                    state='returned' if usage is not None else 'unknown', usage=usage, finished_at=db.now()))
    provider.transport = transport
    provider.stream_transport = stream_transport
    return provider
