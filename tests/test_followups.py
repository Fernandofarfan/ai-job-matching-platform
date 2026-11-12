"""Recordatorios de seguimiento del tracker."""
from datetime import date, datetime
from unittest import mock

import pytest

from tasks import notification_tasks as nt


@pytest.fixture
def tracker_db(app, monkeypatch):
    """db_manager que usan las rutas del tracker."""
    db = mock.Mock()
    monkeypatch.setitem(app.view_functions['api_update_job_reminder'].__globals__, 'db_manager', db)
    return db

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


def test_reminder_api(client, tracker_db):
    tracker_db.update_tracker_dates.return_value = True
    resp = client.put('/api/tracker/job/1/reminder', json={'follow_up': '2026-11-25', 'deadline': '', 'notes': 'Llamar'})
    assert resp.status_code == 200
    tracker_db.update_tracker_dates.assert_called_with(1, date(2026, 11, 25), None, 'Llamar')
    bad = client.put('/api/tracker/job/1/reminder', json={'follow_up': '25/11/2026'})
    assert bad.status_code == 400


def test_tracker_jobs_return_iso_dates_and_due_flag(client, tracker_db):
    tracker_db.get_all_tracked_jobs.return_value = [
        {'id': 1, 'title': 'Dev', 'status': 'applied', 'follow_up': date(2000, 1, 1), 'applied_date': datetime(1999, 12, 1)},
        {'id': 2, 'title': 'QA', 'status': 'rejected', 'follow_up': date(2000, 1, 1)},
    ]
    jobs = client.get('/api/tracker/jobs').get_json()['jobs']
    assert jobs[0]['follow_up'] == '2000-01-01' and jobs[0]['follow_up_due'] is True
    assert jobs[0]['applied_date'] == '1999-12-01T00:00:00'
    assert jobs[1]['follow_up_due'] is False


def test_add_job_validates_dates_before_inserting(client, tracker_db):
    resp = client.post('/api/tracker/job', json={'title': 'Dev', 'company': 'Acme', 'follow_up': '31/12/2026'})
    assert resp.status_code == 400
    tracker_db.add_job_to_tracker.assert_not_called()


def test_add_job_warns_when_dates_not_saved(client, tracker_db):
    tracker_db.add_job_to_tracker.return_value = 7
    tracker_db.update_tracker_dates.return_value = False
    data = client.post('/api/tracker/job', json={'title': 'Dev', 'company': 'Acme', 'follow_up': '2026-12-31'}).get_json()
    assert data['success'] and data['job_id'] == 7 and 'no se guardaron' in data['warning']
