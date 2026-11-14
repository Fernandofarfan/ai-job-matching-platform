"""Páginas HTML de FastAPI: sesión en cookie firmada, CSRF, avisos y url_for.

El formato de la cookie y del token CSRF es el que usaban Flask y Flask-WTF (ver web_settings.py),
así las sesiones abiertas antes de quitar Flask siguen valiendo.
"""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer
from jinja2 import pass_context
from starlette.datastructures import ImmutableMultiDict
from starlette.routing import NoMatchFound

import account_notify
import accounts
import auth
import i18n
import rate_limit
import security_headers

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
# Caracteres que quedan sin escapar en la query (mismas URLs que armaba el url_for de Flask)
QUERY_SAFE = "!$'()*,/:;?@"


def web_app_for(request: Request):
    """Clave, config y globals de la web (web_settings.WebApp de app.py, o la de los tests)."""
    web_app = getattr(request.app.state, 'web_app', None)
    if web_app is None:
        from app import app as web_app
    return web_app


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

    @property
    def permanent(self) -> bool:
        """Si la cookie dura PERMANENT_SESSION_LIFETIME (como session.permanent de Flask)."""
        return bool(self.get('_permanent'))

    @permanent.setter
    def permanent(self, value: bool) -> None:
        """Marca la sesión como permanente o de navegador."""
        self['_permanent'] = bool(value)

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
        web_app = web_app_for(request)
        cookie = request.cookies.get(web_app.config.get('SESSION_COOKIE_NAME', 'session'))
        request.state.web_session = WebSession(auth.load_session_cookie(web_app, cookie))
    return request.state.web_session


ResponseT = TypeVar('ResponseT', bound=Response)


def save_session(request: Request, response: ResponseT) -> ResponseT:
    """Escribe la cookie si la sesión cambió, con los mismos atributos que pone Flask."""
    web_app = web_app_for(request)
    config = web_app.config
    session = get_session(request)
    # como Flask (SESSION_REFRESH_EACH_REQUEST): una sesión permanente renueva su vencimiento en cada página
    refresh = bool(session.get('_permanent')) and config.get('SESSION_REFRESH_EACH_REQUEST', True)
    if not session.modified and not refresh:
        return response
    name = config.get('SESSION_COOKIE_NAME', 'session')
    common: dict[str, Any] = {'path': config.get('SESSION_COOKIE_PATH') or '/',
                              'domain': config.get('SESSION_COOKIE_DOMAIN') or None,
                              'secure': bool(config.get('SESSION_COOKIE_SECURE')),
                              'httponly': bool(config.get('SESSION_COOKIE_HTTPONLY', True)),
                              'samesite': config.get('SESSION_COOKIE_SAMESITE') or 'lax'}
    if not session:
        response.delete_cookie(name, **common)
        return response
    value = web_app.session_serializer().dumps(dict(session))
    expires = None
    if session.get('_permanent'):
        expires = datetime.now(timezone.utc) + web_app.permanent_session_lifetime
    response.set_cookie(name, value, expires=expires, **common)
    return response


def csrf_token(request: Request) -> str:
    """Token firmado igual que Flask-WTF (`csrf_token()` en las plantillas)."""
    web_app = web_app_for(request)
    session = get_session(request)
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(20)
    return URLSafeTimedSerializer(web_app.secret_key, salt='wtf-csrf-token').dumps(session['csrf_token'])


def flash(request: Request, message: str, category: str = 'message') -> None:
    """Aviso para la próxima página, en el mismo lugar de la sesión que usa Flask."""
    session = get_session(request)
    session['_flashes'] = [*session.get('_flashes', []), (category, message)]


def get_flashed_messages(request: Request, with_categories: bool = False) -> list:
    flashes = get_session(request).pop('_flashes', []) or []
    return [tuple(f) for f in flashes] if with_categories else [f[1] for f in flashes]


def all_routes(routes):
    """Rutas de la app, incluidas las de los include_router (FastAPI >= 0.13x los agrupa)."""
    for route in routes:
        nested = getattr(route, 'original_router', None)
        if nested is not None:
            yield from all_routes(nested.routes)
        else:
            yield route


def url_for(request: Request, endpoint: str, **values) -> str:
    """Como el url_for de Flask: la ruta con ese nombre, y lo que sobra va en la query."""
    if endpoint == 'static':
        return str(request.app.url_path_for('static', path=values.pop('filename', values.pop('path', ''))))
    try:
        route = next(r for r in all_routes(request.app.router.routes) if getattr(r, 'name', None) == endpoint)
        params = {k: values.pop(k) for k in list(values) if k in getattr(route, 'param_convertors', {})}
        path = str(request.app.url_path_for(endpoint, **params))
    except StopIteration:
        raise NoMatchFound(endpoint, values) from None
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
def _csp_nonce(context):
    """Nonce de la CSP del pedido, para los <script> inline de las plantillas."""
    return security_headers.nonce(context['request'])


@pass_context
def _get_flashed_messages(context, with_categories=False, **_):
    return get_flashed_messages(context['request'], with_categories)


