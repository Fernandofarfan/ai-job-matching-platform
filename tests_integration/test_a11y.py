"""Accesibilidad con axe-core (WCAG 2.x A/AA) sobre las páginas principales, con sesión iniciada."""
import pytest

from tests_integration.test_e2e import _login

AXE_URL = 'https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js'
PAGES = ['/', '/scraper', '/results', '/profile', '/view_profile', '/mock-interview', '/tracker', '/analytics',
         '/alerts', '/optimize_resume', '/batch_cover_letters', '/batch_optimize', '/connections', '/account',
         '/admin', '/no-existe']
PUBLIC_PAGES = ['/login', '/forgot_password', '/terms', '/privacy']
BLOCKING = {'serious', 'critical'}


def _violations(page):
    """Violaciones serias o críticas de axe en la página actual."""
    page.add_script_tag(url=AXE_URL)
    result = page.evaluate("axe.run(document, {runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']})")
    return [
        f"{v['id']} ({v['impact']}) {n['target']}: {(n['any'] or n['all'] or n['none'] or [{}])[0].get('message', v['help'])}"
        for v in result['violations'] if v['impact'] in BLOCKING for n in v['nodes'][:3]
    ]


@pytest.mark.parametrize('path', PUBLIC_PAGES)
def test_public_pages_are_accessible(page, path):
    """Las pantallas sin sesión no tienen violaciones serias de accesibilidad."""
    page.goto(path)
    assert _violations(page) == []


@pytest.fixture(scope='module')
def authed_page(browser, live_server, credentials):
    """Una sola sesión iniciada para todas las páginas (no gasta el límite de intentos de login)."""
    context = browser.new_context(base_url=live_server, reduced_motion='reduce')
    page = context.new_page()
    page.set_default_timeout(20000)
    page.credentials = credentials
    _login(page)
    yield page
    context.close()


@pytest.mark.parametrize('path', PAGES)
def test_pages_are_accessible(authed_page, path):
    """Cada página principal pasa axe sin violaciones serias ni críticas."""
    authed_page.goto(path)
    authed_page.wait_for_load_state('networkidle')
    assert _violations(authed_page) == []
