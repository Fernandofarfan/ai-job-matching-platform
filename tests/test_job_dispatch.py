"""Lanzamiento de scrapers en thread o Celery y lectura de su progreso."""
import os
from unittest import mock

import pytest

import job_dispatch


def test_unknown_job_is_rejected():
    with pytest.raises(ValueError):
        job_dispatch.resolve('os.system')


def test_thread_backend_runs_function(monkeypatch):
    monkeypatch.delenv('SCRAPER_BACKEND', raising=False)
    calls = []
    with mock.patch.object(job_dispatch, 'resolve', return_value=lambda *a: calls.append(a)), \
            mock.patch('threading.Thread') as thread:
        thread.side_effect = lambda target, args, daemon: mock.Mock(start=lambda: target(*args))
        assert job_dispatch.launch({}, 'bumeran_scraping', 'run_bumeran_job', ['x']) is None
    assert calls == [(['x'],)]


def test_celery_backend_queues_task(monkeypatch):
    monkeypatch.setenv('SCRAPER_BACKEND', 'celery')
    status = {'bumeran_scraping': {'status': 'running'}}
    fake = mock.Mock()
    fake.send_task.return_value.id = 'abc'
    with mock.patch.object(job_dispatch, 'resolve'), mock.patch('celery_app.celery', fake):
        assert job_dispatch.launch(status, 'bumeran_scraping', 'run_bumeran_job', [{'position': 'x'}]) == 'abc'
    fake.send_task.assert_called_once_with(job_dispatch.TASK_NAME, args=['bumeran_scraping', 'run_bumeran_job', [[{'position': 'x'}]]],
                                                kwargs={'user_id': None})
    assert status['bumeran_scraping']['status'] == 'queued'
    assert status['bumeran_scraping']['task_id'] == 'abc'


@pytest.mark.parametrize('state, info, expected', [
    ('PROGRESS', {'status': 'running', 'progress': 40, 'message': 'Buscando'}, ('running', 40)),
    ('SUCCESS', {'status': 'completed', 'progress': 100, 'message': 'Listo'}, ('completed', 100)),
    ('SUCCESS', {'status': 'running', 'progress': 90}, ('completed', 90)),
    ('FAILURE', RuntimeError('chrome'), ('failed', 0)),
    ('PENDING', None, ('queued', 0)),
])
def test_refresh_copies_celery_state(state, info, expected):
    status = {'k': {'status': 'queued', 'progress': 0, 'task_id': 't1'}, 'other': {'status': 'idle'}}
    fake = mock.Mock()
    fake.AsyncResult.return_value = mock.Mock(state=state, info=info)
    with mock.patch('celery_app.celery', fake):
        job_dispatch.refresh(status)
    assert (status['k']['status'], status['k']['progress']) == expected
    assert status['k']['task_id'] == 't1'
    assert status['other'] == {'status': 'idle'}


def test_refresh_ignores_finished_tasks():
    status = {'k': {'status': 'completed', 'task_id': 't1'}}
    with mock.patch('celery_app.celery') as fake:
        job_dispatch.refresh(status)
    fake.AsyncResult.assert_not_called()


def test_worker_publishes_progress_and_result():
    from tasks import scraping_tasks
    fake_app = mock.Mock(job_status={})

    def job(position):
        fake_app.job_status['k'].update(progress=50, message=position)
        fake_app.job_status['k'].update(status='completed', progress=100)

    with mock.patch.dict('sys.modules', {'app': fake_app}), \
            mock.patch('job_dispatch.resolve', return_value=job), \
            mock.patch.object(scraping_tasks.run_web_job, 'update_state'):
        result = scraping_tasks.run_web_job.run('k', 'run_bumeran_job', ['python'], poll_seconds=0.01)
    assert result['status'] == 'completed'
    assert result['message'] == 'python'


