"""Mi cuenta: Telegram, extensión de Chrome y Gmail."""
import logging
import os
import re
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

import auth
import integrations
from fastapi_web import TextForm, flash, get_session, public_url, redirect, render
from routers.auth_pages import audit
from routers.account_pages import _form, _gmail_client_file, _not_found, _to_account, _user_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"], include_in_schema=False)


@router.post("/account/telegram", name="save_telegram")
async def save_telegram(request: Request) -> Response:
    """Guarda el chat de Telegram de la cuenta (vacío lo desconecta)."""
    form, error = await _form(request)
    if error:
        return error
    return await run_in_threadpool(_save_telegram, request, form)


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
async def test_telegram(request: Request) -> Response:
    """Manda un mensaje de prueba al chat de la cuenta."""
    _form_data, error = await _form(request, '5 per minute', 'test_telegram')
    if error:
        return error
    return await run_in_threadpool(_test_telegram, request)


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
def link_extension(request: Request) -> Response:
    """Confirmación para vincular la extensión que abrió esta pestaña."""
    state = request.query_params.get('state', '')
    if not auth.auth_enabled() or not EXTENSION_STATE.match(state):
        return _not_found(request)
    return _extension_page(request, state)


@router.post("/account/extension/link", name="confirm_link_extension")
async def confirm_link_extension(request: Request) -> Response:
    """Genera el token de la extensión (reemplaza al anterior) y se lo pasa en la página, no en la URL."""
    form, error = await _form(request, '5 per minute', 'new_extension_token')
    if error:
        return error
    return await run_in_threadpool(_confirm_link_extension, request, form)


def _confirm_link_extension(request: Request, form: TextForm) -> Response:
    """La extensión lee el token de la página que carga en su pestaña, si el state coincide."""
    state = form.get('state', '')
    if not EXTENSION_STATE.match(state):
        return _not_found(request)
    token = integrations.new_extension_token(_user_id())
    audit(request, _user_id(), 'extension_linked')
    return _extension_page(request, state, token)


@router.post("/account/extension_token/revoke", name="revoke_extension_token")
async def revoke_extension_token(request: Request) -> Response:
    """Revoca el token de la extensión."""
    _form_data, error = await _form(request)
    if error:
        return error
    return await run_in_threadpool(_revoke_extension_token, request)


def _revoke_extension_token(request: Request) -> Response:
    """Borra el token y registra el evento."""
    integrations.revoke_extension_token(_user_id())
    audit(request, _user_id(), 'extension_token_revoked')
    flash(request, 'Extensión desvinculada', 'success')
    return _to_account(request)


def _gmail_flow(request: Request, state: Optional[str] = None) -> Any:
    """Flujo OAuth web para conectar Gmail, o None si falta el cliente o la URL pública."""
    from tasks.gmail_tracker import SCOPES
    redirect_uri = public_url(request, 'gmail_callback')
    if not redirect_uri or not os.path.exists(_gmail_client_file()):
        return None
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_secrets_file(_gmail_client_file(), scopes=SCOPES, state=state, redirect_uri=redirect_uri)


@router.post("/account/gmail/connect", name="gmail_connect")
async def gmail_connect(request: Request) -> Response:
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
def gmail_callback(request: Request) -> Response:
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
async def gmail_disconnect(request: Request) -> Response:
    """Desconecta Gmail de la cuenta."""
    _form_data, error = await _form(request)
    if error:
        return error
    return await run_in_threadpool(_gmail_disconnect, request)


def _gmail_disconnect(request: Request) -> Response:
    """Borra el token de Gmail y registra el evento."""
    integrations.clear_gmail(_user_id())
    audit(request, _user_id(), 'gmail_disconnected')
    flash(request, 'Gmail desconectado', 'success')
    return _to_account(request)
