"""Mi cuenta (integraciones, contraseña, sesiones, segundo factor, exportar y borrar), Administración y
exportación a Excel/PDF, en FastAPI.

Los nombres de ruta son los endpoints que usaba Flask; los límites usan rate_limit (fastapi_web.hit_limit)
con la misma clave por cuenta.
"""
import logging
import os
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool

import accounts
import ai_usage
import auth
import data_export
import integrations
import security_events
import tracker_export
import two_factor
import user_sessions
from fastapi_web import (TextForm, clear_offline_data, client_info, flash, web_app_for, get_session, hit_limit, services_for,
                         limit_key, public_url, read_form, redirect, render, safe_next, save_session,
                         too_many_requests, url_for)
from routers.auth_pages import audit, send_verification

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"], include_in_schema=False)


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


def _gmail_client_file() -> str:
    """Cliente OAuth "aplicación web" de Google (descargado de la consola de GCP)."""
    return os.getenv('GMAIL_OAUTH_CLIENT_FILE', 'credentials.json')


def render_account(request: Request, new_token=None, **once) -> Response:
    """Página de cuenta. `new_token`, el QR y los códigos de recuperación se muestran una sola vez (no-store)."""
    user_id = accounts.require_user_id()
    response = render(
        request, 'account.html', user=accounts.get_user(user_id), min_password=accounts.MIN_PASSWORD,
        integ=integrations.status(user_id), telegram_bot=bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        gmail_available=os.path.exists(_gmail_client_file()), new_token=new_token,
        events=security_events.recent(user_id),
        open_sessions=user_sessions.active(user_id, get_session(request).get('sid')),
        two_factor=_two_factor_status(user_id), totp_setup=once.get('totp_setup'),
        recovery_codes=once.get('recovery_codes'))
    if new_token or once:
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
        integrations.set_telegram_chat(accounts.require_user_id(), form.get('chat_id', ''))
    except integrations.IntegrationError as e:
        flash(request, str(e), 'danger')
    else:
        audit(request, accounts.require_user_id(), 'telegram_changed')
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


@router.post("/account/extension_token", name="new_extension_token")
async def new_extension_token(request: Request):
    """Genera el token de la extensión de Chrome para esta cuenta (reemplaza al anterior)."""
    _form_data, error = await _form(request, '5 per minute', 'new_extension_token')
    return error or await run_in_threadpool(_new_extension_token, request)


def _new_extension_token(request: Request) -> Response:
    """Token nuevo, mostrado una sola vez."""
    token = integrations.new_extension_token(accounts.require_user_id())
    audit(request, accounts.require_user_id(), 'extension_token_created')
    return render_account(request, new_token=token)


