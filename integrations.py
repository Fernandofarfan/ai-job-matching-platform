"""Integraciones de cada cuenta: chat de Telegram, token de la extensión de Chrome y Gmail."""
import hashlib
import re
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, select

import accounts

CHAT_ID = re.compile(r'^-?\d{1,20}$')


class UserIntegration(accounts.Base):  # type: ignore[misc,valid-type]
    """Una fila por cuenta; el token de la extensión se guarda solo como hash y el de Gmail cifrado."""

    __tablename__ = 'user_integrations'
    __table_args__ = {'extend_existing': True}  # los tests reimportan el módulo
    user_id = Column(Integer, primary_key=True, autoincrement=False)
    telegram_chat_id = Column(String(64), nullable=True)
    extension_token_hash = Column(String(64), nullable=True, unique=True)
    gmail_token = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class IntegrationError(ValueError):
    """Dato de integración inválido."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _update(user_id: int, **values):
    """Crea o actualiza la fila de la cuenta."""
    with accounts._sessions()() as session:
        row = session.get(UserIntegration, user_id) or UserIntegration(user_id=user_id)
        for key, value in values.items():
            setattr(row, key, value)
        session.add(row)
        session.commit()


def _row(user_id: Optional[int]) -> Optional[UserIntegration]:
    if user_id is None:
        return None
    with accounts._sessions()() as session:
        return session.get(UserIntegration, user_id)


def status(user_id: Optional[int]) -> dict:
    """Qué tiene conectado la cuenta (sin secretos)."""
    row = _row(user_id)
    return {
        'telegram_chat_id': row.telegram_chat_id if row else None,
        'extension_token': bool(row and row.extension_token_hash),
        'gmail': bool(row and row.gmail_token),
    }


def set_telegram_chat(user_id: int, chat_id: str):
    """Guarda el chat de Telegram de la cuenta ('' lo borra)."""
    chat_id = (chat_id or '').strip()
    if chat_id and not CHAT_ID.match(chat_id):
        raise IntegrationError('El chat ID de Telegram es un número (ej. 123456789)')
    _update(user_id, telegram_chat_id=chat_id or None)


def telegram_chat_id(user_id: Optional[int]) -> Optional[str]:
    """Chat de Telegram propio de la cuenta, o None."""
    row = _row(user_id)
    return row.telegram_chat_id if row else None


def new_extension_token(user_id: int) -> str:
    """Genera un token nuevo para la extensión (reemplaza al anterior); se muestra una sola vez."""
    token = secrets.token_urlsafe(32)
    _update(user_id, extension_token_hash=_hash(token))
    return token


def revoke_extension_token(user_id: int):
    """La extensión deja de poder guardar en esta cuenta."""
    _update(user_id, extension_token_hash=None)


def user_for_extension_token(token: str) -> Optional[int]:
    """Cuenta dueña del token de la extensión, o None."""
    if not token:
        return None
    with accounts._sessions()() as session:
        return session.execute(select(UserIntegration.user_id)
                               .where(UserIntegration.extension_token_hash == _hash(token))).scalar_one_or_none()


def save_gmail_token(user_id: int, token_json: str):
    """Guarda el token OAuth de Gmail (cifrado si hay CV_ENCRYPTION_KEY)."""
    import cv_storage
    fernet = cv_storage.get_fernet()
    _update(user_id, gmail_token=fernet.encrypt(token_json.encode()).decode() if fernet else token_json)


def gmail_token(user_id: int) -> Optional[str]:
    """Token OAuth de Gmail de la cuenta en claro, o None."""
    import cv_storage
    row = _row(user_id)
    if not row or not row.gmail_token:
        return None
    value = row.gmail_token
    if value.lstrip().startswith('{'):
        return value
    fernet = cv_storage.get_fernet()
    if fernet is None:
        raise IntegrationError('El token de Gmail está cifrado y falta CV_ENCRYPTION_KEY')
    return fernet.decrypt(value.encode()).decode()


def clear_gmail(user_id: int):
    """Desconecta Gmail de la cuenta."""
    _update(user_id, gmail_token=None)


def gmail_user_ids() -> list:
    """Cuentas con Gmail conectado."""
    with accounts._sessions()() as session:
        return list(session.execute(select(UserIntegration.user_id)
                                    .where(UserIntegration.gmail_token.is_not(None))).scalars())
