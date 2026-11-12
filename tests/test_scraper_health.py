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


def test_blocked_portal_is_reported_but_does_not_fail():
    from scrapers.common import PortalBlocked
    ok, results = scraper_health.run(portals={'a': lambda: _scraper([{}]),
                                              'b': lambda: _scraper(error=PortalBlocked('captcha'))})
    assert ok and results[1] == {'portal': 'b', 'jobs': 0, 'error': 'captcha', 'blocked': True}


def test_indeed_adapter_counts_listing_cards(monkeypatch):
    from scrapers import indeed_scraper
    calls = []
    monkeypatch.setattr(indeed_scraper.indeedScraper, 'listing',
                        lambda self, query, location, max_jobs: calls.append((query, location, max_jobs)) or [{}])
    monkeypatch.setenv('SCRAPER_HEALTH_INDEED_LOCATION', 'Austin')
    ok, results = scraper_health.run(portals={'indeed': scraper_health.PORTALS['indeed']}, max_jobs=3)
    assert ok and results[0]['jobs'] == 1 and calls == [('python', 'Austin', 3)]
