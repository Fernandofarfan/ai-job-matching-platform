"""
db_config.py — Shim de compatibilidad.

El SQL raw (DatabaseManager) fue reemplazado por el ORM SQLAlchemy
(models.SQLAlchemyManager). Este módulo conserva el nombre de import
`from db_config import db_manager` que usan todos los routers/tasks.
"""
from models import orm_manager as db_manager  # noqa: F401

# Alias legacy usado por tasks/gmail_tracker.py
_STAGE_MAP = {
    "bookmarked": "bookmarked",
    "applying": "applying",
    "applied": "applied",
    "applied ": "applied",
    "interview": "interviewing",
    "interviewing": "interviewing",
    "offer": "negotiating",
    "negotiating": "negotiating",
    "accepted": "accepted",
    "rejected": "rejected",
}


class trackerDbClass:
    """Compatibilidad con el viejo trackerDbClass (ahora sobre el ORM)."""

    def fetch_all_tracked(self):
        return db_manager.get_all_tracked_jobs()

    def fetch_all_tracked_by_status(self, status: str):
        return db_manager.get_applications({'status': status})

    def move_to_stage(self, job_id: int, stage: str) -> bool:
        """Mueve un job a una etapa (usado por tasks/gmail_tracker.py)."""
        mapped = _STAGE_MAP.get((stage or "").strip().lower())
        if not mapped:
            raise ValueError(f"Etapa desconocida: {stage!r}")
        return db_manager.update_job_status(int(job_id), mapped)
