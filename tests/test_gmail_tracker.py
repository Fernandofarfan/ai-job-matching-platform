"""Lector de invitaciones a entrevistas en Gmail."""
import importlib
import sys
from unittest import mock

import pytest

import ai_engine

# El CI de tests unitarios no instala los clientes de Google: alcanza con módulos vacíos
GOOGLE_MODULES = ('googleapiclient', 'googleapiclient.discovery', 'google_auth_oauthlib', 'google_auth_oauthlib.flow',
                  'google.auth', 'google.auth.transport', 'google.auth.transport.requests', 'google.oauth2',
                  'google.oauth2.credentials')


@pytest.fixture
def gmail_tracker():
    with mock.patch.dict(sys.modules, {name: mock.MagicMock() for name in GOOGLE_MODULES}):
        sys.modules.pop('tasks.gmail_tracker', None)
        yield importlib.import_module('tasks.gmail_tracker')
    sys.modules.pop('tasks.gmail_tracker', None)


def _service():
    service = mock.MagicMock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {'messages': [{'id': 'm1'}]}
    messages.get.return_value.execute.return_value = {'payload': {'headers': [
        {'name': 'Subject', 'value': 'Entrevista'}, {'name': 'From', 'value': 'rrhh@acme.com'}]}}
    return service, messages


def test_mail_stays_unread_when_gemini_does_not_answer(gmail_tracker):
    """Sin permiso para la IA (o sin cuota) el correo no se marca leído: se revisa cuando Gemini responda."""
    service, messages = _service()
    db = mock.MagicMock()
    db.get_all_tracked_jobs.return_value = [{'id': 1, 'company': 'Acme', 'status': 'applied'}]
    with mock.patch('db_config.db_manager', db), \
            mock.patch.object(ai_engine, '_call_gemini', return_value=ai_engine.AI_CONSENT_ERROR):
        assert gmail_tracker._process_mailbox(service) == '0 postulaciones actualizadas automáticamente.'
    messages.modify.assert_not_called()
    db.update_job_status.assert_not_called()


def test_mail_marked_read_after_match(gmail_tracker):
    service, messages = _service()
    db = mock.MagicMock()
    db.get_all_tracked_jobs.return_value = [{'id': 1, 'company': 'Acme', 'status': 'applied'}]
    with mock.patch('db_config.db_manager', db), mock.patch.object(ai_engine, '_call_gemini', return_value='Acme'):
        assert gmail_tracker._process_mailbox(service) == '1 postulaciones actualizadas automáticamente.'
    db.update_job_status.assert_called_once_with(1, 'interviewing')
    messages.modify.assert_called_once()
