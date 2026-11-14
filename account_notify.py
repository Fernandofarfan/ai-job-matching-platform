"""Emails y eventos de seguridad de las cuentas, sin depender del framework web.

Las rutas pasan la IP, el navegador y la URL base de su pedido.
"""
import logging
import os
from typing import Callable, Optional
from urllib.parse import urlsplit

from markupsafe import escape

import accounts
import security_events

logger = logging.getLogger(__name__)
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def public_base(host: str, url_root: str) -> Optional[str]:
    """Base de los enlaces de los emails: PUBLIC_BASE_URL (obligatoria en Cloud Run, evita usar el Host del pedido)."""
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if base:
        return base
    # sin PUBLIC_BASE_URL solo se confía en el Host si es local: si no, un Host falso robaría el enlace
    if urlsplit('//' + (host or '')).hostname not in LOCAL_HOSTS:
        logger.error('Definí PUBLIC_BASE_URL para mandar enlaces por email')
        return None
    return url_root.rstrip('/')


def deliver(to: str, subject: str, body: str, link: str, cta: str) -> bool:
    """Manda el email con el enlace por SMTP."""
    from tasks.notification_tasks import _get_email_template, _send_email
    return _send_email(to, subject, _get_email_template(subject, body, link, cta))


def send_verification(user: dict, link: Optional[str]) -> bool:
    """Email con el enlace para confirmar la cuenta."""
    if not link:
        return False
    return deliver(user['email'], 'Confirmá tu email en EmpleoIA',
                                  '<p>Entrá al enlace para confirmar tu cuenta. Vence en 3 días.</p>',
                                  link, 'Confirmar email')


def send_reset(user: dict, link: Optional[str]) -> bool:
    """Email con el enlace para elegir una contraseña nueva."""
    if not link:
        return False
    return deliver(user['email'], 'Recuperar tu contraseña de EmpleoIA',
                                  '<p>Entrá al enlace para elegir una contraseña nueva. Vence en 1 hora. '
                                  'Si no lo pediste, ignorá este email.</p>', link, 'Elegir contraseña')


def audit(user_id, kind: str, ip: Optional[str], agent: Optional[str]) -> bool:
    """Registra el evento con la IP y el navegador del pedido."""
    return security_events.record(user_id, kind, ip, agent)


def audit_login(user: dict, kind: str, ip: Optional[str], agent: Optional[str],
                account_link: Callable[[], Optional[str]]) -> None:
    """Registra el login y, si es un navegador nuevo para la cuenta, avisa por email en segundo plano."""
    try:
        new_device = security_events.login_alerts_enabled() and security_events.is_new_device(user['id'], agent)
    except Exception as e:
        logger.error(f'No se pudo comprobar el dispositivo del login: {e}')
        new_device = False
    audit(user['id'], kind, ip, agent)
    link = account_link() if new_device else None
    if link:
        body = ('<p>Se inició sesión en tu cuenta desde un navegador nuevo:</p>'
                f'<p>{escape(agent or "navegador desconocido")}<br>IP {escape(ip or "")}</p>'
                '<p>Si no fuiste vos, cambiá la contraseña ya.</p>')
        accounts.thread(deliver, (user['email'], 'Nuevo inicio de sesión en EmpleoIA', body, link,
                                  'Revisar mi cuenta'), daemon=True).start()
