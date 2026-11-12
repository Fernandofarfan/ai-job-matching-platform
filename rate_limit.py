"""Límite compartido de llamadas a IA (/api/ai/*) para Flask y FastAPI."""
import logging
import os

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

logger = logging.getLogger(__name__)

_state = {}


def _limiter():
    """Se crea en el primer uso para leer AI_RATE_LIMIT y RATELIMIT_STORAGE_URI ya cargadas desde .env."""
    if not _state:
        storage = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
        _state.update(
            limit=parse(os.getenv('AI_RATE_LIMIT', '30 per minute')),
            storage=storage,
            limiter=MovingWindowRateLimiter(storage),
        )
    return _state


def hit_ai_limit(client_ip: str) -> bool:
    """Suma una llamada de IA para la IP; False si superó AI_RATE_LIMIT. Si el storage falla, deja pasar."""
    try:
        state = _limiter()
        return state['limiter'].hit(state['limit'], 'ai', client_ip or 'unknown')
    except Exception as e:
        logger.warning(f"Rate limit no disponible ({e}); se permite la solicitud")
        return True


def reset() -> None:
    """Descarta los contadores y vuelve a leer la configuración (tests)."""
    _state.clear()
