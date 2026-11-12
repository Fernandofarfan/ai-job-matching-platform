"""Entrar con Google (OAuth 2.0 / OpenID Connect con PKCE)."""
import base64
import hashlib
import logging
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import flash, redirect, request, session, url_for

import accounts
import auth
from app import _safe_next, app, limiter
from web.account import _public_url, audit_login, client_info

logger = logging.getLogger(__name__)
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def google_enabled() -> bool:
    """Hay cliente OAuth de Google (GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET) y login activo."""
    return auth.auth_enabled() and bool(os.getenv('GOOGLE_OAUTH_CLIENT_ID') and os.getenv('GOOGLE_OAUTH_CLIENT_SECRET'))


@app.context_processor
def _google_flag():
    return {'google_login': google_enabled()}


@app.route('/login/google')
@limiter.limit('10 per minute')
def google_login():
    """Manda a Google a elegir la cuenta."""
    redirect_uri = _public_url('google_callback') if google_enabled() else None
    if not redirect_uri:
        flash('El login con Google no está disponible', 'danger')
        return redirect(url_for('login'))
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    session['google_oauth'] = {'state': state, 'verifier': verifier, 'next': request.args.get('next', '')}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return redirect(AUTH_URL + '?' + urlencode({
        'client_id': os.getenv('GOOGLE_OAUTH_CLIENT_ID'), 'redirect_uri': redirect_uri,
        'response_type': 'code', 'scope': 'openid email', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account'}))


def _google_email(code: str, verifier: str, redirect_uri: str):
    """Cambia el código por el email verificado de la cuenta de Google, o None."""
    token = requests.post(TOKEN_URL, data={
        'code': code, 'client_id': os.getenv('GOOGLE_OAUTH_CLIENT_ID'),
        'client_secret': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET'), 'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code', 'code_verifier': verifier}, timeout=10)
    token.raise_for_status()
    info = requests.get(USERINFO_URL, headers={'Authorization': f"Bearer {token.json()['access_token']}"}, timeout=10)
    info.raise_for_status()
    data = info.json()
    return data.get('email') if data.get('email_verified') is True else None


@app.route('/login/google/callback')
@limiter.limit('10 per minute')
def google_callback():
    """Vuelta de Google: entra a la cuenta de ese email (o la crea si el registro está abierto)."""
    pending = session.pop('google_oauth', None) or {}
    redirect_uri = _public_url('google_callback') if google_enabled() else None
    code = request.args.get('code')
    if not redirect_uri or not code or not pending.get('state') or request.args.get('state') != pending['state']:
        flash('No se pudo entrar con Google: volvé a intentarlo', 'danger')
        return redirect(url_for('login'))
    try:
        email = _google_email(code, pending['verifier'], redirect_uri)
    except Exception as e:
        logger.error(f'Google rechazó el login: {type(e).__name__}')
        email = None
    if not email:
        flash('No se pudo entrar con Google: la cuenta tiene que tener el email verificado', 'danger')
        return redirect(url_for('login'))
    user_id = accounts.find_user_id(email)
    if user_id is None:
        try:
            # contraseña al azar: quien entra con Google puede crear una con "¿Olvidaste tu contraseña?"
            user_id = accounts.register(email, secrets.token_urlsafe(32))
        except accounts.AccountError as e:
            flash(str(e), 'warning')
            return redirect(url_for('login'))
    if not accounts.get_user(user_id)['email_verified']:
        # la cuenta pudo crearla otro con este email: su contraseña y sus sesiones dejan de valer
        accounts.set_password(user_id, secrets.token_urlsafe(32))
    # Google ya comprobó que el email es suyo
    accounts.mark_verified(user_id)
    auth.start_session(session, app.secret_key, user_id, *client_info())
    audit_login(accounts.get_user(user_id), 'login_google')
    return redirect(_safe_next(pending.get('next', '')))
