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
    page = mock.Mock()
    page.goto.side_effect = [TimeoutError('lento'), TimeoutError('lento'), None]
    sleeps = []
    get_with_retries(page, 'https://x', attempts=3, sleep=sleeps.append)
    assert page.goto.call_count == 3
    assert sleeps == [2.0, 4.0]


def test_get_with_retries_raises_after_last_attempt():
    page = mock.Mock()
    page.goto.side_effect = TimeoutError('caído')
    with pytest.raises(TimeoutError):
        get_with_retries(page, 'https://x', attempts=2, sleep=lambda s: None)
    assert page.goto.call_count == 2


def test_browser_failure_closes_what_was_opened(monkeypatch):
    from scrapers.common import Browser
    monkeypatch.delenv('PLAYWRIGHT_WS_ENDPOINT', raising=False)
    playwright = mock.Mock()
    playwright.chromium.launch.return_value.new_context.side_effect = RuntimeError('sin memoria')
    with pytest.raises(RuntimeError):
        Browser(playwright_factory=lambda: mock.Mock(start=lambda: playwright))
    playwright.chromium.launch.return_value.close.assert_called_once()
    playwright.stop.assert_called_once()


def test_browser_uses_remote_endpoint_and_proxy(monkeypatch):
    from scrapers.common import Browser
    playwright = mock.Mock()
    factory = lambda: mock.Mock(start=lambda: playwright)  # noqa: E731
    monkeypatch.setenv('PLAYWRIGHT_WS_ENDPOINT', 'ws://chrome:3000')
    Browser(playwright_factory=factory).close()
    playwright.chromium.connect.assert_called_once_with('ws://chrome:3000')
    monkeypatch.delenv('PLAYWRIGHT_WS_ENDPOINT')
    monkeypatch.setenv('PROXY_SERVER', 'http://proxy:8080')
    Browser(playwright_factory=factory)
    assert playwright.chromium.launch.call_args.kwargs['proxy'] == {'server': 'http://proxy:8080'}
    assert playwright.chromium.launch.call_args.kwargs['headless'] is True


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
    assert titles('Lima, Chile') == ['Backend Python Developer']


def _without_browser(cls):
    """Instancia sin __init__: estos helpers solo procesan texto y no abren Chrome."""
    return object.__new__(cls)


def test_indeed_text_helpers_on_saved_description():
    from scrapers.indeed_scraper import indeedScraper
    scraper = _without_browser(indeedScraper)
    text = (FIXTURES / 'indeed_description.txt').read_text(encoding='utf-8')
    # Solo cuenta lo de Basic Qualifications: el 6+ de Preferred no descarta la oferta
    assert scraper.extract_years_of_experience(text) == '2-3'
    assert scraper.categorize_experience(text) == 'Early Career (2-3 years)'
    assert scraper.extract_years_of_experience('Basic qualifications: 5+ years of Java') == 'SKIP_HIGH_EXPERIENCE'
    assert scraper.extract_years_of_experience('Junior role, we train you') == 'Entry Level'
    assert scraper.extract_salary_from_description(text) == '$90,000 - $120,000 per year'
    cleaned = scraper._clean_job_description(text)
    assert 'Data Engineer' in cleaned and '401k' not in cleaned and 'Salary' not in cleaned
    assert scraper._clean_job_description('') == 'Job description not available'


def test_linkedin_text_helpers():
    from scrapers import linkedin_pw
    assert linkedin_pw.extract_years_of_experience('Requires 8+ years of experience in Go') == '8+ years'
    assert linkedin_pw.extract_years_of_experience('2-3 years of experience with SQL') == '2-3 years'
    assert linkedin_pw.extract_years_of_experience('at least 4 years in data') == '4 years'
    assert linkedin_pw.extract_years_of_experience('Great team') == 'Not specified'
    assert linkedin_pw.categorize_experience_with_limit('8+ years') == 'SKIP_HIGH_EXPERIENCE'
    assert linkedin_pw.categorize_experience_with_limit('2-3 years') == 'Early Career (2-3 years)'
    assert linkedin_pw.categorize_experience_with_limit('1 years') == 'Entry Level (0-1 years)'
    assert linkedin_pw.categorize_experience_with_limit('Not specified') == 'Not specified'
    assert linkedin_pw.has_citizenship_requirements('must be a us citizen with active clearance')
    assert not linkedin_pw.has_citizenship_requirements('remote from latam')
