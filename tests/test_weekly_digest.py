"""Resumen semanal por email: qué entra, cuándo no se manda y preferencia en Mi cuenta."""
from datetime import date, datetime, timedelta
from unittest import mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import accounts
import job_alerts
from tasks import notification_tasks as nt

TODAY = date(2026, 11, 20)
PASSWORD = 'clave-larga-1'


def _job(**kw):
    base = {'id': 1, 'title': 'Dev', 'company': 'Acme', 'status': 'applied', 'applied_date': datetime(2026, 11, 1),
            'follow_up': None, 'deadline': None, 'job_link': 'https://x/1'}
    return {**base, **kw}


def test_data_picks_waiting_upcoming_and_interviews():
    jobs = [
        _job(id=1),
        _job(id=2, applied_date=datetime(2026, 11, 18)),
        _job(id=3, status='interviewing', follow_up=date(2026, 11, 22)),
        _job(id=4, status='saved', deadline=date(2026, 11, 27)),
        _job(id=5, status='saved', deadline=date(2026, 11, 28)),
        _job(id=6, status='rejected', follow_up=date(2026, 11, 19)),
    ]
    data = nt.weekly_digest_data(jobs, 3, [], TODAY)
    assert [(j['id'], j['days']) for j in data['waiting']] == [(1, 19)]
    assert [(j['id'], j['kind']) for j in data['upcoming']] == [(3, 'follow_up'), (4, 'deadline')]
    assert data['interviewing'] == 1 and data['new_total'] == 3
    assert not nt.weekly_digest_empty(data)
    assert nt.weekly_digest_empty(nt.weekly_digest_data([_job(applied_date=datetime(2026, 11, 19))], 0, [], TODAY))


def test_html_escapes_and_only_links_http():
    data = nt.weekly_digest_data([_job(title='<b>x</b>', job_link='javascript:alert(1)')], 1,
                                 [{'title': 'Py', 'company': '<i>', 'url': 'https://ok/1', 'source': 'Bumeran'}], TODAY)
    html = nt.weekly_digest_html(data)
    assert '&lt;b&gt;x&lt;/b&gt;' in html and 'javascript:' not in html
    assert 'href="https://ok/1"' in html and '&lt;i&gt;' in html
    assert '/account' in html


@pytest.fixture
def alerts_db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    job_alerts.Base.metadata.create_all(engine)
    job_alerts.configure(sessionmaker(bind=engine))
    yield sessionmaker(bind=engine)
    job_alerts.configure(None)


def test_seen_since_counts_only_recent_and_own(alerts_db):
    old = datetime.now() - timedelta(days=10)
    with alerts_db() as session:
        session.add_all([job_alerts.SeenJob(fingerprint=f'f{i}', user_id=1, title=f'T{i}') for i in range(3)])
        session.add(job_alerts.SeenJob(fingerprint='old', user_id=1, title='Vieja', first_seen_at=old))
        session.add(job_alerts.SeenJob(fingerprint='otro', user_id=2, title='Ajena'))
        session.commit()
    with accounts.as_user(1):
        total, recent = job_alerts.seen_since(datetime.now() - timedelta(days=7), limit=2)
    assert total == 3 and len(recent) == 2 and {r['title'] for r in recent} <= {'T0', 'T1', 'T2'}


def _users(_accounts_sqlite):
    on = accounts.register('on@example.com', PASSWORD)
    off = accounts.register('off@example.com', PASSWORD)
    accounts.set_weekly_digest(off, False)
    return on, off


def test_task_sends_only_to_accounts_with_news_and_digest_on(monkeypatch, _accounts_sqlite):
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.setenv('LOGIN_REQUIRED', 'true')
    on, off = _users(_accounts_sqlite)
    db = mock.Mock()
    db.get_all_tracked_jobs.return_value = [_job(applied_date=datetime.now() - timedelta(days=30))]
    monkeypatch.setattr('db_config.db_manager', db, raising=False)
    monkeypatch.setattr(job_alerts, 'seen_since', lambda since: (0, []))
    monkeypatch.setattr(nt, 'email_configured', lambda: True)
    send = mock.Mock(return_value=True)
    monkeypatch.setattr(nt, '_send_email', send)
    assert nt.send_weekly_digests() == {'sent': 1, 'users': 2}
    assert send.call_args[0][0] == 'on@example.com'
    db.get_all_tracked_jobs.return_value = []
    assert nt.send_weekly_digests()['sent'] == 0


def test_task_without_smtp(monkeypatch):
    monkeypatch.setattr(nt, 'email_configured', lambda: False)
    assert nt.send_weekly_digests()['sent'] == 0


def test_account_toggle(client, accounts_db):
    client.post('/register', data={'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD,
                                   'accept_terms': 'on'})
    uid = accounts.find_user_id('ana@example.com')
    assert accounts.get_user(uid)['weekly_digest']
    assert 'weeklyDigestBtn' in client.get('/account').get_data(as_text=True)
    assert client.post('/account/weekly_digest', data={'enabled': '0'}).status_code in (302, 303)
    assert not accounts.get_user(uid)['weekly_digest']
    client.post('/account/weekly_digest', data={'enabled': '1'})
    assert accounts.get_user(uid)['weekly_digest']
