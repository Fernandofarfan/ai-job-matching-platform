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


def session_fingerprint(secret_key) -> str:
    """Huella de APP_PASSWORD guardada en la sesión: al rotar la contraseña, las sesiones viejas dejan de valer."""
    key = secret_key if isinstance(secret_key, bytes) else str(secret_key).encode()
    return hmac.new(key, os.getenv('APP_PASSWORD', '').encode(), 'sha256').hexdigest()


def is_session_valid(session_data, secret_key) -> bool:
    """La sesión está autenticada y corresponde a la APP_PASSWORD actual."""
    return bool(session_data.get('authenticated')) and hmac.compare_digest(
        str(session_data.get('auth_fp', '')), session_fingerprint(secret_key))


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
    return is_session_valid(data, flask_app.secret_key)
