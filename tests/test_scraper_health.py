"""Tests del monitor de scrapers (sin navegador)."""
from unittest import mock

from scripts import scraper_health


def _scraper(jobs=None, error=None):
    scraper = mock.Mock()
    if error:
        scraper.search_jobs.side_effect = error
    else:
        scraper.search_jobs.return_value = jobs
    return scraper


def test_all_portals_with_jobs_is_ok():
    a, b = _scraper([{}] * 3), _scraper([{}])
    ok, results = scraper_health.run(portals={'a': lambda: a, 'b': lambda: b})
    assert ok and [r['jobs'] for r in results] == [3, 1]
    a.close.assert_called_once()


def test_portal_without_jobs_fails():
    ok, results = scraper_health.run(portals={'a': lambda: _scraper([])})
    assert not ok and results[0]['jobs'] == 0


def test_portal_error_fails_and_closes_browser():
    scraper = _scraper(error=RuntimeError('selector cambió'))
    ok, results = scraper_health.run(portals={'a': lambda: scraper})
    assert not ok and 'selector cambió' in results[0]['error']
    scraper.close.assert_called_once()


def test_driver_setup_error_is_reported():
    def broken():
        raise RuntimeError('sin Chrome')
    ok, results = scraper_health.run(portals={'a': broken})
    assert not ok and 'sin Chrome' in results[0]['error']


def test_main_exit_code(capsys):
    with mock.patch.object(scraper_health, 'PORTALS', {'a': lambda: _scraper([{}])}):
        assert scraper_health.main(['--query', 'qa']) == 0
    assert '"ok": true' in capsys.readouterr().out
