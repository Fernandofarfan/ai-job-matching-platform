"""Passkeys (WebAuthn): entrar sin contraseña con la huella, la cara o el PIN del dispositivo.

Se pide verificación del usuario en el dispositivo (`user_verification=required`), así que una passkey ya es
algo que se tiene más algo que se es o se sabe: el login con passkey no pide además el código de la app.
El origen esperado sale de `WEBAUTHN_ORIGIN` o `APP_BASE_URL` (detrás de un proxy) y, si no hay, del pedido;
el RP ID, de `WEBAUTHN_RP_ID` o del host de ese origen.
"""
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import DateTime, Integer, String, Text, delete as sql_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import accounts
from accounts import Base

logger = logging.getLogger(__name__)

MAX_PER_USER = 10
CHALLENGE_MAX_AGE = 300
RP_NAME = 'EmpleoIA'


class Passkey(Base):
    """Credencial WebAuthn de una cuenta (solo la clave pública)."""
    __tablename__ = 'passkeys'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # hasta 1023 bytes (WebAuthn): el ID va en texto y la unicidad, en su SHA-256
    credential_id: Mapped[str] = mapped_column(Text, nullable=False)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebauthnChallenge(Base):
    """Desafío emitido y todavía sin usar: la cookie de sesión vieja no alcanza para reusarlo."""
    __tablename__ = 'webauthn_challenges'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class PasskeyError(Exception):
    """La passkey no se pudo registrar o no sirve para entrar (mensaje para mostrar)."""


def origin(request_origin: str) -> str:
    """Origen que tiene que firmar el navegador."""
    return (os.getenv('WEBAUTHN_ORIGIN') or os.getenv('APP_BASE_URL') or request_origin).rstrip('/')


def rp_id(site: str) -> str:
    """Dominio al que quedan atadas las passkeys."""
    return os.getenv('WEBAUTHN_RP_ID') or urlparse(site).hostname or 'localhost'


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _b64(data: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url
    return bytes_to_base64url(data)


def _unb64(value: str) -> bytes:
    from webauthn import base64url_to_bytes
    return base64url_to_bytes(value)


def new_challenge(session: dict, purpose: str, user_id: Optional[int] = None) -> bytes:
    """Desafío de un solo uso, guardado en la sesión por `CHALLENGE_MAX_AGE` segundos."""
    challenge = os.urandom(32)
    now = datetime.now()
    with accounts._sessions()() as db:
        db.execute(sql_delete(WebauthnChallenge).where(WebauthnChallenge.expires_at < now))
        db.add(WebauthnChallenge(challenge_hash=_sha(_b64(challenge)), purpose=purpose, user_id=user_id,
                                 expires_at=now + timedelta(seconds=CHALLENGE_MAX_AGE)))
        db.commit()
    session['webauthn'] = {'c': _b64(challenge), 'p': purpose, 'uid': user_id, 'ts': time.time()}
    return challenge


def take_challenge(session: dict, purpose: str, user_id: Optional[int] = None) -> Optional[bytes]:
    """Saca el desafío de la sesión y lo borra de la base (sirve una vez, aunque se restaure una cookie vieja);
    None si no hay, es de otro uso, venció o ya se usó."""
    data = session.pop('webauthn', None)
    if (not isinstance(data, dict) or data.get('p') != purpose or data.get('uid') != user_id
            or time.time() - float(data.get('ts') or 0) > CHALLENGE_MAX_AGE):
        return None
    owner = WebauthnChallenge.user_id.is_(None) if user_id is None else WebauthnChallenge.user_id == user_id
    with accounts._sessions()() as db:
        result = db.execute(sql_delete(WebauthnChallenge).where(
            WebauthnChallenge.challenge_hash == _sha(str(data.get('c'))), WebauthnChallenge.purpose == purpose,
            owner, WebauthnChallenge.expires_at >= datetime.now()))
        db.commit()
    if getattr(result, 'rowcount', 0) != 1:
        return None
    return _unb64(data['c'])


def registration_options(user_id: int, email: str, site: str, challenge: bytes) -> str:
    """Opciones de `navigator.credentials.create` en JSON."""
    import webauthn
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                          ResidentKeyRequirement, UserVerificationRequirement)
    with accounts._sessions()() as session:
        existing = session.scalars(select(Passkey.credential_id).where(Passkey.user_id == user_id)).all()  # noqa: E501
    options = webauthn.generate_registration_options(
        rp_id=rp_id(site), rp_name=RP_NAME, user_name=email, user_display_name=email,
        user_id=str(user_id).encode(), challenge=challenge,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64(c)) for c in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED))
    return webauthn.options_to_json(options)


