"""Tests de cuentas (email + contraseña), login y protección CSRF."""
import io

import pytest

import accounts

PASSWORD = 'clave-larga-1'


def _register(client, email='ana@example.com', password=PASSWORD, confirm=None):
    """Envía el formulario de registro."""
    return client.post('/register', data={'email': email, 'password': password,
                                          'confirm': password if confirm is None else confirm})


def _login(client, email='ana@example.com', password=PASSWORD):
    """Envía el formulario de login."""
    return client.post('/login', data={'email': email, 'password': password})


@pytest.fixture
def registered(client, accounts_db):
    """Primera cuenta creada y sesión cerrada."""
    assert _register(client).status_code == 302
    client.post('/logout')
    return client


def test_without_login_required_no_login(client):
    """Con LOGIN_REQUIRED=false la app funciona sin login (uso local)."""
    assert client.get('/tracker').status_code == 200


def test_no_accounts_sends_to_register(client, accounts_db):
    """Sin cuentas, las páginas llevan a /login, que lleva al registro; las APIs dan 401."""
    response = client.get('/tracker')
    assert response.status_code == 302 and '/login' in response.headers['Location']
    assert '/register' in client.get('/login').headers['Location']
    assert client.get('/api/health').status_code == 200


def test_first_account_logs_in_and_logout(client, accounts_db):
    """Registrar la primera cuenta inicia sesión; al salir se vuelve a pedir login."""
    assert _register(client).status_code == 302
    assert client.get('/tracker').status_code == 200
    client.post('/logout')
    assert client.get('/tracker').status_code == 302


def test_signup_closed_after_first_account(registered, monkeypatch):
    """Después de la primera cuenta el registro se cierra salvo ALLOW_SIGNUP=true."""
    assert '/login' in registered.get('/register').headers['Location']
    assert _register(registered, 'beto@example.com').status_code == 302
    assert accounts.authenticate('beto@example.com', PASSWORD) is None
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    assert registered.get('/register').status_code == 200
    assert _register(registered, 'beto@example.com').status_code == 302
    assert accounts.authenticate('beto@example.com', PASSWORD)


def test_register_validation(client, accounts_db):
    """Email inválido, contraseña corta o distinta no crean la cuenta."""
    assert 'Email inv' in _register(client, email='no-es-email').get_data(as_text=True)
    assert 'al menos' in _register(client, password='corta').get_data(as_text=True)
    assert 'no coinciden' in _register(client, confirm='otra-clave-1').get_data(as_text=True)
    assert accounts.count_users() == 0


def test_duplicate_email_rejected(accounts_db):
    """No puede haber dos cuentas con el mismo email (sin importar mayúsculas)."""
    accounts.register('ana@example.com', PASSWORD)
    with pytest.raises(accounts.AccountError):
        accounts.register('ANA@example.com ', PASSWORD)


def test_login_with_correct_password(registered):
    """Contraseña incorrecta no entra; la correcta sí."""
    assert _login(registered, password='mala-clave-1').status_code == 200
    assert _login(registered, email='otro@example.com').status_code == 200
    assert registered.get('/tracker').status_code == 302
    assert _login(registered).status_code == 302
    assert registered.get('/tracker').status_code == 200


def test_login_ignores_external_next(registered):
    """El parámetro next no puede redirigir a otro dominio."""
    response = registered.post('/login?next=//evil.com', data={'email': 'ana@example.com', 'password': PASSWORD})
    assert response.headers['Location'] == '/'


def test_password_change_invalidates_sessions(registered, accounts_db):
    """Al cambiar la contraseña, la sesión abierta con la anterior deja de valer."""
    _login(registered)
    assert registered.get('/tracker').status_code == 200
    from sqlalchemy import text
    from werkzeug.security import generate_password_hash
    with accounts_db.begin() as conn:
        conn.execute(text('UPDATE users SET password_hash = :h'), {'h': generate_password_hash('nueva-clave-1')})
    assert registered.get('/tracker').status_code == 302


def test_csrf_blocks_post_without_token(client, app):
    """Con CSRF activo, un POST sin token es rechazado."""
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        data = {'role_type': 'dev', 'resume': (io.BytesIO(b'cv'), 'cv.txt')}
        response = client.post('/upload_resume', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_login_and_logout_clear_offline_data(registered):
    """El login y el logout piden al navegador borrar el caché offline."""
    assert registered.get('/login').headers['Clear-Site-Data'] == '"cache", "storage"'
    _login(registered)
    assert registered.post('/logout').headers['Clear-Site-Data'] == '"cache", "storage"'


def test_login_next_to_login_does_not_loop(registered):
    """Con sesión, /login?next=/login lleva al inicio en vez de entrar en bucle."""
    _login(registered)
    assert registered.get('/login?next=/login').headers['Location'] == '/'
    assert registered.get('/login?next=/register').headers['Location'] == '/'
