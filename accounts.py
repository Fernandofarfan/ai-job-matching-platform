"""Cuentas de usuario (email + contraseña) y usuario actual del pedido o la tarea.

Las capas de datos (db_config, profile_store, job_alerts) filtran por `current_user_id()`;
Flask y FastAPI lo fijan desde la sesión, y las tareas de Celery con `as_user()`."""
import contextvars
import logging
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

Base = declarative_base()
MIN_PASSWORD = 10
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_current: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('current_user_id', default=None)
_session_factory = None


class User(Base):  # type: ignore[misc,valid-type]
    """Cuenta con email único y hash de contraseña."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class AccountError(ValueError):
    """Registro inválido; el mensaje se muestra al usuario."""


def configure(session_factory):
    """Fábrica de sesiones (tests) o None para usar la de models.py."""
    global _session_factory
    _session_factory = session_factory


def _sessions():
    """Fábrica de sesiones configurada (o la de models.py)."""
    if _session_factory is not None:
        return _session_factory
    from models import SessionLocal
    return SessionLocal


def current_user_id() -> Optional[int]:
    """Id de la cuenta del pedido o tarea actual (None sin login)."""
    return _current.get()


def set_current_user(user_id: Optional[int]):
    """Fija el usuario del pedido actual; devuelve el token para `reset_current_user`."""
    return _current.set(user_id)


def reset_current_user(token):
    """Restaura el usuario anterior con el token de `set_current_user`."""
    _current.reset(token)


@contextmanager
def as_user(user_id: Optional[int]):
    """Corre un bloque (p. ej. una tarea de Celery) con los datos de ese usuario."""
    token = _current.set(user_id)
    try:
        yield
    finally:
        _current.reset(token)


def thread(target, args=(), **kwargs) -> threading.Thread:
    """Thread que hereda el usuario actual (los threads no copian los contextvars solos)."""
    ctx = contextvars.copy_context()
    return threading.Thread(target=ctx.run, args=(target, *args), **kwargs)


def signup_open() -> bool:
    """Registro abierto con ALLOW_SIGNUP=true, o siempre mientras no haya ninguna cuenta."""
    return _signup_allowed() or count_users() == 0


def _signup_allowed() -> bool:
    """ALLOW_SIGNUP=true habilita cuentas después de la primera."""
    return os.getenv('ALLOW_SIGNUP', 'false').strip().lower() == 'true'


def count_users() -> int:
    """Cantidad de cuentas registradas."""
    with _sessions()() as session:
        return _count(session)


def _count(session) -> int:
    """Cantidad de cuentas dentro de una sesión abierta."""
    from sqlalchemy import func
    return session.execute(select(func.count(User.id))).scalar_one()


def user_ids() -> list:
    """Ids de todas las cuentas, de la más vieja a la más nueva."""
    with _sessions()() as session:
        return list(session.execute(select(User.id).order_by(User.id)).scalars())


def first_user_id() -> Optional[int]:
    """Id de la primera cuenta (dueña de Telegram, Gmail y la extensión)."""
    ids = user_ids()
    return ids[0] if ids else None


def owner_ids() -> list:
    """Dueños por los que corren las tareas periódicas; None cubre los datos sin cuenta (sin login)."""
    ids = user_ids()
    if not ids or os.getenv('LOGIN_REQUIRED', 'true').strip().lower() == 'false':
        ids.append(None)
    return ids


def get_user(user_id) -> Optional[dict]:
    """Cuenta por id como dict, o None."""
    if not user_id:
        return None
    with _sessions()() as session:
        user = session.get(User, user_id)
        return {'id': user.id, 'email': user.email, 'password_hash': user.password_hash} if user else None


def normalize_email(email: str) -> str:
    """Email sin espacios y en minúsculas."""
    return (email or '').strip().lower()


def register(email: str, password: str) -> int:
    """Crea la cuenta y devuelve su id; la primera cuenta se queda con los datos previos (user_id NULL)."""
    email = normalize_email(email)
    if not EMAIL_RE.match(email) or len(email) > 255:
        raise AccountError('Email inválido')
    if len(password or '') < MIN_PASSWORD:
        raise AccountError(f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres')
    admin = normalize_email(os.getenv('ADMIN_EMAIL', ''))
    with _sessions()() as session:
        first = _count(session) == 0
        if first and admin and email != admin:
            raise AccountError('La primera cuenta tiene que usar el email de ADMIN_EMAIL')
        if first and not admin and os.getenv('K_SERVICE'):
            raise AccountError('Definí ADMIN_EMAIL antes de crear la primera cuenta')
        if not first and not _signup_allowed():
            raise AccountError('El registro de cuentas nuevas está cerrado')
        user = User(email=email, password_hash=generate_password_hash(password))
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AccountError('Ya existe una cuenta con ese email') from None
        user_id = user.id
    if first:
        claim_orphans(user_id)
    return user_id


def authenticate(email: str, password: str) -> Optional[int]:
    """Id del usuario si email y contraseña coinciden; None si no."""
    with _sessions()() as session:
        user = session.execute(select(User).where(User.email == normalize_email(email))).scalar_one_or_none()
        if user is None:
            check_password_hash(generate_password_hash('x'), password or '')  # mismo tiempo que con cuenta
            return None
        return user.id if check_password_hash(user.password_hash, password or '') else None


OWNED_TABLES = ('applications', 'user_profiles', 'saved_searches', 'seen_jobs',
                'networking_exclusions', 'connection_requests', 'processed_files')


def claim_orphans(user_id: int):
    """Asigna al usuario las filas creadas antes del multiusuario (user_id NULL)."""
    from sqlalchemy import inspect, text
    with _sessions()() as session:
        inspector = inspect(session.get_bind())
        for table in OWNED_TABLES:
            if inspector.has_table(table) and 'user_id' in {c['name'] for c in inspector.get_columns(table)}:
                session.execute(text(f'UPDATE {table} SET user_id = :uid WHERE user_id IS NULL'), {'uid': user_id})
        session.commit()
