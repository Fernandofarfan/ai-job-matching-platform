"""Segundo factor TOTP por cuenta.

Revision ID: 0012_user_totp
Revises: 0011_user_sessions
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_user_totp'
down_revision = '0011_user_sessions'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `user_totp`."""
    op.create_table(
        'user_totp',
        sa.Column('user_id', sa.Integer, primary_key=True, autoincrement=False),
        sa.Column('secret', sa.String(255), nullable=False),
        sa.Column('recovery_hashes', sa.Text, nullable=True),
        sa.Column('last_step', sa.Integer, nullable=True),
        sa.Column('enabled_at', sa.DateTime, nullable=True),
    )


def downgrade():
    """Borra la tabla."""
    op.drop_table('user_totp')
