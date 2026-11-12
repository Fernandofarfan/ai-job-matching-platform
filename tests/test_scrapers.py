"""Parsers de scrapers contra HTML guardado y reintentos de carga (sin navegador)."""
from pathlib import Path
from unittest import mock

import pytest

from scrapers import bumeran_scraper, computrabajo_scraper
from scrapers.common import get_with_retries

FIXTURES = Path(__file__).parent / 'fixtures'


def test_computrabajo_listing():
    jobs = computrabajo_scraper.parse_listing((FIXTURES / 'computrabajo_listing.html').read_text(encoding='utf-8'))
    assert len(jobs) == 2
    assert jobs[0] == {
        'Title': 'Desarrollador Python Sr',
        'URL': 'https://www.computrabajo.com.ar/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-python-ABC123',
        'Company': 'Acme Software',
        'Location': 'Capital Federal, Buenos Aires',
        'Salary': '$ 1.500.000 (Mensual)',
        'Description': 'Buscamos dev Python con Django y SQL.',
        'Source': 'Computrabajo',
    }
    assert jobs[1]['Company'] == 'Confidential'
    assert jobs[1]['Salary'] == 'Not specified'


def test_computrabajo_empty_page():
    assert computrabajo_scraper.parse_listing('<html><body>Sin resultados</body></html>') == []


def test_bumeran_listing():
    jobs = bumeran_scraper.parse_listing((FIXTURES / 'bumeran_listing.html').read_text(encoding='utf-8'))
    assert [j['Title'] for j in jobs] == ['Desarrollador Backend', 'Data Analyst']
    first = jobs[0]
    assert first['URL'] == 'https://www.bumeran.com.ar/empleos/desarrollador-backend-techco-1115.html'
    assert (first['Company'], first['Location'], first['Job_Type'], first['Date_Posted']) == (
        'TechCo', 'Capital Federal, Buenos Aires', 'Remoto', 'Publicado hace 2 días')
    assert jobs[1]['Company'] == 'Confidencial'


def test_get_with_retries_recovers_after_failures():
    driver = mock.Mock()
    driver.get.side_effect = [TimeoutError('lento'), TimeoutError('lento'), None]
    sleeps = []
    get_with_retries(driver, 'https://x', attempts=3, sleep=sleeps.append)
    assert driver.get.call_count == 3
    assert sleeps == [2.0, 4.0]


def test_get_with_retries_raises_after_last_attempt():
    driver = mock.Mock()
    driver.get.side_effect = TimeoutError('caído')
    with pytest.raises(TimeoutError):
        get_with_retries(driver, 'https://x', attempts=2, sleep=lambda s: None)
    assert driver.get.call_count == 2


def test_configure_driver_failure_closes_browser_and_raises():
    from scrapers.common import configure_driver
    driver = mock.Mock()
    driver.set_page_load_timeout.side_effect = RuntimeError('sesión inválida')
    with pytest.raises(RuntimeError):
        configure_driver(driver)
    driver.quit.assert_called_once()


def test_bumeran_skips_badges_as_company():
    html = ('<a href="/empleos/dev-1.html"><h2>Dev</h2><h3>Apto discapacidad</h3>'
            '<h3>Acme</h3></a>')
    assert bumeran_scraper.parse_listing(html)[0]['Company'] == 'Acme'


def test_zonajobs_reuses_navent_parser_with_its_domain():
    from scrapers import zonajobs_scraper
    jobs = zonajobs_scraper.parse_listing((FIXTURES / 'bumeran_listing.html').read_text(encoding='utf-8'))
    assert jobs[0]['URL'].startswith('https://www.zonajobs.com.ar/empleos/')
    assert {j['Source'] for j in jobs} == {'ZonaJobs'}
    assert zonajobs_scraper.ZonaJobsScraper.base_url == zonajobs_scraper.BASE_URL


def _getonboard_payload():
    import json
    return json.loads((FIXTURES / 'getonboard_search.json').read_text(encoding='utf-8'))


def test_getonboard_parses_api_payload():
    from scrapers import getonboard_scraper
    jobs = getonboard_scraper.parse_payload(_getonboard_payload())
    assert [j['Title'] for j in jobs] == ['Backend Python Developer', 'Data Engineer']
    first = jobs[0]
    assert (first['Company'], first['Location'], first['Salary'], first['Job_Type']) == (
        'Acme', 'Argentina, Chile', 'USD 2500 - 3500', 'Remoto')
    assert first['Description'] == 'API de pagos Django & SQL'
    assert first['URL'] == 'https://www.getonbrd.com/jobs/backend-python-acme'
    assert jobs[1]['Company'] == 'Confidencial'
    assert jobs[1]['URL'] == 'https://www.getonbrd.com/jobs/data-engineer-lima'


def test_getonboard_location_keeps_local_and_remote():
    from scrapers import getonboard_scraper
    titles = [j['Title'] for j in getonboard_scraper.parse_payload(_getonboard_payload(), 'peru')]
    assert titles == ['Backend Python Developer', 'Data Engineer']
    titles = [j['Title'] for j in getonboard_scraper.parse_payload(_getonboard_payload(), 'Uruguay')]
    assert titles == ['Backend Python Developer']


def test_getonboard_search_paginates_and_limits():
    from scrapers import getonboard_scraper
    payload = _getonboard_payload()
    payload['meta']['total_pages'] = 3
    session = mock.Mock()
    session.get.return_value.json.return_value = payload
    jobs = getonboard_scraper.GetOnBoardScraper(session).search_jobs('python', max_jobs=3)
    assert len(jobs) == 3
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs['params']['page'] == 2


def test_getonboard_city_searches_keep_local_jobs():
    """Las ciudades expandidas entran en Location y en el filtro "Ciudad, País"."""
    from scrapers import getonboard_scraper
    payload = _getonboard_payload()

    def titles(location):
        return [j['Title'] for j in getonboard_scraper.parse_payload(payload, location)]
    assert 'Lima, Perú' in [j['Location'] for j in getonboard_scraper.parse_payload(payload)]
    assert 'Data Engineer' in titles('Lima')
    assert 'Data Engineer' in titles('Lima, Peru')
    assert titles('Arequipa, Perú') == ['Backend Python Developer']
