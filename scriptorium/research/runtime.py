"""Shared runtime selection for CLI, ACP and MCP. SQLite is an explicit compatibility mode."""
import os

import sqlalchemy as sa

from . import schema as db
from .config import ResearchSettings
from .legacy_store import PostgresStore
from .service import ResearchService, row, ResearchError


def enabled():
    return bool(os.getenv('SCRIPTORIUM_DATABASE_URL')) and os.getenv('SCRIPTORIUM_RUNTIME') != 'sqlite'


def open_store(project_id, *, resource_id=None, corpus=False):
    cfg = ResearchSettings.from_env()
    service = ResearchService(db.engine_for(cfg.database_url), cfg)
    with service.engine.connect() as c:
        if resource_id:
            matches = list(c.execute(sa.select(db.entities.c.project_id).join(db.members,
                db.members.c.project_id == db.entities.c.project_id).where(
                db.entities.c.external_id == resource_id, db.members.c.user_id == cfg.principal)).scalars())
            if not matches:
                matches = list(c.execute(sa.select(db.assets.c.project_id).join(db.members,
                    db.members.c.project_id == db.assets.c.project_id).where(
                    db.assets.c.id == resource_id, db.members.c.user_id == cfg.principal)).scalars())
            if len(set(matches)) != 1:
                raise ResearchError('RESOURCE_PROJECT_AMBIGUOUS_OR_MISSING')
            project_id = matches[0]
        existing = row(c, db.projects, db.projects.c.id == project_id)
    if not existing:
        service.create_project(cfg.principal, project_id, project_id=project_id)
    return PostgresStore(service, project_id, cfg.principal, corpus=corpus)


def get_provider(mock=False):
    from .capabilities import provider
    if mock:
        return provider('demo')
    if os.getenv('DASHSCOPE_API_KEY'):
        return provider('live')
    class MissingProvider:
        def generate_structured(self, *args, **kwargs):
            raise ResearchError('MODEL_NOT_CONFIGURED')
    return MissingProvider()
