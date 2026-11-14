"""Verificación del email de las cuentas.

Revision ID: 0007_email_verification
Revises: 0006_status_history
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_email_verification'
down_revision = '0006_status_history'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `email_verified_at`; las cuentas que ya existían quedan verificadas."""
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime, nullable=True))
    op.execute("UPDATE users SET email_verified_at = COALESCE(created_at, NOW())")


def downgrade():
    """Quita la columna."""
    op.drop_column('users', 'email_verified_at')
