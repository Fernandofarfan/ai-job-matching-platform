"""Privacidad: cifrado de CVs y perfiles viejos, retención de CVs (CV_RETENTION_DAYS) y borrado de cuentas inactivas."""
from datetime import datetime, timedelta
from typing import Any
import logging
import os

from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="tasks.privacy_tasks.enforce_cv_retention")
def enforce_cv_retention() -> dict[str, Any]:
    """Cifra los CVs y perfiles en texto plano y borra los que superan CV_RETENTION_DAYS junto con su perfil."""
    import cv_storage
    import profile_store

    encrypted = cv_storage.encrypt_existing()
    try:
        import security_events
        security_events.purge()
    except Exception as e:
        logger.warning(f"No se pudieron borrar los eventos de seguridad viejos: {e}")
    try:
        import user_sessions
        user_sessions.purge()
    except Exception as e:
        logger.warning(f"No se pudieron borrar las sesiones vencidas: {e}")
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
    for uid in accounts.owner_ids():
        with accounts.as_user(uid):
            for role, data in profile_store.get_all_profiles().items():
                if data.get("resume_filename") in old and profile_store.delete_profile(role) is not None:
                    deleted_profiles += 1
    deleted_cvs = sum(cv_storage.delete(name) for name in old)
    logger.info(f"Retención de CVs ({days} días): {deleted_cvs} CVs, {deleted_profiles} perfiles, "
                f"{deleted_generated} documentos generados")
    return {"encrypted": encrypted, "deleted_cvs": deleted_cvs,
            "deleted_profiles": deleted_profiles, "deleted_generated": deleted_generated}


def _inactivity_days() -> tuple[int, int]:
    """(ACCOUNT_INACTIVITY_DAYS, días de aviso); el aviso es como mucho la mitad del plazo."""
    days = int(os.getenv("ACCOUNT_INACTIVITY_DAYS", "0") or 0)
    notice = int(os.getenv("ACCOUNT_INACTIVITY_NOTICE_DAYS", "30") or 30)
    return days, max(1, min(notice, days // 2))


def _delete_inactive(user_id: int) -> bool:
    """Borra los CVs y perfiles de la cuenta y después la cuenta, como "Borrar cuenta" en Mi cuenta."""
    import accounts
    import cv_storage
    import profile_store

    try:
        with accounts.as_user(user_id):
            resumes = {p.get("resume_filename") for p in profile_store.get_all_profiles().values()} - {None, ""}
            profile_store.delete_all()
            for name in resumes:
                cv_storage.delete(name)
        accounts.delete_account(user_id)
        return True
    except Exception as e:
        logger.error(f"No se pudo borrar la cuenta inactiva {user_id}: {e}")
        return False


@celery.task(name="tasks.privacy_tasks.enforce_account_inactivity")
def enforce_account_inactivity() -> dict[str, Any]:
    """Avisa por email a las cuentas sin entrar hace ACCOUNT_INACTIVITY_DAYS menos el aviso, y borra las que siguen
    sin entrar al vencer el aviso. Sin aviso enviado no se borra nada; la primera cuenta (administradora) no se toca."""
    import account_notify
    import accounts
    import profile_store

    days, notice = _inactivity_days()
    if days <= 0:
        return {"notified": 0, "deleted": 0}
    if not profile_store.primary_available():
        logger.warning("Borrado de cuentas inactivas postergado: MySQL no responde")
        return {"notified": 0, "deleted": 0}
    now = datetime.now().replace(microsecond=0)  # MySQL guarda DATETIME sin microsegundos; si no, == nunca coincide
    first = accounts.first_user_id()
    notified = deleted = 0
    for user in accounts.inactive_accounts(now - timedelta(days=days - notice)):
        if user["id"] == first:
            continue
        if user["notice_at"] is None:
            # se marca antes de mandar: si dos workers corren a la vez, uno solo manda el email
            if accounts.set_inactivity_notice(user["id"], now):
                if account_notify.send_inactivity_notice(user, now + timedelta(days=notice)):
                    notified += 1
                else:
                    accounts.clear_inactivity_notice(user["id"], now)
        elif user["notice_at"] <= now - timedelta(days=notice) and accounts.still_noticed(user["id"], user["notice_at"]):
            deleted += _delete_inactive(user["id"])
    logger.info(f"Cuentas inactivas ({days} días, aviso de {notice}): {notified} avisadas, {deleted} borradas")
    return {"notified": notified, "deleted": deleted}
