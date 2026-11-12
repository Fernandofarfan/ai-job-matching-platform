"""
tasks/ai_tasks.py — Tareas de IA asíncronas vía Celery
Para procesamiento por lotes, análisis semántico masivo y exportaciones.
"""
import os
import glob
import logging

from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="tasks.ai_tasks.generate_documents_batch")
def generate_documents_batch(self, kind: str, filename: str, num_jobs: int, user_id=None):
    """Genera los documentos como `user_id` (lee su CSV y guarda en su carpeta)."""
    import accounts
    with accounts.as_user(user_id):
        return _generate_documents_batch(self, kind, filename, num_jobs)


def _generate_documents_batch(self, kind: str, filename: str, num_jobs: int):
    """Cartas o CVs adaptados para las primeras `num_jobs` ofertas de un CSV de results/."""
    import document_batch
    from app import get_resume_text_from_profile

    def progress(done, total):
        self.update_state(state="PROGRESS", meta={
            "progress": int(done / max(total, 1) * 100),
            "message": f"Documento {done} de {total}",
        })

    try:
        return document_batch.run(kind, filename, num_jobs, get_resume_text_from_profile(), progress=progress)
    except document_batch.BatchError as e:
        return {"success": False, "error": str(e)}


@celery.task(name="tasks.ai_tasks.cleanup_old_temp_files")
def cleanup_old_temp_files(days: int = 7):
    """Limpia archivos temporales más viejos que N días."""
    import time as time_mod

    cleaned = 0
    cutoff = time_mod.time() - (days * 86400)

    dirs_to_clean = [
        os.path.join("temp", "test_tasks"),
        os.path.join("temp", "resumes"),
    ]

    for dir_path in dirs_to_clean:
        if not os.path.exists(dir_path):
            continue
        for filepath in glob.glob(os.path.join(dir_path, "*")):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    cleaned += 1
            except Exception as e:
                logger.warning(f"Could not delete {filepath}: {e}")

    logger.info(f"Cleanup: removed {cleaned} old temp files")
    return {"cleaned": cleaned, "cutoff_days": days}


AUTO_APPLY_MAX_JOBS = 10
_MAX_FORM_STEPS = 10
AUTO_APPLY_DISABLED_MESSAGE = (
    "Auto-Apply está apagado (AUTO_APPLY_ENABLED=false). Postular con bots puede violar "
    "los términos de LinkedIn y hacer que te bloqueen la cuenta."
)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def _is_linkedin_job(link) -> bool:
    from urllib.parse import urlparse

    try:
        url = urlparse(str(link))
        host = (url.hostname or "").lower()
    except ValueError:
        return False
    return (url.scheme == "https" and (host == "linkedin.com" or host.endswith(".linkedin.com"))
            and url.path.startswith("/jobs/"))


@celery.task(bind=True, name="tasks.ai_tasks.auto_apply_jobs")
def auto_apply_jobs(self, resume_path: str, user_profile: dict, job_links: list):
    """
    Experimental y apagado por defecto: completa postulaciones 'Easy Apply' de LinkedIn con Playwright.

    Requiere AUTO_APPLY_ENABLED=true. Sin AUTO_APPLY_SUBMIT=true recorre el formulario pero no lo envía.
    """
    if not _env_flag("AUTO_APPLY_ENABLED"):
        logger.warning("Auto-Apply pedido con AUTO_APPLY_ENABLED apagado; no se hace nada")
        return {"status": "disabled", "message": AUTO_APPLY_DISABLED_MESSAGE}

    from scrapers.linkedin_pw import linkedinClass
    import time

    links = [link for link in job_links if _is_linkedin_job(link)][:AUTO_APPLY_MAX_JOBS]
    submit = _env_flag("AUTO_APPLY_SUBMIT")
    token = os.getenv("LINKEDIN_LI_AT") or os.getenv("LI_AT_TOKEN") or (user_profile or {}).get("li_at_token")
    logger.warning(f"Auto-Apply experimental: {len(links)} ofertas, envío {'activado' if submit else 'desactivado'}")

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando Auto-Apply..."})
        bot = linkedinClass(li_at_token=token)
        if not bot.login_with_cookie():
            return {"status": "failed", "message": "Falló el login de LinkedIn para Auto-Apply."}

        applied = ready = 0
        for i, link in enumerate(links):
            self.update_state(state="PROGRESS", meta={
                "progress": 20 + int((i / max(len(links), 1)) * 70),
                "message": f"Oferta {i + 1} de {len(links)}..."
            })
            try:
                bot.page.goto(link)
                time.sleep(2)
                easy_apply_btn = bot.page.locator("button.jobs-apply-button")
                if easy_apply_btn.count() == 0 or "Easy Apply" not in easy_apply_btn.inner_text():
                    continue
                easy_apply_btn.click()
                time.sleep(2)
                for _ in range(_MAX_FORM_STEPS):
                    next_btn = bot.page.locator("button[aria-label='Continue to next step']")
                    if next_btn.count() == 0:
                        break
                    next_btn.click()
                    time.sleep(1)
                submit_btn = bot.page.locator("button[aria-label='Submit application']")
                if submit_btn.count() == 0:
                    continue
                if submit:
                    submit_btn.click()
                    applied += 1
                    logger.info(f"Auto-Apply enviado: {link}")
                else:
                    ready += 1
            except Exception as loop_e:
                logger.error(f"Error en Auto-Apply para {link}: {loop_e}")

        return {"status": "completed", "submitted": submit, "applied_count": applied, "ready_count": ready,
                "total_attempted": len(links), "skipped": len(job_links) - len(links)}

    except Exception as e:
        logger.error(f"AutoApply fatal error: {e}", exc_info=True)
        return {"status": "failed", "error": "No se pudo completar Auto-Apply"}
