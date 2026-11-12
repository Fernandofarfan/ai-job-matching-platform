"""
conftest.py – Fixtures globales de pytest para EmpleoIA.
Provee un cliente de prueba de la app con mock de DB y módulos pesados.
"""
import os
import sys
import types
import importlib
import importlib.abc
import importlib.machinery
import unittest.mock as mock
from types import SimpleNamespace

import pytest


# ─── Custom ModuleType que devuelve MagicMock para cualquier atributo ───────────
class _MockModule(types.ModuleType):
    """Módulo que devuelve MagicMock() para cualquier acceso de atributo."""
    def __getattr__(self, name):
        val = mock.MagicMock()
        object.__setattr__(self, name, val)
        return val

    def __call__(self, *args, **kwargs):
        return mock.MagicMock()


def _mk(name):
    m = _MockModule(name)
    m.__path__ = []
    m.__package__ = name.split('.')[0]
    m.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    return m


# ─── Lista exhaustiva de módulos a parchear ──────────────────────────────────
# (debe hacerse ANTES de cualquier import de app.py o scrapers)
_ALL_MOCKS = [
    # Async
    # NLP / ML
    'spacy', 'spacy.lang', 'spacy.lang.es',
    'nltk', 'nltk.tokenize', 'nltk.corpus', 'nltk.data', 'nltk.stem',
    'sklearn', 'sklearn.feature_extraction', 'sklearn.feature_extraction.text',
    'sklearn.metrics', 'sklearn.metrics.pairwise', 'sklearn.preprocessing',
    'sklearn.pipeline',
    'scipy', 'scipy.special', 'scipy.linalg', 'scipy.sparse',
    # Scheduler
    'apscheduler', 'APScheduler',
    'apscheduler.schedulers', 'apscheduler.schedulers.background',
    'apscheduler.triggers', 'apscheduler.triggers.cron', 'apscheduler.triggers.interval',
    # Google AI
    'google', 'google.genai', 'google.genai.types',
    # Database (usar mock en CI, real app usa MySQL)
    'mysql', 'mysql.connector', 'mysql.connector.pooling', 'mysql.connector.errors',
    # BeautifulSoup / parsing
    # Document parsing
    'pypdf', 'PyPDF2', 'docx', 'python_docx',
    # WSGI
    'waitress',
    # Playwright (scrapers/linkedin_pw.py)
    'playwright', 'playwright.sync_api', 'playwright.async_api',
]

for _mod_name in _ALL_MOCKS:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mk(_mod_name)

# Asegurar que el directorio raíz del proyecto esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='session')
def app():
    """
    Config de la web (web_settings.WebApp de app.py) en modo testing.
    Override de db_manager para evitar depender de MySQL durante CI.
    """
    # Parcheamos db_manager ANTES de importar app
    import unittest.mock as mock

    mock_jobs = [
        {
            'id': 1, 'title': 'Data Analyst', 'company': 'Acme Corp',
            'location': 'Buenos Aires', 'salary': '$ 200,000',
            'status': 'applied', 'excitement': 4,
            'date_saved': '2025-11-01 10:00:00', 'date_applied': '2025-11-02',
            'deadline': None, 'follow_up': None, 'notes': 'Test job', 'job_link': 'https://example.com'
        },
        {
            'id': 2, 'title': 'Backend Developer', 'company': 'TechCo',
            'location': 'Remoto', 'salary': '$ 300,000',
            'status': 'interviewing', 'excitement': 5,
            'date_saved': '2025-11-03 09:00:00', 'date_applied': '2025-11-04',
            'deadline': None, 'follow_up': None, 'notes': None, 'job_link': 'https://example2.com'
        },
        {
            'id': 3, 'title': 'Frontend Developer', 'company': 'StartupX',
            'location': 'CABA', 'salary': None,
            'status': 'bookmarked', 'excitement': 3,
            'date_saved': '2025-11-05 08:00:00', 'date_applied': None,
            'deadline': None, 'follow_up': None, 'notes': None, 'job_link': None
        },
    ]

    mock_db = mock.MagicMock()
    mock_db.get_all_tracked_jobs.return_value = mock_jobs
    mock_db.get_tracked_job_by_id.side_effect = lambda jid: next(
        (j for j in mock_jobs if j['id'] == jid), None)
    mock_db.add_job_to_tracker.return_value = 99
    mock_db.update_job_status.return_value = True
    mock_db.delete_tracked_job.return_value = True
    mock_db.get_applications.return_value = mock_jobs
    mock_db.get_companies_for_connections.return_value = []

    # Fuera del patch.dict para que app y los tests compartan el mismo módulo (y su JSON_PATH temporal)
    import profile_store  # noqa: F401
    # numpy no se puede cargar dos veces: si entra dentro del patch.dict, main.py (WebClient) falla al reimportarlo
    import numpy, pandas  # noqa: F401,E401
    # Modelos sobre accounts.Base: reimportarlos duplicaría sus índices en la metadata
    import integrations, push, security_events, two_factor, user_sessions  # noqa: F401,E401

    with mock.patch.dict('sys.modules', {}):
        import db_config
        db_config.db_manager = mock_db

        import app as app_module
        app_module.db_manager = mock_db

    app_module.app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-12345',
        'WTF_CSRF_ENABLED': False,
    })

    yield app_module.app


