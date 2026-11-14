"""Mi cuenta (contraseña, sesiones, exportar y borrar), en FastAPI.

Telegram, extensión y Gmail en account_integrations.py, segundo factor y passkeys en security_pages.py, Administración en admin_pages.py y Excel/PDF en export_pages.py.

Los nombres de ruta son los endpoints que usaba Flask; los límites usan rate_limit (fastapi_web.hit_limit)
con la misma clave por cuenta.
"""
import logging
import os
from datetime import date
from typing import Any, Optional, cast
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

import account_lifecycle
import accounts
import auth
import data_export
import integrations
import security_events
import passkeys
import two_factor
import user_sessions
from fastapi_web import (TextForm, clear_offline_data, client_info, flash, web_app_for, get_session, hit_limit, services_for,
                         limit_key, read_form, redirect, render, safe_next, save_session,
                         too_many_requests, url_for)
from routers.auth_pages import audit, send_verification

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"], include_in_schema=False)


def _user_id() -> int:
    """Cuenta del pedido. Solo es None sin login (LOGIN_REQUIRED=false), donde las acciones de cuenta no
    encuentran a nadie y no hacen nada, igual que antes de tipar."""
    return cast(int, accounts.current_user_id())


async def _form(request: Request, spec: Optional[str] = None, namespace: str = '') -> tuple[TextForm, Optional[Response]]:
    """Formulario con CSRF y, si hay `spec`, el límite por cuenta del endpoint (como hacía @limiter.limit)."""
    form, error = await read_form(request)
    if error:
        return form, error
    if spec and not hit_limit(request, spec, namespace, limit_key(request)):
        return form, too_many_requests()
    return form, None


def _to_account(request: Request) -> Response:
    """Vuelta a Mi cuenta (con los avisos guardados en la sesión)."""
    return redirect(request, url_for(request, 'account'))


def _not_found(request: Request) -> Response:
    """404 genérico: el panel de administración no se anuncia."""
    return render(request, 'error.html', 404, code=404, message='Página no encontrada')


def _download(request: Request, data: bytes, media_type: str, filename: str, no_store: bool = False) -> Response:
    """Archivo para descargar (como send_file(as_attachment=True))."""
    headers = {'Content-Disposition': f"attachment; filename*=utf-8''{quote(filename)}"}
    if no_store:
        headers['Cache-Control'] = 'no-store'
    return save_session(request, Response(data, media_type=media_type, headers=headers))


# ─── Mi cuenta ───────────────────────────────────────────────────────────────

def _two_factor_status(user_id: int) -> dict[str, Any]:
    """Estado del segundo factor para la página; si la tabla falla, la página se muestra igual."""
    try:
        return {'enabled': two_factor.is_enabled(user_id), 'recovery_left': two_factor.recovery_codes_left(user_id)}
    except Exception as e:
        logger.error(f'No se pudo leer el segundo factor de la cuenta {user_id}: {e}')
        return {'enabled': False, 'recovery_left': 0, 'error': True}


def _passkeys(user_id: int) -> dict[str, Any]:
    """Passkeys de la cuenta; si la tabla falla, la página se muestra igual."""
    try:
        return {'items': passkeys.list_for(user_id)}
    except Exception as e:
        logger.error(f'No se pudieron leer las passkeys de la cuenta {user_id}: {e}')
        return {'items': [], 'error': True}


def _gmail_client_file() -> str:
    """Cliente OAuth "aplicación web" de Google (descargado de la consola de GCP)."""
    return os.getenv('GMAIL_OAUTH_CLIENT_FILE', 'credentials.json')


def render_account(request: Request, **once: Any) -> Response:
    """Página de cuenta. El QR y los códigos de recuperación se muestran una sola vez (no-store)."""
    user_id = _user_id()
    response = render(
        request, 'account.html', user=accounts.get_user(user_id), min_password=accounts.MIN_PASSWORD,
        integ=integrations.status(user_id), telegram_bot=bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        gmail_available=os.path.exists(_gmail_client_file()),
        events=security_events.recent(user_id),
        open_sessions=user_sessions.active(user_id, get_session(request).get('sid')),
        two_factor=_two_factor_status(user_id), totp_setup=once.get('totp_setup'),
        recovery_codes=once.get('recovery_codes'), passkeys=_passkeys(user_id))
    if once:
        response.headers['Cache-Control'] = 'no-store'
    return response


