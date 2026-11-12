"""Scrapers de Playwright contra un servidor local con el HTML guardado de cada portal."""
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
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = pages.get(self.path)
            body = path.read_bytes() if path else '<title>404</title>Página no encontrada'.encode()
            self.send_response(200 if path else 404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def test_computrabajo_with_playwright(portal_server):
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    scraper = ComputrabajoScraper()
    scraper.base_url = portal_server
    try:
        jobs = scraper.search_jobs('python', max_jobs=10)
    finally:
        scraper.close()
    assert jobs and jobs[0]['Title'] == 'Desarrollador Python Sr'
    assert jobs[0]['Apply_URL'] == jobs[0]['URL']


def test_bumeran_with_playwright(portal_server):
    from scrapers.bumeran_scraper import BumeranScraper
    scraper = BumeranScraper()
    scraper.base_url = portal_server
    try:
        jobs = scraper.search_jobs('python', max_jobs=10)
    finally:
        scraper.close()
    assert [job['Company'] for job in jobs] == ['TechCo', 'Confidencial']
    assert all(job['URL'].startswith(portal_server) for job in jobs)
