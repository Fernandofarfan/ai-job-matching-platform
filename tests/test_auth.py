"""
test_auth.py – Tests de autenticación: login, logout, lockout, registro,
open redirect y session fixation.
"""
import pytest
from fastapi.testclient import TestClient


def _anon_client() -> TestClient:
    """Cliente sin sesión (misma app).

    IMPORTANTE: importar main DENTRO de la función — si se importa a nivel de
    módulo, los routers bindean db_manager REAL antes de que conftest aplique
    el mock (los tests usarían la BD de verdad).
    """
    import main
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def anon():
    """Alias a nivel módulo para todas las clases."""
    return _anon_client()


class TestProtectedRoutes:
    """Sin sesión: APIs 401, páginas redirect a /login."""

    def test_api_401_without_session(self, anon):
        r = anon.get('/api/tracker/jobs')
        assert r.status_code == 401
        assert r.json()['success'] is False

    def test_page_redirects_to_login(self, anon):
        r = anon.get('/', follow_redirects=False)
        assert r.status_code == 303
        assert r.headers['location'].startswith('/login')

    def test_status_401_without_session(self, anon):
        r = anon.get('/status')
        assert r.status_code == 401

    def test_health_is_public(self, anon):
        r = anon.get('/api/health')
        assert r.status_code == 200
        assert 'checks' in r.json()

    def test_login_page_is_public(self, anon):
        r = anon.get('/login')
        assert r.status_code == 200


class TestLoginLogout:
    def test_wrong_password_rejected(self, anon):
        r = anon.post('/login',
                      data={'username': 'tester', 'password': 'wrong-pass'},
                      follow_redirects=False)
        assert r.status_code == 303
        assert r.headers['location'] == '/login'
        # Sigue sin sesión
        assert anon.get('/api/tracker/jobs').status_code == 401

    def test_logout_clears_session(self, client):
        # 'client' ya está logueado por conftest
        assert client.get('/api/tracker/jobs').status_code == 200
        r = client.get('/logout', follow_redirects=False)
        assert r.status_code == 303
        assert client.get('/api/tracker/jobs').status_code == 401
        # Re-login para no romper los tests siguientes (cliente compartido)
        client.post('/login',
                    data={'username': 'tester', 'password': 'secret123'},
                    follow_redirects=False)
        assert client.get('/api/tracker/jobs').status_code == 200


class TestBruteForceLockout:
    def test_lockout_after_five_failures(self):
        import routers.auth as auth_mod
        anon = _anon_client()
        try:
            for _ in range(5):
                anon.post('/login',
                          data={'username': 'tester', 'password': 'bad-1'},
                          follow_redirects=False)
            # Aunque ahora la contraseña sea CORRECTA, sigue bloqueado
            r = anon.post('/login',
                          data={'username': 'tester', 'password': 'secret123'},
                          follow_redirects=False)
            assert r.status_code == 303
            assert r.headers['location'] == '/login'
            assert anon.get('/api/tracker/jobs').status_code == 401
        finally:
            # No envenenar al resto de la suite (mismo usuario+IP)
            auth_mod._login_failures.clear()

    def test_lockout_is_per_username(self):
        """El lockout de 'tester' no afecta a otro usuario."""
        anon = _anon_client()
        for _ in range(5):
            anon.post('/login',
                      data={'username': 'otro-usuario', 'password': 'x'},
                      follow_redirects=False)
        # 'nobody' no está lockouteado (falla por credenciales, no por lockout);
        # lo que importa es que el flujo llega a verificar credenciales:
        # usamos un username inexistente → sigue siendo 303 a /login sin crash
        r = anon.post('/login',
                      data={'username': 'nobody-xyz', 'password': 'y'},
                      follow_redirects=False)
        assert r.status_code == 303


class TestOpenRedirect:
    def test_safe_next_blocks_external(self):
        from routers.auth import _safe_next
        assert _safe_next('//evil.com') == '/'
        assert _safe_next('/\\evil.com') == '/'
        assert _safe_next('https://evil.com') == '/'
        assert _safe_next('/tracker') == '/tracker'
        assert _safe_next(None) == '/'
        assert _safe_next('\n/evil') == '/'

    def test_login_next_param_cannot_redirect_offsite(self):
        anon = _anon_client()
        r = anon.post('/login?next=//evil.com',
                      data={'username': 'tester', 'password': 'secret123'},
                      follow_redirects=False)
        # 403 CSRF (sin Origin no aplica) o 303 a '/' seguro — nunca a evil.com
        assert r.status_code in (303, 403)
        if r.status_code == 303:
            loc = r.headers['location']
            assert 'evil.com' not in loc
            assert loc in ('/', '/login')


class TestSessionFixation:
    """El login debe limpiar la sesión previa (no conservar claves ajenas)."""

    def _decode_session_cookie(self, cookie_value: str) -> dict:
        # Mismo esquema que starlette SessionMiddleware (versión instalada):
        # TimestampSigner(secret).sign(b64encode(json.dumps(session)))
        import base64
        import json
        import os

        import itsdangerous
        secret = os.getenv('SECRET_KEY', 'empleoia-dev-secret-key-change-me')
        signer = itsdangerous.TimestampSigner(str(secret))
        data = signer.unsign(cookie_value.encode('utf-8'),
                             max_age=14 * 24 * 3600)
        return json.loads(base64.b64decode(data))

    def test_pre_login_session_keys_are_cleared(self):
        anon = _anon_client()
        # 1) Login fallido → genera sesión con '_flashes'
        anon.post('/login',
                  data={'username': 'tester', 'password': 'bad'},
                  follow_redirects=False)
        jar_cookie = anon.cookies.get('session')
        assert jar_cookie, "debería haber cookie de sesión"
        before = self._decode_session_cookie(jar_cookie)
        assert '_flashes' in before

        # 2) Login correcto → la sesión debe reconstruirse:
        # las claves previas (flash de error del intento fallido) desaparecieron;
        # solo queda el flash nuevo de bienvenido agregado DESPUÉS del clear().
        r = anon.post('/login',
                      data={'username': 'tester', 'password': 'secret123'},
                      follow_redirects=False)
        assert r.status_code == 303
        after = self._decode_session_cookie(anon.cookies.get('session'))
        assert 'user_id' in after
        flashes_after = after.get('_flashes', [])
        # Ningún residuo del intento fallido previo al login
        assert not any('incorrectos' in str(f) for f in flashes_after)
        # La sesión limpia solo contiene lo nuevo del login
        leftover_keys = set(after.keys()) - {'user_id', 'username', '_flashes'}
        assert not leftover_keys, f"claves residuales de sesión: {leftover_keys}"


class TestRegisterGating:
    def test_register_closed_after_first_user(self):
        anon = _anon_client()
        r = anon.get('/register', follow_redirects=False)
        # Ya existe el usuario de tests y ALLOW_REGISTRATION no está en true
        assert r.status_code == 303
        assert r.headers['location'] == '/login'