@router.get("/account", name="account")
def account(request: Request) -> Response:
    """Datos de la cuenta, cambio de contraseña y borrado."""
    if not auth.auth_enabled():
        return redirect(request, url_for(request, 'index'))
    return render_account(request)


@router.post("/account/resend_verification", name="resend_verification")
async def resend_verification(request: Request) -> Response:
    """Reenvía el email de verificación."""
    _form_data, error = await _form(request, '3 per hour', 'resend_verification')
    if error:
        return error
    return await run_in_threadpool(_resend_verification, request)


def _resend_verification(request: Request) -> Response:
    """Manda el enlace si el email todavía no está confirmado."""
    user = accounts.get_user(_user_id())
    if user and not user['email_verified']:
        if send_verification(request, user):
            flash(request, 'Te mandamos el enlace de nuevo', 'info')
        else:
            flash(request, 'No se pudo mandar el email: revisá la configuración de SMTP', 'danger')
    return _to_account(request)


@router.post("/account/weekly_digest", name="weekly_digest")
async def weekly_digest(request: Request) -> Response:
    """Prende (enabled=1) o apaga el resumen semanal por email."""
    form, error = await _form(request, '20 per hour', 'weekly_digest')
    if error:
        return error
    user_id = _user_id()
    enabled = form.get('enabled') == '1'
    try:
        await run_in_threadpool(account_lifecycle.set_weekly_digest, user_id, enabled)
    except Exception as e:
        logger.error(f'No se pudo guardar el resumen semanal de la cuenta {user_id}: {e}')
        flash(request, 'No se pudo guardar el cambio: probá de nuevo', 'danger')
        return _to_account(request)
    flash(request, 'Listo: te llega el resumen cada semana' if enabled else 'Listo: no te mandamos más el resumen semanal',
          'success')
    return _to_account(request)


@router.post("/account/ai_consent", name="ai_consent")
async def ai_consent(request: Request) -> Response:
    """Da (granted=1) o quita el permiso para mandar el CV y las ofertas de la cuenta a Gemini."""
    form, error = await _form(request, '20 per hour', 'ai_consent')
    if error:
        return error
    user_id = _user_id()
    granted = form.get('granted') == '1'
    try:
        await run_in_threadpool(accounts.set_ai_consent, user_id, granted)
    except Exception as e:
        logger.error(f'No se pudo guardar el permiso de IA de la cuenta {user_id}: {e}')
        flash(request, 'No se pudo guardar el cambio: probá de nuevo', 'danger')
        return _to_account(request)
    audit(request, user_id, 'ai_consent_given' if granted else 'ai_consent_revoked')
    flash(request, 'Listo: ya podés usar las funciones de IA' if granted
          else 'Listo: no se mandan más datos de tu cuenta a la IA', 'success')
    return redirect(request, safe_next(form.get('next', '')) if form.get('next') else url_for(request, 'account'))


@router.post("/account/password", name="change_password")
async def change_password(request: Request) -> Response:
    """Cambia la contraseña; las otras sesiones se cierran y esta sigue abierta."""
    form, error = await _form(request, '10 per minute', 'change_password')
    if error:
        return error
    return await run_in_threadpool(_change_password, request, form)


def _change_password(request: Request, form: TextForm) -> Response:
    """Comprueba la actual, guarda la nueva y renueva la sesión."""
    user_id = _user_id()
    new = form.get('password', '')
    if new != form.get('confirm', ''):
        flash(request, 'Las contraseñas nuevas no coinciden', 'danger')
        return _to_account(request)
    try:
        accounts.change_password(user_id, form.get('current', ''), new)
    except accounts.AccountError as e:
        flash(request, str(e), 'danger')
        return _to_account(request)
    auth.start_session(get_session(request), web_app_for(request).secret_key, user_id, *client_info(request))
    audit(request, user_id, 'password_changed')
    flash(request, 'Contraseña cambiada; se cerraron las otras sesiones', 'success')
    return _to_account(request)


@router.post("/account/sessions/{session_id}/revoke", name="revoke_session")
async def revoke_session(request: Request, session_id: int) -> Response:
    """Cierra una sesión de la cuenta (si es la actual, también sale)."""
    _form_data, error = await _form(request)
    if error:
        return error
    return await run_in_threadpool(_revoke_session, request, session_id)