@pytest.fixture(autouse=True)
def _no_login_by_default(monkeypatch, tmp_path):
    """Los tests corren sin login salvo que pongan LOGIN_REQUIRED=true (ignora el .env local)."""
    monkeypatch.setenv('LOGIN_REQUIRED', 'false')
    monkeypatch.delenv('ALLOW_SIGNUP', raising=False)
    monkeypatch.delenv('EXTENSION_TOKEN', raising=False)
    monkeypatch.delenv('CV_ENCRYPTION_KEY', raising=False)
    # Perfiles en un JSON temporal: los tests no tocan MySQL ni profiles/ real
    import profile_store
    monkeypatch.setenv('PROFILE_STORAGE', 'json')
    monkeypatch.setattr(profile_store, 'JSON_PATH', str(tmp_path / 'user_profiles.json'))
    profile_store.configure(None)


class _Response:
    """Respuesta de httpx con la interfaz (get_data, get_json) que usan los tests."""

    def __init__(self, response):
        self._r = response
        self.status_code = response.status_code
        self.headers = response.headers
        self.data = response.content
        self.text = response.text
        self.content_type = response.headers.get('content-type', '')
        self.mimetype = self.content_type.split(';')[0]
        self.location = response.headers.get('location')

    def get_data(self, as_text=False):
        return self.text if as_text else self.data

    def get_json(self, silent=False):
        try:
            return self._r.json()
        except ValueError:
            if silent:
                return None
            raise

    @property
    def json(self):
        return self.get_json(silent=True)


class WebClient:
    """Cliente sobre main.create_app con la API del cliente de pruebas que usan los tests."""

    def __init__(self, web_app):
        from fastapi.testclient import TestClient
        import main
        self.app = main.create_app(web_app)
        self._c = TestClient(self.app, base_url='http://localhost')

    def open(self, method, path, data=None, json=None, query_string=None, headers=None,
             follow_redirects=False, content_type=None, **kwargs):
        files, form = None, data
        if isinstance(data, dict) and any(isinstance(v, tuple) for v in data.values()):
            files = {k: (v[1], v[0]) for k, v in data.items() if isinstance(v, tuple)}
            form = {k: v for k, v in data.items() if not isinstance(v, tuple)}
        headers = dict(headers or {})
        if content_type and not files and content_type != 'multipart/form-data':
            headers['Content-Type'] = content_type
        kw = {'content': form} if isinstance(form, (str, bytes)) else {'data': form}
        return _Response(self._c.request(method, path, params=query_string, json=json, files=files,
                                         headers=headers, follow_redirects=follow_redirects, **kw, **kwargs))

    def get(self, path, **kw):
        return self.open('GET', path, **kw)

    def post(self, path, **kw):
        return self.open('POST', path, **kw)

    def put(self, path, **kw):
        return self.open('PUT', path, **kw)

    def delete(self, path, **kw):
        return self.open('DELETE', path, **kw)

    def patch(self, path, **kw):
        return self.open('PATCH', path, **kw)

    def set_cookie(self, key, value='', **_):
        self._c.cookies.set(key, value)

    def delete_cookie(self, key, **_):
        self._c.cookies.delete(key)


@pytest.fixture
def client(app):
    """Cliente HTTP de prueba sobre la app completa, como en producción."""
    return WebClient(app)


@pytest.fixture
def make_client(app):
    """Otro navegador (cookies propias) contra la misma app."""
    return lambda: WebClient(app)


@pytest.fixture
def mock_db(app):
    """Acceso directo al mock del DatabaseManager."""
    import app as app_module
    return app_module.db_manager



@pytest.fixture
def tracker_db(app):
    """Mock del DatabaseManager que usan las rutas (el de app.db_manager)."""
    return app.extensions['empleoia_services'].db


@pytest.fixture
def api(app, tracker_db):
    """Cliente de las APIs FastAPI (tracker e insights) con el mock de la base y la config de los tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import ai, documents, insights, tracker
    from routers import push as push_router
    profiles = app.extensions['empleoia_services'].profiles
    fastapi_app = FastAPI()
    fastapi_app.include_router(tracker.router)
    fastapi_app.include_router(insights.router)
    fastapi_app.include_router(ai.router)
    fastapi_app.include_router(ai.extras)
    fastapi_app.include_router(documents.router)
    fastapi_app.include_router(push_router.router)
    fastapi_app.dependency_overrides[tracker.get_db] = lambda: tracker_db
    fastapi_app.dependency_overrides[tracker.get_web_app] = lambda: app
    fastapi_app.dependency_overrides[ai.get_ai] = lambda: SimpleNamespace(
        available=False, engine=None, notifier=None, resume_text=lambda: None, profile=lambda: None)
    fastapi_app.dependency_overrides[documents.get_resume_text] = lambda: lambda: None
    fastapi_app.dependency_overrides[insights.get_profiles] = lambda: (
        profiles.get_all_user_profiles, profiles.get_user_profile)
    return TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def _accounts_sqlite():
    """Cuentas en SQLite en memoria (vacía): los tests no tocan MySQL; sin cuentas no hay usuario actual."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import accounts
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    import integrations  # noqa: F401  (registra su tabla en Base)
    import push  # noqa: F401
    import security_events  # noqa: F401
    import two_factor  # noqa: F401
    import email_delivery  # noqa: F401
    import passkeys  # noqa: F401
    accounts.Base.metadata.create_all(engine)
    accounts.configure(sessionmaker(bind=engine))
    yield engine
    accounts.configure(None)
    accounts.set_current_user(None)


@pytest.fixture
def accounts_db(monkeypatch, app, _accounts_sqlite):
    """Login obligatorio, sin el límite de intentos de login/registro (lo cubre test_ops)."""
    monkeypatch.setitem(app.config, 'RATELIMIT_ENABLED', False)
    monkeypatch.setenv('LOGIN_REQUIRED', 'true')
    return _accounts_sqlite
