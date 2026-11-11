"""Autenticación de usuario único (APP_PASSWORD) compartida por Flask y FastAPI."""
import hmac
import os


def auth_enabled() -> bool:
    """El login se exige solo si APP_PASSWORD está definida."""
    return bool(os.getenv('APP_PASSWORD'))


def check_password(candidate: str) -> bool:
    """Compara en tiempo constante contra APP_PASSWORD."""
    expected = os.getenv('APP_PASSWORD', '')
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def check_extension_token(candidate: str) -> bool:
    """Valida el token que envía la extensión de Chrome (EXTENSION_TOKEN)."""
    expected = os.getenv('EXTENSION_TOKEN', '')
    return bool(expected) and hmac.compare_digest((candidate or '').encode(), expected.encode())


def is_authenticated_cookie(flask_app, cookie_value: str) -> bool:
    """Decodifica la cookie de sesión de Flask (para rutas servidas por FastAPI)."""
    if not cookie_value:
        return False
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    try:
        data = serializer.loads(cookie_value, max_age=int(flask_app.permanent_session_lifetime.total_seconds()))
    except Exception:
        return False
    return bool(data.get('authenticated'))
