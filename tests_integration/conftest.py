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
# Cuenta de los E2E (en CI la base arranca vacía; en local conviene crear antes tu cuenta, que reclama los datos previos)
E2E_EMAIL = f'e2e-{secrets.token_hex(4)}@example.com'
E2E_PASSWORD = secrets.token_urlsafe(16)
# Con la clave del .env local la app de desarrollo sigue leyendo los perfiles que escribe el E2E (misma base)
CV_ENCRYPTION_KEY = os.getenv('CV_ENCRYPTION_KEY') or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def pytest_collection_modifyitems(config, items):
    """Saltea toda la suite salvo con INTEGRATION=1."""
    if os.getenv('INTEGRATION') != '1':
        skip = pytest.mark.skip(reason='INTEGRATION=1 para correr contra MySQL/Redis reales')
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope='session')
def credentials(migrated_db):
    """(email, contraseña) de una cuenta creada para los E2E."""
    from unittest import mock
    import accounts
    with mock.patch.dict(os.environ, {'ALLOW_SIGNUP': 'true'}):
        accounts.register(E2E_EMAIL, E2E_PASSWORD)
    return E2E_EMAIL, E2E_PASSWORD


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
        **{k: v for k, v in os.environ.items() if k not in ('APP_PASSWORD', 'ADMIN_EMAIL')},
        'LOGIN_REQUIRED': 'true',
        'ALLOW_SIGNUP': 'false',
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


@pytest.fixture(scope='session')
def playwright():
    """Una sola instancia de Playwright: la API síncrona no admite dos a la vez."""
    sync_api = pytest.importorskip('playwright.sync_api')
    with sync_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope='session')
def browser(playwright):
    """Chromium headless compartido por los tests E2E."""
    b = playwright.chromium.launch()
    yield b
    b.close()


@pytest.fixture
def page(browser, live_server, credentials):
    """Pestaña nueva apuntando a la app levantada."""
    context = browser.new_context(base_url=live_server, reduced_motion='reduce')
    page = context.new_page()
    page.set_default_timeout(20000)
    page.credentials = credentials
    yield page
    context.close()
