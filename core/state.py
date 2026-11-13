"""
core/state.py — Estado compartido de la aplicación (sin dependencia de Flask).
Logging, directorios, estado de scrapers y singletons pesados.
"""
import os
import logging

# ── Logging (con rotación: logs/app.log no crece sin límite) ──────────────────
for _folder in ['uploads', 'results', 'logs', 'profiles', 'temp']:
    os.makedirs(_folder, exist_ok=True)

from logging.handlers import RotatingFileHandler  # noqa: E402

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)

if not any(isinstance(h, RotatingFileHandler) for h in _root_logger.handlers):
    _file_handler = RotatingFileHandler(
        'logs/app.log', maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding='utf-8')
    _file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'))
    _root_logger.addHandler(_file_handler)

if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
           for h in _root_logger.handlers):
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'))
    _root_logger.addHandler(_stream_handler)

logger = logging.getLogger(__name__)

# ── Estado de scrapers (fallback local; se superpone con Celery en /status) ───
job_status = {
    'indeed_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'linkedin_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'computrabajo_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'bumeran_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'universal_scraping': {'status': 'idle', 'progress': 0, 'message': '', 'scrapers': {
        'indeed': {'status': 'idle', 'progress': 0},
        'linkedin': {'status': 'idle', 'progress': 0},
        'computrabajo': {'status': 'idle', 'progress': 0},
        'bumeran': {'status': 'idle', 'progress': 0}
    }},
    'connection_requests': {'status': 'idle', 'progress': 0, 'message': ''},
    'auto_apply': {'status': 'idle', 'progress': 0, 'message': ''}
}

# Mapeo clave de estado → nombre de tarea Celery
CELERY_TASK_NAMES = {
    'indeed_scraping': 'tasks.scraping_tasks.run_indeed_scraper',
    'linkedin_scraping': 'tasks.scraping_tasks.run_linkedin_scraper',
    'computrabajo_scraping': 'tasks.scraping_tasks.run_computrabajo_scraper',
    'bumeran_scraping': 'tasks.scraping_tasks.run_bumeran_scraper',
    'universal_scraping': 'tasks.scraping_tasks.run_universal_scraper',
    'connection_requests': 'tasks.connection_tasks.run_connection_requests',
    'auto_apply': 'tasks.ai_tasks.auto_apply_jobs',
}

# ── Registro de tareas activas ────────────────────────────────────────────────
# El task-id se persiste en Redis (sobrevive restarts y multi-worker);
# con fallback en memoria si no hay Redis. Valor Redis: JSON {id, ts}.
ACTIVE_TASKS_KEY = "empleoia:active_tasks"
_STALE_SECONDS = 6 * 3600  # tareas más viejas que esto → estado idle

active_tasks: dict = {}    # clave -> task_id (en memoria, fallback)
active_results: dict = {}  # clave -> objeto resultado local (eager o reciente)


_redis_cache = {"client": None, "checked_at": 0.0, "ttl": 30.0}


def _redis_client():
    """
    Cliente Redis con cache de 30s (positivo y negativo): sin Redis disponible,
    el primer fallo cuesta ~1s y los siguientes son instantáneos.
    """
    import time as _t
    now = _t.monotonic()
    if now - _redis_cache["checked_at"] < _redis_cache["ttl"]:
        return _redis_cache["client"]

    client = None
    try:
        import redis as redis_lib
        candidate = redis_lib.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True, socket_connect_timeout=0.5)
        candidate.ping()
        client = candidate
    except Exception:
        client = None

    _redis_cache["client"] = client
    _redis_cache["checked_at"] = now
    return client


def _remember_task_id(key: str, task_id: str) -> None:
    active_tasks[key] = task_id
    client = _redis_client()
    if client and task_id:
        try:
            import json as _json
            import time as _time
            client.hset(ACTIVE_TASKS_KEY, key,
                        _json.dumps({"id": task_id, "ts": _time.time()}))
            client.expire(ACTIVE_TASKS_KEY, 7 * 24 * 3600)
        except Exception:
            pass


