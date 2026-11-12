"""Webhooks de proveedores externos (sin sesión ni CSRF: los autentica su firma)."""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import email_delivery
from fastapi_web import _body_within

router = APIRouter()
MAX_BODY = 1024 * 1024


@router.post('/webhooks/sendgrid', name='sendgrid_events')
async def sendgrid_events(request: Request):
    """Event Webhook de SendGrid: rebotes y denuncias de spam suprimen la dirección."""
    if not await _body_within(request, MAX_BODY):
        return JSONResponse({'error': 'Pedido demasiado grande'}, status_code=413)
    body = await request.body()
    if not email_delivery.verify_sendgrid_signature(
            body, request.headers.get('X-Twilio-Email-Event-Webhook-Signature', ''),
            request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp', '')):
        return JSONResponse({'error': 'Firma inválida'}, status_code=403)
    try:
        events = json.loads(body)
    except ValueError:
        return JSONResponse({'error': 'JSON inválido'}, status_code=400)
    suppressed = await run_in_threadpool(email_delivery.handle_sendgrid_events, events)
    return JSONResponse({'success': True, 'suppressed': suppressed})