@router.post("/account/extension_token/revoke", name="revoke_extension_token")
async def revoke_extension_token(request: Request):
    """Revoca el token de la extensión."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_revoke_extension_token, request)


def _revoke_extension_token(request: Request) -> Response:
    """Borra el token y registra el evento."""
    integrations.revoke_extension_token(accounts.require_user_id())
    audit(request, accounts.require_user_id(), 'extension_token_revoked')
    flash(request, 'Token de la extensión revocado', 'success')
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
    integrations.save_gmail_token(accounts.require_user_id(), flow.credentials.to_json())
    audit(request, accounts.require_user_id(), 'gmail_connected')
    flash(request, 'Gmail conectado: las invitaciones a entrevistas van a actualizar tu tracker', 'success')
    return _to_account(request)


@router.post("/account/gmail/disconnect", name="gmail_disconnect")
async def gmail_disconnect(request: Request):
    """Desconecta Gmail de la cuenta."""
    _form_data, error = await _form(request)
    return error or await run_in_threadpool(_gmail_disconnect, request)


def _gmail_disconnect(request: Request) -> Response:
    """Borra el token de Gmail y registra el evento."""
    integrations.clear_gmail(accounts.require_user_id())
    audit(request, accounts.require_user_id(), 'gmail_disconnected')
    flash(request, 'Gmail desconectado', 'success')
    return _to_account(request)


@router.post("/account/resend_verification", name="resend_verification")
async def resend_verification(request: Request):
    """Reenvía el email de verificación."""
    _form_data, error = await _form(request, '3 per hour', 'resend_verification')
    return error or await run_in_threadpool(_resend_verification, request)


def _resend_verification(request: Request) -> Response:
    """Manda el enlace si el email todavía no está confirmado."""
    user = accounts.get_user(accounts.require_user_id())
    if user and not user['email_verified']:
        if send_verification(request, user):
            flash(request, 'Te mandamos el enlace de nuevo', 'info')
        else:
            flash(request, 'No se pudo mandar el email: revisá la configuración de SMTP', 'danger')
    return _to_account(request)


@router.post("/account/ai_consent", name="ai_consent")
async def ai_consent(request: Request):
    """Da (granted=1) o quita el permiso para mandar el CV y las ofertas de la cuenta a Gemini."""
    form, error = await _form(request, '20 per hour', 'ai_consent')
    if error:
        return error
    user_id = accounts.require_user_id()
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
    user_id = accounts.require_user_id()
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
    user_id = accounts.require_user_id()
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
    user_id = accounts.require_user_id()
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
    user_id = accounts.require_user_id()
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
    user_id = accounts.require_user_id()
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

def _setup_context(user_id: int) -> dict:
    """QR y secreto de una configuración empezada."""
    secret = two_factor.pending_secret(user_id)
    user = accounts.get_user(user_id)
    if not secret or not user:
        return {}
    uri = two_factor.provisioning_uri(user['email'], secret)
    return {'totp_setup': {'secret': secret, 'qr': Markup(two_factor.qr_svg(uri))}}


@router.post("/account/2fa/setup", name="two_factor_setup")
async def two_factor_setup(request: Request):
    """Genera el secreto y muestra el QR para escanear."""
    form, error = await _form(request, '5 per minute', 'two_factor_setup')
    return error or await run_in_threadpool(_two_factor_setup, request, form)


def _two_factor_setup(request: Request, form: TextForm) -> Response:
    """Pide la contraseña antes de empezar la configuración."""
    user_id = accounts.require_user_id()
    if not accounts.check_password(user_id, form.get('password', '')):
        flash(request, 'La contraseña no es correcta', 'danger')
        return _to_account(request)
    try:
        two_factor.start_setup(user_id)
    except two_factor.TwoFactorError as e:
        flash(request, str(e), 'warning')
        return _to_account(request)
    return render_account(request, **_setup_context(user_id))


@router.post("/account/2fa/enable", name="two_factor_enable")
async def two_factor_enable(request: Request):
    """Activa el segundo factor con un código de la app y muestra los códigos de recuperación una vez."""
    form, error = await _form(request, '10 per minute', 'two_factor_enable')
    return error or await run_in_threadpool(_two_factor_enable, request, form)


def _two_factor_enable(request: Request, form: TextForm) -> Response:
    """Comprueba el primer código y activa el segundo factor."""
    user_id = accounts.require_user_id()
    codes = two_factor.enable(user_id, form.get('code', '').strip())
    if not codes:
        flash(request, 'El código no es correcto: revisá la hora del teléfono y probá con el siguiente', 'danger')
        return render_account(request, **_setup_context(user_id))
    audit(request, user_id, 'two_factor_enabled')
    flash(request, 'Verificación en dos pasos activada', 'success')
    return render_account(request, recovery_codes=codes)


def _confirm_identity(request: Request, user_id: int, form: TextForm) -> bool:
    """Contraseña y código actuales (desactivar o ver códigos nuevos pide los dos)."""
    if not accounts.check_password(user_id, form.get('password', '')):
        flash(request, 'La contraseña no es correcta', 'danger')
        return False
    if not two_factor.verify(user_id, form.get('code', '').strip()):
        audit(request, user_id, 'two_factor_failed')
        flash(request, 'El código no es correcto', 'danger')
        return False
    return True


@router.post("/account/2fa/disable", name="two_factor_disable")
async def two_factor_disable(request: Request):
    """Desactiva el segundo factor."""
    form, error = await _form(request, '5 per minute', 'two_factor_disable')
    return error or await run_in_threadpool(_two_factor_disable, request, form)


def _two_factor_disable(request: Request, form: TextForm) -> Response:
    """Con contraseña y código, quita el segundo factor."""
    user_id = accounts.require_user_id()
    if _confirm_identity(request, user_id, form):
        two_factor.disable(user_id)
        audit(request, user_id, 'two_factor_disabled')
        flash(request, 'Verificación en dos pasos desactivada', 'success')
    return _to_account(request)


@router.post("/account/2fa/recovery", name="two_factor_recovery")
async def two_factor_recovery(request: Request):
    """Genera códigos de recuperación nuevos; los anteriores dejan de valer."""
    form, error = await _form(request, '5 per minute', 'two_factor_recovery')
    return error or await run_in_threadpool(_two_factor_recovery, request, form)


def _two_factor_recovery(request: Request, form: TextForm) -> Response:
    """Con contraseña y código, muestra códigos nuevos una sola vez."""
    user_id = accounts.require_user_id()
    if not _confirm_identity(request, user_id, form):
        return _to_account(request)
    codes = two_factor.regenerate_recovery_codes(user_id)
    audit(request, user_id, 'recovery_codes_regenerated')
    return render_account(request, recovery_codes=codes)


# ─── Administración ──────────────────────────────────────────────────────────

def _admin_id() -> Optional[int]:
    """Id del administrador, o None para cualquier otra cuenta (que recibe 404)."""
    user_id = accounts.require_user_id()
    return user_id if auth.auth_enabled() and user_id is not None and accounts.is_admin(user_id) else None


def _target(request: Request, admin_id: int, user_id: int) -> Optional[dict]:
    """Cuenta sobre la que se actúa; None (con aviso) si es la propia o la administradora."""
    target = accounts.get_user(user_id)
    if target is None:
        return None
    if user_id in (admin_id, accounts.first_user_id()) or accounts.is_admin(user_id):
        flash(request, 'La cuenta administradora se gestiona desde Mi cuenta', 'warning')
        return None
    return target


def _password_ok(request: Request, admin_id: int, form: TextForm) -> bool:
    """Las acciones irreversibles piden la contraseña del administrador."""
    if accounts.check_password(admin_id, form.get('password', '')):
        return True
    flash(request, 'La contraseña no es correcta', 'danger')
    return False


def _to_admin(request: Request) -> Response:
    """Vuelta al panel de administración."""
    return redirect(request, url_for(request, 'admin_panel'))


@router.get("/admin", name="admin_panel")
def admin_panel(request: Request):
    """Lista de cuentas con estado, segundo factor, última actividad y consumo de IA del mes."""
    if _admin_id() is None:
        return _not_found(request)
    users = accounts.list_users()
    try:
        with_two_factor = two_factor.enabled_user_ids()
        last_seen = user_sessions.last_seen_by_user()
    except Exception as e:
        logger.error(f'No se pudo leer el detalle de las cuentas: {e}')
        with_two_factor, last_seen = set(), {}
    for user in users:
        user['two_factor'] = user['id'] in with_two_factor
        user['last_seen'] = last_seen.get(user['id'])
        user['ai'] = ai_usage.account_usage(user['id'])
        user['is_admin'] = accounts.is_admin(user['id'])
    response = render(request, 'admin.html', users=users, signup_open=accounts.signup_open(),
                      usage=ai_usage.summary(), user_limit=ai_usage.user_monthly_limit())
    response.headers['Cache-Control'] = 'no-store'
    return response


async def _admin_action(request: Request, user_id: int, spec: str, namespace: str, action) -> Response:
    """CSRF, 404 para quien no administra, límite y `action(request, admin_id, target, form)` fuera del event loop."""
    form, error = await read_form(request)
    if error:
        return error
    admin_id = await run_in_threadpool(_admin_id)
    if admin_id is None:
        return _not_found(request)
    if not hit_limit(request, spec, namespace, limit_key(request)):
        return too_many_requests()

    def run() -> Response:
        """Busca la cuenta y aplica la acción."""
        if accounts.get_user(user_id) is None:
            return _not_found(request)
        target = _target(request, admin_id, user_id)
        if target:
            action(request, admin_id, target, form)
        return _to_admin(request)
    return await run_in_threadpool(run)


def _block(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Bloquea la cuenta: no entra, sus sesiones se cierran y no recibe avisos."""
    if accounts.set_disabled(target['id'], True):
        audit(request, target['id'], 'account_blocked')
        flash(request, f"{target['email']} quedó bloqueada", 'success')


