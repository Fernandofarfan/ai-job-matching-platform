"""
init_db.py — Inicializa la base de datos ejecutando las migraciones de Alembic.

Uso:  python init_db.py   (o  alembic upgrade head)

NOTA: el antiguo setup_database.sql fue eliminado: el esquema lo define
models.py y las migraciones de alembic/ son la única fuente de verdad.
"""
import subprocess
import sys


def main() -> int:
    print("Aplicando migraciones de Alembic (alembic upgrade head)...")
    result = subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])
    if result == 0:
        print("Base de datos inicializada correctamente.")
    else:
        print("ERROR: las migraciones fallaron. Verificá MySQL y el .env "
              "(DB_HOST/DB_USER/DB_PASSWORD/DB_NAME).", file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
