"""Tests del JavaScript del navegador (static/js) en Chromium, sin levantar la app.

Cada test sirve una página mínima desde https://app.test con los scripts reales de static/js y responde
las APIs con datos fijos; las APIs del navegador que no hay en headless (passkeys, push) se reemplazan
con dobles en `add_init_script`.
"""
import json
import os
from urllib.parse import urlparse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = 'https://app.test'


class FakeApp:
    """Páginas y respuestas de API para un contexto de Chromium; guarda los pedidos a las APIs."""

    def __init__(self, context):
        self.pages = {}
        self.api = {}
        self.requests = []
        context.route(f'{ORIGIN}/**', self._handle)

    def page(self, path, body, scripts, head=''):
        tags = ''.join(f'<script src="/static/js/{name}"></script>' for name in scripts)
        self.pages[path] = f'<!doctype html><html><head>{head}</head><body>{body}{tags}</body></html>'

    def calls(self, method, path):
        return [r for r in self.requests if r['method'] == method and r['path'] == path]

    def _handle(self, route):
        request = route.request
        path = urlparse(request.url).path
        if path.startswith('/static/'):
            route.fulfill(path=os.path.join(ROOT, path.lstrip('/')), content_type='application/javascript; charset=utf-8')
            return
        if path in self.pages:
            route.fulfill(content_type='text/html; charset=utf-8', body=self.pages[path])
            return
        self.requests.append({'method': request.method, 'path': path, 'headers': request.headers,
                              'body': json.loads(request.post_data) if request.post_data else None})
        status, body = self.api.get((request.method, path), (404, {'error': 'No existe'}))
        route.fulfill(status=status, json=body)


@pytest.fixture
def context(browser):
    context = browser.new_context(base_url=ORIGIN, service_workers='block')
    yield context
    context.close()


@pytest.fixture
def app(context):
    return FakeApp(context)


@pytest.fixture
def page(context):
    page = context.new_page()
    page.set_default_timeout(10000)
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    yield page
    assert page.errors == []


# ── actions.js ────────────────────────────────────────────────

ACTIONS_GLOBALS = """<script>
window.calls = [];
window.record = function (...args) {
  window.calls.push(args.map((a) => (a instanceof Element ? 'el:' + a.id : a instanceof Event ? 'ev:' + a.type : a)));
  return this.dataset.keep !== undefined;
};
</script>"""


def test_actions_call_global_with_args_and_cancel_default(app, page):
    app.page('/', ACTIONS_GLOBALS + """
      <a id="link" href="#moved" data-onclick="record" data-args='["x", "$el", "$event", 3]'>ir</a>
      <a id="keep" href="#kept" data-keep data-onclick="record">seguir</a>
      <select id="sel" data-onchange="record" data-onchange-args='["cambio"]' data-onclick="record"
              data-onclick-args='["clic"]'><option>a</option><option>b</option></select>""", ['actions.js'])
    page.goto('/')
    page.click('#link')
    assert page.evaluate('location.hash') == ''
    page.click('#keep')
    assert page.evaluate('location.hash') == '#kept'
    page.select_option('#sel', 'b')
    assert page.evaluate('calls') == [['x', 'el:link', 'ev:click', 3], [], ['cambio']]


def test_actions_ignore_invalid_args_and_unknown_functions(app, page):
    app.page('/', ACTIONS_GLOBALS + """
      <button id="bad" data-onclick="record" data-args="{no es json">a</button>
      <button id="missing" data-onclick="noExiste">b</button>
      <button id="single" data-onclick="record" data-args='"solo"'>c</button>""", ['actions.js'])
    page.goto('/')
    with page.expect_console_message(lambda m: 'data-args inválido' in m.text) as warning:
        page.click('#bad')
    assert warning.value.type == 'warning'
    page.click('#missing')
    page.click('#single')
    assert page.evaluate('calls') == [['solo']]


