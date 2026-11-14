"""Perfiles de CV por rol en MySQL (tabla user_profiles), con fallback a profiles/user_profiles.json.

Con CV_ENCRYPTION_KEY cada perfil (incluido el texto del CV en `raw_text`) se guarda cifrado como
{"_enc": <token Fernet>}, tanto en MySQL como en el JSON de respaldo.
"""
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from cryptography.fernet import InvalidToken
from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    delete,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator

import accounts
import cv_storage

T = TypeVar('T')
Profiles = dict[str, dict[str, Any]]

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarativa de los modelos de este módulo."""


JSON_PATH = os.path.join('profiles', 'user_profiles.json')
# Roles borrados mientras MySQL no respondía; se borran en MySQL al volver
DELETED_KEY = '_deleted'
# Momento exacto de la escritura: el mtime del archivo tiene resolución de milisegundos
WRITTEN_KEY = '_written_at'
_RETRY_SECONDS = 60
ENC_KEY = '_enc'

_session_factory: Callable[[], Session] | None = None
_last_failure = 0.0


def _is_sealed(data: Any) -> bool:
    return isinstance(data, dict) and set(data) == {ENC_KEY}


def _seal(data: Any) -> Any:
    """Perfil cifrado si hay CV_ENCRYPTION_KEY; si no, tal cual."""
    fernet = cv_storage.get_fernet()
    if fernet is None or not isinstance(data, dict) or _is_sealed(data):
        return data
    return {ENC_KEY: fernet.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()}


def _unseal(data: Any) -> Any:
    """Perfil descifrado; los guardados en texto plano se devuelven igual."""
    if not _is_sealed(data):
        return data
    fernet = cv_storage.get_fernet()
    if fernet is None:
        raise RuntimeError('Los perfiles están cifrados y falta CV_ENCRYPTION_KEY')
    try:
        return json.loads(fernet.decrypt(data[ENC_KEY].encode()))
    except InvalidToken:
        raise RuntimeError('No se pudo descifrar el perfil: CV_ENCRYPTION_KEY no es la clave con que se cifró') from None


class SealedJSON(TypeDecorator[Any]):
    """Columna JSON que cifra/descifra el perfil al escribir/leer (el tipo en MySQL sigue siendo JSON)."""
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return _seal(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return _unseal(value)


class UserProfile(Base):
    """Un perfil (CV parseado) por tipo de rol."""
    __tablename__ = 'user_profiles'

    __table_args__ = (UniqueConstraint('user_id', 'role_type', name='uq_user_profiles_user_role_type'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    role_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[Any] = mapped_column(SealedJSON, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


def configure(session_factory: Callable[[], Session] | None) -> None:
    """Usa la fábrica de sesiones dada (tests) o None para volver a la detección automática."""
    global _session_factory, _last_failure
    _session_factory = session_factory
    _last_failure = 0.0


def _mark_failure(error: Exception) -> None:
    """Pasa al JSON y reintenta MySQL dentro de _RETRY_SECONDS."""
    global _session_factory, _last_failure
    _session_factory = None
    _last_failure = time.time()
    logger.warning(f"MySQL no disponible para perfiles ({error}); se usa {JSON_PATH}")


def _sessions() -> Callable[[], Session] | None:
    """Devuelve la fábrica de sesiones de MySQL, o None si se usa el JSON."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    if os.getenv('PROFILE_STORAGE', 'mysql') != 'mysql' or time.time() - _last_failure < _RETRY_SECONDS:
        return None
    try:
        from models import SessionLocal, engine
        UserProfile.metadata.create_all(bind=engine, tables=[UserProfile.__table__], checkfirst=True)  # type: ignore[list-item]
        _session_factory = SessionLocal
        _import_legacy_json()
    except Exception as e:
        _mark_failure(e)
    return _session_factory


def _run[T](db_op: Callable[[Session], T], json_op: Callable[[], T]) -> T:
    """Ejecuta db_op(session) en MySQL; si no hay MySQL o falla, json_op() sobre el JSON."""
    sessions = _sessions()
    if sessions is not None:
        try:
            with sessions() as session:
                return db_op(session)
        except SQLAlchemyError as e:
            _mark_failure(e)
    return json_op()


