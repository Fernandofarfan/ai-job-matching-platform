"""Registro de eventos de seguridad por cuenta (logins, contraseña, integraciones) y aviso de login nuevo."""
import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, delete, select

import accounts

logger = logging.getLogger(__name__)

LABELS = {
    'register': 'Cuenta creada',
    'login': 'Inicio de sesión',
    'login_google': 'Inicio de sesión con Google',
    'login_failed': 'Contraseña incorrecta',
    'password_changed': 'Contraseña cambiada',
    'password_reset': 'Contraseña recuperada por email',
    'email_verified': 'Email confirmado',
    'telegram_changed': 'Telegram configurado',
    'extension_token_created': 'Token de la extensión generado',
    'extension_token_revoked': 'Token de la extensión revocado',
    'gmail_connected': 'Gmail conectado',
    'gmail_disconnected': 'Gmail desconectado',
    'data_exported': 'Datos exportados',
    'two_factor_enabled': 'Verificación en dos pasos activada',
    'two_factor_disabled': 'Verificación en dos pasos desactivada',
    'two_factor_failed': 'Código de verificación incorrecto',
    'recovery_code_used': 'Código de recuperación usado',
    'recovery_codes_regenerated': 'Códigos de recuperación nuevos',
    'session_revoked': 'Sesión cerrada desde Mi cuenta',
    'sessions_revoked': 'Otras sesiones cerradas',
}
LOGIN_KINDS = ('login', 'login_google')


class SecurityEvent(accounts.Base):  # type: ignore[misc,valid-type]
    """Un evento; `device` es un hash del user agent para reconocer dispositivos sin compararlo entero."""

    __tablename__ = 'security_events'
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    device = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)


def device_id(user_agent: Optional[str]) -> str:
    """Huella corta del navegador (hash del user agent)."""
    return hashlib.sha256((user_agent or '').encode()).hexdigest()[:16]


def record(user_id: Optional[int], kind: str, ip: Optional[str] = None, user_agent: Optional[str] = None) -> bool:
    """Guarda el evento; un fallo de la base se registra en el log y no corta el pedido."""
    if not user_id or kind not in LABELS:
        return False
    try:
        with accounts._sessions()() as session:
            session.add(SecurityEvent(user_id=user_id, kind=kind, ip=(ip or '')[:45] or None,
                                      user_agent=(user_agent or '')[:255] or None, device=device_id(user_agent)))
            session.commit()
        return True
    except Exception as e:
        logger.error(f'No se pudo registrar el evento {kind} de la cuenta {user_id}: {e}')
        return False


def is_new_device(user_id: int, user_agent: Optional[str], days: int = 180) -> bool:
    """True si la cuenta ya entró antes pero nunca desde este navegador en los últimos `days` días."""
    since = datetime.now() - timedelta(days=days)
    with accounts._sessions()() as session:
        logins = select(SecurityEvent.device).where(SecurityEvent.user_id == user_id,
                                                    SecurityEvent.kind.in_(LOGIN_KINDS),
                                                    SecurityEvent.created_at >= since)
        devices = set(session.execute(logins).scalars())
    return bool(devices) and device_id(user_agent) not in devices


def recent(user_id: Optional[int], limit: int = 20) -> list:
    """Últimos eventos de la cuenta, del más nuevo al más viejo."""
    if not user_id:
        return []
    try:
        with accounts._sessions()() as session:
            rows = session.execute(select(SecurityEvent).where(SecurityEvent.user_id == user_id)
                                   .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc())
                                   .limit(limit)).scalars()
            return [{'kind': r.kind, 'label': LABELS.get(r.kind, r.kind), 'ip': r.ip,
                     'user_agent': r.user_agent, 'created_at': r.created_at} for r in rows]
    except Exception as e:
        logger.error(f'No se pudieron leer los eventos de la cuenta {user_id}: {e}')
        return []


def purge(days: Optional[int] = None) -> int:
    """Borra los eventos más viejos que SECURITY_EVENTS_DAYS (180 por defecto)."""
    days = days if days is not None else int(os.getenv('SECURITY_EVENTS_DAYS', '180') or 180)
    if days <= 0:
        return 0
    with accounts._sessions()() as session:
        result = session.execute(delete(SecurityEvent).where(
            SecurityEvent.created_at < datetime.now() - timedelta(days=days)))
        session.commit()
        return result.rowcount or 0


def login_alerts_enabled() -> bool:
    """LOGIN_ALERTS=false apaga el aviso por email de login desde un navegador nuevo."""
    return os.getenv('LOGIN_ALERTS', 'true').strip().lower() != 'false'
