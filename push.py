"""Notificaciones push (Web Push con VAPID) a los dispositivos de cada cuenta."""
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlsplit

from sqlalchemy import DateTime, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

import accounts

logger = logging.getLogger(__name__)

# El servidor hace un POST al endpoint que manda el navegador: solo servicios de push conocidos (evita SSRF).
PUSH_HOSTS = ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'push.apple.com',
              'notify.windows.com', 'push.services.mozilla.com')
MAX_ENDPOINT = 2048
DEAD_STATUSES = (404, 410)


class PushSubscription(accounts.Base):
    """Un dispositivo/navegador suscripto; el endpoint se indexa por hash (puede superar 255 caracteres)."""

    __tablename__ = 'push_subscriptions'
    __table_args__ = {'extend_existing': True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)


class PushError(ValueError):
    """Suscripción inválida."""


def configured() -> bool:
    """True si hay claves VAPID."""
    return bool(public_key() and os.getenv('VAPID_PRIVATE_KEY'))


def public_key() -> str:
    """Clave pública VAPID (applicationServerKey del navegador)."""
    return os.getenv('VAPID_PUBLIC_KEY', '').strip()


def _hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def _allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or '').lower()
    extra = tuple(h.strip().lower() for h in os.getenv('PUSH_ALLOWED_HOSTS', '').split(',') if h.strip())
    return (parts.scheme == 'https' and len(endpoint) <= MAX_ENDPOINT and parts.port in (None, 443)
            and any(host == h or host.endswith('.' + h) for h in PUSH_HOSTS + extra))


def _owner_filter(user_id: Optional[int]) -> Any:
    col = PushSubscription.user_id
    return col.is_(None) if user_id is None else col == user_id


def subscribe(user_id: Optional[int], endpoint: str, p256dh: str, auth: str) -> None:
    """Guarda el dispositivo para la cuenta; si ya estaba suscripto con otra cuenta, pasa a esta."""
    endpoint = (endpoint or '').strip()
    if not _allowed_endpoint(endpoint):
        raise PushError('Servicio de push no admitido')
    if not (p256dh and auth) or len(p256dh) > 255 or len(auth) > 255:
        raise PushError('Faltan las claves de la suscripción')
    with accounts._sessions()() as session:
        row = session.execute(select(PushSubscription).where(
            PushSubscription.endpoint_hash == _hash(endpoint))).scalar_one_or_none()
        row = row or PushSubscription(endpoint_hash=_hash(endpoint), endpoint=endpoint)
        row.user_id, row.p256dh, row.auth = user_id, p256dh, auth
        session.add(row)
        session.commit()


def unsubscribe(user_id: Optional[int], endpoint: str) -> bool:
    """Quita el dispositivo, solo si es de la cuenta."""
    with accounts._sessions()() as session:
        result = session.execute(delete(PushSubscription).where(
            PushSubscription.endpoint_hash == _hash(endpoint or ''), _owner_filter(user_id)))
        session.commit()
        return bool(accounts.rowcount(result))


def device_count(user_id: Optional[int]) -> int:
    """Dispositivos suscriptos de la cuenta."""
    try:
        with accounts._sessions()() as session:
            return len(session.execute(select(PushSubscription.id).where(_owner_filter(user_id))).all())
    except Exception as e:
        logger.warning(f'Suscripciones push no disponibles ({type(e).__name__})')
        return 0


def available(user_id: Optional[int]) -> bool:
    """La cuenta puede recibir push: VAPID configurado y al menos un dispositivo."""
    return configured() and device_count(user_id) > 0


def _webpush(**kwargs: Any) -> Any:
    from pywebpush import webpush
    return webpush(**kwargs)


def send(user_id: Optional[int], title: str, body: str, url: str = '/', endpoint: Optional[str] = None) -> int:
    """Manda la notificación a cada dispositivo de la cuenta (o solo a `endpoint`, si es de la cuenta);
    borra los que el servicio dio de baja. Devuelve cuántos la recibieron."""
    if not configured():
        return 0
    query = select(PushSubscription).where(_owner_filter(user_id))
    if endpoint is not None:
        query = query.where(PushSubscription.endpoint_hash == _hash(endpoint))
    with accounts._sessions()() as session:
        subs = session.execute(query).scalars().all()
        targets = [(s.id, s.endpoint, s.p256dh, s.auth) for s in subs]
    payload = json.dumps({'title': title[:120], 'body': body[:300], 'url': url if url.startswith('/') else '/'})
    claims = {'sub': os.getenv('VAPID_SUBJECT') or f"mailto:{os.getenv('ADMIN_EMAIL') or 'admin@localhost'}"}
    delivered, dead = 0, []
    for sub_id, endpoint, p256dh, auth in targets:
        try:
            _webpush(subscription_info={'endpoint': endpoint, 'keys': {'p256dh': p256dh, 'auth': auth}},
                     data=payload, vapid_private_key=os.getenv('VAPID_PRIVATE_KEY'),
                     vapid_claims=dict(claims), ttl=86400, timeout=10)
            delivered += 1
        except Exception as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status in DEAD_STATUSES:
                dead.append(sub_id)
            else:
                logger.error(f'Push falló ({type(e).__name__}, {status})')
    if dead:
        with accounts._sessions()() as session:
            session.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
            session.commit()
    return delivered


def send_to_current(title: str, body: str, url: str = '/') -> bool:
    """send() a la cuenta del pedido/tarea actual."""
    return send(accounts.current_user_id(), title, body, url) > 0