def _lookup_task_id(key: str) -> str | None:
    client = _redis_client()
    if client:
        try:
            import json as _json
            import time as _time
            raw = client.hget(ACTIVE_TASKS_KEY, key)
            if raw:
                data = _json.loads(raw)
                task_id = data.get("id")
                if task_id and (_time.time() - float(data.get("ts", 0))) < _STALE_SECONDS:
                    return task_id
                if task_id and (_time.time() - float(data.get("ts", 0))) >= _STALE_SECONDS:
                    client.hdel(ACTIVE_TASKS_KEY, key)  # caducada
                return None
        except Exception:
            pass
    # Fallback en memoria con detección de caducidad
    task_id = active_tasks.get(key)
    return task_id


def dispatch_task(key: str, task, *args, **kwargs):
    """
    Despacha una tarea Celery; si no hay broker, la ejecuta eager en proceso.
    Las rutas async deben llamar esto vía `await asyncio.to_thread(...)`
    para no bloquear el event loop en el fallback eager.
    """
    try:
        result = task.delay(*args, **kwargs)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Celery broker no disponible ({e}); ejecutando tarea eager: {key}")
        result = task.apply(args=args, kwargs=kwargs)
    active_results[key] = result
    task_id = getattr(result, 'id', None)
    if task_id:
        _remember_task_id(key, task_id)
    return result


def _status_from_result(result) -> dict | None:
    try:
        state = result.state
        info = result.info or {}
    except Exception:
        return None

    if state == 'PROGRESS':
        return {
            'status': info.get('status', 'running'),
            'progress': info.get('progress', 0),
            'message': info.get('message', ''),
        }
    if state == 'SUCCESS':
        if isinstance(info, dict):
            return {
                'status': info.get('status', 'completed'),
                'progress': info.get('progress', 100),
                'message': info.get('message', 'Completed'),
            }
        return {'status': 'completed', 'progress': 100, 'message': 'Completed'}
    if state == 'FAILURE':
        return {
            'status': 'failed',
            'progress': 0,
            'message': str(info)[:300],
        }
    # PENDING / STARTED / RETRY
    return {
        'status': 'running',
        'progress': info.get('progress', 0) if isinstance(info, dict) else 0,
        'message': info.get('message', 'En cola...') if isinstance(info, dict) else 'En cola...',
    }


def get_task_status(key: str) -> dict | None:
    """Estado de la tarea activa para una clave, o None si no hay."""
    # 1) Objeto local (eager sin broker, o recién despachado)
    local = active_results.get(key)
    if local is not None:
        status = _status_from_result(local)
        if status:
            return status

    # 2) Backend de Celery por task-id persistido (restart / otro worker)
    task_id = _lookup_task_id(key)
    if not task_id:
        return None
    try:
        from celery_app import celery
        return _status_from_result(celery.AsyncResult(task_id))
    except Exception:
        return None


def get_all_status() -> dict:
    """Estado completo de todos los scrapers: Celery encima, fallback local."""
    import copy
    combined = copy.deepcopy(job_status)
    for key in list(combined.keys()):
        task_state = get_task_status(key)
        if task_state:
            combined[key].update(task_state)
    return combined


# Tareas de prueba (run_test_scraper)
test_tasks: dict = {}
TASK_DIR = os.path.join('temp', 'test_tasks')
os.makedirs(TASK_DIR, exist_ok=True)

# ── Base de datos (se reemplaza por SQLAlchemy en Fase 3b) ────────────────────
from db_config import db_manager  # noqa: F402,F401  (re-export para los routers)

# ── Singletons pesados (spaCy / TF-IDF) ───────────────────────────────────────
_resume_parser = None
_job_matcher = None


def get_resume_parser():
    global _resume_parser
    if _resume_parser is None:
        from resume_parser import resumeParser
        _resume_parser = resumeParser()
    return _resume_parser


def get_job_matcher():
    global _job_matcher
    if _job_matcher is None:
        from resume_parser import jobMatcher
        _job_matcher = jobMatcher()
    return _job_matcher


def reset_singletons():
    """Solo para tests."""
    global _resume_parser, _job_matcher
    _resume_parser = None
    _job_matcher = None
