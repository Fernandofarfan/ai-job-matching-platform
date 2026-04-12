"""
notifier.py — Sistema de Notificaciones de EmpleoIA
Interfaz de alto nivel para enviar notificaciones y gestionar preferencias.
"""
import os
import logging
from datetime import datetime, date
from typing import Optional, List

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Manager de notificaciones. Decide si usar Celery (async) o SMTP directo (sync)
    dependiendo de la disponibilidad de Redis/Celery.
    """

    def __init__(self):
        self._use_celery = self._check_celery_available()
        logger.info(f"NotificationManager initialized (celery={self._use_celery})")

    def _check_celery_available(self) -> bool:
        try:
            from celery_app import celery
            celery.control.inspect(timeout=1).active()
            return True
        except Exception:
            return False

    def send_followup_reminder(self, job_data: dict, user_email: str) -> bool:
        """Envía recordatorio de follow-up para una postulación."""
        try:
            if self._use_celery:
                from tasks.notification_tasks import send_followup_reminder
                send_followup_reminder.delay(job_data, user_email)
            else:
                from tasks.notification_tasks import send_followup_reminder
                send_followup_reminder(job_data, user_email)
            return True
        except Exception as e:
            logger.error(f"Error sending follow-up reminder: {e}")
            return False

    def send_new_jobs_digest(self, jobs: list, user_email: str) -> bool:
        """Envía digest de nuevos trabajos encontrados."""
        if not jobs or not user_email:
            return False
        try:
            if self._use_celery:
                from tasks.notification_tasks import send_new_jobs_digest
                send_new_jobs_digest.delay(jobs, user_email)
            else:
                from tasks.notification_tasks import send_new_jobs_digest
                send_new_jobs_digest(jobs, user_email)
            return True
        except Exception as e:
            logger.error(f"Error sending jobs digest: {e}")
            return False

    def send_weekly_summary(self, stats: dict, user_email: str) -> bool:
        """Envía resumen semanal de actividad."""
        try:
            if self._use_celery:
                from tasks.notification_tasks import send_weekly_summary
                send_weekly_summary.delay(stats, user_email)
            else:
                from tasks.notification_tasks import send_weekly_summary
                send_weekly_summary(stats, user_email)
            return True
        except Exception as e:
            logger.error(f"Error sending weekly summary: {e}")
            return False

    def check_upcoming_followups(self, applications: list) -> list:
        """
        Verifica cuáles postulaciones tienen follow-up para hoy o vencido.
        Retorna lista de applications que necesitan follow-up.
        """
        today = date.today()
        pending = []

        for app in applications:
            follow_up = app.get("follow_up")
            if not follow_up:
                continue
            if isinstance(follow_up, str):
                try:
                    follow_up = datetime.fromisoformat(follow_up).date()
                except ValueError:
                    continue
            elif isinstance(follow_up, datetime):
                follow_up = follow_up.date()

            if isinstance(follow_up, date) and follow_up <= today:
                pending.append(app)

        return pending

    def get_notification_config(self) -> dict:
        """Retorna la configuración de notificaciones desde .env."""
        return {
            "smtp_configured": bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD")),
            "notification_email": os.getenv("NOTIFICATION_EMAIL", ""),
            "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "celery_available": self._use_celery,
        }

    def test_email_config(self) -> dict:
        """Envía un email de prueba para verificar la configuración SMTP."""
        from tasks.notification_tasks import _send_email, _get_email_template
        email = os.getenv("NOTIFICATION_EMAIL") or os.getenv("SMTP_USER")
        if not email:
            return {"success": False, "message": "NOTIFICATION_EMAIL no configurado en .env"}

        body = """
        <p>¡Tu configuración de email está funcionando correctamente! 🎉</p>
        <p>EmpleoIA puede enviarte:</p>
        <ul>
            <li>📬 Recordatorios de follow-up</li>
            <li>🎯 Digest de nuevas ofertas</li>
            <li>📊 Resúmenes semanales de actividad</li>
        </ul>"""
        html = _get_email_template("✅ Configuración de Email Verificada", body)

        success = _send_email(email, "🤖 EmpleoIA: Test de notificaciones", html)
        return {
            "success": success,
            "message": f"Email de prueba {'enviado' if success else 'fallido'} a {email}"
        }


# Instancia global
notifier = NotificationManager()
