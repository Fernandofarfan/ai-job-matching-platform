"""Entrar con una passkey o con Google (la cuenta y la sesión las abre auth_pages.begin_login)."""
import json
import logging
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

import accounts
import auth
import google_oauth
import passkeys
from fastapi_web import (_body_within, _csrf_ok, save_session, client_info, client_ip, flash, get_session,
                         hit_limit, limit_key, public_url, redirect, safe_next,
                         too_many_requests, url_for)
from routers.auth_pages import _audit_login, _finish_login, _secret, audit, begin_login

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"], include_in_schema=False)


def request_origin(request: Request) -> str:
    """Origen que ve el navegador (sin proxy); passkeys.origin prefiere WEBAUTHN_ORIGIN o APP_BASE_URL."""
    return passkeys.origin(f'{request.url.scheme}://{request.url.netloc}')


async def passkey_json(request: Request, limit: str, namespace: str,
                       key: str) -> tuple[Optional[dict[str, Any]], Optional[Response]]:
    """(cuerpo JSON, error): límite de tamaño, CSRF por header y límite de pedidos."""
    if not await _body_within(request, 64 * 1024):
        return None, JSONResponse({'error': 'Pedido demasiado grande'}, status_code=413)
    if not _csrf_ok(request, None):
        return None, JSONResponse({'error': 'Token CSRF inválido o vencido: recargá la página'}, status_code=400)
    if not hit_limit(request, limit, namespace, key):
        return None, JSONResponse({'error': 'Demasiados intentos: esperá un momento'}, status_code=429)
    try:
        data = json.loads(await request.body() or b'{}')
    except ValueError:
        return None, JSONResponse({'error': 'JSON inválido'}, status_code=400)
    if not isinstance(data, dict):
        return None, JSONResponse({'error': 'JSON inválido'}, status_code=400)
    return data, None


@router.post("/login/passkey/options", name="passkey_login_options")
async def passkey_login_options(request: Request) -> Response:
    """Desafío para entrar con una passkey del dispositivo."""
    _, error = await passkey_json(request, '20 per minute', 'passkey_login', client_ip(request))
    if error:
        return error
    return await run_in_threadpool(_passkey_login_options, request)


def _passkey_login_options(request: Request) -> Response:
    """Guarda el desafío en la base (fuera del event loop) y arma las opciones."""
    site = request_origin(request)
    challenge = passkeys.new_challenge(get_session(request), 'login')
    return save_session(request, Response(passkeys.authentication_options(site, challenge),
                                          media_type='application/json'))


@router.post("/login/passkey", name="passkey_login")
async def passkey_login(request: Request) -> Response:
    """Comprueba la firma de la passkey y abre la sesión (la passkey ya verificó al usuario: sin código)."""
    data, error = await passkey_json(request, '10 per minute', 'passkey_login_finish', client_ip(request))
    if error:
        return error
    return await run_in_threadpool(_passkey_login, request, data or {})


def _passkey_login(request: Request, data: dict[str, Any]) -> Response:
    """Valida la passkey y la cuenta, y responde a dónde ir."""
    challenge = passkeys.take_challenge(get_session(request), 'login')
    if challenge is None:
        return save_session(request, JSONResponse({'error': 'El pedido venció: probá de nuevo'}, status_code=400))
    try:
        user = accounts.get_user(passkeys.authenticate(data.get('credential') or {}, challenge,
                                                       request_origin(request)))
    except passkeys.PasskeyError as e:
        return save_session(request, JSONResponse({'error': str(e)}, status_code=400))
    if user is None:
        return save_session(request, JSONResponse({'error': 'La cuenta ya no existe'}, status_code=400))
    if user['disabled']:
        audit(request, user['id'], 'login_blocked')
        return save_session(request, JSONResponse(
            {'error': 'Tu cuenta está bloqueada: hablá con el administrador'}, status_code=403))
    if auth.verification_required() and not user['email_verified']:
        return save_session(request, JSONResponse({'error': 'Antes de entrar confirmá tu email'}, status_code=403))
    auth.start_session(get_session(request), _secret(request), user['id'], *client_info(request))
    _audit_login(request, user, 'login_passkey')
    return save_session(request, JSONResponse({'redirect': safe_next(str(data.get('next') or ''))}))


@router.get("/login/google", name="google_login")
def google_login(request: Request) -> Response:
    """Manda a Google a elegir la cuenta."""
    if not hit_limit(request, '10 per minute', 'google_login', limit_key(request)):
        return too_many_requests()
    redirect_uri = public_url(request, 'google_callback') if google_oauth.google_enabled() else None
    if not redirect_uri:
        flash(request, 'El login con Google no está disponible', 'danger')
        return redirect(request, url_for(request, 'login'))
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    get_session(request)['google_oauth'] = {'state': state, 'verifier': verifier,
                                            'next': request.query_params.get('next', '')}
    return redirect(request, google_oauth.authorization_url(redirect_uri, state, verifier))


@router.get("/login/google/callback", name="google_callback")
def google_callback(request: Request) -> Response:
    """Vuelta de Google: entra a la cuenta de ese email (o la crea si el registro está abierto)."""
    if not hit_limit(request, '10 per minute', 'google_callback', limit_key(request)):
        return too_many_requests()
    pending = get_session(request).pop('google_oauth', None) or {}
    redirect_uri = public_url(request, 'google_callback') if google_oauth.google_enabled() else None
    code = request.query_params.get('code')
    if (not redirect_uri or not code or not pending.get('state')
            or request.query_params.get('state') != pending['state']):
        flash(request, 'No se pudo entrar con Google: volvé a intentarlo', 'danger')
        return redirect(request, url_for(request, 'login'))
    try:
        email = google_oauth.verified_email(code, pending['verifier'], redirect_uri)
    except Exception as e:
        logger.error(f'Google rechazó el login: {type(e).__name__}')
        email = None
    if not email:
        flash(request, 'No se pudo entrar con Google: la cuenta tiene que tener el email verificado', 'danger')
        return redirect(request, url_for(request, 'login'))
    user_id = accounts.find_user_id(email)
    if user_id is None:
        try:
            # contraseña al azar: quien entra con Google puede crear una con "¿Olvidaste tu contraseña?"
            # el login avisa que continuar con Google acepta los Términos y la Privacidad
            user_id = accounts.register(email, secrets.token_urlsafe(32), terms_accepted=True)
        except accounts.AccountError as e:
            flash(request, str(e), 'warning')
            return redirect(request, url_for(request, 'login'))
        audit(request, user_id, 'register')
    user = accounts.get_user(user_id)
    if user is None:
        return redirect(request, url_for(request, 'login'))
    if user['disabled']:
        audit(request, user_id, 'login_blocked')
        flash(request, 'Tu cuenta está bloqueada: hablá con el administrador', 'danger')
        return redirect(request, url_for(request, 'login'))
    if not user['email_verified']:
        # la cuenta pudo crearla otro con este email: su contraseña, sus sesiones y sus passkeys dejan de valer
        accounts.set_password(user_id, secrets.token_urlsafe(32))
        passkeys.delete_all(user_id)
    # Google ya comprobó que el email es suyo
    accounts.mark_verified(user_id)
    user = accounts.get_user(user_id) or user
    next_url = pending.get('next', '')
    return begin_login(request, user, 'login_google', next_url) or _finish_login(request, user, 'login_google', next_url)
