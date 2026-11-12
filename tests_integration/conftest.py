"""Tests contra MySQL y Redis reales (y la app levantada para los E2E).

No usan los mocks de tests/conftest.py. Se saltean salvo con INTEGRATION=1; en CI
corren en el job `integration` con servicios mysql:8.0 y redis:7.
"""
import base64
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PASSWORD = secrets.token_urlsafe(16)
# Con la clave del .env local la app de desarrollo sigue leyendo los perfiles que escribe el E2E (misma base)
CV_ENCRYPTION_KEY = os.getenv('CV_ENCRYPTION_KEY') or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def pytest_collection_modifyitems(config, items):
    """Saltea toda la suite salvo con INTEGRATION=1."""
    if os.getenv('INTEGRATION') != '1':
        skip = pytest.mark.skip(reason='INTEGRATION=1 para correr contra MySQL/Redis reales')
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope='session')
def app_password():
    """Contraseña con la que se levanta la app en los E2E."""
    return APP_PASSWORD


@pytest.fixture(scope='session')
def migrated_db():
    """Aplica las migraciones de Alembic (dos veces: deben ser idempotentes)."""
    for _ in range(2):
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, check=True)


def _free_port():
    """Puerto TCP libre en 127.0.0.1 para levantar uvicorn."""
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope='session')
def live_server(migrated_db, tmp_path_factory):
    """La app completa (FastAPI + Flask) con uvicorn, login activo y almacenamiento real."""
    port = _free_port()
    env = {
        **os.environ,
        'APP_PASSWORD': APP_PASSWORD,
        'SECRET_KEY': secrets.token_hex(32),
        'SCRAPER_BACKEND': 'thread',
        'CV_ENCRYPTION_KEY': CV_ENCRYPTION_KEY,
    }
    log = open(tmp_path_factory.mktemp('server') / 'uvicorn.log', 'w+')
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f'http://127.0.0.1:{port}'
    deadline = time.time() + 60
    while True:
        try:
            urllib.request.urlopen(url + '/api/health', timeout=2)
            break
        except Exception:
            if proc.poll() is not None or time.time() > deadline:
                log.seek(0)
                pytest.fail('La app no levantó:\n' + log.read()[-4000:])
            time.sleep(0.5)
    yield url
    proc.terminate()
    proc.wait(10)
    log.close()
