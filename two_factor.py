"""Segundo factor TOTP (RFC 6238, app autenticadora) por cuenta, con códigos de recuperación de un uso.

El secreto se guarda cifrado con CV_ENCRYPTION_KEY si está definida; los códigos de recuperación,
solo como hash. `last_step` impide reusar un código ya aceptado.
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime
from typing import Optional

import pyotp
import segno
from sqlalchemy import Column, DateTime, Integer, String, Text, delete, or_, select, update

import accounts

logger = logging.getLogger(__name__)
ISSUER = 'EmpleoIA'
RECOVERY_CODES = 10
VALID_WINDOW = 1  # acepta el código anterior y el siguiente (30 s de desfase de reloj)


class UserTotp(accounts.Base):  # type: ignore[misc,valid-type]
    """Una fila por cuenta; `enabled_at` NULL = configuración empezada y no confirmada."""

    __tablename__ = 'user_totp'
    __table_args__ = {'extend_existing': True}
    user_id = Column(Integer, primary_key=True, autoincrement=False)
    secret = Column(String(255), nullable=False)
    recovery_hashes = Column(Text, nullable=True)
    last_step = Column(Integer, nullable=True)
    enabled_at = Column(DateTime, nullable=True)


class TwoFactorError(RuntimeError):
    """El secreto no se puede leer (por ejemplo, falta CV_ENCRYPTION_KEY)."""


def _encrypt(secret: str) -> str:
    """Cifra el secreto si hay clave."""
    import cv_storage
    fernet = cv_storage.get_fernet()
    return fernet.encrypt(secret.encode()).decode() if fernet else secret


def _decrypt(value: str) -> str:
    """Secreto en claro (base32 sin cifrar o token Fernet)."""
    import cv_storage
    if value.isupper() or value.isdigit():
        return value
    fernet = cv_storage.get_fernet()
    if fernet is None:
        raise TwoFactorError('El secreto del segundo factor está cifrado y falta CV_ENCRYPTION_KEY')
    return fernet.decrypt(value.encode()).decode()


def _hash(code: str) -> str:
    """Hash de un código de recuperación normalizado."""
    return hashlib.sha256(code.replace('-', '').replace(' ', '').lower().encode()).hexdigest()


def _new_recovery_codes() -> list:
    """Códigos de 80 bits tipo `a1b2c-d3e4f-a5b6c-d7e8f`: aun con la base filtrada no se adivinan."""
    codes = (secrets.token_hex(10) for _ in range(RECOVERY_CODES))
    return ['-'.join(c[i:i + 5] for i in range(0, 20, 5)) for c in codes]


def _row(user_id: Optional[int]) -> Optional[UserTotp]:
    """Fila de la cuenta o None."""
    if not user_id:
        return None
    with accounts._sessions()() as session:
        return session.get(UserTotp, user_id)


def is_enabled(user_id: Optional[int]) -> bool:
    """True si la cuenta confirmó el segundo factor."""
    row = _row(user_id)
    return bool(row and row.enabled_at)


def start_setup(user_id: int) -> str:
    """Secreto nuevo sin activar (reemplaza una configuración a medias); lo devuelve en claro."""
    if is_enabled(user_id):
        raise TwoFactorError('El segundo factor ya está activado')
    secret = pyotp.random_base32()
    with accounts._sessions()() as session:
        session.execute(delete(UserTotp).where(UserTotp.user_id == user_id))
        session.add(UserTotp(user_id=user_id, secret=_encrypt(secret)))
        session.commit()
    return secret


def pending_secret(user_id: Optional[int]) -> Optional[str]:
    """Secreto de una configuración empezada y no confirmada."""
    row = _row(user_id)
    return _decrypt(str(row.secret)) if row and not row.enabled_at else None


def provisioning_uri(email: str, secret: str) -> str:
    """URI otpauth:// para la app autenticadora."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    """QR en SVG para incrustar en la página (sin servicios externos)."""
    return segno.make(uri, error='m').svg_inline(scale=4, title='Código QR para la app autenticadora')


