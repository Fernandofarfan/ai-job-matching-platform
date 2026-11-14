"""Textos de las notificaciones: emails y mensajes de Telegram de seguimientos, alertas y resumen semanal.

Funciones puras (sin envío ni base): las tareas de Celery de tasks/notification_tasks.py las arman y las mandan.
"""
import os
from datetime import date, datetime, timedelta


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
