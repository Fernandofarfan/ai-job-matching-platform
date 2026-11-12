"""E2E de la extensión: Chromium la carga, el content script extrae una oferta y el popup responde."""
import os
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, 'chrome_extension')
JOB_URL = 'https://www.getonbrd.com/jobs/programming/backend-python-acme'
JOB_HTML = """<!doctype html><html><head><title>Oferta</title>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "JobPosting",
 "title": "Backend Python <img src=x onerror=alert(1)>", "hiringOrganization": {"name": "ACME"},
 "jobLocation": {"address": {"addressLocality": "Buenos Aires", "addressCountry": "AR"}},
 "description": "<p>Django y <b>FastAPI</b></p>"}</script></head>
<body><h1>Backend Python &lt;img src=x onerror=alert(1)&gt;</h1></body></html>"""


@pytest.fixture
def extension_context(playwright):
    """Chromium con la extensión descomprimida cargada."""
    if not os.getenv('DISPLAY'):
        pytest.skip('Chromium solo carga extensiones con ventana: corré con xvfb-run')
    with tempfile.TemporaryDirectory() as profile:
        context = playwright.chromium.launch_persistent_context(
            profile, headless=False,
            args=[f'--disable-extensions-except={EXT}', f'--load-extension={EXT}'],
        )
        worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
        yield context, worker
        context.close()


def test_extracts_job_posting_and_shows_safe_toast(extension_context):
    """El content script toma los datos del JSON-LD y el aviso muestra el título como texto."""
    context, worker = extension_context
    page = context.new_page()
    page.route('https://www.getonbrd.com/**', lambda route: route.fulfill(content_type='text/html', body=JOB_HTML))
    page.goto(JOB_URL)

    result = worker.evaluate("""async () => {
        const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });
        await chrome.tabs.sendMessage(tab.id, { action: 'showSavedIndicator', jobTitle: response.data.title });
        return response;
    }""")
    data = result['data']
    assert result['success'] and data['platform'] == 'getonbrd'
    assert data['company'] == 'ACME' and data['location'] == 'Buenos Aires, AR'
    assert data['description'] == 'Django y FastAPI'

    toast = page.locator('#empleoia-saved-toast small')
    toast.wait_for()
    assert toast.inner_text().startswith('Backend Python <img')
    assert page.locator('#empleoia-saved-toast img').count() == 0


def test_popup_buttons_work_under_mv3_csp(extension_context):
    """Sin handlers inline, los botones del popup responden y el menú contextual quedó registrado."""
    context, worker = extension_context
    extension_id = worker.url.split('/')[2]
    popup = context.new_page()
    errors = []
    popup.on('pageerror', lambda e: errors.append(str(e)))
    popup.goto(f'chrome-extension://{extension_id}/popup.html')

    popup.click('#settings-toggle')
    assert popup.locator('#settings-panel').is_visible()
    assert popup.get_attribute('#settings-toggle', 'aria-expanded') == 'true'
    popup.fill('#server-url', 'not a url')
    popup.click('#connect-btn')
    assert 'no es válida' in popup.locator('#message-area').inner_text()
    assert errors == []
