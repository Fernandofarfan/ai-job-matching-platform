"""Recordatorios de seguimiento del tracker."""
from datetime import date, datetime
from unittest import mock

from tasks import notification_tasks as nt

TODAY = date(2026, 11, 20)



def _job(**kw):
    base = {'id': 1, 'title': 'Dev', 'company': 'Acme', 'status': 'applied', 'applied_date': datetime(2026, 11, 1),
            'follow_up': None, 'last_reminder_at': None, 'job_link': 'https://x/1'}
    return {**base, **kw}


def test_explicit_follow_up_due_once():
    assert [j['id'] for j in nt.due_followups([_job(follow_up=date(2026, 11, 20))], TODAY)] == [1]
    assert nt.due_followups([_job(follow_up=date(2026, 11, 21))], TODAY) == []
    reminded = _job(follow_up=date(2026, 11, 18), last_reminder_at=datetime(2026, 11, 19, 9))
    assert nt.due_followups([reminded], TODAY) == []
    rescheduled = _job(follow_up=date(2026, 11, 20), last_reminder_at=datetime(2026, 11, 19, 9))
    assert len(nt.due_followups([rescheduled], TODAY)) == 1


def test_default_days_after_applying():
    assert nt.due_followups([_job()], TODAY, default_days=7)[0]['follow_up'] == date(2026, 11, 8)
    assert nt.due_followups([_job(applied_date=datetime(2026, 11, 15))], TODAY, default_days=7) == []
    assert nt.due_followups([_job()], TODAY, default_days=0) == []
    assert nt.due_followups([_job(status='interviewing')], TODAY, default_days=7) == []
    assert len(nt.due_followups([_job(status='interviewing', follow_up='2026-11-19')], TODAY)) == 1


def test_digest_escapes_html():
    jobs = nt.due_followups([_job(title='<b>Dev</b>', follow_up=TODAY)], TODAY)
    text = nt.followup_telegram_text(jobs)
    assert '&lt;b&gt;Dev&lt;/b&gt;' in text and 'href="https://x/1"' in text
    assert '&lt;b&gt;Dev' in nt.followup_email_html(jobs)


def test_task_sends_one_digest_and_marks(monkeypatch):
    db = mock.Mock()
    db.get_followup_candidates.return_value = [_job(follow_up=date(2000, 1, 1)), _job(id=2, follow_up=date(2999, 1, 1))]
    monkeypatch.setattr('db_config.db_manager', db, raising=False)
    monkeypatch.setattr(nt, 'email_configured', lambda: False)
    monkeypatch.setattr(nt, 'telegram_configured', lambda: True)
    send = mock.Mock(return_value=True)
    monkeypatch.setattr(nt, 'send_telegram', send)
    assert nt.check_and_send_followup_reminders() == {'sent': 1}
    send.assert_called_once()
    db.mark_reminded.assert_called_once_with([1])


def test_task_keeps_pending_when_delivery_fails(monkeypatch):
    db = mock.Mock()
    db.get_followup_candidates.return_value = [_job(follow_up=date(2000, 1, 1))]
    monkeypatch.setattr('db_config.db_manager', db, raising=False)
    monkeypatch.setattr(nt, 'email_configured', lambda: False)
    monkeypatch.setattr(nt, 'telegram_configured', lambda: True)
    monkeypatch.setattr(nt, 'send_telegram', lambda text: False)
    assert nt.check_and_send_followup_reminders()['sent'] == 0
    db.mark_reminded.assert_not_called()


def test_task_without_channels(monkeypatch):
    monkeypatch.setattr(nt, 'email_configured', lambda: False)
    monkeypatch.setattr(nt, 'telegram_configured', lambda: False)
    assert nt.check_and_send_followup_reminders()['sent'] == 0