def _json_path(user_id: int | None = None) -> str:
    """JSON de respaldo del usuario (el de JSON_PATH es el de antes del multiusuario)."""
    return JSON_PATH if user_id is None else JSON_PATH.replace('.json', f'.u{int(user_id)}.json')


def _current_json() -> str:
    return _json_path(accounts.current_user_id())


def _read_json_raw(path: str | None = None) -> dict[str, Any]:
    """Contenido completo del JSON (perfiles y lista de borrados)."""
    path = path or _current_json()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data: dict[str, Any] = json.load(f)
    return data


def _read_json(path: str | None = None) -> Profiles:
    return {k: _unseal(v) for k, v in _read_json_raw(path).items() if isinstance(v, dict)}


def _write_json(profiles: Profiles, deleted: set[str], path: str | None = None) -> None:
    path = path or _current_json()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {role: _seal(profile) for role, profile in profiles.items()}
    if deleted:
        data[DELETED_KEY] = sorted(deleted)
    data[WRITTEN_KEY] = time.time()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _json_deleted(path: str | None = None) -> set[str]:
    """Roles borrados mientras MySQL no respondía."""
    deleted = _read_json_raw(path).get(DELETED_KEY, [])
    return set(deleted) if isinstance(deleted, list) else set()


def _json_files() -> list[tuple[str, int | None]]:
    """(ruta, user_id) de los JSON de respaldo; el viejo (sin usuario) va a la primera cuenta."""
    import glob
    files: list[tuple[str, int | None]] = [(path, int(path.rsplit('.u', 1)[1][:-5])) for path in glob.glob(_json_path(0).replace('.u0.', '.u*.'))
             if path.rsplit('.u', 1)[1][:-5].isdigit()]
    if os.path.exists(JSON_PATH):
        try:
            owner = accounts.first_user_id()
        except SQLAlchemyError:
            owner = None
        files.append((JSON_PATH, owner))
    return files


def _import_legacy_json() -> None:
    """Pasa a MySQL lo escrito en los JSON (perfiles viejos o cambios durante una caída).

    Solo se aplica sobre filas que no cambiaron después de la última escritura del JSON, para no
    pisar cambios hechos en MySQL por otra instancia. Después se renombra a .migrated.
    """
    for path, user_id in _json_files():
        _import_json(path, user_id)


def _import_json(path: str, user_id: int | None) -> None:
    legacy, deleted = _read_json(path), _json_deleted(path)
    if not legacy and not deleted:
        return
    if _session_factory is None:
        raise RuntimeError('profile_store sin base configurada')
    with _session_factory() as session:
        stamp = _read_json_raw(path).get(WRITTEN_KEY)
        if not isinstance(stamp, (int, float)):
            stamp = os.path.getmtime(path)
        written_at = datetime.fromtimestamp(stamp)
        owner = UserProfile.user_id.is_(None) if user_id is None else UserProfile.user_id == user_id
        rows = {row.role_type: row for row in session.scalars(select(UserProfile).where(owner))}
        stale = {role for role, row in rows.items()
                 if row.updated_at and row.updated_at > written_at}
        for role, data in legacy.items():
            if role not in rows:
                session.add(UserProfile(role_type=role, data=data, user_id=user_id))
            elif role not in stale:
                rows[role].data = data
        for role in deleted - set(legacy) - stale:
            if role in rows:
                session.delete(rows[role])
        session.commit()
    os.replace(path, path + '.migrated')
    logger.info(f"Migrados {len(legacy)} perfiles y {len(deleted)} borrados de {path} a MySQL")


def _mine() -> ColumnElement[bool]:
    uid = accounts.current_user_id()
    return UserProfile.user_id.is_(None) if uid is None else UserProfile.user_id == uid


def _find(session: Session, role_type: str) -> UserProfile | None:
    """Fila del rol en MySQL o None."""
    return session.scalars(select(UserProfile).where(_mine(), UserProfile.role_type == role_type)).first()


