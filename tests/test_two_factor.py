"""Tests del segundo factor TOTP: configuración, login, recuperación y desactivación."""
import re
import time

import pyotp
import pytest
from cryptography.fernet import Fernet

import accounts
import security_events
import two_factor

PASSWORD = 'clave-larga-1'


@pytest.fixture
def ana(client, accounts_db):
    """Primera cuenta con sesión abierta."""
    client.post('/register', data={'email': 'ana@example.com', 'password': PASSWORD, 'confirm': PASSWORD})
    return accounts.find_user_id('ana@example.com')


def _code(secret, offset=0):
    totp = pyotp.TOTP(secret)
    return totp.generate_otp(int(time.time()) // 30 + offset)


def _enable(client):
    """Configura y activa el segundo factor desde Mi cuenta; devuelve secreto y códigos."""
    page = client.post('/account/2fa/setup', data={'password': PASSWORD}).get_data(as_text=True)
    secret = re.search(r'id="totp-secret">([A-Z2-7]+)<', page).group(1)
    assert '<svg' in page
    page = client.post('/account/2fa/enable', data={'code': _code(secret)}).get_data(as_text=True)
    codes = re.findall(r'<li>([0-9a-f]{5}(?:-[0-9a-f]{5}){3})</li>', page)
    return secret, codes


def _login(client):
    client.post('/logout')
    return client.post('/login', data={'email': 'ana@example.com', 'password': PASSWORD})


def test_setup_shows_qr_and_recovery_codes_once(client, ana):
    response = client.post('/account/2fa/setup', data={'password': PASSWORD})
    assert response.headers['Cache-Control'] == 'no-store'
    secret = re.search(r'id="totp-secret">([A-Z2-7]+)<', response.get_data(as_text=True)).group(1)
    assert not two_factor.is_enabled(ana)
    bad = client.post('/account/2fa/enable', data={'code': '000000' if _code(secret) != '000000' else '111111'})
    assert not two_factor.is_enabled(ana) and 'totp-secret' in bad.get_data(as_text=True)
    response = client.post('/account/2fa/enable', data={'code': _code(secret)})
    codes = re.findall(r'<li>([0-9a-f]{5}(?:-[0-9a-f]{5}){3})</li>', response.get_data(as_text=True))
    assert two_factor.is_enabled(ana) and len(codes) == 10
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'recovery-codes' not in client.get('/account').get_data(as_text=True)
    assert 'two_factor_enabled' in [e['kind'] for e in security_events.recent(ana)]


def test_login_requires_code(client, ana):
    secret, _ = _enable(client)
    response = _login(client)
    assert response.headers['Location'].endswith('/login/2fa')
    assert client.get('/account').status_code == 302
    assert client.post('/login/2fa', data={'code': 'abcdef'}).status_code == 200
    assert client.get('/account').status_code == 302
    assert client.post('/login/2fa', data={'code': _code(secret, 1)}).status_code == 302
    assert client.get('/account').status_code == 200
    kinds = [e['kind'] for e in security_events.recent(ana)]
    assert kinds[0] == 'login' and 'two_factor_failed' in kinds


def test_code_cannot_be_replayed(client, ana):
    secret, _ = _enable(client)
    code = _code(secret, 1)
    _login(client)
    client.post('/login/2fa', data={'code': code})
    _login(client)
    client.post('/login/2fa', data={'code': code})
    assert client.get('/account').status_code == 302


def test_recovery_code_works_once(client, ana):
    _, codes = _enable(client)
    _login(client)
    assert client.post('/login/2fa', data={'code': codes[0].upper()}).status_code == 302
    assert client.get('/account').status_code == 200
    assert two_factor.recovery_codes_left(ana) == 9
    _login(client)
    client.post('/login/2fa', data={'code': codes[0]})
    assert client.get('/account').status_code == 302


def test_pending_login_expires(client, ana, monkeypatch):
    secret, _ = _enable(client)
    _login(client)
    real = time.time
    monkeypatch.setattr(time, 'time', lambda: real() + 301)
    response = client.post('/login/2fa', data={'code': _code(secret)})
    assert response.headers['Location'].endswith('/login')


def test_disable_requires_password_and_code(client, ana):
    secret, _ = _enable(client)
    client.post('/account/2fa/disable', data={'password': 'mal', 'code': _code(secret, 1)})
    assert two_factor.is_enabled(ana)
    client.post('/account/2fa/disable', data={'password': PASSWORD, 'code': '12'})
    assert two_factor.is_enabled(ana)
    client.post('/account/2fa/disable', data={'password': PASSWORD, 'code': _code(secret, 1)})
    assert not two_factor.is_enabled(ana)
    _login(client)
    assert client.get('/account').status_code == 200


def test_regenerate_recovery_codes_invalidates_old(client, ana):
    secret, old = _enable(client)
    page = client.post('/account/2fa/recovery', data={'password': PASSWORD, 'code': _code(secret, 1)})
    new = re.findall(r'<li>([0-9a-f]{5}(?:-[0-9a-f]{5}){3})</li>', page.get_data(as_text=True))
    assert len(new) == 10 and not set(new) & set(old)
    _login(client)
    client.post('/login/2fa', data={'code': old[0]})
    assert client.get('/account').status_code == 302


def test_secret_is_encrypted_at_rest(client, ana, monkeypatch):
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    secret = two_factor.start_setup(ana)
    assert two_factor._row(ana).secret != secret
    assert two_factor.pending_secret(ana) == secret


def test_account_deletion_and_export_skip_totp(client, ana):
    _enable(client)
    import data_export
    assert 'user_totp' not in data_export.EXPORTED_TABLES
    accounts.delete_account(ana)
    assert two_factor._row(ana) is None


def test_google_login_also_requires_code(client, ana, monkeypatch, app):
    import inspect
    from urllib.parse import parse_qs, urlsplit
    _enable(client)
    client.post('/logout')
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', 'cid')
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_SECRET', 'secret')
    monkeypatch.setitem(inspect.unwrap(app.view_functions['google_callback']).__globals__, '_google_email',
                        lambda code, verifier, uri: 'ana@example.com')
    params = parse_qs(urlsplit(client.get('/login/google').headers['Location']).query)
    response = client.get(f"/login/google/callback?state={params['state'][0]}&code=c")
    assert response.headers['Location'].endswith('/login/2fa')
    assert client.get('/account').status_code == 302


def test_setup_requires_password(client, ana):
    """Con una sesión robada no se puede enrolar otro autenticador sin la contraseña."""
    response = client.post('/account/2fa/setup', data={'password': 'mal'})
    assert response.status_code == 302 and two_factor.pending_secret(ana) is None


def test_password_change_invalidates_pending_login(client, ana):
    """Un login pendiente del segundo factor deja de valer si la contraseña cambió."""
    secret, _ = _enable(client)
    _login(client)
    accounts.set_password(ana, 'otra-clave-larga-2')
    response = client.post('/login/2fa', data={'code': _code(secret, 1)})
    assert response.headers['Location'].endswith('/login')
    assert client.get('/account').status_code == 302
