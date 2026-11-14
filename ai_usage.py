"""Consumo de tokens de Gemini: contador mensual, tope opcional y caché de respuestas."""
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from limits.storage import storage_from_string

logger = logging.getLogger(__name__)

MONTH_SECONDS = 32 * 24 * 3600
CACHE_MAX_ENTRIES = 256
# Por encima de esta temperatura se esperan respuestas distintas (entrevistas, chat): no se cachean
CACHE_MAX_TEMPERATURE = 0.5

_state = {}
_cache = OrderedDict()
_lock = threading.Lock()


def _storage():
    """Mismo storage que el rate limit: con redis:// el contador es compartido entre instancias."""
    with _lock:
        if 'storage' not in _state:
            _state['storage'] = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
        return _state['storage']


def _month():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def _key(kind, month=None):
    return f"ai_usage:{month or _month()}:{kind}"


def _env_int(name, default=0):
    try:
        return int(os.getenv(name, default) or default)
    except ValueError:
        logger.error(f"{name} inválido ({os.getenv(name)!r}); se usa {default}")
        return default


def _env_float(name):
    try:
        return float(os.getenv(name, '') or 0)
    except ValueError:
        logger.error(f"{name} inválido ({os.getenv(name)!r}); se ignora")
        return 0.0


def monthly_limit():
    """AI_MONTHLY_TOKEN_LIMIT; 0 o vacío = sin tope."""
    return max(_env_int('AI_MONTHLY_TOKEN_LIMIT'), 0)


def _get(kind):
    try:
        return int(_storage().get(_key(kind)) or 0)
    except Exception as e:
        logger.warning(f"Contador de IA no disponible ({e})")
        return 0


def record(input_tokens, output_tokens):
    """Suma los tokens de una llamada al mes en curso."""
    try:
        storage = _storage()
        for kind, amount in (('input', input_tokens), ('output', output_tokens), ('calls', 1)):
            if amount:
                storage.incr(_key(kind), MONTH_SECONDS, amount=int(amount))
    except Exception as e:
        logger.warning(f"No se pudo registrar el consumo de IA ({e})")


def budget_exceeded():
    limit = monthly_limit()
    return bool(limit) and _get('input') + _get('output') >= limit


def summary():
    """Consumo del mes en curso, con costo estimado si se configuraron los precios."""
    input_tokens, output_tokens = _get('input'), _get('output')
    data = {
        'month': _month(),
        'calls': _get('calls'),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'monthly_token_limit': monthly_limit() or None,
        'cached_responses': len(_cache),
    }
    price_in = _env_float('AI_PRICE_INPUT_PER_MTOK')
    price_out = _env_float('AI_PRICE_OUTPUT_PER_MTOK')
    if price_in or price_out:
        data['estimated_cost_usd'] = round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 4)
    return data


def _cache_key(model, prompt, temperature):
    return hashlib.sha256(f"{model}\0{temperature}\0{prompt}".encode('utf-8')).hexdigest()


def _cache_ttl():
    return max(_env_int('AI_CACHE_TTL', 3600), 0)


def cache_get(model, prompt, temperature):
    if temperature > CACHE_MAX_TEMPERATURE or not _cache_ttl():
        return None
    key = _cache_key(model, prompt, temperature)
    with _lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires, text = entry
        if expires < time.monotonic():
            del _cache[key]
            return None
        _cache.move_to_end(key)
        return text


def cache_set(model, prompt, temperature, text):
    ttl = _cache_ttl()
    if temperature > CACHE_MAX_TEMPERATURE or not ttl:
        return
    with _lock:
        _cache[_cache_key(model, prompt, temperature)] = (time.monotonic() + ttl, text)
        _cache.move_to_end(_cache_key(model, prompt, temperature))
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def reset():
    """Descarta contadores, caché y configuración (tests)."""
    with _lock:
        _state.clear()
        _cache.clear()
