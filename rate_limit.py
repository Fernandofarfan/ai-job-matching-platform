"""Límite compartido de llamadas a IA (/api/ai/*) para Flask y FastAPI."""
import logging
import os

from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

logger = logging.getLogger(__name__)

AI_RATE_LIMIT = parse(os.getenv('AI_RATE_LIMIT', '30 per minute'))
_storage = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
_limiter = MovingWindowRateLimiter(_storage)


def hit_ai_limit(client_ip: str) -> bool:
    """Suma una llamada de IA para la IP; False si superó AI_RATE_LIMIT. Si el storage falla, deja pasar."""
    try:
        return _limiter.hit(AI_RATE_LIMIT, 'ai', client_ip or 'unknown')
    except Exception as e:
        logger.warning(f"Rate limit no disponible ({e}); se permite la solicitud")
        return True


def reset() -> None:
    """Reinicia los contadores (tests)."""
    _storage.reset()
