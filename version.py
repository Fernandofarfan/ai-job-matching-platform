"""Versión de la app (archivo VERSION, la cambia scripts/release.py) y commit del build (APP_COMMIT)."""
import os
from pathlib import Path

__version__ = Path(__file__).with_name('VERSION').read_text(encoding='utf-8').strip()


def commit() -> str | None:
    """Commit corto de la imagen: el Dockerfile lo recibe como build-arg APP_COMMIT."""
    value = os.getenv('APP_COMMIT', '').strip()
    return value[:12] or None


def release() -> str:
    """Identificador del build para Sentry: empleoia@3.0.0 o empleoia@3.0.0+<commit>."""
    sha = commit()
    return f"empleoia@{__version__}" + (f"+{sha}" if sha else "")
