"""Lanza los scrapers en un thread local o en un worker de Celery (SCRAPER_BACKEND=celery).

Con Celery la búsqueda sobrevive a reinicios y escalado del contenedor web: el worker
publica el progreso como estado de la tarea y `refresh()` lo copia a `job_status`.
"""
import copy
import importlib
import logging
import os
from collections.abc import MutableMapping

import accounts
import i18n

logger = logging.getLogger(__name__)

TASK_NAME = 'tasks.scraping_tasks.run_web_job'
# Solo estas funciones pueden ejecutarse desde un mensaje del broker
JOBS = {
    'run_indeed_scraper_with_matching': 'services.portal_search',
    'run_linkedin_scraper_with_matching': 'services.portal_search',
    'run_computrabajo_job': 'scraping_jobs',
    'run_bumeran_job': 'scraping_jobs',
    'run_universal_job': 'scraping_jobs',
}
ACTIVE = ('queued', 'running', 'idle')
_TASK_TTL = 24 * 3600


class PerUserStatus(MutableMapping):
    """`job_status` separado por cuenta: cada usuario ve y modifica solo sus búsquedas."""

    def __init__(self, default):
        self._default = default
        self._by_user: dict = {}

    def _mine(self):
        uid = accounts.current_user_id()
        if uid not in self._by_user:
            self._by_user[uid] = copy.deepcopy(self._default)
        return self._by_user[uid]

    def __getitem__(self, key):
        return self._mine()[key]

    def __setitem__(self, key, value):
        self._mine()[key] = value

    def __delitem__(self, key):
        del self._mine()[key]

    def __iter__(self):
        return iter(self._mine())

    def __len__(self):
        return len(self._mine())


def _task_key(key):
    uid = accounts.current_user_id()
    return f'empleoia:scraper_task:{key}' if uid is None else f'empleoia:scraper_task:u{uid}:{key}'


def _remember(celery, key, task_id):
    """Guarda en Redis la última tarea de cada búsqueda: `job_status` es local a cada proceso web."""
    try:
        celery.backend.client.set(_task_key(key), task_id, ex=_TASK_TTL)
    except Exception as e:
        logger.warning(f'No se pudo guardar la tarea {task_id} de {key}: {e}')


def _recall(celery, key):
    try:
        value = celery.backend.client.get(_task_key(key))
    except Exception:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    return value if isinstance(value, str) else None


def use_celery():
    return os.getenv('SCRAPER_BACKEND', 'thread').strip().lower() == 'celery'


def resolve(name):
    if name not in JOBS:
        raise ValueError(f'Tarea de scraping desconocida: {name}')
    return getattr(importlib.import_module(JOBS[name]), name)


def launch(job_status, key, name, *args):
    """Arranca `name(*args)`; devuelve el id de la tarea Celery o None si corre en un thread."""
    func = resolve(name)
    if use_celery():
        from celery_app import celery
        result = celery.send_task(TASK_NAME, args=[key, name, list(args)],
                                 kwargs={'user_id': accounts.current_user_id()})
        _remember(celery, key, result.id)
        job_status[key] = {
            **job_status.get(key, {}),
            'status': 'queued', 'progress': 0, 'message': i18n.lazy('En cola...'), 'task_id': result.id,
        }
        return result.id
    accounts.thread(target=func, args=args, daemon=True).start()
    return None


def refresh(job_status):
    """Actualiza en `job_status` las búsquedas que corren en Celery.

    Adopta la última tarea guardada en Redis de cada búsqueda, así otra instancia web
    (o la misma tras reiniciar) sigue mostrando el progreso.
    """
    if use_celery():
        from celery_app import celery
        for key, value in job_status.items():
            task_id = _recall(celery, key) if isinstance(value, dict) else None
            if task_id and task_id != value.get('task_id'):
                value.update(task_id=task_id, status='queued')
    pending = {
        key: value['task_id'] for key, value in job_status.items()
        if isinstance(value, dict) and value.get('task_id') and value.get('status') in ACTIVE
    }
    if not pending:
        return job_status
    from celery_app import celery
    for key, task_id in pending.items():
        try:
            result = celery.AsyncResult(task_id)
            state, info = result.state, result.info
        except Exception as e:
            logger.warning(f'No se pudo consultar la tarea {task_id}: {e}')
            continue
        if state in ('PROGRESS', 'SUCCESS') and isinstance(info, dict):
            job_status[key] = {**info, 'task_id': task_id}
            if state == 'SUCCESS' and job_status[key].get('status') in ACTIVE:
                job_status[key]['status'] = 'completed'
        elif state == 'FAILURE':
            job_status[key].update(status='failed', message=i18n.lazy('Error: %(error)s', error=str(info)[:100]))
        elif state == 'STARTED':
            job_status[key]['status'] = 'running'
    return job_status
