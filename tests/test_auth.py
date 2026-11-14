"""Tests de login (APP_PASSWORD) y protección CSRF."""
import io


def _login(client, password):
    """Envía el formulario de login."""
    return client.post('/login', data={'password': password})


def test_without_app_password_no_login_required(client, monkeypatch):
    """Sin APP_PASSWORD la app funciona sin login (uso local)."""
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    assert client.get('/tracker').status_code == 200


def test_pages_redirect_to_login_when_enabled(client, api, monkeypatch):
    """Con APP_PASSWORD, las páginas redirigen a /login y las APIs devuelven 401."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    response = client.get('/tracker')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert api.get('/api/tracker/stats').status_code == 401
    assert client.get('/api/health').status_code == 200


def test_login_with_correct_password(client, monkeypatch):
    """La contraseña correcta abre sesión; la incorrecta no."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    assert _login(client, 'mala').status_code == 200
    assert client.get('/tracker').status_code == 302
    assert _login(client, 'secreta').status_code == 302
    assert client.get('/tracker').status_code == 200
    client.post('/logout')
    assert client.get('/tracker').status_code == 302


def test_login_ignores_external_next(client, monkeypatch):
    """El parámetro next no permite redirigir a otro dominio."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    response = client.post('/login?next=//evil.com', data={'password': 'secreta'})
    assert response.headers['Location'] == '/'
    response = client.post('/login?next=/%5Cevil.com', data={'password': 'secreta'})
    assert response.headers['Location'] == '/'


def test_csrf_blocks_post_without_token(client, app, monkeypatch):
    """Con CSRF activo, un POST sin token es rechazado."""
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        data = {'role_type': 'dev', 'resume': (io.BytesIO(b'cv'), 'cv.txt')}
        response = client.post('/upload_resume', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_rotating_password_invalidates_sessions(client, monkeypatch):
    """Al cambiar APP_PASSWORD, la sesión abierta con la anterior deja de valer."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    _login(client, 'secreta')
    assert client.get('/tracker').status_code == 200
    monkeypatch.setenv('APP_PASSWORD', 'nueva')
    assert client.get('/tracker').status_code == 302


def test_login_and_logout_clear_offline_data(client, monkeypatch):
    """Sin sesión, el navegador borra el caché del service worker e IndexedDB."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    assert client.get('/login').headers['Clear-Site-Data'] == '"cache", "storage"'
    _login(client, 'secreta')
    assert client.post('/logout').headers['Clear-Site-Data'] == '"cache", "storage"'


def test_login_page_keeps_offline_data_with_active_session(client, monkeypatch):
    """Con sesión activa, abrir /login redirige sin borrar los datos offline."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    _login(client, 'secreta')
    response = client.get('/login')
    assert response.status_code == 302
    assert 'Clear-Site-Data' not in response.headers


def test_login_next_to_login_does_not_loop(client, monkeypatch):
    """next=/login no redirige al propio login (evita un bucle con sesión activa)."""
    monkeypatch.setenv('APP_PASSWORD', 'secreta')
    _login(client, 'secreta')
    assert client.get('/login?next=/login').headers['Location'] == '/'
    assert client.get('/login?next=/login/?x=1').headers['Location'] == '/'
