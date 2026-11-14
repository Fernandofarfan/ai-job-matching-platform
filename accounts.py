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
    email_verified_at = Column(DateTime, nullable=True)


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
        if user is None:
            return None
        return {'id': user.id, 'email': user.email, 'password_hash': user.password_hash,
                'email_verified': user.email_verified_at is not None}


def normalize_email(email: str) -> str:
    """Email sin espacios y en minúsculas."""
    return (email or '').strip().lower()


def register(email: str, password: str) -> int:
    """Crea la cuenta y devuelve su id; la primera cuenta se queda con los datos previos (user_id NULL)."""
    email = normalize_email(email)
    if not EMAIL_RE.match(email) or len(email) > 255:
        raise AccountError('Email inválido')
    _check_password(password)
    admin = normalize_email(os.getenv('ADMIN_EMAIL', ''))
    with _sessions()() as session:
        first = _count(session) == 0
        if first and admin and email != admin:
            raise AccountError('La primera cuenta tiene que usar el email de ADMIN_EMAIL')
        if first and not admin and os.getenv('K_SERVICE'):
            raise AccountError('Definí ADMIN_EMAIL antes de crear la primera cuenta')
        if not first and not _signup_allowed():
            raise AccountError('El registro de cuentas nuevas está cerrado')
        # la primera cuenta es la del administrador: no espera el email de verificación
        user = User(email=email, password_hash=generate_password_hash(password),
                    email_verified_at=datetime.now() if first else None)
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


OWNED_TABLES = ('applications', 'application_status_history', 'user_profiles', 'saved_searches', 'seen_jobs',
                'networking_exclusions', 'connection_requests', 'processed_files')


RESULTS_ROOT = 'results'
GENERATED_KINDS = ('cover_letters', 'resumes')


def results_dir() -> str:
    """Carpeta de CSV de la cuenta actual (results/u<id>); sin cuenta, la raíz heredada."""
    uid = current_user_id()
    path = RESULTS_ROOT if uid is None else os.path.join(RESULTS_ROOT, f'u{uid}')
    os.makedirs(path, exist_ok=True)
    return path


def user_subdir(base: str) -> str:
    """`base/u<id>` para la cuenta actual, o `base` sin cuenta."""
    uid = current_user_id()
    return base if uid is None else os.path.join(base, f'u{uid}')


def _move_files(src_dir: str, dst_dir: str):
    """Mueve los archivos (no carpetas) de src_dir a dst_dir."""
    import shutil
    if not os.path.isdir(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        if os.path.isfile(src) and not name.startswith('.'):
            shutil.move(src, os.path.join(dst_dir, name))


def claim_legacy_files(user_id: int):
    """Pasa a la primera cuenta los CSV de results/ y los documentos generados antes del multiusuario."""
    import logging
    try:
        _move_files(RESULTS_ROOT, os.path.join(RESULTS_ROOT, f'u{user_id}'))
        base = os.getenv('GENERATED_DIR', 'temp')
        for kind in GENERATED_KINDS:
            _move_files(os.path.join(base, kind), os.path.join(base, f'u{user_id}', kind))
    except OSError as e:
        logging.getLogger(__name__).error(f'No se pudieron mover los archivos previos: {e}')


def adopt_legacy_files():
    """Instancias que ya tenían cuentas antes de separar archivos: los sueltos pasan a la primera cuenta."""
    uid = first_user_id()
    if uid is not None:
        claim_legacy_files(uid)


def claim_orphans(user_id: int):
    """Asigna al usuario las filas creadas antes del multiusuario (user_id NULL)."""
    from sqlalchemy import inspect, text
    with _sessions()() as session:
        inspector = inspect(session.get_bind())
        for table in OWNED_TABLES:
            if inspector.has_table(table) and 'user_id' in {c['name'] for c in inspector.get_columns(table)}:
                session.execute(text(f'UPDATE {table} SET user_id = :uid WHERE user_id IS NULL'), {'uid': user_id})
        session.commit()
    claim_legacy_files(user_id)


def _check_password(password: str):
    """Valida el largo mínimo de una contraseña nueva."""
    if len(password or '') < MIN_PASSWORD:
        raise AccountError(f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres')


def find_user_id(email: str) -> Optional[int]:
    """Id de la cuenta con ese email, o None."""
    with _sessions()() as session:
        return session.execute(select(User.id).where(User.email == normalize_email(email))).scalar_one_or_none()


def set_password(user_id: int, password: str, expected_hash: Optional[str] = None):
    """Reemplaza la contraseña (invalida las sesiones abiertas y los enlaces de recuperación).

    Con `expected_hash`, solo si la contraseña sigue siendo esa: dos usos simultáneos del mismo enlace no ganan ambos.
    """
    from sqlalchemy import update
    _check_password(password)
    query = update(User).where(User.id == user_id).values(password_hash=generate_password_hash(password))
    if expected_hash is not None:
        query = query.where(User.password_hash == expected_hash)
    with _sessions()() as session:
        changed = session.execute(query).rowcount
        session.commit()
    if not changed:
        raise AccountError('La cuenta no existe o la contraseña ya se cambió')


def change_password(user_id: int, current: str, new: str):
    """Cambia la contraseña si `current` es la actual."""
    user = get_user(user_id)
    if user is None or not check_password_hash(user['password_hash'], current or ''):
        raise AccountError('La contraseña actual no es correcta')
    set_password(user_id, new)


def check_password(user_id: int, password: str) -> bool:
    """True si `password` es la contraseña de la cuenta."""
    user = get_user(user_id)
    return user is not None and check_password_hash(user['password_hash'], password or '')


def mark_verified(user_id: int):
    """Marca el email de la cuenta como verificado."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None and user.email_verified_at is None:
            user.email_verified_at = datetime.now()
            session.commit()


def delete_account(user_id: int):
    """Borra la cuenta, todas sus filas y sus carpetas de resultados (los CVs los borra quien llama)."""
    import shutil
    from sqlalchemy import delete, inspect, text
    with _sessions()() as session:
        inspector = inspect(session.get_bind())
        for table in OWNED_TABLES:
            if inspector.has_table(table) and 'user_id' in {c['name'] for c in inspector.get_columns(table)}:
                session.execute(text(f'DELETE FROM {table} WHERE user_id = :uid'), {'uid': user_id})
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    shutil.rmtree(os.path.join(RESULTS_ROOT, f'u{user_id}'), ignore_errors=True)
    shutil.rmtree(os.path.join(os.getenv('GENERATED_DIR', 'temp'), f'u{user_id}'), ignore_errors=True)
