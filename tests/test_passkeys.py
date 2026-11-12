"""Passkeys: registrar desde Mi cuenta, entrar sin contraseña, bloqueo, borrado y aislamiento entre cuentas.

Un autenticador de software (clave P-256, attestation "none") firma como lo haría el del dispositivo.
"""
import base64
import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import accounts
import passkeys
import security_events

PASSWORD = 'clave-larga-1'
ORIGIN = 'http://localhost'


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


class SoftAuthenticator:
    """Autenticador WebAuthn mínimo con verificación de usuario."""

    def __init__(self, origin=ORIGIN):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.origin = origin
        self.count = 0

    def _client_data(self, kind, challenge):
        return json.dumps({'type': kind, 'challenge': challenge, 'origin': self.origin}).encode()

    def create(self, options):
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, 'big'), -3: numbers.y.to_bytes(32, 'big')})
        auth_data = (hashlib.sha256(options['rp']['id'].encode()).digest() + bytes([0x45]) + struct.pack('>I', 0)
                     + bytes(16) + struct.pack('>H', len(self.credential_id)) + self.credential_id + cose)
        return {'id': _b64(self.credential_id), 'rawId': _b64(self.credential_id), 'type': 'public-key',
                'clientExtensionResults': {}, 'response': {
                    'clientDataJSON': _b64(self._client_data('webauthn.create', options['challenge'])),
                    'attestationObject': _b64(cbor2.dumps({'fmt': 'none', 'attStmt': {}, 'authData': auth_data}))}}

    def get(self, options, flags=0x05):
        self.count += 1
        client_data = self._client_data('webauthn.get', options['challenge'])
        auth_data = hashlib.sha256(options['rpId'].encode()).digest() + bytes([flags]) + struct.pack('>I', self.count)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {'id': _b64(self.credential_id), 'rawId': _b64(self.credential_id), 'type': 'public-key',
                'clientExtensionResults': {}, 'response': {
                    'clientDataJSON': _b64(client_data), 'authenticatorData': _b64(auth_data),
                    'signature': _b64(signature), 'userHandle': None}}


def _register_account(client, email):
    client.post('/register', data={'accept_terms': 'on', 'email': email, 'password': PASSWORD, 'confirm': PASSWORD})
    return accounts.find_user_id(email)


@pytest.fixture
def ana(client, accounts_db):
    return _register_account(client, 'ana@example.com')


def _add_passkey(client, authenticator, name='Notebook'):
    options = client.post('/account/passkeys/options', json={'password': PASSWORD}).get_json()
    return client.post('/account/passkeys', json={'name': name, 'credential': authenticator.create(options)})


def _passkey_login(client, authenticator, **kw):
    options = client.post('/login/passkey/options', json={}).get_json()
    assert options['userVerification'] == 'required' and not options.get('allowCredentials')
    return client.post('/login/passkey', json={'next': '/tracker', 'credential': authenticator.get(options, **kw)})


def test_register_and_login_without_password(client, ana):
    authenticator = SoftAuthenticator()
    options = client.post('/account/passkeys/options', json={'password': PASSWORD}).get_json()
    assert options['rp']['id'] == 'localhost'
    assert options['authenticatorSelection']['residentKey'] == 'required'
    response = client.post('/account/passkeys', json={'name': 'Notebook', 'credential': authenticator.create(options)})
    assert response.status_code == 200, response.get_json()
    page = client.get('/account').get_data(as_text=True)
    assert 'Notebook' in page and 'passkeyForm' in page
    client.post('/logout')
    assert client.get('/tracker').status_code == 302
    response = _passkey_login(client, authenticator)
    assert response.status_code == 200 and response.get_json()['redirect'] == '/tracker'
    assert client.get('/tracker').status_code == 200
    kinds = [e['kind'] for e in security_events.recent(ana)]
    assert 'passkey_added' in kinds and 'login_passkey' in kinds
    assert passkeys.list_for(ana)[0]['last_used_at'] is not None


def test_registration_needs_password_and_fresh_challenge(client, ana):
    assert client.post('/account/passkeys/options', json={'password': 'otra'}).status_code == 400
    authenticator = SoftAuthenticator()
    options = client.post('/account/passkeys/options', json={'password': PASSWORD}).get_json()
    credential = authenticator.create(options)
    assert client.post('/account/passkeys', json={'credential': credential}).status_code == 200
    # el desafío sirve una sola vez
    assert client.post('/account/passkeys', json={'credential': credential}).status_code == 400
    # otro origen (sitio falso) no sirve
    options = client.post('/account/passkeys/options', json={'password': PASSWORD}).get_json()
    fake = SoftAuthenticator(origin='https://empleoia.example.evil').create(options)
    assert client.post('/account/passkeys', json={'credential': fake}).status_code == 400
    assert len(passkeys.list_for(ana)) == 1