def _unblock(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Desbloquea la cuenta."""
    if accounts.set_disabled(target['id'], False):
        audit(request, target['id'], 'account_unblocked')
        flash(request, f"{target['email']} quedó desbloqueada", 'success')


def _reset_two_factor(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Quita la verificación en dos pasos de quien perdió el teléfono y los códigos."""
    if _password_ok(request, admin_id, form):
        two_factor.disable(target['id'])
        audit(request, target['id'], 'two_factor_reset')
        flash(request, f"{target['email']} ya puede entrar solo con la contraseña", 'success')


def _delete(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Borra la cuenta y todos sus datos, igual que "Borrar mi cuenta"."""
    if not _password_ok(request, admin_id, form):
        return
    with accounts.as_user(target['id']):
        removed = services_for(request).profiles.delete_user_profile()
    if not removed:
        flash(request, 'No se pudieron borrar los CVs: la cuenta no se borró', 'danger')
        return
    try:
        accounts.delete_account(target['id'])
    except Exception as e:
        logger.error(f"No se pudo borrar la cuenta {target['id']}: {e}")
        flash(request, 'No se pudo borrar la cuenta; probá de nuevo', 'danger')
        return
    audit(request, admin_id, 'admin_deleted_account')
    flash(request, f"{target['email']} y todos sus datos se borraron", 'success')


@router.post("/admin/users/{user_id}/block", name="admin_block")
async def admin_block(request: Request, user_id: int):
    """Bloquea la cuenta."""
    return await _admin_action(request, user_id, '30 per minute', 'admin_block', _block)


@router.post("/admin/users/{user_id}/unblock", name="admin_unblock")
async def admin_unblock(request: Request, user_id: int):
    """Desbloquea la cuenta."""
    return await _admin_action(request, user_id, '30 per minute', 'admin_unblock', _unblock)


@router.post("/admin/users/{user_id}/2fa/reset", name="admin_reset_two_factor")
async def admin_reset_two_factor(request: Request, user_id: int):
    """Quita la verificación en dos pasos (pide la contraseña del administrador)."""
    return await _admin_action(request, user_id, '10 per minute', 'admin_reset_two_factor', _reset_two_factor)


@router.post("/admin/users/{user_id}/delete", name="admin_delete")
async def admin_delete(request: Request, user_id: int):
    """Borra la cuenta y sus datos (pide la contraseña del administrador)."""
    return await _admin_action(request, user_id, '10 per minute', 'admin_delete', _delete)


# ─── Exportar el tracker y los resultados ────────────────────────────────────

def _stamp() -> str:
    """Fecha y hora para el nombre del archivo."""
    return datetime.now().strftime('%Y%m%d_%H%M')


@router.get("/export/tracker/excel", name="export_tracker_excel")
def export_tracker_excel(request: Request):
    """Exporta el tracker de la cuenta a Excel (.xlsx)."""
    try:
        data = tracker_export.tracker_excel(services_for(request).db.get_all_tracked_jobs())
    except Exception as e:
        logger.error(f'Error exporting tracker to Excel: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'tracker'))
    return _download(request, data, tracker_export.XLSX, f'EmpleoIA_Tracker_{_stamp()}.xlsx')


@router.get("/export/tracker/pdf", name="export_tracker_pdf")
def export_tracker_pdf(request: Request):
    """Exporta el tracker de la cuenta a PDF."""
    try:
        data = tracker_export.tracker_pdf(services_for(request).db.get_all_tracked_jobs())
    except Exception as e:
        logger.error(f'Error exporting tracker to PDF: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'tracker'))
    return _download(request, data, 'application/pdf', f'EmpleoIA_Tracker_{_stamp()}.pdf')


@router.get("/export/results/{filename}/excel", name="export_results_excel")
def export_results_excel(request: Request, filename: str):
    """Exporta un CSV de resultados de la cuenta como Excel."""
    path = os.path.join(accounts.results_dir(), filename)
    if filename != os.path.basename(filename) or not filename.endswith('.csv') or not os.path.isfile(path):
        flash(request, 'Archivo no encontrado', 'danger')
        return redirect(request, url_for(request, 'results'))
    try:
        data = tracker_export.results_excel(path)
    except Exception as e:
        logger.error(f'Error exporting results to Excel: {e}')
        flash(request, 'No se pudo exportar; probá de nuevo', 'danger')
        return redirect(request, url_for(request, 'results'))
    return _download(request, data, tracker_export.XLSX, f'{filename[:-4]}_export.xlsx')
