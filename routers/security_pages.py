"""Segundo factor (TOTP y códigos de recuperación) y passkeys de Mi cuenta, en FastAPI."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool

import accounts
import passkeys
import two_factor
from fastapi_web import (TextForm, flash, get_session, limit_key, save_session)
from routers.auth_pages import audit, passkey_json, request_origin
from routers.account_pages import _form, _to_account, _user_id, render_account

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account"], include_in_schema=False)


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
    user_id = _user_id()
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
    user_id = _user_id()
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
    user_id = _user_id()
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
    user_id = _user_id()
    if not _confirm_identity(request, user_id, form):
        return _to_account(request)
    codes = two_factor.regenerate_recovery_codes(user_id)
    audit(request, user_id, 'recovery_codes_regenerated')
    return render_account(request, recovery_codes=codes)


@router.post("/account/passkeys/options", name="passkey_options")
async def passkey_options(request: Request):
    """Desafío para registrar una passkey; pide la contraseña, como el segundo factor."""
    data, error = await passkey_json(request, '5 per minute', 'passkey_options', limit_key(request))
    return error or await run_in_threadpool(_passkey_options, request, data or {})


def _passkey_options(request: Request, data: dict) -> Response:
    """Comprueba la contraseña y devuelve las opciones de `navigator.credentials.create`."""
    user_id = _user_id()
    user = accounts.get_user(user_id)
    if user is None or not accounts.check_password(user_id, str(data.get('password') or '')):
        return JSONResponse({'error': 'La contraseña no es correcta'}, status_code=400)
    challenge = passkeys.new_challenge(get_session(request), 'register', user_id)
    return save_session(request, Response(
        passkeys.registration_options(user_id, user['email'], request_origin(request), challenge),
        media_type='application/json'))


@router.post("/account/passkeys", name="passkey_register")
async def passkey_register(request: Request):
    """Guarda la passkey que creó el navegador."""
    data, error = await passkey_json(request, '10 per minute', 'passkey_register', limit_key(request))
    return error or await run_in_threadpool(_passkey_register, request, data or {})


def _passkey_register(request: Request, data: dict) -> Response:
    """Verifica la respuesta del navegador con el desafío de la sesión."""
    user_id = _user_id()
    challenge = passkeys.take_challenge(get_session(request), 'register', user_id)
    if challenge is None:
        return save_session(request, JSONResponse({'error': 'El pedido venció: probá de nuevo'}, status_code=400))
    try:
        saved = passkeys.register(user_id, data.get('credential') or {}, challenge, request_origin(request),
                                  str(data.get('name') or ''))
    except passkeys.PasskeyError as e:
        return save_session(request, JSONResponse({'error': str(e)}, status_code=400))
    audit(request, user_id, 'passkey_added')
    flash(request, 'Passkey agregada', 'success')
    return save_session(request, JSONResponse({'success': True, 'passkey': saved}))


@router.post("/account/passkeys/{passkey_id}/delete", name="passkey_delete")
async def passkey_delete(request: Request, passkey_id: int):
    """Borra una passkey de la cuenta."""
    form, error = await _form(request, '10 per minute', 'passkey_delete')
    return error or await run_in_threadpool(_passkey_delete, request, passkey_id)


def _passkey_delete(request: Request, passkey_id: int) -> Response:
    """Solo borra passkeys de la cuenta actual."""
    user_id = _user_id()
    if passkeys.delete(user_id, passkey_id):
        audit(request, user_id, 'passkey_removed')
        flash(request, 'Passkey borrada', 'success')
    else:
        flash(request, 'Esa passkey no existe', 'warning')
    return _to_account(request)
