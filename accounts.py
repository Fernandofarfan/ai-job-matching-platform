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
from typing import Any, Callable, Iterable, Iterator, Optional, cast

from sqlalchemy import Boolean, CursorResult, DateTime, Integer, Result, String, false, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarativa de los modelos de este módulo."""


MIN_PASSWORD = 10
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_current: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('current_user_id', default=None)
_session_factory = None


class User(Base):
    """Cuenta con email único y hash de contraseña."""
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # permiso para mandar el CV y las ofertas a Gemini; sin él las funciones de IA no se llaman
    ai_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # cuándo apagó el resumen semanal por email (None = lo recibe)
    weekly_digest_off_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    weekly_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Resumen tomado y todavía sin confirmar: si el worker muere antes de mandarlo, se vuelve al anterior
    weekly_digest_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    weekly_digest_claimed_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # último login o uso de la web (las sesiones se borran a los 62 días; esto queda) y aviso de borrado por inactividad
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    inactivity_notice_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    inactivity_notice_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                         server_default=false())


class AccountError(ValueError):
    """Registro inválido; el mensaje se muestra al usuario."""


def configure(session_factory: sessionmaker[Session]) -> None:
    """Fábrica de sesiones (tests) o None para usar la de models.py."""
    global _session_factory
    _session_factory = session_factory


def rowcount(result: Result[Any]) -> int:
    """Filas que tocó un UPDATE/DELETE (session.execute lo tipa como Result, pero es un CursorResult)."""
    return int(cast(CursorResult[Any], result).rowcount)


def _sessions() -> sessionmaker[Session]:
    """Fábrica de sesiones configurada (o la de models.py)."""
    if _session_factory is not None:
        return _session_factory
    from models import SessionLocal
    return SessionLocal


def current_user_id() -> Optional[int]:
    """Id de la cuenta del pedido o tarea actual (None sin login)."""
    return _current.get()


def set_current_user(user_id: Optional[int]) -> contextvars.Token[Optional[int]]:
    """Fija el usuario del pedido actual; devuelve el token para `reset_current_user`."""
    return _current.set(user_id)


def reset_current_user(token: contextvars.Token[Optional[int]]) -> None:
    """Restaura el usuario anterior con el token de `set_current_user`."""
    _current.reset(token)


@contextmanager
def as_user(user_id: Optional[int]) -> Iterator[None]:
    """Corre un bloque (p. ej. una tarea de Celery) con los datos de ese usuario."""
    token = _current.set(user_id)
    try:
        yield
    finally:
        _current.reset(token)


def thread(target: Callable[..., Any], args: Iterable[Any] = (), **kwargs: Any) -> threading.Thread:
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


def _count(session: Session) -> int:
    """Cantidad de cuentas dentro de una sesión abierta."""
    from sqlalchemy import func
    return int(session.execute(select(func.count(User.id))).scalar_one())


def user_ids() -> list[int]:
    """Ids de todas las cuentas, de la más vieja a la más nueva."""
    with _sessions()() as session:
        return list(session.execute(select(User.id).order_by(User.id)).scalars())


def first_user_id() -> Optional[int]:
    """Id de la primera cuenta (dueña de Telegram, Gmail y la extensión)."""
    ids = user_ids()
    return ids[0] if ids else None


def owner_ids(active_only: bool = False) -> list[Optional[int]]:
    """Dueños por los que corren las tareas periódicas; None cubre los datos sin cuenta (sin login).

    `active_only` deja afuera las cuentas bloqueadas (avisos); la retención de datos sí las recorre."""
    ids: list[Optional[int]] = list(user_ids())
    if active_only and ids:
        blocked = blocked_ids()
        ids = [i for i in ids if i not in blocked]
    if not ids or os.getenv('LOGIN_REQUIRED', 'true').strip().lower() == 'false':
        ids.append(None)
    return ids


def blocked_ids() -> set[int]:
    """Cuentas bloqueadas desde el panel de administración (no reciben avisos)."""
    with _sessions()() as session:
        return set(session.execute(select(User.id).where(User.disabled_at.isnot(None))).scalars())


def get_user(user_id: Optional[int]) -> Optional[dict[str, Any]]:
    """Cuenta por id como dict, o None."""
    if not user_id:
        return None
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        return {'id': user.id, 'email': user.email, 'password_hash': user.password_hash,
                'email_verified': user.email_verified_at is not None, 'disabled': user.disabled_at is not None,
                'terms_accepted': user.terms_accepted_at is not None, 'ai_consent': user.ai_consent_at is not None,
                'weekly_digest': user.weekly_digest_off_at is None,
                'weekly_digest_since': user.weekly_digest_sent_at or user.created_at,
                'weekly_digest_sent_at': user.weekly_digest_sent_at}


def is_admin(user_id: Optional[int]) -> bool:
    """Administra la instancia la cuenta de ADMIN_EMAIL o, sin esa variable, la primera cuenta."""
    user = get_user(user_id)
    if user is None or user['disabled']:
        return False
    admin = normalize_email(os.getenv('ADMIN_EMAIL', ''))
    return bool(user['email'] == admin if admin else user['id'] == first_user_id())


def list_users() -> list[dict[str, Any]]:
    """Todas las cuentas para el panel de administración, de la más vieja a la más nueva."""
    with _sessions()() as session:
        rows = session.execute(select(User).order_by(User.id)).scalars()
        return [{'id': u.id, 'email': u.email, 'created_at': u.created_at,
                 'email_verified': u.email_verified_at is not None, 'disabled': u.disabled_at is not None}
                for u in rows]


def set_disabled(user_id: int, disabled: bool) -> bool:
    """Bloquea (cierra todas sus sesiones) o desbloquea la cuenta; False si no existe."""
    from sqlalchemy import update
    with _sessions()() as session:
        changed = rowcount(session.execute(update(User).where(User.id == user_id).values(
            disabled_at=datetime.now() if disabled else None)))
        session.commit()
    if changed and disabled:
        import user_sessions
        user_sessions.revoke_all(user_id)
    return bool(changed)


def normalize_email(email: str) -> str:
    """Email sin espacios y en minúsculas."""
    return (email or '').strip().lower()


def register(email: str, password: str, terms_accepted: bool = False) -> int:
    """Crea la cuenta y devuelve su id; la primera cuenta se queda con los datos previos (user_id NULL).

    terms_accepted guarda la aceptación de los Términos en el mismo commit que crea la cuenta.
    """
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
                    email_verified_at=datetime.now() if first else None,
                    terms_accepted_at=datetime.now() if terms_accepted else None)
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AccountError('Ya existe una cuenta con ese email') from None
        user_id = user.id
    if first:
        claim_orphans(user_id)
    return int(user_id)


def authenticate(email: str, password: str) -> Optional[int]:
    """Id del usuario si email y contraseña coinciden; None si no."""
    with _sessions()() as session:
        user = session.execute(select(User).where(User.email == normalize_email(email))).scalar_one_or_none()
        if user is None:
            check_password_hash(generate_password_hash('x'), password or '')  # mismo tiempo que con cuenta
            return None
        return user.id if check_password_hash(user.password_hash, password or '') else None


OWNED_TABLES = ('applications', 'application_status_history', 'user_profiles', 'saved_searches', 'seen_jobs',
                'networking_exclusions', 'connection_requests', 'processed_files', 'user_integrations',
                'push_subscriptions', 'security_events', 'user_sessions', 'user_totp', 'job_feedback', 'passkeys')


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


def _move_files(src_dir: str, dst_dir: str) -> None:
    """Mueve los archivos (no carpetas) de src_dir a dst_dir."""
    import shutil
    if not os.path.isdir(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        if os.path.isfile(src) and not name.startswith('.'):
            shutil.move(src, os.path.join(dst_dir, name))


def claim_legacy_files(user_id: int) -> None:
    """Pasa a la primera cuenta los CSV de results/ y los documentos generados antes del multiusuario."""
    import logging
    try:
        _move_files(RESULTS_ROOT, os.path.join(RESULTS_ROOT, f'u{user_id}'))
        base = os.getenv('GENERATED_DIR', 'temp')
        for kind in GENERATED_KINDS:
            _move_files(os.path.join(base, kind), os.path.join(base, f'u{user_id}', kind))
    except OSError as e:
        logging.getLogger(__name__).error(f'No se pudieron mover los archivos previos: {e}')


def adopt_legacy_files() -> None:
    """Instancias que ya tenían cuentas antes de separar archivos: los sueltos pasan a la primera cuenta."""
    uid = first_user_id()
    if uid is not None:
        claim_legacy_files(uid)


def _owned_tables(inspector: Any) -> list[str]:
    """Tablas de OWNED_TABLES con columna user_id; se inspeccionan antes de escribir, porque en
    SQLite la inspección comparte conexión y descartaría lo pendiente de la transacción."""
    return [t for t in OWNED_TABLES
            if inspector.has_table(t) and 'user_id' in {c['name'] for c in inspector.get_columns(t)}]


def claim_orphans(user_id: int) -> None:
    """Asigna al usuario las filas creadas antes del multiusuario (user_id NULL)."""
    from sqlalchemy import inspect, text
    with _sessions()() as session:
        for table in _owned_tables(inspect(session.get_bind())):
            session.execute(text(f'UPDATE {table} SET user_id = :uid WHERE user_id IS NULL'), {'uid': user_id})
        session.commit()
    claim_legacy_files(user_id)


def _check_password(password: str) -> None:
    """Valida el largo mínimo de una contraseña nueva."""
    if len(password or '') < MIN_PASSWORD:
        raise AccountError(f'La contraseña debe tener al menos {MIN_PASSWORD} caracteres')


def find_user_id(email: str) -> Optional[int]:
    """Id de la cuenta con ese email, o None."""
    with _sessions()() as session:
        user_id: Optional[int] = session.execute(select(User.id).where(User.email == normalize_email(email))).scalar_one_or_none()
        return user_id


def set_password(user_id: int, password: str, expected_hash: Optional[str] = None) -> None:
    """Reemplaza la contraseña (invalida las sesiones abiertas y los enlaces de recuperación).

    Con `expected_hash`, solo si la contraseña sigue siendo esa: dos usos simultáneos del mismo enlace no ganan ambos.
    """
    from sqlalchemy import update
    _check_password(password)
    query = update(User).where(User.id == user_id).values(password_hash=generate_password_hash(password))
    if expected_hash is not None:
        query = query.where(User.password_hash == expected_hash)
    with _sessions()() as session:
        changed = rowcount(session.execute(query))
        session.commit()
    if not changed:
        raise AccountError('La cuenta no existe o la contraseña ya se cambió')
    import user_sessions
    user_sessions.revoke_all(user_id)


def change_password(user_id: int, current: str, new: str) -> None:
    """Cambia la contraseña si `current` es la actual."""
    user = get_user(user_id)
    if user is None or not check_password_hash(user['password_hash'], current or ''):
        raise AccountError('La contraseña actual no es correcta')
    set_password(user_id, new)


def check_password(user_id: int, password: str) -> bool:
    """True si `password` es la contraseña de la cuenta."""
    user = get_user(user_id)
    return user is not None and check_password_hash(user['password_hash'], password or '')


def mark_verified(user_id: int) -> None:
    """Marca el email de la cuenta como verificado."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None and user.email_verified_at is None:
            user.email_verified_at = datetime.now()
            session.commit()


