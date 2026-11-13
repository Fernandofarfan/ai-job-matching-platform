from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import logging
import os

from dotenv import load_dotenv
load_dotenv()

from core.templating import templates
from routers import (ai, analytics, pages, tracker, profile, tools,
                     notifications, scraping, files, export, auth)

app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version="1.0.0")


# ── Autenticación + protección CSRF (Origin check) ────────────────────────────
# IMPORTANTE: agregar ANTES que SessionMiddleware para que quede
# "más adentro" (SessionMiddleware debe correr primero y poblar request.session).
from urllib.parse import urlsplit as _urlsplit


def _origin_allowed(origin: str | None, host: str | None) -> bool:
    """
    True si el Origin (si existe) coincide EXACTAMENTE con el Host.
    Sin Origin → True (clientes no-navegador; SameSite=Lax cubre a los
    navegadores que sí envían cookies cross-site en POST).
    """
    if not origin:
        return True
    if not host:
        return False  # Origin sin Host verificable → rechazar
    parts = _urlsplit(origin)
    if parts.scheme not in ("http", "https"):
        return False
    # Comparación exacta de host:puerto (sin endswith → sin bypass por sufijo)
    return parts.netloc == host and parts.path in ("", "/")


class AuthMiddleware(BaseHTTPMiddleware):
    # Rutas públicas (además de /static, /api/health y el propio /logout)
    PUBLIC = auth.PUBLIC_PATHS | {"/logout"}
    # Endpoints habilitados para la extensión de Chrome (Origin chrome-extension://)
    OPEN_API = {"/api/tracker/save-from-extension"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path.startswith("/static") or path == "/api/health" or path == "/sw.js":
            return await call_next(request)

        origin = request.headers.get("origin")
        host = request.headers.get("host")
        is_extension_origin = bool(origin) and \
            _urlsplit(origin).scheme == "chrome-extension"

        # ── CSRF: Origin debe coincidir exactamente con el Host ──
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if is_extension_origin:
                # El origen chrome-extension:// solo se acepta en OPEN_API
                if path not in self.OPEN_API:
                    return JSONResponse(
                        status_code=403,
                        content={"success": False,
                                 "error": "Origen de extensión no permitido aquí"},
                    )
            elif not _origin_allowed(origin, host):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Origen no permitido (CSRF)"},
                )

        if path in self.PUBLIC:
            return await call_next(request)

        session = request.scope.get("session") or {}
        if not session.get("user_id"):
            # La extensión no maneja sesiones: solo su endpoint, solo con
            # su Origin chrome-extension:// (sin Origin → 401 vía curl).
            if is_extension_origin and path in self.OPEN_API:
                return await call_next(request)
            if path.startswith("/api/") or path in ("/status", "/run_test_scraper",
                                                    "/test_task_status"):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "error": "Unauthorized"},
                )
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        return await call_next(request)


app.add_middleware(AuthMiddleware)

# ── Rate limiting para endpoints de IA (protege la cuota de Gemini) ──────────
import time as _time
from collections import deque as _deque, defaultdict as _defaultdict

class AIRateLimitMiddleware(BaseHTTPMiddleware):
    """Ventana deslizante por IP sobre /api/ai/* (default 30 req/min)."""

    def __init__(self, app, window_seconds: int = 60, max_requests: int = 30):
        super().__init__(app)
        self.window = window_seconds
        self.max = max_requests
        self._hits = _defaultdict(_deque)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/ai/"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = _time.monotonic()
        hits = self._hits[ip]
        while hits and hits[0] < now - self.window:
            hits.popleft()
        if len(hits) >= self.max:
            # Purga defensiva: IPs con colas vacías (evita crecimiento eterno)
            if len(self._hits) > 512:
                for stale_ip in [k for k, q in self._hits.items()
                                 if not q or q[-1] < now - self.window]:
                    del self._hits[stale_ip]
            return JSONResponse(
                status_code=429,
                content={"success": False,
                         "error": "Rate limit alcanzado. Probá de nuevo en unos segundos."},
            )
        hits.append(now)
        return await call_next(request)


_ai_rate = int(os.getenv("AI_RATE_LIMIT_PER_MINUTE", "30"))
app.add_middleware(AIRateLimitMiddleware, max_requests=_ai_rate)

