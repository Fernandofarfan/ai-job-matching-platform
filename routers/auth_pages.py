"""Login, registro, recuperación de contraseña, segundo factor y Google, en FastAPI.

Los nombres de ruta son los endpoints que usaba Flask; la sesión es la misma cookie (fastapi_web).
"""
import hmac
import logging
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

import account_notify
import accounts
import auth
import google_oauth
import two_factor
import user_sessions
from fastapi_web import (TextForm, clear_offline_data, client_info, client_ip, flash, flask_app_for, get_session,
                         hit_limit, limit_key, public_url, read_form, redirect, render, safe_next,
                         too_many_requests, url_for)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"], include_in_schema=False)
PENDING_MAX_AGE = 300


def _secret(request: Request):
    """Clave de la app Flask montada (firma la sesión y los enlaces)."""
    return flask_app_for(request).secret_key


def _email_key(form: TextForm) -> str:
    """Clave por email del formulario: frena probar contraseñas de una cuenta desde muchas IPs."""
    return (form.get('email') or '').strip().lower()[:254]


def audit(request: Request, user_id, kind: str) -> bool:
    """Registra el evento de seguridad con la IP y el navegador del pedido."""
    return account_notify.audit(user_id, kind, *client_info(request))


def _audit_login(request: Request, user: dict, kind: str) -> None:
    """Registra el login y avisa por email si es un navegador nuevo."""
    account_notify.audit_login(user, kind, *client_info(request), lambda: public_url(request, 'account'))


def send_verification(request: Request, user: dict) -> bool:
    """Manda el enlace para confirmar el email de la cuenta."""
    token = auth.account_token(_secret(request), 'verify', user)
    return account_notify.send_verification(user, public_url(request, 'verify_email', token=token))


async def _post(request: Request, limits: list) -> tuple[Optional[TextForm], Optional[Response]]:
    """Formulario del POST (None en GET) con CSRF y límites [(spec, namespace, key_fn(form))]."""
    if request.method != 'POST':
        return None, None
    form, error = await read_form(request)
    if error:
        return form, error
    for spec, namespace, key in limits:
        if not hit_limit(request, spec, namespace, key(form)):
            return form, too_many_requests()
    return form, None


def begin_login(request: Request, user: dict, kind: str, next_url: str) -> Optional[Response]:
    """Con segundo factor activo deja el login pendiente y devuelve la redirección; si no, None."""
    if not two_factor.is_enabled(user['id']):
        return None
    get_session(request)['two_factor'] = {'uid': user['id'], 'kind': kind, 'next': next_url or '', 'ts': time.time(),
                                          'fp': auth.session_fingerprint(_secret(request), user)}
    return redirect(request, url_for(request, 'login_two_factor'))


def _finish_login(request: Request, user: dict, kind: str, next_url: str) -> Response:
    """Abre la sesión, registra el login y vuelve a `next_url` si es local."""
    auth.start_session(get_session(request), _secret(request), user['id'], *client_info(request))
    _audit_login(request, user, kind)
    return redirect(request, safe_next(next_url))


@router.api_route("/login", methods=["GET", "POST"], name="login")
async def login(request: Request):
    """Email y contraseña; con segundo factor sigue en /login/2fa."""
    form, error = await _post(request, [('10 per minute', 'login', lambda f: client_ip(request)),
                                        ('20 per hour', 'login_email', _email_key)])
    return error or await run_in_threadpool(_login, request, form)


def _login(request: Request, form: Optional[TextForm]) -> Response:
    """Muestra el login o comprueba el formulario (corre fuera del event loop)."""
    next_url = request.query_params.get('next', '')
    session = get_session(request)
    if not auth.auth_enabled():
        return redirect(request, safe_next(next_url))
    if form is None and auth.is_session_valid(session, _secret(request)):
        return redirect(request, safe_next(next_url))
    try:
        if accounts.count_users() == 0:
            return redirect(request, url_for(request, 'register', next=next_url))
        if form is not None:
            user_id = accounts.authenticate(form.get('email', ''), form.get('password', ''))
            user = accounts.get_user(user_id) if user_id else None
            if user and auth.verification_required() and not user['email_verified']:
                if send_verification(request, user):
                    flash(request, 'Antes de entrar confirmá tu email: te mandamos un enlace', 'warning')
                else:
                    flash(request, 'Tenés que confirmar tu email, pero no se pudo mandar el enlace: '
                          'avisale al administrador', 'danger')
            elif user and user['disabled']:
                audit(request, user['id'], 'login_blocked')
                flash(request, 'Tu cuenta está bloqueada: hablá con el administrador', 'danger')
            elif user:
                return begin_login(request, user, 'login', next_url) or _finish_login(request, user, 'login', next_url)
            else:
                audit(request, accounts.find_user_id(form.get('email', '')), 'login_failed')
                flash(request, 'Email o contraseña incorrectos', 'danger')
        signup = accounts.signup_open()
    except SQLAlchemyError as e:
        logger.error(f"Login sin base de datos: {e}")
        flash(request, 'La base de datos no responde; probá de nuevo en unos minutos', 'danger')
        signup = False
    return clear_offline_data(render(request, 'login.html', next_url=next_url, signup_open=signup,
                                     google_login=google_oauth.google_enabled()))


