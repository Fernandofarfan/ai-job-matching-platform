"""Cuentas bloqueadas desde el panel de administración.

Revision ID: 0013_user_disabled
Revises: 0012_user_totp
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_user_disabled'
down_revision = '0012_user_totp'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `users.disabled_at`."""
    op.add_column('users', sa.Column('disabled_at', sa.DateTime, nullable=True))


def downgrade():
    """Quita la columna."""
    op.drop_column('users', 'disabled_at')
