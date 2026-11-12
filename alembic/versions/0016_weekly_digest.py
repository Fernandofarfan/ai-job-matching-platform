"""Preferencia del resumen semanal por email.

Revision ID: 0016_weekly_digest
Revises: 0015_core_schema
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_weekly_digest'
down_revision = '0015_core_schema'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `users.weekly_digest_off_at` (None = recibe el resumen)."""
    op.add_column('users', sa.Column('weekly_digest_off_at', sa.DateTime, nullable=True))


def downgrade():
    """Quita la columna."""
    op.drop_column('users', 'weekly_digest_off_at')
