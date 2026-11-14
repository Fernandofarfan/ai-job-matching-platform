"""Mi cuenta (integraciones, contraseña, sesiones, exportar y borrar), en FastAPI.

Segundo factor y passkeys en security_pages.py, Administración en admin_pages.py y Excel/PDF en export_pages.py.

Los nombres de ruta son los endpoints que usaba Flask; los límites usan rate_limit (fastapi_web.hit_limit)
con la misma clave por cuenta.
"""
import logging
import os
import re
from datetime import date
from typing import Optional, cast
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

import accounts
import auth
import data_export
import integrations
import security_events
import passkeys
import two_factor
import user_sessions
from fastapi_web import (TextForm, clear_offline_data, client_info, flash, web_app_for, get_session, hit_limit, services_for,
                         limit_key, public_url, read_form, redirect, render, safe_next, save_session,
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

def _two_factor_status(user_id) -> dict:
    """Estado del segundo factor para la página; si la tabla falla, la página se muestra igual."""
    try:
        return {'enabled': two_factor.is_enabled(user_id), 'recovery_left': two_factor.recovery_codes_left(user_id)}
    except Exception as e:
        logger.error(f'No se pudo leer el segundo factor de la cuenta {user_id}: {e}')
        return {'enabled': False, 'recovery_left': 0, 'error': True}


def _passkeys(user_id) -> dict:
    """Passkeys de la cuenta; si la tabla falla, la página se muestra igual."""
    try:
        return {'items': passkeys.list_for(user_id)}
    except Exception as e:
        logger.error(f'No se pudieron leer las passkeys de la cuenta {user_id}: {e}')
        return {'items': [], 'error': True}


def _gmail_client_file() -> str:
    """Cliente OAuth "aplicación web" de Google (descargado de la consola de GCP)."""
    return os.getenv('GMAIL_OAUTH_CLIENT_FILE', 'credentials.json')


def render_account(request: Request, **once) -> Response:
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
def account(request: Request):
    """Datos de la cuenta, cambio de contraseña y borrado."""
    if not auth.auth_enabled():
        return redirect(request, url_for(request, 'index'))
    return render_account(request)


@router.post("/account/telegram", name="save_telegram")
async def save_telegram(request: Request):
    """Guarda el chat de Telegram de la cuenta (vacío lo desconecta)."""
    form, error = await _form(request)
    return error or await run_in_threadpool(_save_telegram, request, form)


def _save_telegram(request: Request, form: TextForm) -> Response:
    """Guarda el chat y registra el cambio."""
    try:
        integrations.set_telegram_chat(_user_id(), form.get('chat_id', ''))
    except integrations.IntegrationError as e:
        flash(request, str(e), 'danger')
    else:
        audit(request, _user_id(), 'telegram_changed')
        flash(request, 'Chat de Telegram guardado', 'success')
    return _to_account(request)


@router.post("/account/telegram/test", name="test_telegram")
async def test_telegram(request: Request):
    """Manda un mensaje de prueba al chat de la cuenta."""
    _form_data, error = await _form(request, '5 per minute', 'test_telegram')
    return error or await run_in_threadpool(_test_telegram, request)


def _test_telegram(request: Request) -> Response:
    """Mensaje de prueba por el bot."""
    from tasks.notification_tasks import send_telegram
    if send_telegram('✅ EmpleoIA: tus avisos van a llegar a este chat'):
        flash(request, 'Mensaje de prueba enviado', 'success')
    else:
        flash(request, 'No se pudo mandar: revisá el chat ID y que le hayas escrito /start al bot', 'danger')
    return _to_account(request)


# Lo genera la extensión (chrome_extension/link.js); solo ella sabe qué state espera
EXTENSION_STATE = re.compile(r'^[A-Za-z0-9_-]{16,128}$')


def _extension_page(request: Request, state: str, token: Optional[str] = None) -> Response:
    response = render(request, 'extension_link.html', state=state, token=token)
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get("/account/extension/link", name="link_extension")
def link_extension(request: Request):
    """Confirmación para vincular la extensión que abrió esta pestaña."""
    state = request.query_params.get('state', '')
    if not auth.auth_enabled() or not EXTENSION_STATE.match(state):
        return _not_found(request)
    return _extension_page(request, state)


@router.post("/account/extension/link", name="confirm_link_extension")
async def confirm_link_extension(request: Request):
    """Genera el token de la extensión (reemplaza al anterior) y se lo pasa en la página, no en la URL."""
    form, error = await _form(request, '5 per minute', 'new_extension_token')
    return error or await run_in_threadpool(_confirm_link_extension, request, form)


def _confirm_link_extension(request: Request, form: TextForm) -> Response:
    """La extensión lee el token de la página que carga en su pestaña, si el state coincide."""
    state = form.get('state', '')
    if not EXTENSION_STATE.match(state):
        return _not_found(request)
    token = integrations.new_extension_token(_user_id())
    audit(request, _user_id(), 'extension_linked')
    return _extension_page(request, state, token)


@router.post("/account/extension_token/revoke", name="revoke_extension_token")
async def revoke_extension_token(request: Request):
    """Revoca el token de la extensión."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_revoke_extension_token, request)


def _revoke_extension_token(request: Request) -> Response:
    """Borra el token y registra el evento."""
    integrations.revoke_extension_token(_user_id())
    audit(request, _user_id(), 'extension_token_revoked')
    flash(request, 'Extensión desvinculada', 'success')
    return _to_account(request)


def _gmail_flow(request: Request, state=None):
    """Flujo OAuth web para conectar Gmail, o None si falta el cliente o la URL pública."""
    from tasks.gmail_tracker import SCOPES
    redirect_uri = public_url(request, 'gmail_callback')
    if not redirect_uri or not os.path.exists(_gmail_client_file()):
        return None
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_secrets_file(_gmail_client_file(), scopes=SCOPES, state=state, redirect_uri=redirect_uri)


@router.post("/account/gmail/connect", name="gmail_connect")
async def gmail_connect(request: Request):
    """Manda a Google para autorizar la lectura de Gmail de esta cuenta."""
    _form_data, error = await _form(request)
    if error:
        return error
    flow = await run_in_threadpool(_gmail_flow, request)
    if flow is None:
        flash(request, 'Gmail no está disponible: falta el cliente OAuth o PUBLIC_BASE_URL', 'danger')
        return _to_account(request)
    url, state = flow.authorization_url(access_type='offline', prompt='consent')
    get_session(request)['gmail_oauth'] = {'state': state, 'verifier': getattr(flow, 'code_verifier', None)}
    return redirect(request, url)


@router.get("/account/gmail/callback", name="gmail_callback")
def gmail_callback(request: Request):
    """Vuelta de Google: guarda el token de Gmail de la cuenta."""
    pending = get_session(request).pop('gmail_oauth', None) or {}
    state = request.query_params.get('state', '')
    code = request.query_params.get('code')
    if not pending.get('state') or state != pending['state'] or not code:
        flash(request, 'No se pudo conectar Gmail: volvé a intentarlo', 'danger')
        return _to_account(request)
    flow = _gmail_flow(request, state)
    if flow is None:
        return _to_account(request)
    flow.code_verifier = pending.get('verifier')
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error(f'Google rechazó el código de Gmail: {type(e).__name__}')
        flash(request, 'No se pudo conectar Gmail: volvé a intentarlo', 'danger')
        return _to_account(request)
    integrations.save_gmail_token(_user_id(), flow.credentials.to_json())
    audit(request, _user_id(), 'gmail_connected')
    flash(request, 'Gmail conectado: las invitaciones a entrevistas van a actualizar tu tracker', 'success')
    return _to_account(request)


@router.post("/account/gmail/disconnect", name="gmail_disconnect")
async def gmail_disconnect(request: Request):
    """Desconecta Gmail de la cuenta."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_gmail_disconnect, request)


def _gmail_disconnect(request: Request) -> Response:
    """Borra el token de Gmail y registra el evento."""
    integrations.clear_gmail(_user_id())
    audit(request, _user_id(), 'gmail_disconnected')
    flash(request, 'Gmail desconectado', 'success')
    return _to_account(request)


@router.post("/account/resend_verification", name="resend_verification")
async def resend_verification(request: Request):
    """Reenvía el email de verificación."""
    _form_data, error = await _form(request, '3 per hour', 'resend_verification')
    return error or await run_in_threadpool(_resend_verification, request)


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
async def weekly_digest(request: Request):
    """Prende (enabled=1) o apaga el resumen semanal por email."""
    form, error = await _form(request, '20 per hour', 'weekly_digest')
    if error:
        return error
    user_id = _user_id()
    enabled = form.get('enabled') == '1'
    try:
        await run_in_threadpool(accounts.set_weekly_digest, user_id, enabled)
    except Exception as e:
        logger.error(f'No se pudo guardar el resumen semanal de la cuenta {user_id}: {e}')
        flash(request, 'No se pudo guardar el cambio: probá de nuevo', 'danger')
        return _to_account(request)
    flash(request, 'Listo: te llega el resumen cada semana' if enabled else 'Listo: no te mandamos más el resumen semanal',
          'success')
    return _to_account(request)


@router.post("/account/ai_consent", name="ai_consent")
async def ai_consent(request: Request):
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
async def change_password(request: Request):
    """Cambia la contraseña; las otras sesiones se cierran y esta sigue abierta."""
    form, error = await _form(request, '10 per minute', 'change_password')
    return error or await run_in_threadpool(_change_password, request, form)


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
async def revoke_session(request: Request, session_id: int):
    """Cierra una sesión de la cuenta (si es la actual, también sale)."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_revoke_session, request, session_id)


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
async def revoke_other_sessions(request: Request):
    """Cierra todas las sesiones de la cuenta menos esta."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_revoke_other_sessions, request)


def _revoke_other_sessions(request: Request) -> Response:
    """Revoca las demás sesiones y avisa cuántas eran."""
    user_id = _user_id()
    closed = user_sessions.revoke_all(user_id, except_sid=get_session(request).get('sid'))
    audit(request, user_id, 'sessions_revoked')
    flash(request, f'Se cerraron {closed} sesiones' if closed != 1 else 'Se cerró 1 sesión', 'success')
    return _to_account(request)


@router.post("/account/export", name="export_data")
async def export_data(request: Request):
    """ZIP con todos los datos de la cuenta; pide la contraseña porque incluye los CVs."""
    form, error = await _form(request, '5 per hour', 'export_data')
    return error or await run_in_threadpool(_export_data, request, form)


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
async def delete_account(request: Request):
    """Borra la cuenta y todos sus datos (tracker, perfiles, CVs, alertas, resultados)."""
    form, error = await _form(request, '5 per minute', 'delete_account')
    return error or await run_in_threadpool(_delete_account, request, form)


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
        accounts.delete_account(user_id)
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


