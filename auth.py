"""Login con cuentas de usuario (accounts.py) compartido por Flask y FastAPI."""
import hmac
import logging
import os
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

import accounts

logger = logging.getLogger(__name__)


def auth_enabled() -> bool:
    """El login se exige salvo LOGIN_REQUIRED=false (solo para tests o uso local sin cuentas)."""
    return os.getenv('LOGIN_REQUIRED', 'true').strip().lower() != 'false'


def session_fingerprint(secret_key, user: dict) -> str:
    """Huella del usuario y su hash de contraseña: al cambiar la contraseña, las sesiones viejas dejan de valer."""
    key = secret_key if isinstance(secret_key, bytes) else str(secret_key).encode()
    return hmac.new(key, f"{user['id']}:{user['password_hash']}".encode(), 'sha256').hexdigest()


def start_session(session, secret_key, user_id: int):
    """Abre la sesión de `user_id` (borra lo anterior para evitar fijación de sesión)."""
    user = accounts.get_user(user_id)
    if user is None:
        raise ValueError(f'No existe el usuario {user_id}')
    session.clear()
    session['user_id'] = user_id
    session['auth_fp'] = session_fingerprint(secret_key, user)
    session.permanent = True


def session_user_id(session_data, secret_key) -> Optional[int]:
    """Id del usuario de la sesión si sigue siendo válida; None si no."""
    user_id = session_data.get('user_id')
    if not user_id:
        return None
    try:
        user = accounts.get_user(user_id)
    except SQLAlchemyError as e:
        logger.error(f"No se pudo validar la sesión: {e}")
        return None
    if user is None:
        return None
    ok = hmac.compare_digest(str(session_data.get('auth_fp', '')), session_fingerprint(secret_key, user))
    return user['id'] if ok else None


def is_session_valid(session_data, secret_key) -> bool:
    """La sesión está autenticada y corresponde a la contraseña actual del usuario."""
    return session_user_id(session_data, secret_key) is not None


def extension_user_id() -> Optional[int]:
    """La extensión de Chrome (EXTENSION_TOKEN) guarda en el tracker de la primera cuenta."""
    return accounts.first_user_id()


def check_extension_token(candidate: str) -> bool:
    """Valida el token que envía la extensión de Chrome (EXTENSION_TOKEN)."""
    expected = os.getenv('EXTENSION_TOKEN', '')
    return bool(expected) and hmac.compare_digest((candidate or '').encode(), expected.encode())


def load_session_cookie(flask_app, cookie_value) -> dict:
    """Contenido de la cookie de sesión de Flask (para rutas servidas por FastAPI); {} si no vale."""
    if not cookie_value:
        return {}
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    try:
        data = serializer.loads(cookie_value, max_age=int(flask_app.permanent_session_lifetime.total_seconds()))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def cookie_user_id(flask_app, cookie_value) -> Optional[int]:
    """Usuario de la cookie de sesión de Flask, o None."""
    return session_user_id(load_session_cookie(flask_app, cookie_value), flask_app.secret_key)


def check_csrf_token(session_data: dict, token: str, secret_key, time_limit=3600) -> bool:
    """Mismo chequeo que Flask-WTF: token firmado (salt wtf-csrf-token) igual al guardado en la sesión."""
    from itsdangerous import BadData, URLSafeTimedSerializer
    expected = session_data.get('csrf_token')
    if not token or not expected:
        return False
    try:
        raw = URLSafeTimedSerializer(secret_key, salt='wtf-csrf-token').loads(token, max_age=time_limit)
    except BadData:
        return False
    return hmac.compare_digest(str(expected), str(raw))
