"""Búsqueda universal tal como corre en el worker de Celery."""
from unittest import mock


def test_universal_job_without_portal_state(app, monkeypatch, tmp_path):
    """En el worker job_status no trae el estado por portal que arma la web: no debe fallar."""
    import job_dispatch
    module = job_dispatch.resolve('run_universal_job').__globals__
    for cls in ('ComputrabajoScraper', 'BumeranScraper', 'ZonaJobsScraper', 'GetOnBoardScraper'):
        fake = mock.Mock()
        fake.return_value.search_jobs.return_value = [{'Title': cls, 'Company': 'Acme'}]
        monkeypatch.setitem(module, cls, fake)
    monkeypatch.setitem(module['job_status'], 'universal_scraping', {'status': 'running'})
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    module['run_universal_job']('python', '')
    state = module['job_status']['universal_scraping']
    assert state['status'] == 'completed'
    assert state['scrapers']['zonajobs']['status'] == 'completed'
    assert state['scrapers']['getonboard']['status'] == 'completed'
    assert len(list((tmp_path / 'results').glob('universal_jobs_*.csv'))) == 1
