"""Envío de emails por SMTP o SendGrid, con reintentos y lista de direcciones que rebotan.

- `EMAIL_PROVIDER=smtp` (por defecto; sirve para SES SMTP, Gmail, etc.) o `sendgrid` (`SENDGRID_API_KEY`).
- Fallas temporales (SMTP 4xx o conexión caída, HTTP 429/5xx) se reintentan `EMAIL_MAX_ATTEMPTS` veces
  con espera creciente. Un 5xx de SMTP sobre el destinatario no se reintenta y suprime la dirección.
- Rebotes y denuncias de spam que informa SendGrid (`POST /webhooks/sendgrid`, firmado) también la suprimen.
  A una dirección suprimida no se le manda más. Se guarda solo el SHA-256 del email, no el email.
"""
import base64
import hashlib
import logging
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import accounts
from accounts import Base

logger = logging.getLogger(__name__)

SENDGRID_URL = 'https://api.sendgrid.com/v3/mail/send'
# Eventos de SendGrid que suprimen la dirección; `dropped` solo si es por rebote, spam o baja previa
SUPPRESS_EVENTS = {'bounce', 'spamreport'}
SUPPRESS_DROP_REASONS = ('bounced address', 'spam reporting address', 'unsubscribed address', 'invalid')
WEBHOOK_MAX_AGE_SECONDS = 600


class EmailSuppression(Base):
    """Dirección a la que no se manda más (rebote permanente o denuncia de spam)."""
    __tablename__ = 'email_suppressions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class TemporaryError(Exception):
    """Falla que puede andar si se reintenta."""


class PermanentError(Exception):
    """Falla que no se arregla reintentando; `bounce` si la dirección no existe."""

    def __init__(self, message, bounce=False):
        super().__init__(message)
        self.bounce = bounce


def provider() -> str:
    """'smtp' o 'sendgrid'."""
    return 'sendgrid' if os.getenv('EMAIL_PROVIDER', 'smtp').strip().lower() == 'sendgrid' else 'smtp'


def sender() -> str:
    """Remitente: `EMAIL_FROM` o, por SMTP, el usuario SMTP."""
    return os.getenv('EMAIL_FROM') or os.getenv('SMTP_USER') or ''


def configured() -> bool:
    """True si el proveedor elegido tiene credenciales y remitente."""
    if provider() == 'sendgrid':
        return bool(os.getenv('SENDGRID_API_KEY') and sender())
    return bool(os.getenv('SMTP_USER') and os.getenv('SMTP_PASSWORD'))


def _hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()


def is_suppressed(email: str) -> bool:
    """True si la dirección rebotó o denunció spam. Si la base no responde, no frena el envío."""
    try:
        with accounts._sessions()() as session:
            return session.scalar(select(EmailSuppression.id).where(
                EmailSuppression.email_hash == _hash(email))) is not None
    except Exception as e:
        logger.warning(f'No se pudo revisar la lista de rebotes: {type(e).__name__}')
        return False


def suppress(email: str, reason: str) -> bool:
    """Agrega la dirección a la lista de rebotes (si ya estaba, no hace nada); False si la base falló."""
    try:
        with accounts._sessions()() as session:
            session.add(EmailSuppression(email_hash=_hash(email), reason=reason[:50]))
            session.commit()
        logger.warning(f'Email suprimido ({reason})')
    except IntegrityError:
        pass
    except Exception as e:
        logger.error(f'No se pudo suprimir el email: {type(e).__name__}')
        return False
    return True


class SuppressionError(Exception):
    """No se pudo guardar un rebote: el webhook responde error y SendGrid lo reintenta."""