@router.api_route("/register", methods=["GET", "POST"], name="register")
async def register(request: Request):
    """Alta de cuenta: siempre para la primera; después solo con ALLOW_SIGNUP=true."""
    form, error = await _post(request, [('5 per minute', 'register', lambda f: client_ip(request))])
    return error or await run_in_threadpool(_register, request, form)


def _register(request: Request, form: Optional[TextForm]) -> Response:
    """Muestra el registro o crea la cuenta (corre fuera del event loop)."""
    next_url = request.query_params.get('next', '')
    if not auth.auth_enabled():
        return redirect(request, safe_next(next_url))
    try:
        first = accounts.count_users() == 0
        if not accounts.signup_open():
            flash(request, 'El registro está cerrado: pedile una cuenta al administrador', 'warning')
            return redirect(request, url_for(request, 'login', next=next_url))
        if form is not None:
            password = form.get('password', '')
            if password != form.get('confirm', ''):
                flash(request, 'Las contraseñas no coinciden', 'danger')
            else:
                try:
                    user_id = accounts.register(form.get('email', ''), password)
                except accounts.AccountError as e:
                    flash(request, str(e), 'danger')
                else:
                    audit(request, user_id, 'register')
                    user = accounts.get_user(user_id) or {}
                    sent = not user['email_verified'] and send_verification(request, user)
                    if auth.verification_required() and not user['email_verified']:
                        if sent:
                            flash(request, 'Te mandamos un enlace para confirmar tu email', 'info')
                        else:
                            flash(request, 'Cuenta creada, pero no se pudo mandar el enlace para confirmar el '
                                  'email: avisale al administrador', 'danger')
                        return redirect(request, url_for(request, 'login', next=next_url))
                    auth.start_session(get_session(request), _secret(request), user_id, *client_info(request))
                    return redirect(request, safe_next(next_url))
    except SQLAlchemyError as e:
        logger.error(f"Registro sin base de datos: {e}")
        flash(request, 'La base de datos no responde; probá de nuevo en unos minutos', 'danger')
        first = False
    return clear_offline_data(render(request, 'register.html', next_url=next_url, first_account=first,
                                     min_password=accounts.MIN_PASSWORD))


@router.post("/logout", name="logout")
async def logout(request: Request):
    """Cierra la sesión y borra el caché offline del navegador."""
    _form, error = await read_form(request)
    if error:
        return error
    session = get_session(request)
    await run_in_threadpool(user_sessions.revoke_sid, session.get('sid'))
    session.clear()
    return clear_offline_data(redirect(request, url_for(request, 'login')))


@router.api_route("/forgot_password", methods=["GET", "POST"], name="forgot_password")
async def forgot_password(request: Request):
    """Pide el email y manda el enlace de recuperación (la respuesta no dice si la cuenta existe)."""
    form, error = await _post(request, [('5 per minute', 'forgot', lambda f: client_ip(request)),
                                        ('5 per hour', 'forgot_email', _email_key)])
    return error or await run_in_threadpool(_forgot_password, request, form)


def _forgot_password(request: Request, form: Optional[TextForm]) -> Response:
    """Muestra el formulario o manda el enlace de recuperación."""
    if not auth.auth_enabled():
        return redirect(request, url_for(request, 'index'))
    if form is not None:
        user_id = accounts.find_user_id(form.get('email', ''))
        user = accounts.get_user(user_id) if user_id else None
        if user:
            token = auth.account_token(_secret(request), 'reset', user)
            account_notify.send_reset(user, public_url(request, 'reset_password', token=token))
        flash(request, 'Si hay una cuenta con ese email, te mandamos un enlace para recuperar la contraseña', 'info')
        return redirect(request, url_for(request, 'login'))
    return render(request, 'forgot_password.html')


@router.api_route("/reset_password/{token}", methods=["GET", "POST"], name="reset_password")
async def reset_password(request: Request, token: str):
    """Elige una contraseña nueva con el enlace del email; cierra las sesiones abiertas."""
    form, error = await _post(request, [('10 per minute', 'reset', lambda f: client_ip(request))])
    return error or await run_in_threadpool(_reset_password, request, token, form)


