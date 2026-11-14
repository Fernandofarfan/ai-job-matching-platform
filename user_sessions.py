"""Sesiones abiertas por cuenta: cada login guarda una fila para poder listarlas y cerrarlas desde Mi cuenta."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, delete, or_, select, update

import accounts

logger = logging.getLogger(__name__)

LIFETIME = timedelta(days=31)  # igual que PERMANENT_SESSION_LIFETIME de Flask
TOUCH_EVERY = timedelta(minutes=5)


class UserSession(accounts.Base):  # type: ignore[misc,valid-type]
    """Una sesión; la cookie lleva el id aleatorio y acá solo se guarda su hash."""

    __tablename__ = 'user_sessions'
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    sid_hash = Column(String(64), nullable=False, unique=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    last_seen_at = Column(DateTime, default=datetime.now)
    revoked_at = Column(DateTime, nullable=True)


def _hash(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def create(user_id: int, ip: Optional[str] = None, user_agent: Optional[str] = None) -> str:
    """Registra una sesión nueva y devuelve el id que va en la cookie."""
    sid = secrets.token_urlsafe(32)
    with accounts._sessions()() as session:
        session.add(UserSession(user_id=user_id, sid_hash=_hash(sid), ip=(ip or '')[:45] or None,
                                user_agent=(user_agent or '')[:255] or None))
        session.commit()
    return sid


def is_active(user_id: int, sid: Optional[str]) -> bool:
    """True si la sesión `sid` es de la cuenta, no se cerró y no venció; actualiza su última actividad."""
    if not sid:
        return False
    now = datetime.now()
    with accounts._sessions()() as session:
        row = session.execute(select(UserSession).where(UserSession.sid_hash == _hash(sid))).scalar_one_or_none()
        if row is None or row.user_id != user_id or row.revoked_at is not None:
            return False
        if (row.last_seen_at or row.created_at) < now - LIFETIME:
            return False
        if row.last_seen_at is None or row.last_seen_at < now - TOUCH_EVERY:
            row.last_seen_at = now
            session.commit()
        return True


def active(user_id: Optional[int], current_sid: Optional[str] = None) -> list:
    """Sesiones abiertas de la cuenta, la más reciente primero; `current` marca la del navegador actual."""
    if not user_id:
        return []
    current = _hash(current_sid) if current_sid else None
    with accounts._sessions()() as session:
        rows = session.execute(select(UserSession).where(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
            UserSession.last_seen_at >= datetime.now() - LIFETIME,
        ).order_by(UserSession.last_seen_at.desc(), UserSession.id.desc())).scalars()
        return [{'id': r.id, 'ip': r.ip, 'user_agent': r.user_agent, 'created_at': r.created_at,
                 'last_seen_at': r.last_seen_at, 'current': r.sid_hash == current} for r in rows]


def revoke(user_id: int, session_id: int) -> bool:
    """Cierra una sesión de la cuenta (False si no existe o es de otra cuenta)."""
    with accounts._sessions()() as session:
        result = session.execute(update(UserSession).where(
            UserSession.id == session_id, UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now()))
        session.commit()
        return bool(result.rowcount)


def revoke_sid(sid: Optional[str]):
    """Cierra la sesión de esa cookie (logout)."""
    if not sid:
        return
    with accounts._sessions()() as session:
        session.execute(update(UserSession).where(UserSession.sid_hash == _hash(sid), UserSession.revoked_at.is_(None))
                        .values(revoked_at=datetime.now()))
        session.commit()


def revoke_all(user_id: int, except_sid: Optional[str] = None) -> int:
    """Cierra todas las sesiones de la cuenta salvo `except_sid`; devuelve cuántas cerró."""
    query = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_sid:
        query = query.where(UserSession.sid_hash != _hash(except_sid))
    with accounts._sessions()() as session:
        result = session.execute(query.values(revoked_at=datetime.now()))
        session.commit()
        return result.rowcount or 0


def purge() -> int:
    """Borra las sesiones cerradas o vencidas hace más de LIFETIME."""
    limit = datetime.now() - LIFETIME
    with accounts._sessions()() as session:
        result = session.execute(delete(UserSession).where(or_(
            UserSession.revoked_at < limit, UserSession.last_seen_at < limit - LIFETIME)))
        session.commit()
        return result.rowcount or 0
