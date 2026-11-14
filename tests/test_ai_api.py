"""API de IA, notificaciones y salarios migrada a FastAPI (routers/ai.py)."""
from types import SimpleNamespace
from unittest import mock

import pytest

from routers import ai


@pytest.fixture
def engine(api):
    """Gemini simulado y un CV guardado."""
    fake = mock.MagicMock()
    api.app.dependency_overrides[ai.get_ai] = lambda: SimpleNamespace(
        available=True, engine=fake, notifier=None, resume_text=lambda: 'CV con Python',
        profile=lambda: {'dev': {'skills': ['python', 'sql']}})
    return fake


def test_ai_routes_503_without_gemini(api):
    """Sin GEMINI_API_KEY las rutas de IA avisan con 503; el copiloto responde 200 con el aviso."""
    resp = api.post('/api/ai/analyze-job', json={'job_description': 'x'})
    assert resp.status_code == 503 and resp.json()['success'] is False
    chat = api.post('/api/ai/copilot', json={'message': 'hola'})
    assert chat.status_code == 200 and 'GEMINI_API_KEY' in chat.json()['reply']


def test_analyze_job_uses_saved_resume(api, engine):
    """analyze-job pasa el CV guardado al motor."""
    engine.analyze_job_complete.return_value = {'match': 80}
    data = api.post('/api/ai/analyze-job', json={'job_title': 'Dev', 'job_description': 'Python'}).json()
    engine.analyze_job_complete.assert_called_once_with('Dev', 'Python', 'CV con Python')
    assert data == {'success': True, 'analysis': {'match': 80}}


def test_copilot_gets_profile_and_tracker_context(api, engine, tracker_db, monkeypatch):
    """El copiloto recibe rol, skills y conteos del tracker (antes db_manager no estaba importado)."""
    monkeypatch.setattr(tracker_db.get_all_tracked_jobs, 'return_value', [{'status': 'applied'}] * 2)
    engine.copilot_chat.return_value = 'Hola'
    assert api.post('/api/ai/copilot', json={'message': 'hola', 'history': []}).json()['reply'] == 'Hola'
    context = engine.copilot_chat.call_args.args[2]
    assert context['perfil'] == {'rol': 'dev', 'skills': ['python', 'sql']}
    assert context['tracker_stats'] == {'applied': 2} and context['total_postulaciones'] == 2


def test_internal_errors_do_not_leak(api, engine):
    """Una excepción del motor no aparece en la respuesta."""
    engine.rewrite_cv_bullet.side_effect = RuntimeError('clave secreta')
    resp = api.post('/api/ai/rewrite-bullet', json={'bullet': 'x'})
    assert resp.status_code == 500 and 'secreta' not in resp.text
    engine.copilot_chat.side_effect = RuntimeError('clave secreta')
    chat = api.post('/api/ai/copilot', json={'message': 'hola'})
    assert chat.status_code == 500 and 'secreta' not in chat.text


def test_validation_errors(api, engine):
    """Campos requeridos y JSON inválido devuelven 400 con el formato del frontend."""
    assert api.post('/api/ai/interview/evaluate', json={'question': 'q'}).status_code == 400
    assert api.post('/api/ai/learning-path', json={'missing_skills': 'docker'}).status_code == 400
    resp = api.post('/api/ai/copilot', content='{no es json', headers={'Content-Type': 'application/json'})
    assert resp.status_code == 400 and resp.json()['success'] is False


def test_market_insights_get_and_cache(api, engine, tracker_db, monkeypatch):
    """GET lee la query; si hay caché no llama a Gemini."""
    monkeypatch.setattr(tracker_db.get_cached_market_insight, 'return_value', {'mediana': 1})
    data = api.get('/api/ai/market-insights?role=Dev').json()
    assert data == {'success': True, 'data': {'mediana': 1}, 'from_cache': True}
    tracker_db.get_cached_market_insight.assert_called_with('Dev', 'semi-senior', 'Argentina')
    engine.get_market_salary_insights.assert_not_called()


@pytest.mark.parametrize('name', ['../.env', 'sub/x.csv', '/etc/passwd', 'x.txt'])
def test_salary_csv_rejects_paths_outside_results(api, name):
    """/api/salary/analyze-csv solo lee CSVs directamente dentro de results/."""
    assert api.post('/api/salary/analyze-csv', json={'filename': name}).status_code == 400


def test_salary_csv_reads_results_file(api, monkeypatch, tmp_path):
    """Con un CSV válido devuelve la distribución salarial."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    (tmp_path / 'results' / 'jobs.csv').write_text('Title,Salary,Company\nDev,$ 1.000.000,Acme\n', encoding='utf-8')
    data = api.post('/api/salary/analyze-csv', json={'filename': 'jobs.csv'}).json()
    assert data['success'] and 'distribution' in data and 'by_company' in data


def test_notifications_without_manager(api):
    """Sin NotificationManager las rutas responden 503."""
    assert api.get('/api/notifications/config').status_code == 503
    assert api.post('/api/notifications/test').status_code == 503
