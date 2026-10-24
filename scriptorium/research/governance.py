"""Authorization, egress policy and append-only application audit."""
import os
from urllib.parse import urlsplit
from . import schema as db
from .service import ResearchError, row, rows


def audit(c, pid, actor, action, target='', data=None):
    c.execute(db.audit.insert().values(id=db.uid(), project_id=pid, actor=actor,
        action=action, target=target, data=data or {}, created_at=db.now()))


def owner(service, c, pid, actor):
    service.access(c, pid, actor)
    member = row(c, db.members, db.members.c.project_id == pid, db.members.c.user_id == actor)
    if member['role'] != 'owner':
        raise ResearchError('PROJECT_OWNER_REQUIRED', 403)


def administrator(actor, settings):
    if os.getenv('SCRIPTORIUM_OIDC_ISSUER'):
        return actor in set(os.getenv('SCRIPTORIUM_ADMIN_SUBJECTS', '').split(','))
    return actor == settings.principal


def check_egress(s, c, job, provider, estimate):
    pid = job['project_id']
    policy = row(c, db.project_policies, db.project_policies.c.project_id == pid)
    # Local personal mode retains its existing explicit model configuration.
    rules = policy['payload'] if policy else ({'allow_external': False} if os.getenv('SCRIPTORIUM_OIDC_ISSUER') else {})
    base = str(getattr(provider, 'base_url', '') or getattr(getattr(provider, 'client', None), 'base_url', ''))
    host = urlsplit(base).hostname
    external = host not in {'localhost', '127.0.0.1', '::1'}
    if external and rules.get('allow_external') is False:
        raise ResearchError('PROJECT_EXTERNAL_PROCESSING_DISABLED', 403)
    if external and rules.get('allowed_hosts') and host not in rules['allowed_hosts']:
        raise ResearchError('MODEL_ENDPOINT_NOT_AUTHORIZED', 403)
    source_assets = set(job['payload'].get('asset_ids', []))
    if job.get('_synchronous') and not source_assets:
        # Legacy synchronous algorithms predate scope snapshots. Fail conservatively
        # against all project sources rather than bypassing a material allowlist.
        source_assets.update(r['id'] for r in rows(c, db.assets, db.assets.c.project_id == pid, db.assets.c.status == 'ready'))
    for sid in job['payload'].get('segment_ids', []):
        segment = row(c, db.segments, db.segments.c.id == sid, db.segments.c.project_id == pid)
        if not segment:
            raise ResearchError('SOURCE_NO_LONGER_AVAILABLE', 404)
        source_assets.add(segment['asset_id'])
    for aid in source_assets:
        asset = s.asset(c, pid, aid)
        if external and asset['metadata'].get('sensitive'):
            raise ResearchError('SENSITIVE_MATERIAL_EXTERNAL_PROCESSING_DISABLED', 403)
        if external and rules.get('asset_ids') is not None and aid not in rules['asset_ids']:
            raise ResearchError('MATERIAL_EXTERNAL_PROCESSING_NOT_AUTHORIZED', 403)
        if external and rules.get('version_ids') is not None:
            submitted = [w['version_id'] for w in job['payload'].get('scope_snapshot', []) if w['asset_id'] == aid]
            submitted.extend(r['version_id'] for sid in job['payload'].get('segment_ids', []) if (r := row(c, db.segments, db.segments.c.id == sid, db.segments.c.asset_id == aid)))
            if not submitted:
                latest = sorted(rows(c, db.versions, db.versions.c.asset_id == aid), key=lambda r: r['created_at'])
                submitted = [latest[-1]['id']] if latest else []
            if any(v not in rules['version_ids'] for v in submitted):
                raise ResearchError('TEXT_VERSION_EXTERNAL_PROCESSING_NOT_AUTHORIZED', 403)
    if rules.get('token_budget'):
        calls = rows(c, db.model_calls, db.model_calls.c.project_id == pid)
        spent = sum((v['usage'] or {}).get('total_tokens', 0) +
            (v['reserved_tokens'] if v['state'] in {'unknown', 'reserved'} else 0) for v in calls)
        if spent + estimate > rules['token_budget']:
            raise ResearchError('PROJECT_BUDGET_REQUIRED', 409)
    return sorted(source_assets)
