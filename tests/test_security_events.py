"""Tests del registro de eventos de seguridad y del aviso de login nuevo."""
from datetime import datetime, timedelta
from unittest import mock

import inspect

import pytest

import accounts
import security_events

PASSWORD = 'clave-larga-1'
CHROME = 'Mozilla/5.0 Chrome/130'
FIREFOX = 'Mozilla/5.0 Firefox/132'


@pytest.fixture
def ana(client, accounts_db, monkeypatch):
    """Primera cuenta registrada por el formulario y sesión cerrada."""
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://empleoia.example')
    client.post('/register', data={'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD},
                headers={'User-Agent': CHROME})
    client.post('/logout')
    return accounts.find_user_id('ana@example.com')


def _login(client, password=PASSWORD, agent=CHROME):
    return client.post('/login', data={'email': 'ana@example.com', 'password': password},
                       headers={'User-Agent': agent})


@pytest.fixture
def sent(monkeypatch, app):
    """Emails mandados (el aviso corre en un thread: se ejecuta en línea)."""
    outbox = []
    routes = inspect.unwrap(app.view_functions['account']).__globals__
    monkeypatch.setitem(routes, '_deliver', lambda to, subject, body, link, cta: outbox.append(
        (to, subject, body, link)) or True)
    monkeypatch.setattr(accounts, 'thread', lambda target, args=(), **kw: mock.Mock(start=lambda: target(*args)))
    return outbox


def test_register_login_and_failure_are_recorded(client, ana, sent):
    """Registro, login correcto y contraseña incorrecta quedan en el registro de la cuenta."""
    _login(client, 'mal')
    _login(client)
    kinds = [e['kind'] for e in security_events.recent(ana)]
    assert kinds == ['login', 'login_failed', 'register']
    assert security_events.recent(ana)[0]['user_agent'] == CHROME


def test_first_login_from_known_browser_sends_no_alert(client, ana, sent):
    """El primer login y los siguientes desde el mismo navegador no avisan."""
    _login(client)
    client.post('/logout')
    _login(client)
    assert sent == []


def test_login_from_new_browser_sends_alert(client, ana, sent):
    """Un login desde otro navegador manda el aviso con el user agent escapado."""
    _login(client)
    client.post('/logout')
    _login(client, agent='<script>Firefox</script>')
    assert len(sent) == 1
    to, subject, body, link = sent[0]
    assert to == 'ana@example.com' and 'Nuevo inicio' in subject and link.endswith('/account')
    assert '<script>' not in body and '&lt;script&gt;' in body


def test_login_alerts_can_be_disabled(client, ana, sent, monkeypatch):
    monkeypatch.setenv('LOGIN_ALERTS', 'false')
    _login(client)
    client.post('/logout')
    _login(client, agent=FIREFOX)
    assert sent == []


def test_account_page_shows_only_own_events(client, ana, sent, monkeypatch):
    """Mi cuenta lista la actividad de la cuenta, no la de otras."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    beto = accounts.register('beto@example.com', PASSWORD)
    security_events.record(beto, 'login', '203.0.113.9', 'BetoBrowser')
    _login(client)
    client.post('/account/password', data={'current': PASSWORD, 'password': 'otra-clave-larga',
                                           'confirm': 'otra-clave-larga'})
    page = client.get('/account').get_data(as_text=True)
    assert 'Contraseña cambiada' in page and 'Inicio de sesión' in page
    assert 'BetoBrowser' not in page and '203.0.113.9' not in page


def test_unknown_kind_and_missing_user_are_ignored(_accounts_sqlite):
    assert security_events.record(None, 'login') is False
    assert security_events.record(1, 'inventado') is False


def test_purge_removes_old_events(_accounts_sqlite):
    security_events.record(1, 'login', '1.2.3.4', CHROME)
    with accounts._sessions()() as session:
        old = security_events.SecurityEvent(user_id=1, kind='login', created_at=datetime.now() - timedelta(days=200))
        session.add(old)
        session.commit()
    assert security_events.purge(180) == 1
    assert len(security_events.recent(1)) == 1


def test_account_deletion_removes_events(_accounts_sqlite):
    uid = accounts.register('ana@example.com', PASSWORD)
    security_events.record(uid, 'login', '1.2.3.4', CHROME)
    accounts.delete_account(uid)
    assert security_events.recent(uid) == []


def test_db_error_does_not_break_login(client, ana, sent, monkeypatch):
    """Si la tabla falla, el login sigue funcionando."""
    monkeypatch.setattr(security_events, 'is_new_device', mock.Mock(side_effect=RuntimeError('db')))
    monkeypatch.setattr(security_events, 'SecurityEvent', mock.Mock(side_effect=RuntimeError('db')))
    assert _login(client).status_code == 302


def test_register_is_recorded_when_verification_is_required(client, accounts_db, monkeypatch):
    """Con verificación obligatoria el registro redirige al login, pero igual queda el evento."""
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION', 'true')
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    accounts.register('admin@example.com', PASSWORD)
    client.post('/register', data={'email': 'nuevo@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    uid = accounts.find_user_id('nuevo@example.com')
    assert [e['kind'] for e in security_events.recent(uid)] == ['register']
