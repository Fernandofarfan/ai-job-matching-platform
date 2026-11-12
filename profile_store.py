"""Perfiles de CV por rol en MySQL (tabla user_profiles), con fallback a profiles/user_profiles.json."""
import json
import logging
import os
import time
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, select
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()
JSON_PATH = os.path.join('profiles', 'user_profiles.json')
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


def _sessions():
    """Devuelve la fábrica de sesiones de MySQL, o None si se usa el JSON."""
    global _session_factory, _last_failure
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
        _session_factory = None
        _last_failure = time.time()
        logger.warning(f"MySQL no disponible para perfiles ({e}); se usa {JSON_PATH}")
    return _session_factory


def _read_json():
    if not os.path.exists(JSON_PATH):
        return {}
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _write_json(profiles):
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)


def _import_legacy_json():
    """Primera vez con MySQL: copia los perfiles del JSON y lo renombra a .migrated."""
    legacy = _read_json()
    if not legacy:
        return
    with _session_factory() as session:
        if session.execute(select(UserProfile.id).limit(1)).first():
            return
        session.add_all(UserProfile(role_type=role, data=data) for role, data in legacy.items())
        session.commit()
    os.replace(JSON_PATH, JSON_PATH + '.migrated')
    logger.info(f"Migrados {len(legacy)} perfiles de {JSON_PATH} a MySQL")


def get_all_profiles():
    """{role_type: perfil} de todos los perfiles."""
    sessions = _sessions()
    if sessions is None:
        return _read_json()
    with sessions() as session:
        return {row.role_type: row.data for row in session.scalars(select(UserProfile).order_by(UserProfile.id))}


def get_profile(role_type):
    """Perfil de un rol o None."""
    return get_all_profiles().get(role_type)


def get_first_profile():
    """Primer perfil disponible (cualquier rol) o None."""
    return next(iter(get_all_profiles().values()), None)


def save_profile(role_type, data):
    """Crea o reemplaza el perfil de un rol."""
    sessions = _sessions()
    if sessions is None:
        profiles = _read_json()
        profiles[role_type] = data
        _write_json(profiles)
        return
    with sessions() as session:
        row = session.scalars(select(UserProfile).where(UserProfile.role_type == role_type)).first()
        if row:
            row.data = data
        else:
            session.add(UserProfile(role_type=role_type, data=data))
        session.commit()


def delete_profile(role_type):
    """Borra el perfil de un rol; devuelve los datos borrados o None si no existía."""
    sessions = _sessions()
    if sessions is None:
        profiles = _read_json()
        removed = profiles.pop(role_type, None)
        if removed is not None:
            _write_json(profiles)
        return removed
    with sessions() as session:
        row = session.scalars(select(UserProfile).where(UserProfile.role_type == role_type)).first()
        if not row:
            return None
        removed = row.data
        session.delete(row)
        session.commit()
        return removed
