"""Solicitudes de conexión de LinkedIn con el bot simulado."""
from unittest import mock

import pytest

import i18n
from services import connections
from services.state import job_status


@pytest.fixture
def bot(monkeypatch):
    instance = mock.Mock(total_connections_sent=4)
    instance.login_with_credentials.return_value = True
    instance.process_company.return_value = True
    instance.process_general_search.return_value = True
    monkeypatch.setattr(connections, 'linkedinConnections', mock.Mock(return_value=instance))
    monkeypatch.setattr(connections.time, 'sleep', lambda _: None)
    job_status['connection_requests'] = {'status': 'idle', 'progress': 0, 'message': '', 'stop_requested': False}
    return instance


def _message():
    return i18n.render_message(job_status['connection_requests']['message'])


CREDS = {'linkedin_email': 'a@b.co', 'linkedin_password': 'clave'}


def test_companies_mode_sends_to_each_company(bot):
    connections.run_connection_requests(CREDS, ['Acme', 'Globex'], 'Hola')
    assert [c.kwargs['company'] for c in bot.process_company.call_args_list] == ['Acme', 'Globex']
    assert job_status['connection_requests']['status'] == 'completed'
    assert _message() == 'Se enviaron 8 solicitudes de conexión'
    assert bot.cleanup.call_count == 2


def test_general_mode_without_company_list_completes(bot):
    """La búsqueda general llega sin empresas: antes dividía por cero y terminaba como fallida."""
    connections.run_connection_requests(CREDS, [], 'Hola', search_mode='general', search_term='python')
    bot.process_general_search.assert_called_once()
    assert job_status['connection_requests']['status'] == 'completed'
    assert job_status['connection_requests']['progress'] == 100


def test_cookie_login_fallback_and_failure(bot):
    bot.login_with_credentials.return_value = False
    bot.login_with_cookie.return_value = False
    connections.run_connection_requests({**CREDS, 'linkedin_token': 't'}, ['Acme'], 'Hola')
    bot.login_with_cookie.assert_called_once()
    bot.process_company.assert_not_called()
    assert _message() == 'Se enviaron 0 solicitudes de conexión'


def test_stop_requested_stops_before_next_company(bot):
    job_status['connection_requests']['stop_requested'] = True
    connections.run_connection_requests(CREDS, ['Acme'], 'Hola')
    assert job_status['connection_requests']['status'] == 'completed'
    bot.process_company.assert_not_called()


def test_errors_and_failed_companies_are_reported(bot):
    bot.process_company.side_effect = [False, RuntimeError('se cayó')]
    connections.run_connection_requests(CREDS, ['Acme', 'Globex'], 'Hola')
    assert job_status['connection_requests']['status'] == 'completed'
    assert _message() == 'Se enviaron 0 solicitudes de conexión'
