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


def complete(s, job, provider, messages, output_tokens, response_format=None, run_id=None, on_text=None):
    estimate = len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + output_tokens
    identifier = db.uid()
    with s.engine.begin() as c:
        s.access(c, job['project_id'], job['payload'].get('principal', s.settings.principal), True)
        s.locked_job(c, job)
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
            if not run or totals['used_tokens'] + totals['reserved_tokens'] + estimate > run['settings']['token_budget']:
                raise ResearchError('CALL_BUDGET_REQUIRED', 409)
        c.execute(db.model_calls.insert().values(id=identifier, project_id=job['project_id'], job_id=job['id'],
            run_id=run_id, model=provider.model, state='reserved', reserved_tokens=estimate,
            source_assets=job['payload'].get('asset_ids', []), created_at=db.now()))
    try:
        options = {'response_format': response_format} if response_format else {}
        if on_text:
            options.update(stream=True, stream_options={'include_usage': True})
        response = provider.client.chat.completions.create(model=provider.model, messages=messages,
            temperature=provider.temperature, max_tokens=output_tokens, **options)
        if on_text:
            stream = response
            full, pending, last, usage = '', '', time.monotonic(), None
            try:
                for chunk in stream:
                    usage = getattr(chunk, 'usage', None) or usage
                    delta = (getattr(chunk.choices[0].delta, 'content', '') or '') if chunk.choices else ''
                    full += delta
                    pending += delta
                    if pending and (len(pending) >= 80 or time.monotonic() - last >= .15):
                        on_text(pending)
                        pending, last = '', time.monotonic()
                if pending:
                    on_text(pending)
                response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=full))], usage=usage)
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
