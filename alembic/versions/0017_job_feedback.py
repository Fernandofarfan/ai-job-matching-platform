""""Me interesa / no me interesa" por oferta.

Revision ID: 0017_job_feedback
Revises: 0016_weekly_digest
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0017_job_feedback'
down_revision = '0016_weekly_digest'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `job_feedback`: una fila por cuenta y oferta (huella de título y empresa)."""
    op.create_table(
        'job_feedback',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('fingerprint', sa.String(40), nullable=False),
        sa.Column('interested', sa.Boolean, nullable=False),
        sa.Column('title', sa.String(300)),
        sa.Column('company', sa.String(200)),
        sa.Column('location', sa.String(200)),
        sa.Column('url', sa.String(1000)),
        sa.Column('match_score', sa.Float),
        sa.Column('updated_at', sa.DateTime),
        sa.UniqueConstraint('user_id', 'fingerprint', name='uq_job_feedback_user_fingerprint'),
    )
    op.create_index('ix_job_feedback_user_id', 'job_feedback', ['user_id'])


def downgrade():
    """Borra la tabla."""
    op.drop_index('ix_job_feedback_user_id', table_name='job_feedback')
    op.drop_table('job_feedback')
