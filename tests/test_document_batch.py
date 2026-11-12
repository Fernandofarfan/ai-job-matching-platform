"""Lotes de cartas/CVs: validación, generación en el pedido y encolado en Celery."""
from unittest import mock

import pytest

import document_batch


@pytest.fixture
def results_csv(tmp_path, monkeypatch):
    """CSV de ofertas en un results/ temporal, con documentos generados en tmp."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GENERATED_DIR', str(tmp_path / 'gen'))
    (tmp_path / 'results').mkdir()
    (tmp_path / 'results' / 'jobs.csv').write_text(
        'Title,Company,Description\nDev,<b>Acme</b>,Python y SQL\nQA,Globant,nan\nSRE,Mercado,Kubernetes\n',
        encoding='latin-1')
    return 'jobs.csv'


@pytest.mark.parametrize('kind, filename, num_jobs, status', [
    ('otra', 'jobs.csv', 5, 400),
    ('resumes', '', 5, 400),
    ('resumes', '../app.py', 5, 400),
    ('resumes', 'nada.csv', 5, 404),
    ('resumes', 'jobs.csv', 'x', 400),
])
def test_validate_rejects_bad_requests(results_csv, kind, filename, num_jobs, status):
    with pytest.raises(document_batch.BatchError) as err:
        document_batch.validate(kind, filename, num_jobs)
    assert err.value.status == status


def test_validate_caps_number_of_jobs(results_csv):
    assert document_batch.validate('resumes', results_csv, 999) == (results_csv, document_batch.MAX_JOBS)
    assert document_batch.validate('resumes', results_csv, 0) == (results_csv, 1)


def test_run_generates_one_document_per_description(results_csv, tmp_path):
    progress = []
    with mock.patch('document_generators._call_gemini', return_value='Carta lista'):
        out = document_batch.run('cover_letters', results_csv, 5, 'mi cv',
                                 progress=lambda d, t: progress.append((d, t)), pause=0)
    assert out['total'] == 2 and out['successful'] == 2
    assert out['results'][0]['company'] == '<b>Acme</b>'
    assert progress == [(1, 3), (2, 3), (3, 3)]
    saved = list((tmp_path / 'gen' / 'cover_letters').iterdir())
    assert len(saved) == 2


def test_run_hides_internal_errors(results_csv):
    with mock.patch('document_generators._call_gemini', side_effect=RuntimeError('clave secreta')):
        out = document_batch.run('resumes', results_csv, 1, 'mi cv', pause=0)
    assert out['successful'] == 0
    assert 'clave' not in out['results'][0]['error']


def test_run_requires_resume(results_csv):
    with pytest.raises(document_batch.BatchError):
        document_batch.run('resumes', results_csv, 1, '', pause=0)


def test_enqueue_sends_task_without_resume_text(results_csv):
    fake = mock.Mock()
    fake.send_task.return_value.id = 't1'
    with mock.patch('celery_app.celery', fake):
        assert document_batch.enqueue('resumes', results_csv, 3) == 't1'
    fake.send_task.assert_called_once_with(document_batch.TASK_NAME, args=['resumes', results_csv, 3],
                                                    kwargs={'user_id': None})
    fake.backend.client.set.assert_called_once()


@pytest.mark.parametrize('state, info, expected', [
    ('PENDING', None, 'queued'),
    ('STARTED', None, 'running'),
    ('PROGRESS', {'progress': 50, 'message': 'Documento 1 de 2'}, 'running'),
    ('SUCCESS', {'success': True, 'results': [], 'total': 0, 'successful': 0}, 'completed'),
    ('SUCCESS', {'success': False, 'error': 'Primero subí tu CV'}, 'failed'),
    ('FAILURE', RuntimeError('detalle interno'), 'failed'),
])
def test_status_maps_celery_states(state, info, expected):
    fake = mock.Mock()
    fake.backend.client.get.return_value = b'resumes'
    fake.AsyncResult.return_value = mock.Mock(state=state, info=info)
    with mock.patch('celery_app.celery', fake):
        out = document_batch.status('t1')
    assert out['state'] == expected
    assert 'detalle interno' not in str(out)


def test_status_unknown_task_is_none():
    fake = mock.Mock()
    fake.backend.client.get.return_value = None
    with mock.patch('celery_app.celery', fake):
        assert document_batch.status('otra') is None
    fake.AsyncResult.assert_not_called()


def test_batch_route_runs_inline(api, monkeypatch):
    monkeypatch.delenv('AI_BACKEND', raising=False)
    with mock.patch('document_batch.run', return_value={'success': True, 'results': [], 'total': 0,
                                                        'successful': 0}) as run:
        resp = api.post('/api/batch_optimize', json={'filename': 'jobs.csv', 'num_jobs': 2})
    assert resp.status_code == 200
    assert run.call_args.args[:3] == ('resumes', 'jobs.csv', 2)


def test_batch_route_queues_in_celery(api, monkeypatch):
    monkeypatch.setenv('AI_BACKEND', 'celery')
    with mock.patch('document_batch.enqueue', return_value='t9') as enqueue:
        resp = api.post('/api/batch_cover_letters', json={'filename': 'jobs.csv'})
    assert resp.status_code == 202
    assert resp.json() == {'success': True, 'task_id': 't9'}
    enqueue.assert_called_once_with('cover_letters', 'jobs.csv', 5)


def test_batch_route_reports_validation_error(api, monkeypatch):
    monkeypatch.delenv('AI_BACKEND', raising=False)
    resp = api.post('/api/batch_optimize', json={'filename': '../secreto.csv'})
    assert resp.status_code == 400
    assert resp.json()['success'] is False


def test_task_status_route(api):
    with mock.patch('document_batch.status', return_value=None):
        assert api.get('/api/documents/tasks/x').status_code == 404
    with mock.patch('document_batch.status', return_value={'success': True, 'state': 'queued', 'progress': 0}):
        assert api.get('/api/documents/tasks/x').json()['state'] == 'queued'


def test_optimize_resume_api(api):
    """/api/optimize_resume usa el CV guardado y no expone errores internos."""
    from routers import documents
    optimizer = mock.Mock()
    optimizer.optimize_resume.return_value = 'CV nuevo'
    optimizer.save_resume.return_value = 'cv.docx'
    api.app.dependency_overrides[documents.get_optimizer] = lambda: optimizer
    assert api.post('/api/optimize_resume', json={'job_description': 'Python'}).status_code == 400
    api.app.dependency_overrides[documents.get_resume_text] = lambda: lambda: 'CV viejo'
    data = api.post('/api/optimize_resume', json={'job_description': 'Python', 'job_title': 'Dev'}).json()
    assert data == {'success': True, 'filename': 'cv.docx', 'resume_text': 'CV nuevo'}
    optimizer.optimize_resume.assert_called_once_with('CV viejo', 'Python', 'Dev', '')
    optimizer.save_resume.side_effect = OSError('/ruta/secreta')
    resp = api.post('/api/optimize_resume', json={'job_description': 'Python'})
    assert resp.status_code == 500 and 'secreta' not in resp.text
