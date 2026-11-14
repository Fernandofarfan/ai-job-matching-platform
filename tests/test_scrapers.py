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
