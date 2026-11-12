from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

try:
    from ai_engine import analyze_job_complete, copilot_chat
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# /api/ai/copilot lo sirve Flask (web/ai_api.py): arma el contexto del perfil y responde `reply`, que lee el frontend
router = APIRouter(prefix="/api/ai", tags=["ai"])

class JobAnalysisRequest(BaseModel):
    job_title: str
    job_description: str
    resume_text: str = ""

@router.post("/analyze-job")
async def api_analyze_job(request: JobAnalysisRequest):
    """Analiza una oferta laboral con IA (cultura, skills, salario, match)."""
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="Gemini no configurado.")
    
    try:
        result = analyze_job_complete(request.job_title, request.job_description, request.resume_text)
        if not result:
            raise HTTPException(status_code=500, detail="Fallo en inferencia de Gemini")
        return {"success": True, "analysis": result}
    except Exception as e:
        logging.error(f"AI analyze-job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
