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


FOLLOWUP_DAYS = int(os.getenv("FOLLOWUP_DAYS", "7"))
WEEKLY_DAYS = 7


def weekly_digest_data(jobs: list, new_total: int, new_offers: list, today: date) -> dict:
    """Qué entra en el resumen semanal: ofertas nuevas, postulaciones sin respuesta y próximos pasos."""
    waiting, upcoming = [], []
    horizon = today + timedelta(days=WEEKLY_DAYS)
    for job in jobs:
        applied = _as_date(job.get("applied_date"))
        if job.get("status") == "applied" and applied and applied <= today - timedelta(days=FOLLOWUP_DAYS):
            waiting.append({**job, "days": (today - applied).days})
        for kind in ("follow_up", "deadline"):
            when = _as_date(job.get(kind))
            if when and today <= when <= horizon:
                upcoming.append({**job, "kind": kind, "when": when})
    waiting.sort(key=lambda j: -j["days"])
    upcoming.sort(key=lambda j: j["when"])
    return {"new_total": new_total, "new_offers": new_offers, "waiting": waiting, "upcoming": upcoming,
            "interviewing": sum(1 for j in jobs if j.get("status") == "interviewing")}


def weekly_digest_empty(data: dict) -> bool:
    """Sin nada para contar no se manda el email (las entrevistas en curso solas no son novedad)."""
    return not (data["new_total"] or data["waiting"] or data["upcoming"])


def weekly_digest_html(data: dict) -> str:
    """Email del resumen semanal (texto escapado; los enlaces solo si son http/https)."""
    from html import escape

    def card(job, detail):
        title = escape(str(job.get("title") or ""))
        url = str(job.get("url") or job.get("job_link") or "")
        head = f'<a href="{escape(url)}" style="color:#e2e8f0;">{title}</a>' if url.startswith(("http://", "https://")) else title
        return ('<div style="background:#232336;padding:12px;border-radius:10px;margin:8px 0;">'
                f'<strong>{head}</strong> · <span style="color:#a78bfa;">{escape(str(job.get("company") or ""))}</span>'
                f'<br><span style="color:#94a3b8;">{detail}</span></div>')

    stats = [(data["new_total"], "ofertas nuevas", "#a78bfa"), (len(data["waiting"]), "sin respuesta", "#f59e0b"),
             (data["interviewing"], "en entrevistas", "#22c55e")]
    body = ('<div style="display:flex;gap:12px;margin:16px 0;">' + "".join(
        '<div style="flex:1;background:#232336;padding:16px;border-radius:10px;text-align:center;">'
        f'<div style="font-size:28px;font-weight:800;color:{color};">{value}</div>'
        f'<div style="color:#94a3b8;font-size:13px;">{label}</div></div>' for value, label, color in stats) + "</div>")
    if data["upcoming"]:
        labels = {"follow_up": "Seguimiento", "deadline": "Cierra"}
        body += "<h3>Próximos pasos</h3>" + "".join(
            card(j, f'{labels[j["kind"]]} el {j["when"].isoformat()}') for j in data["upcoming"][:10])
    if data["waiting"]:
        body += "<h3>Postulaciones sin respuesta</h3>" + "".join(
            card(j, f'Postulaste hace {j["days"]} días: buen momento para escribir al reclutador')
            for j in data["waiting"][:10])
    if data["new_offers"]:
        body += "<h3>Ofertas nuevas de tus alertas</h3>" + "".join(
            card(j, escape(str(j.get("source") or ""))) for j in data["new_offers"])
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    body += (f'<p style="color:#94a3b8;font-size:12px;">Para dejar de recibir este resumen, apagalo en '
             f'<a href="{base_url}/account" style="color:#94a3b8;">Mi cuenta</a>.</p>')
    return _get_email_template("📈 Tu semana en EmpleoIA", body, f"{base_url}/tracker", "Abrir el tracker")


@celery.task(name="tasks.notification_tasks.send_weekly_digests")
def send_weekly_digests():
    """Periódica (cada hora): un email por cuenta activa que no apagó el resumen, cuyo último resumen tiene
    7 días y que tiene algo para contar."""
    if not email_configured():
        return {"sent": 0, "reason": "SMTP no configurado"}
    per_user = _for_each_user(_send_weekly_digest)
    return {"sent": sum(r.get("sent", 0) for r in per_user.values()), "users": len(per_user)}


