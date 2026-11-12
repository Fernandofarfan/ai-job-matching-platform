"""Drift del esquema: la base que arma Alembic tiene que coincidir con los modelos.

Si este test falla después de tocar un modelo, falta la migración que lleva la base a esa forma.
"""
import os
import pathlib
import secrets
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, make_url, text

import db_schema
import models

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEGACY_SQL = pathlib.Path(__file__).parent / 'fixtures' / 'legacy_schema.sql'


def _engine(database=None):
    """Engine al servidor de los tests, opcionalmente sobre otra base."""
    url = make_url(models.get_database_url())
    return create_engine(url.set(database=database) if database else url)


@pytest.fixture
def scratch_db():
    """Base vacía y temporal en el mismo servidor; se borra al terminar."""
    name = f'schema_{secrets.token_hex(4)}'
    server = _engine('')
    with server.begin() as conn:
        conn.execute(text(f'CREATE DATABASE {name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    try:
        yield name
    finally:
        with server.begin() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS {name}'))
        server.dispose()


def _upgrade(database):
    """`alembic upgrade head` sobre `database` (dos veces: tiene que ser idempotente)."""
    env = {**os.environ, 'DB_NAME': database}
    for _ in range(2):
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env, check=True)


def _diff(database):
    """Diferencias entre `database` y los modelos."""
    engine = _engine(database)
    try:
        with engine.connect() as conn:
            return db_schema.schema_diff(conn)
    finally:
        engine.dispose()


def test_migrated_db_matches_models(migrated_db):
    """La base de los tests de integración (ya migrada) no tiene drift."""
    assert _diff(os.getenv('DB_NAME', 'job_tracker')) == []


def test_empty_db_matches_models_after_migrations(scratch_db):
    """Desde una base vacía, las migraciones crean todas las tablas tal como están en los modelos."""
    _upgrade(scratch_db)
    assert _diff(scratch_db) == []


def test_legacy_setup_sql_db_converges(scratch_db):
    """Una base creada con el viejo setup_database.sql termina igual que los modelos, sin perder filas."""
    engine = _engine(scratch_db)
    with engine.begin() as conn:
        for statement in LEGACY_SQL.read_text(encoding='utf-8').split(';'):
            lines = [line for line in statement.splitlines() if not line.strip().startswith('--')]
            if ''.join(lines).strip():
                conn.execute(text('\n'.join(lines)))
    _upgrade(scratch_db)
    assert _diff(scratch_db) == []
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM applications')).scalar() == 'interviewing'
        assert conn.execute(text('SELECT status FROM connection_requests')).scalar() == 'declined'
        assert conn.execute(text('SELECT total_jobs FROM processed_files')).scalar() == 3
    engine.dispose()


def test_drift_is_detected(scratch_db):
    """Si a la base le falta una columna de un modelo, el chequeo lo marca."""
    _upgrade(scratch_db)
    engine = _engine(scratch_db)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE applications DROP COLUMN ai_resumen'))
    engine.dispose()
    diffs = _diff(scratch_db)
    assert any(d[0] == 'add_column' and d[3].name == 'ai_resumen' for d in diffs)
