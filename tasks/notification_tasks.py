"""
tasks/notification_tasks.py — Tareas de notificaciones vía Celery + Email
Envía alertas de follow-up, nuevos trabajos relevantes y resúmenes semanales.
"""
import logging
import os
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from celery_app import celery
from notification_messages import (
    WEEKLY_DAYS,
    _get_email_template,
    _telegram_chunks,
    alert_email_html,
    alert_telegram_text,
    due_followups,
    followup_email_html,
    followup_telegram_text,
    weekly_digest_data,
    weekly_digest_empty,
    weekly_digest_html,
)

logger = logging.getLogger(__name__)

# ── Configuración SMTP ────────────────────────────────────────────────────────
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", SMTP_USER)


def _send_email(to: str, subject: str, html_body: str) -> bool:
    """Envía un email HTML por el proveedor configurado (email_delivery.py: reintentos y rebotes)."""
    import email_delivery
    return email_delivery.send(to, subject, html_body)


@celery.task(name="tasks.notification_tasks.send_followup_reminder")
def send_followup_reminder(job_data: dict[str, Any], user_email: str) -> bool:
    """Envía un recordatorio de follow-up para un trabajo específico."""
    company = job_data.get("company", "la empresa")
    title = job_data.get("title", "el puesto")
    applied_date = job_data.get("applied_date", "")

    body = f"""
    <p>¡Es hora de hacer follow-up! 📬</p>
    <div style="background:#232336;padding:20px;border-radius:10px;margin:15px 0;
                border-left:4px solid #667eea;">
        <strong style="color:#a78bfa;">Puesto:</strong> {title}<br>
        <strong style="color:#a78bfa;">Empresa:</strong> {company}<br>
        <strong style="color:#a78bfa;">Aplicado el:</strong> {str(applied_date)[:10]}<br>
    </div>
    <p>Han pasado varios días desde tu postulación. Es buen momento para:</p>
    <ul>
        <li>Enviar un email de seguimiento al reclutador</li>
        <li>Conectar en LinkedIn con alguien de la empresa</li>
        <li>Actualizar el estado en tu tracker</li>
    </ul>"""

    html = _get_email_template(
        f"⏰ Follow-up pendiente: {company}",
        body,
        "http://localhost:5000/tracker",
        "Ver en Job Tracker"
    )
    return _send_email(user_email, f"🔔 EmpleoIA: Follow-up recomendado para {company}", html)


@celery.task(name="tasks.notification_tasks.send_new_jobs_digest")
def send_new_jobs_digest(jobs: list[Any], user_email: str) -> bool:
    """Envía un resumen de nuevos trabajos encontrados."""
    if not jobs:
        return False

    jobs_html = ""
    for job in jobs[:10]:  # máximo 10 en el email
        match_score = job.get("overall_match", job.get("ai_match_score", 0))
        score_color = "#22c55e" if float(match_score or 0) > 0.7 else "#f59e0b"

        jobs_html += f"""
        <div style="background:#232336;padding:15px;border-radius:10px;margin:10px 0;
                    border-left:4px solid {score_color};">
            <strong style="color:white;">{job.get('Title', job.get('title', 'Sin título'))}</strong><br>
            <span style="color:#a78bfa;">{job.get('Company', job.get('company', ''))}</span> ·
            <span style="color:#94a3b8;">{job.get('Location', job.get('location', ''))}</span><br>
            <span style="color:{score_color};font-weight:600;">Match: {float(match_score or 0)*100:.0f}%</span>
        </div>"""

    body = f"""
    <p>Se encontraron <strong style="color:#667eea;">{len(jobs)} nuevas ofertas</strong> que podrían interesarte.</p>
    {jobs_html}
    {"<p style='color:#666;'>...y más ofertas en la plataforma</p>" if len(jobs) > 10 else ""}"""

    html = _get_email_template(
        f"🎯 {len(jobs)} nuevas ofertas encontradas",
        body,
        "http://localhost:5000/results",
        "Ver todos los resultados"
    )
    return _send_email(user_email, f"🤖 EmpleoIA: {len(jobs)} nuevas ofertas para vos", html)