def _send_weekly_digest():
    """Resumen semanal de la cuenta actual."""
    import accounts
    import job_alerts
    uid = accounts.current_user_id()
    if uid is None:
        # sin login no hay cuenta donde anotar el último envío: se mandaría cada hora
        return {"sent": 0, "reason": "sin cuenta"}
    user = accounts.get_user(uid)
    if user is None or not user["weekly_digest"]:
        return {"sent": 0, "reason": "apagado"}
    now = datetime.now()
    since = user["weekly_digest_since"] or now - timedelta(days=WEEKLY_DAYS)
    if now - since < timedelta(days=WEEKLY_DAYS):
        return {"sent": 0, "reason": "todavía no"}
    try:
        from db_config import db_manager
        jobs = db_manager.get_all_tracked_jobs()
        new_total, new_offers = job_alerts.seen_since(since)
    except Exception as e:
        logger.error(f"No se pudo armar el resumen semanal: {type(e).__name__}: {e}")
        return {"sent": 0, "error": type(e).__name__}
    data = weekly_digest_data(jobs, new_total, new_offers, now.date())
    if weekly_digest_empty(data):
        accounts.mark_weekly_digest(uid, now)
        return {"sent": 0, "reason": "sin novedades"}
    sent = _send_email(_recipient(), "📈 EmpleoIA: tu resumen de la semana", weekly_digest_html(data))
    if sent:
        accounts.mark_weekly_digest(uid, now)
    return {"sent": int(bool(sent))}


