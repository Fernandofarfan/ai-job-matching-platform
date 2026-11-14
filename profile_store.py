"""Perfiles de CV por rol en MySQL (tabla user_profiles), con fallback a profiles/user_profiles.json."""
import json
import logging
import os
import time
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()
JSON_PATH = os.path.join('profiles', 'user_profiles.json')
# Roles borrados mientras MySQL no respondía; se borran en MySQL al volver
DELETED_KEY = '_deleted'
_RETRY_SECONDS = 60

_session_factory = None
_last_failure = 0.0


class UserProfile(Base):
    """Un perfil (CV parseado) por tipo de rol."""
    __tablename__ = 'user_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_type = Column(String(100), nullable=False, unique=True)
    data = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


def configure(session_factory):
    """Usa la fábrica de sesiones dada (tests) o None para volver a la detección automática."""
    global _session_factory, _last_failure
    _session_factory = session_factory
    _last_failure = 0.0


def _mark_failure(error):
    """Pasa al JSON y reintenta MySQL dentro de _RETRY_SECONDS."""
    global _session_factory, _last_failure
    _session_factory = None
    _last_failure = time.time()
    logger.warning(f"MySQL no disponible para perfiles ({error}); se usa {JSON_PATH}")


def _sessions():
    """Devuelve la fábrica de sesiones de MySQL, o None si se usa el JSON."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    if os.getenv('PROFILE_STORAGE', 'mysql') != 'mysql' or time.time() - _last_failure < _RETRY_SECONDS:
        return None
    try:
        from models import SessionLocal, engine
        UserProfile.__table__.create(bind=engine, checkfirst=True)
        _session_factory = SessionLocal
        _import_legacy_json()
    except Exception as e:
        _mark_failure(e)
    return _session_factory


def _run(db_op, json_op):
    """Ejecuta db_op(session) en MySQL; si no hay MySQL o falla, json_op() sobre el JSON."""
    sessions = _sessions()
    if sessions is not None:
        try:
            with sessions() as session:
                return db_op(session)
        except SQLAlchemyError as e:
            _mark_failure(e)
    return json_op()


def _read_json_raw():
    """Contenido completo del JSON (perfiles y lista de borrados)."""
    if not os.path.exists(JSON_PATH):
        return {}
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _read_json():
    return {k: v for k, v in _read_json_raw().items() if isinstance(v, dict)}


def _write_json(profiles, deleted):
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    data = dict(profiles)
    if deleted:
        data[DELETED_KEY] = sorted(deleted)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _json_deleted():
    """Roles borrados mientras MySQL no respondía."""
    deleted = _read_json_raw().get(DELETED_KEY, [])
    return set(deleted) if isinstance(deleted, list) else set()


def _import_legacy_json():
    """Pasa a MySQL lo escrito en el JSON (perfiles viejos o cambios durante una caída).

    Solo se aplica sobre filas que no cambiaron después de la última escritura del JSON, para no
    pisar cambios hechos en MySQL por otra instancia. Después se renombra a .migrated.
    """
    legacy, deleted = _read_json(), _json_deleted()
    if not legacy and not deleted:
        return
    with _session_factory() as session:
        written_at = datetime.fromtimestamp(os.path.getmtime(JSON_PATH))
        rows = {row.role_type: row for row in session.scalars(select(UserProfile))}
        stale = {role for role, row in rows.items()
                 if row.updated_at and row.updated_at > written_at}
        for role, data in legacy.items():
            if role not in rows:
                session.add(UserProfile(role_type=role, data=data))
            elif role not in stale:
                rows[role].data = data
        for role in deleted - set(legacy) - stale:
            if role in rows:
                session.delete(rows[role])
        session.commit()
    os.replace(JSON_PATH, JSON_PATH + '.migrated')
    logger.info(f"Migrados {len(legacy)} perfiles y {len(deleted)} borrados de {JSON_PATH} a MySQL")


def _find(session, role_type):
    """Fila del rol en MySQL o None."""
    return session.scalars(select(UserProfile).where(UserProfile.role_type == role_type)).first()


def get_all_profiles():
    """{role_type: perfil} de todos los perfiles."""
    def db_op(session):
        rows = session.scalars(select(UserProfile).order_by(UserProfile.id))
        return {row.role_type: row.data for row in rows}
    return _run(db_op, _read_json)


def get_profile(role_type):
    """Perfil de un rol o None."""
    return get_all_profiles().get(role_type)


def get_first_profile():
    """Primer perfil disponible (cualquier rol) o None."""
    return next(iter(get_all_profiles().values()), None)


def save_profile(role_type, data):
    """Crea o reemplaza el perfil de un rol."""
    def db_op(session):
        row = _find(session, role_type)
        if row:
            row.data = data
        else:
            session.add(UserProfile(role_type=role_type, data=data))
        session.commit()

    def json_op():
        profiles = _read_json()
        profiles[role_type] = data
        _write_json(profiles, _json_deleted() - {role_type})
    _run(db_op, json_op)


def delete_profile(role_type):
    """Borra el perfil de un rol; devuelve los datos borrados o None si no existía."""
    def db_op(session):
        row = _find(session, role_type)
        if not row:
            return None
        removed = row.data
        session.delete(row)
        session.commit()
        return removed

    def json_op():
        profiles = _read_json()
        removed = profiles.pop(role_type, None)
        # Sin MySQL no se puede borrar un perfil que solo está en la tabla: se informa que no existe
        if removed is not None:
            _write_json(profiles, _json_deleted() | {role_type})
        return removed
    return _run(db_op, json_op)
