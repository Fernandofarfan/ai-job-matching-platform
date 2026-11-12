"""Sesiones abiertas por cuenta.

Revision ID: 0011_user_sessions
Revises: 0010_security_events
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_user_sessions'
down_revision = '0010_security_events'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `user_sessions`."""
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=False, index=True),
        sa.Column('sid_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.Column('last_seen_at', sa.DateTime, nullable=True),
        sa.Column('revoked_at', sa.DateTime, nullable=True),
    )


def downgrade():
    """Borra la tabla."""
    op.drop_table('user_sessions')
