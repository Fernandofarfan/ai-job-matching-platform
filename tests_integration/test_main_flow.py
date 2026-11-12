"""E2E del recorrido completo con Chromium: registro, CV, resultados de una búsqueda, tracker, exportar y salir.

La búsqueda real contra los portales no corre acá (cambian y bloquean); el CSV de resultados tiene el formato que
escriben los scrapers, que tienen sus propios tests con HTML guardado (test_playwright_scrapers.py).
"""
import csv
import io
import os
import secrets
import uuid

from tests_integration.conftest import ROOT
from tests_integration.test_e2e import CV


def _seed_results(user_id: int, title: str) -> str:
    """CSV de resultados como los que deja una búsqueda, en la carpeta de la cuenta."""
    folder = os.path.join(ROOT, 'results', f'u{user_id}')
    os.makedirs(folder, exist_ok=True)
    name = f'e2e_{uuid.uuid4().hex[:8]}.csv'
    with open(os.path.join(folder, name), 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, ['Title', 'Company', 'Location', 'Job_Link', 'overall_match'])
        writer.writeheader()
        writer.writerow({'Title': title, 'Company': 'Mercado Libre', 'Location': 'Buenos Aires',
                         'Job_Link': 'https://example.com/jobs/1', 'overall_match': 87})
        writer.writerow({'Title': 'Frontend Developer', 'Company': 'Globant', 'Location': 'Remoto',
                         'Job_Link': 'https://example.com/jobs/2', 'overall_match': 41})
    return name


def test_signup_to_export(browser, live_server, credentials, tmp_path):
    """Con la cuenta de administración ya creada (`credentials`), una cuenta nueva se registra, sube su CV, guarda una oferta de sus resultados, la ve en el tracker,
    la exporta a Excel y, al salir, el tracker vuelve a pedir login."""
    import accounts
    from openpyxl import load_workbook

    context = browser.new_context(base_url=live_server, reduced_motion='reduce', accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(20000)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    email, password = f'flow-{secrets.token_hex(4)}@example.com', secrets.token_urlsafe(16)

    page.goto('/register')
    page.fill('#email', email)
    page.fill('#password', password)
    page.fill('#confirm', password)
    page.check('#accept_terms')
    page.click('button[type=submit]')
    page.wait_for_load_state('networkidle')
    assert '/register' not in page.url and '/login' not in page.url, page.locator('.alert').all_inner_texts()
    user_id = accounts.find_user_id(email)
    assert user_id

    cv = tmp_path / 'cv_flow.txt'
    cv.write_text(CV, encoding='utf-8')
    page.goto('/profile')
    page.select_option('#role_type', 'data_engineer')
    page.set_input_files('#resume', str(cv))
    page.click('#submitBtn')
    page.wait_for_load_state('networkidle')
    assert '/profile' in page.url

    title = f'Data Engineer Flow {uuid.uuid4().hex[:6]}'
    filename = _seed_results(user_id, title)
    page.goto('/results')
    page.click(f'a[href="/view/{filename}"]')
    page.get_by_text(title).first.wait_for()
    with page.expect_response(lambda r: r.url.endswith('/api/job_feedback')) as resp:
        page.click('#feedback_no_1')
    assert resp.value.ok and resp.value.json()['success'], resp.value.text()
    page.reload()
    page.get_by_text(title).first.wait_for()
    assert page.get_attribute('#feedback_no_1', 'aria-pressed') == 'true', '"no me interesa" no quedó guardado'
    assert page.get_attribute('#feedback_yes_0', 'aria-pressed') == 'false'
    page.check('#applied_0')
    with page.expect_response(lambda r: r.url.endswith('/api/save_applications')) as resp:
        page.click('[data-onclick="saveApplicationStatus"]')
    body = resp.value.json()
    assert resp.value.ok and body['success'] and body['saved'] == 1, body
    page.locator('#successModal').wait_for(state='visible')

    page.goto('/tracker')
    page.get_by_text(title).first.wait_for()
    with page.expect_download() as download:
        page.click('#btn-tracker-excel')
    path = download.value.path()
    sheet = load_workbook(io.BytesIO(open(path, 'rb').read())).active
    cells = [str(c) for row in sheet.iter_rows(values_only=True) for c in row if c is not None]
    assert title in cells
    assert not any('Frontend Developer' in c for c in cells), 'se exportó una oferta que no se guardó'

    page.click('form[action="/logout"] button[type=submit]')
    page.wait_for_load_state('networkidle')
    page.goto('/tracker')
    assert '/login' in page.url
    assert not errors, errors
    context.close()
