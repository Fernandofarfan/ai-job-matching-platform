"""E2E con Chromium (Playwright) contra la app levantada: login, subida de CV y tracker."""
import glob
import os
import uuid

from tests_integration.conftest import ROOT

CV = (
    "Ana Pérez\nana.perez@example.com\n+54 11 5555-0000\n\n"
    "Data Engineer con 4 años de experiencia.\n"
    "Habilidades: Python, SQL, Airflow, Spark, Docker, AWS.\n"
)


def _login(page, password=None):
    """Inicia sesión desde /login con la contraseña dada (por defecto la correcta)."""
    page.goto('/login')
    page.fill('#password', password or page.app_password)
    page.click('button[type=submit]')


def test_login_required_and_wrong_password(page):
    """Sin sesión redirige a /login y una contraseña incorrecta no entra."""
    page.goto('/tracker')
    assert '/login' in page.url
    _login(page, 'incorrecta')
    assert '/login' in page.url


def test_upload_resume_creates_profile(page, tmp_path):
    """Subir un CV desde /profile crea el perfil del rol elegido."""
    cv = tmp_path / 'cv_ana.txt'
    cv.write_text(CV, encoding='utf-8')
    _login(page)
    page.goto('/profile')
    page.select_option('#role_type', 'data_engineer')
    page.set_input_files('#resume', str(cv))
    page.click('#submitBtn')
    page.wait_for_load_state('networkidle')
    assert '/profile' in page.url
    assert page.get_by_text('uploaded successfully').count() or page.get_by_text('subido').count()
    saved = max(glob.glob(os.path.join(ROOT, 'uploads', '*_cv_ana.txt')), key=os.path.getmtime)
    assert 'Ana' not in open(saved, 'rb').read().decode('latin-1'), 'el CV quedó sin cifrar en disco'


def test_tracker_add_job(page):
    """Agregar un empleo a mano en el tracker lo guarda y sigue tras recargar."""
    title = f'Data Engineer E2E {uuid.uuid4().hex[:6]}'
    _login(page)
    page.goto('/tracker')
    page.click('[data-bs-target="#addJobModal"]')
    page.fill('#addJobForm [name=title]', title)
    page.fill('#addJobForm [name=company]', 'Globant')
    with page.expect_response(lambda r: r.url.endswith('/api/tracker/job') and r.request.method == 'POST') as resp:
        page.click('#addJobModal .modal-footer .btn-primary')
    assert resp.value.ok, resp.value.text()
    page.get_by_text(title).first.wait_for()
    page.reload()
    page.get_by_text(title).first.wait_for()


def test_pages_load_without_console_errors(page):
    """Las páginas principales cargan sin recursos 404 y el service worker se registra."""
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    _login(page)
    for path in ('/', '/profile', '/tracker', '/alerts'):
        page.goto(path)
        page.wait_for_load_state('networkidle')
    registered = False
    for _ in range(20):
        registered = page.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r)")
        if registered:
            break
        page.wait_for_timeout(250)
    assert registered
    assert errors == [], errors
