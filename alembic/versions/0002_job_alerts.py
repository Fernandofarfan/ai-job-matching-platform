"""Alertas de empleo: búsquedas guardadas y ofertas ya avisadas.

Revision ID: 0002_job_alerts
Revises: 0001_user_profiles
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0002_job_alerts'
down_revision = '0001_user_profiles'
branch_labels = None
depends_on = None

_TABLE_ARGS = {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}


def _exists(name):
    return not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _exists('saved_searches'):
        op.create_table(
            'saved_searches',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('position', sa.String(200), nullable=False),
            sa.Column('location', sa.String(200), nullable=False),
            sa.Column('portals', sa.JSON(), nullable=False),
            sa.Column('channels', sa.JSON(), nullable=False),
            sa.Column('min_score', sa.Float(), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('last_run_at', sa.DateTime()),
            sa.Column('last_result', sa.String(255)),
            **_TABLE_ARGS,
        )
    if not _exists('seen_jobs'):
        op.create_table(
            'seen_jobs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('fingerprint', sa.String(40), nullable=False, unique=True),
            sa.Column('title', sa.String(300)),
            sa.Column('company', sa.String(200)),
            sa.Column('url', sa.String(1000)),
            sa.Column('source', sa.String(50)),
            sa.Column('search_id', sa.Integer()),
            sa.Column('first_seen_at', sa.DateTime()),
            **_TABLE_ARGS,
        )


def downgrade():
    op.drop_table('seen_jobs')
    op.drop_table('saved_searches')
