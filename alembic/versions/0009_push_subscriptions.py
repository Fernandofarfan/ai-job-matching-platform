"""Suscripciones a notificaciones push por cuenta.

Revision ID: 0009_push_subscriptions
Revises: 0008_user_integrations
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_push_subscriptions'
down_revision = '0008_user_integrations'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `push_subscriptions`."""
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True, index=True),
        sa.Column('endpoint_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('endpoint', sa.Text, nullable=False),
        sa.Column('p256dh', sa.String(255), nullable=False),
        sa.Column('auth', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )


def downgrade():
    """Borra la tabla."""
    op.drop_table('push_subscriptions')
