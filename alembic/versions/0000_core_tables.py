"""Tablas base que antes creaba setup_database.sql (applications, connection_requests, processed_files).

Se crean con la forma que tenían en ese script; las migraciones siguientes las llevan a la
forma actual. En bases que ya las tienen no hace nada.

Revision ID: 0000_core_tables
Revises:
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0000_core_tables'
down_revision = None
branch_labels = None
depends_on = None

_TABLE_KW = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
_NOW = sa.text('CURRENT_TIMESTAMP')


def _missing(table):
    """True si hay que crear `table` (en modo --sql se asume una base vacía)."""
    return context.is_offline_mode() or not sa.inspect(op.get_bind()).has_table(table)


def upgrade():
    """Crea las tablas base que falten."""
    if _missing('applications'):
        op.create_table(
            'applications',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('company', sa.String(255), nullable=False),
            sa.Column('location', sa.String(255)),
            sa.Column('job_link', sa.Text),
            sa.Column('description', sa.Text),
            sa.Column('salary', sa.String(100)),
            sa.Column('experience_category', sa.String(100)),
            sa.Column('job_type', sa.String(100)),
            sa.Column('suggested_address', sa.String(255)),
            sa.Column('applied_date', sa.TIMESTAMP, server_default=_NOW),
            sa.Column('status', sa.Enum('applied', 'interviewing', 'rejected', 'accepted'),
                      server_default='applied'),
            sa.Column('created_at', sa.TIMESTAMP, server_default=_NOW),
            sa.Index('idx_company', 'company'),
            sa.Index('idx_status', 'status'),
            sa.Index('idx_applied_date', 'applied_date'),
            **_TABLE_KW,
        )
    if _missing('connection_requests'):
        op.create_table(
            'connection_requests',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('company', sa.String(255), nullable=False),
            sa.Column('sent_date', sa.TIMESTAMP, server_default=_NOW),
            sa.Column('status', sa.Enum('sent', 'accepted', 'declined', 'pending'), server_default='sent'),
            sa.Column('application_ids', sa.Text),
            sa.Column('created_at', sa.TIMESTAMP, server_default=_NOW),
            sa.Index('idx_company', 'company'),
            sa.Index('idx_status', 'status'),
            **_TABLE_KW,
        )
    if _missing('processed_files'):
        op.create_table(
            'processed_files',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('filename', sa.String(255), nullable=False, unique=True),
            sa.Column('total_jobs', sa.Integer, server_default='0'),
            sa.Column('jobs_applied', sa.Integer, server_default='0'),
            sa.Column('processed_date', sa.TIMESTAMP, server_default=_NOW),
            sa.Index('idx_filename', 'filename'),
            **_TABLE_KW,
        )


def downgrade():
    """Borra las tablas base."""
    for table in ('processed_files', 'connection_requests', 'applications'):
        op.drop_table(table)
