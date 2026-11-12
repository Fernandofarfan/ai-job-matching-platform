"""Passkeys (WebAuthn).

Revision ID: 0019_passkeys
Revises: 0018_email_delivery
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0019_passkeys'
down_revision = '0018_email_delivery'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `passkeys` y `webauthn_challenges`."""
    op.create_table(
        'passkeys',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('credential_id', sa.Text, nullable=False),
        sa.Column('credential_hash', sa.String(64), nullable=False),
        sa.Column('public_key', sa.Text, nullable=False),
        sa.Column('sign_count', sa.Integer, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime),
        sa.Column('last_used_at', sa.DateTime),
        sa.UniqueConstraint('credential_hash'),
    )
    op.create_index('ix_passkeys_user_id', 'passkeys', ['user_id'])
    op.create_table(
        'webauthn_challenges',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('challenge_hash', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('user_id', sa.Integer),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.UniqueConstraint('challenge_hash'),
    )
    op.create_index('ix_webauthn_challenges_expires_at', 'webauthn_challenges', ['expires_at'])


def downgrade():
    """Quita las tablas."""
    op.drop_index('ix_webauthn_challenges_expires_at', table_name='webauthn_challenges')
    op.drop_table('webauthn_challenges')
    op.drop_index('ix_passkeys_user_id', table_name='passkeys')
    op.drop_table('passkeys')
