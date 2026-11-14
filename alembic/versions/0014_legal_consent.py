"""Aceptación de Términos y Privacidad, y permiso para mandar datos a la IA.

Revision ID: 0014_legal_consent
Revises: 0013_user_disabled
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_legal_consent'
down_revision = '0013_user_disabled'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `users.terms_accepted_at` y `users.ai_consent_at`."""
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime, nullable=True))
    op.add_column('users', sa.Column('ai_consent_at', sa.DateTime, nullable=True))


def downgrade():
    """Quita las columnas."""
    op.drop_column('users', 'ai_consent_at')
    op.drop_column('users', 'terms_accepted_at')
