"""Login con Google (OAuth con PKCE): configuración y canje del código por el email verificado."""
import base64
import hashlib
import os
from urllib.parse import urlencode

import requests

import auth

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'  # noqa: S105 - URL pública
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def google_enabled() -> bool:
    """Hay cliente OAuth de Google (GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET) y login activo."""
    return auth.auth_enabled() and bool(os.getenv('GOOGLE_OAUTH_CLIENT_ID') and os.getenv('GOOGLE_OAUTH_CLIENT_SECRET'))


def authorization_url(redirect_uri: str, state: str, verifier: str) -> str:
    """URL de Google para elegir la cuenta, con el desafío PKCE de `verifier`."""
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return AUTH_URL + '?' + urlencode({
        'client_id': os.getenv('GOOGLE_OAUTH_CLIENT_ID'), 'redirect_uri': redirect_uri,
        'response_type': 'code', 'scope': 'openid email', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account'})


def verified_email(code: str, verifier: str, redirect_uri: str) -> str | None:
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
