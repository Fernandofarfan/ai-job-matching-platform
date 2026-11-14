"""Última actividad de cada cuenta y aviso de borrado por inactividad.

Revision ID: 0021_account_inactivity
Revises: 0020_job_feedback_text
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = '0021_account_inactivity'
down_revision = '0020_job_feedback_text'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `users.last_active_at` (con la última sesión de cada cuenta), `users.inactivity_notice_at` e `inactivity_notice_sent`."""
    op.add_column('users', sa.Column('last_active_at', sa.DateTime, nullable=True))
    op.add_column('users', sa.Column('inactivity_notice_at', sa.DateTime, nullable=True))
    op.add_column('users', sa.Column('inactivity_notice_sent', sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute('UPDATE users SET last_active_at = '
               '(SELECT MAX(s.last_seen_at) FROM user_sessions s WHERE s.user_id = users.id)')


def downgrade():
    """Quita las dos columnas."""
    op.drop_column('users', 'inactivity_notice_sent')
    op.drop_column('users', 'inactivity_notice_at')
    op.drop_column('users', 'last_active_at')
