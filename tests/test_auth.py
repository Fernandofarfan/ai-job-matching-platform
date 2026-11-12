"""Tests de cuentas (email + contraseña), login y protección CSRF."""
import inspect
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


def test_register_rejects_second_account_when_signup_closed(accounts_db, monkeypatch):
    """Aunque se saltee el chequeo de la vista, accounts.register respeta ALLOW_SIGNUP."""
    import pytest
    import accounts
    monkeypatch.delenv('ALLOW_SIGNUP', raising=False)
    accounts.register('a@example.com', 'x' * 10)
    with pytest.raises(accounts.AccountError):
        accounts.register('b@example.com', 'x' * 10)


def test_first_account_requires_admin_email_on_cloud_run(accounts_db, monkeypatch):
    """En Cloud Run no se puede crear la primera cuenta sin ADMIN_EMAIL."""
    import pytest
    import accounts
    monkeypatch.setenv('K_SERVICE', 'app')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    with pytest.raises(accounts.AccountError):
        accounts.register('a@example.com', 'x' * 10)


@pytest.fixture
def outbox(monkeypatch, app):
    """Emails que mandaría la app (enlace incluido) en vez de usar SMTP."""
    sent = []
    monkeypatch.setitem(inspect.unwrap(app.view_functions['forgot_password']).__globals__, '_deliver',
                        lambda to, subject, body, link, cta: sent.append((to, link)) or True)
    return sent


def _path(link):
    """Ruta relativa de un enlace absoluto del email."""
    from urllib.parse import urlparse
    return urlparse(link).path


def test_password_reset_flow(registered, outbox):
    """El enlace del email cambia la contraseña, es de un solo uso y no revela si la cuenta existe."""
    registered.post('/forgot_password', data={'email': 'nadie@example.com'})
    assert outbox == []
    response = registered.post('/forgot_password', data={'email': 'ANA@example.com'})
    assert response.status_code == 302 and len(outbox) == 1 and outbox[0][0] == 'ana@example.com'
    link = _path(outbox[0][1])
    assert registered.get(link).status_code == 200
    assert registered.post(link, data={'password': 'nueva-clave-99', 'confirm': 'nueva-clave-99'}).status_code == 302
    assert accounts.authenticate('ana@example.com', PASSWORD) is None
    assert accounts.authenticate('ana@example.com', 'nueva-clave-99')
    assert 'forgot_password' in registered.get(link).headers['Location']


def test_change_password_closes_other_sessions(registered, app):
    """Cambiar la contraseña mantiene esta sesión y cierra las demás."""
    other = app.test_client()
    _login(other)
    _login(registered)
    bad = registered.post('/account/password', data={'current': 'mal', 'password': 'otra-clave-12', 'confirm': 'otra-clave-12'})
    assert bad.status_code == 302 and accounts.authenticate('ana@example.com', PASSWORD)
    registered.post('/account/password', data={'current': PASSWORD, 'password': 'otra-clave-12', 'confirm': 'otra-clave-12'})
    assert registered.get('/account').status_code == 200
    assert other.get('/tracker').status_code == 302


def test_email_verification_required(registered, outbox, monkeypatch):
    """Con REQUIRE_EMAIL_VERIFICATION, una cuenta nueva entra solo después de confirmar el email."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION', 'true')
    _register(registered, 'beto@example.com')
    assert registered.get('/tracker').status_code == 302
    assert outbox[-1][0] == 'beto@example.com'
    _login(registered, 'beto@example.com')
    assert registered.get('/tracker').status_code == 302
    registered.get(_path(outbox[-1][1]))
    _login(registered, 'beto@example.com')
    assert registered.get('/tracker').status_code == 200


def test_first_account_is_verified(registered):
    """La primera cuenta (administrador) no espera el email de verificación."""
    assert accounts.get_user(accounts.find_user_id('ana@example.com'))['email_verified']


def test_delete_account_needs_password(registered, monkeypatch, app):
    """Borrar la cuenta pide la contraseña y después la cuenta deja de existir."""
    monkeypatch.setitem(inspect.unwrap(app.view_functions['delete_account']).__globals__, 'delete_user_profile', lambda: True)
    _login(registered)
    registered.post('/account/delete', data={'password': 'mal'})
    assert accounts.find_user_id('ana@example.com')
    response = registered.post('/account/delete', data={'password': PASSWORD})
    assert response.status_code == 302 and accounts.find_user_id('ana@example.com') is None
    assert registered.get('/tracker').status_code == 302


def test_reset_link_ignores_foreign_host(registered, outbox):
    """Sin PUBLIC_BASE_URL, un Host que no es local no recibe el enlace (evita robar el token)."""
    registered.post('/forgot_password', data={'email': 'ana@example.com'}, headers={'Host': 'evil.example'})
    assert outbox == []


def test_reset_link_is_single_use_under_race(registered):
    """Dos usos del mismo enlace: el segundo falla porque la contraseña ya cambió."""
    user = accounts.get_user(accounts.find_user_id('ana@example.com'))
    accounts.set_password(user['id'], 'primera-clave-1', expected_hash=user['password_hash'])
    with pytest.raises(accounts.AccountError):
        accounts.set_password(user['id'], 'segunda-clave-2', expected_hash=user['password_hash'])
    assert accounts.authenticate('ana@example.com', 'primera-clave-1')


def test_admin_account_kept_while_others_exist(registered, monkeypatch, app):
    """La primera cuenta no se borra si hay otras (Telegram, Gmail y la extensión son suyos)."""
    monkeypatch.setitem(inspect.unwrap(app.view_functions['delete_account']).__globals__, 'delete_user_profile', lambda: True)
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    accounts.register('beto@example.com', PASSWORD)
    _login(registered)
    registered.post('/account/delete', data={'password': PASSWORD})
    assert accounts.find_user_id('ana@example.com')
