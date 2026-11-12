from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import logging

from routers import ai, analytics, documents, insights, tracker
from routers import push as push_router

app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version="1.0.0")

# Setup para Archivos Estáticos (CSS, JS)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logging.warning(f"Static directory not found during boot: {e}")

# Include Routers
app.include_router(ai.router)
app.include_router(ai.extras)
app.include_router(analytics.router)
app.include_router(tracker.router)
app.include_router(insights.router)
app.include_router(documents.router)
app.include_router(push_router.router)

import accounts  # noqa: E402
import rate_limit  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.routing import Match  # noqa: E402

PUBLIC_API_PATHS = {"/api/health"}


@app.middleware("http")
async def rate_limit_ai(request: Request, call_next):
    """Límites por cuenta (o por IP sin sesión): API_RATE_LIMIT para todo /api/* y AI_RATE_LIMIT para la IA.

    Corre dentro de require_login, que ya fijó la cuenta. Las rutas de IA que siguen en Flask
    las cuenta app.py con el mismo contador.
    """
    client_ip = rate_limit.client_ip(request.client.host if request.client else None,
                                     request.headers.get("x-forwarded-for"))
    user_id = accounts.current_user_id()
    token = request.headers.get("x-extension-token")
    if user_id is None and token:
        # la extensión no manda cookie: su token identifica la cuenta (uno inválido cuenta por IP)
        user_id = await run_in_threadpool(auth.extension_token_user, token)
    key = rate_limit.client_key(user_id, client_ip)
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS and not rate_limit.hit_api_limit(key):
        return JSONResponse({"error": "Demasiadas solicitudes, probá de nuevo en un minuto"}, status_code=429)
    if any(route.matches(request.scope)[0] != Match.NONE for route in ai.router.routes):
        if not rate_limit.hit_ai_limit(key):
            return JSONResponse({"error": "Demasiadas solicitudes de IA, probá de nuevo en un minuto"}, status_code=429)
    return await call_next(request)

import auth  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from urllib.parse import quote  # noqa: E402


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Fija el usuario de la sesión para las capas de datos; las rutas nativas de FastAPI exigen login."""
    from app import app as flask_app
    cookie = request.cookies.get(flask_app.config.get("SESSION_COOKIE_NAME", "session"))
    user_id = await run_in_threadpool(auth.cookie_user_id, flask_app, cookie) if cookie else None
    accounts.set_current_user(user_id)
    if auth.auth_enabled() and request.url.path not in PUBLIC_API_PATHS:
        is_api_route = any(
            route.matches(request.scope)[0] != Match.NONE
            for route in [*ai.router.routes, *analytics.router.routes]
        )
        if is_api_route:
            if user_id is None:
                if request.url.path.startswith("/api/"):
                    return JSONResponse({"error": "No autenticado"}, status_code=401)
                return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=302)
    return await call_next(request)

import time  # noqa: E402
import observability  # noqa: E402
from fastapi import Header  # noqa: E402
from fastapi.responses import Response  # noqa: E402


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    """Último middleware registrado = el más externo: también cuenta los 401 y 429."""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        try:
            from app import app as flask_app
        except Exception:
            flask_app = None
        observability.observe_request(request.method, observability.route_label(app, request.scope, flask_app),
                                      status, time.perf_counter() - start)


@app.get("/metrics", include_in_schema=False)
def metrics(authorization: str | None = Header(default=None)):
    """Corre en el threadpool: render() lee Redis de forma sincrónica. Métricas Prometheus; exige `Authorization: Bearer $METRICS_TOKEN` (sin token configurado, 404)."""
    allowed = observability.metrics_allowed(authorization)
    if allowed is None:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if not allowed:
        return JSONResponse({"error": "No autorizado"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(observability.render(), media_type=observability.CONTENT_TYPE)


observability.setup_tracing(fastapi_app=app)

@app.get("/api/health")
async def health_check():
    """Para verificar si los contenedores/FastAPI están vivos."""
    return {"status": "ok", "service": "EmpleoIA API (FastAPI Mode)"}

# ========================================================
# FLASK MOUNTING (STRANGLER FIG PATTERN)
# Montamos toda la app Legacy de Flask (app.py) para que maneje
# las vistas y rutas viejas que aún no pasamos a los routers nativos de FastAPI.
# ========================================================
try:
    from fastapi.middleware.wsgi import WSGIMiddleware
    from app import app as flask_app
    
    # Montar en la raiz todo lo que no atrape FastAPI.
    app.mount("/", WSGIMiddleware(flask_app))
    logging.info("Flask app successfully mounted under FastAPI!")
except Exception as e:
    logging.error(f"Error mounting Flask app: {e}")
