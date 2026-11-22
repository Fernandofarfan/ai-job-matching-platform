"""Perfiles borrados como fila vacía con `deleted_at`, para que un respaldo de una caída no los reviva.

Revision ID: 0022_profile_tombstones
Revises: 0021_account_inactivity
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0022_profile_tombstones'
down_revision = '0021_account_inactivity'
branch_labels = None
depends_on = None


def upgrade():
    """Agrega `user_profiles.deleted_at`."""
    op.add_column('user_profiles', sa.Column('deleted_at', sa.DateTime, nullable=True))


def downgrade():
    """Borra las filas marcadas como borradas y la columna."""
    op.execute('DELETE FROM user_profiles WHERE deleted_at IS NOT NULL')
    op.drop_column('user_profiles', 'deleted_at')
