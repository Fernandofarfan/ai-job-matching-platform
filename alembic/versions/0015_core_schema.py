"""Lleva las tablas base a la forma de models.py y crea las que solo creaba create_all.

Hasta acá algunas tablas venían de setup_database.sql y otras de `create_all` al arrancar,
cada una con columnas distintas. Desde esta migración Alembic crea todo el esquema y el
test de drift (tests_integration/test_schema.py) compara la base con los modelos.

Revision ID: 0015_core_schema
Revises: 0014_legal_consent
Create Date: 2026-11-12
"""
from alembic import context, op
import sqlalchemy as sa

revision = '0015_core_schema'
down_revision = '0014_legal_consent'
branch_labels = None
depends_on = None

_TABLE_KW = {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
_KANBAN = "'bookmarked','applying','applied','interviewing','negotiating','accepted','rejected'"
_CONN_STATUS = "'sent','accepted','declined','pending','withdrawn'"

APPLICATION_COLUMNS = {
    'excitement': sa.Integer(),
    'date_applied': sa.Date(),
    'overall_match': sa.Float(),
    'skill_match': sa.Float(),
    'experience_match': sa.Float(),
    'text_similarity': sa.Float(),
    'ai_match_score': sa.Float(),
    'ai_nivel': sa.String(50),
    'ai_modalidad': sa.String(50),
    'ai_resumen': sa.Text(),
    'salary_min_usd': sa.Float(),
    'salary_max_usd': sa.Float(),
    'updated_at': sa.DateTime(),
    'source_platform': sa.String(50),
}
CONNECTION_COLUMNS = {
    'contact_name': sa.String(255),
    'contact_profile_url': sa.Text(),
    'message_sent': sa.Text(),
}
# Columnas TIMESTAMP de setup_database.sql que en los modelos son DATETIME
TIMESTAMP_COLUMNS = (('applications', 'applied_date'), ('applications', 'created_at'),
                     ('connection_requests', 'sent_date'), ('processed_files', 'processed_date'),
                     ('networking_exclusions', 'excluded_at'))
# Índices de setup_database.sql que los modelos no tienen
LEGACY_INDEXES = (('connection_requests', 'idx_company'), ('connection_requests', 'idx_status'),
                  ('processed_files', 'idx_filename'))


def _inspector():
    """Inspector de la base conectada (None en modo --sql)."""
    return None if context.is_offline_mode() else sa.inspect(op.get_bind())


def _columns(inspector, table):
    """{columna: tipo en minúsculas}; en modo --sql, la forma que deja 0000_core_tables."""
    if inspector is None:
        legacy = {
            'applications': {'applied_date': 'timestamp', 'created_at': 'timestamp'},
            'connection_requests': {'sent_date': 'timestamp', 'created_at': 'timestamp'},
            'processed_files': {'processed_date': 'timestamp'},
        }
        return legacy.get(table, {})
    return {c['name']: str(c['type']).lower() for c in inspector.get_columns(table)}


def _indexes(inspector, table):
    """Nombres de los índices de `table` (vacío en modo --sql)."""
    if inspector is None:
        return {name for t, name in LEGACY_INDEXES if t == table}
    return {i['name'] for i in inspector.get_indexes(table)}


def _has_table(inspector, table):
    """True si `table` existe (en modo --sql se asume que no)."""
    return inspector is not None and inspector.has_table(table)


def _core_tables(inspector):
    """Columnas, tipos e índices de applications, connection_requests y processed_files."""
    apps = _columns(inspector, 'applications')
    for name, type_ in APPLICATION_COLUMNS.items():
        if name not in apps:
            op.add_column('applications', sa.Column(name, type_, nullable=True))
    if 'idx_overall_match' not in _indexes(inspector, 'applications'):
        op.create_index('idx_overall_match', 'applications', ['overall_match'])
    op.execute("UPDATE applications SET status = 'applied' WHERE status IS NULL")
    op.execute(f"ALTER TABLE applications MODIFY status ENUM({_KANBAN}) NOT NULL DEFAULT 'applied'")

    conns = _columns(inspector, 'connection_requests')
    for name, type_ in CONNECTION_COLUMNS.items():
        if name not in conns:
            op.add_column('connection_requests', sa.Column(name, type_, nullable=True))
    op.execute(f"ALTER TABLE connection_requests MODIFY status ENUM({_CONN_STATUS}) DEFAULT 'sent'")
    op.execute("ALTER TABLE connection_requests MODIFY application_ids TEXT NULL")
    if 'created_at' in conns:
        op.execute("UPDATE connection_requests SET sent_date = created_at WHERE sent_date IS NULL")
        op.drop_column('connection_requests', 'created_at')

    op.execute("ALTER TABLE processed_files MODIFY filename VARCHAR(500) NOT NULL")

    for table, name in LEGACY_INDEXES:
        if name in _indexes(inspector, table):
            op.drop_index(name, table_name=table)
    for table, column in TIMESTAMP_COLUMNS:
        if inspector is not None and not inspector.has_table(table):
            continue
        if _columns(inspector, table).get(column) == 'timestamp':
            op.execute(f"ALTER TABLE {table} MODIFY {column} DATETIME NULL DEFAULT CURRENT_TIMESTAMP")


def _new_tables(inspector):
    """Tablas que hasta ahora solo creaba `create_all` al arrancar la app."""
    if not _has_table(inspector, 'networking_exclusions'):
        op.create_table(
            'networking_exclusions',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer),
            sa.Column('company_name', sa.String(255), nullable=False),
            sa.Column('excluded_at', sa.DateTime),
            **_TABLE_KW,
        )
        op.create_index('ix_networking_exclusions_user_id', 'networking_exclusions', ['user_id'])
        op.create_index('uq_networking_exclusions_user_company_name', 'networking_exclusions',
                        ['user_id', 'company_name'], unique=True)
    if not _has_table(inspector, 'market_insights'):
        op.create_table(
            'market_insights',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('role', sa.String(255), nullable=False),
            sa.Column('experience_level', sa.String(50)),
            sa.Column('location', sa.String(100)),
            sa.Column('salary_avg_usd', sa.Float),
            sa.Column('salary_low_usd', sa.Float),
            sa.Column('salary_high_usd', sa.Float),
            sa.Column('demand_level', sa.String(20)),
            sa.Column('trend', sa.String(50)),
            sa.Column('top_skills', sa.Text),
            sa.Column('raw_data', sa.Text),
            sa.Column('generated_at', sa.DateTime),
            sa.Column('expires_at', sa.DateTime),
            sa.Index('idx_role_level', 'role', 'experience_level'),
            **_TABLE_KW,
        )
    if not _has_table(inspector, 'mock_interviews'):
        op.create_table(
            'mock_interviews',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('job_title', sa.String(255), nullable=False),
            sa.Column('company', sa.String(255)),
            sa.Column('application_id', sa.Integer,
                      sa.ForeignKey('applications.id', ondelete='SET NULL'), nullable=True),
            sa.Column('questions_json', sa.Text),
            sa.Column('answers_json', sa.Text),
            sa.Column('overall_score', sa.Float),
            sa.Column('completed', sa.Boolean),
            sa.Column('created_at', sa.DateTime),
            sa.Column('completed_at', sa.DateTime),
            **_TABLE_KW,
        )
    if not _has_table(inspector, 'user_settings'):
        op.create_table(
            'user_settings',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('key', sa.String(100), nullable=False, unique=True),
            sa.Column('value', sa.Text),
            sa.Column('updated_at', sa.DateTime),
            **_TABLE_KW,
        )


def upgrade():
    """Completa las tablas base y crea las que falten."""
    inspector = _inspector()
    _core_tables(inspector)
    _new_tables(inspector)


def downgrade():
    """No vuelve atrás: las columnas y tablas nuevas pueden tener datos que la app usa."""
