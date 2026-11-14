"""Registro de eventos de seguridad por cuenta.

Revision ID: 0010_security_events
Revises: 0009_push_subscriptions
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_security_events'
down_revision = '0009_push_subscriptions'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `security_events`."""
    op.create_table(
        'security_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=False, index=True),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('device', sa.String(16), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True, index=True),
    )


def downgrade():
    """Borra la tabla."""
    op.drop_table('security_events')
