from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ResearchSettings


def main(argv=None):
    parser = argparse.ArgumentParser(prog='scriptorium-research', description='Scriptorium research service and non-destructive migration')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db')
    sub.add_parser('start')
    serve = sub.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', default=8010, type=int)
    worker = sub.add_parser('worker')
    worker.add_argument('--once', action='store_true')
    migrate = sub.add_parser('migrate-sqlite')
    migrate.add_argument('source', type=Path)
    migrate.add_argument('--apply', action='store_true')
    migrate.add_argument('--source-root', type=Path, action='append', default=[])
    migrate.add_argument('--report', type=Path)
    sub.add_parser('rebuild-index')
    sub.add_parser('retry-index')
    sub.add_parser('doctor')
    verify = sub.add_parser('verify-anchors')
    verify.add_argument('--report', type=Path)
    save = sub.add_parser('backup')
    save.add_argument('destination', type=Path)
    load = sub.add_parser('restore')
    load.add_argument('source', type=Path)
    load.add_argument('--withdrawal-ledger', type=Path)
    gc = sub.add_parser('gc')
    gc.add_argument('--apply', action='store_true')
    gc.add_argument('--retention-hours', type=int, default=24)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv()
    settings = ResearchSettings.from_env()
    if args.command == 'start':
        from .supervisor import start
        start()
        return
    if args.command == 'migrate-sqlite' and not args.apply:
        from .migration import migrate as run
        result = run(None, args.source, settings.principal)
    elif args.command == 'serve':
        if args.host not in {'localhost', '127.0.0.1', '::1'} and not settings.api_key and not __import__('os').getenv('SCRIPTORIUM_OIDC_ISSUER'):
            parser.error('Remote binding requires SCRIPTORIUM_RESEARCH_API_KEY')
        import uvicorn
        uvicorn.run('scriptorium.research.api:app', host=args.host, port=args.port)
        return
    elif args.command == 'init-db':
        from alembic import command
        from alembic.config import Config
        import sys
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        config = Config(str(base / 'alembic-research.ini'))
        config.set_main_option('script_location', str(base / 'migrations' / 'research'))
        command.upgrade(config, 'head')
        result = {'status': 'schema_upgraded'}
    else:
        import sqlalchemy as sa
        from . import schema as db
        from .service import ResearchService
        engine = db.engine_for(settings.database_url)
        service = ResearchService(engine, settings)
        try:
            if args.command == 'worker':
                from .worker import run_one, work
                from .search import sync_one
                if not args.once:
                    work(service)
                    return
                result = {'job_processed': run_one(service), 'index_event_processed': sync_one(service)}
            elif args.command == 'migrate-sqlite':
                from .migration import migrate as run
                result = run(service, args.source, settings.principal, apply=True, source_roots=args.source_root)
            elif args.command == 'rebuild-index':
                from .search import rebuild
                result = {'index': rebuild(service)}
            elif args.command == 'retry-index':
                with engine.begin() as c:
                    count = c.execute(db.outbox.update().where(db.outbox.c.done.is_(False)).values(attempts=0, error=None)).rowcount
                result = {'requeued': count}
            elif args.command == 'verify-anchors':
                # Switch-checklist item: every reference counted as verified must still resolve.
                from .service import row, rows
                with engine.connect() as c:
                    anchors = rows(c, db.anchors)
                    problems, located = [], 0
                    for anchor in anchors:
                        segment = row(c, db.segments, db.segments.c.id == anchor['segment_id'])
                        if not segment:
                            problems.append({'anchor_id': anchor['id'], 'reason': 'SEGMENT_MISSING'})
                            continue
                        if segment['text'][anchor['start_codepoint']:anchor['end_codepoint']] != anchor['exact_quote']:
                            problems.append({'anchor_id': anchor['id'], 'reason': 'QUOTE_MISMATCH',
                                             'asset_id': segment['asset_id'], 'version_id': segment['version_id']})
                            continue
                        asset = row(c, db.assets, db.assets.c.id == segment['asset_id'])
                        if not asset or asset['status'] == 'revoked':
                            problems.append({'anchor_id': anchor['id'], 'reason': 'MATERIAL_REVOKED',
                                             'asset_id': segment['asset_id']})
                            continue
                        located += 1
                result = {'anchors_total': len(anchors), 'located': located,
                          'problem_count': len(problems), 'problems': problems[:2000],
                          'truncated': len(problems) > 2000}
            elif args.command == 'doctor':
                result = {**service.queue_status(), 'object_backend': settings.object_backend,
                          'object_root': str(service.objects.root),
                          'object_root_exists': service.objects.root.exists(),
                          'elasticsearch_url': settings.elasticsearch_url,
                          'api_key_configured': bool(settings.api_key),
                          'principal': settings.principal}
            elif args.command == 'backup':
                from .backup import backup
                result = backup(service, args.destination)
            elif args.command == 'restore':
                from .backup import restore
                result = restore(service, args.source, args.withdrawal_ledger)
            elif args.command == 'gc':
                if settings.object_backend != 'filesystem':
                    parser.error('S3 cleanup requires bucket inventory and retention policy; filesystem GC is disabled')
                if args.retention_hours < 1:
                    parser.error('Retention must be at least one hour')
                # Serialize with material registration/revision using a table lock, and retain young objects.
                with engine.begin() as c:
                    c.execute(sa.text('LOCK TABLE r_assets, r_text_versions IN EXCLUSIVE MODE'))
                    keys = set(c.execute(sa.select(db.assets.c.object_key)).scalars())
                    keys.update(c.execute(sa.select(db.versions.c.object_key)).scalars())
                    keys.update(r['result']['object_key'] for r in c.execute(sa.select(db.jobs)).mappings() if (r['result'] or {}).get('object_key'))
                    removed = []
                    cutoff = db.now() - args.retention_hours * 3600
                    for path in service.objects.root.glob('*/*'):
                        key = path.relative_to(service.objects.root).as_posix()
                        if path.is_file() and key not in keys and path.stat().st_mtime < cutoff:
                            service.objects.path(key)  # validate resolved workspace containment
                            removed.append(key)
                            if args.apply:
                                path.unlink()
                    result = {'dry_run': not args.apply, 'unreferenced_objects': removed}
            else:
                parser.error('Unknown command')
        finally:
            engine.dispose()
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if getattr(args, 'report', None):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding='utf-8')
        # Reports can be very large; print only the counts an operator needs to decide next steps.
        counted = {key: result[key] for key in ('source_rows', 'accounted_source_rows', 'anchors_migrated',
            'anchors_total', 'located', 'problem_count') if key in result}
        if 'exceptions' in result:
            counted['exceptions'] = len(result['exceptions'])
        print(json.dumps({'report': str(args.report), **counted}, ensure_ascii=False))
    else:
        print(output)


if __name__ == '__main__':
    main()
