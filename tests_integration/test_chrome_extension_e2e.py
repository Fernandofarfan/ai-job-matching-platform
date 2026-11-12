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
 "description": "<p>Django y <b>FastAPI</b></p><p>Python</p>"}</script></head>
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
    assert data['description'] == 'Django y FastAPI\nPython'

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


LINK_URL = 'http://localhost:5000/account/extension/link'
STATE = 'estado-de-la-extension-123'
TOKEN = 'tok_' + 'a' * 40


def _serve_link_page(context, state=STATE, token=TOKEN):
    """La página de confirmación de la app, con el token para la extensión (sin levantar la app)."""
    body = (f'<!doctype html><title>Vincular</title><div id="empleoia-extension-link" hidden '
            f'data-state="{state}" data-token="{token}"></div>')
    context.route('http://localhost:5000/**', lambda route: route.fulfill(content_type='text/html', body=body))


def _local_token(worker, wait=True):
    return worker.evaluate("""async (wait) => {
        for (let i = 0; i < (wait ? 50 : 1); i++) {
            const { extensionToken } = await chrome.storage.local.get('extensionToken');
            if (extensionToken) return extensionToken;
            await new Promise(r => setTimeout(r, 100));
        }
        return null;
    }""", wait)


def test_link_stores_token_only_on_device(extension_context):
    """Con el state que generó el popup, el service worker guarda el token en storage.local y no en sync."""
    context, worker = extension_context
    worker.evaluate(f"chrome.storage.session.set({{ linkState: '{STATE}' }})")
    _serve_link_page(context)
    context.new_page().goto(LINK_URL)
    assert _local_token(worker) == TOKEN
    stored = worker.evaluate("""async () => ({
        sync: await chrome.storage.sync.get('extensionToken'),
        session: await chrome.storage.session.get('linkState'),
    })""")
    assert stored == {'sync': {}, 'session': {}}


def test_link_ignores_page_with_another_state(extension_context):
    """Una página con otro state (no la abrió esta extensión) no cambia el token."""
    context, worker = extension_context
    worker.evaluate(f"chrome.storage.session.set({{ linkState: '{STATE}' }})")
    _serve_link_page(context, state='otro-estado-cualquiera-456')
    page = context.new_page()
    page.goto(LINK_URL)
    page.wait_for_timeout(1000)
    assert _local_token(worker, wait=False) is None


def test_token_from_old_version_moves_out_of_sync(extension_context):
    """El token que versiones anteriores dejaban en storage.sync pasa a storage.local."""
    _context, worker = extension_context
    result = worker.evaluate("""async () => {
        await chrome.storage.sync.set({ extensionToken: 'viejo' });
        await EmpleoIALink.migrateToken(chrome.storage);
        return { sync: await chrome.storage.sync.get('extensionToken'), local: await chrome.storage.local.get('extensionToken') };
    }""")
    assert result == {'sync': {}, 'local': {'extensionToken': 'viejo'}}


def test_popup_link_button_opens_account_with_state(extension_context):
    """"Vincular con mi cuenta" abre Mi cuenta con un state nuevo, que queda guardado para comprobar la respuesta."""
    context, worker = extension_context
    extension_id = worker.url.split('/')[2]
    popup = context.new_page()
    popup.goto(f'chrome-extension://{extension_id}/popup.html')
    # el estado lo carga el popup de forma asíncrona desde storage.local
    popup.wait_for_function("document.getElementById('link-status').innerText.includes('Sin vincular')")
    # se registra la URL que abriría la pestaña: así no depende de que haya una app escuchando en el puerto
    popup.evaluate("() => { window.openedUrls = []; chrome.tabs.create = async (o) => { window.openedUrls.push(o.url); return {}; }; }")
    popup.click('#settings-toggle')
    popup.click('#link-btn')
    popup.wait_for_function('window.openedUrls.length > 0')
    url = popup.evaluate('window.openedUrls[0]')
    state = worker.evaluate("async () => (await chrome.storage.session.get('linkState')).linkState")
    assert url == f'{LINK_URL}?state={state}' and len(state) >= 32