@celery.task(name="tasks.notification_tasks.send_weekly_summary")
def send_weekly_summary(stats: dict[str, Any], user_email: str) -> bool:
    """Envía resumen semanal de actividad."""
    body = f"""
    <p>Tu resumen de actividad de esta semana 📊</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:20px 0;">
        <div style="background:#232336;padding:20px;border-radius:10px;text-align:center;">
            <div style="font-size:32px;font-weight:800;color:#667eea;">{stats.get('total_applied', 0)}</div>
            <div style="color:#94a3b8;font-size:14px;">Postulaciones</div>
        </div>
        <div style="background:#232336;padding:20px;border-radius:10px;text-align:center;">
            <div style="font-size:32px;font-weight:800;color:#22c55e;">{stats.get('interviewing', 0)}</div>
            <div style="color:#94a3b8;font-size:14px;">Entrevistas</div>
        </div>
        <div style="background:#232336;padding:20px;border-radius:10px;text-align:center;">
            <div style="font-size:32px;font-weight:800;color:#a78bfa;">{stats.get('jobs_scraped', 0)}</div>
            <div style="color:#94a3b8;font-size:14px;">Ofertas Encontradas</div>
        </div>
        <div style="background:#232336;padding:20px;border-radius:10px;text-align:center;">
            <div style="font-size:32px;font-weight:800;color:#f59e0b;">{stats.get('response_rate', 0)}%</div>
            <div style="color:#94a3b8;font-size:14px;">Tasa de Respuesta</div>
        </div>
    </div>
    <p style="color:#94a3b8;">{stats.get('tip', '¡Seguí adelante! La constancia es clave en la búsqueda laboral.')}</p>"""

    html = _get_email_template("📈 Tu resumen semanal", body, "http://localhost:5000/analytics", "Ver Analytics")
    return _send_email(user_email, "📊 EmpleoIA: Tu resumen semanal de búsqueda laboral", html)


@celery.task(name="tasks.notification_tasks.send_weekly_digests")
def send_weekly_digests() -> dict[str, Any]:
    """Periódica (cada hora): un email por cuenta activa que no apagó el resumen, cuyo último resumen tiene
    7 días y que tiene algo para contar."""
    if not email_configured():
        return {"sent": 0, "reason": "SMTP no configurado"}
    per_user = _for_each_user(_send_weekly_digest)
    return {"sent": sum(r.get("sent", 0) for r in per_user.values()), "users": len(per_user)}


def _claim_minutes() -> int:
    """Minutos tras los que un resumen tomado y sin confirmar se da por perdido (`WEEKLY_DIGEST_CLAIM_MINUTES`)."""
    try:
        return max(5, int(os.getenv("WEEKLY_DIGEST_CLAIM_MINUTES", "60")))
    except ValueError:
        return 60


