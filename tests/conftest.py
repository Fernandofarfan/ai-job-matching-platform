"""
conftest.py – Fixtures globales de pytest para EmpleoIA.
Provee un cliente de prueba FastAPI (TestClient) con mock de DB y módulos pesados.
"""
import os
import sys
import types
import importlib
import importlib.machinery
import unittest.mock as mock
import pytest

# Base de datos para tests: SQLite en memoria en disco (sin MySQL)
os.environ.setdefault("DATABASE_URL", "sqlite:///temp/test.db")


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
# (debe hacerse ANTES de cualquier import de main.py o scrapers)
_ALL_MOCKS = [
    # Async
    'eventlet', 'eventlet.wsgi',
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
    # Google AI (SDK google-genai)
    'google', 'google.genai', 'google.genai.types',
    'google.generativeai', 'google.generativeai.types',
    # Security
    'cryptography', 'cryptography.fernet', 'cryptography.hazmat',
    'cryptography.hazmat.primitives', 'cryptography.hazmat.backends',
    # Database (usar mock en CI, real app usa MySQL)
    'mysql', 'mysql.connector', 'mysql.connector.pooling', 'mysql.connector.errors',
    # Selenium remote (needed by indeed_scraper.py)
    'selenium.webdriver.remote.webelement', 'selenium.webdriver.remote.command',
    'selenium.webdriver.remote.errorhandler', 'selenium.webdriver.remote.file_detector',
    'selenium.webdriver.remote.shadowroot', 'selenium.webdriver.remote.switch_to',
    # BeautifulSoup / parsing
    'bs4', 'beautifulsoup4', 'lxml', 'lxml.html',
    # Document parsing
    'PyPDF2', 'pypdf', 'docx', 'python_docx',
    # WSGI
    'waitress',
]

for _mod_name in _ALL_MOCKS:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mk(_mod_name)

# Asegurar que el directorio raíz del proyecto esté en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_mock_jobs():
    return [
        {
            'id': 1, 'title': 'Data Analyst', 'company': 'Acme Corp',
            'location': 'Buenos Aires', 'salary': '$ 200,000',
            'status': 'applied', 'excitement': 4,
            'date_saved': '2025-11-01 10:00:00', 'date_applied': '2025-11-02',
            'deadline': None, 'follow_up': None, 'notes': 'Test job',
            'job_link': 'https://example.com'
        },
        {
            'id': 2, 'title': 'Backend Developer', 'company': 'TechCo',
            'location': 'Remoto', 'salary': '$ 300,000',
            'status': 'interviewing', 'excitement': 5,
            'date_saved': '2025-11-03 09:00:00', 'date_applied': '2025-11-04',
            'deadline': None, 'follow_up': None, 'notes': None,
            'job_link': 'https://example2.com'
        },
        {
            'id': 3, 'title': 'Frontend Developer', 'company': 'StartupX',
            'location': 'CABA', 'salary': None,
            'status': 'bookmarked', 'excitement': 3,
            'date_saved': '2025-11-05 08:00:00', 'date_applied': None,
            'deadline': None, 'follow_up': None, 'notes': None, 'job_link': None
        },
    ]


@pytest.fixture(scope='session')
def app():
    """
    Crea la app FastAPI en modo testing.
    Override de db_manager ANTES de importar main para que todos los routers
    bindeen el mock (patrón idéntico al que usaba el viejo conftest de Flask).
    """
    mock_jobs = _make_mock_jobs()

    mock_db = mock.MagicMock()
    mock_db.get_all_tracked_jobs.return_value = mock_jobs
    mock_db.get_tracked_job_by_id.side_effect = lambda jid: next(
        (j for j in mock_jobs if j['id'] == jid), None)
    mock_db.add_job_to_tracker.return_value = 99
    mock_db.update_job_status.return_value = True
    mock_db.delete_tracked_job.return_value = True
    mock_db.get_applications.return_value = mock_jobs
    mock_db.create_job_tracker_table.return_value = True
    mock_db.get_companies_for_connections.return_value = []
    mock_db.exclude_company.return_value = True
    mock_db.save_application.return_value = 1
    mock_db.save_processed_file.return_value = True

    import db_config
    db_config.db_manager = mock_db

    import main
    # Reforzar por si algún módulo bindeó antes del patch
    import core.state
    core.state.db_manager = mock_db

    from fastapi.testclient import TestClient
    client = TestClient(main.app, raise_server_exceptions=False)

    # Crear usuario de test e iniciar sesión (la app exige login)
    from models import SessionLocal, User, Base, engine
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        existing = session.query(User).filter_by(username="tester").first()
        if not existing:
            from routers.auth import hash_password
            session.add(User(username="tester", password_hash=hash_password("secret123")))
            session.commit()

    client.post("/login",
                data={"username": "tester", "password": "secret123"},
                follow_redirects=False)

    return client


@pytest.fixture
def client(app):
    """Cliente HTTP de prueba."""
    return app


@pytest.fixture
def mock_db(app):
    """Acceso directo al mock del DatabaseManager."""
    import db_config
    return db_config.db_manager