def accept_terms(user_id: int) -> None:
    """Guarda cuándo la cuenta aceptó los Términos y la Política de privacidad."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None and user.terms_accepted_at is None:
            user.terms_accepted_at = datetime.now()
            session.commit()


def set_ai_consent(user_id: int, granted: bool) -> None:
    """Da o quita el permiso para mandar los datos de la cuenta a la IA."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.ai_consent_at = datetime.now() if granted else None
            session.commit()


def set_weekly_digest(user_id: int, enabled: bool) -> None:
    """Prende o apaga el resumen semanal por email de la cuenta."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.weekly_digest_off_at = None if enabled else datetime.now()
            session.commit()


def claim_weekly_digest(user_id: int, previous: Optional[datetime], when: datetime) -> bool:
    """Toma el resumen de la cuenta: anota `when` solo si el último envío sigue siendo `previous`.
    Si dos ejecuciones se pisan, solo una gana y manda el email."""
    last = User.weekly_digest_sent_at
    with _sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, last.is_(None) if previous is None
                                                    else last == previous).values(
            weekly_digest_sent_at=when, weekly_digest_claimed_at=when, weekly_digest_claimed_from=previous))
        session.commit()
        return bool(getattr(result, 'rowcount', 0))


def mark_weekly_digest(user_id: int, when: Optional[datetime]) -> None:
    """Anota hasta cuándo cubrió el último resumen semanal de la cuenta (el próximo arranca ahí)."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.weekly_digest_sent_at = when
            user.weekly_digest_claimed_at = user.weekly_digest_claimed_from = None
            session.commit()


