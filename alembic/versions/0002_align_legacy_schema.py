"""align legacy schema with ORM models

Repara esquemas creados por el viejo setup_database.sql:
- applications: ENUM de 4 estados -> 7 estados (ORM default 'bookmarked'),
  agrega columnas que el ORM inserta (excitement, ai_*, etc.) e índice faltante.
- connection_requests: ENUM ampliado + columnas de contacto.
- processed_files: filename VARCHAR(255) -> VARCHAR(500).
- Elimina la tabla muerta 'job_tracker' (la app siempre usó 'applications').

Idempotente: inspecciona information_schema antes de cada ALTER.

Revision ID: 0002_align_legacy_schema
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_align_legacy_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_APP_STATUS = ["bookmarked", "applying", "applied", "interviewing",
               "negotiating", "accepted", "rejected"]
_CONN_STATUS = ["sent", "accepted", "pending", "withdrawn", "declined"]

_APP_ADDITIONS = [
    ("excitement", "INT DEFAULT 0"),
    ("date_applied", "DATE NULL"),
    ("deadline", "DATE NULL"),
    ("follow_up", "DATE NULL"),
    ("notes", "TEXT NULL"),
    ("overall_match", "FLOAT DEFAULT 0"),
    ("skill_match", "FLOAT DEFAULT 0"),
    ("experience_match", "FLOAT DEFAULT 0"),
    ("text_similarity", "FLOAT DEFAULT 0"),
    ("ai_match_score", "FLOAT DEFAULT 0"),
    ("ai_nivel", "VARCHAR(50) NULL"),
    ("ai_modalidad", "VARCHAR(50) NULL"),
    ("ai_resumen", "TEXT NULL"),
    ("salary_min_usd", "FLOAT NULL"),
    ("salary_max_usd", "FLOAT NULL"),
    ("updated_at", "DATETIME NULL"),
    ("source_platform", "VARCHAR(50) DEFAULT 'manual'"),
]

_CONN_ADDITIONS = [
    ("contact_name", "VARCHAR(255) NULL"),
    ("contact_profile_url", "TEXT NULL"),
    ("message_sent", "TEXT NULL"),
]


def _enum_literal(values) -> str:
    return ",".join(f"'{v}'" for v in values)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        # SQLite (tests) u otros: 0001 create_all ya creó el esquema correcto
        return

    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # ── applications ──────────────────────────────────────────────────────
    if "applications" in tables:
        cols = {c["name"]: c for c in insp.get_columns("applications")}

        status_col = cols.get("status")
        if status_col is not None and status_col["type"].name.lower() == "enum":
            current = set(status_col["type"].enums)
            if not set(_APP_STATUS).issubset(current):
                bind.execute(sa.text(
                    "ALTER TABLE applications MODIFY status "
                    f"ENUM({_enum_literal(_APP_STATUS)}) "
                    "NOT NULL DEFAULT 'bookmarked'"))

        for name, ddl in _APP_ADDITIONS:
            if name not in cols:
                bind.execute(sa.text(
                    f"ALTER TABLE applications ADD COLUMN {name} {ddl}"))

        indexes = {i["name"] for i in insp.get_indexes("applications")}
        if "idx_overall_match" not in indexes:
            bind.execute(sa.text(
                "CREATE INDEX idx_overall_match ON applications (overall_match)"))

    # ── connection_requests ───────────────────────────────────────────────
    if "connection_requests" in tables:
        cols = {c["name"]: c for c in insp.get_columns("connection_requests")}

        status_col = cols.get("status")
        if status_col is not None and status_col["type"].name.lower() == "enum":
            current = set(status_col["type"].enums)
            if not set(_CONN_STATUS).issubset(current):
                bind.execute(sa.text(
                    "ALTER TABLE connection_requests MODIFY status "
                    f"ENUM({_enum_literal(_CONN_STATUS)}) "
                    "NOT NULL DEFAULT 'sent'"))

        for name, ddl in _CONN_ADDITIONS:
            if name not in cols:
                bind.execute(sa.text(
                    f"ALTER TABLE connection_requests ADD COLUMN {name} {ddl}"))

    # ── processed_files ───────────────────────────────────────────────────
    if "processed_files" in tables:
        cols = {c["name"]: c for c in insp.get_columns("processed_files")}
        fname = cols.get("filename")
        if fname is not None and getattr(fname["type"], "length", None) \
                and fname["type"].length < 500:
            bind.execute(sa.text(
                "ALTER TABLE processed_files MODIFY filename "
                "VARCHAR(500) UNIQUE NOT NULL"))

    # ── tabla muerta ──────────────────────────────────────────────────────
    # La app siempre leyó/escribió 'applications' (ver db_config histórico);
    # 'job_tracker' nunca fue leída por el código actual.
    if "job_tracker" in tables:
        bind.execute(sa.text("DROP TABLE job_tracker"))


def downgrade() -> None:
    # Migración reparadora de esquemas legacy; no hay downgrade significativo.
    pass
