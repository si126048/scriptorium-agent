"""Frozen additive schema for research_0004. Never imports the runtime schema."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from .schema_v3 import metadata as previous


def add_tables(target):
    json = sa.JSON().with_variant(JSONB(), 'postgresql')
    calls = sa.Table('r_model_calls', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('job_id', sa.String(64), nullable=False, index=True),
        sa.Column('run_id', sa.String(64), index=True),
        sa.Column('model', sa.Text, nullable=False),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('reserved_tokens', sa.Integer, nullable=False),
        sa.Column('usage', json), sa.Column('error', sa.String(128)),
        sa.Column('source_assets', json, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False), sa.Column('finished_at', sa.Float))
    drafts = sa.Table('r_method_drafts', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('job_id', sa.String(64), nullable=False, unique=True),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('payload', json, nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    events = sa.Table('r_conversation_events', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), nullable=False, index=True),
        sa.Column('sequence', sa.BigInteger, nullable=False),
        sa.Column('type', sa.String(64), nullable=False),
        sa.Column('payload', json, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False),
        sa.UniqueConstraint('conversation_id', 'sequence'))
    chapters = sa.Table('r_document_chapters', target,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('record_id', sa.ForeignKey('r_records.id'), nullable=False, index=True),
        sa.Column('ordinal', sa.Integer, nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('payload', json, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    return calls, drafts, events, chapters


metadata = sa.MetaData()
for table in previous.sorted_tables:
    table.to_metadata(metadata)
add_tables(metadata)
NEW_TABLES = {'r_model_calls', 'r_method_drafts', 'r_conversation_events', 'r_document_chapters'}
