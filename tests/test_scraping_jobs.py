"""Búsquedas de Computrabajo y Bumeran en segundo plano (scraping_jobs.py)."""
import os
from unittest import mock

import pytest

import accounts
import scraping_jobs


@pytest.fixture(autouse=True)
def quick(monkeypatch, tmp_path):
    monkeypatch.setattr(scraping_jobs.time, 'sleep', lambda s: None)
    monkeypatch.setattr(scraping_jobs.scraper_stats, 'record', lambda *a: None)


def _fake(jobs=None, error=None):
    scraper = mock.Mock()
    scraper.search_jobs.side_effect = error or (lambda *a, **k: list(jobs or []))
    return mock.Mock(return_value=scraper), scraper


@pytest.mark.parametrize('portal,cls,run', [
    ('computrabajo', 'ComputrabajoScraper', lambda s: scraping_jobs.run_computrabajo_job(s, 'a@b.co', 'x')),
    ('bumeran', 'BumeranScraper', lambda s: scraping_jobs.run_bumeran_job(s)),
])
def test_jobs_saved_empty_and_failed(monkeypatch, portal, cls, run):
    key = f'{portal}_scraping'
    searches = [{'position': 'python', 'location': 'CABA'}, {'position': 'go'}]
    maker, scraper = _fake([{'Title': 'Dev'}])
    monkeypatch.setattr(scraping_jobs, cls, maker)
    monkeypatch.setitem(scraping_jobs.job_status, key, {'status': 'running'})
    run(searches)
    assert scraping_jobs.job_status[key]['status'] == 'completed'
    assert scraper.save_to_csv.call_args[0][0] == [{'Title': 'Dev'}, {'Title': 'Dev'}]
    scraper.close.assert_called_once()

    maker, scraper = _fake([])
    monkeypatch.setattr(scraping_jobs, cls, maker)
    run(searches)
    assert scraping_jobs.job_status[key]['progress'] == 100 and not scraper.save_to_csv.called

    maker, _ = _fake(error=RuntimeError('bloqueado'))
    monkeypatch.setattr(scraping_jobs, cls, maker)
    run(searches)
    assert scraping_jobs.job_status[key]['status'] == 'failed'


def test_universal_portal_failures_are_isolated(monkeypatch, tmp_path):
    module = scraping_jobs
    ok, _ = _fake([{'Title': 'Dev', 'Company': 'Acme'}])
    broken, _ = _fake(error=RuntimeError('caído'))
    monkeypatch.setattr(module, 'ComputrabajoScraper', ok)
    monkeypatch.setattr(module, 'BumeranScraper', broken)
    monkeypatch.setattr(module, 'ZonaJobsScraper', broken)
    monkeypatch.setattr(module, 'GetOnBoardScraper', ok)
    monkeypatch.setitem(module.job_status, 'universal_scraping', {'status': 'running'})
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    module.run_universal_job('python', '')
    state = module.job_status['universal_scraping']
    assert state['status'] == 'completed'
    assert state['scrapers']['bumeran']['status'] == 'failed' and state['scrapers']['zonajobs']['status'] == 'failed'
    assert state['scrapers']['indeed']['status'] == 'skipped'

    monkeypatch.setattr(module, 'ComputrabajoScraper', broken)
    monkeypatch.setattr(module, 'GetOnBoardScraper', broken)
    module.run_universal_job('python', '')
    assert state['status'] == 'completed' and state['progress'] == 100
    assert os.path.exists(os.path.join(accounts.results_dir(), '.searched'))
