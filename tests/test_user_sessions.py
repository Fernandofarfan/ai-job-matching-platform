"""Tests de las sesiones abiertas: listarlas, cerrarlas y que una cerrada deje de valer."""
from datetime import datetime, timedelta

import pytest

import accounts
import user_sessions

PASSWORD = 'clave-larga-1'
CHROME = 'Mozilla/5.0 Chrome/130'
FIREFOX = 'Mozilla/5.0 Firefox/132'


@pytest.fixture
def two_browsers(client, app, accounts_db):
    """La misma cuenta abierta en dos navegadores (dos clientes con cookies separadas)."""
    client.post('/register', data={'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD},
                headers={'User-Agent': CHROME})
    other = type(client)(app)
    other.post('/login', data={'email': 'ana@example.com', 'password': PASSWORD}, headers={'User-Agent': FIREFOX})
    return client, other


def _uid():
    return accounts.find_user_id('ana@example.com')


def test_account_lists_both_sessions_marking_current(two_browsers):
    chrome, _firefox = two_browsers
    page = chrome.get('/account').get_data(as_text=True)
    assert CHROME in page and FIREFOX in page and 'Este navegador' in page
    sessions = user_sessions.active(_uid())
    assert len(sessions) == 2 and not any(s['current'] for s in sessions)


def test_revoke_one_session_logs_that_browser_out(two_browsers):
    chrome, firefox = two_browsers
    target = next(s for s in user_sessions.active(_uid()) if s['user_agent'] == FIREFOX)
    assert chrome.post(f"/account/sessions/{target['id']}/revoke").status_code == 302
    assert firefox.get('/account').status_code == 302
    assert chrome.get('/account').status_code == 200


def test_revoke_current_session_logs_out(two_browsers):
    chrome, firefox = two_browsers
    target = next(s for s in user_sessions.active(_uid()) if s['user_agent'] == CHROME)
    response = chrome.post(f"/account/sessions/{target['id']}/revoke")
    assert '/login' in response.headers['Location']
    assert chrome.get('/account').status_code == 302
    assert firefox.get('/account').status_code == 200


def test_revoke_others_keeps_current(two_browsers):
    chrome, firefox = two_browsers
    chrome.post('/account/sessions/revoke_others')
    assert firefox.get('/account').status_code == 302
    assert chrome.get('/account').status_code == 200
    assert len(user_sessions.active(_uid())) == 1


def test_cannot_revoke_session_of_other_account(two_browsers, monkeypatch):
    chrome, _ = two_browsers
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    beto = accounts.register('beto@example.com', PASSWORD)
    sid = user_sessions.create(beto, '1.2.3.4', 'BetoBrowser')
    beto_session = user_sessions.active(beto)[0]
    chrome.post(f"/account/sessions/{beto_session['id']}/revoke")
    assert user_sessions.is_active(beto, sid)
    assert 'BetoBrowser' not in chrome.get('/account').get_data(as_text=True)


def test_logout_and_password_change_close_sessions(two_browsers):
    chrome, firefox = two_browsers
    firefox.post('/logout')
    assert len(user_sessions.active(_uid())) == 1
    other = type(chrome)(chrome.app.state.flask_app)
    other.post('/login', data={'email': 'ana@example.com', 'password': PASSWORD})
    chrome.post('/account/password', data={'current': PASSWORD, 'password': 'otra-clave-larga',
                                           'confirm': 'otra-clave-larga'})
    assert other.get('/account').status_code == 302
    assert chrome.get('/account').status_code == 200
    assert len(user_sessions.active(_uid())) == 1


def test_session_without_sid_is_rejected(_accounts_sqlite):
    uid = accounts.register('ana@example.com', PASSWORD)
    assert not user_sessions.is_active(uid, None)
    assert not user_sessions.is_active(uid, 'inventado')
    sid = user_sessions.create(uid)
    assert user_sessions.is_active(uid, sid) and not user_sessions.is_active(uid + 1, sid)


def test_expired_session_is_inactive_and_purged(_accounts_sqlite):
    uid = accounts.register('ana@example.com', PASSWORD)
    sid = user_sessions.create(uid)
    old = datetime.now() - 3 * user_sessions.LIFETIME
    with accounts._sessions()() as session:
        session.query(user_sessions.UserSession).update({'last_seen_at': old, 'created_at': old})
        session.commit()
    assert not user_sessions.is_active(uid, sid)
    assert user_sessions.active(uid) == []
    assert user_sessions.purge() == 1


def test_last_seen_is_touched_only_every_few_minutes(_accounts_sqlite):
    uid = accounts.register('ana@example.com', PASSWORD)
    sid = user_sessions.create(uid)
    before = datetime.now() - timedelta(minutes=10)
    with accounts._sessions()() as session:
        session.query(user_sessions.UserSession).update({'last_seen_at': before})
        session.commit()
    user_sessions.is_active(uid, sid)
    assert user_sessions.active(uid)[0]['last_seen_at'] > before
