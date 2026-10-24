"""Interrupt an isolated demo Worker, then verify checkpointed recovery.

Requires HERMENEUT_DATABASE_URL pointing at a disposable PostgreSQL database. Each
run creates a unique schema and object directory; it never claims other projects' jobs.
This tests process failure, not an operating-system reboot or real model quality.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from hermeneut.research import schema as db
from hermeneut.research.config import ResearchSettings
from hermeneut.research.service import ResearchService, row, rows
from hermeneut.research.worker import run_one
from hermeneut.research.workspace import create_conversation, submit


def stop(process):
    if process.poll() is None:
        process.kill()  # Only a child created by this drill; simulates an abrupt failure.
    process.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('output/restart-drill'))
    parser.add_argument('--chars', type=int, default=36000)
    parser.add_argument('--lease-seconds', type=int, default=6)
    parser.add_argument('--timeout-seconds', type=int, default=120)
    args = parser.parse_args()
    if args.chars < 9000 or args.lease_seconds < 3 or args.timeout_seconds < 10:
        parser.error('Use at least 9000 chars, a 3-second lease and a 10-second timeout')
    cfg = ResearchSettings.from_env()
    base = db.engine_for(cfg.database_url)
    schema = 'drill_' + db.uid()
    out = args.out.resolve() / schema
    out.mkdir(parents=True, exist_ok=False)
    with base.begin() as c:
        c.execute(sa.text(f'CREATE SCHEMA {schema}'))
    url = sa.engine.make_url(cfg.database_url).update_query_dict({'options': f'-csearch_path={schema}'})
    env = {**os.environ, 'HERMENEUT_DATABASE_URL': url.render_as_string(hide_password=False),
           'HERMENEUT_OBJECT_ROOT': str(out / 'objects'), 'HERMENEUT_OBJECT_BACKEND': 'filesystem',
           'HERMENEUT_LEASE_SECONDS': str(args.lease_seconds), 'HERMENEUT_RESEARCH_OWNER': 'drill-operator'}
    from dataclasses import replace
    settings = replace(cfg, database_url=env['HERMENEUT_DATABASE_URL'], object_root=out / 'objects',
                       object_backend='filesystem', lease_seconds=args.lease_seconds, principal='drill-operator')
    engine = db.engine_for(settings.database_url)
    db.metadata.create_all(engine)
    service = ResearchService(engine, settings)
    timeline, children, checks = [], [], {}
    ok, error = False, None

    def note(step, **detail):
        item = {'at': datetime.now(UTC).isoformat(), 'step': step, **detail}
        timeline.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def spawn():
        log = (out / f'worker-{len(children)+1}.log').open('wb')
        try:
            child = subprocess.Popen([sys.executable, '-m', 'hermeneut.research.cli', 'worker'],
                                     env=env, stdout=log, stderr=subprocess.STDOUT)
        finally:
            log.close()
        children.append(child)
        return child

    try:
        pid = service.create_project(settings.principal, '重启演练')['id']
        phrase = '自由需要条件，制度要求说明理由。'
        text = (phrase * ((args.chars + len(phrase)-1)//len(phrase)))[:args.chars]
        imported = service.import_material(pid, settings.principal, text.encode(), 'drill.md', 'material')
        run_one(service, imported['id'])
        with engine.connect() as c:
            assert row(c, db.jobs, db.jobs.c.id == imported['id'])['state'] == 'succeeded'
        cid = create_conversation(service, pid, settings.principal)['id']
        job = submit(service, pid, settings.principal, cid, {'text': '长文中断恢复', 'tool': 'research',
            'asset_ids': [imported['payload']['asset_id']], 'segment_ids': [], 'provider_mode': 'demo',
            'methods': ['situating.v1'], 'token_budget': 400000}, 'research')
        jid = job['id']
        note('submitted', schema=schema, job_id=jid, codepoints=len(text), lease_seconds=args.lease_seconds)
        first = spawn()
        deadline, checkpoint = time.monotonic() + args.timeout_seconds, {}
        while time.monotonic() < deadline:
            with engine.connect() as c:
                current = row(c, db.jobs, db.jobs.c.id == jid)
                runs = rows(c, db.research_runs, db.research_runs.c.project_id == pid)
                steps = rows(c, db.research_steps, db.research_steps.c.run_id == runs[0]['id']) if runs else []
            checkpoint = {s['id']: s['result'] for s in steps if s['state'] == 'succeeded'}
            if checkpoint and current['state'] == 'running':
                stop(first)
                break
            if first.poll() is not None or current['state'] in {'succeeded', 'failed', 'cancelled'}:
                raise RuntimeError('No in-flight checkpoint interruption was observed')
            time.sleep(0.05)
        else:
            raise TimeoutError('Worker did not reach an interruptible checkpoint')
        with engine.connect() as c:
            interrupted = row(c, db.jobs, db.jobs.c.id == jid)
        assert interrupted['state'] == 'running', 'Interruption raced completion; not a valid drill'
        note('interrupted', completed_steps=len(checkpoint), attempts=interrupted['attempts'])
        spawn()
        deadline = time.monotonic() + args.timeout_seconds
        while time.monotonic() < deadline:
            with engine.connect() as c:
                final = row(c, db.jobs, db.jobs.c.id == jid)
            if final['state'] in {'succeeded', 'failed', 'cancelled'}:
                break
            time.sleep(0.25)
        assert final['state'] == 'succeeded', f'Recovery failed: {final["state"]} / {final["error"]}'
        with engine.connect() as c:
            run = row(c, db.research_runs, db.research_runs.c.id == final['result']['run_id'])
            steps = rows(c, db.research_steps, db.research_steps.c.run_id == run['id'])
            records = rows(c, db.records, db.records.c.project_id == pid)
            messages = rows(c, db.messages, db.messages.c.conversation_id == cid)
        keys = [s['step_key'] for s in steps]
        checks = {'steps': len(steps), 'checkpointed_before_crash': len(checkpoint),
            'checkpoint_preserved': all(next(s for s in steps if s['id'] == key)['result'] == value
                                        for key, value in checkpoint.items()),
            'steps_succeeded': sum(s['state'] == 'succeeded' for s in steps),
            'duplicate_step_keys': len(keys)-len(set(keys)), 'recovered_attempts': final['attempts'],
            'manuscripts_for_run': sum(r['kind']=='manuscript' and r['payload'].get('run_id')==run['id'] for r in records),
            'unique_step_artifacts': len({s['result']['record_id'] for s in steps}),
            'completion_messages': sum(run['id']==m['metadata'].get('run_id') and final['result']['record_id'] in m['artifact_ids'] for m in messages)}
        ok = (run['state']=='completed_with_open_questions' and checks['checkpoint_preserved']
              and checks['steps_succeeded']==len(steps) and checks['duplicate_step_keys']==0
              and checks['unique_step_artifacts']==len(steps) and checks['manuscripts_for_run']==1
              and checks['completion_messages']==1 and checks['recovered_attempts']>=2)
        note('recovered', **checks)
    except Exception as exc:
        error = str(exc)
        note('failed', error=error)
    finally:
        for child in children:
            stop(child)
        engine.dispose()
        base.dispose()
        report = {'ok': ok, 'schema': schema, 'checks': checks, 'timeline': timeline, 'error': error,
                  'scope': 'Process restart only; synthetic material and explicit demo model'}
        (out / 'drill.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'drill.md').write_text('\n'.join(['# Worker 中断恢复演练', '',
            f'- 结果：{"通过" if ok else "未通过"}', f'- 隔离 schema：`{schema}`',
            '- 范围：进程崩溃恢复；合成材料、显式演示模式；不等于系统重启或学术质量验收。',
            '', '| 检查 | 值 |', '|---|---|', *[f'| {k} | {v} |' for k,v in checks.items()],
            '', f'错误：{error or "无"}']), encoding='utf-8')
    print(json.dumps({'report': str(out / 'drill.json'), 'ok': ok}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
