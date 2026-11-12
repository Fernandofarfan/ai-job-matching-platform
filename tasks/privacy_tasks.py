"""Privacidad de CVs: cifrado de los archivos y perfiles viejos y retención (CV_RETENTION_DAYS)."""
import logging
import os

from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="tasks.privacy_tasks.enforce_cv_retention")
def enforce_cv_retention():
    """Cifra los CVs y perfiles en texto plano y borra los que superan CV_RETENTION_DAYS junto con su perfil."""
    import cv_storage
    import profile_store

    encrypted = cv_storage.encrypt_existing()
    try:
        encrypted += profile_store.encrypt_existing()
    except Exception as e:
        logger.warning(f"No se pudieron cifrar los perfiles existentes: {e}")
    days = int(os.getenv("CV_RETENTION_DAYS", "0") or 0)
    if days <= 0:
        return {"encrypted": encrypted, "deleted_cvs": 0, "deleted_profiles": 0, "deleted_generated": 0}

    deleted_generated = cv_storage.purge_generated(days)
    if not profile_store.primary_available():
        logger.warning("Retención de CVs postergada: MySQL no responde y quedarían perfiles sin borrar")
        return {"encrypted": encrypted, "deleted_cvs": 0, "deleted_profiles": 0,
                "deleted_generated": deleted_generated}

    import accounts

    old = set(cv_storage.expired(days))
    deleted_profiles = 0
    for uid in accounts.user_ids() or [None]:
        with accounts.as_user(uid):
            for role, data in profile_store.get_all_profiles().items():
                if data.get("resume_filename") in old and profile_store.delete_profile(role) is not None:
                    deleted_profiles += 1
    deleted_cvs = sum(cv_storage.delete(name) for name in old)
    logger.info(f"Retención de CVs ({days} días): {deleted_cvs} CVs, {deleted_profiles} perfiles, "
                f"{deleted_generated} documentos generados")
    return {"encrypted": encrypted, "deleted_cvs": deleted_cvs,
            "deleted_profiles": deleted_profiles, "deleted_generated": deleted_generated}
