"""Scrapers de Playwright contra un servidor local con el HTML guardado de cada portal."""
import concurrent.futures
import http.server
import threading
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / 'tests' / 'fixtures'


@pytest.fixture
def portal_server():
    """Sirve la primera página de resultados de cada portal; las demás responden 404 ('no encontrada')."""
    pages = {
        '/trabajo-de-python': FIXTURES / 'computrabajo_listing.html',
        '/empleos-busqueda-python.html': FIXTURES / 'bumeran_listing.html',
        '/jobs': FIXTURES / 'indeed_listing.html',
        '/search/results/people/': FIXTURES / 'linkedin_people.html',
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            route, _, query = self.path.partition('?')
            if route == '/viewjob':
                description = (FIXTURES / 'indeed_description.txt').read_text(encoding='utf-8')
                self._send(200, f'<div id="jobDescriptionText">{description}</div>'
                                '<a href="https://acme.example/apply">Apply on company site</a>'.encode())
                return
            path = pages.get(route) if route in ('/jobs', '/search/results/people/') or not query else None
            if route == '/search/results/people/' and 'page=' in query:
                path = None
            body = path.read_bytes() if path else '<title>404</title>Página no encontrada'.encode()
            self._send(200 if path else 404, body)

        def _send(self, status, body):
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def _in_thread(fn):
    """Como en la app: el scraper corre en un thread propio (la API sync de Playwright no anda dentro de un loop asyncio)."""
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(fn).result(timeout=120)


def _search(scraper_cls, base_url):
    scraper = scraper_cls()
    scraper.base_url = base_url
    try:
        return scraper.search_jobs('python', max_jobs=10)
    finally:
        scraper.close()


def test_computrabajo_with_playwright(portal_server):
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    jobs = _in_thread(lambda: _search(ComputrabajoScraper, portal_server))
    assert jobs and jobs[0]['Title'] == 'Desarrollador Python Sr'
    assert jobs[0]['Apply_URL'] == jobs[0]['URL']


def test_bumeran_with_playwright(portal_server):
    from scrapers.bumeran_scraper import BumeranScraper
    jobs = _in_thread(lambda: _search(BumeranScraper, portal_server))
    assert [job['Company'] for job in jobs] == ['TechCo', 'Confidencial']
    assert all(job['URL'].startswith(portal_server) for job in jobs)


def test_indeed_with_playwright(portal_server):
    from scrapers.indeed_scraper import indeedScraper

    def search():
        scraper = indeedScraper()
        scraper.base_url = portal_server
        try:
            return scraper.search_jobs('Data Engineer', 'Remote', max_jobs_per_search=5)
        finally:
            scraper.close()
    jobs = _in_thread(search)
    assert [job['Title'] for job in jobs] == ['Data Engineer']
    assert jobs[0]['Company'] == 'Acme Analytics' and jobs[0]['Job_Link'] == f'{portal_server}/viewjob?jk=abc123'
    assert jobs[0]['Experience_Category'] == 'Early Career (2-3 years)'


def test_linkedin_connections_with_playwright(portal_server, monkeypatch):
    from scrapers import linkedin_connection as lc
    monkeypatch.setattr(lc, 'people_search_url',
                        lambda keywords, page=1: f'{portal_server}/search/results/people/?keywords={keywords}'
                                                 + (f'&page={page}' if page > 1 else ''))
    monkeypatch.setattr(lc.random, 'randint', lambda a, b: b)

    def run():
        bot = lc.linkedinConnections()
        try:
            ok = bot.process_company('Acme', 'Hola {name}', max_pages=2)
            return ok, bot.total_connections_sent, bot.page.evaluate('window.sent'), bot.processed_profiles
        finally:
            bot.cleanup()
    ok, total, clicked, profiles = _in_thread(run)
    # Ana se invita; Beto tiene una invitación pendiente; Carolina no trabaja en Acme
    assert ok and total == 1 and clicked == 1
    assert profiles == {'https://www.linkedin.com/in/ana-perez', 'https://www.linkedin.com/in/beto'}
