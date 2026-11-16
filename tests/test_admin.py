"""Tests del panel de administración: acceso, bloqueo, segundo factor y borrado de cuentas."""
import pyotp
import pytest

import accounts
import security_events
import two_factor

PASSWORD = 'clave-larga-1'


@pytest.fixture
def bob_client(app, client, accounts_db, monkeypatch, make_client):
    """Ana (primera cuenta, administradora) en `client`; Bob con su propia sesión."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    client.post('/register', data={'accept_terms': 'on', 'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    bob = make_client()
    bob.post('/register', data={'accept_terms': 'on', 'email': 'bob@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    return bob


def _ids():
    return accounts.find_user_id('ana@example.com'), accounts.find_user_id('bob@example.com')


def test_only_admin_sees_panel(client, bob_client):
    ana, _bob = _ids()
    assert bob_client.get('/admin').status_code == 404
    assert bob_client.post(f'/admin/users/{ana}/block').status_code == 404
    assert 'Administración' not in bob_client.get('/account').get_data(as_text=True)
    page = client.get('/admin')
    assert page.status_code == 200 and page.headers['Cache-Control'] == 'no-store'
    assert 'bob@example.com' in page.get_data(as_text=True)
    assert 'Administración' in client.get('/account').get_data(as_text=True)


def test_block_closes_sessions_and_login(client, bob_client):
    _, bob = _ids()
    client.post(f'/admin/users/{bob}/block')
    assert bob_client.get('/account').status_code == 302
    response = bob_client.post('/login', data={'email': 'bob@example.com', 'password': PASSWORD})
    assert 'bloqueada' in response.get_data(as_text=True)
    assert bob_client.get('/account').status_code == 302
    kinds = [e['kind'] for e in security_events.recent(bob)]
    assert 'account_blocked' in kinds and 'login_blocked' in kinds
    client.post(f'/admin/users/{bob}/unblock')
    bob_client.post('/login', data={'email': 'bob@example.com', 'password': PASSWORD})
    assert bob_client.get('/account').status_code == 200


def test_admin_cannot_block_or_delete_itself(client, bob_client):
    ana, _ = _ids()
    client.post(f'/admin/users/{ana}/block')
    client.post(f'/admin/users/{ana}/delete', data={'password': PASSWORD})
    assert not accounts.get_user(ana)['disabled']


def test_blocked_accounts_get_no_reminders(client, bob_client):
    ana, bob = _ids()
    accounts.set_disabled(bob, True)
    assert accounts.owner_ids(active_only=True) == [ana]
    assert accounts.owner_ids() == [ana, bob]


def test_reset_two_factor_requires_password(client, bob_client):
    _, bob = _ids()
    secret = two_factor.start_setup(bob)
    assert two_factor.enable(bob, pyotp.TOTP(secret).now())
    client.post(f'/admin/users/{bob}/2fa/reset', data={'password': 'mal'})
    assert two_factor.is_enabled(bob)
    client.post(f'/admin/users/{bob}/2fa/reset', data={'password': PASSWORD})
    assert not two_factor.is_enabled(bob)
    assert 'two_factor_reset' in [e['kind'] for e in security_events.recent(bob)]


def test_delete_requires_password(client, bob_client):
    ana, bob = _ids()
    client.post(f'/admin/users/{bob}/delete', data={'password': 'mal'})
    assert accounts.get_user(bob)
    client.post(f'/admin/users/{bob}/delete', data={'password': PASSWORD})
    assert accounts.get_user(bob) is None
    assert 'admin_deleted_account' in [e['kind'] for e in security_events.recent(ana)]


def test_admin_email_decides_admin(client, bob_client, monkeypatch):
    ana, bob = _ids()
    assert accounts.is_admin(ana) and not accounts.is_admin(bob)
    monkeypatch.setenv('ADMIN_EMAIL', 'bob@example.com')
    assert accounts.is_admin(bob) and not accounts.is_admin(ana)


def test_blocked_account_extension_token_rejected(client, bob_client):
    import auth
    import integrations
    _, bob = _ids()
    token = integrations.new_extension_token(bob)
    assert auth.extension_token_user(token) == bob
    accounts.set_disabled(bob, True)
    assert auth.extension_token_user(token) is None
