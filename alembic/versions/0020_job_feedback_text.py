"""Descripción de la oferta en cada "me interesa / no me interesa", para el dataset de evaluación.

Revision ID: 0020_job_feedback_text
Revises: 0019_passkeys
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = '0020_job_feedback_text'
down_revision = '0019_passkeys'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `job_feedback.job_text`."""
    op.add_column('job_feedback', sa.Column('job_text', sa.Text))


def downgrade():
    """Quita `job_feedback.job_text`."""
    op.drop_column('job_feedback', 'job_text')
