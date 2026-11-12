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

_state: dict = {}
_cache: OrderedDict = OrderedDict()
_lock = threading.Lock()


def _storage():
    """Mismo storage que el rate limit: con redis:// el contador es compartido entre instancias."""
    with _lock:
        if 'storage' not in _state:
            _state['storage'] = storage_from_string(os.getenv('RATELIMIT_STORAGE_URI', 'memory://'))
        return _state['storage']


def _redis():
    """Cliente Redis si RATELIMIT_STORAGE_URI es redis://: la caché de respuestas se comparte entre instancias."""
    uri = os.getenv('RATELIMIT_STORAGE_URI', '')
    if not uri.startswith(('redis://', 'rediss://')):
        return None
    with _lock:
        if 'redis' not in _state:
            import redis
            _state['redis'] = redis.Redis.from_url(uri, socket_timeout=1)
        return _state['redis']


def _month():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def _key(kind, month=None, user=None):
    scope = '' if user is None else f':u{user}'
    return f"ai_usage:{month or _month()}{scope}:{kind}"


def _uid():
    import accounts
    return accounts.current_user_id()


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


def user_monthly_limit():
    """AI_USER_MONTHLY_TOKEN_LIMIT: tope por cuenta; 0 o vacío = sin tope."""
    return max(_env_int('AI_USER_MONTHLY_TOKEN_LIMIT'), 0)


def _get(kind, user=None):
    try:
        return int(_storage().get(_key(kind, user=user)) or 0)
    except Exception as e:
        logger.warning(f"Contador de IA no disponible ({e})")
        return 0


def record(input_tokens, output_tokens):
    """Suma los tokens de una llamada al mes en curso."""
    try:
        import observability
        observability.observe_ai(input_tokens, output_tokens)
    except Exception as e:
        logger.debug(f"Métricas de IA no registradas ({e})")
    try:
        storage = _storage()
        uid = _uid()
        for user in ([None] if uid is None else [None, uid]):
            for kind, amount in (('input', input_tokens), ('output', output_tokens), ('calls', 1)):
                if amount:
                    storage.incr(_key(kind, user=user), MONTH_SECONDS, amount=int(amount))
    except Exception as e:
        logger.warning(f"No se pudo registrar el consumo de IA ({e})")


def budget_exceeded():
    """True si se llegó al tope de la instancia o al de la cuenta actual."""
    limit = monthly_limit()
    if limit and _get('input') + _get('output') >= limit:
        return True
    uid, user_limit = _uid(), user_monthly_limit()
    return uid is not None and bool(user_limit) and _get('input', uid) + _get('output', uid) >= user_limit


def account_usage(user_id) -> dict:
    """Llamadas y tokens del mes en curso de una cuenta (panel de administración)."""
    tokens_in, tokens_out = _get('input', user_id), _get('output', user_id)
    return {'calls': _get('calls', user_id), 'total_tokens': tokens_in + tokens_out}


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
        'cache_hits': _get('cache_hits'),
    }
    uid = _uid()
    if uid is not None:
        mine_in, mine_out = _get('input', uid), _get('output', uid)
        data['account'] = {
            'calls': _get('calls', uid),
            'input_tokens': mine_in,
            'output_tokens': mine_out,
            'total_tokens': mine_in + mine_out,
            'monthly_token_limit': user_monthly_limit() or None,
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


def _remember(key, text, ttl):
    with _lock:
        _cache[key] = (time.monotonic() + ttl, text)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def _count_hit():
    try:
        _storage().incr(_key('cache_hits'), MONTH_SECONDS)
    except Exception as e:
        logger.debug(f"Acierto de caché no registrado ({e})")


def cache_get(model, prompt, temperature):
    """Respuesta guardada para el mismo modelo, prompt y temperatura (en memoria o en Redis), o None."""
    ttl = _cache_ttl()
    if temperature > CACHE_MAX_TEMPERATURE or not ttl:
        return None
    key = _cache_key(model, prompt, temperature)
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] < time.monotonic():
            del _cache[key]
            entry = None
        if entry:
            _cache.move_to_end(key)
    if entry:
        _count_hit()
        return entry[1]
    try:
        client = _redis()
        shared, remaining = (
            client.pipeline().get(f'ai_cache:{key}').ttl(f'ai_cache:{key}').execute() if client else (None, 0)
        )
    except Exception as e:
        logger.warning(f"Caché de IA en Redis no disponible ({e})")
        shared, remaining = None, 0
    if shared is None:
        return None
    text = shared.decode('utf-8') if isinstance(shared, bytes) else shared
    if remaining and remaining > 0:
        _remember(key, text, min(remaining, ttl))  # vence junto con la copia de Redis
    _count_hit()
    return text


def cache_set(model, prompt, temperature, text):
    """Guarda la respuesta en memoria y, con Redis, para las demás instancias (AI_CACHE_TTL segundos)."""
    ttl = _cache_ttl()
    if temperature > CACHE_MAX_TEMPERATURE or not ttl:
        return
    key = _cache_key(model, prompt, temperature)
    _remember(key, text, ttl)
    try:
        client = _redis()
        if client:
            client.setex(f'ai_cache:{key}', ttl, text)
    except Exception as e:
        logger.warning(f"Caché de IA en Redis no disponible ({e})")


def reset():
    """Descarta contadores, caché y configuración (tests)."""
    with _lock:
        _state.clear()
        _cache.clear()
