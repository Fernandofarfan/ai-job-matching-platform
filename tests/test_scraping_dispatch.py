"""
test_scraping_dispatch.py – Tests del despacho de tareas Celery:
fallback eager sin broker, mapeo de estados y overlay en /status.
"""
import pytest


class _FakeResult:
    def __init__(self, state, info, task_id='11111111-2222-3333-4444-555555555555'):
        self.state = state
        self.info = info
        self.id = task_id


class _FakeTask:
    """Simula una tarea Celery sin broker: delay() falla → apply() eager."""

    def __init__(self, state='SUCCESS', info=None):
        self._state = state
        self._info = {'status': 'completed', 'progress': 100,
                      'message': 'done'} if info is None else info

    def delay(self, *args, **kwargs):
        raise ConnectionError('broker no disponible (simulado)')

    def apply(self, args=(), kwargs=None):
        return _FakeResult(self._state, self._info)


@pytest.fixture
def state():
    """Importa core.state DESPUÉS de que conftest aplicó los mocks."""
    import core.state as s
    yield s
    # Limpieza: no dejar tareas falsas que contaminen /status
    for key in ('indeed_scraping', 'fake_key'):
        s.active_results.pop(key, None)
        s.active_tasks.pop(key, None)


class TestEagerFallback:
    def test_dispatch_falls_back_without_broker(self, state):
        task = _FakeTask()
        result = state.dispatch_task('fake_key', task, 'arg1')
        assert result is not None
        assert result.state == 'SUCCESS'
        assert 'fake_key' in state.active_results

    def test_status_mapping_success(self, state):
        state.dispatch_task('fake_key', _FakeTask())
        status = state.get_task_status('fake_key')
        assert status == {'status': 'completed', 'progress': 100, 'message': 'done'}

    def test_status_mapping_progress_uses_task_status_field(self, state):
        task = _FakeTask(state='PROGRESS',
                         info={'status': 'running', 'progress': 42,
                               'message': 'Scrapeando...'})
        state.dispatch_task('fake_key', task)
        status = state.get_task_status('fake_key')
        assert status['status'] == 'running'
        assert status['progress'] == 42
        assert status['message'] == 'Scrapeando...'

    def test_status_mapping_stopped(self, state):
        task = _FakeTask(state='PROGRESS',
                         info={'status': 'stopped', 'progress': 50,
                               'message': 'Process stopped by user.'})
        state.dispatch_task('fake_key', task)
        assert state.get_task_status('fake_key')['status'] == 'stopped'

    def test_status_mapping_failure(self, state):
        task = _FakeTask(state='FAILURE', info=RuntimeError('boom'))
        state.dispatch_task('fake_key', task)
        status = state.get_task_status('fake_key')
        assert status['status'] == 'failed'
        assert 'boom' in status['message']

    def test_unknown_key_returns_none(self, state):
        assert state.get_task_status('no_existe') is None


class TestStatusOverlay:
    def test_get_all_status_overlays_task_state(self, state):
        """/status debe mostrar el estado de la tarea por encima del local."""
        task = _FakeTask(state='PROGRESS',
                         info={'status': 'running', 'progress': 77,
                               'message': 'en marcha'})
        state.dispatch_task('indeed_scraping', task)
        all_status = state.get_all_status()
        assert all_status['indeed_scraping']['status'] == 'running'
        assert all_status['indeed_scraping']['progress'] == 77
        # El resto de las claves sigue presente
        assert 'linkedin_scraping' in all_status
        assert 'connection_requests' in all_status

    def test_local_job_status_preserved_without_tasks(self, state):
        all_status = state.get_all_status()
        assert all_status['bumeran_scraping']['status'] == 'idle'


class TestTaskIdValidation:
    def test_is_valid_task_id(self):
        from utils import is_valid_task_id
        assert is_valid_task_id('123e4567-e89b-12d3-a456-426614174000')
        assert not is_valid_task_id('../../etc/passwd')
        assert not is_valid_task_id('')
        assert not is_valid_task_id('not-a-uuid')
