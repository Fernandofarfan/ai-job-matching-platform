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


def test_reset_link_on_ipv6_loopback(registered, outbox):
    """[::1] es local: recibe el enlace aunque no haya PUBLIC_BASE_URL."""
    registered.post('/forgot_password', data={'email': 'ana@example.com'}, headers={'Host': '[::1]:5000'})
    assert len(outbox) == 1


def test_extension_token_is_per_account(registered, monkeypatch):
    """Cada cuenta genera su token; el de una no guarda en la otra y revocarlo lo invalida."""
    import auth
    import integrations
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    ana = accounts.find_user_id('ana@example.com')
    beto = accounts.register('beto@example.com', PASSWORD)
    token_ana, token_beto = integrations.new_extension_token(ana), integrations.new_extension_token(beto)
    assert auth.extension_token_user(token_ana) == ana
    assert auth.extension_token_user(token_beto) == beto
    integrations.revoke_extension_token(beto)
    assert auth.extension_token_user(token_beto) is None
    assert auth.extension_token_user('') is None


def test_legacy_extension_token_goes_to_first_account(registered, monkeypatch):
    """EXTENSION_TOKEN del .env sigue guardando en la primera cuenta."""
    import auth
    monkeypatch.setenv('EXTENSION_TOKEN', 'viejo-token')
    assert auth.extension_token_user('viejo-token') == accounts.find_user_id('ana@example.com')


def test_telegram_chat_is_per_account(registered, monkeypatch):
    """TELEGRAM_CHAT_ID es de la primera cuenta; otra cuenta usa solo su propio chat."""
    import integrations
    from tasks import notification_tasks as nt
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '111')
    ana = accounts.find_user_id('ana@example.com')
    beto = accounts.register('beto@example.com', PASSWORD)
    with accounts.as_user(ana):
        assert nt._telegram_chat() == '111'
    with accounts.as_user(beto):
        assert nt._telegram_chat() is None
        integrations.set_telegram_chat(beto, '222')
        assert nt._telegram_chat() == '222'
    with pytest.raises(integrations.IntegrationError):
        integrations.set_telegram_chat(beto, 'abc')


def test_gmail_token_encrypted(registered, monkeypatch):
    """Con CV_ENCRYPTION_KEY el token de Gmail queda cifrado en la base y se lee en claro."""
    from cryptography.fernet import Fernet
    import integrations
    monkeypatch.setenv('CV_ENCRYPTION_KEY', Fernet.generate_key().decode())
    ana = accounts.find_user_id('ana@example.com')
    integrations.save_gmail_token(ana, '{"token": "x"}')
    assert '"token"' not in integrations._row(ana).gmail_token
    assert integrations.gmail_token(ana) == '{"token": "x"}'
    assert integrations.gmail_user_ids() == [ana]
    integrations.clear_gmail(ana)
    assert integrations.gmail_user_ids() == []


def test_account_page_integrations(registered, monkeypatch):
    """Desde "Mi cuenta" se guarda el chat y el token nuevo se muestra una sola vez."""
    import integrations
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'bot')
    _login(registered)
    registered.post('/account/telegram', data={'chat_id': '333'})
    ana = accounts.find_user_id('ana@example.com')
    assert integrations.telegram_chat_id(ana) == '333'
    page = registered.post('/account/extension_token')
    assert page.headers['Cache-Control'] == 'no-store'
    token = page.get_data(as_text=True).split('id="new-token" value="')[1].split('"')[0]
    assert integrations.user_for_extension_token(token) == ana
    assert token not in registered.get('/account').get_data(as_text=True)


def test_gmail_callback_rejects_bad_state(registered):
    """La vuelta de Google sin el state guardado en la sesión no conecta nada."""
    _login(registered)
    response = registered.get('/account/gmail/callback?state=x&code=y')
    assert response.status_code == 302
    import integrations
    assert integrations.gmail_user_ids() == []


@pytest.fixture
def google(monkeypatch, app):
    """Cliente OAuth de Google simulado: `google.email` es lo que devuelve Google (None = sin verificar)."""
    import inspect
    from types import SimpleNamespace
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', 'cid')
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_SECRET', 'secret')
    fake = SimpleNamespace(email='ana@example.com', calls=[])

    def exchange(code, verifier, redirect_uri):
        fake.calls.append((code, verifier, redirect_uri))
        return fake.email
    monkeypatch.setitem(inspect.unwrap(app.view_functions['google_callback']).__globals__, '_google_email', exchange)
    return fake


