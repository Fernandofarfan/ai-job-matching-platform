"""
celery_app.py — Configuración central de Celery para EmpleoIA
Permite ejecutar scrapers y tareas de IA de forma asíncrona.
"""
import os
import sys
from celery import Celery
from celery.signals import worker_init
from dotenv import load_dotenv

load_dotenv()

_ROOT = os.path.dirname(os.path.abspath(__file__))


@worker_init.connect
def _project_on_path(**_):
    """El CLI de celery quita el cwd del path tras cargar la app; las tareas importan app, job_dispatch, etc."""
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "empleoia",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.scraping_tasks",
        "tasks.ai_tasks",
        "tasks.notification_tasks",
    ],
)

celery.conf.update(
    # Serialización
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,

    # Reintentos
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,

    # Expiración de resultados (24 horas)
    result_expires=86400,

    # Colas separadas por tipo de tarea
    task_routes={
        "tasks.scraping_tasks.*": {"queue": "scraping"},
        "tasks.ai_tasks.*": {"queue": "ai_processing"},
        "tasks.notification_tasks.*": {"queue": "notifications"},
    },

    # Rate limits para scraping (evitar bloqueos)
    task_annotations={
        "tasks.scraping_tasks.run_linkedin_scraper": {"rate_limit": "2/m"},
        "tasks.scraping_tasks.run_indeed_scraper": {"rate_limit": "2/m"},
    },

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)


# ── Beat schedule (tareas periódicas con APScheduler/Celery Beat) ─────────────
celery.conf.beat_schedule = {
    # Verificar follow-ups pendientes cada día a las 9am
    "check-followups-daily": {
        "task": "tasks.notification_tasks.check_and_send_followup_reminders",
        "schedule": 86400,  # 24 horas en segundos
    },
    # Búsquedas guardadas: avisa solo por ofertas nuevas
    "run-job-alerts": {
        "task": "tasks.notification_tasks.run_job_alerts",
        "schedule": float(os.getenv("ALERTS_INTERVAL_HOURS", "6")) * 3600,
    },
    # Limpiar archivos tmp antiguos cada semana
    "cleanup-old-temp-files": {
        "task": "tasks.ai_tasks.cleanup_old_temp_files",
        "schedule": 604800,  # 7 días
    },
}


if __name__ == "__main__":
    celery.start()
