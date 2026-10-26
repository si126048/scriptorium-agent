"""Frozen source acquisition and resumable timeline schema (research_0007)."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from .schema_v6 import metadata as previous


def add_tables(target):
    j = sa.JSON().with_variant(JSONB(), 'postgresql')
    blocks = sa.Table('r_timeline_blocks', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), nullable=False, index=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), nullable=False, index=True),
        sa.Column('block_key', sa.String(200), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False), sa.Column('state', sa.String(32), nullable=False),
        sa.Column('generation', sa.Integer, nullable=False), sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('payload', j, nullable=False), sa.Column('created_at', sa.Float, nullable=False),
        sa.Column('updated_at', sa.Float, nullable=False), sa.UniqueConstraint('job_id', 'block_key'))
    locations = sa.Table('r_source_locations', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('source_id', sa.ForeignKey('r_sources.id'), nullable=False, index=True),
        sa.Column('url', sa.Text, nullable=False), sa.Column('identity', sa.String(64), nullable=False),
        sa.Column('payload', j, nullable=False), sa.Column('created_at', sa.Float, nullable=False),
        sa.UniqueConstraint('source_id', 'identity'))
    attempts = sa.Table('r_acquisition_attempts', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), nullable=False, index=True),
        sa.Column('source_id', sa.ForeignKey('r_sources.id'), nullable=False),
        sa.Column('location_id', sa.ForeignKey('r_source_locations.id')),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('payload', j, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    requests = sa.Table('r_metadata_requests', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('job_id', sa.ForeignKey('r_jobs.id'), nullable=False, index=True),
        sa.Column('channel', sa.String(32), nullable=False), sa.Column('request_key', sa.String(64), nullable=False),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('payload', j, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False), sa.UniqueConstraint('job_id', 'request_key'))
    return blocks, locations, attempts, requests

metadata = sa.MetaData()
for table in previous.sorted_tables:
    table.to_metadata(metadata)
add_tables(metadata)
NEW_TABLES = {'r_timeline_blocks', 'r_source_locations', 'r_acquisition_attempts', 'r_metadata_requests'}
