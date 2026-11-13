#!/usr/bin/env sh
# Entrypoint: aplica migraciones Alembic y luego levanta la app.
# (Alembic es la única fuente de verdad del esquema — setup_database.sql fue eliminado)
set -e

echo "[entrypoint] Aplicando migraciones Alembic..."
alembic upgrade head
echo "[entrypoint] Migraciones OK."

echo "[entrypoint] Iniciando uvicorn (main:app)..."
exec uvicorn main:app --host 0.0.0.0 --port 5000