def confirm_weekly_digest(user_id: int, when: datetime) -> None:
    """El resumen tomado en `when` ya salió: deja de poder recuperarse."""
    with _sessions()() as session:
        session.execute(update(User).where(User.id == user_id, User.weekly_digest_claimed_at == when).values(
            weekly_digest_claimed_at=None, weekly_digest_claimed_from=None))
        session.commit()


def recover_weekly_digest(user_id: int, older_than: datetime) -> bool:
    """Un resumen tomado antes de `older_than` y nunca confirmado (el worker murió) vuelve a estar pendiente."""
    with _sessions()() as session:
        user = session.get(User, user_id)
        claimed = user.weekly_digest_claimed_at if user is not None else None
        if claimed is None or claimed >= older_than:
            return False
        result = session.execute(update(User).where(User.id == user_id, User.weekly_digest_claimed_at == claimed)
                                 .values(weekly_digest_sent_at=User.weekly_digest_claimed_from,
                                         weekly_digest_claimed_at=None, weekly_digest_claimed_from=None))
        session.commit()
        return bool(getattr(result, 'rowcount', 0))


def ai_consent_missing() -> bool:
    """True si la cuenta actual no dio permiso para usar la IA. Sin cuenta (modo local) no hace falta.

    Si la base no responde, se asume que falta: ante la duda no se mandan datos a la IA.
    """
    user_id = current_user_id()
    if user_id is None:
        return False
    try:
        with _sessions()() as session:
            user = session.get(User, user_id)
            return user is None or user.ai_consent_at is None
    except SQLAlchemyError as e:
        logger.error(f'No se pudo leer el permiso de IA de la cuenta {user_id}: {e}')
        return True