def test_actions_confirm_blocks_form_and_link_when_dismissed(app, page):
    app.page('/', """
      <form id="f" action="/sent" method="get" data-confirm="¿Borrar?"><button id="send">Borrar</button></form>
      <a id="del" href="/sent" data-confirm="¿Seguro?">Borrar</a>""", ['actions.js'])
    app.page('/sent', '<p>ok</p>', [])
    page.goto('/')
    dialogs = []
    page.once('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))
    page.click('#send')
    page.once('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))
    page.click('#del')
    assert urlparse(page.url).path == '/'
    page.once('dialog', lambda d: d.accept())
    with page.expect_navigation(url='**/sent'):
        page.click('#del')
    assert dialogs == ['¿Borrar?', '¿Seguro?']


# ── passkeys.js ───────────────────────────────────────────────

PASSKEY_FORM = """
  <input type="hidden" name="csrf_token" value="tok123">
  <form id="passkeyForm" action="/account/passkeys" data-options-url="/account/passkeys/options"
        data-unsupported="No soportado" data-cancelled="Cancelado" data-failed="Falló">
    <input name="name" value="Mi laptop"><input name="password" value="clave">
    <button id="add" type="submit">Agregar</button>
  </form>
  <div id="passkeyStatus" class="d-none"></div>"""

PASSKEY_LOGIN = """
  <button id="passkeyLogin" data-options-url="/login/passkey/options" data-login-url="/login/passkey"
          data-next="/tracker" data-cancelled="Cancelado" data-failed="Falló">Entrar con una passkey</button>
  <div id="passkeyLoginStatus" class="d-none"></div>"""

# Autenticador falso: guarda las opciones que recibe (bytes como listas) y devuelve buffers conocidos
FAKE_CREDENTIALS = """
(() => {
  const buf = (bytes) => new Uint8Array(bytes).buffer;
  const list = (v) => Array.from(new Uint8Array(v));
  window.passkeyCalls = [];
  const fail = () => { const name = localStorage.getItem('passkey-error'); if (name) throw new DOMException('x', name); };
  const base = { id: 'cred-1', rawId: buf([251, 255, 0]), type: 'public-key', authenticatorAttachment: 'platform',
                 getClientExtensionResults: () => ({}) };
  Object.defineProperty(navigator, 'credentials', { configurable: true, value: {
    async create({ publicKey }) {
      fail();
      window.passkeyCalls.push({ challenge: list(publicKey.challenge), user: list(publicKey.user.id),
                                 exclude: publicKey.excludeCredentials.map((c) => list(c.id)) });
      return { ...base, response: { clientDataJSON: buf([1, 2, 3]), attestationObject: buf([4, 5]),
                                    getTransports: () => ['internal'] } };
    },
    async get({ publicKey }) {
      fail();
      window.passkeyCalls.push({ challenge: list(publicKey.challenge), allow: publicKey.allowCredentials.map((c) => list(c.id)) });
      return { ...base, response: { clientDataJSON: buf([1]), authenticatorData: buf([2]), signature: buf([3]), userHandle: null } };
    },
  } });
})();
"""


def test_passkey_register_converts_base64url_and_sends_csrf(app, page):
    page.add_init_script(FAKE_CREDENTIALS)
    app.page('/account', PASSKEY_FORM, ['passkeys.js'])
    app.api[('POST', '/account/passkeys/options')] = (200, {
        'challenge': '-_8', 'user': {'id': 'AQI'}, 'excludeCredentials': [{'id': 'BAU', 'type': 'public-key'}]})
    app.api[('POST', '/account/passkeys')] = (200, {'success': True})
    page.goto('/account')
    with page.expect_navigation():
        page.click('#add')
    assert page.evaluate('passkeyCalls') == []  # la página se recargó
    options, register = app.calls('POST', '/account/passkeys/options'), app.calls('POST', '/account/passkeys')
    assert options[0]['body'] == {'password': 'clave'} and options[0]['headers']['x-csrftoken'] == 'tok123'
    sent = register[0]['body']
    assert sent['name'] == 'Mi laptop'
    assert sent['credential']['rawId'] == '-_8A'
    assert sent['credential']['response'] == {'clientDataJSON': 'AQID', 'attestationObject': 'BAU',
                                              'transports': ['internal']}


def test_passkey_register_passes_decoded_options_to_authenticator(app, page):
    page.add_init_script(FAKE_CREDENTIALS)
    app.page('/account', PASSKEY_FORM, ['passkeys.js'])
    app.api[('POST', '/account/passkeys/options')] = (200, {
        'challenge': '-_8', 'user': {'id': 'AQI'}, 'excludeCredentials': [{'id': 'BAU', 'type': 'public-key'}]})
    app.api[('POST', '/account/passkeys')] = (400, {'error': 'La passkey ya existe'})
    page.goto('/account')
    page.click('#add')
    page.wait_for_selector('#passkeyStatus:not(.d-none)')
    assert page.evaluate('passkeyCalls') == [{'challenge': [251, 255], 'user': [1, 2], 'exclude': [[4, 5]]}]
    assert page.inner_text('#passkeyStatus') == 'La passkey ya existe'


def test_passkey_cancelled_and_unsupported_messages(app, page, context):
    page.add_init_script(FAKE_CREDENTIALS)
    page.add_init_script("localStorage.setItem('passkey-error', 'NotAllowedError')")
    app.page('/account', PASSKEY_FORM, ['passkeys.js'])
    app.api[('POST', '/account/passkeys/options')] = (200, {'challenge': 'AA', 'user': {'id': 'AA'}})
    page.goto('/account')
    page.click('#add')
    page.wait_for_selector('#passkeyStatus:not(.d-none)')
    assert page.inner_text('#passkeyStatus') == 'Cancelado'

    other = context.new_page()
    other.add_init_script('delete window.PublicKeyCredential')
    app.page('/login', PASSKEY_LOGIN, ['passkeys.js'])
    other.goto('/account')
    hidden = "(sel) => document.querySelector(sel).classList.contains('d-none')"
    assert other.evaluate(hidden, '#passkeyForm') and other.inner_text('#passkeyStatus') == 'No soportado'
    other.goto('/login')
    assert other.evaluate(hidden, '#passkeyLogin')


def test_passkey_login_posts_assertion_and_follows_redirect(app, page):
    page.add_init_script(FAKE_CREDENTIALS)
    app.page('/login', PASSKEY_LOGIN, ['passkeys.js'])
    app.page('/tracker', '<p>tracker</p>', [])
    app.api[('POST', '/login/passkey/options')] = (200, {'challenge': '-_8', 'allowCredentials': [{'id': 'AQI'}]})
    app.api[('POST', '/login/passkey')] = (200, {'redirect': '/tracker'})
    page.goto('/login')
    with page.expect_navigation(url='**/tracker'):
        page.click('#passkeyLogin')
    sent = app.calls('POST', '/login/passkey')[0]['body']
    assert sent['next'] == '/tracker'
    assert sent['credential']['response'] == {'clientDataJSON': 'AQ', 'authenticatorData': 'Ag', 'signature': 'Aw',
                                              'userHandle': None}


def test_passkey_login_shows_server_error(app, page):
    page.add_init_script(FAKE_CREDENTIALS)
    app.page('/login', PASSKEY_LOGIN, ['passkeys.js'])
    app.api[('POST', '/login/passkey/options')] = (429, {'error': 'Demasiados intentos'})
    page.goto('/login')
    page.click('#passkeyLogin')
    page.wait_for_selector('#passkeyLoginStatus:not(.d-none)')
    assert page.inner_text('#passkeyLoginStatus') == 'Demasiados intentos'


# ── push.js ───────────────────────────────────────────────────

# Service worker, PushManager y Notification falsos; window.push guarda lo que hizo la página
FAKE_PUSH = """
(() => {
  const saved = JSON.parse(localStorage.getItem('push-setup') || '{}');
  const state = window.push = { unsubscribed: [], subscribeKey: null, permission: saved.permission || 'default' };
  const make = (endpoint) => ({ endpoint, toJSON: () => ({ endpoint, keys: { p256dh: 'k', auth: 'a' } }),
                                unsubscribe: async () => { state.unsubscribed.push(endpoint); return true; } });
  let current = saved.subscribed ? make(saved.subscribed) : null;
  const registration = { pushManager: {
    getSubscription: async () => current,
    subscribe: async ({ applicationServerKey }) => {
      state.subscribeKey = Array.from(new Uint8Array(applicationServerKey));
      current = make('https://fcm.googleapis.com/fcm/send/new');
      return current;
    },
  } };
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
    register: async () => registration, ready: Promise.resolve(registration), getRegistration: async () => registration } });
  window.PushManager = function () {};
  window.Notification = { get permission() { return state.permission; },
                          requestPermission: async () => (state.permission = saved.grant || 'denied') };
})();
"""

PUSH_HEAD = '<meta name="push-account" content="yo@example.com">'
PUSH_BOX = """<div id="push-box"><p id="push-status"></p>
  <button id="push-enable" hidden>Activar</button><button id="push-test" hidden>Probar</button>
  <button id="push-disable" hidden>Desactivar</button></div>"""


def _push_page(page, setup=None, owner=None):
    page.add_init_script(f"""
      if (!sessionStorage.getItem('push-ready')) {{
        sessionStorage.setItem('push-ready', '1');
        localStorage.setItem('push-setup', {json.dumps(json.dumps(setup or {}))});
        {f"localStorage.setItem('empleoia-push-account', {json.dumps(owner)});" if owner else ''}
      }}""")
    page.add_init_script(FAKE_PUSH)


def _visible(page):
    return [b for b in ('push-enable', 'push-test', 'push-disable') if page.is_visible(f'#{b}')]


def test_push_enable_subscribes_with_vapid_key(app, page):
    _push_page(page, {'grant': 'granted'})
    app.page('/account', PUSH_BOX, ['push.js'], PUSH_HEAD)
    app.api[('GET', '/api/push/config')] = (200, {'enabled': True, 'public_key': 'AQID'})
    app.api[('POST', '/api/push/subscribe')] = (200, {'success': True})
    page.goto('/account')
    page.wait_for_selector('#push-enable:visible')
    page.click('#push-enable')
    page.wait_for_selector('#push-test:visible')
    assert page.evaluate('push.subscribeKey') == [1, 2, 3]
    assert app.calls('POST', '/api/push/subscribe')[0]['body']['endpoint'] == 'https://fcm.googleapis.com/fcm/send/new'
    assert page.evaluate("localStorage.getItem('empleoia-push-account')") == 'yo@example.com'
    assert _visible(page) == ['push-test', 'push-disable']


def test_push_permission_denied_and_not_configured(app, page, context):
    _push_page(page, {'grant': 'denied'})
    app.page('/account', PUSH_BOX, ['push.js'], PUSH_HEAD)
    app.api[('GET', '/api/push/config')] = (200, {'enabled': True, 'public_key': 'AQID'})
    page.goto('/account')
    page.click('#push-enable')
    page.wait_for_function("document.getElementById('push-status').textContent.startsWith('Bloqueaste')")
    assert _visible(page) == [] and app.calls('POST', '/api/push/subscribe') == []

    app.api[('GET', '/api/push/config')] = (200, {'enabled': False})
    page.reload()
    page.wait_for_function("document.getElementById('push-status').textContent.includes('VAPID_PUBLIC_KEY')")


def test_push_unsupported_browser(app, page):
    page.add_init_script('delete window.PushManager')
    app.page('/account', PUSH_BOX, ['push.js'], PUSH_HEAD)
    page.goto('/account')
    assert 'no admite' in page.inner_text('#push-status')
    assert app.requests == []


def test_push_disable_unsubscribes(app, page):
    endpoint = 'https://fcm.googleapis.com/fcm/send/old'
    _push_page(page, {'subscribed': endpoint, 'permission': 'granted'}, owner='yo@example.com')
    app.page('/account', PUSH_BOX, ['push.js'], PUSH_HEAD)
    app.api[('GET', '/api/push/config')] = (200, {'enabled': True, 'public_key': 'AQID'})
    app.api[('POST', '/api/push/unsubscribe')] = (200, {'success': True})
    page.goto('/account')
    page.wait_for_selector('#push-disable:visible')
    page.click('#push-disable')
    page.wait_for_selector('#push-enable:visible')
    assert app.calls('POST', '/api/push/unsubscribe')[0]['body'] == {'endpoint': endpoint}
    assert page.evaluate('push.unsubscribed') == [endpoint]
    assert page.evaluate("localStorage.getItem('empleoia-push-account')") is None


@pytest.mark.parametrize('owner, dropped', [('otra@example.com', True), ('yo@example.com', False)])
def test_push_drops_subscription_of_another_account(app, page, owner, dropped):
    endpoint = 'https://fcm.googleapis.com/fcm/send/old'
    _push_page(page, {'subscribed': endpoint, 'permission': 'granted'}, owner=owner)
    app.page('/', '<p>inicio</p>', ['push.js'], PUSH_HEAD)
    page.goto('/')
    page.wait_for_timeout(300)
    assert page.evaluate('push.unsubscribed') == ([endpoint] if dropped else [])
    assert page.evaluate("localStorage.getItem('empleoia-push-account')") == (None if dropped else owner)


def test_push_logout_unsubscribes_before_submitting(app, page):
    endpoint = 'https://fcm.googleapis.com/fcm/send/old'
    _push_page(page, {'subscribed': endpoint, 'permission': 'granted'}, owner='yo@example.com')
    app.page('/', '<form action="/logout" method="post"><button id="out">Salir</button></form>', ['push.js'], PUSH_HEAD)
    app.page('/logout', '<p>chau</p>', [])
    app.api[('POST', '/api/push/unsubscribe')] = (200, {'success': True})
    page.goto('/')
    with page.expect_navigation(url='**/logout'):
        page.click('#out')
    assert app.calls('POST', '/api/push/unsubscribe')[0]['body'] == {'endpoint': endpoint}
    assert page.evaluate("localStorage.getItem('empleoia-push-account')") is None


# ── offline-cache.js ──────────────────────────────────────────

OFFLINE_BODY = '<div id="network-indicator"></div><main>contenido</main>'


def _cached(page):
    return page.evaluate("OfflineCache.getAllFromStore(OfflineCache.STORES.tracker).then((jobs) => jobs.map((j) => j.id))")


def test_offline_cache_keeps_only_current_tracker_jobs(app, page):
    app.page('/', OFFLINE_BODY, ['offline-cache.js'])
    app.api[('GET', '/api/tracker/jobs')] = (200, {'success': True, 'jobs': [{'id': 1}, {'id': 2}]})
    page.goto('/')
    page.wait_for_function("OfflineCache.getAllFromStore(OfflineCache.STORES.tracker).then((j) => j.length === 2)")
    assert 'Online' in page.inner_text('#network-indicator')

    app.api[('GET', '/api/tracker/jobs')] = (200, {'success': True, 'jobs': [{'id': 2}]})
    assert page.evaluate('OfflineCache.syncTrackerData().then((jobs) => jobs.length)') == 1
    assert _cached(page) == [2]

    app.api[('GET', '/api/tracker/jobs')] = (500, {'error': 'caído'})
    assert page.evaluate('OfflineCache.syncTrackerData().then((jobs) => jobs.map((j) => j.id))') == [2]


def test_offline_banner_follows_connection(app, page, context):
    app.page('/', OFFLINE_BODY, ['offline-cache.js'])
    app.api[('GET', '/api/tracker/jobs')] = (200, {'success': True, 'jobs': []})
    page.goto('/')
    context.set_offline(True)
    page.wait_for_selector('#offline-banner', state='attached')
    assert 'Offline' in page.inner_text('#network-indicator')
    page.click('[data-close-offline-banner]')
    assert page.query_selector('#offline-banner') is None

    context.set_offline(True)
    context.set_offline(False)
    page.wait_for_function("document.getElementById('network-indicator').textContent.includes('Online')")
    assert page.query_selector('#offline-banner') is None


# ── document_batch.js ─────────────────────────────────────────

def test_document_batch_returns_sync_result_or_polls_task(app, page):
    app.page('/', '<table><tbody id="rows"></tbody></table>', ['document_batch.js'])
    app.api[('POST', '/api/batch_cover_letters')] = (200, {'success': True, 'results': []})
    page.goto('/')
    assert page.evaluate("runDocumentBatch('/api/batch_cover_letters', {n: 1}, () => {})") == {'success': True, 'results': []}
    assert app.calls('POST', '/api/batch_cover_letters')[0]['body'] == {'n': 1}

    app.api[('POST', '/api/batch_optimize')] = (202, {'task_id': 'a/b'})
    app.api[('GET', '/api/documents/tasks/a/b')] = (404, {})
    app.api[('GET', '/api/documents/tasks/a%2Fb')] = (200, {'state': 'completed', 'results': [{'status': 'success'}]})
    page.clock.install()
    result = page.evaluate_handle("""() => {
      window.progress = [];
      window.batch = runDocumentBatch('/api/batch_optimize', {}, (p, m) => window.progress.push([p, m]));
      return true;
    }""")
    result.dispose()
    page.clock.run_for(2500)
    assert page.evaluate('batch') == {'state': 'completed', 'results': [{'status': 'success'}]}


def test_document_batch_reports_progress_and_failure(app, page):
    app.page('/', '', ['document_batch.js'])
    app.api[('POST', '/api/batch_optimize')] = (202, {'task_id': 't1'})
    app.api[('GET', '/api/documents/tasks/t1')] = (200, {'state': 'queued'})
    page.goto('/')
    page.clock.install()
    page.evaluate("""() => {
      window.progress = [];
      window.batch = runDocumentBatch('/api/batch_optimize', {}, (p, m) => window.progress.push([p, m]))
        .catch((e) => 'error: ' + e.message);
    }""")
    page.clock.run_for(2500)
    page.wait_for_function('progress.length === 1')
    app.api[('GET', '/api/documents/tasks/t1')] = (200, {'state': 'failed', 'error': 'Sin cuota de IA'})
    page.clock.run_for(2500)
    assert page.evaluate('batch') == 'error: Sin cuota de IA'
    assert page.evaluate('progress') == [[0, 'En cola...']]

    app.api[('POST', '/api/batch_cover_letters')] = (400, {'error': 'Elegí un archivo'})
    assert page.evaluate("runDocumentBatch('/api/batch_cover_letters', {}, () => {}).catch((e) => e.message)") == 'Elegí un archivo'


def test_document_rows_render_text_not_html(app, page):
    app.page('/', '<table><tbody id="rows"><tr><td>viejo</td></tr></tbody></table>', ['document_batch.js'])
    page.goto('/')
    page.evaluate("""renderDocumentRows(document.getElementById('rows'), [
      {status: 'success', job_title: '<img src=x onerror="window.pwned=1">', company: 'ACME & Co', filename: 'cv a/b.pdf'},
      {status: 'error', job_title: 'Dev', company: 'X', error: 'Sin cuota'},
      {status: 'error', job_title: 'QA', company: 'Y'},
    ])""")
    rows = page.locator('#rows tr')
    assert rows.count() == 3
    assert page.locator('#rows img').count() == 0 and page.evaluate('window.pwned') is None
    assert rows.nth(0).locator('td').nth(0).inner_text() == '<img src=x onerror="window.pwned=1">'
    assert rows.nth(0).locator('a').get_attribute('href') == '/download_resume/cv%20a%2Fb.pdf'
    assert rows.nth(1).locator('td').nth(3).inner_text() == 'Sin cuota'
    assert rows.nth(2).locator('td').nth(3).inner_text() == 'Fallido'
    assert rows.nth(0).locator('.badge').inner_text() == 'Éxito'


# ── todos los archivos ────────────────────────────────────────

@pytest.mark.parametrize('name', sorted(os.path.relpath(os.path.join(d, f), os.path.join(ROOT, 'static', 'js'))
                                        for d, _, files in os.walk(os.path.join(ROOT, 'static', 'js'))
                                        for f in files if f.endswith('.js')))
def test_static_js_parses(app, page, name):
    """Un error de sintaxis en cualquier archivo de static/js, incluidos los que no tienen tests propios, falla acá."""
    app.page('/', '', [])
    page.goto('/')
    source = open(os.path.join(ROOT, 'static', 'js', name), encoding='utf-8').read()
    assert page.evaluate('(src) => { try { new Function(src); return null; } catch (e) { return String(e); } }', source) is None