def _revoke_session(request: Request, session_id: int) -> Response:
    """Revoca la sesión `session_id` si es de esta cuenta."""
    user_id = _user_id()
    session = get_session(request)
    current = next((s for s in user_sessions.active(user_id, session.get('sid')) if s['current']), None)
    if not user_sessions.revoke(user_id, session_id):
        flash(request, 'Esa sesión ya estaba cerrada', 'warning')
        return _to_account(request)
    audit(request, user_id, 'session_revoked')
    if current and current['id'] == session_id:
        session.clear()
        return clear_offline_data(redirect(request, url_for(request, 'login')))
    flash(request, 'Sesión cerrada', 'success')
    return _to_account(request)


@router.post("/account/sessions/revoke_others", name="revoke_other_sessions")
async def revoke_other_sessions(request: Request) -> Response:
    """Cierra todas las sesiones de la cuenta menos esta."""
    _form_data, error = await _form(request)
    if error:
        return error
    return await run_in_threadpool(_revoke_other_sessions, request)


def _revoke_other_sessions(request: Request) -> Response:
    """Revoca las demás sesiones y avisa cuántas eran."""
    user_id = _user_id()
    closed = user_sessions.revoke_all(user_id, except_sid=get_session(request).get('sid'))
    audit(request, user_id, 'sessions_revoked')
    flash(request, f'Se cerraron {closed} sesiones' if closed != 1 else 'Se cerró 1 sesión', 'success')
    return _to_account(request)


@router.post("/account/export", name="export_data")
async def export_data(request: Request) -> Response:
    """ZIP con todos los datos de la cuenta; pide la contraseña porque incluye los CVs."""
    form, error = await _form(request, '5 per hour', 'export_data')
    if error:
        return error
    return await run_in_threadpool(_export_data, request, form)


def _export_data(request: Request, form: TextForm) -> Response:
    """Arma el ZIP de la cuenta (no-store)."""
    user_id = _user_id()
    if not accounts.check_password(user_id, form.get('password', '')):
        flash(request, 'La contraseña no es correcta', 'danger')
        return _to_account(request)
    try:
        data = data_export.build(user_id)
        audit(request, user_id, 'data_exported')
    except Exception as e:
        logger.error(f'No se pudo exportar la cuenta {user_id}: {e}')
        flash(request, 'No se pudieron exportar tus datos; probá de nuevo', 'danger')
        return _to_account(request)
    return _download(request, data, 'application/zip', f'empleoia-datos-{date.today():%Y%m%d}.zip', no_store=True)


@router.post("/account/delete", name="delete_account")
async def delete_account(request: Request) -> Response:
    """Borra la cuenta y todos sus datos (tracker, perfiles, CVs, alertas, resultados)."""
    form, error = await _form(request, '5 per minute', 'delete_account')
    if error:
        return error
    return await run_in_threadpool(_delete_account, request, form)


def _delete_account(request: Request, form: TextForm) -> Response:
    """Pide la contraseña, borra los CVs y después la cuenta; cierra la sesión."""
    user_id = _user_id()
    if not accounts.check_password(user_id, form.get('password', '')):
        flash(request, 'La contraseña no es correcta: la cuenta no se borró', 'danger')
        return _to_account(request)
    if user_id == accounts.first_user_id() and accounts.count_users() > 1:
        # Telegram, Gmail y la extensión son de la primera cuenta: pasarían a la siguiente
        flash(request, 'La primera cuenta (administradora) no se puede borrar mientras haya otras cuentas', 'danger')
        return _to_account(request)
    if not services_for(request).profiles.delete_user_profile():
        flash(request, 'No se pudieron borrar tus CVs: la cuenta no se borró', 'danger')
        return _to_account(request)
    try:
        account_lifecycle.delete_account(user_id)
    except Exception as e:
        logger.error(f'No se pudo borrar la cuenta {user_id}: {e}')
        flash(request, 'No se pudo borrar la cuenta; probá de nuevo', 'danger')
        return _to_account(request)
    session = get_session(request)
    session.clear()
    flash(request, 'Tu cuenta y todos tus datos se borraron', 'success')
    return clear_offline_data(redirect(request, url_for(request, 'login')))


# ─── Segundo factor desde Mi cuenta ──────────────────────────────────────────


# ─── Administración ──────────────────────────────────────────────────────────


# ─── Exportar el tracker y los resultados ────────────────────────────────────


# ─── Passkeys ────────────────────────────────────────────────────────────────


