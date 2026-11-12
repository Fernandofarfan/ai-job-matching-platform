"""Cuentas de usuario y `user_id` en las tablas con datos personales.

Revision ID: 0005_users
Revises: 0004_tracker_reminders
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0005_users'
down_revision = '0004_tracker_reminders'
branch_labels = None
depends_on = None

OWNED = ('applications', 'user_profiles', 'saved_searches', 'seen_jobs',
         'networking_exclusions', 'connection_requests', 'processed_files')
# Únicos globales que pasan a ser por usuario: (tabla, índice viejo, columna)
PER_USER_UNIQUE = (('user_profiles', 'role_type'), ('seen_jobs', 'fingerprint'),
                   ('networking_exclusions', 'company_name'), ('processed_files', 'filename'))


def _inspector():
    return None if context.is_offline_mode() else sa.inspect(op.get_bind())


def _has_table(inspector, table):
    return inspector is None or inspector.has_table(table)


def _unique_on(inspector, table, column):
    """Nombres de los índices únicos de una sola columna sobre `column`."""
    if inspector is None:
        return [column]
    names = [i['name'] for i in inspector.get_indexes(table) if i.get('unique') and i['column_names'] == [column]]
    names += [u['name'] for u in inspector.get_unique_constraints(table) if u['column_names'] == [column]]
    return list(dict.fromkeys(names))


def upgrade():
    inspector = _inspector()
    if inspector is None or not inspector.has_table('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('email', sa.String(255), nullable=False, unique=True),
            sa.Column('password_hash', sa.String(255), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
        )
    for table in OWNED:
        if not _has_table(inspector, table):
            continue
        if inspector is None or 'user_id' not in {c['name'] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column('user_id', sa.Integer(), nullable=True))
            op.create_index(f'ix_{table}_user_id', table, ['user_id'])
    for table, column in PER_USER_UNIQUE:
        if not _has_table(inspector, table):
            continue
        for name in _unique_on(inspector, table, column):
            op.drop_index(name, table_name=table)
        op.create_index(f'uq_{table}_user_{column}', table, ['user_id', column], unique=True)


def downgrade():
    inspector = _inspector()
    for table, column in PER_USER_UNIQUE:
        if _has_table(inspector, table):
            op.drop_index(f'uq_{table}_user_{column}', table_name=table)
            op.create_index(column, table, [column], unique=True)
    for table in OWNED:
        if _has_table(inspector, table):
            op.drop_index(f'ix_{table}_user_id', table_name=table)
            op.drop_column(table, 'user_id')
    op.drop_table('users')
