"""Errores de producción a Sentry (opcional, con SENTRY_DSN), sin datos personales.

Se reportan las excepciones no atrapadas de la web (500) y las tareas de Celery que fallan.
Los eventos llevan solo el id de la cuenta: sin cookies, cabeceras de autenticación,
cuerpos de pedidos, query strings ni emails.
"""
from typing import TYPE_CHECKING, Any, cast
import logging
import os
import re

import version

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

logger = logging.getLogger(__name__)

_SENSITIVE_HEADERS = {'authorization', 'cookie', 'set-cookie', 'x-csrftoken', 'x-csrf-token',
                      'x-extension-token', 'x-forwarded-for', 'x-real-ip'}
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_enabled = False


def enabled() -> bool:
    """True si Sentry quedó inicializado en este proceso."""
    return _enabled


def _scrub_text(value: Any) -> Any:
    return _EMAIL.sub('[email]', value) if isinstance(value, str) else value


def before_send(event: "Event", hint: "Hint | None" = None) -> "Event":
    """Saca datos personales del evento y le pone solo el id de la cuenta actual."""
    return cast("Event", _scrub_event(cast(dict[str, Any], event)))


def _scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    """`before_send` sobre el evento como dict: el TypedDict de Sentry no deja editar claves anidadas."""
    request = event.get('request')
    if isinstance(request, dict):
        headers = request.get('headers') or {}
        request['headers'] = {k: ('[filtrado]' if k.lower() in _SENSITIVE_HEADERS else v)
                              for k, v in headers.items()}
        for key in ('cookies', 'data', 'query_string', 'env'):
            request.pop(key, None)
        if isinstance(request.get('url'), str):
            request['url'] = request['url'].split('?', 1)[0]
    for exc in (event.get('exception') or {}).get('values') or []:
        exc['value'] = _scrub_text(exc.get('value'))
    if isinstance(event.get('logentry'), dict):
        for key in ('message', 'formatted'):
            event['logentry'][key] = _scrub_text(event['logentry'].get(key))
    try:
        import accounts
        uid = accounts.current_user_id()
    except Exception:
        uid = None
    if uid is None:
        # el 500 lo maneja una capa que no ve el ContextVar del middleware: queda el id de `identify`
        uid = (event.get('user') or {}).get('id')
    event['user'] = {'id': str(uid)} if uid is not None else {}
    return event


def _float_env(name: str, default: str | float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def setup(component: str) -> bool:
    """Inicializa Sentry si hay SENTRY_DSN; `component` ('web' o 'worker') queda como tag."""
    global _enabled
    dsn = os.getenv('SENTRY_DSN')
    if not dsn or _enabled:
        return _enabled
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning('SENTRY_DSN configurado pero falta sentry-sdk')
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv('SENTRY_ENVIRONMENT') or 'development',
        # versión y commit de la imagen (VERSION y APP_COMMIT); SENTRY_RELEASE lo reemplaza
        release=os.getenv('SENTRY_RELEASE') or version.release(),
        traces_sample_rate=_float_env('SENTRY_TRACES_SAMPLE_RATE', '0'),
        send_default_pii=False,
        max_request_body_size='never',
        before_send=before_send,
        # los logger.error son breadcrumbs; eventos solo para excepciones no atrapadas
        integrations=[LoggingIntegration(level=logging.INFO, event_level=None)],
    )
    sentry_sdk.set_tag('component', component)
    _enabled = True
    return True


def identify(user_id: int | None) -> None:
    """Deja el id de la cuenta en el scope del pedido (sobrevive a los middlewares que corren en otra tarea)."""
    if not _enabled:
        return
    try:
        import sentry_sdk
        sentry_sdk.get_isolation_scope().set_user({'id': str(user_id)} if user_id is not None else None)
    except Exception as e:
        logger.warning(f'No se pudo fijar la cuenta en Sentry: {e}')


def capture(exc: BaseException) -> None:
    """Reporta `exc` si Sentry está activo; nunca falla."""
    if not _enabled:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception as e:
        logger.warning(f'No se pudo reportar el error a Sentry: {e}')
