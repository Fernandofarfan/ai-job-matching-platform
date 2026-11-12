"""Errores de producción a Sentry: solo con SENTRY_DSN y sin datos personales."""
from unittest import mock

from fastapi.testclient import TestClient

import accounts
import error_reporting


def test_setup_is_noop_without_dsn(monkeypatch):
    monkeypatch.delenv('SENTRY_DSN', raising=False)
    monkeypatch.setattr(error_reporting, '_enabled', False)
    with mock.patch('sentry_sdk.init') as init:
        assert error_reporting.setup('web') is False
    init.assert_not_called()
    error_reporting.capture(RuntimeError('x'))  # sin Sentry no hace nada


def test_setup_with_dsn(monkeypatch):
    monkeypatch.setattr(error_reporting, '_enabled', False)
    monkeypatch.setenv('SENTRY_DSN', 'https://key@example.ingest.sentry.io/1')
    monkeypatch.setenv('SENTRY_ENVIRONMENT', 'staging')
    monkeypatch.setenv('K_REVISION', 'empleoia-web-00042')
    monkeypatch.setenv('SENTRY_TRACES_SAMPLE_RATE', 'nope')
    with mock.patch('sentry_sdk.init') as init, mock.patch('sentry_sdk.set_tag') as set_tag:
        assert error_reporting.setup('worker') is True
        assert error_reporting.setup('worker') is True  # una sola vez por proceso
    kwargs = init.call_args.kwargs
    assert init.call_count == 1
    assert kwargs['environment'] == 'staging'
    assert kwargs['release'] == 'empleoia-web-00042'
    assert kwargs['traces_sample_rate'] == 0.0
    assert kwargs['send_default_pii'] is False
    assert kwargs['before_send'] is error_reporting.before_send
    set_tag.assert_called_once_with('component', 'worker')
    monkeypatch.setattr(error_reporting, '_enabled', False)


def test_before_send_strips_personal_data():
    event = {
        'request': {
            'url': 'https://app.example.com/reset?token=abc',
            'headers': {'Cookie': 'session=x', 'Authorization': 'Bearer t', 'User-Agent': 'UA'},
            'cookies': {'session': 'x'}, 'data': {'password': 'p'}, 'query_string': 'token=abc',
        },
        'exception': {'values': [{'type': 'ValueError', 'value': 'no existe ana@example.com'}]},
        'logentry': {'message': 'login de ana@example.com', 'formatted': None},
        'user': {'email': 'ana@example.com', 'ip_address': '1.2.3.4'},
    }
    token = accounts.set_current_user(7)
    try:
        out = error_reporting.before_send(event)
    finally:
        accounts.reset_current_user(token)
    request = out['request']
    assert request['url'] == 'https://app.example.com/reset'
    assert request['headers'] == {'Cookie': '[filtrado]', 'Authorization': '[filtrado]', 'User-Agent': 'UA'}
    assert not {'cookies', 'data', 'query_string'} & set(request)
    assert out['exception']['values'][0]['value'] == 'no existe [email]'
    assert out['logentry']['message'] == 'login de [email]'
    assert out['user'] == {'id': '7'}


def test_before_send_without_user():
    assert error_reporting.before_send({'user': {'email': 'a@b.co'}})['user'] == {}


def test_server_error_is_reported(monkeypatch):
    import main
    app = main.create_app(web_app=main.app.state.web_app)

    @app.get('/api/health/boom')
    def boom():
        raise RuntimeError('falló')

    captured = []
    monkeypatch.setattr(error_reporting, 'capture', captured.append)
    resp = TestClient(app, raise_server_exceptions=False).get('/api/health/boom')
    assert resp.status_code == 500
    assert resp.json() == {'error': 'Error interno'}
    assert [str(e) for e in captured] == ['falló']