templates.env.globals.update({'url_for': _url_for, 'csrf_token': _csrf_token, 'csp_nonce': _csp_nonce,
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
            'ai_consent_needed': user is not None and not user.get('ai_consent', True),
            'current_lang': lang, 'languages': i18n.LANGUAGES,
            'current_path': request.url.path + (f'?{request.url.query}' if request.url.query else '')}
    response = templates.TemplateResponse(request=request, name=name, context={**base, **context},
                                          status_code=status_code)
    return save_session(request, response)


def redirect(request: Request, target: str, status_code: int = 302) -> RedirectResponse:
    return save_session(request, RedirectResponse(target, status_code=status_code))


def legacy(request: Request) -> dict:
    """Globals de app.py (perfil, resultados, base, job_status)."""
    return web_app_for(request).extensions['empleoia_app_globals']


def client_ip(request: Request) -> str:
    """IP del cliente respetando TRUSTED_PROXY_HOPS (ver rate_limit.client_ip)."""
    return rate_limit.client_ip(request.client.host if request.client else None,
                                request.headers.get('x-forwarded-for'))


def client_info(request: Request) -> tuple[str, Optional[str]]:
    """IP y navegador del pedido, para registrar la sesión y los eventos de seguridad."""
    return client_ip(request), request.headers.get('user-agent')


def limit_key(request: Request) -> str:
    """Clave por cuenta si hay sesión, si no por IP (como limit_key de app.py)."""
    return rate_limit.client_key(current_user_id(), client_ip(request))


def hit_limit(request: Request, spec: str, namespace: str, key: str) -> bool:
    """Suma un pedido al límite `spec` de la página; False si lo superó (RATELIMIT_ENABLED=False lo apaga)."""
    if not web_app_for(request).config.get('RATELIMIT_ENABLED', True):
        return True
    return rate_limit.hit_page(spec, namespace, key)


def too_many_requests() -> JSONResponse:
    """Respuesta 429 de los límites de pedidos."""
    return JSONResponse({'error': 'Demasiadas solicitudes, probá de nuevo en un minuto'}, status_code=429)


FORM_MAX_BYTES = 64 * 1024


class TextForm(ImmutableMultiDict[str, str]):
    """Campos de texto del formulario (`get` y `getlist`, como request.form de Flask)."""

FORM_MAX_FIELDS = 50


async def _body_within(request: Request, limit: int) -> bool:
    """Lee el cuerpo hasta `limit` bytes (aunque no venga Content-Length); False si lo supera."""
    length = request.headers.get('content-length', '')
    if length.isdigit() and int(length) > limit:
        return False
    body = b''
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return False
    request._body = body  # request.form() lo parsea desde acá
    return True


def _csrf_ok(request: Request, token: Optional[str]) -> bool:
    """Token del formulario o de los headers X-CSRFToken/X-CSRF-Token (como CSRFProtect de Flask)."""
    web_app = web_app_for(request)
    if not web_app.config.get('WTF_CSRF_ENABLED', True):
        return True
    token = token or request.headers.get('x-csrftoken') or request.headers.get('x-csrf-token')
    if not token:
        return False
    return auth.check_csrf_token(get_session(request), token, web_app.secret_key,
                                                 web_app.config.get('WTF_CSRF_TIME_LIMIT', 3600))


def csrf_error(request: Request) -> Response:
    """Página 400 por token CSRF faltante o inválido."""
    return render(request, 'error.html', 400, code=400, message='The CSRF token is missing or invalid.')


async def _parse(request: Request, max_bytes: int, max_files: int) -> tuple[TextForm, dict, Optional[Response]]:
    """Cuerpo limitado a `max_bytes`, campos de texto, archivos y error (413/400) si corresponde."""
    if not await _body_within(request, max_bytes):
        return TextForm(), {}, render(request, 'error.html', 413, code=413, message='Request Entity Too Large')
    parsed = await request.form(max_files=max_files, max_fields=FORM_MAX_FIELDS)
    form = TextForm([(k, v) for k, v in parsed.multi_items() if isinstance(v, str)])
    files = {k: v for k, v in parsed.multi_items() if not isinstance(v, str)}
    if not _csrf_ok(request, str(form.get('csrf_token') or '')):
        return form, files, csrf_error(request)
    return form, files, None


async def read_form(request: Request) -> tuple[TextForm, Optional[Response]]:
    """Formulario del POST (`get`/`getlist`) y, si el token CSRF no es válido, la respuesta 400."""
    form, _files, error = await _parse(request, FORM_MAX_BYTES, 0)
    return form, error


def upload_max_bytes(request: Request) -> int:
    """MAX_CONTENT_LENGTH (MAX_UPLOAD_MB)."""
    return int(web_app_for(request).config.get('MAX_CONTENT_LENGTH') or 16 * 1024 * 1024)


async def read_upload(request: Request) -> tuple[TextForm, dict, Optional[Response]]:
    """Formulario con un archivo (hasta MAX_CONTENT_LENGTH): campos, {nombre: UploadFile} y error (413/400)."""
    return await _parse(request, upload_max_bytes(request), 1)


def clear_offline_data(response: ResponseT) -> ResponseT:
    """Sin sesión no deben quedar páginas ni datos del tracker en el caché del service worker ni en IndexedDB."""
    response.headers['Clear-Site-Data'] = '"cache", "storage"'
    return response


def safe_next(target: str) -> str:
    """Destino local después del login; nunca otro sitio ni de vuelta al login."""
    is_local = auth.is_local_path(target)
    loops = is_local and target.split('?')[0].rstrip('/') in ('/login', '/logout', '/register')
    return target if is_local and not loops else '/'


def public_url(request: Request, endpoint: str, **values) -> Optional[str]:
    """URL absoluta para los emails (ver account_notify.public_base)."""
    base = account_notify.public_base(request.headers.get('host', ''), str(request.base_url))
    return base + url_for(request, endpoint, **values) if base else None
