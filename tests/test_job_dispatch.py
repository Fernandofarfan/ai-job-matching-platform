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
    fake.send_task.assert_called_once_with(job_dispatch.TASK_NAME, args=['bumeran_scraping', 'run_bumeran_job', [[{'position': 'x'}]]])
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
    from web import scrapers
    (tmp_path / '.env').write_text('SCRAPER_BACKEND=thread\nINDEED_EMAIL=nuevo@x.com\n')
    monkeypatch.setenv('SCRAPER_BACKEND', 'celery')
    monkeypatch.setenv('INDEED_EMAIL', 'viejo@x.com')
    scrapers._reload_portal_credentials(tmp_path / '.env')
    assert os.environ['SCRAPER_BACKEND'] == 'celery'
    assert os.environ['INDEED_EMAIL'] == 'nuevo@x.com'


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
