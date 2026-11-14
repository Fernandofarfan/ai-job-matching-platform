"""Reglas de cuentas, sesiones y límites que las pruebas de mutación (mutmut) marcaron sin cubrir."""
import pytest

import accounts
import auth
import rate_limit
import user_sessions

PASSWORD = 'clave-larga-1'
SECRET = 'secreto-de-prueba'


@pytest.fixture
def signup(accounts_db, monkeypatch):
    """Base de cuentas vacía con registro abierto y sin ADMIN_EMAIL."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)


def _error(email, password=PASSWORD):
    with pytest.raises(accounts.AccountError) as exc:
        accounts.register(email, password)
    return str(exc.value)


def test_register_errors_explain_the_reason(signup, monkeypatch):
    assert _error('no-es-un-email') == 'Email inválido'
    monkeypatch.setenv('ADMIN_EMAIL', 'Admin@Example.com')
    assert _error('ana@example.com') == 'La primera cuenta tiene que usar el email de ADMIN_EMAIL'
    monkeypatch.delenv('ADMIN_EMAIL')
    monkeypatch.setenv('K_SERVICE', 'empleoia')
    assert _error('ana@example.com') == 'Definí ADMIN_EMAIL antes de crear la primera cuenta'
    monkeypatch.delenv('K_SERVICE')
    accounts.register('ana@example.com', PASSWORD)
    assert _error('ANA@example.com') == 'Ya existe una cuenta con ese email'
    monkeypatch.setenv('ALLOW_SIGNUP', 'false')
    assert _error('beto@example.com') == 'El registro de cuentas nuevas está cerrado'


def test_register_accepts_emails_up_to_255_characters(signup):
    domain = '@example.com'
    assert accounts.register('a' * (255 - len(domain)) + domain, PASSWORD)
    assert _error('b' * (256 - len(domain)) + domain) == 'Email inválido'


def test_register_records_terms_and_verifies_only_the_first_account(signup):
    first = accounts.get_user(accounts.register('ana@example.com', PASSWORD))
    second = accounts.get_user(accounts.register('beto@example.com', PASSWORD, terms_accepted=True))
    assert first and second
    assert (first['email_verified'], first['terms_accepted']) == (True, False)
    assert (second['email_verified'], second['terms_accepted']) == (False, True)
    assert first['ai_consent'] is False and first['weekly_digest'] is True
    assert first['weekly_digest_sent_at'] is None and first['weekly_digest_since'] is not None


def test_get_user_reflects_consent_and_weekly_digest(signup):
    user_id = accounts.register('ana@example.com', PASSWORD)
    accounts.set_ai_consent(user_id, True)
    user = accounts.get_user(user_id)
    assert user and user['ai_consent'] is True
    assert accounts.get_user(None) is None and accounts.get_user(999) is None


def test_admin_is_admin_email_or_first_account(signup, monkeypatch):
    ana = accounts.register('ana@example.com', PASSWORD)
    beto = accounts.register('beto@example.com', PASSWORD)
    assert (accounts.is_admin(ana), accounts.is_admin(beto)) == (True, False)
    monkeypatch.setenv('ADMIN_EMAIL', ' Beto@Example.com ')
    assert (accounts.is_admin(ana), accounts.is_admin(beto)) == (False, True)
    accounts.set_disabled(beto, True)
    assert accounts.is_admin(beto) is False
    assert accounts.is_admin(None) is False


class Session(dict[str, object]):
    """Sesión de Starlette mínima: un dict con `permanent`."""

    permanent = False


def _session(user_id):
    session = Session(sid='sesion-anterior')
    auth.start_session(session, SECRET, user_id)
    assert session.permanent is True and session['user_id'] == user_id and session['sid'] != 'sesion-anterior'
    return session


def test_session_of_blocked_account_is_rejected_even_if_not_revoked(signup, monkeypatch):
    """Bloquear cierra las sesiones; si eso fallara, la sesión igual deja de valer."""
    ana = accounts.register('ana@example.com', PASSWORD)
    session = _session(ana)
    assert auth.session_user_id(session, SECRET) == ana
    monkeypatch.setattr(user_sessions, 'revoke_all', lambda *_: None)
    accounts.set_disabled(ana, True)
    assert auth.session_user_id(session, SECRET) is None


def test_session_of_unverified_account_needs_verification(signup, monkeypatch):
    accounts.register('ana@example.com', PASSWORD)
    beto = accounts.register('beto@example.com', PASSWORD)
    session = _session(beto)
    assert auth.session_user_id(session, SECRET) == beto
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION', 'true')
    assert auth.session_user_id(session, SECRET) is None


def test_session_without_fingerprint_is_rejected(signup):
    session = _session(accounts.register('ana@example.com', PASSWORD))
    del session['auth_fp']
    assert auth.session_user_id(session, SECRET) is None


@pytest.fixture
def limits(monkeypatch):
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'memory://')
    monkeypatch.setenv('AI_RATE_LIMIT', '1 per minute')
    rate_limit._state.clear()
    yield
    rate_limit._state.clear()


def test_page_limits_are_per_namespace_and_key(limits):
    assert rate_limit.hit_page('1 per minute', 'login', 'ip:1')
    assert not rate_limit.hit_page('1 per minute', 'login', 'ip:1')
    assert rate_limit.hit_page('1 per minute', 'register', 'ip:1')
    assert rate_limit.hit_page('1 per minute', 'login', 'ip:2')


def test_empty_key_counts_as_unknown(limits):
    assert rate_limit.hit_page('1 per minute', 'login', '')
    assert not rate_limit.hit_page('1 per minute', 'login', 'unknown')
    assert rate_limit.hit_ai_limit('')
    assert not rate_limit.hit_ai_limit('unknown')


def test_limits_with_same_key_do_not_share_namespace(limits):
    assert rate_limit._hit('limit', 'uno', 'user:1')
    assert not rate_limit._hit('limit', 'uno', 'user:1')
    assert rate_limit._hit('limit', 'dos', 'user:1')


def test_client_ip_defaults(monkeypatch):
    monkeypatch.delenv('TRUSTED_PROXY_HOPS', raising=False)
    assert rate_limit.client_ip('10.0.0.1', '6.6.6.6') == '10.0.0.1'
    assert rate_limit.client_ip(None, None) == 'unknown'
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', '1')
    assert rate_limit.client_ip('10.0.0.1', '1' * 60) == '1' * 45
