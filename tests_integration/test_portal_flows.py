"""Login, paginación, enlace de postulación y CSV de Computrabajo, Bumeran y LinkedIn, con Chromium real.

Cada pestaña intercepta todas las URLs (`page.route`), así los logins con dominio fijo tampoco salen a internet.
"""
import concurrent.futures
import csv
import types
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / 'tests' / 'fixtures'
EXTERNAL_APPLY = 'https://acme.example/apply'
NO_SLEEP = types.SimpleNamespace(sleep=lambda *_: None)


def _in_thread(fn):
    """La API sync de Playwright no anda dentro del loop asyncio de pytest-anyio: cada flujo corre en su thread."""
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(fn).result(timeout=180)


def _serve(page, pages):
    """Responde cada request con el primer (fragmento de URL, HTML) que coincide; si ninguno, 404."""
    def handler(route):
        url = route.request.url
        for fragment, body in pages:
            if fragment in url:
                return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=body)
        return route.fulfill(status=404, content_type='text/html', body='<title>404</title>Página no encontrada')
    page.route('**/*', handler)


@pytest.fixture
def results_dir(monkeypatch, tmp_path):
    import accounts
    monkeypatch.setattr(accounts, 'results_dir', lambda: str(tmp_path))
    return tmp_path


def test_computrabajo_login_pages_and_external_apply(monkeypatch, results_dir):
    from scrapers import computrabajo_scraper as ct
    monkeypatch.setattr(ct, 'time', NO_SLEEP)
    listing = (FIXTURES / 'computrabajo_listing.html').read_text(encoding='utf-8')
    per_page = len(ct.parse_listing(listing, 'https://ct.test'))
    pages = [
        ('Login.aspx', '<input id="Email"><button id="continueWithMailButton">Seguir</button><input id="password">'
                       '<button id="btnSubmitPass" onclick="location.href=\'https://ct.test/candidato\'">Entrar</button>'),
        ('/candidato', '<h1>Hola</h1>'),
        ('/trabajo-de-python?p=2', listing),
        ('/trabajo-de-python', listing.replace('</body>', '<a href="/trabajo-de-python?p=2">Siguiente</a></body>')),
        ('/ofertas-de-trabajo/', f'<a id="btnApply" href="{EXTERNAL_APPLY}">Postularme</a>'),
    ]

    def run():
        scraper = ct.ComputrabajoScraper()
        scraper.base_url = 'https://ct.test'
        _serve(scraper.page, pages)
        try:
            jobs = scraper.search_jobs('python', max_jobs=50, email='a@example.com', password='x')
            logged_in = scraper._login('a@example.com', 'x')
            return jobs, logged_in, scraper.save_to_csv(jobs, 'ct.csv')
        finally:
            scraper.close()

    jobs, logged_in, path = _in_thread(run)
    assert logged_in
    assert per_page and len(jobs) == 2 * per_page
    assert {job['Apply_URL'] for job in jobs} == {EXTERNAL_APPLY}
    with open(path, encoding='utf-8-sig') as f:
        header = next(csv.reader(f))
    assert header[:6] == ['Title', 'Company', 'Location', 'Salary', 'URL', 'Apply_URL']


def test_computrabajo_stops_at_max_jobs_and_without_next_page(monkeypatch):
    from scrapers import computrabajo_scraper as ct
    monkeypatch.setattr(ct, 'time', NO_SLEEP)
    listing = (FIXTURES / 'computrabajo_listing.html').read_text(encoding='utf-8')

    def run():
        scraper = ct.ComputrabajoScraper()
        scraper.base_url = 'https://ct.test'
        _serve(scraper.page, [('/trabajo-de-python-en-cordoba', listing)])
        try:
            return scraper.search_jobs('python', 'Cordoba', max_jobs=1), scraper.search_jobs('python', 'Cordoba')
        finally:
            scraper.close()

    one, all_jobs = _in_thread(run)
    assert len(one) == 1 and one[0]['Apply_URL'] == one[0]['URL']
    assert len(all_jobs) == len(ct.parse_listing(listing, 'https://ct.test'))


