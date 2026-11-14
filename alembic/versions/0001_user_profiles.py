"""Tabla user_profiles (perfiles de CV por rol, antes en profiles/user_profiles.json).

Revision ID: 0001_user_profiles
Revises: 0000_core_tables
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0001_user_profiles'
down_revision = '0000_core_tables'
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table('user_profiles'):
        return
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('role_type', sa.String(100), nullable=False, unique=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade():
    op.drop_table('user_profiles')
