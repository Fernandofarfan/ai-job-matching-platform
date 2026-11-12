"""API del tracker en FastAPI (routers/tracker.py) con la sesión y el CSRF de Flask."""
from datetime import date, datetime
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flask_wtf.csrf import generate_csrf

import auth
from routers import tracker

JOBS = [
    {'id': 1, 'title': 'Data Analyst', 'company': 'Acme Corp', 'status': 'applied',
     'follow_up': date(2000, 1, 1), 'applied_date': datetime(1999, 12, 1)},
    {'id': 2, 'title': 'QA', 'company': 'TechCo', 'status': 'rejected', 'follow_up': date(2000, 1, 1)},
]


@pytest.fixture
def db():
    """DatabaseManager falso que usan las rutas."""
    fake = mock.MagicMock()
    fake.get_all_tracked_jobs.return_value = JOBS
    fake.get_tracked_job_by_id.side_effect = lambda jid: next((j for j in JOBS if j['id'] == jid), None)
    fake.add_job_to_tracker.return_value = 99
    fake.update_tracker_dates.return_value = True
    return fake


@pytest.fixture
def api(app, db):
    """Cliente de una app FastAPI con el router del tracker y la app Flask de los tests."""
    fastapi_app = FastAPI()
    fastapi_app.include_router(tracker.router)
    fastapi_app.dependency_overrides[tracker.get_db] = lambda: db
    fastapi_app.dependency_overrides[tracker.get_flask_app] = lambda: app
    return TestClient(fastapi_app)


def _session_cookie(app, **data):
    """Cookie de sesión de Flask firmada (como la que deja /login) y su token CSRF."""
    with app.test_request_context():
        from flask import session
        session.update(data)
        token = generate_csrf()
        return app.session_interface.get_signing_serializer(app).dumps(dict(session)), token


def test_list_and_detail_return_iso_dates(api):
    data = api.get('/api/tracker/jobs').json()
    assert data['count'] == 2
    assert data['jobs'][0]['follow_up'] == '2000-01-01' and data['jobs'][0]['follow_up_due'] is True
    assert data['jobs'][0]['applied_date'] == '1999-12-01T00:00:00'
    assert data['jobs'][1]['follow_up_due'] is False
    assert api.get('/api/tracker/job/1').json()['job']['title'] == 'Data Analyst'
    missing = api.get('/api/tracker/job/9999')
    assert missing.status_code == 404 and missing.json()['success'] is False


def test_add_job_and_required_fields(api, db):
    resp = api.post('/api/tracker/job', json={'title': 'DevOps', 'company': 'CloudCo', 'location': 'Remoto'})
    assert resp.status_code == 200 and resp.json()['job_id'] == 99
    assert db.add_job_to_tracker.call_args[0][0]['location'] == 'Remoto'
    bad = api.post('/api/tracker/job', json={'title': 'Sin empresa'})
    assert bad.status_code == 400 and 'company' in bad.json()['error']
    db.add_job_to_tracker.return_value = {'exists': True, 'job_id': 5}
    assert api.post('/api/tracker/job', json={'title': 'A', 'company': 'B'}).status_code == 409


def test_add_job_validates_dates_before_inserting(api, db):
    resp = api.post('/api/tracker/job', json={'title': 'Dev', 'company': 'Acme', 'follow_up': '31/12/2026'})
    assert resp.status_code == 400 and resp.json()['error'] == 'Fecha inválida: usá AAAA-MM-DD'
    db.add_job_to_tracker.assert_not_called()


def test_add_job_warns_when_dates_not_saved(api, db):
    db.update_tracker_dates.return_value = False
    data = api.post('/api/tracker/job', json={'title': 'Dev', 'company': 'Acme', 'follow_up': '2026-12-31'}).json()
    assert data['success'] and 'no se guardaron' in data['warning']


def test_status_reminder_and_delete(api, db):
    assert api.put('/api/tracker/job/1/status', json={'status': 'interviewing'}).json()['success']
    db.update_job_status.assert_called_with(1, 'interviewing')
    assert api.put('/api/tracker/job/1/status', json={}).status_code == 400
    resp = api.put('/api/tracker/job/1/reminder', json={'follow_up': '2026-11-25', 'deadline': '', 'notes': 'Llamar'})
    assert resp.status_code == 200
    db.update_tracker_dates.assert_called_with(1, date(2026, 11, 25), None, 'Llamar')
    assert api.put('/api/tracker/job/1/reminder', json={'follow_up': '25/11/2026'}).status_code == 400
    assert api.delete('/api/tracker/job/3').json()['success']


def test_internal_errors_do_not_leak_details(api, db):
    db.get_all_tracked_jobs.side_effect = RuntimeError('password=secreta')
    resp = api.get('/api/tracker/jobs')
    assert resp.status_code == 500 and 'secreta' not in resp.text


def test_login_required_with_app_password(api, app, monkeypatch):
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    assert api.get('/api/tracker/jobs').status_code == 401
    cookie, _ = _session_cookie(app, authenticated=True, auth_fp=auth.session_fingerprint(app.secret_key))
    api.cookies.set('session', cookie)
    assert api.get('/api/tracker/jobs').status_code == 200
    monkeypatch.setenv('APP_PASSWORD', 'rotada')
    assert api.get('/api/tracker/jobs').status_code == 401


def test_csrf_required_for_writes(api, app, monkeypatch):
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    cookie, token = _session_cookie(app)
    api.cookies.set('session', cookie)
    job = {'title': 'Dev', 'company': 'Acme'}
    assert api.post('/api/tracker/job', json=job).status_code == 400
    assert api.post('/api/tracker/job', json=job, headers={'X-CSRFToken': 'falso'}).status_code == 400
    assert api.post('/api/tracker/job', json=job, headers={'X-CSRFToken': token}).status_code == 200
    assert api.get('/api/tracker/jobs').status_code == 200


def test_extension_token_and_no_csrf(api, app, monkeypatch):
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    monkeypatch.setenv('EXTENSION_TOKEN', 'tok')
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    url = '/api/tracker/save-from-extension'
    assert api.post(url, json={'title': 'x'}).status_code == 401
    resp = api.post(url, json={'title': 'x', 'apply_url': 'https://x/1'}, headers={'X-Extension-Token': 'tok'})
    assert resp.status_code == 200 and resp.json()['job_id'] == 99


def test_body_limit_returns_json_413(api, app, monkeypatch):
    monkeypatch.setitem(app.config, 'MAX_CONTENT_LENGTH', 10)
    resp = api.post('/api/tracker/save-from-extension', json={'title': 'x' * 100})
    assert resp.status_code == 413 and 'error' in resp.json()


def test_main_serves_tracker_api_with_fastapi():
    import main
    assert main.app.url_path_for('list_jobs') == '/api/tracker/jobs'
    assert main.app.url_path_for('update_reminder', job_id=1) == '/api/tracker/job/1/reminder'
    assert main.app.url_path_for('save_from_extension') == '/api/tracker/save-from-extension'


def test_entry_points_serve_fastapi_app():
    """`python app.py` y el launcher de Windows sirven main:app; con Flask solo, la API del tracker daría 404."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert "'main:app'" in (root / 'app.py').read_text(encoding='utf-8')
    launcher = (root / 'scripts' / 'start_server.ps1').read_text(encoding='utf-8')
    assert 'uvicorn main:app' in launcher and 'waitress' not in launcher