def test_credential_reload_keeps_backend(monkeypatch, tmp_path):
    """Releer el .env actualiza credenciales pero no cambia el backend fijado por el entorno."""
    from routers import scraper_pages as scrapers
    (tmp_path / '.env').write_text('SCRAPER_BACKEND=thread\nINDEED_EMAIL=nuevo@x.com\nLI_AT_TOKEN=nuevo-token\n')
    monkeypatch.setenv('SCRAPER_BACKEND', 'celery')
    monkeypatch.setenv('INDEED_EMAIL', 'viejo@x.com')
    monkeypatch.setenv('LI_AT_TOKEN', 'viejo-token')
    scrapers._reload_portal_credentials(tmp_path / '.env')
    assert os.environ['SCRAPER_BACKEND'] == 'celery'
    assert os.environ['INDEED_EMAIL'] == 'nuevo@x.com'
    assert os.environ['LI_AT_TOKEN'] == 'nuevo-token'


def test_refresh_adopts_task_from_redis(monkeypatch):
    """Tras reiniciar (o en otra instancia) se recupera la tarea guardada en Redis."""
    monkeypatch.setenv('SCRAPER_BACKEND', 'celery')
    status = {'bumeran_scraping': {'status': 'idle', 'progress': 0}, 'other': {'status': 'idle'}}
    fake = mock.Mock()
    fake.backend.client.get.side_effect = lambda k: b't9' if k.endswith(':bumeran_scraping') else None
    fake.AsyncResult.return_value = mock.Mock(state='PROGRESS', info={'status': 'running', 'progress': 30})
    with mock.patch('celery_app.celery', fake):
        job_dispatch.refresh(status)
    fake.AsyncResult.assert_called_once_with('t9')
    assert status['bumeran_scraping'] == {'status': 'running', 'progress': 30, 'task_id': 't9'}
    assert status['other'] == {'status': 'idle'}


def test_launch_remembers_task_in_redis(monkeypatch):
    monkeypatch.setenv('SCRAPER_BACKEND', 'celery')
    fake = mock.Mock()
    fake.send_task.return_value.id = 'abc'
    with mock.patch.object(job_dispatch, 'resolve'), mock.patch('celery_app.celery', fake):
        job_dispatch.launch({}, 'bumeran_scraping', 'run_bumeran_job', [])
    fake.backend.client.set.assert_called_once_with('empleoia:scraper_task:bumeran_scraping', 'abc', ex=86400)


def test_per_user_status_is_isolated():
    """El progreso de una búsqueda solo lo ve la cuenta que la lanzó."""
    import accounts
    status = job_dispatch.PerUserStatus({'indeed_scraping': {'status': 'idle'}})
    with accounts.as_user(1):
        status['indeed_scraping'] = {'status': 'running'}
    with accounts.as_user(2):
        assert status['indeed_scraping'] == {'status': 'idle'}
        assert job_dispatch._task_key('indeed_scraping') == 'empleoia:scraper_task:u2:indeed_scraping'
    with accounts.as_user(1):
        assert status['indeed_scraping'] == {'status': 'running'}


def test_results_dir_is_per_account(tmp_path, monkeypatch):
    """Cada cuenta escribe sus CSV en results/u<id>; sin cuenta, en results/."""
    import accounts
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    (tmp_path / 'results' / 'viejo.csv').write_text('a')
    assert accounts.results_dir() == 'results'
    accounts.claim_legacy_files(7)
    with accounts.as_user(7):
        assert sorted(p.name for p in (tmp_path / accounts.results_dir()).iterdir()) == ['viejo.csv']
    with accounts.as_user(8):
        assert list((tmp_path / accounts.results_dir()).iterdir()) == []


def test_generated_dirs_include_account_folders(tmp_path, monkeypatch):
    """La retención también recorre los documentos generados de cada cuenta."""
    import cv_storage
    monkeypatch.setenv('GENERATED_DIR', str(tmp_path))
    (tmp_path / 'u3' / 'resumes').mkdir(parents=True)
    assert str(tmp_path / 'u3' / 'resumes') in cv_storage.generated_dirs()


def test_adopt_legacy_files_moves_to_first_account(tmp_path, monkeypatch):
    """Si ya había cuentas, los CSV sueltos de results/ pasan a la primera."""
    import accounts
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    (tmp_path / 'results' / 'jobs.csv').write_text('a')
    (tmp_path / 'results' / '.gitkeep').write_text('')
    monkeypatch.setattr(accounts, 'first_user_id', lambda: 7)
    accounts.adopt_legacy_files()
    assert (tmp_path / 'results' / 'u7' / 'jobs.csv').exists()
    assert (tmp_path / 'results' / '.gitkeep').exists()
