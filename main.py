from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import logging

from routers import views, ai, analytics

app = FastAPI(title="EmpleoIA API", description="FastAPI Core para EmpleoIA", version="1.0.0")

# Setup para Archivos Estáticos (CSS, JS)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logging.warning(f"Static directory not found during boot: {e}")

# Include Routers
app.include_router(ai.router)
app.include_router(analytics.router)

import os  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from limits import parse as parse_rate_limit  # noqa: E402
from limits.storage import storage_from_string  # noqa: E402
from limits.strategies import MovingWindowRateLimiter  # noqa: E402

_ai_rate_limit = parse_rate_limit(os.getenv("AI_RATE_LIMIT", "30 per minute"))
_ai_rate_limiter = MovingWindowRateLimiter(storage_from_string(os.getenv("RATELIMIT_STORAGE_URI", "memory://")))


@app.middleware("http")
async def rate_limit_ai(request: Request, call_next):
    """Aplica AI_RATE_LIMIT a /api/ai/* también cuando lo atiende FastAPI."""
    if request.url.path.startswith("/api/ai/"):
        client_ip = request.client.host if request.client else "unknown"
        if not _ai_rate_limiter.hit(_ai_rate_limit, "fastapi-ai", client_ip):
            return JSONResponse({"error": "Demasiadas solicitudes de IA, probá de nuevo en un minuto"}, status_code=429)
    return await call_next(request)

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