def _send_weekly_digest() -> dict[str, Any]:
    """Resumen semanal de la cuenta actual."""
    import account_lifecycle
    import accounts
    import job_alerts
    uid = accounts.current_user_id()
    if uid is None:
        # sin login no hay cuenta donde anotar el último envío: se mandaría cada hora
        return {"sent": 0, "reason": "sin cuenta"}
    if account_lifecycle.recover_weekly_digest(uid, datetime.now() - timedelta(minutes=_claim_minutes())):
        logger.warning("Resumen semanal sin confirmar (el worker se cortó): se vuelve a mandar")
    user = accounts.get_user(uid)
    if user is None or not user["weekly_digest"]:
        return {"sent": 0, "reason": "apagado"}
    # sin microsegundos: DATETIME de MySQL no los guarda y confirm_weekly_digest compara por igualdad
    now = datetime.now().replace(microsecond=0)
    since = user["weekly_digest_since"] or now - timedelta(days=WEEKLY_DAYS)
    if now - since < timedelta(days=WEEKLY_DAYS):
        return {"sent": 0, "reason": "todavía no"}
    previous = user["weekly_digest_sent_at"]
    if not account_lifecycle.claim_weekly_digest(uid, previous, now):
        return {"sent": 0, "reason": "otra ejecución lo está mandando"}
    try:
        from db_config import db_manager
        jobs = db_manager.get_all_tracked_jobs()
        # sin resumen previo (cuenta anterior al resumen) solo cuentan las ofertas de la última semana
        offers_since = since if user["weekly_digest_sent_at"] else max(since, now - timedelta(days=WEEKLY_DAYS))
        # hasta `now`, que es donde arranca el próximo resumen: una oferta no sale en dos emails
        new_total, new_offers = job_alerts.seen_since(offers_since, until=now)
    except Exception as e:
        logger.error(f"No se pudo armar el resumen semanal: {type(e).__name__}: {e}")
        account_lifecycle.mark_weekly_digest(uid, previous)
        return {"sent": 0, "error": type(e).__name__}
    data = weekly_digest_data(jobs, new_total, new_offers, now.date())
    if weekly_digest_empty(data):
        account_lifecycle.confirm_weekly_digest(uid, now)
        return {"sent": 0, "reason": "sin novedades"}
    sent = _send_email(_recipient(), "📈 EmpleoIA: tu resumen de la semana", weekly_digest_html(data))
    if sent:
        account_lifecycle.confirm_weekly_digest(uid, now)
    else:
        account_lifecycle.mark_weekly_digest(uid, previous)
    return {"sent": int(bool(sent))}


def _recipient() -> str:
    """Email del usuario actual (su cuenta); sin usuario, NOTIFICATION_EMAIL."""
    import accounts
    user = accounts.get_user(accounts.current_user_id())
    return user["email"] if user else NOTIFICATION_EMAIL


def _telegram_chat() -> str | None:
    """Chat de la cuenta actual; TELEGRAM_CHAT_ID es del dueño de la instancia (primera cuenta o sin cuentas)."""
    import accounts
    uid = accounts.current_user_id()
    if uid is None:
        return os.getenv("TELEGRAM_CHAT_ID") or None
    try:
        import integrations
        own = integrations.telegram_chat_id(uid)
        if own is not None:
            return own or None
        return (os.getenv("TELEGRAM_CHAT_ID") or None) if uid == accounts.first_user_id() else None
    except Exception as e:
        logger.error(f"No se pudo leer el chat de Telegram de la cuenta: {type(e).__name__}")
        return None


def _telegram_allowed() -> bool:
    """La cuenta actual tiene un chat de Telegram donde recibir avisos (sin cuentas, el de la instancia)."""
    import accounts
    return accounts.current_user_id() is None or _telegram_chat() is not None


def accounts_current() -> int | None:
    """Cuenta de la tarea actual (None sin cuentas)."""
    import accounts
    return accounts.current_user_id()




def _for_each_user[T](func: Callable[[], T]) -> dict[int | None, T]:
    """Corre func() una vez por cuenta (o una sola vez sin usuario si todavía no hay cuentas)."""
    import accounts
    results = {}
    for uid in accounts.owner_ids(active_only=True):
        with accounts.as_user(uid):
            results[uid] = func()
    return results


@celery.task(name="tasks.notification_tasks.check_and_send_followup_reminders")
def check_and_send_followup_reminders() -> dict[str, Any]:
    """Periódica: un aviso por usuario (email y/o Telegram) con los seguimientos que vencen hoy."""
    import push
    if not (email_configured() or telegram_configured() or os.getenv("TELEGRAM_BOT_TOKEN") or push.configured()):
        return {"sent": 0, "reason": "Sin canal configurado (SMTP, Telegram o push)"}
    per_user = _for_each_user(_send_followup_reminders)
    if len(per_user) == 1:
        return next(iter(per_user.values()))
    return {"sent": sum(r.get("sent", 0) for r in per_user.values()), "users": per_user}


