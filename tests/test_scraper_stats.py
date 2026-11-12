"""Resultado de las búsquedas por portal: contador compartido, /metrics y registro desde las alertas."""
from types import SimpleNamespace
from unittest import mock

import pytest

import ai_usage
import observability
import scraper_stats


@pytest.fixture(autouse=True)
def fresh_storage(monkeypatch):
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'memory://')
    ai_usage.reset()
    yield
    ai_usage.reset()


def test_outcome_classification():
    assert scraper_stats.outcome([{'Title': 'Dev'}]) == 'ok'
    assert scraper_stats.outcome([]) == 'empty'
    assert scraper_stats.outcome(None) == 'empty'
    assert scraper_stats.outcome([{'Title': 'Dev'}], RuntimeError('x')) == 'error'


def test_record_counts_by_portal_and_outcome():
    scraper_stats.record('bumeran', [])
    scraper_stats.record('bumeran', [])
    scraper_stats.record('bumeran', [{'Title': 'Dev'}])
    scraper_stats.record('computrabajo', None, TimeoutError('caído'))
    found = scraper_stats.counts()
    assert found['bumeran'] == {'ok': 1, 'empty': 2, 'error': 0}
    assert found['computrabajo'] == {'ok': 0, 'empty': 0, 'error': 1}
    # los portales sin búsquedas salen en 0: así Prometheus ve el incremento de la primera
    assert found['linkedin'] == {'ok': 0, 'empty': 0, 'error': 0}


def test_record_never_breaks_the_search():
    with mock.patch.object(ai_usage, '_storage', side_effect=ConnectionError('redis caído')):
        assert scraper_stats.record('bumeran', [{'Title': 'Dev'}]) == 'ok'


def test_metrics_expose_runs_per_portal():
    scraper_stats.record('zonajobs', [])
    scraper_stats.record('zonajobs', [{'Title': 'Dev'}])
    value = observability.REGISTRY.get_sample_value
    assert value('empleoia_scraper_runs_total', {'portal': 'zonajobs', 'outcome': 'empty'}) == 1
    assert value('empleoia_scraper_runs_total', {'portal': 'zonajobs', 'outcome': 'ok'}) == 1
    assert value('empleoia_scraper_runs_total', {'portal': 'bumeran', 'outcome': 'ok'}) == 0


def test_job_alert_scrape_records_each_portal():
    import job_alerts

    def make(portal):
        if portal == 'bumeran':
            raise RuntimeError('selector roto')
        return SimpleNamespace(search_jobs=lambda *a, **k: [], close=lambda: None)

    search = {'name': 'Python', 'position': 'python', 'portals': ['computrabajo', 'bumeran']}
    assert job_alerts.scrape(search, make) == []
    found = scraper_stats.counts()
    assert found['computrabajo'] == {'ok': 0, 'empty': 1, 'error': 0}
    assert found['bumeran'] == {'ok': 0, 'empty': 0, 'error': 1}
