"""Tareas del worker: documentos en lote, limpieza de temporales y conexión con Gmail (sin Google)."""
import os
import time
from unittest import mock

import pytest

from tasks import ai_tasks
from tests.test_gmail_tracker import gmail_tracker  # noqa: F401  (fixture: clientes de Google simulados)


def test_documents_batch_reports_progress_and_errors(monkeypatch):
    import document_batch
    task = mock.Mock()

    def run(kind, filename, num_jobs, resume, progress):
        progress(1, 2)
        return {'success': True, 'kind': kind, 'resume': resume}
    monkeypatch.setattr(document_batch, 'run', run)
    monkeypatch.setattr('services.profiles.get_resume_text_from_profile', lambda: 'CV')
    assert ai_tasks._generate_documents_batch(task, 'cover', 'r.csv', 2)['resume'] == 'CV'
    assert task.update_state.call_args.kwargs['meta']['progress'] == 50

    def fail(*a, **k):
        raise document_batch.BatchError('sin CV')
    monkeypatch.setattr(document_batch, 'run', fail)
    assert ai_tasks._generate_documents_batch(task, 'cover', 'r.csv', 2) == {'success': False, 'error': 'sin CV'}


def test_cleanup_removes_only_old_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'temp' / 'resumes'
    folder.mkdir(parents=True)
    old, new = folder / 'old.txt', folder / 'new.txt'
    old.write_text('x')
    new.write_text('x')
    os.utime(old, (time.time() - 10 * 86400,) * 2)
    assert ai_tasks.cleanup_old_temp_files(days=7) == {'cleaned': 1, 'cutoff_days': 7}
    assert new.exists() and not old.exists()


@pytest.fixture
def creds(monkeypatch, gmail_tracker):  # noqa: F811
    fake = mock.Mock(valid=True)
    cls = mock.Mock()
    cls.from_authorized_user_info.return_value = fake
    cls.from_authorized_user_file.return_value = fake
    monkeypatch.setattr(gmail_tracker, 'Credentials', cls)
    monkeypatch.setattr(gmail_tracker, 'build', lambda *a, **k: 'servicio')
    monkeypatch.setattr(gmail_tracker, 'Request', mock.Mock())
    return fake


def test_service_from_token_refreshes_and_saves(creds, gmail_tracker):  # noqa: F811
    assert gmail_tracker.service_from_token('{}') == 'servicio'
    creds.valid, creds.expired, creds.refresh_token = False, True, 'r'
    creds.to_json.return_value = '{"nuevo": 1}'
    saved = []
    assert gmail_tracker.service_from_token('{}', saved.append) == 'servicio'
    assert saved == ['{"nuevo": 1}']
    creds.refresh_token = None
    assert gmail_tracker.service_from_token('{}') is None


def test_legacy_service(creds, gmail_tracker, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.chdir(tmp_path)
    assert gmail_tracker.get_gmail_service() is None  # sin token.json ni credentials.json
    (tmp_path / 'token.json').write_text('{}')
    creds.has_scopes.return_value = True
    assert gmail_tracker.get_gmail_service() == 'servicio'
    creds.valid, creds.expired, creds.refresh_token = False, True, 'r'
    creds.to_json.return_value = '{}'
    assert gmail_tracker.get_gmail_service() == 'servicio'


def test_check_interview_emails_per_account(monkeypatch, gmail_tracker):  # noqa: F811
    import accounts
    import integrations
    monkeypatch.setattr(integrations, 'gmail_user_ids', lambda: [1, 2])
    monkeypatch.setattr(integrations, 'gmail_token', lambda uid: '{}')
    monkeypatch.setattr(integrations, 'legacy_allowed', lambda uid, kind: False)
    monkeypatch.setattr(accounts, 'first_user_id', lambda: 1)

    def service(token, on_refresh):
        if token == 'roto':
            raise ValueError
        return 'servicio'
    monkeypatch.setattr(gmail_tracker, 'service_from_token', service)
    monkeypatch.setattr(gmail_tracker, '_process_mailbox', lambda s: 'ok')
    assert set(gmail_tracker.check_interview_emails()) == {1, 2}
    monkeypatch.setattr(integrations, 'gmail_token', lambda uid: 'roto')
    assert 'vencido' in gmail_tracker.check_interview_emails()[1]
    monkeypatch.setattr(integrations, 'gmail_user_ids', list)
    monkeypatch.setattr(integrations, 'legacy_allowed', lambda uid, kind: True)
    monkeypatch.setattr(gmail_tracker, 'get_gmail_service', lambda: None)
    assert 'skipped' in gmail_tracker.check_interview_emails()
