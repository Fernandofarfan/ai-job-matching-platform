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


def test_universal_job_unifies_offers_repeated_across_portals(app, monkeypatch, tmp_path):
    """La misma oferta en Computrabajo y Bumeran queda una sola vez en el CSV, con los dos portales."""
    import job_dispatch
    import pandas as pd
    module = job_dispatch.resolve('run_universal_job').__globals__
    same = {'Title': 'Data Engineer', 'Company': 'Globant', 'Location': 'Buenos Aires'}
    for cls, extra in (('ComputrabajoScraper', {'URL': 'https://ct.example/1'}),
                       ('BumeranScraper', {'URL': 'https://bm.example/1'}),
                       ('ZonaJobsScraper', None), ('GetOnBoardScraper', None)):
        fake = mock.Mock()
        fake.return_value.search_jobs.return_value = [{**same, **extra}] if extra else []
        monkeypatch.setitem(module, cls, fake)
    monkeypatch.setitem(module['job_status'], 'universal_scraping', {'status': 'running'})
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    module['run_universal_job']('data', '')
    [csv] = (tmp_path / 'results').glob('universal_jobs_*.csv')
    df = pd.read_csv(csv, encoding='utf-8-sig')
    assert len(df) == 1
    assert df.loc[0, 'Portales'] == 'Computrabajo, Bumeran'