def test_bumeran_login_external_apply_and_csv(monkeypatch, results_dir):
    from scrapers import bumeran_scraper as bm
    monkeypatch.setattr(bm, 'time', NO_SLEEP)
    listing = (FIXTURES / 'bumeran_listing.html').read_text(encoding='utf-8')
    pages = [
        ('/login', '<form action="/candidato"><input id="email"><input id="password">'
                   '<button type="submit">Entrar</button></form>'),
        ('/candidato', '<h1>Hola</h1>'),
        ('/empleos-busqueda-python.html', listing),
        ('/empleos/', f'<a href="{EXTERNAL_APPLY}?postula=1">Postularme</a>'),
    ]

    def run():
        scraper = bm.BumeranScraper()
        scraper.base_url = 'https://bm.test'
        _serve(scraper.page, pages)
        try:
            jobs = scraper.search_jobs('python', max_jobs=50, email='a@example.com', password='x')
            return jobs, scraper.save_to_csv(jobs, 'bm.csv'), scraper.save_to_csv([])
        finally:
            scraper.close()

    jobs, path, empty = _in_thread(run)
    assert [job['Company'] for job in jobs] == ['TechCo', 'Confidencial']
    assert {job['Apply_URL'] for job in jobs} == {f'{EXTERNAL_APPLY}?postula=1'}
    assert Path(path).read_text(encoding='utf-8-sig').count('\n') == 3
    assert empty is None


def test_bumeran_internal_apply_keeps_the_offer_url(monkeypatch):
    from scrapers import bumeran_scraper as bm
    monkeypatch.setattr(bm, 'time', NO_SLEEP)

    def run():
        scraper = bm.BumeranScraper()
        scraper.base_url = 'https://bm.test'
        _serve(scraper.page, [('/empleos/1.html', '<a href="https://www.bumeran.test/postulacion/1">Postularme</a>')])
        try:
            return scraper._get_apply_url('https://www.bumeran.test/empleos/1.html')
        finally:
            scraper.close()

    assert _in_thread(run) == 'https://www.bumeran.test/empleos/1.html'


LINKEDIN_PAGES = [
    ('/login', '<form action="/feed/"><input id="username"><input id="password"><button type="submit">Entrar</button></form>'),
    ('/feed/', '<div class="feed-identity-module">Hola</div>'),
    ('/jobs/search/', '<div class="jobs-search-results-list">'
                      '<div class="job-card-container"><span class="job-card-container__title">Backend Dev</span>'
                      '<span class="job-card-container__primary-description">Acme</span></div>'
                      '<div class="job-card-container"><span class="job-card-container__title">Data Engineer</span></div>'
                      '</div>'),
    ('linkedin.com', '<h1>LinkedIn</h1>'),
]


def test_linkedin_login_and_job_cards(monkeypatch):
    from scrapers import linkedin_pw
    monkeypatch.setattr(linkedin_pw, 'time', NO_SLEEP)

    def run():
        results = {}
        for name, kwargs in (('credentials', {'email': 'a@example.com', 'password': 'x'}),
                             ('cookie', {'li_at_token': 'token'}), ('no_token', {})):
            bot = linkedin_pw.linkedinClass(**kwargs)
            _serve(bot.context, LINKEDIN_PAGES)
            try:
                results[name] = (bot.login_with_credentials() if 'email' in kwargs else bot.login_with_cookie())
                if name == 'credentials':
                    results['jobs'] = bot.search_jobs('python', 'Buenos Aires', max_jobs_per_search=1)
                    results['all_jobs'] = bot.search_jobs('python', 'Buenos Aires')
            finally:
                bot.close()
                bot.close()
        return results

    results = _in_thread(run)
    assert results['credentials'] and results['cookie'] and not results['no_token']
    assert [(j['Title'], j['Company']) for j in results['jobs']] == [('Backend Dev', 'Acme')]
    assert [(j['Title'], j['Company']) for j in results['all_jobs']] == [('Backend Dev', 'Acme'),
                                                                          ('Data Engineer', 'No company')]
