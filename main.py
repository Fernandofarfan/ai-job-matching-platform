from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import logging

from routers import ai, analytics, insights, tracker

app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version="1.0.0")

# Setup para Archivos Estáticos (CSS, JS)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logging.warning(f"Static directory not found during boot: {e}")

# Include Routers
app.include_router(ai.router)
app.include_router(analytics.router)
app.include_router(tracker.router)
app.include_router(insights.router)

import rate_limit  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.routing import Match  # noqa: E402


@app.middleware("http")
async def rate_limit_ai(request: Request, call_next):
    """Cuenta las rutas de IA nativas de FastAPI; las de Flask las cuenta app.py con el mismo contador."""
    if any(route.matches(request.scope)[0] != Match.NONE for route in ai.router.routes):
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limit.hit_ai_limit(client_ip):
            return JSONResponse({"error": "Demasiadas solicitudes de IA, probá de nuevo en un minuto"}, status_code=429)
    return await call_next(request)

import auth  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from urllib.parse import quote  # noqa: E402

PUBLIC_API_PATHS = {"/api/health"}


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Las rutas nativas de FastAPI exigen la misma sesión que Flask (las de Flask se validan en app.py)."""
    if auth.auth_enabled() and request.url.path not in PUBLIC_API_PATHS:
        is_api_route = any(
            route.matches(request.scope)[0] != Match.NONE
            for route in [*ai.router.routes, *analytics.router.routes]
        )
        if is_api_route:
            from app import app as flask_app
            cookie = request.cookies.get(flask_app.config.get("SESSION_COOKIE_NAME", "session"))
            if not auth.is_authenticated_cookie(flask_app, cookie):
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

# ========================================================
# WebSockets Nativos (Reemplazo de Flask-SocketIO)
# ========================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantener la conexion viva
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

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
