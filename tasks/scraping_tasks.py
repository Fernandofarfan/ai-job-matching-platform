"""tasks/scraping_tasks.py — corre en el worker de Celery las búsquedas que lanza la web (job_dispatch)."""
import copy
import logging
from typing import Any

import accounts
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="tasks.scraping_tasks.run_web_job")
def run_web_job(self: Any, key: str, name: str, args: list[Any], poll_seconds: float = 2.0,
                user_id: int | None = None) -> dict[str, Any]:
    """Corre en el worker el mismo scraper que lanza la web (como `user_id`) y publica su `job_status[key]`."""
    import job_dispatch
    from services.state import job_status as status

    func = job_dispatch.resolve(name)
    with accounts.as_user(user_id):
        status[key] = {**status.get(key, {}), "status": "running", "progress": 0, "message": "Iniciando..."}
        worker = accounts.thread(target=func, args=args, daemon=True)
        worker.start()
        while worker.is_alive():
            self.update_state(state="PROGRESS", meta=copy.deepcopy(status.get(key, {})))
            worker.join(poll_seconds)
        final: dict[str, Any] = copy.deepcopy(status.get(key, {}))
    if final.get("status") in job_dispatch.ACTIVE:
        final["status"] = "completed"
    return final
