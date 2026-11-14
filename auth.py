"""Login con cuentas de usuario (accounts.py) de las páginas y APIs de FastAPI."""
import hashlib
import hmac
import logging
import os
from collections.abc import Mapping
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError

import accounts
import user_sessions

logger = logging.getLogger(__name__)


def auth_enabled() -> bool:
    """El login se exige salvo LOGIN_REQUIRED=false (solo para tests o uso local sin cuentas)."""
    return os.getenv('LOGIN_REQUIRED', 'true').strip().lower() != 'false'


def session_fingerprint(secret_key: str, user: dict[str, Any]) -> str:
    """Huella del usuario y su hash de contraseña: al cambiar la contraseña, las sesiones viejas dejan de valer."""
    key = secret_key if isinstance(secret_key, bytes) else str(secret_key).encode()
    return hmac.new(key, f"{user['id']}:{user['password_hash']}".encode(), 'sha256').hexdigest()


def start_session(session: Any, secret_key: str, user_id: int, ip: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    """Abre la sesión de `user_id` (borra lo anterior para evitar fijación de sesión) y la registra en user_sessions."""
    user = accounts.get_user(user_id)
    if user is None:
        raise ValueError(f'No existe el usuario {user_id}')
    user_sessions.revoke_sid(session.get('sid'))
    session.clear()
    session['user_id'] = user_id
    session['auth_fp'] = session_fingerprint(secret_key, user)
    session['sid'] = user_sessions.create(user_id, ip, user_agent)
    session.permanent = True


def session_user_id(session_data: Mapping[str, Any], secret_key: str) -> Optional[int]:
    """Id del usuario de la sesión si sigue siendo válida; None si no."""
    user_id = session_data.get('user_id')
    if not user_id:
        return None
    try:
        user = accounts.get_user(user_id)
    except SQLAlchemyError as e:
        logger.error(f"No se pudo validar la sesión: {e}")
        return None
    if user is None or user.get('disabled') or (verification_required() and not user.get('email_verified', True)):
        return None
    if not hmac.compare_digest(str(session_data.get('auth_fp', '')), session_fingerprint(secret_key, user)):
        return None
    try:
        return user['id'] if user_sessions.is_active(user['id'], session_data.get('sid')) else None
    except SQLAlchemyError as e:
        logger.error(f"No se pudo validar la sesión: {e}")
        return None


def is_session_valid(session_data: Mapping[str, Any], secret_key: str) -> bool:
    """La sesión está autenticada y corresponde a la contraseña actual del usuario."""
    return session_user_id(session_data, secret_key) is not None


def extension_token_user(candidate: str) -> Optional[int]:
    """Cuenta del token de la extensión: el generado en "Mi cuenta", o EXTENSION_TOKEN para la primera cuenta."""
    if not candidate:
        return None
    import integrations
    uid = integrations.user_for_extension_token(candidate)
    if uid is None and legacy_extension_token(candidate):
        uid = accounts.first_user_id()
    user = accounts.get_user(uid) if uid is not None else None
    return uid if user and not user['disabled'] else None


def legacy_extension_token(candidate: str) -> bool:
    """True si es el EXTENSION_TOKEN del .env y la primera cuenta no generó ni revocó su propio token."""
    import integrations
    expected = os.getenv('EXTENSION_TOKEN', '')
    return (bool(expected and candidate) and hmac.compare_digest(candidate.encode(), expected.encode())
            and integrations.legacy_allowed(accounts.first_user_id(), 'extension'))


def is_local_path(target: object) -> bool:
    """Ruta de esta app (`/algo`), no una URL externa ni `//host`."""
    return isinstance(target, str) and target.startswith('/') and not target.startswith('//') and '\\' not in target


def load_session_cookie(web_app: Any, cookie_value: Optional[str]) -> dict[str, Any]:
    """Contenido de la cookie de sesión (web_settings.WebApp); {} si no vale."""
    if not cookie_value:
        return {}
    try:
        data = web_app.session_serializer().loads(
            cookie_value, max_age=int(web_app.permanent_session_lifetime.total_seconds()))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def cookie_user_id(web_app: Any, cookie_value: Optional[str]) -> Optional[int]:
    """Usuario de la cookie de sesión, o None."""
    return session_user_id(load_session_cookie(web_app, cookie_value), web_app.secret_key)


def check_csrf_token(session_data: Mapping[str, Any], token: str, secret_key: str, time_limit: int = 3600) -> bool:
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


def _token_fp(purpose: str, user: dict[str, Any]) -> str:
    """Lo que invalida el enlace: la contraseña (recuperar) o el email (verificar)."""
    basis = user['password_hash'] if purpose == 'reset' else user['email']
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def account_token(secret_key: str, purpose: str, user: dict[str, Any]) -> str:
    """Enlace firmado para recuperar la contraseña o verificar el email; deja de valer al usarse."""
    from itsdangerous import URLSafeTimedSerializer
    return str(URLSafeTimedSerializer(secret_key, salt=f'account-{purpose}').dumps(
        {'uid': user['id'], 'fp': _token_fp(purpose, user)}))


def read_account_token(secret_key: str, purpose: str, token: str, max_age: int) -> Optional[dict[str, Any]]:
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
