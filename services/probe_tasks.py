"""Pruebas de scrapers en segundo plano: estado en memoria y en disco, visible entre workers de Gunicorn."""
import json
import logging
import os

logger = logging.getLogger(__name__)

tasks: dict = {}
TASK_DIR = os.path.join('temp', 'test_tasks')
os.makedirs(TASK_DIR, exist_ok=True)


def _path(task_id: str) -> str:
    return os.path.join(TASK_DIR, f"{task_id}.json")


def save(task_id: str):
    """Guarda en disco el estado de la prueba `task_id`."""
    try:
        task = tasks.get(task_id)
        if task is None:
            return
        with open(_path(task_id), 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False)
    except Exception:
        logger.exception(f"Failed to save task {task_id} to disk")


def load(task_id: str):
    """Estado guardado de la prueba `task_id` (None si no existe)."""
    path = _path(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Failed to load task {task_id} from disk")
        return None