def _as_date(value):
    """date de un date/datetime/str ISO; None si no hay."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def due_followups(jobs: list, today: date, default_days: int = FOLLOWUP_DAYS) -> list:
    """Postulaciones a recordar hoy: con fecha de seguimiento vencida o, sin fecha, `default_days`
    después de postular (0 lo desactiva). Una vez avisada, no se repite hasta una fecha nueva."""
    due = []
    for job in jobs:
        follow_up = _as_date(job.get("follow_up"))
        if follow_up is None and default_days > 0 and job.get("status") == "applied":
            applied = _as_date(job.get("applied_date"))
            follow_up = applied + timedelta(days=default_days) if applied else None
        reminded = _as_date(job.get("last_reminder_at"))
        if follow_up and follow_up <= today and (reminded is None or reminded < follow_up):
            due.append({**job, "follow_up": follow_up})
    return due


def followup_telegram_text(jobs: list) -> str:
    """Resumen de seguimientos para Telegram."""
    from html import escape
    lines = [f"⏰ <b>{len(jobs)} postulaciones para hacer seguimiento</b>"]
    for job in jobs:
        title, company = escape(str(job.get("title") or "")), escape(str(job.get("company") or ""))
        link = escape(str(job.get("job_link") or ""))
        head = f'<a href="{link}">{title}</a>' if link else title
        lines.append(f"• {head}\n  {company} · desde {job['follow_up'].isoformat()}")
    return "\n".join(lines)


def followup_email_html(jobs: list) -> str:
    """Resumen de seguimientos por email."""
    from html import escape
    items = "".join(
        '<div style="background:#232336;padding:12px;border-radius:10px;margin:8px 0;">'
        f'<strong>{escape(str(j.get("title") or ""))}</strong> · '
        f'<span style="color:#a78bfa;">{escape(str(j.get("company") or ""))}</span><br>'
        f'<span style="color:#94a3b8;">Seguimiento desde {j["follow_up"].isoformat()}</span></div>'
        for j in jobs
    )
    body = ("<p>Es buen momento para escribirle al reclutador, conectar en LinkedIn o actualizar el estado.</p>"
            + items)
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    return _get_email_template(f"⏰ {len(jobs)} seguimientos pendientes", body, f"{base_url}/tracker",
                               "Abrir el tracker")


def _recipient() -> str:
    """Email del usuario actual (su cuenta); sin usuario, NOTIFICATION_EMAIL."""
    import accounts
    user = accounts.get_user(accounts.current_user_id())
    return user["email"] if user else NOTIFICATION_EMAIL


def _telegram_chat():
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


def accounts_current():
    """Cuenta de la tarea actual (None sin cuentas)."""
    import accounts
    return accounts.current_user_id()


def _for_each_user(func):
    """Corre func() una vez por cuenta (o una sola vez sin usuario si todavía no hay cuentas)."""
    import accounts
    results = {}
    for uid in accounts.owner_ids(active_only=True):
        with accounts.as_user(uid):
            results[uid] = func()
    return results


@celery.task(name="tasks.notification_tasks.check_and_send_followup_reminders")
def check_and_send_followup_reminders():
    """Periódica: un aviso por usuario (email y/o Telegram) con los seguimientos que vencen hoy."""
    import push
    if not (email_configured() or telegram_configured() or os.getenv("TELEGRAM_BOT_TOKEN") or push.configured()):
        return {"sent": 0, "reason": "Sin canal configurado (SMTP, Telegram o push)"}
    per_user = _for_each_user(_send_followup_reminders)
    if len(per_user) == 1:
        return next(iter(per_user.values()))
    return {"sent": sum(r.get("sent", 0) for r in per_user.values()), "users": per_user}


def _send_followup_reminders():
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
    """True si el SMTP tiene credenciales y destinatario."""
    return bool(SMTP_USER and SMTP_PASSWORD and NOTIFICATION_EMAIL)


TELEGRAM_MAX_CHARS = 4096


def _telegram_chunks(text: str, size: int = TELEGRAM_MAX_CHARS) -> list:
    """Parte el texto en mensajes de hasta `size` caracteres, cortando entre ofertas (líneas '• ')."""
    chunks: list[str] = []
    current = ""
    for block in text.split("\n• "):
        block = block if not current and not chunks else "• " + block
        candidate = f"{current}\n{block}" if current else block
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block[:size]
    if current:
        chunks.append(current)
    return chunks


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


def _job_line(job: dict) -> tuple:
    """(título, empresa, ubicación, url, match) escapados para HTML."""
    from html import escape
    get = lambda k: escape(str(job.get(k.capitalize()) or job.get(k.upper()) or job.get(k) or ""))  # noqa: E731
    match = job.get("match_percent")
    return get("title"), get("company"), get("location"), get("url"), match


def alert_telegram_text(search: dict, jobs: list, limit: int = 15) -> str:
    """Mensaje de Telegram con las ofertas nuevas de una búsqueda (máx. `limit`)."""
    from html import escape
    lines = [f"🔔 <b>{len(jobs)} ofertas nuevas</b> · {escape(search['name'])}"]
    for job in jobs[:limit]:
        title, company, location, url, match = _job_line(job)
        head = f'<a href="{url}">{title}</a>' if url else title
        details = [company, location] + ([f"{match:.0f}%"] if match is not None else [])
        lines.append(f"• {head}\n  " + " · ".join(d for d in details if d))
    return "\n".join(lines)


def alert_email_html(search: dict, jobs: list, limit: int = 15) -> str:
    """Email con las ofertas nuevas de una búsqueda (máx. `limit`)."""
    from html import escape
    items = ""
    for job in jobs[:limit]:
        title, company, location, url, match = _job_line(job)
        link = f'<a href="{url}" style="color:white;">{title}</a>' if url else title
        details = [f'<span style="color:#a78bfa;">{company}</span>' if company else "",
                   f'<span style="color:#94a3b8;">{location}</span>' if location else "",
                   f'<span style="color:#22c55e;">{match:.0f}%</span>' if match is not None else ""]
        items += (
            '<div style="background:#232336;padding:12px;border-radius:10px;margin:8px 0;">'
            f'<strong>{link}</strong><br>{" · ".join(d for d in details if d)}</div>'
        )
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    return _get_email_template(
        f"🔔 {len(jobs)} ofertas nuevas: {escape(search['name'])}", items,
        f"{base_url}/alerts", "Ver mis alertas",
    )


def notify_alert(search: dict, jobs: list) -> dict:
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
def run_job_alerts():
    """Corre todas las búsquedas guardadas activas (Celery Beat)."""
    import job_alerts
    return job_alerts.run_all(notify_alert)


@celery.task(name="tasks.notification_tasks.run_job_alert")
def run_job_alert(search_id: int):
    """Corre una búsqueda guardada ahora (botón "Buscar ahora")."""
    import accounts
    import job_alerts
    with accounts.as_user(job_alerts.search_owner(search_id)):
        return job_alerts.run_search(search_id, notify_alert)
