"""Frozen automatic-research provenance and discovery schema (research_0006)."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from .schema_v5 import metadata as previous


def add_tables(target):
    j = sa.JSON().with_variant(JSONB(), 'postgresql')
    sources = sa.Table('r_sources', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('identity', sa.String(64), nullable=False),
        sa.Column('payload', j, nullable=False), sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False),
        sa.UniqueConstraint('project_id', 'identity'))
    intakes = sa.Table('r_intakes', target,
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), nullable=False),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('payload', j, nullable=False), sa.Column('created_at', sa.Float, nullable=False))
    links = sa.Table('r_run_sources', target,
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), primary_key=True),
        sa.Column('source_id', sa.ForeignKey('r_sources.id'), primary_key=True),
        sa.Column('payload', j, nullable=False), sa.Column('revision', sa.Integer, nullable=False))
    calls = sa.Table('r_discovery_calls', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), nullable=False, index=True),
        sa.Column('model_call_id', sa.ForeignKey('r_model_calls.id')),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('payload', j, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    return sources, intakes, links, calls


metadata = sa.MetaData()
for table in previous.sorted_tables:
    table.to_metadata(metadata)
add_tables(metadata)
NEW_TABLES = {'r_sources', 'r_intakes', 'r_run_sources', 'r_discovery_calls'}
