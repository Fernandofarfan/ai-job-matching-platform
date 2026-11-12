"""Integraciones por cuenta (Telegram, extensión de Chrome y Gmail).

Revision ID: 0008_user_integrations
Revises: 0007_email_verification
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_user_integrations'
down_revision = '0007_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `user_integrations`."""
    op.create_table(
        'user_integrations',
        sa.Column('user_id', sa.Integer, primary_key=True, autoincrement=False),
        sa.Column('telegram_chat_id', sa.String(64), nullable=True),
        sa.Column('extension_token_hash', sa.String(64), nullable=True, unique=True),
        sa.Column('gmail_token', sa.Text, nullable=True),
        sa.Column('legacy_extension_off', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )


def downgrade():
    """Borra la tabla."""
    op.drop_table('user_integrations')