def register(user_id: int, credential: dict, challenge: bytes, site: str, name: str) -> dict:
    """Verifica la respuesta del navegador y guarda la passkey."""
    import webauthn
    name = (name or '').strip()[:100] or 'Passkey'
    with accounts._sessions()() as session:
        if session.scalar(select(func.count()).select_from(Passkey).where(Passkey.user_id == user_id)) >= MAX_PER_USER:
            raise PasskeyError(f'Llegaste al máximo de {MAX_PER_USER} passkeys: borrá una antes de agregar otra')
    try:
        verified = webauthn.verify_registration_response(
            credential=json.dumps(credential), expected_challenge=challenge, expected_rp_id=rp_id(site),
            expected_origin=site, require_user_verification=True)
    except Exception as e:
        logger.warning(f'Passkey rechazada al registrarla: {type(e).__name__}: {e}')
        raise PasskeyError('El navegador no pudo crear la passkey') from e
    credential_id = _b64(verified.credential_id)
    with accounts._sessions()() as session:
        row = Passkey(user_id=user_id, credential_id=credential_id, credential_hash=_sha(credential_id),
                      public_key=_b64(verified.credential_public_key), sign_count=verified.sign_count, name=name)
        session.add(row)
        try:
            session.commit()
        except IntegrityError as e:
            raise PasskeyError('Esa passkey ya está registrada') from e
        return {'id': row.id, 'name': row.name}


def authentication_options(site: str, challenge: bytes) -> str:
    """Opciones de `navigator.credentials.get` en JSON (passkeys guardadas en el dispositivo: sin email)."""
    import webauthn
    from webauthn.helpers.structs import UserVerificationRequirement
    return webauthn.options_to_json(webauthn.generate_authentication_options(
        rp_id=rp_id(site), challenge=challenge, user_verification=UserVerificationRequirement.REQUIRED))


def authenticate(credential: dict, challenge: bytes, site: str) -> int:
    """Cuenta dueña de la passkey si la firma es válida; levanta PasskeyError si no."""
    import webauthn
    credential_id = credential.get('id') if isinstance(credential, dict) else None
    if not isinstance(credential_id, str):
        raise PasskeyError('Passkey inválida')
    with accounts._sessions()() as session:
        row = session.scalars(select(Passkey).where(Passkey.credential_hash == _sha(credential_id))).first()
        if row is None:
            raise PasskeyError('Esa passkey no está registrada en ninguna cuenta')
        try:
            verified = webauthn.verify_authentication_response(
                credential=json.dumps(credential), expected_challenge=challenge, expected_rp_id=rp_id(site),
                expected_origin=site, credential_public_key=_unb64(row.public_key),
                credential_current_sign_count=row.sign_count, require_user_verification=True)
        except Exception as e:
            logger.warning(f'Passkey rechazada al entrar: {type(e).__name__}: {e}')
            raise PasskeyError('No se pudo comprobar la passkey') from e
        row.sign_count = verified.new_sign_count
        row.last_used_at = datetime.now()
        session.commit()
        return row.user_id


def list_for(user_id: Optional[int]) -> list:
    """Passkeys de la cuenta para Mi cuenta."""
    with accounts._sessions()() as session:
        rows = session.scalars(select(Passkey).where(Passkey.user_id == user_id).order_by(Passkey.id)).all()
        return [{'id': r.id, 'name': r.name, 'created_at': r.created_at, 'last_used_at': r.last_used_at}
                for r in rows]


def delete_all(user_id: int) -> int:
    """Borra todas las passkeys de la cuenta (la recupera quien sí es dueño del email); devuelve cuántas."""
    with accounts._sessions()() as session:
        result = session.execute(sql_delete(Passkey).where(Passkey.user_id == user_id))
        session.commit()
        return int(getattr(result, 'rowcount', 0) or 0)


def delete(user_id: int, passkey_id: int) -> bool:
    """Borra una passkey de la cuenta; False si no es suya o no existe."""
    with accounts._sessions()() as session:
        row = session.get(Passkey, passkey_id)
        if row is None or row.user_id != user_id:
            return False
        session.delete(row)
        session.commit()
        return True
