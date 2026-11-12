"""Límite compartido de llamadas a IA (/api/ai/*) para Flask y FastAPI."""
import logging
import os
import threading

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

logger = logging.getLogger(__name__)

DEFAULT_AI_RATE_LIMIT = '30 per minute'
_state: dict = {}
_lock = threading.Lock()


def _parse_limit():
    """AI_RATE_LIMIT inválido no desactiva la cuota: se usa el valor por defecto."""
    value = os.getenv('AI_RATE_LIMIT', DEFAULT_AI_RATE_LIMIT)
    try:
        return parse(value)
    except ValueError:
        logger.error(f"AI_RATE_LIMIT inválido ({value!r}); se usa {DEFAULT_AI_RATE_LIMIT}")
        return parse(DEFAULT_AI_RATE_LIMIT)


def _limiter():
    """Se crea una sola vez, en el primer uso, para leer la configuración ya cargada desde .env."""
    with _lock:
        if not _state:
            storage = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
            _state.update(
                limit=_parse_limit(), storage=storage, limiter=MovingWindowRateLimiter(storage),
            )
        return _state


def hit_ai_limit(client_ip: str) -> bool:
    """Suma una llamada de IA para la IP; False si superó AI_RATE_LIMIT.

    Si el storage falla, deja pasar la solicitud.
    """
    try:
        state = _limiter()
        return state['limiter'].hit(state['limit'], 'ai', client_ip or 'unknown')
    except Exception as e:
        logger.warning(f"Rate limit no disponible ({e}); se permite la solicitud")
        return True


def reset() -> None:
    """Descarta los contadores y vuelve a leer la configuración (tests)."""
    with _lock:
        _state.clear()
