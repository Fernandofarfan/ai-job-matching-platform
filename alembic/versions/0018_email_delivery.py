"""Lista de rebotes y resumen semanal recuperable si el worker se corta.

Revision ID: 0018_email_delivery
Revises: 0017_job_feedback
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0018_email_delivery'
down_revision = '0017_job_feedback'
branch_labels = None
depends_on = None


def upgrade():
    """Crea `email_suppressions` y agrega `users.weekly_digest_claimed_at/_from`."""
    op.create_table(
        'email_suppressions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('email_hash', sa.String(64), nullable=False),
        sa.Column('reason', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime),
        sa.UniqueConstraint('email_hash'),
    )
    op.add_column('users', sa.Column('weekly_digest_claimed_at', sa.DateTime, nullable=True))
    op.add_column('users', sa.Column('weekly_digest_claimed_from', sa.DateTime, nullable=True))


def downgrade():
    """Quita las columnas y la tabla."""
    op.drop_column('users', 'weekly_digest_claimed_from')
    op.drop_column('users', 'weekly_digest_claimed_at')
    op.drop_table('email_suppressions')
