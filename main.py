"""App ASGI de EmpleoIA: páginas, APIs, métricas y páginas de error."""
import logging
import os
import time
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Header, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

import accounts
import auth
import error_reporting
import fastapi_web
import observability
import rate_limit
import security_headers
import version
from routers import (account_integrations, account_pages, admin_pages, ai, alert_pages, analytics, auth_pages, content_pages, documents,
                     export_pages, insights, login_providers, pages, profile_pages, scraper_pages, security_pages, tracker)
from routers import push as push_router
from routers import webhooks

PUBLIC_API_PATHS = {"/api/health", "/api/ready"}
EXTENSION_API_PATHS = {"/api/tracker/save-from-extension"}
LOGIN_ROUTERS = [account_pages.router, account_integrations.router, security_pages.router, admin_pages.router, export_pages.router, content_pages.router,
                 profile_pages.router, alert_pages.router, scraper_pages.router, ai.router, analytics.router, pages.router]
PUBLIC_PAGES = {"set_language", "service_worker", "robots", "health_check", "readiness_check"}


def _matches(routers, scope) -> bool:
    return any(route.matches(scope)[0] != Match.NONE for r in routers for route in r.routes
               if getattr(route, "name", None) not in PUBLIC_PAGES)


async def rate_limit_ai(request: Request, call_next):
    """Límites por cuenta (o por IP sin sesión): API_RATE_LIMIT para todo /api/* y AI_RATE_LIMIT para la IA.

    Corre dentro de require_login, que ya fijó la cuenta.
    """
    client_ip = rate_limit.client_ip(request.client.host if request.client else None,
                                     request.headers.get("x-forwarded-for"))
    user_id = accounts.current_user_id()
    path = request.url.path
    token = request.headers.get("x-extension-token")
    if user_id is None and token and path in EXTENSION_API_PATHS:
        # la extensión no manda cookie: su token identifica la cuenta. Los tokens inválidos se
        # cuentan por IP y, superado el límite, se corta antes de consultar la base.
        if not rate_limit.bad_token_allowed(client_ip):
            return JSONResponse({"error": "Demasiadas solicitudes, probá de nuevo en un minuto"}, status_code=429)
        user_id = await run_in_threadpool(auth.extension_token_user, token)
        if user_id is None:
            rate_limit.record_bad_token(client_ip)
    key = rate_limit.client_key(user_id, client_ip)
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS and not rate_limit.hit_api_limit(key):
        return JSONResponse({"error": "Demasiadas solicitudes, probá de nuevo en un minuto"}, status_code=429)
    if _matches([ai.router], request.scope):
        if not rate_limit.hit_ai_limit(key):
            return JSONResponse({"error": "Demasiadas solicitudes de IA, probá de nuevo en un minuto"}, status_code=429)
    return await call_next(request)

async def require_login(request: Request, call_next):
    """Fija el usuario de la sesión para las capas de datos; las rutas nativas de FastAPI exigen login."""
    web_app = request.app.state.web_app
    cookie = request.cookies.get(web_app.config.get("SESSION_COOKIE_NAME", "session"))
    user_id = await run_in_threadpool(auth.cookie_user_id, web_app, cookie) if cookie else None
    accounts.set_current_user(user_id)
    error_reporting.identify(user_id)
    if (auth.auth_enabled() and user_id is None and request.url.path not in PUBLIC_API_PATHS
            and _matches(LOGIN_ROUTERS, request.scope)):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "No autenticado"}, status_code=401)
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target)}", status_code=302)
    return await call_next(request)

async def record_metrics(request: Request, call_next):
    """Último middleware registrado = el más externo: también cuenta los 401 y 429."""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        observability.observe_request(
            request.method, observability.route_label(request.app, request.scope),
            status, time.perf_counter() - start)

