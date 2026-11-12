"""Rutas de IA nativas de FastAPI (rate limit y login en main.py)."""
from fastapi import APIRouter

# /api/ai/copilot y /api/ai/analyze-job los sirve Flask (web/ai_api.py): usan el perfil y el CV guardados
router = APIRouter(prefix="/api/ai", tags=["ai"])
