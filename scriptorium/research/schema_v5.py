"""Frozen additive governance and editorial schema for research_0005."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from .schema_v4 import metadata as previous


def add_tables(target):
    j = sa.JSON().with_variant(JSONB(), 'postgresql')
    users = sa.Table('r_users', target, sa.Column('id', sa.String(128), primary_key=True),
        sa.Column('name', sa.Text, nullable=False), sa.Column('created_at', sa.Float, nullable=False))
    sessions = sa.Table('r_sessions', target, sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.ForeignKey('r_users.id'), nullable=False),
        sa.Column('expires_at', sa.Float, nullable=False))
    policies = sa.Table('r_project_policies', target,
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), primary_key=True),
        sa.Column('revision', sa.Integer, nullable=False), sa.Column('payload', j, nullable=False))
    audit = sa.Table('r_audit', target, sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), index=True),
        sa.Column('actor', sa.String(128), nullable=False), sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target', sa.String(128), nullable=False), sa.Column('data', j, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    workspaces = sa.Table('r_workspaces', target,
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), primary_key=True),
        sa.Column('user_id', sa.String(128), primary_key=True),
        sa.Column('conversation_id', sa.ForeignKey('r_conversations.id'), primary_key=True),
        sa.Column('revision', sa.Integer, nullable=False), sa.Column('payload', j, nullable=False))
    comments = sa.Table('r_comments', target, sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('record_id', sa.ForeignKey('r_records.id'), nullable=False, index=True),
        sa.Column('author', sa.String(128), nullable=False), sa.Column('text', sa.Text, nullable=False),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('created_at', sa.Float, nullable=False))
    proposals = sa.Table('r_change_proposals', target, sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.ForeignKey('r_projects.id'), nullable=False, index=True),
        sa.Column('record_id', sa.ForeignKey('r_records.id'), nullable=False, index=True),
        sa.Column('base_revision', sa.Integer, nullable=False), sa.Column('author', sa.String(128), nullable=False),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('payload', j, nullable=False),
        sa.Column('created_at', sa.Float, nullable=False))
    return users, sessions, policies, audit, workspaces, comments, proposals


metadata = sa.MetaData()
for table in previous.sorted_tables:
    table.to_metadata(metadata)
add_tables(metadata)
NEW_TABLES = {'r_users', 'r_sessions', 'r_project_policies', 'r_audit', 'r_workspaces', 'r_comments', 'r_change_proposals'}