def _send_followup_reminders() -> dict[str, Any]:
    """Seguimientos vencidos del usuario actual."""
    try:
        from db_config import db_manager
        due = due_followups(db_manager.get_followup_candidates(), date.today())
    except Exception as e:
        logger.error(f"Error fetching applications for reminders: {type(e).__name__}: {e}")
        return {"sent": 0, "error": str(e)}
    if not due:
        return {"sent": 0}

    delivered = []
    if email_configured():
        delivered.append(_send_email(_recipient(), f"⏰ EmpleoIA: {len(due)} seguimientos pendientes",
                                     followup_email_html(due)))
    if _telegram_allowed():
        delivered.append(send_telegram(followup_telegram_text(due)))
    import push
    if push.available(accounts_current()):
        delivered.append(push.send_to_current(f"{len(due)} seguimientos pendientes",
                                              ", ".join(str(j.get("company") or j.get("title") or "") for j in due[:3]),
                                              "/tracker"))
    if not any(delivered):
        return {"sent": 0, "due": len(due), "error": "Ningún canal entregó el aviso"}
    db_manager.mark_reminded([job["id"] for job in due])
    logger.info(f"Follow-up reminder sent for {len(due)} applications")
    return {"sent": len(due)}


# ── Alertas de empleo (búsquedas guardadas) ──────────────────────────────────
def telegram_configured() -> bool:
    """True si hay bot de Telegram y la cuenta actual tiene chat."""
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and _telegram_chat())


def email_configured() -> bool:
    """True si el proveedor de email tiene credenciales (SMTP o SendGrid)."""
    import email_delivery
    return email_delivery.configured()


def send_telegram(text: str) -> bool:
    """Envía un mensaje HTML al chat configurado vía Bot API (en partes si supera el límite)."""
    if not telegram_configured():
        logger.warning("Telegram no configurado: falta TELEGRAM_BOT_TOKEN o el chat de la cuenta")
        return False
    chat_id = _telegram_chat()
    import requests
    try:
        for chunk in _telegram_chunks(text):
            resp = requests.post(
                f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
                json={
                    "chat_id": chat_id, "text": chunk,
                    "parse_mode": "HTML", "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if not resp.ok:
                logger.error(f"Telegram respondió {resp.status_code}")
                return False
        return True
    except Exception as e:
        logger.error(f"Error enviando a Telegram: {type(e).__name__}")
        return False


def notify_alert(search: dict[str, Any], jobs: list[Any]) -> dict[str, Any]:
    """Avisa por cada canal de la búsqueda; devuelve {canal: enviado}."""
    sent = {}
    if "email" in search["channels"]:
        sent["email"] = _send_email(
            _recipient(), f"🔔 EmpleoIA: {len(jobs)} ofertas nuevas ({search['name']})",
            alert_email_html(search, jobs),
        )
    if "telegram" in search["channels"] and _telegram_allowed():
        sent["telegram"] = send_telegram(alert_telegram_text(search, jobs))
    if "push" in search["channels"]:
        import push
        first = jobs[0] if jobs else {}
        title = str(first.get("Title") or first.get("title") or "")
        sent["push"] = push.send_to_current(
            f"{len(jobs)} ofertas nuevas: {search['name']}"[:120],
            title + (f" y {len(jobs) - 1} más" if len(jobs) > 1 else ""), "/alerts")
    return sent


@celery.task(name="tasks.notification_tasks.run_job_alerts")
def run_job_alerts() -> list[dict[str, Any]]:
    """Corre todas las búsquedas guardadas activas (Celery Beat)."""
    import job_alerts
    summary: list[dict[str, Any]] = job_alerts.run_all(notify_alert)
    return summary


@celery.task(name="tasks.notification_tasks.run_job_alert")
def run_job_alert(search_id: int) -> dict[str, Any]:
    """Corre una búsqueda guardada ahora (botón "Buscar ahora")."""
    import accounts
    import job_alerts
    with accounts.as_user(job_alerts.search_owner(search_id)):
        summary: dict[str, Any] = job_alerts.run_search(search_id, notify_alert)
        return summary