def mark_active(user_id: int, session: Optional[Session] = None) -> None:
    """Anota que la cuenta usó la web y anula el aviso de borrado por inactividad."""
    query = update(User).where(User.id == user_id).values(last_active_at=datetime.now(), inactivity_notice_at=None,
                                                   inactivity_notice_sent=False)
    if session is not None:
        session.execute(query)
        return
    with _sessions()() as own:
        own.execute(query)
        own.commit()


def inactive_accounts(since: datetime) -> list[dict[str, Any]]:
    """Cuentas sin actividad desde `since` (las nunca usadas cuentan desde el alta), con el estado del aviso."""
    last = func.coalesce(User.last_active_at, User.created_at)
    with _sessions()() as session:
        rows = session.execute(select(User.id, User.email, User.inactivity_notice_at, User.inactivity_notice_sent)
                               .where(last < since).order_by(User.id))
        return [{'id': uid, 'email': email, 'notice_at': notice, 'notice_sent': bool(sent)}
                for uid, email, notice, sent in rows]


def set_inactivity_notice(user_id: int, when: datetime, previous: Optional[datetime] = None) -> bool:
    """Reserva el aviso de borrado (todavía sin enviar); False si la cuenta volvió a entrar u otro worker lo tomó.

    `previous` retoma una reserva que quedó sin enviar (el worker se cortó antes de mandar el email).
    """
    pending = (User.inactivity_notice_at.is_(None) if previous is None else
               (User.inactivity_notice_at == previous) & User.inactivity_notice_sent.is_(False))
    with _sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, pending)
                                 .values(inactivity_notice_at=when, inactivity_notice_sent=False))
        session.commit()
        return bool(rowcount(result))


def confirm_inactivity_notice(user_id: int, when: datetime) -> bool:
    """Marca como enviado el aviso reservado en `when`; desde ahí corre el plazo para borrar."""
    with _sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, User.inactivity_notice_at == when)
                                 .values(inactivity_notice_sent=True))
        session.commit()
        return bool(rowcount(result))


def clear_inactivity_notice(user_id: int, when: datetime) -> None:
    """Deshace el aviso reservado en `when` (el email no salió): se vuelve a intentar en la próxima corrida."""
    with _sessions()() as session:
        session.execute(update(User).where(User.id == user_id, User.inactivity_notice_at == when,
                                           User.inactivity_notice_sent.is_(False))
                        .values(inactivity_notice_at=None))
        session.commit()


def still_noticed(user_id: int, notice_at: datetime) -> bool:
    """True si la cuenta sigue con el mismo aviso (no entró desde entonces: entrar lo anula)."""
    with _sessions()() as session:
        return session.execute(select(User.id).where(User.id == user_id, User.inactivity_notice_at == notice_at,
                                                     User.inactivity_notice_sent.is_(True))).first() is not None


def delete_account(user_id: int) -> None:
    """Borra la cuenta, todas sus filas y sus carpetas de resultados (los CVs los borra quien llama)."""
    import shutil
    from sqlalchemy import delete, inspect, text
    with _sessions()() as session:
        for table in _owned_tables(inspect(session.get_bind())):
            session.execute(text(f'DELETE FROM {table} WHERE user_id = :uid'), {'uid': user_id})
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    shutil.rmtree(os.path.join(RESULTS_ROOT, f'u{user_id}'), ignore_errors=True)
    shutil.rmtree(os.path.join(os.getenv('GENERATED_DIR', 'temp'), f'u{user_id}'), ignore_errors=True)