def get_all_profiles() -> Profiles:
    """{role_type: perfil} de todos los perfiles."""
    def db_op(session: Session) -> Profiles:
        rows = session.scalars(select(UserProfile).where(_mine()).order_by(UserProfile.id))
        return {row.role_type: row.data for row in rows}
    return _run(db_op, _read_json)


def get_profile(role_type: str) -> dict[str, Any] | None:
    """Perfil de un rol o None."""
    return get_all_profiles().get(role_type)


def get_first_profile() -> dict[str, Any] | None:
    """Primer perfil disponible (cualquier rol) o None."""
    return next(iter(get_all_profiles().values()), None)


def save_profile(role_type: str, data: dict[str, Any]) -> None:
    """Crea o reemplaza el perfil de un rol."""
    def db_op(session: Session) -> None:
        row = _find(session, role_type)
        if row:
            row.data = data
        else:
            session.add(UserProfile(role_type=role_type, data=data, user_id=accounts.current_user_id()))
        session.commit()

    def json_op() -> None:
        profiles = _read_json()
        profiles[role_type] = data
        _write_json(profiles, _json_deleted() - {role_type})
    _run(db_op, json_op)


def delete_profile(role_type: str) -> dict[str, Any] | None:
    """Borra el perfil de un rol; devuelve los datos borrados o None si no existía."""
    def db_op(session: Session) -> dict[str, Any] | None:
        row = _find(session, role_type)
        if not row:
            return None
        removed: dict[str, Any] | None = row.data
        session.delete(row)
        session.commit()
        return removed

    def json_op() -> dict[str, Any] | None:
        profiles = _read_json()
        removed = profiles.pop(role_type, None)
        # Sin MySQL no se puede borrar un perfil que solo está en la tabla: se informa que no existe
        if removed is not None:
            _write_json(profiles, _json_deleted() | {role_type})
        return removed
    return _run(db_op, json_op)


def primary_available() -> bool:
    """False si los perfiles van en MySQL pero ahora no responde (solo se vería el JSON de respaldo)."""
    return os.getenv('PROFILE_STORAGE', 'mysql') != 'mysql' or _sessions() is not None


def delete_all() -> None:
    """Borra todos los perfiles del usuario, incluido su JSON de respaldo y la copia .migrated.

    Si MySQL está configurado pero caído, falla: borrar solo el JSON dejaría los perfiles en la base.
    """
    if not primary_available():
        raise RuntimeError('MySQL no disponible: no se pueden borrar los perfiles guardados ahí')
    sessions = _sessions()
    if sessions is not None:
        with sessions() as session:
            session.execute(delete(UserProfile).where(_mine()))
            session.commit()
    paths = [_current_json()]
    if accounts.current_user_id() is not None and accounts.current_user_id() == accounts.first_user_id():
        paths.append(JSON_PATH)  # el JSON de antes del multiusuario es de la primera cuenta
    for path in paths:
        for candidate in (path, path + '.migrated'):
            if os.path.exists(candidate):
                os.remove(candidate)


def _seal_json_file(path: str) -> int:
    """Cifra los perfiles en texto plano de un JSON de respaldo, sin tocar el resto de las claves."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    plain = [k for k, v in raw.items() if isinstance(v, dict) and not _is_sealed(v)]
    if plain:
        raw.update({k: _seal(raw[k]) for k in plain})
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
    return len(plain)


def encrypt_existing() -> int:
    """Cifra los perfiles guardados en texto plano (MySQL, JSON y .migrated). Sin clave no hace nada."""
    if cv_storage.get_fernet() is None:
        return 0
    done = 0
    sessions = _sessions()
    if sessions is not None:
        with sessions() as session:
            for row_id, raw in session.execute(text('SELECT id, data FROM user_profiles')):
                if not _is_sealed(json.loads(raw) if isinstance(raw, str) else raw):
                    row = session.get(UserProfile, row_id)
                    flag_modified(row, 'data')
                    done += 1
            session.commit()
    import glob
    for path in glob.glob(JSON_PATH.replace('.json', '*.json*')):
        done += _seal_json_file(path)
    return done