def _google_start(client):
    """Arranca el login con Google y devuelve los parámetros de la redirección."""
    from urllib.parse import parse_qs, urlsplit
    response = client.get('/login/google')
    assert response.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers['Location']).query).items()}


def test_google_login_existing_account(registered, google):
    """Google con un email ya registrado entra a esa cuenta, con PKCE y state."""
    params = _google_start(registered)
    assert params['code_challenge_method'] == 'S256' and params['scope'] == 'openid email'
    assert registered.get(f"/login/google/callback?state={params['state']}&code=c").status_code == 302
    assert google.calls[0][0] == 'c' and google.calls[0][2].endswith('/login/google/callback')
    assert registered.get('/account').status_code == 200


def test_google_login_rejects_bad_state(registered, google):
    """Sin el state de la sesión no se entra."""
    _google_start(registered)
    registered.get('/login/google/callback?state=otro&code=c')
    assert not google.calls
    assert registered.get('/account').status_code == 302


def test_google_login_needs_verified_email(registered, google):
    """Un email que Google no verificó no entra."""
    google.email = None
    params = _google_start(registered)
    registered.get(f"/login/google/callback?state={params['state']}&code=c")
    assert registered.get('/account').status_code == 302


def test_google_login_respects_closed_signup(registered, google, monkeypatch):
    """Un email nuevo no crea cuenta si el registro está cerrado; con ALLOW_SIGNUP sí, ya verificada."""
    google.email = 'beto@example.com'
    params = _google_start(registered)
    registered.get(f"/login/google/callback?state={params['state']}&code=c")
    assert accounts.find_user_id('beto@example.com') is None
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    params = _google_start(registered)
    registered.get(f"/login/google/callback?state={params['state']}&code=c")
    beto = accounts.find_user_id('beto@example.com')
    assert beto is not None and accounts.get_user(beto)['email_verified']


def test_google_button_hidden_without_client(registered):
    """Sin cliente OAuth no aparece el botón ni funciona la ruta."""
    assert 'Entrar con Google' not in registered.get('/login').get_data(as_text=True)
    assert registered.get('/login/google').headers['Location'].endswith('/login')



def test_disconnect_beats_instance_integrations(registered, monkeypatch):
    """Si la primera cuenta desconecta Telegram o revoca su token, no se vuelve a TELEGRAM_CHAT_ID ni a EXTENSION_TOKEN."""
    import auth
    import integrations
    from tasks import notification_tasks as nt
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '111')
    monkeypatch.setenv('EXTENSION_TOKEN', 'viejo-token')
    ana = accounts.find_user_id('ana@example.com')
    integrations.set_telegram_chat(ana, '')
    with accounts.as_user(ana):
        assert nt._telegram_chat() is None
    integrations.revoke_extension_token(ana)
    assert auth.extension_token_user('viejo-token') is None
    assert not auth.legacy_extension_token('viejo-token')


def test_gmail_disconnect_skips_token_json(registered, monkeypatch):
    """La primera cuenta que desconectó Gmail no vuelve a leer token.json."""
    import sys
    from types import ModuleType
    import integrations
    for name in ('googleapiclient', 'googleapiclient.discovery', 'google_auth_oauthlib', 'google_auth_oauthlib.flow',
                 'google.auth.transport.requests', 'google.oauth2.credentials'):
        stub = ModuleType(name)
        stub.build = stub.InstalledAppFlow = stub.Request = stub.Credentials = object
        monkeypatch.setitem(sys.modules, name, stub)
    monkeypatch.delitem(sys.modules, 'tasks.gmail_tracker', raising=False)
    from tasks import gmail_tracker
    called = []
    monkeypatch.setattr(gmail_tracker, 'get_gmail_service', lambda: called.append(1))
    integrations.clear_gmail(accounts.find_user_id('ana@example.com'))
    assert integrations.gmail_user_ids() == []
    gmail_tracker.check_interview_emails()
    assert not called


def test_google_login_drops_password_of_unverified_account(registered, google, monkeypatch):
    """Una cuenta sin verificar creada por otro con el email: al entrar con Google su contraseña deja de valer."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    accounts.register('beto@example.com', PASSWORD)
    google.email = 'beto@example.com'
    params = _google_start(registered)
    registered.get(f"/login/google/callback?state={params['state']}&code=c")
    beto = accounts.find_user_id('beto@example.com')
    assert accounts.get_user(beto)['email_verified']
    assert accounts.authenticate('beto@example.com', PASSWORD) is None