def metrics(authorization: str | None = Header(default=None)):
    """Corre en el threadpool: render() lee Redis de forma sincrónica. Métricas Prometheus; exige `Authorization: Bearer $METRICS_TOKEN` (sin token configurado, 404)."""
    allowed = observability.metrics_allowed(authorization)
    if allowed is None:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if not allowed:
        return JSONResponse({"error": "No autorizado"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(observability.render(), media_type=observability.CONTENT_TYPE)

async def health_check():
    """Para verificar si los contenedores/FastAPI están vivos."""
    return {"status": "ok", "service": "EmpleoIA API (FastAPI Mode)",
            "version": version.__version__, "commit": version.commit()}


def _check_database():
    """`SELECT 1` contra la base; levanta si no responde."""
    from sqlalchemy import text

    import models
    with models.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _check_redis():
    """`PING` al Redis de los límites de pedidos, si `RATELIMIT_STORAGE_URI` es redis://; levanta si no responde.

    Es el único Redis sin el que la web no atiende: sin él, login y APIs fallan. `REDIS_URL` (Celery, cachés,
    métricas) tiene respaldo local, así que no lo revisa."""
    import redis
    url = os.getenv("RATELIMIT_STORAGE_URI", "")
    if url.startswith(("redis://", "rediss://")):
        client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        try:
            client.ping()
        finally:
            client.close()


def readiness_check():
    """Lista para recibir pedidos: la base responde y, si los límites usan Redis, también. 503 si algo falla.
    /api/health solo dice que el proceso está vivo (liveness); esta es la de startup y del uptime check."""
    checks, ok = {}, True
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            check()
            checks[name] = "ok"
        except Exception as e:
            logging.warning(f"Readiness: {name} no responde ({type(e).__name__}: {e})")
            checks[name], ok = "error", False
    return JSONResponse({"status": "ok" if ok else "error", "checks": checks}, status_code=200 if ok else 503)


async def http_error(request: Request, exc: StarletteHTTPException):
    """Errores HTTP: JSON en /api/* y en los 405; página de error en el resto (404 sin detalles internos)."""
    if request.url.path.startswith("/api/") or exc.status_code != 404:
        return await http_exception_handler(request, exc)
    return fastapi_web.render(request, "error.html", 404, code=404, message="Página no encontrada")


async def server_error(request: Request, exc: Exception):
    """500 sin el mensaje interno (queda en el log y, con SENTRY_DSN, en Sentry)."""
    logging.exception(f"500 en {request.url.path}: {exc}")
    error_reporting.capture(exc)
    if request.url.path.startswith("/api/"):
        return security_headers.apply(request, JSONResponse({"error": "Error interno"}, status_code=500))
    return security_headers.apply(request, fastapi_web.templates.TemplateResponse(
        request=request, name="error.html", status_code=500,
        context={"code": 500, "message": "Error interno del servidor"}))


# Errores que cualquier ruta de la API puede devolver; se publican en /openapi.json para que Schemathesis los acepte.
DOCUMENTED_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Pedido inválido o token CSRF vencido"},
    401: {"description": "Sin sesión"},
    403: {"description": "Sin permiso (consentimiento de IA, rol o cuenta)"},
    404: {"description": "No existe o no es de la cuenta"},
    409: {"description": "Ya existe"},
    413: {"description": "Pedido demasiado grande"},
    429: {"description": "Límite de pedidos"},
    503: {"description": "Servicio no configurado o no disponible (IA, push, worker)"},
}


def create_app(web_app=None) -> FastAPI:
    """FastAPI con sus routers; `web_app` (por defecto la de app.py) tiene la clave, la config y los globals."""
    error_reporting.setup("web")
    docs = os.getenv("ENABLE_API_DOCS", "0") == "1"
    app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version=version.__version__,
                  docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
                  openapi_url="/openapi.json" if docs else None, responses=DOCUMENTED_ERRORS)
    try:
        app.mount("/static", StaticFiles(directory="static"), name="static")
    except Exception as e:
        logging.warning(f"Static directory not found during boot: {e}")

    app.include_router(ai.router)
    app.include_router(ai.extras)
    app.include_router(analytics.router)
    app.include_router(tracker.router)
    app.include_router(insights.router)
    app.include_router(documents.router)
    app.include_router(push_router.router)
    app.include_router(pages.router)
    app.include_router(auth_pages.router)
    app.include_router(login_providers.router)
    app.include_router(account_pages.router)
    app.include_router(account_integrations.router)
    app.include_router(security_pages.router)
    app.include_router(admin_pages.router)
    app.include_router(export_pages.router)
    app.include_router(content_pages.router)
    app.include_router(profile_pages.router)
    app.include_router(alert_pages.router)
    app.include_router(scraper_pages.router)
    app.include_router(webhooks.router)

    app.get("/metrics", include_in_schema=False)(metrics)
    app.get("/api/health", name="health_check")(health_check)
    app.get("/api/ready", name="readiness_check")(readiness_check)
    # el último registrado es el más externo: métricas > cabeceras > login > límites
    for middleware in (rate_limit_ai, require_login, security_headers.add_security_headers, record_metrics):
        app.middleware("http")(middleware)

    observability.setup_tracing(fastapi_app=app)

    app.add_exception_handler(StarletteHTTPException, http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, server_error)

    if web_app is None:
        from app import app as web_app
    app.state.web_app = web_app
    return app


app = create_app()
