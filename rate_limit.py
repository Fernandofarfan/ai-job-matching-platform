"""Límites de pedidos: por cuenta si hay sesión, si no por IP."""
import logging
import os
import threading
from typing import Any

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

logger = logging.getLogger(__name__)

DEFAULT_AI_RATE_LIMIT = '30 per minute'
DEFAULT_API_RATE_LIMIT = '300 per minute'
_state: dict[str, Any] = {}
_lock = threading.Lock()


def _parse_limit(env: str, default: str) -> Any:
    """Un valor inválido no desactiva el límite: se usa el valor por defecto."""
    value = os.getenv(env, default)
    try:
        return parse(value)
    except ValueError:
        logger.error(f"{env} inválido ({value!r}); se usa {default}")
        return parse(default)


def _limiter() -> dict[str, Any]:
    """Se crea una sola vez, en el primer uso, para leer la configuración ya cargada desde .env."""
    with _lock:
        if not _state:
            storage = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
            _state.update(
                limit=_parse_limit('AI_RATE_LIMIT', DEFAULT_AI_RATE_LIMIT),
                api_limit=_parse_limit('API_RATE_LIMIT', DEFAULT_API_RATE_LIMIT),
                storage=storage, limiter=MovingWindowRateLimiter(storage),
            )
        return _state


def client_ip(remote_addr: str | None, forwarded_for: str | None) -> str:
    """IP real del cliente.

    Detrás de un proxy (Cloud Run, nginx) todos los pedidos llegan desde la IP del proxy.
    TRUSTED_PROXY_HOPS=N toma la N-ésima IP desde el final de X-Forwarded-For, que es la que
    agregó el proxy propio; las anteriores las puede inventar el cliente.
    """
    try:
        hops = int(os.getenv('TRUSTED_PROXY_HOPS', '0') or 0)
    except ValueError:
        hops = 0
    if hops > 0 and forwarded_for:
        chain = [ip.strip() for ip in forwarded_for.split(',') if ip.strip()]
        if chain:
            return chain[-min(hops, len(chain))][:45]
    return remote_addr or 'unknown'


def client_key(user_id: int | None, ip: str | None) -> str:
    """Clave del contador: la cuenta si hay sesión, si no la IP."""
    return f'user:{user_id}' if user_id else f'ip:{ip or "unknown"}'


def _hit(limit_name: str, namespace: str, key: str, consume: bool = True) -> bool:
    """Suma un pedido a `key` (o solo consulta, con consume=False); False si superó el límite.

    Si el storage falla, deja pasar.
    """
    try:
        state = _limiter()
        check = state['limiter'].hit if consume else state['limiter'].test
        return bool(check(state[limit_name], namespace, key or 'unknown'))
    except Exception as e:
        logger.warning(f"Rate limit no disponible ({e}); se permite la solicitud")
        return True


def hit_page(spec: str, namespace: str, key: str) -> bool:
    """Suma un pedido al límite `spec` (p. ej. '5 per minute') de una página; False si lo superó."""
    try:
        state = _limiter()
        return bool(state['limiter'].hit(parse(spec), 'page', namespace, key or 'unknown'))
    except Exception as e:
        logger.warning(f"Rate limit no disponible ({e}); se permite la solicitud")
        return True


def hit_ai_limit(key: str) -> bool:
    """Suma una llamada de IA (/api/ai/*); False si superó AI_RATE_LIMIT."""
    return _hit('limit', 'ai', key)


def hit_api_limit(key: str) -> bool:
    """Suma un pedido a /api/*; False si superó API_RATE_LIMIT."""
    return _hit('api_limit', 'api', key)


def bad_token_allowed(ip: str) -> bool:
    """False si la IP ya mandó API_RATE_LIMIT tokens de extensión inválidos (sin consumir)."""
    return _hit('api_limit', 'bad_token', ip, consume=False)


def record_bad_token(ip: str) -> None:
    """Cuenta un token de extensión inválido de la IP."""
    _hit('api_limit', 'bad_token', ip)


def reset() -> None:
    """Descarta los contadores y vuelve a leer la configuración (tests)."""
    with _lock:
        _state.clear()