def _reset_password(request: Request, token: str, form: Optional[TextForm]) -> Response:
    """Comprueba el enlace y guarda la contraseña nueva."""
    if not auth.auth_enabled():
        return redirect(request, url_for(request, 'index'))
    user = auth.read_account_token(_secret(request), 'reset', token, auth.RESET_MAX_AGE)
    if user is None:
        flash(request, 'El enlace venció o ya se usó: pedí uno nuevo', 'danger')
        return redirect(request, url_for(request, 'forgot_password'))
    if form is not None:
        password = form.get('password', '')
        if password != form.get('confirm', ''):
            flash(request, 'Las contraseñas no coinciden', 'danger')
        else:
            try:
                accounts.set_password(user['id'], password, expected_hash=user['password_hash'])
            except accounts.AccountError as e:
                flash(request, str(e), 'danger')
            else:
                accounts.mark_verified(user['id'])  # recibió el email: la dirección es suya
                audit(request, user['id'], 'password_reset')
                get_session(request).clear()
                flash(request, 'Listo: ya podés entrar con la contraseña nueva', 'success')
                return clear_offline_data(redirect(request, url_for(request, 'login')))
    response = render(request, 'reset_password.html', token=token, min_password=accounts.MIN_PASSWORD)
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@router.get("/verify_email/{token}", name="verify_email")
def verify_email(request: Request, token: str):
    """Confirma el email con el enlace que se mandó al registrarse."""
    user = auth.read_account_token(_secret(request), 'verify', token, auth.VERIFY_MAX_AGE)
    if user is None:
        flash(request, 'El enlace de verificación venció o no es válido', 'danger')
    else:
        accounts.mark_verified(user['id'])
        audit(request, user['id'], 'email_verified')
        flash(request, 'Email confirmado', 'success')
    logged_in = auth.is_session_valid(get_session(request), _secret(request))
    return redirect(request, url_for(request, 'account' if logged_in else 'login'))


def _pending(request: Request) -> Optional[dict]:
    """Login pendiente del segundo factor, si no venció."""
    session = get_session(request)
    pending = session.get('two_factor')
    if not pending or time.time() - pending.get('ts', 0) > PENDING_MAX_AGE:
        session.pop('two_factor', None)
        return None
    return pending


@router.api_route("/login/2fa", methods=["GET", "POST"], name="login_two_factor")
async def login_two_factor(request: Request):
    """Pide el código de la app autenticadora (o uno de recuperación) después de la contraseña."""
    # el límite por cuenta pendiente frena probar códigos desde muchas IPs
    form, error = await _post(request, [
        ('10 per minute', 'two_factor', lambda f: client_ip(request)),
        ('10 per 15 minutes', 'two_factor_pending', lambda f: str((_pending(request) or {}).get('uid')))])
    return error or await run_in_threadpool(_login_two_factor, request, form)


def _login_two_factor(request: Request, form: Optional[TextForm]) -> Response:
    """Muestra el pedido de código o lo comprueba y termina el login pendiente."""
    session = get_session(request)
    pending = _pending(request)
    user = accounts.get_user(pending['uid']) if pending else None
    if not pending or not user or not hmac.compare_digest(str(pending.get('fp', '')),
                                                          auth.session_fingerprint(_secret(request), user)):
        session.pop('two_factor', None)
        flash(request, 'Volvé a ingresar tu email y contraseña', 'warning')
        return redirect(request, url_for(request, 'login'))
    if form is not None:
        try:
            method = two_factor.verify(user['id'], form.get('code', '').strip())
        except two_factor.TwoFactorError as e:
            logger.error(f'Segundo factor ilegible para la cuenta {user["id"]}: {e}')
            flash(request, 'No se pudo comprobar el código: avisale al administrador', 'danger')
            return render(request, 'login_2fa.html')
        if method:
            response = _finish_login(request, user, pending['kind'], pending.get('next', ''))
            if method == 'recovery':
                audit(request, user['id'], 'recovery_code_used')
                flash(request, f'Usaste un código de recuperación: te quedan '
                      f'{two_factor.recovery_codes_left(user["id"])}', 'warning')
                response = redirect(request, response.headers['location'])
            return response
        audit(request, user['id'], 'two_factor_failed')
        flash(request, 'El código no es correcto', 'danger')
    return render(request, 'login_2fa.html')


@router.get("/login/google", name="google_login")
def google_login(request: Request):
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
def google_callback(request: Request):
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
            user_id = accounts.register(email, secrets.token_urlsafe(32))
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
        # la cuenta pudo crearla otro con este email: su contraseña y sus sesiones dejan de valer
        accounts.set_password(user_id, secrets.token_urlsafe(32))
    # Google ya comprobó que el email es suyo
    accounts.mark_verified(user_id)
    user = accounts.get_user(user_id) or user
    next_url = pending.get('next', '')
    return begin_login(request, user, 'login_google', next_url) or _finish_login(request, user, 'login_google', next_url)
