"""App ASGI: rutas de FastAPI y, montada debajo, la app Flask con lo que todavía no se migró."""
import logging
import time
from urllib.parse import quote

from fastapi import FastAPI, Header, Request
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.routing import Match

import accounts
import auth
import observability
import rate_limit
from routers import account_pages, ai, analytics, auth_pages, content_pages, documents, insights, pages, tracker
from routers import push as push_router

PUBLIC_API_PATHS = {"/api/health"}
EXTENSION_API_PATHS = {"/api/tracker/save-from-extension"}
LOGIN_ROUTERS = [account_pages.router, content_pages.router, ai.router, analytics.router, pages.router]
PUBLIC_PAGES = {"set_language", "service_worker", "health_check"}


def _matches(routers, scope) -> bool:
    return any(route.matches(scope)[0] != Match.NONE for r in routers for route in r.routes
               if getattr(route, "name", None) not in PUBLIC_PAGES)


async def rate_limit_ai(request: Request, call_next):
    """Límites por cuenta (o por IP sin sesión): API_RATE_LIMIT para todo /api/* y AI_RATE_LIMIT para la IA.

    Corre dentro de require_login, que ya fijó la cuenta. Las rutas de IA que siguen en Flask
    las cuenta app.py con el mismo contador.
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
    flask = request.app.state.flask_app
    cookie = request.cookies.get(flask.config.get("SESSION_COOKIE_NAME", "session")) if flask else None
    user_id = await run_in_threadpool(auth.cookie_user_id, flask, cookie) if cookie else None
    accounts.set_current_user(user_id)
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
            request.method, observability.route_label(request.app, request.scope, request.app.state.flask_app),
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
    return {"status": "ok", "service": "EmpleoIA API (FastAPI Mode)"}


def create_app(flask_app=None) -> FastAPI:
    """FastAPI con sus routers y `flask_app` (por defecto la de app.py) montada en `/`."""
    app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version="1.0.0")
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
    app.include_router(account_pages.router)
    app.include_router(content_pages.router)

    app.get("/metrics", include_in_schema=False)(metrics)
    app.get("/api/health", name="health_check")(health_check)
    # el último registrado es el más externo: métricas > login > límites
    for middleware in (rate_limit_ai, require_login, record_metrics):
        app.middleware("http")(middleware)

    observability.setup_tracing(fastapi_app=app)

    if flask_app is None:
        try:
            from app import app as flask_app
        except Exception as e:
            logging.error(f"Error mounting Flask app: {e}")
    app.state.flask_app = flask_app
    if flask_app is not None:
        # Lo que FastAPI no atiende lo sirve Flask (migración gradual)
        app.mount("/", WSGIMiddleware(flask_app))
    return app


app = create_app()
