"""Suscripciones a notificaciones push del navegador (/api/push/*)."""
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

import accounts
import push
from routers.tracker import ApiError, TrackerRoute, browser

router = APIRouter(prefix='/api/push', tags=['push'], route_class=TrackerRoute, dependencies=browser)


class SubscriptionKeys(BaseModel):
    """Claves que genera el navegador para cifrar el mensaje."""

    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class Subscription(BaseModel):
    """PushSubscription.toJSON() del navegador."""

    endpoint: str = Field(min_length=1, max_length=push.MAX_ENDPOINT)
    keys: SubscriptionKeys


class Endpoint(BaseModel):
    """Dispositivo a dar de baja."""

    endpoint: str = Field(min_length=1, max_length=push.MAX_ENDPOINT)


def _require_configured() -> None:
    if not push.configured():
        raise ApiError(503, 'Notificaciones push no configuradas (faltan VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY)')


@router.get('/config', response_model=None)
def config() -> dict[str, Any]:
    """Clave pública VAPID y cuántos dispositivos tiene la cuenta."""
    return {'success': True, 'enabled': push.configured(), 'public_key': push.public_key(),
            'devices': push.device_count(accounts.current_user_id())}


@router.post('/subscribe', response_model=None)
def subscribe(sub: Subscription) -> dict[str, Any]:
    """Suscribe este navegador a los avisos de la cuenta."""
    _require_configured()
    try:
        push.subscribe(accounts.current_user_id(), sub.endpoint, sub.keys.p256dh, sub.keys.auth)
    except push.PushError as e:
        raise ApiError(400, str(e))
    return {'success': True}


@router.post('/unsubscribe', response_model=None)
def unsubscribe(body: Endpoint) -> dict[str, Any]:
    """Da de baja este navegador."""
    return {'success': True, 'removed': push.unsubscribe(accounts.current_user_id(), body.endpoint)}


@router.post('/test', response_model=None)
def test(body: Endpoint) -> dict[str, Any]:
    """Manda una notificación de prueba solo a este navegador (si está suscripto a la cuenta)."""
    _require_configured()
    sent = push.send(accounts.current_user_id(), 'EmpleoIA', 'Las notificaciones funcionan en este dispositivo',
                     '/account', endpoint=body.endpoint)
    if not sent:
        raise ApiError(502, 'No se pudo entregar en este dispositivo')
    return {'success': True, 'sent': sent}
