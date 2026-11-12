"""Páginas HTML servidas por FastAPI con la misma sesión, CSRF y avisos que Flask.

La cookie `session` se lee y se escribe con el serializador de la app Flask montada en main.py,
así una sesión abierta en Flask sirve en FastAPI y viceversa mientras dure la migración.
"""
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer
from jinja2 import pass_context
from starlette.routing import NoMatchFound

import accounts
import auth
import i18n

templates = Jinja2Templates(directory='templates')
# Caracteres que Werkzeug deja sin escapar en la query: mismas URLs que el url_for de Flask
QUERY_SAFE = "!$'()*,/:;?@"


def flask_app_for(request: Request):
    """App Flask de la que salen la clave, la config y las rutas que todavía no pasaron a FastAPI."""
    flask_app = getattr(request.app.state, 'flask_app', None)
    if flask_app is None:
        from app import app as flask_app
    return flask_app


class WebSession(dict):
    """Contenido de la cookie de sesión; `modified` indica si hay que volver a escribirla."""

    def __init__(self, data: dict):
        super().__init__(data)
        self.modified = False

    def __setitem__(self, key, value):
        self.modified = True
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.modified = True
        super().__delitem__(key)

    def pop(self, key, *default):
        if key in self:
            self.modified = True
        return super().pop(key, *default)

    def clear(self):
        self.modified = True
        super().clear()


def get_session(request: Request) -> WebSession:
    """Sesión del pedido (se carga una vez y queda en request.state)."""
    if not hasattr(request.state, 'web_session'):
        flask_app = flask_app_for(request)
        cookie = request.cookies.get(flask_app.config.get('SESSION_COOKIE_NAME', 'session'))
        request.state.web_session = WebSession(auth.load_session_cookie(flask_app, cookie))
    return request.state.web_session


ResponseT = TypeVar('ResponseT', bound=Response)


def save_session(request: Request, response: ResponseT) -> ResponseT:
    """Escribe la cookie si la sesión cambió, con los mismos atributos que pone Flask."""
    session = getattr(request.state, 'web_session', None)
    if session is None or not session.modified:
        return response
    flask_app = flask_app_for(request)
    config = flask_app.config
    name = config.get('SESSION_COOKIE_NAME', 'session')
    common: dict[str, Any] = {'path': config.get('SESSION_COOKIE_PATH') or '/',
                              'domain': config.get('SESSION_COOKIE_DOMAIN') or None,
                              'secure': bool(config.get('SESSION_COOKIE_SECURE')),
                              'httponly': bool(config.get('SESSION_COOKIE_HTTPONLY', True)),
                              'samesite': config.get('SESSION_COOKIE_SAMESITE') or 'lax'}
    if not session:
        response.delete_cookie(name, **common)
        return response
    value = flask_app.session_interface.get_signing_serializer(flask_app).dumps(dict(session))
    expires = None
    if session.get('_permanent'):
        expires = datetime.now(timezone.utc) + flask_app.permanent_session_lifetime
    response.set_cookie(name, value, expires=expires, **common)
    return response


def csrf_token(request: Request) -> str:
    """Token firmado igual que Flask-WTF (`csrf_token()` en las plantillas)."""
    flask_app = flask_app_for(request)
    session = get_session(request)
    if 'csrf_token' not in session:
        session['csrf_token'] = hashlib.sha1(os.urandom(64)).hexdigest()
    return URLSafeTimedSerializer(flask_app.secret_key, salt='wtf-csrf-token').dumps(session['csrf_token'])


def flash(request: Request, message: str, category: str = 'message') -> None:
    """Aviso para la próxima página, en el mismo lugar de la sesión que usa Flask."""
    session = get_session(request)
    session['_flashes'] = [*session.get('_flashes', []), (category, message)]


def get_flashed_messages(request: Request, with_categories: bool = False) -> list:
    flashes = get_session(request).pop('_flashes', []) or []
    return [tuple(f) for f in flashes] if with_categories else [f[1] for f in flashes]


def url_for(request: Request, endpoint: str, **values) -> str:
    """Como el url_for de Flask: rutas de FastAPI o de Flask, y lo que sobra va en la query."""
    if endpoint == 'static':
        return str(request.app.url_path_for('static', path=values.pop('filename', values.pop('path', ''))))
    try:
        route = next(r for r in request.app.router.routes if getattr(r, 'name', None) == endpoint)
        params = {k: values.pop(k) for k in list(values) if k in getattr(route, 'param_convertors', {})}
        path = str(request.app.url_path_for(endpoint, **params))
    except (StopIteration, NoMatchFound):
        flask_app = flask_app_for(request)
        return flask_app.url_map.bind('').build(endpoint, values)
    values = {k: v for k, v in values.items() if v is not None}
    return f'{path}?{urlencode(values, safe=QUERY_SAFE)}' if values else path


def current_user_id() -> Optional[int]:
    return accounts.current_user_id() if auth.auth_enabled() else None


@pass_context
def _url_for(context, endpoint: str, **values):
    return url_for(context['request'], endpoint, **values)


@pass_context
def _csrf_token(context):
    return csrf_token(context['request'])


@pass_context
def _get_flashed_messages(context, with_categories=False, **_):
    return get_flashed_messages(context['request'], with_categories)


templates.env.globals.update({'url_for': _url_for, 'csrf_token': _csrf_token,
                              'get_flashed_messages': _get_flashed_messages, '_': i18n.jinja_gettext})


def select_language(request: Request) -> str:
    lang = i18n.negotiate(request.cookies.get(i18n.COOKIE), request.headers.get('accept-language'))
    i18n.set_locale(lang)
    return lang


def render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    """Plantilla con el contexto que Flask agrega a todas (cuenta, idioma) y la sesión guardada."""
    lang = select_language(request)
    user_id = current_user_id()
    user = accounts.get_user(user_id) if user_id else None
    base = {'auth_enabled': auth.auth_enabled(), 'current_user_email': user['email'] if user else '',
            'current_user_is_admin': user is not None and accounts.is_admin(user['id']),
            'current_lang': lang, 'languages': i18n.LANGUAGES}
    response = templates.TemplateResponse(request=request, name=name, context={**base, **context},
                                          status_code=status_code)
    return save_session(request, response)


def redirect(request: Request, target: str, status_code: int = 302) -> RedirectResponse:
    return save_session(request, RedirectResponse(target, status_code=status_code))
