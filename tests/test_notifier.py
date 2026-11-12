"""NotificationManager: Celery o envío directo, y seguimientos vencidos."""
from datetime import date, datetime, timedelta
from unittest import mock

import pytest

import notifier as notifier_module
import tasks.notification_tasks as tasks


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(notifier_module.NotificationManager, '_check_celery_available', lambda self: False)
    return notifier_module.NotificationManager()


@pytest.mark.parametrize('method,task,args', [
    ('send_followup_reminder', 'send_followup_reminder', ({'Title': 'Dev'}, 'a@b.co')),
    ('send_new_jobs_digest', 'send_new_jobs_digest', ([{'Title': 'Dev'}], 'a@b.co')),
    ('send_weekly_summary', 'send_weekly_summary', ({'applied': 3}, 'a@b.co')),
])
def test_sends_directly_or_through_celery(manager, monkeypatch, method, task, args):
    fake = mock.Mock()
    monkeypatch.setattr(tasks, task, fake)
    assert getattr(manager, method)(*args) is True
    fake.assert_called_once_with(*args)
    manager._use_celery = True
    assert getattr(manager, method)(*args) is True
    fake.delay.assert_called_once_with(*args)
    fake.delay.side_effect = RuntimeError('sin broker')
    assert getattr(manager, method)(*args) is False


def test_digest_needs_jobs_and_email(manager):
    assert manager.send_new_jobs_digest([], 'a@b.co') is False
    assert manager.send_new_jobs_digest([{'Title': 'Dev'}], '') is False


def test_check_upcoming_followups(manager):
    today = date.today()
    apps = [
        {'id': 1, 'follow_up': today.isoformat()},
        {'id': 2, 'follow_up': datetime.now() - timedelta(days=2)},
        {'id': 3, 'follow_up': today + timedelta(days=3)},
        {'id': 4, 'follow_up': 'no es fecha'},
        {'id': 5},
    ]
    assert [a['id'] for a in manager.check_upcoming_followups(apps)] == [1, 2]


def test_notification_config_and_test_email(manager, monkeypatch):
    monkeypatch.setenv('SMTP_USER', 'bot@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'x')
    monkeypatch.delenv('NOTIFICATION_EMAIL', raising=False)
    assert manager.get_notification_config()['smtp_configured'] is True
    sent = []
    monkeypatch.setattr(tasks, '_send_email', lambda to, subject, html: sent.append(to) or True)
    assert manager.test_email_config()['success'] is True
    assert sent == ['bot@example.com']
    monkeypatch.delenv('SMTP_USER')
    assert manager.test_email_config()['success'] is False
