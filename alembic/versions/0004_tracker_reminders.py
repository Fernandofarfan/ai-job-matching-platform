"""Fechas de seguimiento, vencimiento y notas en `applications`, y cuándo se avisó por última vez.

Revision ID: 0004_tracker_reminders
Revises: 0003_tracker_status
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0004_tracker_reminders'
down_revision = '0003_tracker_status'
branch_labels = None
depends_on = None

COLUMNS = {
    'follow_up': sa.Date(),
    'deadline': sa.Date(),
    'notes': sa.Text(),
    'last_reminder_at': sa.DateTime(),
}


def _missing_columns():
    """Columnas que faltan; sin `applications` no hay nada que hacer."""
    if context.is_offline_mode():
        return list(COLUMNS)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('applications'):
        return []
    existing = {c['name'] for c in inspector.get_columns('applications')}
    return [name for name in COLUMNS if name not in existing]


def upgrade():
    """Agrega las columnas que falten (las bases creadas con models.py ya tienen algunas)."""
    for name in _missing_columns():
        op.add_column('applications', sa.Column(name, COLUMNS[name], nullable=True))


def downgrade():
    """Solo quita last_reminder_at: las demás columnas pueden venir de models.py."""
    if context.is_offline_mode() or sa.inspect(op.get_bind()).has_table('applications'):
        op.drop_column('applications', 'last_reminder_at')
