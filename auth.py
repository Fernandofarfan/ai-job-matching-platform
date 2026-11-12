"""Login con cuentas de usuario (accounts.py) compartido por Flask y FastAPI."""
import hashlib
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
    if user is None or (verification_required() and not user.get('email_verified', True)):
        return None
    ok = hmac.compare_digest(str(session_data.get('auth_fp', '')), session_fingerprint(secret_key, user))
    return user['id'] if ok else None


def is_session_valid(session_data, secret_key) -> bool:
    """La sesión está autenticada y corresponde a la contraseña actual del usuario."""
    return session_user_id(session_data, secret_key) is not None


def extension_token_user(candidate: str) -> Optional[int]:
    """Cuenta del token de la extensión: el generado en "Mi cuenta", o EXTENSION_TOKEN para la primera cuenta."""
    if not candidate:
        return None
    import integrations
    uid = integrations.user_for_extension_token(candidate)
    if uid is not None:
        return uid
    return accounts.first_user_id() if legacy_extension_token(candidate) else None


def legacy_extension_token(candidate: str) -> bool:
    """True si es el EXTENSION_TOKEN del .env (de la primera cuenta)."""
    expected = os.getenv('EXTENSION_TOKEN', '')
    return bool(expected and candidate) and hmac.compare_digest(candidate.encode(), expected.encode())


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


RESET_MAX_AGE = 3600
VERIFY_MAX_AGE = 3 * 86400


def verification_required() -> bool:
    """REQUIRE_EMAIL_VERIFICATION=true: las cuentas nuevas no entran hasta confirmar el email."""
    return os.getenv('REQUIRE_EMAIL_VERIFICATION', 'false').strip().lower() == 'true'


def _token_fp(purpose: str, user: dict) -> str:
    """Lo que invalida el enlace: la contraseña (recuperar) o el email (verificar)."""
    basis = user['password_hash'] if purpose == 'reset' else user['email']
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def account_token(secret_key, purpose: str, user: dict) -> str:
    """Enlace firmado para recuperar la contraseña o verificar el email; deja de valer al usarse."""
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(secret_key, salt=f'account-{purpose}').dumps(
        {'uid': user['id'], 'fp': _token_fp(purpose, user)})


def read_account_token(secret_key, purpose: str, token: str, max_age: int) -> Optional[dict]:
    """Cuenta del enlace si es válido, no venció y no se usó; None si no."""
    from itsdangerous import BadData, URLSafeTimedSerializer
    try:
        data = URLSafeTimedSerializer(secret_key, salt=f'account-{purpose}').loads(token, max_age=max_age)
        user = accounts.get_user(int(data['uid']))
    except (BadData, KeyError, TypeError, ValueError):
        return None
    if user is None or not hmac.compare_digest(str(data.get('fp', '')), _token_fp(purpose, user)):
        return None
    return user
