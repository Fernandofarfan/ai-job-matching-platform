"""Historial de cambios de estado de las postulaciones.

Revision ID: 0006_status_history
Revises: 0005_users
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0006_status_history'
down_revision = '0005_users'
branch_labels = None
depends_on = None


def upgrade():
    """Crea la tabla y la siembra con el estado actual de cada postulación."""
    op.create_table(
        'application_status_history',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('application_id', sa.Integer, nullable=False, index=True),
        sa.Column('user_id', sa.Integer, nullable=True, index=True),
        sa.Column('old_status', sa.String(20), nullable=True),
        sa.Column('new_status', sa.String(20), nullable=False),
        sa.Column('changed_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    if context.is_offline_mode() or sa.inspect(op.get_bind()).has_table('applications'):
        op.execute(
            "INSERT INTO application_status_history (application_id, user_id, old_status, new_status, changed_at) "
            "SELECT id, user_id, NULL, status, COALESCE(created_at, NOW()) FROM applications"
        )


def downgrade():
    """Borra el historial."""
    op.drop_table('application_status_history')
