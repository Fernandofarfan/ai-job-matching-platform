"""Lanza los scrapers en un thread local o en un worker de Celery (SCRAPER_BACKEND=celery).

Con Celery la búsqueda sobrevive a reinicios y escalado del contenedor web: el worker
publica el progreso como estado de la tarea y `refresh()` lo copia a `job_status`.
"""
import importlib
import logging
import os
import threading

logger = logging.getLogger(__name__)

TASK_NAME = 'tasks.scraping_tasks.run_web_job'
# Solo estas funciones pueden ejecutarse desde un mensaje del broker
JOBS = {
    'run_indeed_scraper_with_matching': 'app',
    'run_linkedin_scraper_with_matching': 'app',
    'run_computrabajo_job': 'web.scrapers',
    'run_bumeran_job': 'web.scrapers',
    'run_universal_job': 'web.scrapers',
}
ACTIVE = ('queued', 'running', 'idle')


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
        result = celery.send_task(TASK_NAME, args=[key, name, list(args)])
        job_status[key] = {
            **job_status.get(key, {}),
            'status': 'queued', 'progress': 0, 'message': 'En cola...', 'task_id': result.id,
        }
        return result.id
    threading.Thread(target=func, args=args, daemon=True).start()
    return None


def refresh(job_status):
    """Actualiza en `job_status` las búsquedas que corren en Celery."""
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
            job_status[key].update(status='failed', message=f'Error: {str(info)[:100]}')
        elif state == 'STARTED':
            job_status[key]['status'] = 'running'
    return job_status
