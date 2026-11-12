"""Configuración de la web (antes `app.config` de Flask) y la cookie de sesión.

La cookie se firma con el mismo formato que usaba Flask (itsdangerous, salt `cookie-session`, HMAC-SHA1 y
JSON con etiquetas), así las sesiones abiertas antes de quitar Flask siguen valiendo.
"""
import hashlib
import json
import logging
import os
import uuid
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any

from itsdangerous import URLSafeTimedSerializer
from markupsafe import Markup

logger = logging.getLogger(__name__)
_TAGS = (' di', ' t', ' b', ' m', ' u', ' d')


def _tag(value: Any) -> Any:
    """Valor con las etiquetas de flask.json.tag (tuplas, bytes, Markup, UUID y fechas)."""
    if isinstance(value, dict):
        if len(value) == 1 and next(iter(value)) in _TAGS:
            key = next(iter(value))
            return {' di': {f'{key}__': _tag(value[key])}}
        return {k: _tag(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return {' t': [_tag(v) for v in value]}
    if isinstance(value, list):
        return [_tag(v) for v in value]
    if isinstance(value, bytes):
        return {' b': b64encode(value).decode('ascii')}
    if callable(getattr(value, '__html__', None)):
        return {' m': str(value.__html__())}
    if isinstance(value, uuid.UUID):
        return {' u': value.hex}
    if isinstance(value, datetime):
        return {' d': format_datetime(value.astimezone(timezone.utc), usegmt=True)}
    return value


def _untag(obj: dict) -> Any:
    """Inverso de `_tag` (object_hook de json.loads)."""
    if len(obj) != 1:
        return obj
    key, value = next(iter(obj.items()))
    if key == ' di':
        inner_key = next(iter(value))
        return {inner_key[:-2]: value[inner_key]}
    if key == ' t':
        return tuple(value)
    if key == ' b':
        return b64decode(value)
    if key == ' m':
        return Markup(value)
    if key == ' u':
        return uuid.UUID(value)
    if key == ' d':
        return parsedate_to_datetime(value)
    return obj


class TaggedJSON:
    """Serializador de la cookie, compatible con flask.json.tag.TaggedJSONSerializer."""

    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(_tag(value), separators=(',', ':'))

    @staticmethod
    def loads(value: str | bytes) -> Any:
        return json.loads(value, object_hook=_untag)


class WebApp:
    """Clave, configuración y globals de app.py que comparten las páginas de FastAPI."""

    def __init__(self):
        self.config: dict[str, Any] = {
            'SECRET_KEY': os.getenv('SECRET_KEY'),
            'MAX_CONTENT_LENGTH': int(os.getenv('MAX_UPLOAD_MB', '16')) * 1024 * 1024,
            'SESSION_COOKIE_NAME': 'session',
            'SESSION_COOKIE_SAMESITE': 'Lax',
            'SESSION_COOKIE_SECURE': os.getenv('SESSION_COOKIE_SECURE', '0') == '1',
            'SESSION_COOKIE_HTTPONLY': True,
            'SESSION_REFRESH_EACH_REQUEST': True,
            'PERMANENT_SESSION_LIFETIME': timedelta(days=31),
            'WTF_CSRF_ENABLED': True,
            'WTF_CSRF_TIME_LIMIT': 3600,
            'RATELIMIT_ENABLED': True,
            'DEBUG': os.getenv('FLASK_DEBUG', '0') == '1',
        }
        if not self.config['SECRET_KEY']:
            logger.warning("SECRET_KEY no definida: se usa una clave temporal y las sesiones se pierden al reiniciar")
            self.config['SECRET_KEY'] = os.urandom(24)
        self.extensions: dict[str, Any] = {}

    @property
    def secret_key(self):
        """SECRET_KEY de la config (firma la sesión, el CSRF y los enlaces de las cuentas)."""
        return self.config['SECRET_KEY']

    @property
    def debug(self) -> bool:
        """Modo debug (FLASK_DEBUG=1)."""
        return bool(self.config.get('DEBUG'))

    @debug.setter
    def debug(self, value: bool) -> None:
        self.config['DEBUG'] = bool(value)

    @property
    def permanent_session_lifetime(self) -> timedelta:
        """Duración de una sesión permanente."""
        return self.config['PERMANENT_SESSION_LIFETIME']

    def session_serializer(self) -> URLSafeTimedSerializer:
        """Firma de la cookie `session`, igual que SecureCookieSessionInterface de Flask."""
        return URLSafeTimedSerializer(self.secret_key, salt='cookie-session', serializer=TaggedJSON,
                                      signer_kwargs={'key_derivation': 'hmac', 'digest_method': hashlib.sha1})