def test_login_rejects_bad_signature_replay_and_missing_verification(client, ana):
    authenticator = SoftAuthenticator()
    _add_passkey(client, authenticator)
    client.post('/logout')
    # sin verificación del usuario (solo presencia) no entra
    assert _passkey_login(client, authenticator, flags=0x01).status_code == 400
    # firma de otra clave
    impostor = SoftAuthenticator()
    impostor.credential_id = authenticator.credential_id
    assert _passkey_login(client, impostor).status_code == 400
    # una respuesta válida no se puede reusar (desafío consumido)
    options = client.post('/login/passkey/options', json={}).get_json()
    credential = authenticator.get(options)
    assert client.post('/login/passkey', json={'credential': credential}).status_code == 200
    client.post('/logout')
    assert client.post('/login/passkey', json={'credential': credential}).status_code == 400
    assert client.get('/tracker').status_code == 302


def test_blocked_account_cannot_use_passkey(client, ana):
    authenticator = SoftAuthenticator()
    _add_passkey(client, authenticator)
    client.post('/logout')
    accounts.set_disabled(ana, True)
    assert _passkey_login(client, authenticator).status_code == 403
    assert client.get('/tracker').status_code == 302


def test_delete_only_own_passkeys(client, make_client, ana):
    authenticator = SoftAuthenticator()
    _add_passkey(client, authenticator)
    own = passkeys.list_for(ana)[0]['id']
    other = make_client()
    beto = _register_account(other, 'beto@example.com')
    other.post(f'/account/passkeys/{own}/delete')
    assert len(passkeys.list_for(ana)) == 1 and passkeys.list_for(beto) == []
    client.post(f'/account/passkeys/{own}/delete')
    assert passkeys.list_for(ana) == []
    client.post('/logout')
    assert _passkey_login(client, authenticator).status_code == 400


def test_account_deletion_removes_passkeys(ana):
    assert 'passkeys' in accounts.OWNED_TABLES


def test_origin_and_rp_id_from_config(monkeypatch):
    monkeypatch.setenv('APP_BASE_URL', 'https://app.example.com/')
    assert passkeys.origin('http://10.0.0.1:8080') == 'https://app.example.com'
    assert passkeys.rp_id('https://app.example.com') == 'app.example.com'
    monkeypatch.setenv('WEBAUTHN_RP_ID', 'example.com')
    assert passkeys.rp_id('https://app.example.com') == 'example.com'


def test_challenge_expires(monkeypatch):
    session: dict = {}
    passkeys.new_challenge(session, 'login')
    session['webauthn']['ts'] -= passkeys.CHALLENGE_MAX_AGE + 1
    assert passkeys.take_challenge(session, 'login') is None
    passkeys.new_challenge(session, 'register', 1)
    assert passkeys.take_challenge(session, 'register', 2) is None


def test_restored_cookie_cannot_replay_a_used_challenge(client, ana):
    authenticator = SoftAuthenticator()
    _add_passkey(client, authenticator)
    client.post('/logout')
    options = client.post('/login/passkey/options', json={}).get_json()
    cookie = client._c.cookies.get('session')
    credential = authenticator.get(options)
    assert client.post('/login/passkey', json={'credential': credential}).status_code == 200
    client.post('/logout')
    client.set_cookie('session', cookie)
    assert client.post('/login/passkey', json={'credential': credential}).status_code == 400
    assert client.get('/tracker').status_code == 302


def test_long_credential_ids_are_stored(client, ana):
    authenticator = SoftAuthenticator()
    authenticator.credential_id = os.urandom(600)
    assert _add_passkey(client, authenticator).status_code == 200
    client.post('/logout')
    assert _passkey_login(client, authenticator).status_code == 200
    # la misma credencial otra vez es un duplicado
    options = client.post('/account/passkeys/options', json={'password': PASSWORD}).get_json()
    again = client.post('/account/passkeys', json={'credential': authenticator.create(options)})
    assert again.status_code == 400 and 'ya está registrada' in again.get_json()['error']


def test_reclaimed_account_loses_passkeys(client, ana):
    _add_passkey(client, SoftAuthenticator())
    _add_passkey(client, SoftAuthenticator(), name='Otra')
    assert passkeys.delete_all(ana) == 2 and passkeys.list_for(ana) == []