def _matching_step(secret: str, code: str) -> Optional[int]:
    """Paso de 30 s cuyo código coincide, dentro de la ventana permitida."""
    code = (code or '').replace(' ', '')
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time()) // totp.interval
    for step in range(now - VALID_WINDOW, now + VALID_WINDOW + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def _consume_step(user_id: int, step: int) -> bool:
    """Marca el paso como usado; False si ese código (o uno posterior) ya se aceptó."""
    with accounts._sessions()() as session:
        result = session.execute(update(UserTotp).where(
            UserTotp.user_id == user_id,
            or_(UserTotp.last_step.is_(None), UserTotp.last_step < step),
        ).values(last_step=step))
        session.commit()
        return bool(result.rowcount)


def enable(user_id: int, code: str) -> Optional[list]:
    """Confirma la configuración con un código de la app; devuelve los códigos de recuperación."""
    row = _row(user_id)
    if not row or row.enabled_at:
        return None
    step = _matching_step(_decrypt(str(row.secret)), code)
    if step is None or not _consume_step(user_id, step):
        return None
    codes = _new_recovery_codes()
    with accounts._sessions()() as session:
        session.execute(update(UserTotp).where(UserTotp.user_id == user_id).values(
            enabled_at=datetime.now(), recovery_hashes=json.dumps([_hash(c) for c in codes])))
        session.commit()
    return codes


def verify(user_id: int, code: str) -> Optional[str]:
    """'totp' o 'recovery' si el código vale (y lo consume); None si no."""
    row = _row(user_id)
    if not row or not row.enabled_at:
        return None
    try:
        secret: Optional[str] = _decrypt(str(row.secret))
    except Exception as e:
        # sin la clave (o con otra) la app autenticadora no se puede comprobar; los códigos de recuperación sí
        logger.error(f'No se pudo descifrar el segundo factor de la cuenta {user_id}: {e}')
        secret = None
    step = _matching_step(secret, code) if secret else None
    if step is not None:
        return 'totp' if _consume_step(user_id, step) else None
    hashes = json.loads(str(row.recovery_hashes or "[]"))
    candidate = _hash(code or '')
    if not code or candidate not in hashes:
        return None
    remaining = json.dumps([h for h in hashes if h != candidate])
    with accounts._sessions()() as session:
        # solo si nadie usó otro código entretanto: el mismo código no vale dos veces
        result = session.execute(update(UserTotp).where(
            UserTotp.user_id == user_id, UserTotp.recovery_hashes == row.recovery_hashes,
        ).values(recovery_hashes=remaining))
        session.commit()
    return 'recovery' if result.rowcount else None


def recovery_codes_left(user_id: Optional[int]) -> int:
    """Cuántos códigos de recuperación quedan sin usar."""
    row = _row(user_id)
    return len(json.loads(str(row.recovery_hashes or "[]"))) if row and row.enabled_at else 0


def regenerate_recovery_codes(user_id: int) -> Optional[list]:
    """Códigos nuevos; los anteriores dejan de valer."""
    if not is_enabled(user_id):
        return None
    codes = _new_recovery_codes()
    with accounts._sessions()() as session:
        session.execute(update(UserTotp).where(UserTotp.user_id == user_id).values(
            recovery_hashes=json.dumps([_hash(c) for c in codes])))
        session.commit()
    return codes


def disable(user_id: int) -> None:
    """Desactiva el segundo factor y borra el secreto."""
    with accounts._sessions()() as session:
        session.execute(delete(UserTotp).where(UserTotp.user_id == user_id))
        session.commit()


def enabled_user_ids() -> set:
    """Cuentas con el segundo factor activo (para el panel de administración)."""
    with accounts._sessions()() as session:
        return set(session.execute(select(UserTotp.user_id).where(UserTotp.enabled_at.isnot(None))).scalars())