# Sesiones (flash messages + datos de conexiones) — requiere itsdangerous
# Se agrega DESPUÉS para que sea la capa externa (corre primero).
_secret = os.getenv('SECRET_KEY')
if not _secret:
    if os.getenv('ENV', '').lower() == 'production':
        raise RuntimeError(
            'SECRET_KEY no está definida. Configurala en el entorno '
            '(obligatoria en producción).')
    _secret = 'empleoia-dev-secret-key-change-me'
    logging.warning('SECRET_KEY no definida — usando clave de DESARROLLO. '
                    'Nunca usar en producción.')
_session_secure = os.getenv('SESSION_SECURE', '').lower() == 'true'
# https_only → cookie con flag Secure + solo enviable por HTTPS
app.add_middleware(SessionMiddleware, secret_key=_secret, same_site='lax',
                   https_only=_session_secure)

# Setup para Archivos Estáticos (CSS, JS)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logging.warning(f"Static directory not found during boot: {e}")

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(analytics.router)
app.include_router(pages.router)
app.include_router(tracker.router)
app.include_router(tracker.router_legacy)
app.include_router(profile.router)
app.include_router(tools.router)
app.include_router(notifications.router)
app.include_router(scraping.router)
app.include_router(files.router)
app.include_router(export.router)


# ── Manejadores de errores globales ───────────────────────────────────────────
def _wants_html(request: Request) -> bool:
    accept = request.headers.get('accept', '')
    return 'text/html' in accept and not request.url.path.startswith('/api/')


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if _wants_html(request):
        try:
            return templates.TemplateResponse(
                request=request, name="error.html",
                context={"code": exc.status_code, "message": str(exc.detail)},
                status_code=exc.status_code,
            )
        except Exception:
            pass
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation error",
                 "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log completo en servidor; al cliente solo mensaje genérico (sin
    # paths/stack/errores SQL que puedan filtrar info interna).
    logging.exception(f"Unhandled error on {request.url.path}: {exc}")
    if _wants_html(request):
        try:
            return templates.TemplateResponse(
                request=request, name="error.html",
                context={"code": 500,
                         "message": "Error interno del servidor. "
                                    "Revisá los logs para más detalles."},
                status_code=500,
            )
        except Exception:
            pass
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Error interno del servidor"},
    )


# ── WebSockets nativos ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Auth/CSRF para WebSockets: SessionMiddleware no cubre scope 'websocket',
    # así que validamos el header Origin (los navegadores siempre lo envían).
    ws_origin = dict(websocket.headers).get("origin")
    ws_host = dict(websocket.headers).get("host")
    if not _origin_allowed(ws_origin, ws_host):
        await websocket.close(code=1008)  # policy violation
        return
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Health check real (MySQL + Redis + Celery) ────────────────────────────────
# ── Service Worker en la raíz (scope '/') ─────────────────────────────────────
from fastapi.responses import FileResponse as _FileResponse


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """
    Sirve el SW desde la raíz: el navegador exige que el scope del SW ('/')
    esté bajo su path. Se sirve desde /static/sw.js el registro con
    scope '/' sería rechazado sin el header Service-Worker-Allowed.
    """
    return _FileResponse(
        "static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/api/health")
async def health_check(request: Request):
    """
    Estado real de las dependencias. Público (lo usan los probes de Docker/GCP):
    devuelve solo flags 'ok'/'error'; el detalle solo para usuarios autenticados.
    """
    checks = {}
    details = {}
    overall = "ok"
    authenticated = bool((request.scope.get("session") or {}).get("user_id"))

    try:
        from core.state import db_manager
        db_manager.ping()
        checks["mysql"] = "ok"
    except Exception as e:
        checks["mysql"] = "error"
        details["mysql"] = str(e)[:120]
        overall = "degraded"

    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = "error"
        details["redis"] = str(e)[:120]
        overall = "degraded"

    try:
        from celery_app import celery
        active = celery.control.inspect(timeout=0.5).ping()
        checks["celery"] = "ok" if active else "no workers"
        if not active:
            overall = "degraded"
    except Exception as e:
        checks["celery"] = "error"
        details["celery"] = str(e)[:120]
        overall = "degraded"

    payload = {
        "status": overall,
        "service": "EmpleoIA API (FastAPI)",
        "checks": checks,
    }
    if authenticated and details:
        payload["details"] = details
    return payload
