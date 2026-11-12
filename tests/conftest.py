"""
conftest.py – Fixtures globales de pytest para EmpleoIA.
Provee un cliente de prueba Flask con mock de DB y módulos pesados.
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
    # Flask extensions
    # Async
    # Selenium (todos los subpaths conocidos)
    'selenium', 'selenium.webdriver', 'selenium.webdriver.chrome',
    'selenium.webdriver.chrome.options', 'selenium.webdriver.chrome.service',
    'selenium.webdriver.remote', 'selenium.webdriver.remote.webdriver',
    'selenium.webdriver.support', 'selenium.webdriver.support.ui',
    'selenium.webdriver.support.expected_conditions',
    'selenium.webdriver.common', 'selenium.webdriver.common.by',
    'selenium.webdriver.common.keys', 'selenium.webdriver.common.action_chains',
    'selenium.webdriver.common.desired_capabilities',
    'selenium.common', 'selenium.common.exceptions',
    'undetected_chromedriver', 'webdriver_manager', 'webdriver_manager.chrome',
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
    # Selenium remote (needed by indeed_scraper.py)
    'selenium.webdriver.remote', 'selenium.webdriver.remote.webdriver',
    'selenium.webdriver.remote.webelement', 'selenium.webdriver.remote.command',
    'selenium.webdriver.remote.errorhandler', 'selenium.webdriver.remote.file_detector',
    'selenium.webdriver.remote.shadowroot', 'selenium.webdriver.remote.switch_to',
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
    Crea la app Flask en modo testing.
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
    # Modelos sobre accounts.Base: reimportarlos duplicaría sus índices en la metadata
    import integrations, push, security_events  # noqa: F401,E401

    with mock.patch.dict('sys.modules', {}):
        import db_config
        db_config.db_manager = mock_db

        import app as flask_app
        flask_app.db_manager = mock_db

    flask_app.app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-12345',
        'WTF_CSRF_ENABLED': False,
    })

    yield flask_app.app


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


@pytest.fixture
def client(app):
    """Cliente HTTP de prueba."""
    return app.test_client()


@pytest.fixture
def mock_db(app):
    """Acceso directo al mock del DatabaseManager."""
    import app as flask_app
    return flask_app.db_manager



@pytest.fixture
def tracker_db(app):
    """Mock del DatabaseManager que usan las rutas (el mismo que ven las vistas de Flask)."""
    return app.view_functions['index'].__globals__['db_manager']


@pytest.fixture
def api(app, tracker_db):
    """Cliente de las APIs FastAPI (tracker e insights) con el mock de la base y la app Flask de los tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import ai, documents, insights, tracker
    from routers import push as push_router
    flask_globals = app.view_functions['index'].__globals__['get_user_profile'].__globals__
    fastapi_app = FastAPI()
    fastapi_app.include_router(tracker.router)
    fastapi_app.include_router(insights.router)
    fastapi_app.include_router(ai.router)
    fastapi_app.include_router(ai.extras)
    fastapi_app.include_router(documents.router)
    fastapi_app.include_router(push_router.router)
    fastapi_app.dependency_overrides[tracker.get_db] = lambda: tracker_db
    fastapi_app.dependency_overrides[tracker.get_flask_app] = lambda: app
    fastapi_app.dependency_overrides[ai.get_ai] = lambda: SimpleNamespace(
        available=False, engine=None, notifier=None, resume_text=lambda: None, profile=lambda: None)
    fastapi_app.dependency_overrides[documents.get_resume_text] = lambda: lambda: None
    fastapi_app.dependency_overrides[insights.get_profiles] = lambda: (
        flask_globals['get_all_user_profiles'], flask_globals['get_user_profile'])
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
    accounts.Base.metadata.create_all(engine)
    accounts.configure(sessionmaker(bind=engine))
    yield engine
    accounts.configure(None)
    accounts.set_current_user(None)


@pytest.fixture
def accounts_db(monkeypatch, app, _accounts_sqlite):
    """Login obligatorio, sin el límite de intentos de login/registro (lo cubre test_ops)."""
    # El módulo app se importa dentro de patch.dict(sys.modules): el limiter se busca en la app
    limiters = app.extensions['limiter']
    for limiter in limiters if isinstance(limiters, (set, list, tuple)) else [limiters]:
        monkeypatch.setattr(limiter, 'enabled', False)
    monkeypatch.setenv('LOGIN_REQUIRED', 'true')
    return _accounts_sqlite
