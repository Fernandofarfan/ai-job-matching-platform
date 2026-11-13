"""
routers/notifications.py — API de notificaciones (config, test, digest).
Migrado desde app.py (Flask).
"""
import os
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.state import db_manager

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

try:
    from notifier import notifier as notification_manager
except ImportError:
    notification_manager = None


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


@router.get("/config")
async def api_notifications_config():
    """Retorna la configuración de notificaciones."""
    if notification_manager:
        return {'success': True, 'config': notification_manager.get_notification_config()}
    return _err(503, "Notification manager not available")


@router.post("/test")
async def api_notifications_test():
    """Envía un email de prueba para verificar configuración SMTP."""
    if not notification_manager:
        return _err(503, "Notification manager not available")
    result = notification_manager.test_email_config()
    return {'success': result['success'], 'message': result['message']}


@router.post("/trigger-digest")
async def api_trigger_digest():
    """Fuerza el envío de un digest de trabajos al email configurado."""
    if not notification_manager:
        return _err(503, "Notification manager not available")
    try:
        user_email = os.getenv('NOTIFICATION_EMAIL', '')
        if not user_email:
            return _err(400, "NOTIFICATION_EMAIL no configurado en .env")
        jobs = db_manager.get_all_tracked_jobs()
        recent_jobs = [j for j in jobs if j.get('status') in ('bookmarked', 'applying')][:20]
        result = notification_manager.send_new_jobs_digest(recent_jobs, user_email)
        return {'success': result,
                'message': f'Digest enviado a {user_email}' if result else 'Error al enviar'}
    except Exception as e:
        return _err(500, str(e))
