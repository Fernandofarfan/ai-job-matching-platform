"""El tracker usa los estados del kanban en `applications` (antes solo applied/interviewing/...).

Revision ID: 0003_tracker_status
Revises: 0002_job_alerts
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0003_tracker_status'
down_revision = '0002_job_alerts'
branch_labels = None
depends_on = None

_KANBAN = "'bookmarked','applying','applied','interviewing','negotiating','accepted','rejected'"
_LEGACY = "'applied','interviewing','rejected','accepted'"


def _has_applications():
    return context.is_offline_mode() or sa.inspect(op.get_bind()).has_table('applications')


def upgrade():
    if _has_applications():
        op.execute(f"ALTER TABLE applications MODIFY status ENUM({_KANBAN}) DEFAULT 'applied'")


def downgrade():
    if _has_applications():
        op.execute("UPDATE applications SET status = 'applied' WHERE status IN ('bookmarked','applying','negotiating')")
        op.execute(f"ALTER TABLE applications MODIFY status ENUM({_LEGACY}) DEFAULT 'applied'")
