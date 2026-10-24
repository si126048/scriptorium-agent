"""Explicit relational identities, versioned JSON payloads, and durable work queues."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
JSON = sa.JSON().with_variant(JSONB(), 'postgresql')


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(UTC).timestamp()


projects = sa.Table('r_projects', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('name', sa.Text, nullable=False),
    sa.Column('description', sa.Text, nullable=False, default=''),
    sa.Column('owner_id', sa.String(128), nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
members = sa.Table('r_members', metadata,
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), primary_key=True),
    sa.Column('user_id', sa.String(128), primary_key=True),
    sa.Column('role', sa.String(16), nullable=False))
works = sa.Table('r_works', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('title', sa.Text, nullable=False),
    sa.Column('metadata', JSON, nullable=False))
editions = sa.Table('r_editions', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('work_id', sa.ForeignKey('r_works.id'), nullable=False),
    sa.Column('metadata', JSON, nullable=False))
assets = sa.Table('r_assets', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('edition_id', sa.ForeignKey('r_editions.id'), nullable=False),
    sa.Column('name', sa.Text, nullable=False),
    sa.Column('object_key', sa.Text, nullable=False),
    sa.Column('sha256', sa.String(64), nullable=False),
    sa.Column('size', sa.BigInteger, nullable=False),
    sa.Column('status', sa.String(32), nullable=False),
    sa.Column('revision', sa.Integer, nullable=False, default=1),
    sa.Column('metadata', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
versions = sa.Table('r_text_versions', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('asset_id', sa.ForeignKey('r_assets.id'), nullable=False, index=True),
    sa.Column('parent_id', sa.ForeignKey('r_text_versions.id')),
    sa.Column('object_key', sa.Text, nullable=False),
    sa.Column('projection_version', sa.String(32), nullable=False),
    sa.Column('quality', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
segments = sa.Table('r_segments', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('asset_id', sa.ForeignKey('r_assets.id'), nullable=False, index=True),
    sa.Column('version_id', sa.ForeignKey('r_text_versions.id'), nullable=False, index=True),
    sa.Column('xml_id', sa.String(128), nullable=False),
    sa.Column('ordinal', sa.Integer, nullable=False),
    sa.Column('page_label', sa.String(128)),
    sa.Column('text', sa.Text, nullable=False),
    sa.UniqueConstraint('version_id', 'xml_id'))
anchors = sa.Table('r_anchors', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('segment_id', sa.ForeignKey('r_segments.id'), nullable=False),
    sa.Column('start_codepoint', sa.Integer, nullable=False),
    sa.Column('end_codepoint', sa.Integer, nullable=False),
    sa.Column('exact_quote', sa.Text, nullable=False),
    sa.Column('quote_sha256', sa.String(64), nullable=False),
    sa.CheckConstraint('start_codepoint >= 0 AND end_codepoint > start_codepoint'))
records = sa.Table('r_records', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('kind', sa.String(64), nullable=False, index=True),
    sa.Column('revision', sa.Integer, nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False),
    sa.Column('updated_at', sa.Float, nullable=False))
record_history = sa.Table('r_record_history', metadata,
    sa.Column('record_id', sa.ForeignKey('r_records.id'), primary_key=True),
    sa.Column('revision', sa.Integer, primary_key=True),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
jobs = sa.Table('r_jobs', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('kind', sa.String(32), nullable=False),
    sa.Column('idem', sa.String(128), nullable=False),
    sa.Column('request_hash', sa.String(64), nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('state', sa.String(32), nullable=False),
    sa.Column('attempts', sa.Integer, nullable=False, default=0),
    sa.Column('lease_until', sa.Float),
    sa.Column('lease_token', sa.String(64)),
    sa.Column('error', sa.Text),
    sa.Column('result', JSON),
    sa.Column('created_at', sa.Float, nullable=False),
    sa.UniqueConstraint('project_id', 'kind', 'idem'))
events = sa.Table('r_events', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('job_id', sa.ForeignKey('r_jobs.id'), nullable=False, index=True),
    sa.Column('created_at', sa.Float, nullable=False),
    sa.Column('data', JSON, nullable=False))
outbox = sa.Table('r_outbox', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('asset_id', sa.ForeignKey('r_assets.id'), nullable=False),
    sa.Column('revision', sa.Integer, nullable=False),
    sa.Column('done', sa.Boolean, nullable=False, default=False),
    sa.Column('attempts', sa.Integer, nullable=False, default=0),
    sa.Column('error', sa.Text),
    sa.Column('created_at', sa.Float, nullable=False))
legacy = sa.Table('r_legacy', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('source', sa.String(64), nullable=False),
    sa.Column('table_name', sa.String(128), nullable=False),
    sa.Column('legacy_key', sa.Text, nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('status', sa.String(96), nullable=False),
    sa.UniqueConstraint('source', 'table_name', 'legacy_key'))

conversations = sa.Table('r_conversations', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('title', sa.Text, nullable=False),
    sa.Column('archived', sa.Boolean, nullable=False, default=False),
    sa.Column('revision', sa.Integer, nullable=False, default=1),
    sa.Column('workspace', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
messages = sa.Table('r_messages', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), nullable=False, index=True),
    sa.Column('role', sa.String(16), nullable=False),
    sa.Column('content', sa.Text, nullable=False),
    sa.Column('artifact_ids', JSON, nullable=False),
    sa.Column('metadata', JSON, nullable=False),
    sa.Column('created_at', sa.Float, nullable=False))
entities = sa.Table('r_entities', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('kind', sa.String(48), nullable=False, index=True),
    sa.Column('external_id', sa.String(256), nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('revision', sa.Integer, nullable=False, default=1),
    sa.Column('created_at', sa.Float, nullable=False),
    sa.UniqueConstraint('project_id', 'kind', 'external_id'))
research_runs = sa.Table('r_research_runs', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), nullable=False),
    sa.Column('question', sa.Text, nullable=False),
    sa.Column('state', sa.String(32), nullable=False),
    sa.Column('scope', JSON, nullable=False),
    sa.Column('settings', JSON, nullable=False),
    sa.Column('used_tokens', sa.Integer, nullable=False, default=0),
    sa.Column('reserved_tokens', sa.Integer, nullable=False, default=0),
    sa.Column('created_at', sa.Float, nullable=False))
research_steps = sa.Table('r_research_steps', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('run_id', sa.ForeignKey('r_research_runs.id'), nullable=False, index=True),
    sa.Column('step_key', sa.String(128), nullable=False),
    sa.Column('state', sa.String(32), nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('result', JSON),
    sa.Column('created_at', sa.Float, nullable=False),
    sa.UniqueConstraint('run_id', 'step_key'))
decisions = sa.Table('r_decisions', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('run_id', sa.ForeignKey('r_research_runs.id'), nullable=False),
    sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
    sa.Column('kind', sa.String(32), nullable=False),
    sa.Column('state', sa.String(16), nullable=False),
    sa.Column('payload', JSON, nullable=False),
    sa.Column('answer', JSON),
    sa.Column('created_at', sa.Float, nullable=False))


from .schema_v4 import add_tables
model_calls, method_drafts, conversation_events, document_chapters = add_tables(metadata)


def engine_for(url: str, *, test=False):
    if not url or (not test and not url.startswith('postgresql+psycopg://')):
        raise ValueError('SCRIPTORIUM_DATABASE_URL must use postgresql+psycopg://')
    return sa.create_engine(url, pool_pre_ping=True)
