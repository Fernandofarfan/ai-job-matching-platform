"""
tasks/notification_tasks.py — Tareas de notificaciones vía Celery + Email
Envía alertas de follow-up, nuevos trabajos relevantes y resúmenes semanales.
"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date, timedelta
from typing import Optional

from celery_app import celery

logger = logging.getLogger(__name__)

# ── Configuración SMTP ────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", SMTP_USER)


def _send_email(to: str, subject: str, html_body: str) -> bool:
    """Envía un email HTML vía SMTP."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado. Configurá SMTP_USER y SMTP_PASSWORD en .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"EmpleoIA <{SMTP_USER}>"
        msg["To"] = to

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to, msg.as_string())

        logger.info(f"Email enviado a {to}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Error enviando email: {e}")
        return False


def _get_email_template(title: str, body: str, cta_url: str = "", cta_text: str = "") -> str:
    """Template HTML para emails de EmpleoIA."""
    cta_section = ""
    if cta_url and cta_text:
        cta_section = f"""
        <div style="text-align:center;margin:30px 0;">
            <a href="{cta_url}" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;
               padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:16px;">
                {cta_text}
            </a>
        </div>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:#0f0f1a;margin:0;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:#1a1a2e;border-radius:16px;overflow:hidden;
                    border:1px solid rgba(102,126,234,0.3);">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:28px;">🤖 EmpleoIA</h1>
                <p style="color:rgba(255,255,255,0.8);margin:5px 0 0;">Tu asistente de búsqueda laboral</p>
            </div>
            <!-- Content -->
            <div style="padding:30px;color:#e0e0e0;">
                <h2 style="color:#667eea;margin-top:0;">{title}</h2>
                {body}
                {cta_section}
            </div>
            <!-- Footer -->
            <div style="background:#0f0f1a;padding:20px;text-align:center;
                        border-top:1px solid rgba(102,126,234,0.2);">
                <p style="color:#666;font-size:12px;margin:0;">
                    EmpleoIA · Hecho con ❤️ en Argentina<br>
                    <a href="http://localhost:5000" style="color:#667eea;">Abrir plataforma</a>
                </p>
            </div>
        </div>
    </body>
    </html>"""


@celery.task(name="tasks.notification_tasks.send_followup_reminder")
def send_followup_reminder(job_data: dict, user_email: str):
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
def send_new_jobs_digest(jobs: list, user_email: str):
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
def send_weekly_summary(stats: dict, user_email: str):
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


@celery.task(name="tasks.notification_tasks.check_and_send_followup_reminders")
def check_and_send_followup_reminders():
    """Periódica: verifica follow-ups pendientes y envía recordatorios."""
    if not NOTIFICATION_EMAIL:
        return {"sent": 0, "reason": "NOTIFICATION_EMAIL no configurado"}

    try:
        from db_config import db_manager
        jobs = db_manager.get_applications({"status": "applied"})
    except Exception as e:
        logger.error(f"Error fetching applications for reminders: {e}")
        return {"sent": 0, "error": str(e)}

    today = date.today()
    sent = 0

    for job in jobs:
        follow_up = job.get("follow_up")
        if follow_up and isinstance(follow_up, (date, datetime)):
            follow_up_date = follow_up.date() if isinstance(follow_up, datetime) else follow_up
            if follow_up_date <= today:
                try:
                    send_followup_reminder.delay(
                        {
                            "title": job.get("title"),
                            "company": job.get("company"),
                            "applied_date": str(job.get("applied_date", "")),
                        },
                        NOTIFICATION_EMAIL
                    )
                    sent += 1
                except Exception as e:
                    logger.error(f"Error queuing reminder for job {job.get('id')}: {e}")

    logger.info(f"Queued {sent} follow-up reminders")
    return {"sent": sent, "checked": len(jobs)}