def unsuppress(email: str) -> bool:
    """Saca la dirección de la lista (p. ej. si la cuenta la arregló); True si estaba."""
    with accounts._sessions()() as session:
        row = session.scalars(select(EmailSuppression).where(EmailSuppression.email_hash == _hash(email))).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def _send_smtp(to, subject, html):
    user, password = os.getenv('SMTP_USER', ''), os.getenv('SMTP_PASSWORD', '')
    msg = MIMEMultipart('alternative')
    msg['Subject'], msg['From'], msg['To'] = subject, f'EmpleoIA <{sender()}>', to
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    try:
        with smtplib.SMTP(os.getenv('SMTP_HOST', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', '587')),
                          timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(sender(), to, msg.as_string())
    except smtplib.SMTPRecipientsRefused as e:
        code = next(iter(e.recipients.values()))[0] if e.recipients else 550
        if 400 <= code < 500:
            raise TemporaryError(f'SMTP {code}') from e
        raise PermanentError(f'SMTP {code}', bounce=True) from e
    except smtplib.SMTPAuthenticationError as e:
        if 400 <= e.smtp_code < 500:
            raise TemporaryError(f'SMTP {e.smtp_code}: login') from e
        raise PermanentError(f'SMTP {e.smtp_code}: login rechazado') from e
    except smtplib.SMTPResponseException as e:
        if 400 <= e.smtp_code < 500:
            raise TemporaryError(f'SMTP {e.smtp_code}') from e
        raise PermanentError(f'SMTP {e.smtp_code}') from e
    except (smtplib.SMTPException, OSError) as e:
        raise TemporaryError(type(e).__name__) from e


def _send_sendgrid(to, subject, html):
    import requests
    try:
        resp = requests.post(SENDGRID_URL, timeout=15, headers={
            'Authorization': f"Bearer {os.getenv('SENDGRID_API_KEY')}"}, json={
            'personalizations': [{'to': [{'email': to}]}],
            'from': {'email': sender(), 'name': 'EmpleoIA'},
            'subject': subject, 'content': [{'type': 'text/html', 'value': html}],
        })
    except requests.RequestException as e:
        raise TemporaryError(type(e).__name__) from e
    if resp.status_code in (200, 202):
        return
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TemporaryError(f'SendGrid {resp.status_code}')
    raise PermanentError(f'SendGrid {resp.status_code}')


def _attempts() -> int:
    try:
        return max(1, int(os.getenv('EMAIL_MAX_ATTEMPTS', '3')))
    except ValueError:
        return 3


def _wait(attempt: int):
    """Espera antes del reintento `attempt` (1 s, 2 s, 4 s... con `EMAIL_RETRY_SECONDS=1`)."""
    time.sleep(float(os.getenv('EMAIL_RETRY_SECONDS', '1')) * 2 ** (attempt - 1))


def send(to: str, subject: str, html: str) -> bool:
    """Manda un email HTML; True si el proveedor lo aceptó. Nunca levanta."""
    if not configured():
        logger.warning(f'Email sin configurar para {provider()}')
        return False
    if not to:
        return False
    if is_suppressed(to):
        logger.info('Email no enviado: la dirección rebotó o denunció spam')
        return False
    deliver = _send_sendgrid if provider() == 'sendgrid' else _send_smtp
    attempts = _attempts()
    for attempt in range(1, attempts + 1):
        try:
            deliver(to, subject, html)
            logger.info(f'Email enviado por {provider()}: {subject}')
            return True
        except PermanentError as e:
            logger.error(f'Email rechazado por {provider()}: {e}')
            if e.bounce:
                suppress(to, 'smtp_bounce')
            return False
        except TemporaryError as e:
            logger.warning(f'Email falló ({e}), intento {attempt} de {attempts}')
            if attempt < attempts:
                _wait(attempt)
    logger.error(f'Email no enviado tras {attempts} intentos')
    return False


def verify_sendgrid_signature(payload: bytes, signature: str, timestamp: str, now=None) -> bool:
    """Firma ECDSA del Event Webhook de SendGrid con `SENDGRID_WEBHOOK_PUBLIC_KEY` y timestamp reciente."""
    key = os.getenv('SENDGRID_WEBHOOK_PUBLIC_KEY', '')
    if not (key and signature and timestamp):
        return False
    try:
        if abs((now or time.time()) - int(timestamp)) > WEBHOOK_MAX_AGE_SECONDS:
            return False
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        public_key = serialization.load_der_public_key(base64.b64decode(key))
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            return False
        public_key.verify(base64.b64decode(signature), timestamp.encode() + payload, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def handle_sendgrid_events(events) -> int:
    """Suprime las direcciones con rebote, denuncia de spam o `dropped` por esas causas; devuelve cuántas.
    Levanta SuppressionError si alguna no se pudo guardar."""
    count = failed = 0
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict) or not isinstance(event.get('email'), str):
            continue
        kind = event.get('event')
        reason = str(event.get('reason') or '').lower()
        if kind == 'bounce' and event.get('type') == 'blocked':
            continue  # bloqueo temporal del servidor de destino
        if kind in SUPPRESS_EVENTS or (kind == 'dropped' and reason.startswith(SUPPRESS_DROP_REASONS)):
            if suppress(event['email'], f'sendgrid_{kind}'):
                count += 1
            else:
                failed += 1
    if failed:
        raise SuppressionError(f'{failed} rebotes sin guardar')
    return count
